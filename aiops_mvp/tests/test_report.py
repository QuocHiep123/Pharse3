import re

import pytest

from calldiag import config
from calldiag.models import AnomalyResult, CallMeta, IncidentReport, Phase, PipelineResult, Severity
from calldiag.pipeline.render import render_markdown
from calldiag.pipeline.report import compute_severity
from calldiag.pipeline.run import run_pipeline, run_scenario
from calldiag.scenarios import REGISTRY


@pytest.mark.parametrize("sid", REGISTRY)
def test_report_outcome_and_round_trip(sid: str, results: dict[str, PipelineResult]) -> None:
    result = results[sid]
    report = result.report
    expected = REGISTRY[sid].expected
    assert report.validation.passed and report.validation.issues == []
    assert report.summary.severity == expected.severity
    assert report.summary.confidence == expected.primary_confidence
    assert report.summary.has_incident is expected.has_incident
    assert report.summary.primary_rule_id == expected.primary_rule
    assert {phase.phase.value: phase.status.value for phase in report.phases} == expected.phase_status
    assert IncidentReport.model_validate_json(report.model_dump_json()) == report
    assert PipelineResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("sid", REGISTRY)
def test_markdown_has_complete_sections(sid: str, results: dict[str, PipelineResult]) -> None:
    markdown = render_markdown(results[sid].report)
    numbered = re.findall(r"^## (\d+)\.", markdown, flags=re.MULTILINE)
    assert numbered == [str(i) for i in range(1, 14)]
    assert "## Validation\n\npassed ✅" in markdown
    assert "Supported by:" in markdown
    if sid == "S1":
        assert "TURN CPU (turn-01) tăng từ" in markdown
        assert "Lý do confidence:" in markdown and "Điều kiện của rule" in markdown
    if sid == "S6":
        assert "## 7. HYPOTHESES" in markdown and "turn_cpu_pct" in markdown
    if sid == "S2":
        assert "Contradicting facts:" in markdown


@pytest.mark.parametrize("sid", REGISTRY)
def test_pipeline_deterministic_except_generated_at(sid: str, results: dict[str, PipelineResult]) -> None:
    result = results[sid]
    before = result.bundle.model_dump_json()
    again = run_pipeline(result.bundle)
    assert again.report.model_dump(exclude={"generated_at", "scenario_id"}) == result.report.model_dump(exclude={"generated_at", "scenario_id"})
    assert again.report.scenario_id == ""
    assert result.bundle.model_dump_json() == before
    assert again.anomalies == result.anomalies


def test_engineering_citations_and_timeline_filtering(results: dict[str, PipelineResult]) -> None:
    for result in results.values():
        report = result.report
        ids = {f.fact_id for f in report.facts} | {i.inference_id for i in report.inferences}
        assert set(re.findall(r"\[([FI]\d+)\]", report.engineering_summary)) <= ids
        assert f"[{report.summary.primary_inference_id}]" in report.engineering_summary
        related = {log.log_id for log in report.related_logs}
        assert {item.ref_id for item in report.timeline if item.kind == "log"} == related
        assert {item.ref_id for item in report.timeline if item.kind == "event"} == {event.event_id for event in result.bundle.events}
        assert [log.ts for log in report.related_logs] == sorted(log.ts for log in report.related_logs)
        assert len(related) == len(report.related_logs)


def test_severity_minor_major_and_confidence_are_independent(results: dict[str, PipelineResult]) -> None:
    result = results["S1"]
    anomalies = result.anomalies.model_copy(deep=True)
    anomalies.incidents[0].duration_sec = config.MAJOR_INCIDENT_MIN_SEC - 1
    for anomaly in anomalies.anomalies:
        if anomaly.metric == "packet_loss_pct":
            anomaly.peak_value = config.MAJOR_LOSS_PCT - 1
    assert compute_severity(result.phases, anomalies) == Severity.MINOR
    next(a for a in anomalies.anomalies if a.metric == "packet_loss_pct").peak_value = config.MAJOR_LOSS_PCT
    assert compute_severity(result.phases, anomalies) == Severity.MAJOR
    assert compute_severity(result.phases, AnomalyResult(skipped=False)) == Severity.NONE
    assert results["S1"].report.summary.severity == results["S6"].report.summary.severity
    assert results["S1"].report.summary.confidence != results["S6"].report.summary.confidence


