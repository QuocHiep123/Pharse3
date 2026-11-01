"""Benchmark the pipeline against each scenario's ExpectedOutcome (plan 11).

Evaluation sits outside the pipeline: it may read scenario labels and ground truth,
the pipeline itself never does.
"""

from dataclasses import dataclass

from calldiag import config
from calldiag.models import FactKind, PipelineResult
from calldiag.pipeline.run import run_scenario
from calldiag.scenarios import REGISTRY
from calldiag.scenarios.expected import ExpectedOutcome
from calldiag.utils import offset_sec

PASS_MARK, FAIL_MARK, NA_MARK = "✓", "✗", "–"
# Table column → the checks it aggregates. A column whose checks were all skipped shows NA_MARK.
COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("phase", ("phase_status",)),
    ("incident", ("has_incident",)),
    ("interval", ("interval",)),
    ("primary", ("primary_rule",)),
    ("conf", ("primary_confidence",)),
    ("sev", ("severity",)),
    ("req", ("required_inferences", "required_hypotheses", "required_rejected")),
    ("forbid", ("forbidden_inferences",)),
    ("missing", ("required_missing",)),
    ("valid", ("validation",)),
    ("trace", ("traceability",)),
)


@dataclass
class CheckResult:
    name: str
    passed: bool
    expected: str
    actual: str


@dataclass
class ScenarioEval:
    scenario_id: str
    title: str
    passed: bool
    checks: list[CheckResult]

    def check(self, name: str) -> CheckResult | None:
        return next((c for c in self.checks if c.name == name), None)

    def actual(self, name: str) -> str:
        check = self.check(name)
        return check.actual if check is not None else NA_MARK


def _list(items: list[str] | tuple[str, ...]) -> str:
    return ", ".join(items) if items else "(không có)"


def _offsets(result: PipelineResult) -> tuple[float, float] | None:
    summary, start = result.report.summary, result.bundle.meta.start_ts
    if summary.incident_window_start is None or summary.incident_window_end is None:
        return None
    return offset_sec(summary.incident_window_start, start), offset_sec(summary.incident_window_end, start)


def evaluate(sid: str, result: PipelineResult, expected: ExpectedOutcome) -> ScenarioEval:
    report, summary = result.report, result.report.summary
    checks: list[CheckResult] = []

    def add(name: str, passed: bool, want: str, got: str) -> None:
        checks.append(CheckResult(name, passed, want, got))

    statuses = {phase.phase.value: phase.status.value for phase in report.phases}
    add("phase_status", statuses == expected.phase_status,
        " · ".join(expected.phase_status.values()), " · ".join(statuses.get(p, "?") for p in expected.phase_status))
    add("has_incident", summary.has_incident == expected.has_incident, str(expected.has_incident), str(summary.has_incident))
    if expected.qos_interval_offset is not None:
        want_start, want_end = expected.qos_interval_offset
        got = _offsets(result)
        tolerance = config.EVAL_INTERVAL_TOLERANCE_SEC
        add("interval", got is not None and abs(got[0] - want_start) <= tolerance and abs(got[1] - want_end) <= tolerance,
            f"{want_start:g}–{want_end:g} s (±{tolerance} s)", f"{got[0]:g}–{got[1]:g} s" if got else "không có incident window")
    add("primary_rule", summary.primary_rule_id == expected.primary_rule, expected.primary_rule, str(summary.primary_rule_id))
    confidence = summary.confidence.value if summary.confidence is not None else "None"
    add("primary_confidence", confidence == expected.primary_confidence, expected.primary_confidence, confidence)
    add("severity", summary.severity.value == expected.severity, expected.severity, summary.severity.value)

    found = {
        "required_inferences": [i.rule_id for i in report.inferences],
        "required_hypotheses": [h.rule_id for h in report.hypotheses],
        "required_rejected": [r.rule_id for r in report.rejected],
    }
    for name, actual in found.items():
        wanted = getattr(expected, name)
        if wanted:
            add(name, all(rule in actual for rule in wanted), _list(wanted), _list(actual))
    if expected.forbidden_inferences:
        hits = [rule for rule in found["required_inferences"] if rule in expected.forbidden_inferences]
        add("forbidden_inferences", not hits, f"không có {_list(expected.forbidden_inferences)}",
            f"có {_list(hits)}" if hits else "không có")
    if expected.required_missing_metrics:
        missing = [f"{f.source}/{f.metric.value}" for f in report.facts if f.kind == FactKind.MISSING_DATA and f.metric is not None]
        add("required_missing", all(m in missing for m in expected.required_missing_metrics),
            _list(expected.required_missing_metrics), _list(missing))

    errors = [i.code for i in report.validation.issues if i.level == "error"] if report.validation else ["chưa chạy"]
    passed = report.validation is not None and report.validation.passed and not errors
    add("validation", passed, "passed, 0 error", "passed" if passed else f"failed: {_list(errors)}")

    fact_ids = {fact.fact_id for fact in report.facts}
    claims = ([(i.inference_id, i.supported_by) for i in report.inferences]
              + [(h.hypothesis_id, h.supporting_fact_ids) for h in report.hypotheses]
              + [(r.rejected_id, r.contradicting_fact_ids) for r in report.rejected])
    broken = [cid for cid, cited in claims if (not cited and cid.startswith("I")) or not set(cited) <= fact_ids]
    add("traceability", not broken, "mọi INFERENCE/HYPOTHESIS/REJECTED trích FACT có thật",
        f"{len(claims) - len(broken)}/{len(claims)} hợp lệ" + (f" (lỗi: {_list(broken)})" if broken else ""))

    return ScenarioEval(sid, REGISTRY[sid].title if sid in REGISTRY else sid, all(c.passed for c in checks), checks)


