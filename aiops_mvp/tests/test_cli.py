from pathlib import Path
import json
import os
import subprocess
import sys

import pytest

from calldiag import cli
from calldiag.io import save_bundle, save_pipeline_outputs
from calldiag.models import IncidentReport, PipelineResult, ValidationIssue, ValidationResult
from calldiag.scenarios import REGISTRY


def test_run_all_strict_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "--scenario", "all", "--strict", "--out", str(tmp_path)]) == 0
    for sid in REGISTRY:
        report_path = tmp_path / "reports" / f"{sid}.json"
        report = IncidentReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        assert report.validation.passed
        assert (tmp_path / "reports" / f"{sid}.md").is_file()
        trace = json.loads((tmp_path / "traces" / f"{sid}.otel.json").read_text(encoding="utf-8"))
        assert len(trace["spans"]) == 6
    assert len(list(tmp_path.rglob("*.json"))) == 14
    assert len(list(tmp_path.rglob("*.md"))) == 7
    stdout = capsys.readouterr().out
    assert stdout.count("validation: passed") == 7
    assert "severity=major  confidence=Medium" in stdout


def test_run_from_json_input(tmp_path: Path, results: dict[str, PipelineResult]) -> None:
    source = tmp_path / "input.json"
    save_bundle(results["S2"].bundle, source)
    assert cli.main(["run", "--input", str(source), "--out", str(tmp_path / "output"), "--strict"]) == 0
    report = IncidentReport.model_validate_json((tmp_path / "output/reports/S2.json").read_text(encoding="utf-8"))
    assert report.summary.primary_rule_id == "NETWORK_PATH_DEGRADATION"


def test_strict_returns_one_when_validation_fails(tmp_path: Path, results: dict[str, PipelineResult], monkeypatch: pytest.MonkeyPatch) -> None:
    invalid = results["S1"].model_copy(deep=True)
    invalid.report.validation = ValidationResult(passed=False, issues=[ValidationIssue(level="error", code="E_INF_BAD_SUPPORT", message="Test invalid support", ref="I1")])
    monkeypatch.setattr(cli, "run_pipeline", lambda *args, **kwargs: invalid)
    assert cli.main(["run", "--scenario", "S1", "--strict", "--out", str(tmp_path)]) == 1
    assert cli.main(["run", "--scenario", "S1", "--out", str(tmp_path)]) == 0


@pytest.mark.parametrize("args", [
    ["run"], ["run", "--scenario", "invalid"],
    ["run", "--scenario", "S1", "--input", "input.json"],
    ["run", "--input", "/nonexistent/calldiag.json"],
])
def test_invalid_cli_source_arguments(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2


def test_output_label_cannot_escape_output_directory(tmp_path: Path, results: dict[str, PipelineResult]) -> None:
    result = results["S1"].model_copy(deep=True)
    result.report.scenario_id = "../../escape"
    with pytest.raises(ValueError, match="filename"):
        save_pipeline_outputs(result, tmp_path / "outputs")
    assert not (tmp_path / "outputs").exists()


def test_module_run_all_strict_exit_zero(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    completed = subprocess.run(
        [sys.executable, "-m", "calldiag", "run", "--scenario", "all", "--strict"],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.count("validation: passed") == 7
    assert len(list((tmp_path / "out/reports").glob("*.json"))) == 7


def test_list_prints_every_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines] == list(REGISTRY)
    assert all(REGISTRY[line.split()[0]].description in line for line in lines)
