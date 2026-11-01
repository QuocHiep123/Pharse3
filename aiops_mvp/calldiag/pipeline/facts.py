"""The only FACT factory: observed events, metric calculations and raw logs."""

from typing import Any

from calldiag import config
from calldiag.models import (
    AnomalyResult, CallTelemetry, EvidenceBundle, EventType, Fact, FactKind,
    MetricCategory, MetricName, PathContext, Phase, PhaseSpan, PhaseStatus, TraceMetrics,
)
from calldiag.utils import fmt_time, fmt_value, fmt_window, offset_sec


class FactStore:
    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}

    def add(self, **fields: Any) -> Fact:
        fact = Fact(fact_id=f"F{len(self._facts) + 1}", **fields)
        self._facts[fact.fact_id] = fact
        return fact

    def get(self, fact_id: str) -> Fact:
        return self._facts[fact_id]

    def all(self) -> list[Fact]:
        return list(self._facts.values())

    def query(self, kind: FactKind | None = None, **data_eq: Any) -> list[Fact]:
        return [
            fact for fact in self._facts.values()
            if (kind is None or fact.kind == kind)
            and all(
                (getattr(fact, key) == value if key in {"metric", "source"} else key in fact.data and fact.data[key] == value)
                for key, value in data_eq.items()
            )
        ]

    def ids(self) -> set[str]:
        return set(self._facts)


def _refs(*refs: str | None) -> list[str]:
    return list(dict.fromkeys(ref for ref in refs if ref is not None))


def _has_banned_words(statement: str) -> bool:
    return any(word.lower() in statement.lower() for word in config.BANNED_FACT_WORDS)


def _phase_facts(store: FactStore, bundle: CallTelemetry, phases: list[PhaseSpan]) -> None:
    events = {event.event_id: event for event in bundle.events}
    previous_failure: str | None = None
    for phase in sorted(phases, key=lambda span: list(Phase).index(span.phase)):
        refs = _refs(phase.start_event_id, phase.end_event_id)
        data = {"phase": phase.phase.value, "status": phase.status.value}
        raw = sorted((event for event in bundle.events if event.phase == phase.phase), key=lambda event: (event.ts, event.event_id))
        if phase.status == PhaseStatus.FAILED:
            previous_failure = phase.failure_event_id
            end = events[phase.failure_event_id]
            start = events[phase.start_event_id]
            statement = (
                f"Phase {phase.label}: thất bại lúc {fmt_time(end.ts, ms=True)} ({end.type.value}), "
                f"sau {phase.duration_ms} ms kể từ {start.type.value}."
            )
        elif phase.status == PhaseStatus.SKIPPED:
            refs = _refs(previous_failure, *(event.event_id for event in raw))
            if raw:
                statement = f"Phase {phase.label}: trạng thái skipped; telemetry có {len(raw)} event thuộc phase nhưng thiếu mốc bắt đầu hoặc phase trước đã thất bại."
            else:
                statement = f"Phase {phase.label}: không quan sát thấy event nào của phase này trong telemetry."
        elif phase.status == PhaseStatus.INCOMPLETE:
            statement = (
                f"Phase {phase.label}: bắt đầu lúc {fmt_time(phase.start_ts, ms=True)} nhưng không quan sát thấy event kết thúc."
                if phase.start_ts is not None else
                f"Phase {phase.label}: không quan sát thấy đủ event bắt đầu và kết thúc trong telemetry."
            )
        elif phase.phase == Phase.MEDIA:
            assert phase.established_ts is not None
            ending = fmt_time(phase.end_ts, ms=True) if phase.end_ts is not None else "mốc kết thúc chưa được quan sát"
            statement = f"Phase {phase.label}: media bắt đầu lúc {fmt_time(phase.established_ts, ms=True)} (FIRST_RTP_RECEIVED), kéo dài tới {ending}."
            refs = _refs(*refs, *(event.event_id for event in bundle.events if event.ts == phase.end_ts and event.type in {EventType.HANGUP, EventType.CALL_ENDED}))
        elif phase.phase == Phase.TERMINATION:
            end = events[phase.end_event_id]
            data["end_reason"] = phase.attrs["end_reason"]
            statement = f"Phase {phase.label}: CALL_ENDED lúc {fmt_time(end.ts, ms=True)}, reason={phase.attrs['end_reason']}."
        else:
            end = events[phase.end_event_id]
            statement = f"Phase {phase.label}: hoàn tất lúc {fmt_time(end.ts, ms=True)} ({end.type.value}), thời lượng {phase.duration_ms} ms."
        if not refs and bundle.events:
            # An observed event anchors a statement about absence in this bundle;
            # never fabricate an event ID when the entire trace is empty.
            refs = [min(bundle.events, key=lambda event: (event.ts, event.event_id)).event_id]
        if refs:
            store.add(kind=FactKind.PHASE_STATUS, statement=statement, ts=phase.end_ts,
                      window_start=phase.start_ts, window_end=phase.end_ts, data=data, refs=refs)


