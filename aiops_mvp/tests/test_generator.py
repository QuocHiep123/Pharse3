import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from calldiag import config
from calldiag.cli import main
from calldiag.io import load_bundle, validate_bundle
from calldiag.models import CallTelemetry, Direction, EventType, MetricName
from calldiag.scenarios import REGISTRY, build_all, data, get_scenario, s6_missing_turn_metrics
from calldiag.scenarios.builder import Plateau, Profile, ScenarioBuilder
from calldiag.scenarios.common import add_background_logs


@pytest.fixture(scope="module")
def scenarios() -> dict[str, CallTelemetry]:
    return build_all()


@pytest.mark.parametrize("sid", REGISTRY)
def test_deterministic_and_valid(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    first = scenarios[sid]
    second = get_scenario(sid).build()
    assert first.model_dump() == second.model_dump()
    assert first.model_dump_json() == second.model_dump_json()
    validate_bundle(first)
    assert first.meta.scenario_id == sid
    assert first.meta.title == REGISTRY[sid].title


def test_s1_metric_values(scenarios: dict[str, CallTelemetry]) -> None:
    samples = {s.sample_id: s.value for s in scenarios["S1"].metrics}
    assert 90 <= samples["m-turn-01-turn_cpu_pct-0090"] <= 100
    assert 270 <= samples["m-alice-rtt_ms-0090"] <= 350
    assert 65 <= samples["m-alice-rtt_ms-0030"] <= 95


def test_s6_preserves_all_missing_turn_samples(scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios["S6"]
    samples = [s for s in bundle.metrics if s.metric == MetricName.TURN_CPU_PCT]
    assert len(samples) == 121
    assert all(s.value is None and s.call_id is None for s in samples)
    assert s6_missing_turn_metrics.MISSING_TURN_SOURCE in bundle.meta.missing_sources
    assert not any(log.component == config.TURN_SERVER and log.level.value in {"WARN", "ERROR"} for log in bundle.logs)


@pytest.mark.parametrize("sid", ["S3", "S5"])
def test_early_failure_has_no_qos(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid]
    assert all(config.METRIC_META[s.metric]["category"] == "resource" for s in bundle.metrics)
    assert set(bundle.meta.expected_metrics) == set(data.EXPECTED_METRICS_RESOURCE)
    assert all(e.type not in {EventType.FIRST_RTP_SENT, EventType.FIRST_RTP_RECEIVED} for e in bundle.events)


def test_failure_event_sequences(scenarios: dict[str, CallTelemetry]) -> None:
    ice_types = [e.type for e in scenarios["S3"].events]
    assert ice_types.count(EventType.ICE_PAIR_FAILED) == 3
    assert EventType.ICE_FAILED in ice_types
    assert EventType.ICE_SELECTED_PAIR not in ice_types
    timeout_types = [e.type for e in scenarios["S5"].events]
    assert EventType.SIGNALING_TIMEOUT in timeout_types
    assert EventType.ANSWER_RECEIVED not in timeout_types
    assert not any(e.type.value.startswith("ICE_") for e in scenarios["S5"].events)
    assert all(log.call_id == scenarios["S5"].meta.call_id for log in scenarios["S5"].logs)


@pytest.mark.parametrize(("sid", "via_turn"), [("S0", False), ("S1", True), ("S2", False), ("S4", True), ("S6", True)])
def test_selected_path(sid: str, via_turn: bool, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid]
    selected = [e for e in bundle.events if e.type == EventType.ICE_SELECTED_PAIR]
    assert len(selected) == 1
    assert selected[0].attrs["via_turn"] is via_turn
    assert selected[0].attrs["turn_server"] == (config.TURN_SERVER if via_turn else None)
    # Gathering a relay candidate alone does not imply relay selection.
    assert any(e.type == EventType.ICE_CANDIDATE_GATHERED and e.attrs["candidate_type"] == "relay" for e in bundle.events)


@pytest.mark.parametrize("sid", REGISTRY)
def test_ids_metadata_and_measurement_scope(sid: str, scenarios: dict[str, CallTelemetry]) -> None:
    bundle = scenarios[sid]
    assert re.fullmatch(r"call-\d{4}", bundle.meta.call_id)
    assert sid.lower() not in bundle.meta.call_id.lower()
    assert all(word.lower() not in bundle.meta.call_id.lower() for word in bundle.meta.title.split())
    assert [e.event_id for e in bundle.events] == [f"ev-{n:03d}" for n in range(1, len(bundle.events) + 1)]
    assert [log.log_id for log in bundle.logs] == [f"log-{n:03d}" for n in range(1, len(bundle.logs) + 1)]
    assert all(e.call_id == bundle.meta.call_id for e in bundle.events)
    assert bundle.meta.clock_model == "single_synthetic_clock"
    assert data.MISSING_SOURCES[0] in bundle.meta.missing_sources
    assert all(s.source != config.CALLEE for s in bundle.metrics)
    for sample in bundle.metrics:
        assert sample.direction.value == config.METRIC_META[sample.metric]["direction"]
        assert sample.call_id == (None if sample.source == config.TURN_SERVER else bundle.meta.call_id)
        if sample.value is not None:
            assert sample.value >= 0
            if config.METRIC_META[sample.metric]["unit"] == "%":
                assert sample.value <= 100
    if sid != "S5":
        noise = [log for log in bundle.logs if log.call_id == "call-0999"]
        assert len(noise) == 1
        assert (noise[0].ts - bundle.meta.start_ts).total_seconds() == 30.5


@pytest.mark.parametrize(("sid", "qos_count", "resource_count", "end_t"), [
    ("S0", 115, 121, 120.2), ("S1", 115, 121, 120.2), ("S2", 115, 121, 120.2),
    ("S3", 0, 34, 33.0), ("S4", 115, 121, 120.2), ("S5", 0, 12, 11.8), ("S6", 115, 121, 120.2),
])
def test_series_counts_and_endpoints(
    sid: str, qos_count: int, resource_count: int, end_t: float, scenarios: dict[str, CallTelemetry],
) -> None:
    bundle = scenarios[sid]
    assert (bundle.meta.end_ts - bundle.meta.start_ts).total_seconds() == end_t
    assert bundle.events[-1].type == EventType.CALL_ENDED
    assert bundle.events[-1].ts == bundle.meta.end_ts
    for metric in MetricName:
        samples = [s for s in bundle.metrics if s.metric == metric]
        is_qos = config.METRIC_META[metric]["category"] == "qos"
        assert len(samples) == (qos_count if is_qos else resource_count)
        if samples:
            assert (samples[0].ts - bundle.meta.start_ts).total_seconds() == (5 if is_qos else 0)
            assert all((right.ts - left.ts).total_seconds() == 1 for left, right in zip(samples, samples[1:]))


def test_registry_and_expected_targets() -> None:
    assert list(REGISTRY) == [f"S{i}" for i in range(7)]
    assert all(s.description and len(s.expected.phase_status) == 5 for s in REGISTRY.values())
    assert REGISTRY["S2"].expected.required_rejected == ("TURN_OVERLOAD_DEGRADATION",)
    assert REGISTRY["S6"].expected.required_hypotheses == ("TURN_OVERLOAD_DEGRADATION",)
    assert REGISTRY["S6"].expected.primary_confidence == "Medium"
    with pytest.raises(KeyError, match="S0, S1, S2, S3, S4, S5, S6"):
        get_scenario("invalid")


@pytest.mark.parametrize(("t", "weight"), [(7, 0), (8, 0), (9, 0.5), (10, 1), (15, 1), (20, 1), (21.5, 0.5), (23, 0), (24, 0)])
def test_plateau_interpolation(t: float, weight: float) -> None:
    plateau = Plateau(10, 20, 100, 10)
    assert plateau.weight(t) == weight
    assert Profile(0, 2, (plateau,)).parameters_at(t) == (100 * weight, 2 + 8 * weight)


def test_profile_selects_largest_weight_and_zero_ramps() -> None:
    profile = Profile(10, 2, (Plateau(10, 15, 100, 4), Plateau(20, 25, 200, 6)))
    assert profile.parameters_at(21) == (200, 6)
    assert profile.parameters_at(0) == (10, 2)
    plateau = Plateau(10, 20, 100, 0, ramp_in=0, ramp_out=0)
    assert [plateau.weight(t) for t in (9, 10, 20, 21)] == [0, 1, 1, 0]


def make_builder() -> ScenarioBuilder:
    return ScenarioBuilder(scenario_id="test", title="Test", call_id="call-9999", seed=123)


def test_missing_series_does_not_consume_rng() -> None:
    with_missing, control = make_builder(), make_builder()
    with_missing.series("turn-01", Direction.NONE, MetricName.TURN_CPU_PCT, 0, 2, Profile(0, 0, missing=True))
    for b in (with_missing, control):
        b.series("alice", Direction.NONE, MetricName.RTT_MS, 0, 2, Profile(80, 4))
    first = with_missing.build(end_t=2, expected_metrics=[], missing_sources=[])
    second = control.build(end_t=2, expected_metrics=[], missing_sources=[])
    assert first.metrics[3:] == second.metrics


def test_builder_orders_ties_and_returns_independent_bundles() -> None:
    b = make_builder()
    b.event(1, "alice", EventType.INVITE_SENT)
    b.event(0, "signaling", EventType.CALL_CREATED)
    b.event(1, "bob", EventType.INVITE_RECEIVED)
    first = b.build(end_t=2, expected_metrics=[], missing_sources=[])
    assert [e.type for e in first.events] == [EventType.CALL_CREATED, EventType.INVITE_SENT, EventType.INVITE_RECEIVED]
    first.events[0].attrs["mutation"] = True
    second = b.build(end_t=2, expected_metrics=[], missing_sources=[])
    assert "mutation" not in second.events[0].attrs


@pytest.mark.parametrize(("metric", "mean", "expected"), [(MetricName.RTT_MS, -10, 0), (MetricName.TURN_CPU_PCT, 150, 100), (MetricName.PACKET_LOSS_PCT, 150, 100)])
def test_builder_clamps_metrics(metric: MetricName, mean: float, expected: float) -> None:
    b = make_builder()
    b.series("alice", Direction.NONE, metric, 0, 0, Profile(mean, 0))
    bundle = b.build(end_t=0, expected_metrics=[], missing_sources=[])
    assert bundle.metrics[0].value == expected


def test_background_logs_respect_media_window_and_call_end() -> None:
    b = make_builder()
    add_background_logs(b, media_from=25, media_to=39, relay=True, end_t=40)
    bundle = b.build(end_t=40, expected_metrics=[], missing_sources=[])
    own = [log for log in bundle.logs if log.call_id == b.call_id]
    assert len(own) == 2
    assert all((log.ts - bundle.meta.start_ts).total_seconds() == 30 for log in own)
    b = make_builder()
    add_background_logs(b, media_from=None, media_to=None, relay=False, end_t=30)
    assert b.build(end_t=30, expected_metrics=[], missing_sources=[]).logs == []


def test_generate_cli_all(tmp_path: Path, scenarios: dict[str, CallTelemetry], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["generate", "--scenario", "all", "--out", str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.glob("*.json")) == [f"{sid}.json" for sid in REGISTRY]
    for sid, bundle in scenarios.items():
        assert load_bundle(tmp_path / f"{sid}.json") == bundle
    assert len(capsys.readouterr().out.splitlines()) == 7


def test_generate_cli_single_and_invalid(tmp_path: Path) -> None:
    assert main(["generate", "--scenario", "S1", "--out", str(tmp_path)]) == 0
    assert [p.name for p in tmp_path.glob("*.json")] == ["S1.json"]
    with pytest.raises(SystemExit) as exc:
        main(["generate", "--scenario", "S7", "--out", str(tmp_path)])
    assert exc.value.code == 2


def test_module_entrypoint_and_default_output(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [sys.executable, "-m", "calldiag", "generate"],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(list((tmp_path / "data" / "scenarios").glob("*.json"))) == 7


def test_config_holds_no_scenario_data() -> None:
    # Pipeline modules import config; scenario parameters must stay in calldiag.scenarios.
    sids = set(REGISTRY)
    for name in dir(config):
        value = getattr(config, name)
        if isinstance(value, dict):
            assert not sids & set(value), f"config.{name} is keyed by scenario ID"
