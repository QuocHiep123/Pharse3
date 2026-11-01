from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

from calldiag import config
from calldiag.io import load_bundle, metrics_to_frame, save_bundle, validate_bundle
from calldiag.models import EVENT_PHASE, CallMeta, CallTelemetry, EventType, MetricName, Phase
from calldiag.utils import at, fmt_time, fmt_value, fmt_window, offset_sec


def test_round_trip(bundle: CallTelemetry, tmp_path: Path) -> None:
    path = tmp_path / "nested" / "telemetry.json"
    save_bundle(bundle, path)
    assert path.read_text(encoding="utf-8") == bundle.model_dump_json(indent=2)
    assert "Z\"" in path.read_text(encoding="utf-8")
    assert load_bundle(path) == bundle
    assert CallTelemetry.model_validate_json(bundle.model_dump_json()) == bundle


def test_enum_and_metric_maps_are_complete() -> None:
    assert set(EVENT_PHASE) == set(EventType)
    assert set(config.METRIC_META) == set(MetricName)


@pytest.mark.parametrize("field", ["events", "logs", "metrics"])
def test_duplicate_ids_rejected(bundle: CallTelemetry, field: str) -> None:
    records = getattr(bundle, field)
    records.append(records[0].model_copy(deep=True))
    with pytest.raises(ValueError, match="Duplicate"):
        validate_bundle(bundle)


def test_wrong_phase_rejected(bundle: CallTelemetry) -> None:
    bundle.events[0].phase = Phase.MEDIA
    with pytest.raises(ValueError, match="phase.*does not match"):
        validate_bundle(bundle)


@pytest.mark.parametrize("field", ["events", "logs", "metrics"])
@pytest.mark.parametrize("offset", [-0.001, 2.001])
def test_timestamp_outside_bounds_rejected(bundle: CallTelemetry, field: str, offset: float) -> None:
    getattr(bundle, field)[0].ts = at(config.BASE_START, offset)
    with pytest.raises(ValueError, match="outside meta time range"):
        validate_bundle(bundle)


def test_invalid_meta_time_range_rejected(bundle: CallTelemetry) -> None:
    bundle.meta.end_ts = at(bundle.meta.start_ts, -1)
    with pytest.raises(ValueError, match="meta.end_ts"):
        validate_bundle(bundle)


@pytest.mark.parametrize("field", ["events", "logs"])
@pytest.mark.parametrize("tie", [False, True])
def test_order_and_tie_break_rejected(bundle: CallTelemetry, field: str, tie: bool) -> None:
    records = getattr(bundle, field)
    if tie:
        records[1].ts = records[0].ts
    records.reverse()
    with pytest.raises(ValueError, match="sorted by"):
        validate_bundle(bundle)


@pytest.mark.parametrize("sample_id", ["m-alice-rtt_ms-0002", "m-bob-rtt_ms-0001", "m-alice-jitter_ms-0001", "m-alice-rtt_ms-1"])
def test_sample_id_matches_source_metric_and_offset(bundle: CallTelemetry, sample_id: str) -> None:
    bundle.metrics[0].sample_id = sample_id
    with pytest.raises(ValueError, match="Invalid sample_id"):
        validate_bundle(bundle)


def test_sample_id_rounds_fractional_offset(bundle: CallTelemetry) -> None:
    bundle.metrics[0].ts = at(config.BASE_START, 1.49)
    validate_bundle(bundle)


ATTR_CASES: list[tuple[EventType, dict[str, Any]]] = [
    (EventType.ICE_CANDIDATE_GATHERED, {"candidate_type": "relay", "address": "203.0.113.10:49152"}),
    (EventType.ICE_PAIR_SUCCEEDED, {"local_type": "relay", "remote_type": "srflx"}),
    (EventType.ICE_PAIR_FAILED, {"local_type": "host", "remote_type": "host", "error": "timeout"}),
    (EventType.ICE_SELECTED_PAIR, {"local_type": "relay", "remote_type": "srflx", "via_turn": True, "turn_server": "turn-01"}),
    (EventType.ICE_FAILED, {"after_ms": 30000}),
    (EventType.SIGNALING_TIMEOUT, {"waited_ms": 10000}),
    (EventType.HANGUP, {"by": "alice", "reason": "normal"}),
    (EventType.CALL_ENDED, {"reason": "normal"}),
    (EventType.FIRST_RTP_RECEIVED, {"ssrc": 1234567, "kind": "video"}),
]


@pytest.mark.parametrize(("event_type", "attrs"), ATTR_CASES)
def test_required_attrs_accepted(bundle: CallTelemetry, event_type: EventType, attrs: dict[str, Any]) -> None:
    event = bundle.events[0]
    event.type, event.phase, event.attrs = event_type, EVENT_PHASE[event_type], attrs.copy()
    validate_bundle(bundle)


@pytest.mark.parametrize(("event_type", "attrs", "missing"), [
    (event_type, attrs, key) for event_type, attrs in ATTR_CASES for key in attrs
])
def test_every_required_attr_is_checked(
    bundle: CallTelemetry, event_type: EventType, attrs: dict[str, Any], missing: str,
) -> None:
    event = bundle.events[0]
    event.type, event.phase, event.attrs = event_type, EVENT_PHASE[event_type], attrs.copy()
    del event.attrs[missing]
    with pytest.raises(ValueError, match=f"missing required attr {missing}"):
        validate_bundle(bundle)


