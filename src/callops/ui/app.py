"""Demo Gradio: call flow + QoS timeline + chẩn đoán FACT/INFERENCE. Chạy bằng InMemoryStore, không LLM.

Callback là hàm module-level thuần Python (test gọi trực tiếp). UI chỉ hiển thị; không tạo FACT/INFERENCE.
Nội dung từ file upload là dữ liệu không tin cậy: giữ sanitize_html mặc định của gr.Markdown/gr.HTML,
còn views.py tự html.escape mọi text từ dữ liệu.
"""

from __future__ import annotations

import math
import tempfile
from html import escape
from pathlib import Path
from typing import Any

import gradio as gr

from callops.qos import THRESHOLDS
from callops.scenarios import SCENARIOS
from callops.ui.charts import qos_figure
from callops.ui.contracts import RunResult, UiInputError
from callops.ui.flow import build_timeline, render_flow_svg, steps_until
from callops.ui.loaders import (
    dump_events_jsonl,
    dump_qos_csv,
    load_jsonl,
    load_qos_csv,
    load_scenario,
    parse_scenario_text,
    scenario_to_yaml,
)
from callops.ui.runner import DEFAULT_SEED, reanalyze, run_scenario
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

DEFAULT_SCENARIO = "congestion"
SLIDER_STEP = 0.5
EMPTY_MSG = "Chưa có kết quả — chọn kịch bản và bấm Chạy"

# thứ tự cố định của các output hiển thị (khớp danh sách component trong build_app)
RENDER_KEYS: tuple[str, ...] = (
    "summary", "flow", "step", "plot", "qos", "facts", "inf_pick", "inf_md", "rules", "events", "logs",
)

_CSS = """
.gradio-container{max-width:1180px !important;margin:0 auto}
#callops-head h1{margin:0 0 2px;font-size:1.55rem;letter-spacing:-.01em}
#callops-head p{margin:0;opacity:.75}
#callops-warn{min-height:0}
#callops-warn p{margin:0}
.callops-flow-wrap{border:1px solid rgba(127,127,127,.25);border-radius:8px;padding:6px}
"""


def _theme() -> gr.themes.ThemeClass:
    return gr.themes.Base(primary_hue="teal", neutral_hue="slate", radius_size="sm")


# ------------------------------------------------------------------ thông báo lỗi
def _warn(msg: str) -> str:
    """Toast (đã escape) + chuỗi markdown cảnh báo cho khung trong UI."""
    try:
        gr.Warning(escape(msg))
    except Exception:  # noqa: BLE001 - ngoài ngữ cảnh request thì chỉ bỏ qua toast
        pass
    return f"⚠️ {msg}"


def qos_legend_markdown() -> str:
    """Chú thích chart, khớp charts.qos_figure: vạch ngưỡng, vùng sự cố, cursor."""
    return (
        "Mỗi đường là một participant. Vạch ngang nét đứt là ngưỡng `warn` (vàng nâu) và `crit` (đỏ) lấy từ "
        "`THRESHOLDS`. Vùng tô màu là đoạn vượt ngưỡng (cam = WARNING, đỏ = CRITICAL), nhãn `[Fxx]` là FACT "
        "tương ứng. Vạch dọc xám đậm là thời điểm đang xem."
    )


# ------------------------------------------------------------------ render
def render_all(r: RunResult | None, t: float, beginner: bool) -> dict[str, Any]:
    """Nội dung mọi output (khóa = RENDER_KEYS)."""
    if r is None:
        return {
            "summary": EMPTY_MSG,
            "flow": render_flow_svg([]),
            "step": step_markdown(None, beginner),
            "plot": qos_figure([]),
            "qos": qos_explain_markdown(beginner),
            "facts": "<p>Không có FACT</p>",
            "inf_pick": gr.update(choices=[], value=None),
            "inf_md": inference_markdown_empty(),
            "rules": "",
            "events": [],
            "logs": "",
        }
    steps = build_timeline(r.events, r.t0)
    return {
        "summary": summary_markdown(r, beginner),
        "flow": render_flow_svg(steps, steps_until(steps, t)),
        "step": step_markdown(current_step(steps, t), beginner),
        "plot": qos_figure(r.samples, THRESHOLDS, r.windows, t0=r.t0, cursor_t=t),
        "qos": _qos_text(beginner),
        "facts": facts_html(r),
        "inf_pick": gr.update(choices=inference_choices(r), value=None),
        "inf_md": inference_markdown(r, None, beginner),
        "rules": rules_markdown(r),
        "events": events_rows(r),
        "logs": "\n".join(r.log_lines),
    }


def inference_markdown_empty() -> str:
    return "Chọn một INFERENCE ở danh sách để xem nó dựa trên FACT nào."


def _qos_text(beginner: bool) -> str:
    return f"{qos_explain_markdown(beginner)}\n\n{qos_legend_markdown()}"


