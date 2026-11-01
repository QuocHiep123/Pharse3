"""End-to-end local diagnosis orchestration without file I/O."""

from calldiag.io import validate_bundle
from calldiag.models import CallTelemetry, PipelineResult
from calldiag.pipeline.anomaly import detect_anomalies
from calldiag.pipeline.correlate import build_path_context, correlate
from calldiag.pipeline.facts import extract_facts
from calldiag.pipeline.phases import compute_trace_metrics, extract_selected_path, localize_phases, mark_degraded
from calldiag.pipeline.reasoning import reason
from calldiag.pipeline.report import assemble_report
from calldiag.pipeline.rules import Ctx
from calldiag.pipeline.timeline import build_timeline
from calldiag.pipeline.validator import apply_validation, validate_report


def run_pipeline(bundle: CallTelemetry, *, use_llm: bool = False) -> PipelineResult:
    validate_bundle(bundle)
    phases = localize_phases(bundle)
    selected = extract_selected_path(bundle)
    trace = compute_trace_metrics(bundle, phases, selected)
    anomalies = detect_anomalies(bundle, phases)
    phases = mark_degraded(phases, anomalies)
    path = build_path_context(bundle, selected)
    evidence = correlate(bundle, phases, anomalies, path)
    facts = extract_facts(bundle, phases, trace, path, anomalies, evidence)
    reasoning = reason(Ctx(facts, phases, path, anomalies, evidence))
    report = assemble_report(
        bundle=bundle, phases=phases, trace=trace, path_ctx=path, anomalies=anomalies,
        evidence=evidence, facts=facts, reasoning=reasoning, timeline=build_timeline(bundle, anomalies),
    )
    if use_llm:
        from calldiag.llm.summary import add_llm_summary  # optional feature; keeps the SDK import lazy

        report = add_llm_summary(report)
    report = apply_validation(report, validate_report(report, bundle))
    return PipelineResult(bundle=bundle, phases=phases, path=path, anomalies=anomalies, evidence=evidence, report=report)


def run_scenario(scenario_id: str, *, use_llm: bool = False) -> PipelineResult:
    from calldiag.scenarios import get_scenario
    result = run_pipeline(get_scenario(scenario_id).build(), use_llm=use_llm)
    result.report.scenario_id = scenario_id
    return result
