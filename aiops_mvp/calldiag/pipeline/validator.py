"""Validate refs, provenance, confidence and narrative guardrails."""

from collections import Counter
from decimal import Decimal
import json
import re

from calldiag import config
from calldiag.models import (
    CallTelemetry, Confidence, IncidentReport, ValidationIssue, ValidationResult,
)
from calldiag.pipeline.anomaly import detect_anomalies
from calldiag.pipeline.phases import localize_phases
from calldiag.pipeline.report import build_engineering_summary, build_executive_summary, report_window


def _citations(text: str) -> set[str]:
    return {match for group in re.findall(r"\[((?:[FI]\d+\s*,?\s*)+)\]", text) for match in re.findall(r"[FI]\d+", group)}


def _numbers(text: str) -> set[Decimal]:
    return {Decimal(number.replace(",", ".")) for number in re.findall(r"(?<![\w])\d+(?:[.,]\d+)?", text)}


def validate_report(report: IncidentReport, bundle: CallTelemetry) -> ValidationResult:
    issues = [issue.model_copy(deep=True) for issue in report.validation.issues] if report.validation else []

    def add(code: str, message: str, ref: str | None = None, level: str = "error") -> None:
        issue = ValidationIssue(level=level, code=code, message=message, ref=ref)
        if issue not in issues:
            issues.append(issue)

    collections = (report.facts, report.inferences, report.hypotheses, report.rejected)
    names = ("fact_id", "inference_id", "hypothesis_id", "rejected_id")
    all_ids = [getattr(item, field) for items, field in zip(collections, names) for item in items]
    for item_id, count in Counter(all_ids).items():
        if count > 1:
            add("E_DUP_ID", f"ID bị trùng: {item_id}", item_id)
    # Report stores intervals but not MetricAnomaly; rebuild from the raw input
    # rather than accepting IDs asserted by a FACT itself.
    anomalies = detect_anomalies(bundle, localize_phases(bundle))
    refs = {
        "ev-": {e.event_id for e in bundle.events}, "log-": {log.log_id for log in bundle.logs},
        "m-": {s.sample_id for s in bundle.metrics}, "an-": {a.anomaly_id for a in anomalies.anomalies},
        "inc-": {i.interval_id for i in anomalies.incidents},
    }
    fact_ids = {fact.fact_id for fact in report.facts}
    inference_ids = {item.inference_id for item in report.inferences}
    for fact in report.facts:
        if not fact.refs:
            add("E_FACT_NO_REF", "FACT không có refs", fact.fact_id)
        for ref in fact.refs:
            if not any(ref.startswith(prefix) and ref in targets for prefix, targets in refs.items()):
                add("E_FACT_BAD_REF", f"FACT ref không tồn tại: {ref}", fact.fact_id)
        if any(word.lower() in fact.statement.lower() for word in config.BANNED_FACT_WORDS):
            add("E_FACT_BANNED_WORD", "FACT chứa từ nhân quả/suy diễn bị cấm", fact.fact_id)
    for inference in report.inferences:
        if not inference.supported_by:
            add("E_INF_NO_SUPPORT", "INFERENCE không có supported_by", inference.inference_id)
        if not set(inference.supported_by) <= fact_ids:
            add("E_INF_BAD_SUPPORT", "supported_by có ID không phải FACT tồn tại", inference.inference_id)
        if any(not set(counter.fact_ids) <= fact_ids for counter in inference.counter_evidence):
            add("E_COUNTER_BAD_REF", "Counter-evidence có FACT không tồn tại", inference.inference_id)
        if inference.confidence not in tuple(Confidence):
            add("E_CONFIDENCE", "Confidence của INFERENCE không hợp lệ", inference.inference_id)
        if any(not set(condition.fact_ids) <= fact_ids for condition in inference.conditions):
            add("E_INF_BAD_SUPPORT", "Condition có FACT không tồn tại", inference.inference_id)
    for hypothesis in report.hypotheses:
        if not hypothesis.missing_evidence:
            add("E_HYP_NO_MISSING", "HYPOTHESIS không có missing_evidence", hypothesis.hypothesis_id)
        if not set(hypothesis.supporting_fact_ids) <= fact_ids:
            add("E_INF_BAD_SUPPORT", "HYPOTHESIS có FACT không tồn tại", hypothesis.hypothesis_id)
    for rejected in report.rejected:
        if not set(rejected.contradicting_fact_ids) <= fact_ids:
            add("E_INF_BAD_SUPPORT", "REJECTED có FACT không tồn tại", rejected.rejected_id)
    if report.summary.confidence is not None and report.summary.confidence not in tuple(Confidence):
        add("E_CONFIDENCE", "Confidence của primary không hợp lệ", report.summary.primary_inference_id)
    primary = next((i for i in report.inferences if i.inference_id == report.summary.primary_inference_id), None)
    if (report.summary.primary_inference_id is not None and primary is None) or (inference_ids and primary is None):
        add("E_PRIMARY", "Primary inference không tồn tại", report.summary.primary_inference_id)
    elif primary is not None and (report.summary.primary_rule_id != primary.rule_id or report.summary.confidence != primary.confidence):
        add("E_PRIMARY", "Primary rule/confidence không khớp INFERENCE", primary.inference_id)
    narrative = report.engineering_summary + "\n" + report.executive_summary
    unknown_cites = _citations(narrative) - fact_ids - inference_ids
    if unknown_cites:
        add("W_SUMMARY_UNKNOWN_CITE", "Summary trích ID không tồn tại: " + ", ".join(sorted(unknown_cites)), level="warning")
    if report.summary_source == "llm":
        from calldiag.llm.summary import build_llm_input  # local: llm depends on the pipeline, not the reverse

        # Numbers may come only from what the LLM was shown.
        allowed = _numbers(json.dumps(build_llm_input(report), ensure_ascii=False))
        new_numbers = {n for n in _numbers(narrative) - allowed if n > config.SUMMARY_SMALL_NUMBER_LIMIT}
        if new_numbers:
            add("W_SUMMARY_NEW_NUMBER", "Summary LLM thêm số không có trong dữ liệu đầu vào: " + ", ".join(str(n) for n in sorted(new_numbers)), level="warning")
        # A bracket must hold an ID list; "[unknowns]" or "[nguồn]" would pose as evidence.
        known = fact_ids | inference_ids | {h.hypothesis_id for h in report.hypotheses} | {r.rejected_id for r in report.rejected}
        bad = [group for group in re.findall(r"\[([^\]]*)\]", narrative)
               if not re.fullmatch(r"\s*[FIHR]\d+(\s*,\s*[FIHR]\d+)*\s*", group)
               or not set(re.findall(r"[FIHR]\d+", group)) <= known]
        if bad:
            add("W_SUMMARY_BAD_CITE", "Summary LLM có ngoặc vuông không phải danh sách ID hợp lệ: " + ", ".join(f"[{b}]" for b in bad), level="warning")
        if not _citations(report.engineering_summary):
            add("W_SUMMARY_NO_CITE", "Engineering summary của LLM không trích FACT/INFERENCE nào", level="warning")
        if _citations(report.executive_summary):
            add("W_SUMMARY_EXEC_CITE", "Executive summary của LLM chứa trích dẫn ID", level="warning")
        words = len(report.executive_summary.split())
        if words > config.EXEC_SUMMARY_MAX_WORDS:
            add("W_SUMMARY_TOO_LONG", f"Executive summary của LLM dài {words} từ (tối đa {config.EXEC_SUMMARY_MAX_WORDS})", level="warning")
    return ValidationResult(passed=not any(issue.level == "error" for issue in issues), issues=issues)


