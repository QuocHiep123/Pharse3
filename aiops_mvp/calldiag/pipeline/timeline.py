"""Build an ordered, traceable timeline without inferring a cause."""

from calldiag import config
from calldiag.models import AnomalyResult, CallTelemetry, EventType, Phase, TimelineItem, TraceEvent
from calldiag.utils import fmt_value


def _event_summary(event: TraceEvent) -> str:
    name, attrs = event.type.value, event.attrs
    match event.type:
        case EventType.ICE_CANDIDATE_GATHERED:
            return f"{name} {attrs['candidate_type']} {attrs['address']}"
        case EventType.ICE_PAIR_SUCCEEDED | EventType.ICE_PAIR_FAILED | EventType.ICE_SELECTED_PAIR:
            summary = f"{name} {attrs['local_type']}↔{attrs['remote_type']}"
            if event.type == EventType.ICE_PAIR_FAILED:
                return f"{summary} ({attrs['error']})"
            if event.type == EventType.ICE_SELECTED_PAIR:
                return f"{summary} via {attrs['turn_server']}" if attrs["via_turn"] else f"{summary} (direct)"
            return summary
        case EventType.CALL_ENDED:
            return f"{name} reason={attrs['reason']}"
        case _:
            return name


def build_timeline(
    bundle: CallTelemetry, anomalies: AnomalyResult | None = None,
) -> list[TimelineItem]:
    items = [
        TimelineItem(
            ts=event.ts, kind="event", ref_id=event.event_id, phase=event.phase,
            component=event.component, summary=_event_summary(event),
        )
        for event in bundle.events
    ]
    items.extend(
        TimelineItem(
            ts=log.ts, kind="log", ref_id=log.log_id, phase=None,
            component=log.component, summary=f"{log.level.value} {log.message}",
        )
        for log in bundle.logs
        if config.LOG_LEVEL_WEIGHT[log.level] >= config.LOG_LEVEL_WEIGHT[config.TIMELINE_MIN_LOG_LEVEL]
    )
    if anomalies is not None:
        for anomaly in anomalies.anomalies:
            peak = fmt_value(anomaly.metric, anomaly.peak_value)
            for kind, ts, boundary in (
                ("anomaly_start", anomaly.start_ts, "start"),
                ("anomaly_end", anomaly.end_ts, "end"),
            ):
                items.append(TimelineItem(
                    ts=ts, kind=kind, ref_id=anomaly.anomaly_id, phase=Phase.MEDIA,
                    component=anomaly.source,
                    summary=f"ANOMALY {anomaly.metric.value} {boundary} (peak {peak})",
                ))
    return sorted(items, key=lambda item: (item.ts, config.TIMELINE_KIND_ORDER[item.kind], item.ref_id))
