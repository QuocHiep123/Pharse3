"""Test các hàm hiển thị thuần (callops.ui.views); không cần Gradio."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from callops.models import DiagnosisReport, Fact, Inference, Severity
from callops.scenarios import SCENARIOS
from callops.ui.contracts import STEP_TITLES_VI, RuleTrace, RunResult
from callops.ui.explain import NO_MEDIA_PATH_EXPLAIN_VI, RULE_EXPLAIN
from callops.ui.flow import build_timeline
from callops.ui.runner import run_scenario
from callops.ui.views import (
    EVENT_COLUMNS,
    current_step,
    events_rows,
    facts_html,
    inference_choices,
    inference_markdown,
    qos_explain_markdown,
    rules_markdown,
    step_markdown,
    summary_markdown,
)


@pytest.fixture(scope="module")
def congestion() -> RunResult:
    return run_scenario(SCENARIOS["congestion"])


@pytest.fixture(scope="module")
def p2p_good() -> RunResult:
    return run_scenario(SCENARIOS["p2p_good"])


@pytest.fixture(scope="module")
def ice_failed() -> RunResult:
    return run_scenario(SCENARIOS["ice_failed_no_turn"])


def _congestion_inf(r: RunResult) -> Inference:
    return next(i for i in r.report.inferences if "Nghẽn" in i.hypothesis)


def test_inference_markdown_cites_facts_and_rule(congestion: RunResult) -> None:
    inf = _congestion_inf(congestion)
    md = inference_markdown(congestion, inf.id, beginner=False)
    for fid in inf.derived_from:
        assert f"[{fid}]" in md
    assert "congestion_vs_random_loss" in md
    assert "giả thuyết" in md
    assert "Thuật ngữ" not in md
    assert "Thuật ngữ" in inference_markdown(congestion, inf.id, beginner=True)


def test_facts_html_highlight(congestion: RunResult) -> None:
    inf = _congestion_inf(congestion)
    first = inf.derived_from[0]
    html = facts_html(congestion, highlight={first})
    assert html.count('class="hl"') == 1
    row = next(x for x in html.split("<tr") if 'class="hl"' in x)
    assert first in row


def test_facts_html_empty() -> None:
    r = _minimal([], [])
    assert "Không có FACT" in facts_html(r)


def _minimal(facts: list[Fact], infs: list[Inference]) -> RunResult:
    report = DiagnosisReport(call_id="c1", scenario="x", verdict=Severity.OK, media_path=None,
                             facts=facts, inferences=infs)
    traces = (RuleTrace("healthy_call", tuple(i.id for i in infs)),)
    return RunResult(scenario_name="x", source="uploaded", call_id="c1", events=(), samples=(),
                     report=report, windows=(), rule_traces=traces)


def test_escape_html_and_markdown_free_of_raw_script() -> None:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fact = Fact(id="F01", ts=ts, source="log", statement="<script>x</script>", evidence="<b>e</b>")
    inf = Inference(id="I01", hypothesis="h", reasoning="r", derived_from=["F01"], confidence=0.5)
    r = _minimal([fact], [inf])
    html = facts_html(r)
    assert "&lt;script&gt;" in html
    assert "<script>x" not in html
    assert "<b>e" not in html


def test_rules_markdown_p2p_good(p2p_good: RunResult) -> None:
    md = rules_markdown(p2p_good)
    assert "✔ healthy_call" in md
    assert "✘ ice_failure_root_cause" in md
    assert RULE_EXPLAIN["ice_failure_root_cause"].when_vi in md


def test_inference_markdown_placeholder(congestion: RunResult) -> None:
    assert "Chọn một INFERENCE" in inference_markdown(congestion, None, True)
    assert "Chọn một INFERENCE" in inference_markdown(congestion, "I99", True)


def test_summary_ice_failed(ice_failed: RunResult) -> None:
    md = summary_markdown(ice_failed, True)
    assert "CRITICAL" in md
    assert NO_MEDIA_PATH_EXPLAIN_VI in md
    assert "không có media" in summary_markdown(ice_failed, False)


def test_summary_beginner_adds_explanations(p2p_good: RunResult) -> None:
    assert len(summary_markdown(p2p_good, True)) > len(summary_markdown(p2p_good, False))
    assert p2p_good.call_id in summary_markdown(p2p_good, False)


def test_events_rows(congestion: RunResult) -> None:
    rows = events_rows(congestion)
    assert len(rows) == len(congestion.events)
    assert all(len(row) == len(EVENT_COLUMNS) for row in rows)


def test_current_step_and_step_markdown(congestion: RunResult) -> None:
    steps = build_timeline(congestion.events, congestion.t0)
    assert current_step(steps, -1) is None
    assert current_step(steps, 1e9) is steps[-1]
    assert "Kéo thanh thời gian" in step_markdown(None, True)
    md = step_markdown(steps[0], True)
    assert STEP_TITLES_VI[steps[0].step_no] in md
    assert steps[0].log_ref in md
    assert steps[0].explain_vi in md
    assert steps[0].explain_vi not in step_markdown(steps[0], False)


def test_inference_choices(congestion: RunResult) -> None:
    ch = inference_choices(congestion)
    assert len(ch) == len(congestion.report.inferences)
    assert [v for _, v in ch] == [i.id for i in congestion.report.inferences]


def test_qos_explain() -> None:
    assert len(qos_explain_markdown(True)) > len(qos_explain_markdown(False))
