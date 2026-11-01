"""LLM summary (plan 10): every path uses FakeLLM or a stubbed SDK; no network calls."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from calldiag.llm import summary as llm_summary
from calldiag.llm.client import FakeLLM, OpenAIClient, resolve_client
from calldiag.llm.summary import SYSTEM_PROMPT, add_llm_summary, build_llm_input
from calldiag.models import FactKind, IncidentReport, PipelineResult
from calldiag.pipeline.run import run_scenario
from calldiag.pipeline.validator import apply_validation, validate_report

ENV = ("CALLDIAG_LLM_PROVIDER", "CALLDIAG_LLM_MODEL", "OPENAI_API_KEY")


def _fact(report: IncidentReport, kind: FactKind, metric: str | None = None) -> str:
    return next(f.fact_id for f in report.facts if f.kind == kind and (metric is None or f.data.get("metric") == metric))


def _good_s1(report: IncidentReport) -> tuple[str, str]:
    path, cpu = _fact(report, FactKind.SELECTED_PATH), _fact(report, FactKind.METRIC_CHANGE, "turn_cpu_pct")
    loss, rtt = _fact(report, FactKind.METRIC_CHANGE, "packet_loss_pct"), _fact(report, FactKind.METRIC_CHANGE, "rtt_ms")
    engineering = (
        f"Cuộc gọi hoàn tất thiết lập và đi qua TURN relay turn-01 [{path}]. "
        f"TURN CPU tăng từ 42% lên 95% [{cpu}], cùng lúc packet loss lên 11.8% [{loss}] và RTT từ 80 ms lên 311 ms [{rtt}]. "
        "Nhận định (confidence High): suy giảm trong 10:21:19–10:21:44 có khả năng liên quan tới quá tải TURN server turn-01 [I1]. "
        "Chưa rõ lý do TURN CPU tăng [I1]."
    )
    executive = ("Cuộc gọi kết nối được nhưng chất lượng giảm trong khoảng 10:21:19–10:21:44, trùng lúc máy chủ trung chuyển "
                 "chịu tải cao. Chưa rõ vì sao tải máy chủ tăng.")
    return engineering, executive


def _reply(engineering: str, executive: str) -> str:
    return json.dumps({"engineering_summary": engineering, "executive_summary": executive}, ensure_ascii=False)


def _finish(report: IncidentReport, result: PipelineResult) -> IncidentReport:
    return apply_validation(report, validate_report(report, result.bundle))


@pytest.fixture
def s1(results: dict[str, PipelineResult]) -> PipelineResult:
    return results["S1"]


def test_valid_llm_summary_is_kept(s1: PipelineResult) -> None:
    engineering, executive = _good_s1(s1.report)
    fake = FakeLLM(_reply(engineering, executive))
    report = _finish(add_llm_summary(s1.report, fake, cache_dir=None), s1)
    assert report.summary_source == "llm"
    assert report.engineering_summary == engineering and report.executive_summary == executive
    assert report.validation.passed and not report.validation.issues
    assert len(fake.calls) == 1 and fake.calls[0][0] == SYSTEM_PROMPT


@pytest.mark.parametrize(("change", "code"), [
    (lambda e, x: (e + " Thêm [F99].", x), "W_SUMMARY_UNKNOWN_CITE"),
    (lambda e, x: (e.replace("311 ms", "999 ms"), x), "W_SUMMARY_NEW_NUMBER"),
    (lambda e, x: (e, x + " Kéo dài khoảng 25 giây."), "W_SUMMARY_NEW_NUMBER"),
    (lambda e, x: ("Chất lượng giảm do TURN quá tải.", x), "W_SUMMARY_NO_CITE"),
    (lambda e, x: (e, x + " [I1]"), "W_SUMMARY_EXEC_CITE"),
    (lambda e, x: (e + " Chưa rõ vị trí nghẽn [unknowns].", x), "W_SUMMARY_BAD_CITE"),
    (lambda e, x: (e, x + " chi tiết" * 80), "W_SUMMARY_TOO_LONG"),
])
def test_guardrail_violation_falls_back_to_template(s1: PipelineResult, change, code: str) -> None:
    engineering, executive = change(*_good_s1(s1.report))
    report = _finish(add_llm_summary(s1.report, FakeLLM(_reply(engineering, executive)), cache_dir=None), s1)
    assert report.summary_source == "template"
    assert report.engineering_summary == s1.report.engineering_summary
    assert report.executive_summary == s1.report.executive_summary
    assert code in {issue.code for issue in report.validation.issues}
    assert report.validation.passed           # summary problems are warnings, not report errors


@pytest.mark.parametrize("fake", [
    FakeLLM("đây không phải JSON"),
    FakeLLM(json.dumps({"engineering_summary": "chỉ có một trường [I1]"})),
    FakeLLM(json.dumps(["không", "phải", "object"])),
    FakeLLM(error=TimeoutError("quá 30 s")),
])
def test_llm_failure_keeps_template_with_warning(s1: PipelineResult, fake: FakeLLM) -> None:
    report = _finish(add_llm_summary(s1.report, fake, cache_dir=None), s1)
    assert report.summary_source == "template" and report.validation.passed
    failed = [i for i in report.validation.issues if i.code == "W_LLM_FAILED"]
    assert len(failed) == 1


def test_code_fence_is_stripped(s1: PipelineResult) -> None:
    fenced = "```json\n" + _reply(*_good_s1(s1.report)) + "\n```"
    report = _finish(add_llm_summary(s1.report, FakeLLM(fenced), cache_dir=None), s1)
    assert report.summary_source == "llm"


@pytest.mark.parametrize("sid", ["S1", "S2", "S6"])
def test_llm_input_hides_scenario_label(sid: str, results: dict[str, PipelineResult]) -> None:
    from calldiag.scenarios import REGISTRY

    fake = FakeLLM("{}")
    add_llm_summary(results[sid].report, fake, cache_dir=None)
    sent = fake.calls[0][1]
    payload = json.loads(sent)
    assert set(payload) == {"headline", "severity", "confidence", "incident_window", "path", "phases",
                            "facts", "inferences", "hypotheses", "rejected", "unknowns"}
    for label in (sid, REGISTRY[sid].title, results[sid].report.scope.call_id, "scenario"):
        assert label not in sent
    assert payload == build_llm_input(results[sid].report)


def test_rejected_and_hypotheses_are_shown_to_llm(results: dict[str, PipelineResult]) -> None:
    assert build_llm_input(results["S2"].report)["rejected"][0]["id"] == "R1"
    assert build_llm_input(results["S6"].report)["hypotheses"][0]["missing_evidence"]


def test_cache_reuses_response_and_depends_on_model(s1: PipelineResult, tmp_path: Path) -> None:
    reply = _reply(*_good_s1(s1.report))
    first = add_llm_summary(s1.report, FakeLLM(reply), cache_dir=tmp_path)
    assert first.summary_source == "llm" and len(list(tmp_path.glob("*.json"))) == 1
    offline = FakeLLM(error=ConnectionError("không có mạng"))
    second = add_llm_summary(s1.report, offline, cache_dir=tmp_path)
    assert second.engineering_summary == first.engineering_summary and not offline.calls
    other = FakeLLM(reply, model="another-model")
    add_llm_summary(s1.report, other, cache_dir=tmp_path)
    assert len(other.calls) == 1 and len(list(tmp_path.glob("*.json"))) == 2


def test_failed_response_is_not_cached(s1: PipelineResult, tmp_path: Path) -> None:
    add_llm_summary(s1.report, FakeLLM("không phải JSON"), cache_dir=tmp_path)
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize(("env", "reason"), [
    ({}, "CALLDIAG_LLM_MODEL"),
    ({"CALLDIAG_LLM_MODEL": "m"}, "OPENAI_API_KEY"),
    ({"CALLDIAG_LLM_PROVIDER": "anthropic", "CALLDIAG_LLM_MODEL": "m", "OPENAI_API_KEY": "k"}, "chưa được hỗ trợ"),
])
def test_resolve_client_explains_why_unavailable(monkeypatch: pytest.MonkeyPatch, env: dict, reason: str) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    client, why = resolve_client()
    assert client is None and reason in why


def test_resolve_client_builds_openai_client_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLDIAG_LLM_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.delenv("CALLDIAG_LLM_PROVIDER", raising=False)
    client, why = resolve_client()
    assert why is None and isinstance(client, OpenAIClient) and client.model == "test-model"


class _StubCompletions:
    def __init__(self, message: SimpleNamespace, finish_reason: str = "stop") -> None:
        self.kwargs: dict = {}
        self._choice = SimpleNamespace(message=message, finish_reason=finish_reason)

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(choices=[self._choice])


def _stub_sdk(completions: _StubCompletions) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_openai_client_request_shape() -> None:
    completions = _StubCompletions(SimpleNamespace(content='{"a": 1}', refusal=None))
    text = OpenAIClient("test-model", sdk_client=_stub_sdk(completions)).complete("SYS", "USER")
    assert text == '{"a": 1}'
    assert completions.kwargs["model"] == "test-model"
    assert completions.kwargs["response_format"] == {"type": "json_object"}
    assert completions.kwargs["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert "temperature" not in completions.kwargs


@pytest.mark.parametrize(("message", "finish", "error"), [
    (SimpleNamespace(content=None, refusal="không thể hỗ trợ"), "stop", "refused"),
    (SimpleNamespace(content='{"engineering_summary": "cắt', refusal=None), "length", "token limit"),
])
def test_openai_client_rejects_refusal_and_truncation(message: SimpleNamespace, finish: str, error: str) -> None:
    client = OpenAIClient("m", sdk_client=_stub_sdk(_StubCompletions(message, finish)))
    with pytest.raises(RuntimeError, match=error):
        client.complete("SYS", "USER")


def test_pipeline_with_llm_end_to_end(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # default cache dir is relative: keep it out of the repo
    template = run_scenario("S1").report
    reply = _reply(*_good_s1(template))
    monkeypatch.setattr(llm_summary, "resolve_client", lambda: (FakeLLM(reply), None))
    report = run_scenario("S1", use_llm=True).report
    assert report.summary_source == "llm" and report.validation.passed and not report.validation.issues
    assert report.inferences == template.inferences and report.facts == template.facts   # LLM touches summaries only
    assert list((tmp_path / "out" / "llm_cache").glob("*.json"))
