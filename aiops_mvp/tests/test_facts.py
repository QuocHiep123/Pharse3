from collections import Counter

import pytest

from calldiag import config
from calldiag.models import (
    AnomalyResult, CallMeta, CallTelemetry, Fact, FactKind, LogCategory, LogLevel, MetricName,
)
from calldiag.pipeline.anomaly import detect_anomalies
from calldiag.pipeline.correlate import build_path_context, correlate
from calldiag.pipeline.facts import FactStore, extract_facts
from calldiag.pipeline.phases import compute_trace_metrics, extract_selected_path, localize_phases, mark_degraded
from calldiag.scenarios import REGISTRY
from calldiag.utils import at
from conftest import M3Result


@pytest.mark.parametrize(("sid", "path", "checks", "timing", "changes", "levels", "missing"), [
    ("S0", 1, 1, 0, 0, 4, 0), ("S1", 1, 1, 0, 5, 1, 0), ("S2", 1, 1, 0, 5, 1, 0),
    ("S3", 0, 1, 1, 0, 0, 0), ("S4", 1, 1, 0, 0, 4, 0), ("S5", 0, 0, 1, 0, 0, 0), ("S6", 1, 1, 0, 4, 1, 1),
])
def test_fact_kind_counts(
    sid: str, path: int, checks: int, timing: int, changes: int, levels: int, missing: int,
    m3_results: dict[str, M3Result],
) -> None:
    counts = Counter(fact.kind for fact in m3_results[sid].facts.all())
    for kind, expected in (
        (FactKind.PHASE_STATUS, 5), (FactKind.SELECTED_PATH, path), (FactKind.ICE_CHECKS, checks),
        (FactKind.TRACE_TIMING, timing), (FactKind.METRIC_CHANGE, changes), (FactKind.METRIC_LEVEL, levels), (FactKind.MISSING_DATA, missing),
    ):
        assert counts[kind] == expected
    assert counts[FactKind.LOG_EVENT] <= config.MAX_LOG_FACTS
    if sid in {"S0", "S4"}:
        assert counts[FactKind.LOG_EVENT] == 0
    if sid in {"S3", "S5"}:
        assert counts[FactKind.LOG_EVENT] == (4 if sid == "S3" else 2)


@pytest.mark.parametrize("sid", REGISTRY)
def test_all_fact_refs_resolve_and_no_banned_words(sid: str, m3_results: dict[str, M3Result]) -> None:
    result = m3_results[sid]
    refs = (
        {e.event_id for e in result.bundle.events} | {log.log_id for log in result.bundle.logs}
        | {sample.sample_id for sample in result.bundle.metrics}
        | {a.anomaly_id for a in result.anomalies.anomalies} | {i.interval_id for i in result.anomalies.incidents}
    )
    facts = result.facts.all()
    assert [fact.fact_id for fact in facts] == [f"F{i}" for i in range(1, len(facts) + 1)]
    for fact in facts:
        assert fact.refs and set(fact.refs) <= refs
        assert not any(word in fact.statement.lower() for word in config.BANNED_FACT_WORDS)
        assert Fact.model_validate_json(fact.model_dump_json()) == fact
    assert len(result.facts.ids()) == len(facts)


def test_s1_metric_change_values_and_query(m3_results: dict[str, M3Result]) -> None:
    store = m3_results["S1"].facts
    turn, = store.query(FactKind.METRIC_CHANGE, metric="turn_cpu_pct")
    rtt, = store.query(FactKind.METRIC_CHANGE, metric="rtt_ms")
    assert turn.value_after >= 90 and turn.data["on_path"] is True
    assert 75 <= rtt.value_before <= 85 and rtt.value_after >= 280
    assert store.query(source="turn-01", category="resource", on_path=True) == [turn]
    assert store.get(rtt.fact_id) == rtt
    with pytest.raises(KeyError):
        store.get("F999")


def test_s2_turn_fact_is_off_path(m3_results: dict[str, M3Result]) -> None:
    turn, = m3_results["S2"].facts.query(FactKind.METRIC_CHANGE, metric="turn_cpu_pct")
    assert turn.data["on_path"] is False


def test_s6_turn_missing_is_never_normal_or_zero(m3_results: dict[str, M3Result]) -> None:
    store = m3_results["S6"].facts
    missing, = store.query(FactKind.MISSING_DATA, metric="turn_cpu_pct")
    assert "không có dữ liệu" in missing.statement
    assert "bằng 0" not in missing.statement and "bình thường" not in missing.statement
    assert missing.value_before is missing.value_after is missing.value_peak is None
    assert not store.query(FactKind.METRIC_LEVEL, metric="turn_cpu_pct")
    assert not store.query(FactKind.METRIC_CHANGE, metric="turn_cpu_pct")


def test_s3_skipped_media_ice_checks_and_trace_timing(m3_results: dict[str, M3Result]) -> None:
    store = m3_results["S3"].facts
    media, = store.query(FactKind.PHASE_STATUS, phase="media")
    checks, = store.query(FactKind.ICE_CHECKS)
    timing, = store.query(FactKind.TRACE_TIMING, phase="ice")
    assert media.data["status"] == "skipped"
    assert checks.data["succeeded"] == 0 and checks.data["relay_pair_failed"] is True
    assert timing.data["duration_ms"] == 30000
    assert len(timing.refs) == 2
    assert media.refs[0] in store.query(FactKind.PHASE_STATUS, phase="ice")[0].refs


def test_signaling_timeout_is_observed_not_inferred(m3_results: dict[str, M3Result]) -> None:
    timing, = m3_results["S5"].facts.query(FactKind.TRACE_TIMING, phase="offer_answer")
    assert timing.data["duration_ms"] == 10000
    assert "Không nhận được ANSWER" in timing.statement


