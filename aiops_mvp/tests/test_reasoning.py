from dataclasses import replace

import pytest

from calldiag.models import ConditionResult, CondState, Confidence, FactKind, PipelineResult
from calldiag.pipeline.facts import FactStore
from calldiag.pipeline.reasoning import reason
from calldiag.pipeline.rules import (
    RULES, Ctx, RuleSpec, all_phases_ok, turn_cpu_high_overlap, turn_cpu_on_path_high,
    via_turn, qos_incident, no_qos_anomaly,
)
from calldiag.scenarios import REGISTRY
from conftest import M3Result


def context(result: M3Result) -> Ctx:
    store = FactStore()
    for fact in result.facts.all():
        store.add(**fact.model_dump(exclude={"fact_id"}))
    return Ctx(store, result.phases, result.path, result.anomalies, result.evidence)


@pytest.mark.parametrize("sid", REGISTRY)
def test_reasoning_outcome_table(sid: str, results: dict[str, PipelineResult]) -> None:
    report = results[sid].report
    expected = REGISTRY[sid].expected
    assert report.summary.primary_rule_id == expected.primary_rule
    assert report.summary.confidence == expected.primary_confidence
    assert set(expected.required_inferences) <= {i.rule_id for i in report.inferences}
    assert set(expected.required_hypotheses) <= {h.rule_id for h in report.hypotheses}
    assert set(expected.required_rejected) <= {r.rule_id for r in report.rejected}
    assert not set(expected.forbidden_inferences) & {i.rule_id for i in report.inferences}
    assert report.inferences[0].inference_id == report.summary.primary_inference_id == "I1"
    facts = {f.fact_id for f in report.facts}
    for inference in report.inferences:
        assert inference.supported_by and set(inference.supported_by) <= facts
        assert all(set(c.fact_ids) <= facts for c in inference.conditions)


def test_s1_supports_metrics_path_and_precedence(results: dict[str, PipelineResult]) -> None:
    report = results["S1"].report
    primary = report.inferences[0]
    support = [fact for fact in report.facts if fact.fact_id in primary.supported_by]
    assert {"rtt_ms", "packet_loss_pct", "turn_cpu_pct"} <= {f.metric for f in support}
    assert any(f.kind == FactKind.SELECTED_PATH for f in support)
    assert len(primary.supported_by) >= 4
    assert any("Booster" in text and "tăng trước" in text for text in primary.confidence_reasons)


def test_s2_rejected_turn_contains_selected_path(results: dict[str, PipelineResult]) -> None:
    report = results["S2"].report
    rejected = report.rejected[0]
    assert any(f.kind == FactKind.SELECTED_PATH and f.fact_id in rejected.contradicting_fact_ids for f in report.facts)
    assert "TURN không nằm trên media path" in rejected.reason
    # A direct path has no turn_server; the TURN metric FACT must still name the server.
    assert "turn-01" in rejected.reason and "turn-01" in rejected.statement
    assert "chưa rõ server" not in rejected.reason + rejected.statement


def test_s6_missing_turn_lowers_network_confidence(results: dict[str, PipelineResult]) -> None:
    report = results["S6"].report
    assert report.inferences[0].confidence == Confidence.MEDIUM
    assert any("turn_cpu_pct" in item for item in report.hypotheses[0].missing_evidence)
    assert any("Trừ 1 bậc" in item for item in report.inferences[0].confidence_reasons)


def test_client_cpu_counter_reduces_confidence(m3_results: dict[str, M3Result]) -> None:
    ctx = context(m3_results["S1"])
    reference = ctx.facts.query(FactKind.METRIC_CHANGE)[0]
    client = ctx.facts.query(FactKind.METRIC_LEVEL, metric="client_cpu_pct")[0]
    client.kind = FactKind.METRIC_CHANGE
    client.data = {"metric": "client_cpu_pct", "category": "resource", "interval_ids": list(reference.data["interval_ids"])}
    reasoning = reason(ctx)
    turn = next(i for i in reasoning.inferences if i.rule_id == "TURN_OVERLOAD_DEGRADATION")
    assert turn.confidence == Confidence.MEDIUM
    assert turn.counter_evidence[0].fact_ids == [client.fact_id]


