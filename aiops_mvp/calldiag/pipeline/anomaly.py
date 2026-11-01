"""Deterministic rolling-threshold anomalies and QoS incident intervals."""

from datetime import datetime, timedelta
from typing import Literal

import pandas as pd

from calldiag import config
from calldiag.io import metrics_to_frame
from calldiag.models import (
    AnomalyResult, Baseline, CallTelemetry, Direction, IncidentInterval,
    MetricAnomaly, MetricCategory, MetricName, MetricSummary, MissingMetric,
    Phase, PhaseSpan, PhaseStatus,
)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, config.STAT_DECIMALS)


def _duration(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() + config.SAMPLE_INTERVAL_SEC


def _summary(
    group: pd.DataFrame, *, source: str, direction: Direction, metric: MetricName,
    start: datetime, end: datetime, scope: Literal["media_phase", "interval"],
    interval_id: str | None = None,
) -> MetricSummary:
    window = group.loc[group.ts.between(start, end)]
    values = window.value.dropna()
    return MetricSummary(
        source=source, direction=direction, metric=metric, scope=scope, interval_id=interval_id,
        window_start=start, window_end=end, n=len(window), n_missing=int(window.value.isna().sum()),
        missing_ratio=float(window.value.isna().mean()) if len(window) else 1.0,
        median=_round(float(values.median())) if len(values) else None,
        p95=_round(float(values.quantile(config.SUMMARY_P95_QUANTILE))) if len(values) else None,
        min=_round(float(values.min())) if len(values) else None,
        max=_round(float(values.max())) if len(values) else None,
        first_sample_id=window.iloc[0].sample_id if len(window) else None,
        last_sample_id=window.iloc[-1].sample_id if len(window) else None,
    )


def _runs(group: pd.DataFrame, flags: pd.Series) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    for i, flagged in enumerate(flags):
        if not flagged:
            continue
        if runs:
            first, last = runs[-1]
            gap = (group.iloc[i].ts - group.iloc[last].ts).total_seconds() - config.SAMPLE_INTERVAL_SEC
            if gap <= config.MERGE_GAP_SEC:
                runs[-1] = first, i
                continue
        runs.append((i, i))
    return [(a, b) for a, b in runs if _duration(group.iloc[a].ts, group.iloc[b].ts) >= config.MIN_ANOMALY_SEC]


def _group_anomalies(group: pd.DataFrame, baseline: Baseline) -> list[MetricAnomaly]:
    metric = baseline.metric
    rule = config.METRIC_RULES[metric]
    higher = config.METRIC_META[metric]["worse"] == "higher"
    rolling = group.value.rolling(config.ROLLING_WINDOW, center=True, min_periods=config.ROLLING_MIN_PERIODS).mean()
    relative = rule["rel"] * baseline.median if baseline.available and baseline.median is not None else None
    flags = rolling.ge(rule["abs"]) if higher else rolling.le(rule["abs"])
    if relative is not None:
        flags &= rolling.ge(relative) if higher else rolling.le(relative)
    result: list[MetricAnomaly] = []
    for first, last in _runs(group, flags):
        run = group.iloc[first:last + 1]
        values = run.value.dropna()
        if values.empty:
            continue
        peak_index = values.idxmax() if higher else values.idxmin()
        peak = group.loc[peak_index]
        result.append(MetricAnomaly(
            anomaly_id="", source=baseline.source, direction=baseline.direction, metric=metric,
            category=MetricCategory(config.METRIC_META[metric]["category"]),
            start_ts=run.iloc[0].ts, end_ts=run.iloc[-1].ts,
            duration_sec=_duration(run.iloc[0].ts, run.iloc[-1].ts),
            baseline_value=baseline.median, median_value=_round(float(values.median())),
            peak_value=float(peak.value), peak_ts=peak.ts,
            threshold_abs=rule["abs"], threshold_rel_value=_round(relative),
            first_sample_id=run.iloc[0].sample_id, peak_sample_id=peak.sample_id,
            last_sample_id=run.iloc[-1].sample_id, sample_ids=run.sample_id.tolist(),
        ))
    return result


def _incidents(anomalies: list[MetricAnomaly]) -> list[IncidentInterval]:
    incidents: list[IncidentInterval] = []
    for anomaly in anomalies:
        if anomaly.category != MetricCategory.QOS:
            continue
        if incidents and (anomaly.start_ts - incidents[-1].end_ts).total_seconds() <= config.INCIDENT_MERGE_GAP_SEC:
            incident = incidents[-1]
            incident.end_ts = max(incident.end_ts, anomaly.end_ts)
            incident.duration_sec = _duration(incident.start_ts, incident.end_ts)
            incident.qos_anomaly_ids.append(anomaly.anomaly_id)
        else:
            incident = IncidentInterval(
                interval_id=f"inc-{len(incidents) + 1:02d}", start_ts=anomaly.start_ts,
                end_ts=anomaly.end_ts, duration_sec=anomaly.duration_sec,
                qos_anomaly_ids=[anomaly.anomaly_id], resource_anomaly_ids=[],
            )
            incidents.append(incident)
        anomaly.interval_ids.append(incident.interval_id)
    padding = timedelta(seconds=config.RESOURCE_OVERLAP_SEC)
    for anomaly in anomalies:
        if anomaly.category == MetricCategory.RESOURCE:
            for incident in incidents:
                if anomaly.start_ts <= incident.end_ts + padding and anomaly.end_ts >= incident.start_ts - padding:
                    incident.resource_anomaly_ids.append(anomaly.anomaly_id)
                    anomaly.interval_ids.append(incident.interval_id)
    return incidents


def detect_anomalies(bundle: CallTelemetry, phases: list[PhaseSpan]) -> AnomalyResult:
    media = next((phase for phase in phases if phase.phase == Phase.MEDIA), None)
    if media is None or media.status != PhaseStatus.OK:
        return AnomalyResult(skipped=True, skip_reason="Phase Media Established không được thiết lập; không phân tích QoS")
    if media.established_ts is None or media.end_ts is None:
        return AnomalyResult(skipped=True, skip_reason="Thiếu mốc thời gian của phase Media Established; không phân tích QoS")
    start, end = media.established_ts, media.end_ts
    frame = metrics_to_frame(bundle)
    frame = frame.loc[frame.ts.between(start, end)]
    if not any(config.METRIC_META[metric]["category"] == "qos" for metric in frame.metric):
        return AnomalyResult(skipped=True, skip_reason="Không có metric QoS trong telemetry")
    result = AnomalyResult(skipped=False)
    groups: list[tuple[str, Direction, MetricName, pd.DataFrame]] = []
    for (source, direction_name, metric_name), raw in frame.groupby(["source", "direction", "metric"], sort=True):
        group = raw.sort_values(["ts", "sample_id"]).reset_index(drop=True)
        direction, metric = Direction(direction_name), MetricName(metric_name)
        groups.append((source, direction, metric, group))
        baseline_end = start + timedelta(seconds=config.BASELINE_SEC)
        base = group.loc[group.ts < baseline_end]
        values = base.value.dropna()
        available = len(values) >= config.BASELINE_MIN_SAMPLES
        median = _round(float(values.median())) if available else None
        baseline = Baseline(
            source=source, direction=direction, metric=metric, available=available,
            median=median, mad=_round(float((values - median).abs().median())) if available else None,
            window_start=start, window_end=min(baseline_end, end), n_samples=len(values),
        )
        result.baselines.append(baseline)
        summary = _summary(group, source=source, direction=direction, metric=metric, start=start, end=end, scope="media_phase")
        result.summaries.append(summary)
        if summary.missing_ratio >= config.MISSING_RATIO_THRESHOLD:
            missing = group.loc[group.value.isna()]
            refs = list(dict.fromkeys((missing.iloc[0].sample_id, missing.iloc[-1].sample_id)))
            result.missing.append(MissingMetric(
                source=source, metric=metric, missing_ratio=summary.missing_ratio,
                window_start=start, window_end=end, sample_ids=refs,
            ))
        else:
            result.anomalies.extend(_group_anomalies(group, baseline))
    result.anomalies.sort(key=lambda a: (
        a.start_ts, config.ANOMALY_CATEGORY_ORDER[a.category], a.metric.value, a.source, a.direction.value,
    ))
    for i, anomaly in enumerate(result.anomalies, start=1):
        anomaly.anomaly_id = f"an-{i:02d}"
    result.incidents = _incidents(result.anomalies)
    for incident in result.incidents:
        for source, direction, metric, group in groups:
            if config.METRIC_META[metric]["category"] == "resource":
                result.summaries.append(_summary(
                    group, source=source, direction=direction, metric=metric,
                    start=incident.start_ts, end=incident.end_ts, scope="interval", interval_id=incident.interval_id,
                ))
    return result