def apply_validation(report: IncidentReport, result: ValidationResult) -> IncidentReport:
    output = report.model_copy(deep=True)
    bad_inferences = {issue.ref for issue in result.issues if issue.level == "error" and (
        issue.code.startswith("E_INF_") or issue.code in {"E_COUNTER_BAD_REF", "E_CONFIDENCE", "E_DUP_ID"}
    )}
    bad_facts = {issue.ref for issue in result.issues if issue.level == "error" and issue.code.startswith("E_FACT_")}
    output.inferences = [i for i in output.inferences if i.inference_id not in bad_inferences and not set(i.supported_by) & bad_facts]
    primary = next((i for i in output.inferences if i.inference_id == output.summary.primary_inference_id), None)
    if primary is None:
        primary = next(iter(output.inferences), None)
    output.summary.primary_inference_id = primary.inference_id if primary else None
    output.summary.primary_rule_id = primary.rule_id if primary else None
    output.summary.confidence = primary.confidence if primary else None
    output.summary.headline = config.REPORT_HEADLINES.get(primary.rule_id, "Không đủ evidence để kết luận").format(window=report_window(output)) if primary else "Không đủ evidence để kết luận"
    summary_warning = any(issue.level == "warning" for issue in result.issues)
    if output.inferences != report.inferences or (output.summary_source == "llm" and summary_warning):
        output.summary_source = "template"
        output.engineering_summary = build_engineering_summary(output)
        output.executive_summary = build_executive_summary(output)
    output.validation = result.model_copy(deep=True)
    return output
