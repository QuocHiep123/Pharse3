"""M2 lifecycle, trace metrics, timeline and OTel-like export contracts."""

from datetime import datetime
import json

import pytest

from calldiag import config
from calldiag.models import (
    PHASE_LABELS, PHASE_ORDER, AnomalyResult, CallMeta, CallTelemetry, Direction, EventType,
    IncidentInterval, LogLevel, MetricAnomaly, MetricCategory, MetricName, Phase, PhaseSpan, PhaseStatus, TraceEvent,
)
from calldiag.pipeline.phases import (
    compute_trace_metrics, extract_selected_path, localize_phases,
    mark_degraded, to_otel_trace,
)
from calldiag.pipeline.timeline import build_timeline
from calldiag.scenarios import REGISTRY, build_all
from calldiag.utils import at


def make_anomaly(
    anomaly_id: str, source: str, metric: MetricName,
    start_ts: datetime, end_ts: datetime, peak_value: float,
) -> MetricAnomaly:
    return MetricAnomaly(
        anomaly_id=anomaly_id, source=source, metric=metric,
        direction=Direction(config.METRIC_META[metric]["direction"]),
        category=MetricCategory(config.METRIC_META[metric]["category"]),
        start_ts=start_ts, end_ts=end_ts, duration_sec=(end_ts - start_ts).total_seconds() + 1,
        peak_value=peak_value, median_value=peak_value, baseline_value=None, peak_ts=start_ts,
        threshold_abs=config.METRIC_RULES[metric]["abs"], threshold_rel_value=None,
        first_sample_id="sample-first", peak_sample_id="sample-first", last_sample_id="sample-last",
        sample_ids=["sample-first", "sample-last"],
    )


def make_incident(interval_id: str) -> IncidentInterval:
    return IncidentInterval(
        interval_id=interval_id, start_ts=config.BASE_START, end_ts=config.BASE_START,
        duration_sec=1, qos_anomaly_ids=[], resource_anomaly_ids=[],
    )


@pytest.fixture(scope="module")
def scenarios() -> dict[str, CallTelemetry]:
    return build_all()


def event_of(bundle: CallTelemetry, event_type: EventType) -> TraceEvent:
    return next(event for event in bundle.events if event.type == event_type)


def phase_of(phases: list[PhaseSpan], phase: Phase) -> PhaseSpan:
    return next(span for span in phases if span.phase == phase)


def remove_events(bundle: CallTelemetry, *types: EventType) -> None:
    bundle.events = [event for event in bundle.events if event.type not in types]


@pytest.mark.parametrize("sid", REGISTRY)
def test_phase_status_table(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid]
    phases = localize_phases(bundle)
    assert [span.phase for span in phases] == PHASE_ORDER
    expected = REGISTRY[sid].expected.phase_status
    assert {span.phase.value: span.status.value for span in phases} == {
        name: "ok" if status == "degraded" else status for name, status in expected.items()
    }
    by_id = {event.event_id: event for event in bundle.events}
    for span in phases:
        assert span.label == PHASE_LABELS[span.phase]
        assert all(by_id[ref].phase == span.phase for ref in span.event_ids)
        if span.status == PhaseStatus.SKIPPED:
            assert span.start_ts is span.end_ts is span.duration_ms is None
            assert span.start_event_id is span.end_event_id is span.failure_event_id is None
            assert span.event_ids == []
        else:
            assert span.start_event_id in by_id
            assert span.end_event_id in by_id
            assert span.duration_ms == round((span.end_ts - span.start_ts).total_seconds() * 1000)
        if span.status == PhaseStatus.FAILED:
            assert span.failure_event_id == span.end_event_id
            assert span.end_ts == by_id[span.failure_event_id].ts
    termination = phase_of(phases, Phase.TERMINATION)
    assert termination.attrs["end_reason"] == event_of(bundle, EventType.CALL_ENDED).attrs["reason"]
    assert termination.attrs["abnormal_end"] is (sid in {"S3", "S5"})