@pytest.mark.parametrize(("event_type", "key", "bad_value"), [
    (EventType.ICE_CANDIDATE_GATHERED, "candidate_type", "unknown"),
    (EventType.ICE_CANDIDATE_GATHERED, "address", 123),
    (EventType.ICE_SELECTED_PAIR, "via_turn", "false"),
    (EventType.ICE_SELECTED_PAIR, "turn_server", False),
    (EventType.ICE_FAILED, "after_ms", True),
    (EventType.SIGNALING_TIMEOUT, "waited_ms", "10000"),
    (EventType.CALL_ENDED, "reason", "unknown"),
    (EventType.FIRST_RTP_RECEIVED, "ssrc", True),
    (EventType.FIRST_RTP_RECEIVED, "kind", "data"),
])
def test_invalid_attrs_rejected(bundle: CallTelemetry, event_type: EventType, key: str, bad_value: Any) -> None:
    event = bundle.events[0]
    event.type, event.phase = event_type, EVENT_PHASE[event_type]
    event.attrs = next(attrs.copy() for kind, attrs in ATTR_CASES if kind == event_type)
    event.attrs[key] = bad_value
    with pytest.raises(ValueError, match=f"attr {key} must be"):
        validate_bundle(bundle)


def test_dataframe_preserves_missing_and_time(bundle: CallTelemetry) -> None:
    frame = metrics_to_frame(bundle)
    assert list(frame.columns) == ["sample_id", "ts", "t", "source", "direction", "metric", "value"]
    assert frame.loc[0, "t"] == 1.0
    assert pd.isna(frame.loc[0, "value"])
    assert frame.loc[0, "ts"] == bundle.metrics[0].ts
    assert frame.loc[0, "metric"] == "rtt_ms"
    assert frame.loc[0, "direction"] == "none"
    bundle.metrics[0].value = 0.0
    assert metrics_to_frame(bundle).loc[0, "value"] == 0.0


def test_empty_dataframe_has_expected_columns(bundle: CallTelemetry) -> None:
    bundle.metrics = []
    frame = metrics_to_frame(bundle)
    assert frame.empty
    assert list(frame.columns) == ["sample_id", "ts", "t", "source", "direction", "metric", "value"]


def test_io_rejects_invalid_data(bundle: CallTelemetry, tmp_path: Path) -> None:
    del bundle.events[1].attrs["via_turn"]
    path = tmp_path / "bad.json"
    with pytest.raises(ValueError, match="via_turn"):
        save_bundle(bundle, path)
    assert not path.exists()
    path.write_text(bundle.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="via_turn"):
        load_bundle(path)


@pytest.mark.parametrize("field", ["start_ts", "end_ts"])
def test_naive_meta_timestamps_rejected(bundle: CallTelemetry, field: str) -> None:
    data = bundle.meta.model_dump()
    data[field] = data[field].replace(tzinfo=None)
    with pytest.raises(ValidationError, match="timezone"):
        CallMeta.model_validate(data)


@pytest.mark.parametrize("field", ["events", "logs", "metrics"])
def test_naive_record_timestamps_rejected(bundle: CallTelemetry, field: str) -> None:
    record = getattr(bundle, field)[0]
    data = record.model_dump()
    data["ts"] = data["ts"].replace(tzinfo=None)
    with pytest.raises(ValidationError, match="timezone"):
        type(record).model_validate(data)


def test_aware_timestamps_normalized_to_utc(bundle: CallTelemetry) -> None:
    data = bundle.meta.model_dump()
    data["start_ts"] = data["start_ts"].astimezone(timezone(timedelta(hours=7)))
    meta = CallMeta.model_validate(data)
    assert meta.start_ts == config.BASE_START
    assert meta.start_ts.tzinfo == UTC
    assert '"start_ts":"2026-10-31T10:20:00Z"' in meta.model_dump_json()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_metric_rejected(bundle: CallTelemetry, value: float) -> None:
    data = bundle.metrics[0].model_dump()
    data["value"] = value
    with pytest.raises(ValidationError):
        type(bundle.metrics[0]).model_validate(data)


def test_defaults_are_independent(bundle: CallTelemetry) -> None:
    first = CallMeta.model_validate(bundle.meta.model_dump(exclude={"missing_sources"}))
    second = CallMeta.model_validate(bundle.meta.model_dump(exclude={"missing_sources"}))
    first.missing_sources.append("missing")
    assert second.missing_sources == []


def test_time_and_value_helpers() -> None:
    assert fmt_value("packet_loss_pct", 12.04) == "12.0%"
    assert fmt_value("rtt_ms", 309.6) == "310 ms"
    assert fmt_value(MetricName.TURN_CPU_PCT, 95) == "95%"
    assert fmt_value("rtt_ms", None) == "missing"
    assert offset_sec(at(config.BASE_START, 80.31), config.BASE_START) == 80.31
    assert fmt_time(at(config.BASE_START, 80.31)) == "10:21:20"
    assert fmt_time(at(config.BASE_START, 80.31), ms=True) == "10:21:20.310"
    assert fmt_window(at(config.BASE_START, 79), at(config.BASE_START, 103)) == "10:21:19–10:21:43"
    assert at(config.BASE_START, 0.0006) == config.BASE_START + timedelta(milliseconds=1)
    assert at(config.BASE_START, 0.9996) == config.BASE_START + timedelta(seconds=1)
    assert at(datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC), 0.9996) == datetime(2026, 11, 1, tzinfo=UTC)
