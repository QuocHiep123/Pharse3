"""Smoke tests for the Streamlit UI (plan 09): pure charts and a headless app run per scenario."""

from pathlib import Path

import plotly.graph_objects as go
import pytest
from streamlit.testing.v1 import AppTest

from app.charts import metric_panels, phase_waterfall
from calldiag.io import metrics_to_frame
from calldiag.models import PipelineResult
from calldiag.scenarios import REGISTRY

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


@pytest.mark.parametrize("sid", REGISTRY)
@pytest.mark.parametrize("traced", [False, True])
def test_charts_build_for_every_scenario(sid: str, traced: bool, results: dict[str, PipelineResult]) -> None:
    result = results[sid]
    facts = result.report.facts
    highlight = {"fact_ids": [f.fact_id for f in facts], "refs": [r for f in facts for r in f.refs]} if traced else {}
    refs = set(highlight.get("refs", ()))
    for zoom in (False, True):
        assert isinstance(phase_waterfall(result.phases, result.bundle.events, refs, zoom), go.Figure)
    assert isinstance(metric_panels(metrics_to_frame(result.bundle), result.anomalies, facts, highlight), go.Figure)


def test_waterfall_marks_traced_events_and_skipped_phases(results: dict[str, PipelineResult]) -> None:
    result = results["S3"]
    fig = phase_waterfall(result.phases, result.bundle.events, {"ev-021"})
    assert any(a.text == "⏭ skipped" for a in fig.layout.annotations)
    traced = [t for t in fig.data if t.name == "event (đang truy vết)"]
    assert len(traced) == 1 and len(traced[0].x) == 1


def test_missing_turn_cpu_is_annotated_not_drawn(results: dict[str, PipelineResult]) -> None:
    result = results["S6"]
    fig = metric_panels(metrics_to_frame(result.bundle), result.anomalies, result.report.facts)
    assert any("TURN CPU (turn-01): không có dữ liệu" in (a.text or "") for a in fig.layout.annotations)
    assert not any(t.name == "TURN CPU (turn-01)" for t in fig.data)


@pytest.mark.parametrize("sid", REGISTRY)
def test_app_renders_each_scenario(sid: str, results: dict[str, PipelineResult]) -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.selectbox(key="scenario").set_value(sid).run()
    assert not at.exception, at.exception
    assert at.subheader[0].value == results[sid].report.summary.headline
    assert len(at.tabs) == 7


def test_trace_button_highlights_inference_facts() -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.selectbox(key="scenario").set_value("S1").run()
    at.button(key="trace_I1").click().run()
    assert not at.exception, at.exception
    highlight = at.session_state.highlight
    assert highlight["label"] == "I1" and "F6" in highlight["fact_ids"]
    assert any(ref.startswith("m-") for ref in highlight["refs"])
    assert any("Đang truy vết" in info.value for info in at.info)
    at.button[0].click().run()  # "Bỏ truy vết" is the first button on the page
    assert at.session_state.highlight is None


def test_switching_scenario_clears_trace() -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.selectbox(key="scenario").set_value("S2").run()
    at.button(key="trace_R1").click().run()
    assert at.session_state.highlight["label"] == "R1"
    at.sidebar.selectbox(key="scenario").set_value("S6").run()
    assert at.session_state.highlight is None
    assert not at.exception


def test_query_params_open_scenario_with_trace() -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["scenario"] = "S2"
    at.query_params["trace"] = "R1"
    at.run()
    assert not at.exception, at.exception
    assert at.sidebar.selectbox(key="scenario").value == "S2"
    assert at.session_state.highlight["label"] == "R1"


def test_traced_windows_are_merged_into_one_outline(results: dict[str, PipelineResult]) -> None:
    result = results["S1"]
    inference = result.report.inferences[0]
    fig = metric_panels(metrics_to_frame(result.bundle), result.anomalies, result.report.facts,
                        {"fact_ids": inference.supported_by, "refs": []})
    outlines = [s for s in fig.layout.shapes if s.type == "rect" and s.line.color == "#7b1fa2"]
    # S1 metric windows all overlap the incident: 1 merged span drawn on each of the 5 panels.
    assert len(outlines) == 5