def run_eval() -> list[ScenarioEval]:
    return [evaluate(sid, run_scenario(sid), scenario.expected) for sid, scenario in REGISTRY.items()]


def _marks(evaluation: ScenarioEval) -> list[str]:
    marks = []
    for _, names in COLUMNS:
        checks = [c for name in names if (c := evaluation.check(name)) is not None]
        marks.append(NA_MARK if not checks else PASS_MARK if all(c.passed for c in checks) else FAIL_MARK)
    return marks


def _total(evals: list[ScenarioEval]) -> str:
    return f"{sum(e.passed for e in evals)}/{len(evals)} PASS"


def render_eval_table(evals: list[ScenarioEval]) -> str:
    title_width = max([len("Title"), *(len(e.title) for e in evals)])
    header = ["Scenario", "Title".ljust(title_width), *(name for name, _ in COLUMNS), "RESULT"]
    widths = [len(h) for h in header]
    lines = ["  ".join(header)]
    for e in evals:
        cells = [e.scenario_id, e.title, *_marks(e), "PASS" if e.passed else "FAIL"]
        lines.append("  ".join(cell.ljust(width) for cell, width in zip(cells, widths)).rstrip())
    return "\n".join([*lines, _total(evals)])


def render_eval_markdown(evals: list[ScenarioEval]) -> str:
    def row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    headers = ["Scenario", "Title", *(name for name, _ in COLUMNS), "Result"]
    parts = [
        "# CallDiag eval",
        f"**{_total(evals)}** · tolerance khoảng incident ±{config.EVAL_INTERVAL_TOLERANCE_SEC} s · "
        f"{PASS_MARK} đạt · {FAIL_MARK} trượt · {NA_MARK} không áp dụng cho kịch bản",
        "\n".join([row(headers), row(["---"] * len(headers)),
                   *(row([e.scenario_id, e.title, *_marks(e), "**PASS**" if e.passed else "**FAIL**"]) for e in evals)]),
        "## Kết luận của hệ thống",
        "\n".join([row(["Scenario", "Primary rule", "Confidence", "Severity", "Incident (s)"]), row(["---"] * 5), *(
            row([e.scenario_id, *(e.actual(name) for name in ("primary_rule", "primary_confidence", "severity", "interval"))])
            for e in evals)]),
        "## Check trượt",
    ]
    failed = [(e, c) for e in evals for c in e.checks if not c.passed]
    if failed:
        parts.append("\n".join([row(["Scenario", "Check", "Expected", "Actual"]), row(["---"] * 4),
                                *(row([e.scenario_id, c.name, c.expected, c.actual]) for e, c in failed)]))
    else:
        parts.append("_Không có check nào trượt._")
    return "\n\n".join(parts) + "\n"