def _path_and_checks(store: FactStore, trace: TraceMetrics, path: PathContext) -> None:
    selected = path.selected
    if selected is not None:
        route = f"qua TURN {selected.turn_server or 'chưa rõ server'}" if selected.via_turn else "(trực tiếp, không qua TURN)"
        store.add(
            kind=FactKind.SELECTED_PATH,
            statement=f"Selected candidate pair: {selected.local_type}↔{selected.remote_type} {route}, chọn lúc {fmt_time(selected.ts, ms=True)}.",
            ts=selected.ts, data={
                "local_type": selected.local_type, "remote_type": selected.remote_type,
                "via_turn": selected.via_turn, "turn_server": selected.turn_server,
            }, refs=[selected.event_id],
        )
    if trace.pair_results:
        pairs = trace.pair_results
        succeeded = sum(pair["result"] == "succeeded" for pair in pairs)
        detail = ", ".join(f"{pair['local_type']}↔{pair['remote_type']} {pair['result']}" for pair in pairs)
        store.add(
            kind=FactKind.ICE_CHECKS,
            statement=f"ICE đã kiểm tra {len(pairs)} candidate pair: {succeeded} succeeded, {len(pairs) - succeeded} failed ({detail}).",
            data={"total": len(pairs), "succeeded": succeeded, "failed": len(pairs) - succeeded,
                  "relay_pair_failed": any(pair["result"] == "failed" and "relay" in (pair["local_type"], pair["remote_type"]) for pair in pairs),
                  "relay_candidate_gathered": path.relay_candidate_gathered},
            refs=[pair["event_id"] for pair in pairs],
        )


def _timing_facts(store: FactStore, bundle: CallTelemetry, phases: list[PhaseSpan], trace: TraceMetrics) -> None:
    events = sorted(bundle.events, key=lambda event: (event.ts, event.event_id))
    for phase in phases:
        if phase.status != PhaseStatus.FAILED:
            continue
        if phase.phase == Phase.ICE and trace.ice_checking_ms is not None:
            start = next((event for event in events if event.type == EventType.ICE_CHECKING), None)
            failure = next((event for event in events if event.event_id == phase.failure_event_id and event.type == EventType.ICE_FAILED), None)
            if start is not None and failure is not None:
                store.add(
                    kind=FactKind.TRACE_TIMING, ts=failure.ts,
                    statement=f"ICE checking kéo dài {trace.ice_checking_ms} ms (ICE_CHECKING → ICE_FAILED).",
                    data={"phase": phase.phase.value, "duration_ms": trace.ice_checking_ms},
                    refs=[start.event_id, failure.event_id],
                )
        elif phase.phase == Phase.OFFER_ANSWER:
            start = next((event for event in events if event.type == EventType.OFFER_SENT), None)
            failure = next((event for event in events if event.event_id == phase.failure_event_id and event.type == EventType.SIGNALING_TIMEOUT), None)
            if start is not None and failure is not None:
                waited = failure.attrs["waited_ms"]
                store.add(
                    kind=FactKind.TRACE_TIMING, ts=failure.ts,
                    statement=f"Không nhận được ANSWER sau {waited} ms kể từ OFFER_SENT.",
                    data={"phase": phase.phase.value, "duration_ms": waited}, refs=[start.event_id, failure.event_id],
                )


