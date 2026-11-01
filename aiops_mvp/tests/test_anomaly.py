from datetime import timedelta

import pytest

from calldiag import config
from calldiag.io import metrics_to_frame
from calldiag.models import AnomalyResult, CallTelemetry, Direction, MetricCategory, MetricName, Phase, PhaseSpan
from calldiag.pipeline.anomaly import detect_anomalies
from calldiag.pipeline.phases import localize_phases
from calldiag.pipeline.timeline import build_timeline
from calldiag.scenarios import REGISTRY, get_scenario
from calldiag.scenarios.builder import Plateau, Profile, ScenarioBuilder
from conftest import M3Result


@pytest.mark.parametrize("sid", REGISTRY)
def test_scenario_anomaly_table(sid: str, m3_results: dict[str, M3Result]) -> None:
    result = m3_results[sid]
    anomalies = result.anomalies
    assert anomalies.skipped is (sid in {"S3", "S5"})
    qos = [a for a in anomalies.anomalies if a.category == MetricCategory.QOS]
    assert len(qos) == (4 if sid in {"S1", "S2", "S6"} else 0)
    assert len(anomalies.incidents) == (1 if sid in {"S1", "S2", "S6"} else 0)
    expected = REGISTRY[sid].expected.qos_interval_offset
    if expected is not None:
        interval = anomalies.incidents[0]
        offsets = ((interval.start_ts - result.bundle.meta.start_ts).total_seconds(), (interval.end_ts - result.bundle.meta.start_ts).total_seconds())
        assert all(abs(actual - target) <= config.EVAL_INTERVAL_TOLERANCE_SEC for actual, target in zip(offsets, expected))
        assert len(interval.resource_anomaly_ids) == (0 if sid == "S6" else 1)
    if anomalies.skipped:
        assert anomalies.skip_reason
        assert not anomalies.baselines and not anomalies.summaries
    assert [a.anomaly_id for a in anomalies.anomalies] == [f"an-{i:02d}" for i in range(1, len(anomalies.anomalies) + 1)]
    for a in anomalies.anomalies:
        assert a.duration_sec == (a.end_ts - a.start_ts).total_seconds() + 1
        assert a.first_sample_id == a.sample_ids[0]
        assert a.last_sample_id == a.sample_ids[-1]
        for interval_id in a.interval_ids:
            interval = next(i for i in anomalies.incidents if i.interval_id == interval_id)
            assert a.anomaly_id in interval.qos_anomaly_ids + interval.resource_anomaly_ids


def test_s1_baseline_peak_and_precedence(m3_results: dict[str, M3Result]) -> None:
    result = m3_results["S1"]
    rtt = next(a for a in result.anomalies.anomalies if a.metric == MetricName.RTT_MS)
    turn = next(a for a in result.anomalies.anomalies if a.metric == MetricName.TURN_CPU_PCT)
    assert 75 <= rtt.baseline_value <= 85
    assert rtt.peak_value >= 300
    assert turn.start_ts < rtt.start_ts
    samples = {sample.sample_id: sample for sample in result.bundle.metrics}
    assert samples[rtt.peak_sample_id].value == rtt.peak_value
    assert samples[rtt.peak_sample_id].ts == rtt.peak_ts
    assert set(rtt.sample_ids) <= samples.keys()
    baseline = next(b for b in result.anomalies.baselines if b.metric == MetricName.RTT_MS)
    values = [sample.value for sample in result.bundle.metrics if sample.metric == MetricName.RTT_MS and baseline.window_start <= sample.ts < baseline.window_end]
    assert baseline.n_samples == len(values)
    assert baseline.mad >= 0
    media = next(p for p in result.phases if p.phase == Phase.MEDIA)
    assert all(sample.ts >= media.established_ts for a in result.anomalies.anomalies for sample in (samples[a.first_sample_id],))


def test_s6_missing_preserves_nulls_and_no_turn_anomaly(m3_results: dict[str, M3Result]) -> None:
    result = m3_results["S6"]
    assert len(result.anomalies.missing) == 1
    missing = result.anomalies.missing[0]
    assert missing.source == "turn-01" and missing.metric == MetricName.TURN_CPU_PCT
    assert missing.missing_ratio == 1
    samples = {sample.sample_id: sample for sample in result.bundle.metrics}
    assert all(samples[ref].value is None for ref in missing.sample_ids)
    assert not any(a.metric == MetricName.TURN_CPU_PCT for a in result.anomalies.anomalies)
    summaries = [s for s in result.anomalies.summaries if s.metric == MetricName.TURN_CPU_PCT]
    assert len(summaries) == 2
    assert all(s.median is s.p95 is s.min is s.max is None and s.missing_ratio == 1 for s in summaries)
    assert metrics_to_frame(result.bundle).query("metric == 'turn_cpu_pct'").value.isna().all()


def build_series(
    metric: MetricName, profile: Profile, *, start: int = 5, end: int = 90,
    turn: Profile | None = None,
) -> tuple[CallTelemetry, list[PhaseSpan]]:
    template = get_scenario("S0").build()
    b = ScenarioBuilder(scenario_id="unit", title="unit", call_id=template.meta.call_id, seed=42)
    b.series("alice", Direction(config.METRIC_META[metric]["direction"]), metric, start, end, profile)
    if turn is not None:
        b.series("turn-01", Direction.NONE, MetricName.TURN_CPU_PCT, start, end, turn, call_scoped=False)
    generated = b.build(end_t=120.2, expected_metrics=[], missing_sources=[])
    template.metrics = generated.metrics
    return template, localize_phases(template)