def test_no_data_has_no_inference_and_no_false_healthy_claim(results: dict[str, PipelineResult]) -> None:
    bundle = results["S0"].bundle.model_copy(deep=True)
    bundle.events = bundle.logs = bundle.metrics = []
    report = run_pipeline(bundle).report
    assert report.inferences == []
    assert report.summary.confidence is None
    assert report.summary.headline == "Không đủ evidence để kết luận"
    assert "Chưa đủ dữ liệu" in report.executive_summary
    assert report.validation.passed


def test_llm_request_without_configuration_keeps_template(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CALLDIAG_LLM_PROVIDER", "CALLDIAG_LLM_MODEL", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    report = run_scenario("S1", use_llm=True).report
    assert report.summary_source == "template" and report.validation.passed
    assert any(issue.code == "W_LLM_UNAVAILABLE" for issue in report.validation.issues)


def test_markdown_escapes_untrusted_table_content(results: dict[str, PipelineResult]) -> None:
    report = results["S1"].report.model_copy(deep=True)
    report.related_logs[0].message = "<script>alert(1)</script>|line\nnext"
    markdown = render_markdown(report)
    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown and "\\|line<br>next" in markdown


def test_scenario_labels_do_not_change_diagnosis(results: dict[str, PipelineResult]) -> None:
    result = results["S1"]
    bundle = result.bundle.model_copy(deep=True)
    bundle.meta.scenario_id = "opaque-label"
    bundle.meta.title = "Signaling timeout"
    bundle.meta.call_id = "opaque-call"
    for record in [*bundle.events, *bundle.metrics, *bundle.logs]:
        if record.call_id == result.bundle.meta.call_id:
            record.call_id = bundle.meta.call_id
    report = run_pipeline(bundle).report
    assert report.summary == result.report.summary
    assert report.facts == result.report.facts
    assert report.inferences == result.report.inferences
    assert report.scenario_id == "" and report.scope.call_id == "opaque-call"


def test_core_pipeline_does_not_read_scenario_metadata(results: dict[str, PipelineResult]) -> None:
    class GuardedMeta(CallMeta):
        def __getattribute__(self, name: str) -> object:
            if name in {"scenario_id", "title"}:
                raise AssertionError(f"Analysis read meta.{name}")
            return super().__getattribute__(name)

    bundle = results["S1"].bundle.model_copy(deep=True)
    bundle.meta = GuardedMeta.model_validate(bundle.meta.model_dump())
    report = run_pipeline(bundle).report
    assert report.scenario_id == ""
    assert report.summary.primary_rule_id == "TURN_OVERLOAD_DEGRADATION"


def test_engineering_summary_keeps_rtt_and_time_order(results: dict[str, PipelineResult]) -> None:
    report = results["S1"].report
    facts = {f.fact_id: f for f in report.facts}
    cited = [facts[fid] for fid in re.findall(r"\[(F\d+)\]", report.engineering_summary) if facts[fid].kind.value == "metric_change"]
    assert "rtt_ms" in {f.data["metric"] for f in cited}
    assert [f.ts for f in cited] == sorted(f.ts for f in cited)
    assert cited[0].data["metric"] == "turn_cpu_pct"


def test_s6_turn_cpu_gap_reported_once(results: dict[str, PipelineResult]) -> None:
    lines = [u for u in results["S6"].report.unknowns if "turn-01/turn_cpu_pct" in u]
    assert len(lines) == 1 and "collector không gửi dữ liệu" in lines[0]


@pytest.mark.parametrize("sid", REGISTRY)
def test_markdown_has_no_quote_entities_and_json_has_no_float_noise(sid: str, results: dict[str, PipelineResult]) -> None:
    report = results[sid].report
    assert "&quot;" not in render_markdown(report)
    noisy = [v for v in _floats(report.model_dump(mode="json")) if round(v, 4) != v]
    assert not noisy, noisy[:5]


def _floats(value: object) -> list[float]:
    if isinstance(value, float):
        return [value]
    if isinstance(value, dict):
        return [f for v in value.values() for f in _floats(v)]
    if isinstance(value, list):
        return [f for v in value for f in _floats(v)]
    return []
