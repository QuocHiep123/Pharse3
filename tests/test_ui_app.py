"""Test callback + build_app() của demo Gradio; không mở server."""

from __future__ import annotations

import pytest

gr = pytest.importorskip("gradio")
pytest.importorskip("plotly")
pytest.importorskip("yaml")

from callops.scenarios import SCENARIOS  # noqa: E402
from callops.ui import app  # noqa: E402
from callops.ui.contracts import RunResult  # noqa: E402
from callops.ui.loaders import scenario_to_yaml  # noqa: E402

_N = 3 + len(app.RENDER_KEYS)  # state, warning, slider + các output render


@pytest.fixture(scope="module")
def run_out():
    return app.on_run(scenario_to_yaml(SCENARIOS["congestion"]), 42, True)


def test_build_app_returns_blocks() -> None:
    assert isinstance(app.build_app(), gr.Blocks)


def test_on_run_ok(run_out) -> None:
    assert len(run_out) == _N
    assert isinstance(run_out[0], RunResult)
    assert run_out[1] == ""


def test_on_run_bad_yaml_warns_and_keeps_state() -> None:
    out = app.on_run("name: [", 42, True)
    assert len(out) == _N
    assert out[0] is None and "⚠️" in out[1]


def test_on_reanalyze_missing_files_warns() -> None:
    out = app.on_reanalyze(None, None, True)
    assert out[0] is None and "⚠️" in out[1]


def test_export_roundtrip(run_out) -> None:
    r = run_out[0]
    ev, qos, rep = app.on_export(r)
    out = app.on_reanalyze(ev, qos, True)
    assert out[1] == ""
    assert out[0].report.verdict == r.report.verdict
    assert rep.endswith("-report.json")


def test_reanalyze_csv_missing_columns(tmp_path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("ts,call_id\n1,2\n", encoding="utf-8")
    out = app.on_reanalyze(None, str(p), True)
    assert "Thiếu cột" in out[1]


def test_render_all_none() -> None:
    d = app.render_all(None, 0, True)
    assert set(d) == set(app.RENDER_KEYS)
    assert "Chưa có kết quả" in d["summary"]


def test_select_inference_highlights(run_out) -> None:
    r = run_out[0]
    inf_id = r.report.inferences[0].id
    md, html = app.on_select_inference(r, inf_id, True)
    assert 'class="hl"' in html and inf_id in md


def test_on_tick_stops_at_end(run_out) -> None:
    r = run_out[0]
    end = app._slider_end(r)
    t, timer = app.on_tick(r, end)
    assert t == end
    assert timer.active is False
    t2, timer2 = app.on_tick(r, 0)
    assert t2 == 1 and timer2.active is True


def test_qos_legend_matches_chart() -> None:
    txt = app.qos_legend_markdown()
    assert "đứt" in txt and "FACT" in txt


def test_scenario_file_error_is_warning(tmp_path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("a", encoding="utf-8")
    code, warn = app.on_load_scenario_file(str(p))
    assert "⚠️" in warn


def test_slider_end_is_multiple_of_step() -> None:
    """Điểm cuối thanh trượt phải là bội của SLIDER_STEP, nếu không không kéo tới cuối được."""
    from callops.scenarios import SCENARIOS
    from callops.ui import app
    from callops.ui.runner import run_scenario

    r = run_scenario(SCENARIOS["congestion"])
    end = app._slider_end(r)
    assert end >= r.duration_s
    assert end / app.SLIDER_STEP == round(end / app.SLIDER_STEP)