def test_short_spike_is_not_anomaly() -> None:
    bundle, phases = build_series(MetricName.RTT_MS, Profile(80, 0, (Plateau(40, 42, 400, 0, 0, 0),)))
    assert detect_anomalies(bundle, phases).anomalies == []


def test_runs_with_two_second_gap_merge() -> None:
    bundle, phases = build_series(MetricName.RTT_MS, Profile(80, 0, (
        Plateau(40, 50, 400, 0, 0, 0), Plateau(53, 65, 400, 0, 0, 0),
    )))
    anomalies = detect_anomalies(bundle, phases).anomalies
    assert len(anomalies) == 1
    assert (anomalies[0].end_ts - bundle.meta.start_ts).total_seconds() >= 64


def test_bitrate_uses_lower_threshold_and_raw_minimum() -> None:
    bundle, phases = build_series(MetricName.BITRATE_KBPS, Profile(1500, 0, (Plateau(40, 60, 600, 0, 0, 0),)))
    anomaly = detect_anomalies(bundle, phases).anomalies[0]
    assert anomaly.baseline_value == 1500
    assert anomaly.median_value == anomaly.peak_value == 600
    assert anomaly.threshold_rel_value == 900


def test_exact_half_missing_suppresses_detection() -> None:
    bundle, phases = build_series(MetricName.RTT_MS, Profile(400, 0), end=84)
    for i, sample in enumerate(bundle.metrics):
        if i % 2 == 0:
            sample.value = None
    result = detect_anomalies(bundle, phases)
    assert result.missing[0].missing_ratio == 0.5
    assert result.anomalies == []
    assert result.summaries[0].n == 80 and result.summaries[0].n_missing == 40


def test_insufficient_baseline_uses_absolute_threshold() -> None:
    bundle, phases = build_series(MetricName.RTT_MS, Profile(400, 0), start=50, end=70)
    result = detect_anomalies(bundle, phases)
    assert not result.baselines[0].available
    assert result.baselines[0].median is result.baselines[0].mad is None
    assert result.anomalies[0].baseline_value is result.anomalies[0].threshold_rel_value is None


def test_relative_threshold_must_also_hold() -> None:
    bundle, phases = build_series(MetricName.RTT_MS, Profile(200, 0, (Plateau(40, 60, 300, 0, 0, 0),)))
    assert detect_anomalies(bundle, phases).anomalies == []


def test_resource_only_anomaly_does_not_create_incident() -> None:
    bundle, phases = build_series(MetricName.RTT_MS, Profile(80, 0), turn=Profile(40, 0, (Plateau(40, 60, 95, 0, 0, 0),)))
    result = detect_anomalies(bundle, phases)
    assert len(result.anomalies) == 1
    assert result.anomalies[0].category == MetricCategory.RESOURCE
    assert not result.incidents and not result.anomalies[0].interval_ids


def test_no_qos_and_missing_media_boundaries_skip(m3_results: dict[str, M3Result]) -> None:
    bundle = m3_results["S0"].bundle.model_copy(deep=True)
    phases = localize_phases(bundle)
    bundle.metrics = [s for s in bundle.metrics if s.metric == MetricName.TURN_CPU_PCT]
    result = detect_anomalies(bundle, phases)
    assert result.skipped and "Không có metric QoS" in result.skip_reason
    next(p for p in phases if p.phase == Phase.MEDIA).end_ts = None
    result = detect_anomalies(bundle, phases)
    assert result.skipped and "Thiếu mốc thời gian" in result.skip_reason
    assert detect_anomalies(bundle, []).skipped


def test_multiple_incidents_and_resource_overlap() -> None:
    bundle, phases = build_series(MetricName.RTT_MS, Profile(80, 0, (
        Plateau(35, 45, 400, 0, 0, 0), Plateau(70, 90, 400, 0, 0, 0),
    )), turn=Profile(40, 0, (Plateau(30, 90, 95, 0, 0, 0),)))
    result = detect_anomalies(bundle, phases)
    assert len(result.incidents) == 2
    turn = next(a for a in result.anomalies if a.metric == MetricName.TURN_CPU_PCT)
    assert turn.interval_ids == ["inc-01", "inc-02"]
    assert all(turn.anomaly_id in i.resource_anomaly_ids for i in result.incidents)
    assert len([s for s in result.summaries if s.scope == "interval"]) == 2
    assert result.incidents[-1].end_ts == bundle.meta.start_ts + timedelta(seconds=90)


@pytest.mark.parametrize("sid", REGISTRY)
def test_anomaly_round_trip_and_determinism(sid: str, m3_results: dict[str, M3Result]) -> None:
    result = m3_results[sid]
    before = result.bundle.model_dump_json()
    regenerated = detect_anomalies(result.bundle, localize_phases(result.bundle))
    assert regenerated == result.anomalies
    assert AnomalyResult.model_validate_json(regenerated.model_dump_json()) == regenerated
    assert result.bundle.model_dump_json() == before
    timeline = build_timeline(result.bundle, regenerated)
    assert len([item for item in timeline if item.kind.startswith("anomaly_")]) == len(regenerated.anomalies) * 2