def test_resource_fact_from_other_interval_cannot_accuse_turn(m3_results: dict[str, M3Result]) -> None:
    ctx = context(m3_results["S1"])
    turn = ctx.facts.query(FactKind.METRIC_CHANGE, metric="turn_cpu_pct")[0]
    turn.data["interval_ids"] = ["inc-02"]
    assert turn_cpu_high_overlap(ctx).state == CondState.UNKNOWN
    assert not any(i.rule_id == "TURN_OVERLOAD_DEGRADATION" for i in reason(ctx).inferences)


def test_turn_metric_from_different_server_is_not_evidence(m3_results: dict[str, M3Result]) -> None:
    ctx = context(m3_results["S1"])
    turn = ctx.facts.query(FactKind.METRIC_CHANGE, metric="turn_cpu_pct")[0]
    turn.source = "turn-other"
    turn.data["on_path"] = False
    assert turn_cpu_on_path_high(ctx).state == CondState.UNKNOWN


def test_normal_turn_cpu_is_contradicting_evidence(m3_results: dict[str, M3Result]) -> None:
    ctx = context(m3_results["S1"])
    turn = ctx.facts.query(FactKind.METRIC_CHANGE, metric="turn_cpu_pct")[0]
    turn.kind = FactKind.METRIC_LEVEL
    turn.data = {"scope": "interval", "interval_id": "inc-01", "metric": "turn_cpu_pct", "anomalous": False}
    assert turn_cpu_on_path_high(ctx).state == CondState.FALSE
    assert any(r.rule_id == "TURN_OVERLOAD_DEGRADATION" for r in reason(ctx).rejected)


def test_missing_qos_does_not_support_healthy(m3_results: dict[str, M3Result]) -> None:
    ctx = context(m3_results["S0"])
    normal = ctx.facts.query(FactKind.METRIC_LEVEL)[0]
    normal.kind = FactKind.MISSING_DATA
    assert qos_incident(ctx).state == no_qos_anomaly(ctx).state == CondState.UNKNOWN
    assert not reason(ctx).inferences


def test_conditions_use_facts_and_do_not_modify_them(m3_results: dict[str, M3Result]) -> None:
    ctx = context(m3_results["S1"])
    before = [fact.model_dump_json() for fact in ctx.facts.all()]
    expected = reason(ctx)
    ctx.phases = []
    ctx.path = m3_results["S5"].path
    ctx.anomalies = m3_results["S5"].anomalies
    assert reason(ctx) == expected
    assert [fact.model_dump_json() for fact in ctx.facts.all()] == before


def test_missing_phase_facts_are_unknown(m3_results: dict[str, M3Result]) -> None:
    ctx = context(m3_results["S0"])
    ctx.facts = FactStore()
    assert all_phases_ok(ctx).state == via_turn(ctx).state == CondState.UNKNOWN
    assert not reason(ctx).inferences


def test_unrelated_rule_without_preconditions_is_not_rejected(m3_results: dict[str, M3Result]) -> None:
    ctx = context(m3_results["S0"])
    rule = replace(RULES[2], preconditions=(), required=(lambda ctx: ConditionResult(name="test", description="Không liên quan", state=CondState.FALSE, fact_ids=[]),))
    output = reason(ctx, (rule,))
    assert output.rejected == output.hypotheses == output.inferences == []


def test_confidence_floor_booster_absence_and_rule_order(m3_results: dict[str, M3Result]) -> None:
    ctx = context(m3_results["S1"])
    true = lambda ctx: ConditionResult(name="test", description="Có FACT", state=CondState.TRUE, fact_ids=[ctx.facts.all()[0].fact_id])
    unknown = lambda ctx: ConditionResult(name="unknown", description="Chưa biết", state=CondState.UNKNOWN, fact_ids=[])
    base = RuleSpec("CUSTOM", "Test", 1, (true,), (true,), lambda ctx: "Kết luận", lambda ctx: "Giả thuyết", boosters=(unknown,), counters=(true, true), missing_penalties=(true,))
    output = reason(ctx, (base, replace(base, rule_id="SECOND")))
    assert [i.rule_id for i in output.inferences] == ["CUSTOM", "SECOND"]
    assert all(i.confidence == Confidence.LOW for i in output.inferences)
    assert any("chưa có booster" in text for text in output.inferences[0].confidence_reasons)