def _pack(d: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(d[k] for k in RENDER_KEYS)


def _result_outputs(r: RunResult, beginner: bool) -> tuple[Any, ...]:
    """(state, warning, slider, *render) cho kết quả mới."""
    slider = gr.update(minimum=0, maximum=_slider_end(r), value=0, visible=True)
    return (r, "", slider, *_pack(render_all(r, 0.0, beginner)))


def _error_outputs(current: RunResult | None, exc: UiInputError) -> tuple[Any, ...]:
    """Giữ nguyên mọi output cũ, chỉ hiện cảnh báo."""
    return (current, _warn(str(exc)), *([gr.skip()] * (1 + len(RENDER_KEYS))))


# ------------------------------------------------------------------ callback
def on_pick_scenario(name: str) -> str:
    return scenario_to_yaml(SCENARIOS[name])


def on_run(scenario_text: str, seed: float, beginner: bool, current: RunResult | None = None) -> tuple[Any, ...]:
    try:
        scenario = parse_scenario_text(scenario_text, source="editor")
        r = run_scenario(scenario, int(seed))
    except UiInputError as exc:
        return _error_outputs(current, exc)
    return _result_outputs(r, beginner)


def on_reanalyze(
    events_path: str | None, qos_path: str | None, beginner: bool, current: RunResult | None = None
) -> tuple[Any, ...]:
    try:
        if not events_path and not qos_path:
            raise UiInputError("Chưa chọn file nào: tải lên file events (.jsonl) và/hoặc QoS (.csv)")
        events = load_jsonl(events_path) if events_path else []
        samples = load_qos_csv(qos_path) if qos_path else []
        name = Path(events_path or qos_path or "uploaded").stem
        r = reanalyze(events, samples, scenario_name=name)
    except UiInputError as exc:
        return _error_outputs(current, exc)
    return _result_outputs(r, beginner)


def on_load_scenario_file(path: str | None) -> tuple[Any, str]:
    """(nội dung editor, cảnh báo)."""
    if not path:
        return gr.skip(), _warn("Chưa chọn file scenario (.yaml/.yml/.json)")
    try:
        return scenario_to_yaml(load_scenario(path)), ""
    except UiInputError as exc:
        return gr.skip(), _warn(str(exc))


def on_export(r: RunResult | None) -> tuple[str, str, str]:
    if r is None:
        raise UiInputError("Chưa có kết quả để xuất")
    out = Path(tempfile.mkdtemp(prefix="callops-"))
    ev = dump_events_jsonl(r.events, out / f"{r.call_id}-events.jsonl")
    qos = dump_qos_csv(r.samples, out / f"{r.call_id}-qos.csv")
    rep = out / f"{r.call_id}-report.json"
    rep.write_text(r.report.model_dump_json(indent=2), encoding="utf-8")
    return str(ev), str(qos), str(rep)


def _export_ui(r: RunResult | None) -> tuple[Any, Any, Any, str]:
    try:
        return (*on_export(r), "")
    except UiInputError as exc:
        return (gr.skip(), gr.skip(), gr.skip(), _warn(str(exc)))


def on_select_inference(r: RunResult | None, inf_id: str | None, beginner: bool) -> tuple[str, str]:
    if r is None:
        return inference_markdown_empty(), "<p>Không có FACT</p>"
    try:
        cited = set(r.inference(inf_id).derived_from) if inf_id else set()
    except KeyError:
        cited = set()
    return inference_markdown(r, inf_id, beginner), facts_html(r, highlight=cited)


def on_time_change(r: RunResult | None, t: float, beginner: bool) -> tuple[Any, Any, Any]:
    d = render_all(r, float(t or 0), beginner)
    return d["flow"], d["step"], d["plot"]


def on_beginner_change(r: RunResult | None, t: float, beginner: bool, inf_id: str | None) -> tuple[str, str, str, str]:
    d = render_all(r, float(t or 0), beginner)
    return d["summary"], d["step"], d["qos"], inference_markdown(r, inf_id, beginner) if r else d["inf_md"]


def _slider_end(r: RunResult) -> float:
    """Điểm cuối thanh trượt: làm tròn lên bội của SLIDER_STEP để kéo tới được cuối."""
    return max(math.ceil(r.duration_s / SLIDER_STEP) * SLIDER_STEP, 1.0)


def on_tick(r: RunResult | None, t: float) -> tuple[float, Any]:
    """Mỗi tick +1s; dừng timer khi tới cuối."""
    end = _slider_end(r) if r else 0.0
    nt = min(float(t or 0) + 1.0, end)
    return nt, gr.Timer(active=nt < end)


def on_play(r: RunResult | None, t: float) -> tuple[float, Any]:
    end = _slider_end(r) if r else 0.0
    start = 0.0 if float(t or 0) >= end else float(t or 0)
    return start, gr.Timer(active=end > 0)


def on_pause() -> Any:
    return gr.Timer(active=False)


# ------------------------------------------------------------------ giao diện
def build_app() -> gr.Blocks:
    with gr.Blocks(title="callops · WebRTC AIOps demo") as demo:
        state = gr.State(None)
        gr.HTML(
            '<div id="callops-head"><h1>callops: vì sao cuộc gọi WebRTC lỗi?</h1>'
            "<p>Xem từng bước call flow, QoS theo thời gian và mỗi giả thuyết (INFERENCE) dựa trên FACT nào.</p></div>"
        )
        # thanh thời gian đặt trên Tabs: điều khiển cả flow SVG lẫn cursor trên chart
        with gr.Row(equal_height=True):
            beginner = gr.Checkbox(value=True, label="Giải thích cho người mới", scale=2)
            play = gr.Button("Play", variant="primary", scale=1, min_width=80)
            pause = gr.Button("Pause", scale=1, min_width=80)
            slider = gr.Slider(0, 60, value=0, step=SLIDER_STEP, label="Thời gian (giây)", scale=8, visible=False)
        timer = gr.Timer(1.0, active=False)
        warn = gr.Markdown("", elem_id="callops-warn")

        with gr.Tabs():
            with gr.Tab("Run / Playground"):
                with gr.Row():
                    with gr.Column(scale=2):
                        pick = gr.Dropdown(sorted(SCENARIOS), value=DEFAULT_SCENARIO, label="Kịch bản")
                        seed = gr.Number(DEFAULT_SEED, precision=0, label="Seed")
                        run_btn = gr.Button("Chạy mô phỏng", variant="primary")
                        editor = gr.Code(on_pick_scenario(DEFAULT_SCENARIO), language="yaml", label="Scenario (sửa được)")
                    with gr.Column(scale=3):
                        summary = gr.Markdown(EMPTY_MSG)
            with gr.Tab("Call Flow"):
                flow = gr.HTML(render_flow_svg([]))
                step = gr.Markdown()
            with gr.Tab("QoS Timeline"):
                plot = gr.Plot()
                qos_md = gr.Markdown()
            with gr.Tab("Diagnosis"):
                with gr.Row():
                    with gr.Column(scale=3):
                        gr.Markdown("#### FACT (dữ kiện)")
                        facts = gr.HTML()
                    with gr.Column(scale=2):
                        gr.Markdown("#### INFERENCE (giả thuyết)")
                        inf_pick = gr.Radio([], label="Chọn INFERENCE")
                        inf_md = gr.Markdown()
                        with gr.Accordion("Rule khớp / không khớp và lý do", open=False):
                            rules = gr.Markdown()
            with gr.Tab("Logs / Export"):
                events = gr.Dataframe(headers=list(EVENT_COLUMNS), interactive=False, wrap=True, label="Events")
                logs = gr.Code(label="Log console", interactive=False, lines=12)
                export_btn = gr.Button("Xuất events / QoS / report")
                with gr.Row():
                    f_ev = gr.File(label="events.jsonl")
                    f_qos = gr.File(label="qos.csv")
                    f_rep = gr.File(label="report.json")
            with gr.Tab("Upload / Re-analyze"):
                gr.Markdown("Tải lên file đã xuất từ tab Logs / Export (events `.jsonl`, QoS `.csv`) để chẩn đoán lại.")
                up_ev = gr.File(label="Events (.jsonl)", file_types=[".jsonl"], type="filepath")
                up_qos = gr.File(label="QoS (.csv)", file_types=[".csv"], type="filepath")
                re_btn = gr.Button("Phân tích lại", variant="primary")
                up_sc = gr.File(label="Scenario (.yaml/.yml/.json) → nạp vào editor tab Run",
                                file_types=[".yaml", ".yml", ".json"], type="filepath")

        render_outs = [summary, flow, step, plot, qos_md, facts, inf_pick, inf_md, rules, events, logs]
        run_outs = [state, warn, slider, *render_outs]

        run_btn.click(on_run, [editor, seed, beginner, state], run_outs)
        demo.load(on_run, [editor, seed, beginner, state], run_outs)
        re_btn.click(on_reanalyze, [up_ev, up_qos, beginner, state], run_outs)
        pick.change(on_pick_scenario, pick, editor)
        up_sc.upload(on_load_scenario_file, up_sc, [editor, warn])
        export_btn.click(_export_ui, state, [f_ev, f_qos, f_rep, warn])

        slider.change(on_time_change, [state, slider, beginner], [flow, step, plot])
        beginner.change(on_beginner_change, [state, slider, beginner, inf_pick], [summary, step, qos_md, inf_md])
        inf_pick.change(on_select_inference, [state, inf_pick, beginner], [inf_md, facts])

        play.click(on_play, [state, slider], [slider, timer])
        pause.click(on_pause, None, timer)
        timer.tick(on_tick, [state, slider], [slider, timer])
    return demo


def launch(host: str = "127.0.0.1", port: int = 7860, share: bool = False) -> None:
    # Gradio 6: theme/css truyền ở launch(), không ở gr.Blocks(...)
    build_app().launch(server_name=host, server_port=port, share=share, theme=_theme(), css=_CSS)