def test_trace_query_param_mirrors_highlight() -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["scenario"] = "S1"
    at.query_params["trace"] = "I1"
    at.run()
    assert dict(at.query_params) == {"scenario": "S1", "trace": "I1"}
    at.button[0].click().run()                                  # "Bỏ truy vết"
    assert at.session_state.highlight is None and "trace" not in at.query_params
    at.button(key="trace_I1").click().run()                     # tracing writes the link
    assert at.query_params["trace"] == "I1"
    at.sidebar.selectbox(key="scenario").set_value("S4").run()  # switching drops the stale ID
    assert dict(at.query_params) == {"scenario": "S4"} and at.session_state.highlight is None


def test_reopening_link_after_switch_does_not_trace_other_scenario() -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["scenario"] = "S1"
    at.query_params["trace"] = "I1"
    at.run()
    at.sidebar.selectbox(key="scenario").set_value("S4").run()
    reopened = AppTest.from_file(APP, default_timeout=60)
    for key, value in at.query_params.items():
        reopened.query_params[key] = value
    reopened.run()
    assert reopened.session_state.highlight is None


def test_unknown_trace_id_is_dropped_from_url() -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["scenario"] = "S0"
    at.query_params["trace"] = "R9"
    at.run()
    assert not at.exception and at.session_state.highlight is None
    assert "trace" not in at.query_params


def test_fact_trace_link_traces_single_fact() -> None:
    # AppTest cannot fire st.dataframe's on_select; a FACT ID in the link takes the same set_highlight path.
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["scenario"] = "S1"
    at.query_params["trace"] = "F12"
    at.run()
    assert at.session_state.highlight["fact_ids"] == ["F12"]
    assert at.query_params["trace"] == "F12"


def test_llm_checkbox_disabled_without_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CALLDIAG_LLM_PROVIDER", "CALLDIAG_LLM_MODEL", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert at.sidebar.checkbox(key="use_llm").disabled
    assert any("CALLDIAG_LLM_MODEL" in caption.value for caption in at.sidebar.caption)


def test_llm_checkbox_enabled_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLDIAG_LLM_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.sidebar.checkbox(key="use_llm").disabled
    assert any("test-model" in caption.value for caption in at.sidebar.caption)


def test_split_summary_into_sentences_and_badges() -> None:
    from app.summary_view import badges, split_summary

    text = ("Selected pair relay↔srflx, chọn lúc 10:20:03.650 [F6]. Loss tăng 0.4% lên 11.8% [F8, F9]. "
            "Giả thuyết TURN bị loại [F8, R1]. Chưa xác định: vị trí nghẽn.")
    assert split_summary(text) == [
        ("Selected pair relay↔srflx, chọn lúc 10:20:03.650.", ["F6"]),
        ("Loss tăng 0.4% lên 11.8%.", ["F8", "F9"]),
        ("Giả thuyết TURN bị loại.", ["F8", "R1"]),
        ("Chưa xác định: vị trí nghẽn.", []),
    ]
    assert badges(["F8", "I1", "H1", "R1"]) == ":blue-badge[F8] :violet-badge[I1] :orange-badge[H1] :red-badge[R1]"


@pytest.mark.parametrize("sid", REGISTRY)
def test_template_summaries_lose_no_citation(sid: str, results: dict[str, PipelineResult]) -> None:
    import re
    from app.summary_view import split_summary

    summary = results[sid].report.engineering_summary
    shown = [i for _, ids in split_summary(summary) for i in ids]
    assert set(shown) == set(re.findall(r"[FIHR]\d+", summary))
    assert all("[" not in text for text, _ in split_summary(summary))