def _metric_facts(store: FactStore, bundle: CallTelemetry, path: PathContext, anomalies: AnomalyResult) -> None:
    # anomaly_id order is chronological, so FACT IDs follow the incident's timeline.
    for anomaly in sorted(anomalies.anomalies, key=lambda a: a.anomaly_id):
        meta = config.METRIC_META[anomaly.metric]
        location = anomaly.source + (f", {anomaly.direction.value}" if anomaly.direction.value != "none" else "")
        label = f"{meta['label']} ({location})"
        median, peak = fmt_value(anomaly.metric, anomaly.median_value), fmt_value(anomaly.metric, anomaly.peak_value)
        higher = meta["worse"] == "higher"
        extremum = "đỉnh" if higher else "thấp nhất"
        if anomaly.baseline_value is not None:
            change = "tăng từ" if higher else "giảm từ"
            to = "lên" if higher else "xuống"
            statement = f"{label} {change} {fmt_value(anomaly.metric, anomaly.baseline_value)} {to} {median} ({extremum} {peak} lúc {fmt_time(anomaly.peak_ts)})"
        else:
            comparison = "cao hơn hoặc bằng" if higher else "thấp hơn hoặc bằng"
            statement = f"{label} ở mức {median} ({extremum} {peak}), {comparison} ngưỡng {fmt_value(anomaly.metric, anomaly.threshold_abs)}"
        statement += f" trong {fmt_window(anomaly.start_ts, anomaly.end_ts)}."
        on_path: bool | None = anomaly.source in path.media_components if path.selected is not None else None
        if anomaly.source in (bundle.meta.caller, bundle.meta.callee):
            on_path = True
        store.add(
            kind=FactKind.METRIC_CHANGE, statement=statement, ts=anomaly.start_ts,
            window_start=anomaly.start_ts, window_end=anomaly.end_ts,
            source=anomaly.source, metric=anomaly.metric, direction=anomaly.direction,
            value_before=anomaly.baseline_value, value_after=anomaly.median_value,
            value_peak=anomaly.peak_value, unit=meta["unit"],
            data={"metric": anomaly.metric.value, "category": anomaly.category.value,
                  "anomaly_id": anomaly.anomaly_id, "interval_ids": list(anomaly.interval_ids),
                  "on_path": on_path, "start_offset_sec": offset_sec(anomaly.start_ts, bundle.meta.start_ts)},
            refs=_refs(anomaly.anomaly_id, anomaly.first_sample_id, anomaly.peak_sample_id),
        )
    for summary in anomalies.summaries:
        category = config.METRIC_META[summary.metric]["category"]
        if summary.median is None or summary.missing_ratio >= config.MISSING_RATIO_THRESHOLD:
            continue
        if summary.scope == "media_phase":
            if anomalies.incidents or anomalies.skipped or category != "qos":
                continue
            # A short spike can cross the absolute threshold without satisfying
            # the duration/relative rules. State exactly what was detected.
            if any(a.source == summary.source and a.direction == summary.direction and a.metric == summary.metric for a in anomalies.anomalies):
                continue
            stats = f"p95 {fmt_value(summary.metric, summary.p95)}"
        else:
            if category != "resource" or any(
                a.source == summary.source and a.direction == summary.direction and a.metric == summary.metric
                and summary.interval_id in a.interval_ids for a in anomalies.anomalies
            ):
                continue
            stats = f"max {fmt_value(summary.metric, summary.max)}"
        refs = _refs(summary.first_sample_id, summary.last_sample_id)
        if refs:
            store.add(
                kind=FactKind.METRIC_LEVEL,
                statement=f"{config.METRIC_META[summary.metric]['label']} ({summary.source}) median {fmt_value(summary.metric, summary.median)}, {stats} trong {fmt_window(summary.window_start, summary.window_end)}; không ghi nhận anomaly theo rule.",
                window_start=summary.window_start, window_end=summary.window_end,
                source=summary.source, metric=summary.metric, direction=summary.direction,
                value_after=summary.median, unit=config.METRIC_META[summary.metric]["unit"],
                data={"metric": summary.metric.value, "category": category, "scope": summary.scope,
                      **({"interval_id": summary.interval_id} if summary.scope == "interval" else {}), "anomalous": False},
                refs=refs,
            )
    for missing in anomalies.missing:
        store.add(
            kind=FactKind.MISSING_DATA,
            statement=f"{config.METRIC_META[missing.metric]['label']} ({missing.source}): không có dữ liệu trong telemetry ({missing.missing_ratio:.0%} sample null) trong {fmt_window(missing.window_start, missing.window_end)}.",
            window_start=missing.window_start, window_end=missing.window_end,
            source=missing.source, metric=missing.metric, unit=config.METRIC_META[missing.metric]["unit"],
            data={"metric": missing.metric.value, "source": missing.source, "missing_ratio": missing.missing_ratio},
            refs=list(missing.sample_ids),
        )


