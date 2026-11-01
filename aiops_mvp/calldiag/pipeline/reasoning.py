"""Evaluate rule conditions without creating or modifying FACTs."""

from collections.abc import Sequence

from calldiag import config
from calldiag.models import (
    Confidence, ConditionResult, CondState, CounterEvidence, Hypothesis,
    Inference, ReasoningResult, RejectedHypothesis,
)
from calldiag.pipeline.rules import RULES, Ctx, RuleSpec


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _fact_ids(conditions: list[ConditionResult]) -> list[str]:
    return _unique([fid for condition in conditions for fid in condition.fact_ids])


def reason(ctx: Ctx, rules: Sequence[RuleSpec] = RULES) -> ReasoningResult:
    accepted: list[tuple[Inference, RuleSpec]] = []
    hypotheses: list[Hypothesis] = []
    rejected: list[RejectedHypothesis] = []
    hypothesis_rules: list[RuleSpec] = []
    for rule in rules:
        pre = [condition(ctx) for condition in rule.preconditions]
        if any(condition.state != CondState.TRUE for condition in pre):
            continue
        required = [condition(ctx) for condition in rule.required]
        false = [condition for condition in required if condition.state == CondState.FALSE]
        unknown = [condition for condition in required if condition.state == CondState.UNKNOWN]
        if false:
            if pre:
                rejected.append(RejectedHypothesis(
                    rejected_id=f"R{len(rejected) + 1}", rule_id=rule.rule_id,
                    statement=rule.hypothesis_statement(ctx), contradicting_fact_ids=_fact_ids(false),
                    reason=rule.rejection_reason(ctx, false) if rule.rejection_reason else "; ".join(
                        f"{condition.description} không đúng" + (f": {condition.note}" if condition.note else "") for condition in false),
                ))
            continue
        if unknown:
            if pre:
                hypotheses.append(Hypothesis(
                    hypothesis_id=f"H{len(hypotheses) + 1}", rule_id=rule.rule_id,
                    statement=rule.hypothesis_statement(ctx),
                    supporting_fact_ids=_fact_ids(pre + [c for c in required if c.state == CondState.TRUE]),
                    missing_evidence=[c.description + (f": {c.note}" if c.note else "") for c in unknown],
                    how_to_verify=rule.next_checks(ctx),
                ))
                hypothesis_rules.append(rule)
            continue
        boosters = [condition(ctx) for condition in rule.boosters]
        counters = [condition(ctx) for condition in rule.counters]
        penalties = [condition(ctx) for condition in rule.missing_penalties]
        support = _fact_ids(pre + required + [c for c in boosters if c.state == CondState.TRUE])
        if not support:
            continue
        level = len(config.CONFIDENCE_LEVELS) - 1
        reasons = [f"Mọi điều kiện bắt buộc thỏa ({', '.join(_fact_ids(pre + required))})"]
        for booster in boosters:
            if booster.state == CondState.TRUE:
                reasons.append(f"Booster: {booster.description} ({', '.join(booster.fact_ids)})")
        if boosters and not any(c.state == CondState.TRUE for c in boosters):
            level -= 1
            reasons.append("Trừ 1 bậc: chưa có booster được xác minh")
        counter_evidence: list[CounterEvidence] = []
        for counter in counters:
            if counter.state == CondState.TRUE:
                level -= 1
                counter_evidence.append(CounterEvidence(description=counter.description, fact_ids=counter.fact_ids))
                reasons.append(f"Trừ 1 bậc: counter-evidence {counter.description} ({', '.join(counter.fact_ids)})")
            elif counter.state == CondState.FALSE:
                reasons.append(f"Đã kiểm tra, không có phản chứng: {counter.description} ({', '.join(counter.fact_ids)})")
            else:
                reasons.append(f"Chưa xác minh phản chứng: {counter.description}")
        for penalty in penalties:
            if penalty.state == CondState.TRUE:
                level -= 1
                reasons.append(f"Trừ 1 bậc: {penalty.description} ({', '.join(penalty.fact_ids)})")
        accepted.append((Inference(
            inference_id="", rule_id=rule.rule_id, conclusion=rule.conclusion(ctx), supported_by=support,
            confidence=Confidence(config.CONFIDENCE_LEVELS[max(level, 0)]), confidence_reasons=reasons,
            counter_evidence=counter_evidence, alternatives=list(rule.alternatives),
            conditions=pre + required + boosters + counters + penalties,
            specificity=rule.specificity, focus_ref=ctx.focus_ref,
        ), rule))
    order = {id(rule): i for i, rule in enumerate(rules)}
    accepted.sort(key=lambda item: (-item[0].specificity, config.CONFIDENCE_ORDER[item[0].confidence], order[id(item[1])]))
    for i, (inference, _) in enumerate(accepted, start=1):
        inference.inference_id = f"I{i}"
    unknowns = _unique([item for _, rule in accepted for item in rule.unknowns]
                       + [item for rule in hypothesis_rules for item in rule.unknowns]
                       + [f"Thiếu dữ liệu: {item}" for evidence in ctx.evidence for item in evidence.missing_evidence])
    checks = _unique([item for _, rule in accepted for item in rule.next_checks(ctx)]
                     + [item for hypothesis in hypotheses for item in hypothesis.how_to_verify])[:config.MAX_NEXT_CHECKS]
    return ReasoningResult(
        inferences=[inference for inference, _ in accepted], hypotheses=hypotheses, rejected=rejected,
        primary_inference_id="I1" if accepted else None, unknowns=unknowns, next_checks=checks,
    )
