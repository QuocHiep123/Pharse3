"""Correlate observed logs with lifecycle failures or QoS intervals."""

from datetime import datetime, timedelta

from calldiag import config
from calldiag.models import (
    AnomalyResult, CallTelemetry, CorrelatedLog, EvidenceBundle, EvidenceFocus,
    EventType, PathContext, Phase, PhaseSpan, PhaseStatus, SelectedPath,
)
from calldiag.utils import fmt_window, offset_sec


def build_path_context(bundle: CallTelemetry, path: SelectedPath | None) -> PathContext:
    gathered = any(event.type == EventType.ICE_CANDIDATE_GATHERED and event.attrs["candidate_type"] == "relay" for event in bundle.events)
    caller, callee = bundle.meta.caller, bundle.meta.callee
    control = [caller, callee, config.SIGNALING]
    if gathered:
        control.append(bundle.meta.turn_server)
    media: list[str] = []
    description = "chưa có selected pair"
    if path is not None:
        media = [caller, callee]
        pair = f"{path.local_type}↔{path.remote_type}"
        if path.via_turn:
            if path.turn_server is not None:
                media.insert(1, path.turn_server)
                control.append(path.turn_server)
            description = f"{pair} qua {path.turn_server or 'TURN chưa rõ server'}"
        else:
            description = f"{pair} (trực tiếp)"
    return PathContext(
        selected=path.model_copy(deep=True) if path is not None else None,
        via_turn=path.via_turn if path is not None else None,
        media_components=media, control_components=list(dict.fromkeys(control)),
        relay_candidate_gathered=gathered, description=description,
    )


def _related_logs(
    bundle: CallTelemetry, path: PathContext, focus: EvidenceFocus, focus_ref: str | None,
    focus_start: datetime, window_start: datetime, window_end: datetime,
) -> list[CorrelatedLog]:
    components = path.control_components if focus == EvidenceFocus.PHASE_FAILURE else path.media_components
    categories = config.INCIDENT_LOG_CATEGORIES if focus == EvidenceFocus.INCIDENT_INTERVAL else (
        config.PHASE_FAILURE_LOG_CATEGORIES.get(focus_ref, frozenset()) if focus == EvidenceFocus.PHASE_FAILURE else frozenset()
    )
    result: list[CorrelatedLog] = []
    for log in bundle.logs:
        weight = config.LOG_LEVEL_WEIGHT[log.level]
        if not window_start <= log.ts <= window_end or weight < config.LOG_LEVEL_WEIGHT[config.CORRELATION_MIN_LOG_LEVEL]:
            continue
        warning = weight >= config.LOG_LEVEL_WEIGHT[config.CORRELATION_WARNING_LEVEL]
        if focus == EvidenceFocus.NONE and not warning:
            continue
        same_call = None if log.call_id is None else log.call_id == bundle.meta.call_id
        on_path = log.component in components
        score = weight + config.CORRELATION_ON_PATH_BONUS * on_path + config.CORRELATION_CATEGORY_BONUS * (log.category in categories)
        if same_call is False:
            score -= config.CORRELATION_OTHER_CALL_PENALTY
        if warning or score >= config.RELATED_LOG_MIN_SCORE:
            result.append(CorrelatedLog(
                log_id=log.log_id, ts=log.ts, component=log.component, level=log.level,
                category=log.category, message=log.message, same_call=same_call, on_path=on_path,
                lag_sec=offset_sec(log.ts, focus_start), score=score,
            ))
    return sorted(result, key=lambda log: (-log.score, log.ts, log.log_id))


def correlate(
    bundle: CallTelemetry, phases: list[PhaseSpan], anomalies: AnomalyResult, path_ctx: PathContext,
) -> list[EvidenceBundle]:
    # Each focus is (kind, ref, start, end, window start/end, resource IDs).
    focuses: list[tuple[EvidenceFocus, str | None, datetime, datetime, datetime, datetime, list[str]]] = []
    failed = next((p for p in phases if p.phase != Phase.TERMINATION and p.status == PhaseStatus.FAILED), None)
    if failed is not None:
        assert failed.start_ts is not None and failed.end_ts is not None
        focuses.append((EvidenceFocus.PHASE_FAILURE, failed.phase.value, failed.start_ts, failed.end_ts,
                        failed.start_ts, failed.end_ts + timedelta(seconds=config.PHASE_FAILURE_POST_SEC), []))
    elif anomalies.incidents:
        for incident in sorted(anomalies.incidents, key=lambda inc: (inc.start_ts, inc.interval_id)):
            focuses.append((EvidenceFocus.INCIDENT_INTERVAL, incident.interval_id, incident.start_ts, incident.end_ts,
                            incident.start_ts - timedelta(seconds=config.CORRELATION_PRE_SEC),
                            incident.end_ts + timedelta(seconds=config.CORRELATION_POST_SEC), list(incident.resource_anomaly_ids)))
    else:
        media = next((p for p in phases if p.phase == Phase.MEDIA), None)
        start, end = bundle.meta.start_ts, bundle.meta.end_ts
        if media is not None and media.established_ts is not None and media.end_ts is not None:
            start, end = media.established_ts, media.end_ts
        focuses.append((EvidenceFocus.NONE, None, start, end, start, end, []))
    clock = (
        "Mọi nguồn dùng chung một synthetic clock (UTC); không có clock skew giữa các nguồn."
        if bundle.meta.clock_model == config.CLOCK_MODEL else
        f"Clock model: {bundle.meta.clock_model}; chưa xác minh độ lệch giữa các nguồn."
    )
    result: list[EvidenceBundle] = []
    for focus, ref, start, end, window_start, window_end, resources in focuses:
        missing = list(bundle.meta.missing_sources)
        for item in anomalies.missing:
            # Fold a declared source note for the same metric into the detected gap: one line per gap.
            key = f"{item.source}/{item.metric.value}"
            notes = [note.removeprefix(f"{key}:").strip() for note in missing if note.startswith(f"{key}:")]
            missing = [note for note in missing if not note.startswith(f"{key}:")]
            detected = f"{key}: không có dữ liệu ({item.missing_ratio:.0%} sample null) trong {fmt_window(item.window_start, item.window_end)}"
            missing.append(detected + (f" (ghi chú nguồn: {'; '.join(notes)})" if notes else ""))
        turn = path_ctx.selected.turn_server if path_ctx.selected is not None else None
        if focus == EvidenceFocus.INCIDENT_INTERVAL and path_ctx.via_turn is True and turn is not None:
            observed = any(
                log.component == turn and window_start <= log.ts <= window_end
                and config.LOG_LEVEL_WEIGHT[log.level] >= config.LOG_LEVEL_WEIGHT[config.CORRELATION_MIN_LOG_LEVEL]
                and log.call_id in (None, bundle.meta.call_id)
                for log in bundle.logs
            )
            if not observed:
                missing.append(f"{turn}: không quan sát thấy log nào từ INFO trở lên của call/server trong window {fmt_window(window_start, window_end)}")
        result.append(EvidenceBundle(
            evidence_id=f"eb-{len(result) + 1:02d}", call_id=bundle.meta.call_id,
            focus=focus, focus_ref=ref, focus_start=start, focus_end=end,
            window_start=window_start, window_end=window_end, path=path_ctx.model_copy(deep=True),
            related_logs=_related_logs(bundle, path_ctx, focus, ref, start, window_start, window_end),
            resource_anomaly_ids=resources, clock_alignment=clock, missing_evidence=list(dict.fromkeys(missing)),
        ))
    return result