def _log_facts(store: FactStore, evidence: list[EvidenceBundle]) -> None:
    logs = {log.log_id: log for item in reversed(evidence) for log in item.related_logs if (
        config.LOG_LEVEL_WEIGHT[log.level] >= config.LOG_LEVEL_WEIGHT[config.CORRELATION_WARNING_LEVEL]
        and not _has_banned_words(f'{log.component} {log.level.value} lúc {fmt_time(log.ts)}: "{log.message}"')
    )}
    selected = sorted(logs.values(), key=lambda log: (-config.LOG_LEVEL_WEIGHT[log.level], log.ts, log.log_id))[:config.MAX_LOG_FACTS]
    for log in sorted(selected, key=lambda log: (log.ts, log.log_id)):
        store.add(
            kind=FactKind.LOG_EVENT, ts=log.ts, source=log.component,
            statement=f'{log.component} {log.level.value} lúc {fmt_time(log.ts)}: "{log.message}"',
            data={"log_id": log.log_id, "component": log.component, "level": log.level.value,
                  "category": log.category.value, "on_path": log.on_path, "same_call": log.same_call},
            refs=[log.log_id],
        )


def extract_facts(
    bundle: CallTelemetry, phases: list[PhaseSpan], trace: TraceMetrics,
    path_ctx: PathContext, anomalies: AnomalyResult, evidence: list[EvidenceBundle],
) -> FactStore:
    store = FactStore()
    _phase_facts(store, bundle, phases)
    _path_and_checks(store, trace, path_ctx)
    _timing_facts(store, bundle, phases, trace)
    _metric_facts(store, bundle, path_ctx, anomalies)
    _log_facts(store, evidence)
    valid_refs = (
        {event.event_id for event in bundle.events} | {log.log_id for log in bundle.logs}
        | {sample.sample_id for sample in bundle.metrics} | {a.anomaly_id for a in anomalies.anomalies}
        | {incident.interval_id for incident in anomalies.incidents}
    )
    for fact in store.all():
        assert fact.refs, f"{fact.fact_id}: FACT requires refs"
        assert set(fact.refs) <= valid_refs, f"{fact.fact_id}: unresolved FACT refs"
        assert not _has_banned_words(fact.statement), f"{fact.fact_id}: banned FACT words"
    return store