def test_log_facts_deduplicate_limit_and_prioritize_errors(m3_results: dict[str, M3Result]) -> None:
    result = m3_results["S1"]
    bundle = result.bundle.model_copy(deep=True)
    for i in range(10):
        bundle.logs.append(bundle.logs[0].model_copy(update={
            "log_id": f"extra-{i}", "ts": at(bundle.meta.start_ts, 95 + i / 10),
            "component": "alice", "level": LogLevel.WARN, "category": LogCategory.MEDIA,
            "message": f"additional warning {i}",
        }))
    error = bundle.logs[0].model_copy(update={
        "log_id": "extra-error", "ts": at(bundle.meta.start_ts, 100),
        "component": "alice", "level": LogLevel.ERROR, "category": LogCategory.MEDIA, "message": "late media error",
    })
    bundle.logs.append(error)
    evidence = correlate(bundle, result.phases, result.anomalies, result.path)
    store = extract_facts(bundle, result.phases, result.trace, result.path, result.anomalies, evidence + evidence)
    logs = store.query(FactKind.LOG_EVENT)
    assert len(logs) == config.MAX_LOG_FACTS
    assert len({fact.data["log_id"] for fact in logs}) == len(logs)
    assert "extra-error" in {fact.data["log_id"] for fact in logs}
    assert [fact.ts for fact in logs] == sorted(fact.ts for fact in logs)
    assert all(fact.data["level"] in {"WARN", "ERROR"} for fact in logs)


def test_raw_log_with_banned_words_stays_in_evidence_but_not_facts(m3_results: dict[str, M3Result]) -> None:
    result = m3_results["S1"]
    bundle = result.bundle.model_copy(deep=True)
    bundle.logs.append(bundle.logs[0].model_copy(update={
        "log_id": "speculative", "ts": at(bundle.meta.start_ts, 85),
        "component": "alice", "level": LogLevel.ERROR, "message": "Video froze because of TURN",
    }))
    evidence = correlate(bundle, result.phases, result.anomalies, result.path)
    assert any(log.log_id == "speculative" for item in evidence for log in item.related_logs)
    store = extract_facts(bundle, result.phases, result.trace, result.path, result.anomalies, evidence)
    assert not any("speculative" in fact.refs for fact in store.all())


def test_empty_trace_never_invents_fact_refs(bundle: CallTelemetry) -> None:
    bundle.events = []
    phases = localize_phases(bundle)
    path = build_path_context(bundle, None)
    anomalies = detect_anomalies(bundle, phases)
    trace = compute_trace_metrics(bundle, phases, None)
    evidence = correlate(bundle, phases, anomalies, path)
    assert extract_facts(bundle, phases, trace, path, anomalies, evidence).all() == []


def test_fact_store_query_and_collection_independence() -> None:
    store = FactStore()
    one = store.add(kind=FactKind.PHASE_STATUS, statement="Phase ICE: hoàn tất.", data={"phase": "ice", "status": "ok"}, refs=["ev-001"])
    two = store.add(kind=FactKind.MISSING_DATA, statement="RTT: không có dữ liệu.", metric=MetricName.RTT_MS, source="alice", refs=["m-alice-rtt_ms-0001"])
    assert store.query(phase="ice") == [one]
    assert store.query(metric="rtt_ms", source="alice") == [two]
    assert store.query(missing_key=None) == []
    returned = store.all()
    returned.clear()
    assert store.ids() == {"F1", "F2"}


class GuardedMeta(CallMeta):
    def __getattribute__(self, name: str) -> object:
        if name in {"scenario_id", "title"}:
            raise AssertionError(f"M3 must not read meta.{name}")
        return super().__getattribute__(name)


@pytest.mark.parametrize("sid", REGISTRY)
def test_m3_deterministic_pure_and_scenario_independent(sid: str, m3_results: dict[str, M3Result]) -> None:
    result = m3_results[sid]
    snapshot = (result.bundle.model_dump_json(), result.anomalies.model_dump_json(), [p.model_dump_json() for p in result.phases], [e.model_dump_json() for e in result.evidence])
    facts = extract_facts(result.bundle, result.phases, result.trace, result.path, result.anomalies, result.evidence)
    assert facts.all() == result.facts.all()
    assert snapshot == (result.bundle.model_dump_json(), result.anomalies.model_dump_json(), [p.model_dump_json() for p in result.phases], [e.model_dump_json() for e in result.evidence])
    bundle = result.bundle.model_copy(deep=True)
    old_id = bundle.meta.call_id
    bundle.meta = GuardedMeta.model_validate({**bundle.meta.model_dump(), "call_id": "opaque-id", "scenario_id": "unknown", "title": "unknown"})
    for event in bundle.events:
        event.call_id = "opaque-id"
    for record in [*bundle.metrics, *bundle.logs]:
        if record.call_id == old_id:
            record.call_id = "opaque-id"
    phases = localize_phases(bundle)
    path = extract_selected_path(bundle)
    trace = compute_trace_metrics(bundle, phases, path)
    anomalies = detect_anomalies(bundle, phases)
    assert anomalies == result.anomalies
    phases = mark_degraded(phases, anomalies)
    context = build_path_context(bundle, path)
    evidence = correlate(bundle, phases, anomalies, context)
    assert extract_facts(bundle, phases, trace, context, anomalies, evidence).all() == result.facts.all()


def test_concrete_model_defaults_do_not_share_lists() -> None:
    one, two = AnomalyResult(skipped=False), AnomalyResult(skipped=False)
    one.skip_reason = "changed"
    assert two.skip_reason is None
    assert one.anomalies is not two.anomalies and one.incidents is not two.incidents
