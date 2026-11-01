"""Render the complete report to Markdown without reading or writing files."""

from html import escape
from datetime import datetime
import re

from calldiag import config
from calldiag.models import IncidentReport
from calldiag.pipeline.report import report_window
from calldiag.utils import fmt_time, fmt_window


def _cell(value: object) -> str:
    if value is None:
        return "—"
    return escape(str(value), quote=False).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return "_Không có._"
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(_cell(cell) for cell in row) + " |" for row in rows),
    ])


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {_cell(item)}" for item in items) if items else "_Không có._"


def _time(ts: datetime | None) -> str:
    return fmt_time(ts, ms=True) if ts is not None else "—"


def render_markdown(report: IncidentReport) -> str:
    summary = report.summary
    parts = [
        f"# Incident Report: {_cell(report.scope.call_id)}",
        f"> **{_cell(summary.headline)}**",
        _table(["Severity", "Confidence", "Incident window", "Media path", "Failed phase"], [[
            summary.severity.value, summary.confidence.value if summary.confidence is not None else None,
            report_window(report) if summary.has_incident else "—", report.scope.path,
            summary.failed_phase.value if summary.failed_phase is not None else None,
        ]]),
        "## 1. Call lifecycle (5 phase)",
        _table(["Phase", "Status", "Start", "End", "Duration"], [[
            phase.label, f"{config.PHASE_STATUS_ICONS[phase.status]} {phase.status.value}",
            _time(phase.start_ts), _time(phase.end_ts),
            f"{phase.duration_ms} ms" if phase.duration_ms is not None else None,
        ] for phase in report.phases]),
        "## 2. Trace metrics",
    ]
    metrics = report.trace_metrics
    rows: list[list[object]] = [[name, f"{getattr(metrics, name)} ms" if getattr(metrics, name) is not None else None] for name in config.TRACE_METRIC_EVENTS]
    rows += [["end_reason", metrics.end_reason], ["candidate_counts", ", ".join(f"{key}: {count}" for key, count in metrics.candidate_counts.items())]]
    rows += [["pair result", f"{pair['event_id']}: {pair['local_type']}↔{pair['remote_type']} {pair['result']}" + (f" ({pair['error']})" if pair["error"] is not None else "")] for pair in metrics.pair_results]
    parts += [_table(["Metric", "Value"], rows), "## 3. Timeline"]
    timeline = "\n".join(f"{fmt_time(item.ts, ms=True)}  [{item.component}]  {item.summary}  ({item.ref_id})" for item in report.timeline)
    fence = "`" * max(3, max((len(run) + 1 for run in re.findall(r"`+", timeline)), default=0))
    parts += [f"{fence}text\n{timeline}\n{fence}" if timeline else "_Không có._", "## 4. FACTS"]
    parts += [_table(["ID", "Time / Window", "Kind", "Statement", "Refs"], [[
        fact.fact_id, fmt_window(fact.window_start, fact.window_end) if fact.window_start is not None and fact.window_end is not None else _time(fact.ts),
        fact.kind.value, fact.statement, ", ".join(fact.refs),
    ] for fact in report.facts]), "## 5. Related logs"]
    parts += [_table(["Log", "Time", "Component", "Level", "On path", "Message"], [[
        log.log_id, _time(log.ts), log.component, log.level.value, str(log.on_path), log.message,
    ] for log in report.related_logs]), "## 6. INFERENCES"]
    if not report.inferences:
        parts.append("_Không có._")
    for inference in report.inferences:
        parts += [
            f"### {inference.inference_id} · {_cell(inference.rule_id)} · Confidence {inference.confidence.value}",
            f"**Kết luận:** {_cell(inference.conclusion)}",
            f"**Supported by:** {', '.join(inference.supported_by)}",
            "**Lý do confidence:**", _bullets(inference.confidence_reasons),
            "**Counter-evidence:**", _bullets([f"{item.description} ({', '.join(item.fact_ids)})" for item in inference.counter_evidence]),
            "**Alternatives:**", _bullets(inference.alternatives),
            "<details><summary>Điều kiện của rule</summary>",
            _table(["Name", "State", "Facts", "Description / Note"], [[
                condition.name, condition.state.value, ", ".join(condition.fact_ids),
                condition.description + (f": {condition.note}" if condition.note else ""),
            ] for condition in inference.conditions]), "</details>",
        ]
    parts.append("## 7. HYPOTHESES")
    if not report.hypotheses:
        parts.append("_Không có._")
    for hypothesis in report.hypotheses:
        parts += [f"### {hypothesis.hypothesis_id} · {_cell(hypothesis.rule_id)}", _cell(hypothesis.statement),
                  f"**Supporting facts:** {', '.join(hypothesis.supporting_fact_ids)}", "**Missing evidence:**", _bullets(hypothesis.missing_evidence),
                  "**How to verify:**", _bullets(hypothesis.how_to_verify)]
    parts.append("## 8. REJECTED")
    if not report.rejected:
        parts.append("_Không có._")
    for rejected in report.rejected:
        parts += [f"### {rejected.rejected_id} · {_cell(rejected.rule_id)}", _cell(rejected.statement),
                  f"**Contradicting facts:** {', '.join(rejected.contradicting_fact_ids)}", f"**Reason:** {_cell(rejected.reason)}"]
    parts += ["## 9. UNKNOWN", _bullets(report.unknowns), "## 10. NEXT CHECK", _bullets(report.next_checks), "## 11. Evidence bundle"]
    if not report.evidence:
        parts.append("_Không có._")
    for evidence in report.evidence:
        parts += [f"### {evidence.evidence_id} · {evidence.focus.value}",
                  f"Focus: {_cell(evidence.focus_ref)} · {fmt_window(evidence.focus_start, evidence.focus_end)}",
                  f"Window: {fmt_window(evidence.window_start, evidence.window_end)}",
                  _cell(evidence.clock_alignment), "**Missing evidence:**", _bullets(evidence.missing_evidence)]
    parts += ["## 12. Engineering summary", _cell(report.engineering_summary), "## 13. Executive summary", _cell(report.executive_summary), "## Validation"]
    if report.validation is None:
        parts.append("_Chưa chạy._")
    else:
        parts.append("passed ✅" if report.validation.passed else "failed ❌")
        parts.append(_bullets([f"{issue.level} {issue.code}: {issue.message}" + (f" ({issue.ref})" if issue.ref else "") for issue in report.validation.issues]))
    return "\n\n".join(parts) + "\n"
