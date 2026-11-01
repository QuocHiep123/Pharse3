"""Localize lifecycle phases and derive timing/path data from trace events."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from calldiag import config
from calldiag.models import (
    PHASE_LABELS, PHASE_ORDER, AnomalyResult, CallTelemetry, EventType, Phase, PhaseSpan,
    PhaseStatus, SelectedPath, TraceEvent, TraceMetrics,
)


def _ordered_events(bundle: CallTelemetry) -> list[TraceEvent]:
    return sorted(bundle.events, key=lambda event: (event.ts, event.event_id))


def _first(
    events: Sequence[TraceEvent], *types: EventType, after: datetime | None = None,
) -> TraceEvent | None:
    return next((event for event in events if event.type in types and (after is None or event.ts >= after)), None)


def _duration_ms(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() * config.MILLISECONDS_PER_SECOND)


def _span(
    phase: Phase, status: PhaseStatus, events: Sequence[TraceEvent], *,
    start: TraceEvent | None = None, end: TraceEvent | None = None,
    time_end: TraceEvent | None = None, failure: TraceEvent | None = None,
    established: TraceEvent | None = None, attrs: dict[str, Any] | None = None,
) -> PhaseSpan:
    start_ts = start.ts if start is not None else None
    end_ts = time_end.ts if time_end is not None else None
    return PhaseSpan(
        phase=phase, label=PHASE_LABELS[phase], status=status,
        start_ts=start_ts, end_ts=end_ts, duration_ms=_duration_ms(start_ts, end_ts),
        established_ts=established.ts if established is not None else None,
        start_event_id=start.event_id if start is not None else None,
        end_event_id=end.event_id if end is not None else None,
        failure_event_id=failure.event_id if failure is not None else None,
        event_ids=[event.event_id for event in events], attrs=attrs if attrs is not None else {},
    )


def localize_phases(bundle: CallTelemetry) -> list[PhaseSpan]:
    events = _ordered_events(bundle)
    grouped = {phase: [event for event in events if event.phase == phase] for phase in PHASE_ORDER}
    phases: list[PhaseSpan] = []
    failed = False
    for phase in PHASE_ORDER:
        phase_events = grouped[phase]
        if phase == Phase.TERMINATION:
            ended = _first(phase_events, EventType.CALL_ENDED)
            start = _first(phase_events, EventType.HANGUP) or ended
            attrs = {} if ended is None else {
                "end_reason": ended.attrs["reason"],
                "abnormal_end": ended.attrs["reason"] != "normal",
            }
            last = phase_events[-1] if phase_events else None
            phases.append(_span(
                phase, PhaseStatus.OK if ended is not None else PhaseStatus.INCOMPLETE,
                phase_events, start=start, end=ended or last, time_end=ended or last, attrs=attrs,
            ))
            continue

        if failed:
            phases.append(_span(phase, PhaseStatus.SKIPPED, ()))
            continue
        rule = config.PHASE_EVENT_RULES[phase.value]
        start = _first(phase_events, EventType(rule["start"]))
        if start is None:
            phases.append(_span(phase, PhaseStatus.SKIPPED, ()))
            continue
        failure = _first(phase_events, *(EventType(name) for name in rule["failures"]), after=start.ts)
        if failure is not None:
            phases.append(_span(phase, PhaseStatus.FAILED, phase_events,
                                start=start, end=failure, time_end=failure, failure=failure))
            failed = True
            continue
        success = next((
            event for event in phase_events
            if event.type == rule["success"] and event.ts >= start.ts
            and (phase != Phase.OFFER_ANSWER or event.component == bundle.meta.caller)
        ), None)
        if success is None:
            last = phase_events[-1]
            phases.append(_span(phase, PhaseStatus.INCOMPLETE, phase_events, start=start, end=last, time_end=last))
            continue

        time_end = success
        established = None
        if phase == Phase.MEDIA:
            time_end = _first(events, EventType.HANGUP, after=success.ts)
            if time_end is None:
                time_end = _first(events, EventType.CALL_ENDED, after=success.ts)
            established = success
        phases.append(_span(phase, PhaseStatus.OK, phase_events, start=start, end=success,
                            time_end=time_end, established=established))
    return phases


def extract_selected_path(bundle: CallTelemetry) -> SelectedPath | None:
    event = next((event for event in reversed(_ordered_events(bundle)) if event.type == EventType.ICE_SELECTED_PAIR), None)
    if event is None:
        return None
    return SelectedPath(
        event_id=event.event_id, ts=event.ts,
        local_type=event.attrs["local_type"], remote_type=event.attrs["remote_type"],
        via_turn=event.attrs["via_turn"], turn_server=event.attrs["turn_server"],
    )


def compute_trace_metrics(
    bundle: CallTelemetry, phases: list[PhaseSpan], path: SelectedPath | None,
) -> TraceMetrics:
    # These durations measure event pairs, independently of the display span
    # (notably Media, whose end_ts is HANGUP rather than FIRST_RTP_RECEIVED).
    events = _ordered_events(bundle)
    durations: dict[str, int | None] = {}
    for name, (start_type, end_types) in config.TRACE_METRIC_EVENTS.items():
        start = _first(events, EventType(start_type))
        end = _first(events, *(EventType(t) for t in end_types), after=start.ts) if start is not None else None
        durations[name] = _duration_ms(start.ts if start is not None else None, end.ts if end is not None else None)

    counts = {candidate_type: 0 for candidate_type in sorted(config.CANDIDATE_TYPES)}
    pairs: list[dict[str, Any]] = []
    for event in events:
        if event.type == EventType.ICE_CANDIDATE_GATHERED:
            counts[event.attrs["candidate_type"]] += 1
        elif event.type in (EventType.ICE_PAIR_SUCCEEDED, EventType.ICE_PAIR_FAILED):
            pairs.append({
                "event_id": event.event_id, "local_type": event.attrs["local_type"],
                "remote_type": event.attrs["remote_type"],
                "result": "succeeded" if event.type == EventType.ICE_PAIR_SUCCEEDED else "failed",
                "error": event.attrs.get("error"),
            })
    ended = _first(events, EventType.CALL_ENDED)
    return TraceMetrics(
        **durations, candidate_counts=counts, pair_results=pairs,
        selected_pair=path.model_copy(deep=True) if path is not None else None,
        end_reason=ended.attrs["reason"] if ended is not None else None,
    )


def mark_degraded(phases: list[PhaseSpan], anomalies: AnomalyResult) -> list[PhaseSpan]:
    result = [phase.model_copy(deep=True) for phase in phases]
    if anomalies.incidents:
        for phase in result:
            if phase.phase == Phase.MEDIA and phase.status == PhaseStatus.OK:
                phase.status = PhaseStatus.DEGRADED
                phase.degraded_interval_ids = [incident.interval_id for incident in anomalies.incidents]
    return result


def to_otel_trace(bundle: CallTelemetry, phases: list[PhaseSpan]) -> dict[str, Any]:
    """Return an OTel-like, JSON-serializable trace; perform no file I/O."""
    events = _ordered_events(bundle)
    ended = _first(events, EventType.CALL_ENDED)
    root_id = f"{bundle.meta.call_id}/call"
    spans: list[dict[str, Any]] = [{
        "span_id": root_id, "parent_span_id": None, "name": "call",
        "start": bundle.meta.start_ts.isoformat().replace("+00:00", "Z"),
        "end": bundle.meta.end_ts.isoformat().replace("+00:00", "Z"),
        "status": "ERROR" if any(phase.status == PhaseStatus.FAILED for phase in phases) else "OK",
        "attributes": {"end_reason": ended.attrs["reason"] if ended is not None else None},
    }]
    for phase in sorted(phases, key=lambda span: PHASE_ORDER.index(span.phase)):
        serialized = phase.model_dump(mode="json")
        span_events = []
        for event in events:
            if event.event_id in phase.event_ids:
                event_data = event.model_dump(mode="json")
                span_events.append({
                    "name": event.type.value, "ts": event_data["ts"],
                    "attributes": event_data["attrs"], "event_id": event.event_id,
                })
        spans.append({
            "span_id": f"{bundle.meta.call_id}/{phase.phase.value}",
            "parent_span_id": root_id, "name": phase.label,
            "start": serialized["start_ts"], "end": serialized["end_ts"],
            "status": config.OTEL_PHASE_STATUS[phase.status],
            "attributes": {
                **serialized["attrs"], "phase_status": phase.status.value,
                "duration_ms": phase.duration_ms,
                **({"established_ts": serialized["established_ts"]} if phase.established_ts is not None else {}),
                "degraded_interval_ids": list(phase.degraded_interval_ids),
            },
            "events": span_events,
        })
    return {"trace_id": bundle.meta.call_id, "spans": spans}
