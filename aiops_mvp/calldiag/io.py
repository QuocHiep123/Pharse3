"""Telemetry persistence, validation and dataframe conversion."""

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

import pandas as pd

from calldiag import config
from calldiag.models import EVENT_PHASE, CallTelemetry, EventType, PipelineResult, TraceEvent
from calldiag.utils import offset_sec


def save_bundle(bundle: CallTelemetry, path: Path) -> None:
    validate_bundle(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")


def load_bundle(path: Path) -> CallTelemetry:
    bundle = CallTelemetry.model_validate_json(path.read_text(encoding="utf-8"))
    validate_bundle(bundle)
    return bundle


def save_pipeline_outputs(result: PipelineResult, out: Path) -> tuple[Path, Path, Path]:
    from calldiag.pipeline.phases import to_otel_trace
    from calldiag.pipeline.render import render_markdown

    sid = result.report.scenario_id
    if not sid or sid in {".", ".."} or "/" in sid or "\\" in sid or "\x00" in sid:
        raise ValueError("scenario_id must be a nonempty filename without path separators")
    report_path, markdown_path = out / "reports" / f"{sid}.json", out / "reports" / f"{sid}.md"
    trace_path = out / "traces" / f"{sid}.otel.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result.report.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(result.report), encoding="utf-8")
    trace_path.write_text(json.dumps(to_otel_trace(result.bundle, result.phases), ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path, markdown_path, trace_path


def metrics_to_frame(bundle: CallTelemetry) -> pd.DataFrame:
    columns = ["sample_id", "ts", "t", "source", "direction", "metric", "value"]
    frame = pd.DataFrame([
        {
            "sample_id": sample.sample_id,
            "ts": sample.ts,
            "t": offset_sec(sample.ts, bundle.meta.start_ts),
            "source": sample.source,
            "direction": sample.direction.value,
            "metric": sample.metric.value,
            "value": sample.value,
        }
        for sample in bundle.metrics
    ], columns=columns)
    # Explicit dtypes also preserve NaN for an entirely missing series.
    frame["value"] = frame["value"].astype(float)
    frame["t"] = frame["t"].astype(float)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame


def _validate_attrs(event: TraceEvent) -> None:
    def require(name: str, valid: Callable[[Any], bool], description: str) -> None:
        if name not in event.attrs:
            raise ValueError(f"{event.event_id} ({event.type.value}): missing required attr {name}")
        if not valid(event.attrs[name]):
            raise ValueError(f"{event.event_id} ({event.type.value}): attr {name} must be {description}")

    def text(value: Any) -> bool:
        return isinstance(value, str) and bool(value)

    def integer(value: Any) -> bool:
        return type(value) is int

    def candidate(value: Any) -> bool:
        return isinstance(value, str) and value in config.CANDIDATE_TYPES

    match event.type:
        case EventType.ICE_CANDIDATE_GATHERED:
            require("candidate_type", candidate, "host, srflx or relay")
            require("address", text, "a nonempty string")
        case EventType.ICE_PAIR_SUCCEEDED | EventType.ICE_PAIR_FAILED | EventType.ICE_SELECTED_PAIR:
            require("local_type", candidate, "host, srflx or relay")
            require("remote_type", candidate, "host, srflx or relay")
            if event.type == EventType.ICE_PAIR_FAILED:
                require("error", text, "a nonempty string")
            elif event.type == EventType.ICE_SELECTED_PAIR:
                require("via_turn", lambda v: type(v) is bool, "a bool")
                require("turn_server", lambda v: v is None or text(v), "a string or None")
        case EventType.ICE_FAILED:
            require("after_ms", integer, "an int")
        case EventType.SIGNALING_TIMEOUT:
            require("waited_ms", integer, "an int")
        case EventType.HANGUP:
            require("by", text, "a component string")
            require("reason", text, "a nonempty string")
        case EventType.CALL_ENDED:
            require("reason", lambda v: isinstance(v, str) and v in config.END_REASONS, "a supported termination reason")
        case EventType.FIRST_RTP_RECEIVED:
            require("ssrc", integer, "an int")
            require("kind", lambda v: isinstance(v, str) and v in config.MEDIA_KINDS, "audio or video")


def validate_bundle(bundle: CallTelemetry) -> None:
    start, end = bundle.meta.start_ts, bundle.meta.end_ts
    if end < start:
        raise ValueError("meta.end_ts must be on or after meta.start_ts")

    for records, id_field in (
        (bundle.events, "event_id"), (bundle.logs, "log_id"), (bundle.metrics, "sample_id"),
    ):
        seen: set[str] = set()
        for record in records:
            record_id = getattr(record, id_field)
            if record_id in seen:
                raise ValueError(f"Duplicate {id_field}: {record_id}")
            seen.add(record_id)
            if not start <= record.ts <= end:
                raise ValueError(f"{record_id}: ts {record.ts.isoformat()} outside meta time range")

    for records, id_field in ((bundle.events, "event_id"), (bundle.logs, "log_id")):
        keys = [(record.ts, getattr(record, id_field)) for record in records]
        if keys != sorted(keys):
            raise ValueError(f"{id_field} records must be sorted by (ts, ID)")

    for event in bundle.events:
        if event.phase != EVENT_PHASE[event.type]:
            raise ValueError(f"{event.event_id}: phase {event.phase.value} does not match {event.type.value}")
        _validate_attrs(event)

    for sample in bundle.metrics:
        t = round(offset_sec(sample.ts, start))
        expected = f"m-{sample.source}-{sample.metric.value}-{t:04d}"
        if sample.sample_id != expected:
            raise ValueError(f"Invalid sample_id {sample.sample_id!r}; expected {expected!r}")
