"""Hàm hiển thị thuần (markdown/HTML) cho các tab của demo; KHÔNG import gradio."""

from __future__ import annotations

from html import escape
from typing import Any, Collection, Sequence

from callops.ui.contracts import STEP_TITLES_VI, FlowStep, RunResult
from callops.ui.explain import (
    MEDIA_PATH_EXPLAIN_VI,
    NO_MEDIA_PATH_EXPLAIN_VI,
    VERDICT_EXPLAIN_VI,
    find_terms,
    metric_explain_vi,
    rule_explain,
)
from callops.ui.flow import steps_until

__all__ = ["EVENT_COLUMNS", "summary_markdown", "facts_html", "inference_choices", "inference_markdown",
           "rules_markdown", "step_markdown", "current_step", "events_rows", "qos_explain_markdown"]

EVENT_COLUMNS: tuple[str, ...] = ("t (s)", "level", "event", "state", "error_code", "message")

_PICK_INFERENCE = "Chọn một INFERENCE ở danh sách để xem nó dựa trên FACT nào."
_PICK_STEP = "Kéo thanh thời gian hoặc bấm Play để xem từng bước."
_CHART_METRICS = ("rtt_ms", "jitter_ms", "packet_loss_pct", "mos", "concealment_pct")

_FACTS_STYLE = (
    "<style>.callops-facts{border-collapse:collapse;width:100%;font-size:13px}"
    ".callops-facts th,.callops-facts td{border-bottom:1px solid rgba(127,127,127,.3);"
    "padding:4px 8px;text-align:left;vertical-align:top}"
    ".callops-facts tr.hl{background:rgba(250,204,21,.28);outline:2px solid #eab308}</style>"
)


def _glossary_section(text: str) -> list[str]:
    terms = find_terms(text)
    if not terms:
        return []
    return ["", "**Thuật ngữ**", *(f"- **{t.name}**: {t.short_vi}" for t in terms)]


def summary_markdown(r: RunResult, beginner: bool) -> str:
    verdict = r.report.verdict
    mp = r.report.media_path
    media = mp.value if mp is not None else "không có media"
    source = "mô phỏng" if r.source == "simulated" else "upload"
    lines = [
        f"### {r.scenario_name}",
        f"- Nguồn: {source}",
        f"- call_id: `{r.call_id}`",
        f"- Verdict: **{verdict.value}**",
        f"- Media path: **{media}**",
        f"- Số liệu: {len(r.events)} event, {len(r.samples)} sample, "
        f"{len(r.report.facts)} FACT, {len(r.report.inferences)} INFERENCE",
    ]
    if r.scenario is not None:
        lines.append(f"- Mô tả: {r.scenario.description}")
        if r.scenario.expected:
            lines.append(f"- Kỳ vọng: {r.scenario.expected}")
    if beginner:
        lines += ["", f"> {VERDICT_EXPLAIN_VI[verdict]}",
                  f"> {MEDIA_PATH_EXPLAIN_VI[mp] if mp is not None else NO_MEDIA_PATH_EXPLAIN_VI}"]
    return "\n".join(lines)


def facts_html(r: RunResult, highlight: Collection[str] = ()) -> str:
    if not r.facts:
        return "<p>Không có FACT</p>"
    rows = []
    for f in r.facts:
        cls = ' class="hl"' if f.id in highlight else ""
        rows.append(
            f"<tr{cls}><td>{escape(f.id)}</td><td>{r.rel_t(f.ts):.1f}</td><td>{escape(f.source)}</td>"
            f"<td>{escape(f.statement)}<details><summary>evidence</summary>"
            f"<pre>{escape(f.evidence)}</pre></details></td>"
            f"<td>{escape(f.error_code or '')}</td></tr>"
        )
    head = "<tr><th>ID</th><th>t (s)</th><th>Nguồn</th><th>Statement</th><th>error_code</th></tr>"
    return f'{_FACTS_STYLE}<table class="callops-facts">{head}{"".join(rows)}</table>'


def inference_choices(r: RunResult) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i in r.report.inferences:
        hyp = i.hypothesis if len(i.hypothesis) <= 70 else i.hypothesis[:69] + "…"
        out.append((f"{i.id} · {hyp} (conf {i.confidence:.2f})", i.id))
    return out


def inference_markdown(r: RunResult, inf_id: str | None, beginner: bool) -> str:
    if inf_id is None:
        return _PICK_INFERENCE
    try:
        inf = r.inference(inf_id)
    except KeyError:
        return _PICK_INFERENCE
    rule = r.rule_of(inf_id)
    lines = [
        f"### INFERENCE {inf.id} — giả thuyết (không phải dữ kiện)",
        inf.hypothesis,
        "",
        f"- Confidence: **{inf.confidence:.2f}**",
        f"- Lập luận: {inf.reasoning}",
    ]
    if rule:
        lines.append(f"- Rule: `{rule}` — {rule_explain(rule).title_vi}")
    lines += ["", "**Dựa trên FACT**", *(f"- [{f.id}] {f.statement}" for f in r.cited_facts(inf_id))]
    if inf.recommendation:
        lines += ["", f"**Khuyến nghị**: {inf.recommendation}"]
    if beginner:
        lines += _glossary_section(f"{inf.hypothesis} {inf.reasoning} {inf.recommendation}")
    return "\n".join(lines)


def rules_markdown(r: RunResult) -> str:
    matched = [t for t in r.rule_traces if t.matched]
    unmatched = [t for t in r.rule_traces if not t.matched]
    lines = ["**Rule khớp**"]
    lines += [f"- ✔ {t.rule} — {rule_explain(t.rule).title_vi} → {', '.join(t.inference_ids)}" for t in matched] \
        or ["- (không có)"]
    lines += ["", "**Rule không khớp và lý do**"]
    lines += [f"- ✘ {t.rule} — Không khớp vì dữ liệu không thỏa: {rule_explain(t.rule).when_vi}"
              for t in unmatched] or ["- (không có)"]
    return "\n".join(lines)


def step_markdown(step: FlowStep | None, beginner: bool) -> str:
    if step is None:
        return _PICK_STEP
    lines = [
        f"### STEP {step.step_no} · {STEP_TITLES_VI.get(step.step_no, '')}",
        f"**#{step.seq} {step.title}** (t={step.t:.2f}s)",
        f"`{step.actor_from} → {step.actor_to}`",
        "",
        f"Log: {step.message}",
        f"`{step.log_ref}`",
    ]
    if beginner:
        lines += ["", step.explain_vi, *_glossary_section(f"{step.message} {step.explain_vi}")]
    return "\n".join(lines)


def current_step(steps: Sequence[FlowStep], t: float) -> FlowStep | None:
    n = steps_until(steps, t)
    return steps[n - 1] if n else None


def events_rows(r: RunResult) -> list[list[Any]]:
    return [[round(r.rel_t(e.ts), 2), e.level, e.event, e.state.value, e.error_code or "", e.message]
            for e in r.events]


def qos_explain_markdown(beginner: bool) -> str:
    if not beginner:
        return "Đường trên chart là giá trị từng giây; vùng đỏ/vàng là đoạn vượt ngưỡng."
    return "\n".join(f"- {metric_explain_vi(m)}" for m in _CHART_METRICS)
