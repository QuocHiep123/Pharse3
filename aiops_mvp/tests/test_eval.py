"""Benchmark checks (plan 11): all scenarios pass, and each check really fails when it should."""

from dataclasses import replace
from pathlib import Path

import pytest

from calldiag import cli
from calldiag import eval as evaluation
from calldiag.eval import NA_MARK, CheckResult, ScenarioEval, evaluate, render_eval_markdown, render_eval_table
from calldiag.models import PipelineResult
from calldiag.scenarios import REGISTRY


@pytest.fixture(scope="module")
def evals(results: dict[str, PipelineResult]) -> list[ScenarioEval]:
    return [evaluate(sid, results[sid], REGISTRY[sid].expected) for sid in REGISTRY]


def test_every_scenario_passes(evals: list[ScenarioEval]) -> None:
    failed = [(e.scenario_id, c.name, c.expected, c.actual) for e in evals for c in e.checks if not c.passed]
    assert not failed
    assert [e.scenario_id for e in evals] == list(REGISTRY)


def test_not_applicable_checks_are_skipped_and_marked(evals: list[ScenarioEval]) -> None:
    s0 = evals[0]
    assert s0.check("interval") is None and s0.check("required_missing") is None
    assert s0.check("required_inferences") is not None
    row = next(line for line in render_eval_table(evals).splitlines() if line.startswith("S0"))
    assert NA_MARK in row


def _one(sid: str, results: dict[str, PipelineResult], **changes: object) -> ScenarioEval:
    return evaluate(sid, results[sid], replace(REGISTRY[sid].expected, **changes))


@pytest.mark.parametrize(("sid", "changes", "check"), [
    ("S1", {"primary_rule": "NETWORK_PATH_DEGRADATION"}, "primary_rule"),
    ("S6", {"primary_confidence": "High"}, "primary_confidence"),
    ("S1", {"severity": "minor"}, "severity"),
    ("S0", {"has_incident": True}, "has_incident"),
    ("S1", {"qos_interval_offset": (60, 85)}, "interval"),
    ("S3", {"phase_status": {"call_setup": "ok", "offer_answer": "ok", "ice": "ok", "media": "ok", "termination": "ok"}}, "phase_status"),
    ("S1", {"required_hypotheses": ("TURN_OVERLOAD_DEGRADATION",)}, "required_hypotheses"),
    ("S2", {"required_rejected": ("NETWORK_PATH_DEGRADATION",)}, "required_rejected"),
    ("S1", {"forbidden_inferences": ("TURN_OVERLOAD_DEGRADATION",)}, "forbidden_inferences"),
    ("S1", {"required_missing_metrics": ("turn-01/turn_cpu_pct",)}, "required_missing"),
])
def test_each_check_detects_a_wrong_expectation(
    sid: str, changes: dict, check: str, results: dict[str, PipelineResult],
) -> None:
    result = _one(sid, results, **changes)
    failed = [c.name for c in result.checks if not c.passed]
    assert failed == [check] and not result.passed


def test_interval_tolerance_boundary(results: dict[str, PipelineResult]) -> None:
    # S1 incident is 79–104 s; tolerance is 5 s on each end.
    assert _one("S1", results, qos_interval_offset=(84, 99)).check("interval").passed
    assert not _one("S1", results, qos_interval_offset=(85, 104)).check("interval").passed


def test_validation_and_traceability_catch_broken_reports(results: dict[str, PipelineResult]) -> None:
    broken = results["S1"].model_copy(deep=True)
    broken.report.inferences[0].supported_by = ["F999"]
    broken.report.validation.passed = False
    result = evaluate("S1", broken, REGISTRY["S1"].expected)
    assert {c.name for c in result.checks if not c.passed} == {"validation", "traceability"}
    assert "I1" in result.check("traceability").actual


def test_markdown_lists_failed_checks() -> None:
    evals = [ScenarioEval("S9", "Thử", False, [CheckResult("severity", False, "major", "minor")])]
    markdown = render_eval_markdown(evals)
    assert "0/1 PASS" in markdown and "| S9 | severity | major | minor |" in markdown


def test_cli_eval_writes_report_and_exit_code(
    tmp_path: Path, evals: list[ScenarioEval], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(evaluation, "run_eval", lambda: evals)
    assert cli.main(["eval", "--out", str(tmp_path)]) == 0
    assert "7/7 PASS" in (tmp_path / "eval.md").read_text(encoding="utf-8")
    assert capsys.readouterr().out.count("PASS") == 8      # 7 rows + total
    failing = [replace(evals[0], passed=False)]
    monkeypatch.setattr(evaluation, "run_eval", lambda: failing)
    assert cli.main(["eval", "--out", str(tmp_path)]) == 1


def test_run_eval_end_to_end() -> None:
    assert all(e.passed for e in evaluation.run_eval())