def test_s1_trace_metrics_reference(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S1"]
    path = extract_selected_path(bundle)
    metrics = compute_trace_metrics(bundle, localize_phases(bundle), path)
    assert metrics.time_to_accept_ms == 1500
    assert metrics.time_to_answer_ms == 350
    assert metrics.ice_gathering_ms == 550
    assert metrics.ice_checking_ms == 1000
    assert metrics.dtls_ms == 200
    assert metrics.time_to_first_media_ms == 4400
    assert metrics.call_duration_ms == 120200
    assert metrics.candidate_counts == {"host": 1, "srflx": 1, "relay": 1}
    assert metrics.selected_pair == path
    assert metrics.end_reason == "normal"
    pair_events = [event for event in bundle.events if event.type in {EventType.ICE_PAIR_FAILED, EventType.ICE_PAIR_SUCCEEDED}]
    assert metrics.pair_results == [
        {"event_id": pair_events[0].event_id, "local_type": "host", "remote_type": "host", "result": "failed", "error": "timeout"},
        {"event_id": pair_events[1].event_id, "local_type": "srflx", "remote_type": "srflx", "result": "failed", "error": "timeout"},
        {"event_id": pair_events[2].event_id, "local_type": "relay", "remote_type": "srflx", "result": "succeeded", "error": None},
    ]


def test_early_failure_trace_metrics(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S3"]
    metrics = compute_trace_metrics(bundle, localize_phases(bundle), extract_selected_path(bundle))
    assert metrics.ice_checking_ms == 30000
    assert metrics.time_to_first_media_ms is metrics.dtls_ms is metrics.selected_pair is None
    assert metrics.call_duration_ms == 33000
    assert metrics.end_reason == "ice_failed"
    bundle = scenarios["S5"]
    metrics = compute_trace_metrics(bundle, localize_phases(bundle), extract_selected_path(bundle))
    assert metrics.time_to_answer_ms is metrics.ice_checking_ms is metrics.time_to_first_media_ms is None
    assert metrics.candidate_counts == {"host": 0, "srflx": 0, "relay": 0}
    assert metrics.pair_results == []
    assert metrics.end_reason == "signaling_timeout"


@pytest.mark.parametrize("sid", ["S0", "S1", "S2", "S4", "S6"])
def test_media_span_and_established_marker(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid]
    media = phase_of(localize_phases(bundle), Phase.MEDIA)
    assert media.start_event_id == event_of(bundle, EventType.DTLS_CONNECTING).event_id
    assert media.end_event_id == event_of(bundle, EventType.FIRST_RTP_RECEIVED).event_id
    assert media.established_ts == event_of(bundle, EventType.FIRST_RTP_RECEIVED).ts
    assert "established_ts" not in media.attrs
    assert media.end_ts == event_of(bundle, EventType.HANGUP).ts
    assert media.end_ts > media.established_ts


@pytest.mark.parametrize("sid", REGISTRY)
def test_phase_spans_round_trip_json(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    for span in localize_phases(scenarios[sid]):
        assert PhaseSpan.model_validate_json(span.model_dump_json()) == span
        assert (span.established_ts is not None) == (span.phase == Phase.MEDIA and span.status == PhaseStatus.OK)


@pytest.mark.parametrize(("sid", "relay"), [("S0", False), ("S1", True), ("S2", False), ("S4", True), ("S6", True)])
def test_selected_path_table(sid: str, relay: bool, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid]
    path = extract_selected_path(bundle)
    assert path is not None
    assert path.event_id == event_of(bundle, EventType.ICE_SELECTED_PAIR).event_id
    assert path.via_turn is relay
    assert path.local_type == ("relay" if relay else "srflx")
    assert path.remote_type == "srflx"
    assert path.turn_server == ("turn-01" if relay else None)


def test_last_selected_pair_is_used(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S0"].model_copy(deep=True)
    original = event_of(bundle, EventType.ICE_SELECTED_PAIR)
    latest = original.model_copy(deep=True, update={
        "event_id": "ev-999", "ts": at(bundle.meta.start_ts, 90),
        "attrs": {"local_type": "relay", "remote_type": "srflx", "via_turn": True,
                  "turn_server": "turn-02", "event_id": "extra-attr", "ts": "extra-attr"},
    })
    # Deliberately not insertion order: the API chooses the latest timestamp.
    bundle.events.insert(0, latest)
    path = extract_selected_path(bundle)
    assert path.event_id == "ev-999"
    assert path.ts == latest.ts
    assert path.via_turn is True
    assert path.turn_server == "turn-02"


def test_ice_without_terminal_event_is_incomplete(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S0"].model_copy(deep=True)
    remove_events(bundle, EventType.ICE_CONNECTED, EventType.ICE_FAILED)
    ice = phase_of(localize_phases(bundle), Phase.ICE)
    assert ice.status == PhaseStatus.INCOMPLETE
    assert ice.end_ts == event_of(bundle, EventType.ICE_SELECTED_PAIR).ts
    assert ice.duration_ms == 1050
    assert ice.failure_event_id is None


def test_offer_answer_success_requires_caller(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S0"].model_copy(deep=True)
    success = event_of(bundle, EventType.SET_REMOTE_DESCRIPTION_OK)
    success.component = bundle.meta.callee
    assert phase_of(localize_phases(bundle), Phase.OFFER_ANSWER).status == PhaseStatus.INCOMPLETE
    bundle.meta.caller = "carol"
    success.component = "carol"
    assert phase_of(localize_phases(bundle), Phase.OFFER_ANSWER).status == PhaseStatus.OK


@pytest.mark.parametrize(("replace_type", "failure_type", "failed_phase"), [
    (EventType.CALL_ACCEPTED, EventType.CALL_REJECTED, Phase.CALL_SETUP),
    (EventType.SET_REMOTE_DESCRIPTION_OK, EventType.SET_REMOTE_DESCRIPTION_FAILED, Phase.OFFER_ANSWER),
    (EventType.ICE_CONNECTED, EventType.ICE_FAILED, Phase.ICE),
    (EventType.FIRST_RTP_RECEIVED, EventType.DTLS_FAILED, Phase.MEDIA),
])
def test_failure_skips_later_phases_but_preserves_termination(
    scenarios: dict[str, CallTelemetry], replace_type: EventType, failure_type: EventType, failed_phase: Phase,
) -> None:
    bundle = scenarios["S0"].model_copy(deep=True)
    event = event_of(bundle, replace_type)
    event.type = failure_type
    event.attrs = {"after_ms": 500} if failure_type == EventType.ICE_FAILED else {}
    phases = localize_phases(bundle)
    failed = phase_of(phases, failed_phase)
    assert failed.status == PhaseStatus.FAILED
    assert failed.failure_event_id == event.event_id
    for later in PHASE_ORDER[PHASE_ORDER.index(failed_phase) + 1:-1]:
        skipped = phase_of(phases, later)
        assert skipped.status == PhaseStatus.SKIPPED
        assert skipped.event_ids == []
        assert skipped.start_ts is skipped.end_ts is skipped.duration_ms is None
    assert phase_of(phases, Phase.TERMINATION).status == PhaseStatus.OK


def test_failure_takes_precedence_over_success(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S0"].model_copy(deep=True)
    connected = event_of(bundle, EventType.ICE_CONNECTED)
    bundle.events.append(connected.model_copy(update={
        "event_id": "ev-999", "type": EventType.ICE_FAILED,
        "ts": at(bundle.meta.start_ts, 4), "attrs": {"after_ms": 1300},
    }))
    phases = localize_phases(bundle)
    assert phase_of(phases, Phase.ICE).status == PhaseStatus.FAILED
    assert phase_of(phases, Phase.MEDIA).status == PhaseStatus.SKIPPED


def test_missing_start_is_skipped(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S0"].model_copy(deep=True)
    remove_events(bundle, EventType.ICE_GATHERING_START)
    ice = phase_of(localize_phases(bundle), Phase.ICE)
    assert ice.status == PhaseStatus.SKIPPED
    assert ice.start_ts is ice.end_ts is ice.duration_ms is None


def test_no_hangup_falls_back_to_call_ended(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S0"].model_copy(deep=True)
    remove_events(bundle, EventType.HANGUP)
    phases = localize_phases(bundle)
    ended = event_of(bundle, EventType.CALL_ENDED)
    media, termination = phase_of(phases, Phase.MEDIA), phase_of(phases, Phase.TERMINATION)
    assert media.end_ts == ended.ts
    assert termination.status == PhaseStatus.OK
    assert termination.start_event_id == termination.end_event_id == ended.event_id
    assert termination.duration_ms == 0


@pytest.mark.parametrize("keep_hangup", [True, False])
def test_missing_call_ended_is_incomplete(scenarios: dict[str, CallTelemetry], keep_hangup: bool) -> None:
    bundle = scenarios["S0"].model_copy(deep=True)
    remove_events(bundle, EventType.CALL_ENDED)
    if not keep_hangup:
        remove_events(bundle, EventType.HANGUP)
    phases = localize_phases(bundle)
    termination, media = phase_of(phases, Phase.TERMINATION), phase_of(phases, Phase.MEDIA)
    assert termination.status == PhaseStatus.INCOMPLETE
    assert "end_reason" not in termination.attrs
    assert media.status == PhaseStatus.OK
    if keep_hangup:
        assert media.end_ts == event_of(bundle, EventType.HANGUP).ts
    else:
        assert media.end_ts is media.duration_ms is None
        assert termination.start_ts is termination.end_ts is termination.duration_ms is None
    metrics = compute_trace_metrics(bundle, phases, extract_selected_path(bundle))
    assert metrics.call_duration_ms is metrics.end_reason is None


@pytest.mark.parametrize(("missing_type", "metric_name"), [
    (EventType.CALL_CREATED, "time_to_accept_ms"), (EventType.CALL_ACCEPTED, "time_to_accept_ms"),
    (EventType.OFFER_SENT, "time_to_answer_ms"), (EventType.ANSWER_RECEIVED, "time_to_answer_ms"),
    (EventType.ICE_GATHERING_START, "ice_gathering_ms"), (EventType.ICE_GATHERING_COMPLETE, "ice_gathering_ms"),
    (EventType.ICE_CHECKING, "ice_checking_ms"), (EventType.ICE_CONNECTED, "ice_checking_ms"),
    (EventType.DTLS_CONNECTING, "dtls_ms"), (EventType.DTLS_CONNECTED, "dtls_ms"),
    (EventType.CALL_CREATED, "time_to_first_media_ms"), (EventType.FIRST_RTP_RECEIVED, "time_to_first_media_ms"),
    (EventType.CALL_CREATED, "call_duration_ms"), (EventType.CALL_ENDED, "call_duration_ms"),
])
def test_missing_event_keeps_timing_none(
    scenarios: dict[str, CallTelemetry], missing_type: EventType, metric_name: str,
) -> None:
    bundle = scenarios["S0"].model_copy(deep=True)
    remove_events(bundle, missing_type)
    metrics = compute_trace_metrics(bundle, localize_phases(bundle), extract_selected_path(bundle))
    assert getattr(metrics, metric_name) is None


def test_empty_events_preserve_missing(bundle: CallTelemetry) -> None:
    bundle.events = []
    phases = localize_phases(bundle)
    assert [p.status for p in phases] == [PhaseStatus.SKIPPED] * 4 + [PhaseStatus.INCOMPLETE]
    assert all(p.start_ts is p.end_ts is p.duration_ms is None for p in phases)
    metrics = compute_trace_metrics(bundle, phases, extract_selected_path(bundle))
    assert all(getattr(metrics, name) is None for name in config.TRACE_METRIC_EVENTS)


@pytest.mark.parametrize("sid", REGISTRY)
def test_timeline_contains_events_and_non_debug_logs(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid]
    timeline = build_timeline(bundle)
    event_items = [item for item in timeline if item.kind == "event"]
    log_items = [item for item in timeline if item.kind == "log"]
    assert {item.ref_id for item in event_items} == {event.event_id for event in bundle.events}
    assert {item.ref_id for item in log_items} == {log.log_id for log in bundle.logs if log.level != LogLevel.DEBUG}
    assert all(item.phase is None for item in log_items)
    keys = [(item.ts, config.TIMELINE_KIND_ORDER[item.kind], item.ref_id) for item in timeline]
    assert keys == sorted(keys)
    assert all("\n" not in item.summary for item in timeline)


def test_timeline_event_summaries(scenarios: dict[str, CallTelemetry]) -> None:
    summaries = {item.summary for item in build_timeline(scenarios["S1"])}
    assert "ICE_CANDIDATE_GATHERED relay 203.0.113.10:49152" in summaries
    assert "ICE_PAIR_FAILED host↔host (timeout)" in summaries
    assert "ICE_PAIR_SUCCEEDED relay↔srflx" in summaries
    assert "ICE_SELECTED_PAIR relay↔srflx via turn-01" in summaries
    assert "CALL_ENDED reason=normal" in summaries
    assert "ICE_SELECTED_PAIR srflx↔srflx (direct)" in {item.summary for item in build_timeline(scenarios["S2"])}


def test_timeline_anomalies_and_kind_ref_ties(bundle: CallTelemetry) -> None:
    # At the same instant: event, anomaly starts, logs, anomaly ends.
    ts = bundle.meta.start_ts
    anomalies = AnomalyResult(skipped=False, anomalies=[
        make_anomaly("an-02", "alice", MetricName.RTT_MS, ts, ts, 334.4),
        make_anomaly("an-01", "alice", MetricName.PACKET_LOSS_PCT, ts, ts, 12.04),
    ])
    first_log = bundle.logs[0]
    bundle.logs.append(first_log.model_copy(update={"log_id": "log-000"}))
    items = [item for item in build_timeline(bundle, anomalies) if item.ts == ts]
    assert [(item.kind, item.ref_id) for item in items] == [
        ("event", "ev-001"), ("anomaly_start", "an-01"), ("anomaly_start", "an-02"),
        ("log", "log-000"), ("log", "log-001"), ("anomaly_end", "an-01"), ("anomaly_end", "an-02"),
    ]
    assert items[1].summary == "ANOMALY packet_loss_pct start (peak 12.0%)"
    assert items[2].summary == "ANOMALY rtt_ms start (peak 334 ms)"
    assert items[6].summary == "ANOMALY rtt_ms end (peak 334 ms)"
    assert all(item.phase == Phase.MEDIA and item.component == "alice" for item in items if item.kind.startswith("anomaly_"))


def test_anomaly_boundaries_keep_their_actual_times(bundle: CallTelemetry) -> None:
    start, end = at(bundle.meta.start_ts, 0.5), at(bundle.meta.start_ts, 1.5)
    result = AnomalyResult(skipped=False, anomalies=[make_anomaly("an-01", "turn-01", MetricName.TURN_CPU_PCT, start, end, 95)])
    items = [item for item in build_timeline(bundle, result) if item.ref_id == "an-01"]
    assert [item.ts for item in items] == [start, end]


def test_mark_degraded_is_pure_and_uses_only_incidents(scenarios: dict[str, CallTelemetry]) -> None:
    phases = localize_phases(scenarios["S1"])
    media = phase_of(phases, Phase.MEDIA)
    media.attrs["nested"] = {"refs": []}
    before = [phase.model_dump() for phase in phases]
    anomalies = AnomalyResult(skipped=False, incidents=[make_incident("inc-01"), make_incident("inc-02")])
    result = mark_degraded(phases, anomalies)
    degraded = phase_of(result, Phase.MEDIA)
    assert degraded.status == PhaseStatus.DEGRADED
    assert degraded.degraded_interval_ids == ["inc-01", "inc-02"]
    assert [phase.model_dump() for phase in phases] == before
    degraded.attrs["nested"]["refs"].append("new")
    assert media.attrs["nested"]["refs"] == []
    assert all(new is not old for new, old in zip(result, phases))
    no_incident = mark_degraded(phases, AnomalyResult(skipped=False))
    assert no_incident == phases
    assert no_incident is not phases
    ts = scenarios["S1"].meta.start_ts
    resource_only = AnomalyResult(skipped=False, anomalies=[make_anomaly("an-01", "turn-01", MetricName.TURN_CPU_PCT, ts, ts, 95)])
    assert mark_degraded(phases, resource_only) == phases


@pytest.mark.parametrize("status", [PhaseStatus.FAILED, PhaseStatus.SKIPPED, PhaseStatus.INCOMPLETE, PhaseStatus.DEGRADED])
def test_mark_degraded_preserves_other_statuses(scenarios: dict[str, CallTelemetry], status: PhaseStatus) -> None:
    phases = localize_phases(scenarios["S1"])
    phase_of(phases, Phase.MEDIA).status = status
    assert mark_degraded(phases, AnomalyResult(skipped=False, incidents=[make_incident("inc-01")])) == phases


@pytest.mark.parametrize("sid", REGISTRY)
def test_otel_trace_json_and_references(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid]
    phases = localize_phases(bundle)
    trace = to_otel_trace(bundle, phases)
    assert json.loads(json.dumps(trace, ensure_ascii=False)) == trace
    assert trace["trace_id"] == bundle.meta.call_id
    root, *spans = trace["spans"]
    assert len(spans) == 5
    assert root["span_id"] == f"{bundle.meta.call_id}/call"
    assert root["parent_span_id"] is None
    assert root["status"] == ("ERROR" if sid in {"S3", "S5"} else "OK")
    assert root["attributes"]["end_reason"] == event_of(bundle, EventType.CALL_ENDED).attrs["reason"]
    by_id = {event.event_id: event for event in bundle.events}
    for phase, span in zip(phases, spans):
        assert span["span_id"] == f"{bundle.meta.call_id}/{phase.phase.value}"
        assert span["parent_span_id"] == root["span_id"]
        assert span["attributes"]["duration_ms"] == phase.duration_ms
        assert span["attributes"]["phase_status"] == phase.status.value
        assert [event["event_id"] for event in span["events"]] == phase.event_ids
        for event in span["events"]:
            original = by_id[event["event_id"]].model_dump(mode="json")
            assert event["name"] == original["type"]
            assert event["ts"] == original["ts"]
            assert event["attributes"] == original["attrs"]


def test_otel_s3_failure_and_skipped_media(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S3"]
    spans = {span["span_id"].rsplit("/", 1)[-1]: span for span in to_otel_trace(bundle, localize_phases(bundle))["spans"]}
    assert spans["ice"]["status"] == spans["call"]["status"] == "ERROR"
    assert spans["media"]["status"] == "UNSET"
    assert spans["media"]["start"] is spans["media"]["end"] is None
    assert spans["media"]["events"] == []


def test_otel_incomplete_and_degraded_status(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S1"].model_copy(deep=True)
    phases = mark_degraded(localize_phases(bundle), AnomalyResult(skipped=False, incidents=[make_incident("inc-01")]))
    media = to_otel_trace(bundle, phases)["spans"][4]
    assert media["status"] == "OK"
    assert media["attributes"]["degraded_interval_ids"] == ["inc-01"]
    assert isinstance(media["attributes"]["established_ts"], str)
    remove_events(bundle, EventType.ICE_CONNECTED)
    assert to_otel_trace(bundle, localize_phases(bundle))["spans"][3]["status"] == "UNSET"


@pytest.mark.parametrize("sid", REGISTRY)
def test_functions_are_deterministic_and_do_not_mutate_telemetry(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid]
    before = bundle.model_dump_json()
    phases = localize_phases(bundle)
    assert phases == localize_phases(bundle)
    path = extract_selected_path(bundle)
    assert path == extract_selected_path(bundle)
    assert build_timeline(bundle) == build_timeline(bundle)
    assert compute_trace_metrics(bundle, phases, path) == compute_trace_metrics(bundle, phases, path)
    assert to_otel_trace(bundle, phases) == to_otel_trace(bundle, phases)
    assert bundle.model_dump_json() == before


class GuardedMeta(CallMeta):
    def __getattribute__(self, name: str) -> object:
        if name in {"scenario_id", "title"}:
            raise AssertionError(f"Pipeline must not read meta.{name}")
        return super().__getattribute__(name)


@pytest.mark.parametrize("sid", REGISTRY)
def test_pipeline_does_not_read_scenario_labels_or_branch_on_call_id(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid].model_copy(deep=True)
    expected_phases = localize_phases(bundle)
    expected_path = extract_selected_path(bundle)
    expected_metrics = compute_trace_metrics(bundle, expected_phases, expected_path)
    expected_timeline = build_timeline(bundle)
    bundle.meta = GuardedMeta.model_validate({
        **bundle.meta.model_dump(), "call_id": "call-without-scenario-hints",
        "scenario_id": "unexpected", "title": "different label",
    })
    for event in bundle.events:
        event.call_id = bundle.meta.call_id
    phases = localize_phases(bundle)
    assert phases == expected_phases
    assert extract_selected_path(bundle) == expected_path
    assert compute_trace_metrics(bundle, phases, extract_selected_path(bundle)) == expected_metrics
    assert build_timeline(bundle) == expected_timeline
    trace = to_otel_trace(bundle, phases)
    assert trace["trace_id"] == "call-without-scenario-hints"


def test_export_and_selected_path_do_not_alias_inputs(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S1"].model_copy(deep=True)
    phases = localize_phases(bundle)
    path = extract_selected_path(bundle)
    metrics = compute_trace_metrics(bundle, phases, path)
    metrics.selected_pair.turn_server = "changed"
    assert path.turn_server == "turn-01"
    trace = to_otel_trace(bundle, phases)
    ice = trace["spans"][3]
    selected = next(event for event in ice["events"] if event["name"] == "ICE_SELECTED_PAIR")
    selected["attributes"]["turn_server"] = "changed"
    assert event_of(bundle, EventType.ICE_SELECTED_PAIR).attrs["turn_server"] == "turn-01"


def test_optional_phase_dates_accept_none_and_defaults_are_independent() -> None:
    params = {
        "phase": Phase.MEDIA, "label": PHASE_LABELS[Phase.MEDIA], "status": PhaseStatus.SKIPPED,
        "start_ts": None, "end_ts": None, "duration_ms": None,
        "start_event_id": None, "end_event_id": None, "event_ids": [],
    }
    first, second = PhaseSpan(**params), PhaseSpan(**params)
    first.attrs["test"] = True
    first.degraded_interval_ids.append("inc-01")
    assert second.attrs == {}
    assert second.degraded_interval_ids == []
