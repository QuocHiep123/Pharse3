"""CallDiag one-page UI (plan 09): lifecycle trace, metrics, logs and a traceable incident report."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Both `streamlit run` and AppTest execute this file as a script; make charts.py importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from charts import metric_panels, phase_waterfall  # noqa: E402
from summary_view import badges, escape_markdown, split_summary  # noqa: E402

from calldiag import config  # noqa: E402
from calldiag.io import metrics_to_frame  # noqa: E402
from calldiag.models import CondState, IncidentReport, PipelineResult  # noqa: E402
from calldiag.pipeline.render import render_markdown  # noqa: E402
from calldiag.envfile import load_env_file  # noqa: E402
from calldiag.llm.client import resolve_client  # noqa: E402
from calldiag.pipeline.run import run_scenario  # noqa: E402
from calldiag.scenarios import REGISTRY  # noqa: E402
from calldiag.utils import fmt_time, fmt_window  # noqa: E402

TRACE_LABELS = {
    "time_to_accept_ms": "Chờ accept (CALL_CREATED → CALL_ACCEPTED)",
    "time_to_answer_ms": "Time-to-answer (OFFER_SENT → ANSWER_RECEIVED)",
    "ice_gathering_ms": "ICE gathering",
    "ice_checking_ms": "ICE checking",
    "dtls_ms": "DTLS handshake",
    "time_to_first_media_ms": "Time-to-first-media (CALL_CREATED → FIRST_RTP_RECEIVED)",
    "call_duration_ms": "Thời lượng cuộc gọi",
}
SEVERITY_COLORS = {"critical": "red", "major": "orange", "minor": "orange", "none": "green"}
CONFIDENCE_COLORS = {"High": "green", "Medium": "orange", "Low": "red"}
STATE_ICONS = {CondState.TRUE: "✅ true", CondState.FALSE: "❌ false", CondState.UNKNOWN: "❓ unknown"}
ROW_HIGHLIGHT = "background-color: rgba(123, 31, 162, 0.28)"
ROW_RELATED = "background-color: rgba(249, 168, 37, 0.16)"

st.set_page_config(page_title="CallDiag MVP", layout="wide")
load_env_file()


@st.cache_data(show_spinner="Đang chạy pipeline…")
def load(sid: str, use_llm: bool) -> PipelineResult:
    return run_scenario(sid, use_llm=use_llm)


# The URL's `trace` mirrors the highlight, so a copied link reopens exactly this screen.
def set_highlight(label: str, fact_ids: list[str], report: IncidentReport) -> None:
    facts = {fact.fact_id: fact for fact in report.facts}
    ids = [fid for fid in dict.fromkeys(fact_ids) if fid in facts]
    st.session_state.highlight = {
        "label": label, "fact_ids": ids,
        "refs": sorted({ref for fid in ids for ref in facts[fid].refs}),
    }
    st.query_params["trace"] = label


def drop_highlight() -> None:
    st.session_state.highlight = None
    if "trace" in st.query_params:
        del st.query_params["trace"]


def clear_highlight() -> None:
    drop_highlight()
    st.session_state.facts_key += 1      # a fresh key also clears the table's row selection


def on_fact_select(key: str, fact_ids: list[str], report: IncidentReport) -> None:
    rows = st.session_state[key].selection.rows
    if rows:
        set_highlight(fact_ids[rows[0]], [fact_ids[rows[0]]], report)
    else:
        drop_highlight()


def trace_targets(report: IncidentReport) -> dict[str, list[str]]:
    """Every traceable ID (FACT, INFERENCE, HYPOTHESIS, REJECTED) → the FACT IDs it rests on."""
    targets = {fact.fact_id: [fact.fact_id] for fact in report.facts}
    for item in report.inferences:
        targets[item.inference_id] = item.supported_by + [fid for c in item.counter_evidence for fid in c.fact_ids]
    targets.update({h.hypothesis_id: h.supporting_fact_ids for h in report.hypotheses})
    targets.update({r.rejected_id: r.contradicting_fact_ids for r in report.rejected})
    return targets


def badge(label: str, value: str, color: str) -> str:
    return f"**{label}**  \n:{color}[**{value}**]"


def trace_button(label: str, fact_ids: list[str], report: IncidentReport, key: str) -> None:
    st.button("🔎 Truy vết", key=key, on_click=set_highlight, args=(label, fact_ids, report),
              help="Tô sáng các FACT này trên waterfall, chart và bảng log")


# ---------------------------------------------------------------- sidebar
st.session_state.setdefault("highlight", None)
st.session_state.setdefault("facts_key", 0)
with st.sidebar:
    st.header("CallDiag MVP")
    # ?scenario=S1&trace=I1 opens a scenario already traced (handy as a demo link).
    requested = st.query_params.get("scenario")
    sid = st.selectbox("Kịch bản", list(REGISTRY), format_func=lambda s: f"{s} · {REGISTRY[s].title}", key="scenario",
                       index=list(REGISTRY).index(requested) if requested in REGISTRY else 0)
    st.caption(REGISTRY[sid].description)
    related_only = st.checkbox("Chỉ hiện log liên quan", value=True)
    llm_client, llm_reason = resolve_client()
    use_llm = st.checkbox("Dùng LLM cho summary", value=False, disabled=llm_client is None, key="use_llm",
                          help="LLM chỉ viết lại engineering/executive summary từ FACT và INFERENCE đã có; "
                               "summary vi phạm guardrail sẽ bị thay bằng bản template.")
    if llm_client is None:
        st.caption(f"LLM đang tắt: {llm_reason}.")
    else:
        st.caption(f"LLM: OpenAI · `{llm_client.model}`")
    st.caption("Dữ liệu giả lập, tất định. FACT do code sinh; INFERENCE do rule suy ra và luôn trích FACT.")
result = load(sid, use_llm)
report, bundle, anomalies = result.report, result.bundle, result.anomalies
if st.session_state.get("loaded_sid") != sid:
    st.session_state.facts_key += 1
    st.query_params["scenario"] = sid
    # Only the page's first load honours ?trace=; a scenario switch must not carry an ID
    # that would name a different FACT/INFERENCE in the new report.
    trace_id = st.query_params.get("trace")
    if st.session_state.get("loaded_sid") is None and trace_id in trace_targets(report):
        set_highlight(trace_id, trace_targets(report)[trace_id], report)
    else:
        drop_highlight()
    st.session_state.loaded_sid = sid
summary = report.summary
highlight = st.session_state.highlight or {}
refs = set(highlight.get("refs", ()))
facts_by_id = {fact.fact_id: fact for fact in report.facts}
related_ids = {log.log_id for log in report.related_logs}
on_path = {log.log_id: log.on_path for log in report.related_logs}

# ---------------------------------------------------------------- A. header
st.title("Chẩn đoán sự cố cuộc gọi WebRTC")
st.caption("Dữ liệu cuộc gọi → phát hiện bất thường → tìm bằng chứng (log) → FACT / INFERENCE → chẩn đoán có giải thích")
st.subheader(summary.headline)
columns = st.columns(4)
columns[0].markdown(badge("Severity", summary.severity.value, SEVERITY_COLORS[summary.severity.value]))
confidence = summary.confidence.value if summary.confidence is not None else "—"
columns[1].markdown(badge("Confidence", confidence, CONFIDENCE_COLORS.get(confidence, "gray")))
window = (fmt_window(summary.incident_window_start, summary.incident_window_end)
          if summary.incident_window_start is not None and summary.incident_window_end is not None else "—")
columns[2].markdown(badge("Incident window", window, "red" if summary.has_incident else "gray"))
columns[3].markdown(badge("Media path", report.scope.path, "violet" if "qua " in report.scope.path else "blue"))
if highlight:
    left, right = st.columns([5, 1])
    left.info(f"🔎 Đang truy vết **{highlight['label']}** → FACT {', '.join(highlight['fact_ids'])} "
              f"· {len(highlight['refs'])} ref tới event / sample / log (tô tím bên dưới)")
    right.button("Bỏ truy vết", on_click=clear_highlight, width="stretch")

# ---------------------------------------------------------------- B. lifecycle trace
st.header("1. Call lifecycle (trace 5 phase)")
zoom = st.toggle("Zoom vào giai đoạn thiết lập (Setup → Media established)", value=False)
st.plotly_chart(phase_waterfall(result.phases, bundle.events, refs, zoom), width="stretch")
phase_col, trace_col = st.columns(2)
phase_col.dataframe(pd.DataFrame([{
    "Phase": phase.label,
    "Status": f"{config.PHASE_STATUS_ICONS[phase.status]} {phase.status.value}",
    "Start": fmt_time(phase.start_ts, ms=True) if phase.start_ts else "—",
    "End": fmt_time(phase.end_ts, ms=True) if phase.end_ts else "—",
    "Duration": f"{phase.duration_ms} ms" if phase.duration_ms is not None else "—",
} for phase in result.phases]), hide_index=True, width="stretch")
trace = report.trace_metrics
trace_rows = [{"Chỉ số": TRACE_LABELS[name], "Giá trị": f"{value} ms" if (value := getattr(trace, name)) is not None else "—"}
              for name in TRACE_LABELS]
selected = trace.selected_pair
trace_rows += [
    {"Chỉ số": "Selected pair", "Giá trị": f"{selected.local_type}↔{selected.remote_type}" + (f" via {selected.turn_server}" if selected.via_turn else " (direct)") if selected else "—"},
    {"Chỉ số": "Candidates", "Giá trị": ", ".join(f"{k}: {v}" for k, v in trace.candidate_counts.items())},
    {"Chỉ số": "End reason", "Giá trị": trace.end_reason or "—"},
]
trace_col.dataframe(pd.DataFrame(trace_rows), hide_index=True, width="stretch")
with st.expander(f"Trace events ({len(bundle.events)})"):
    events = pd.DataFrame([{
        "event_id": e.event_id, "time": fmt_time(e.ts, ms=True), "phase": e.phase.value,
        "component": e.component, "type": e.type.value,
        "attrs": ", ".join(f"{k}={v}" for k, v in e.attrs.items()),
    } for e in bundle.events])
    st.dataframe(events.style.apply(lambda row: [ROW_HIGHLIGHT if row.event_id in refs else ""] * len(row), axis=1),
                 hide_index=True, width="stretch")

# ---------------------------------------------------------------- C. metrics
st.header("2. Metrics")
if anomalies.skipped:
    st.info(f"{anomalies.skip_reason}.")
else:
    st.caption("Vùng đỏ: QoS incident · vùng vàng: resource anomaly · nét đứt xám: baseline · nét chấm đỏ: ngưỡng tuyệt đối · tím: đang truy vết")
    st.plotly_chart(metric_panels(metrics_to_frame(bundle), anomalies, report.facts, highlight), width="stretch")

# ---------------------------------------------------------------- D. logs
st.header("3. Logs")
logs = pd.DataFrame([{
    "log_id": log.log_id, "time": fmt_time(log.ts, ms=True), "component": log.component,
    "level": log.level.value, "category": log.category.value,
    "on_path": on_path.get(log.log_id), "message": log.message,
} for log in bundle.logs if not related_only or log.log_id in related_ids or log.log_id in refs])
if logs.empty:
    st.info("Không có log liên quan trong evidence window.")
else:
    # Traced logs float to the top; otherwise keep log order.
    logs = logs.assign(_traced=~logs.log_id.isin(refs)).sort_values(["_traced", "log_id"]).drop(columns="_traced").reset_index(drop=True)
    st.caption("Vàng: log được correlate vào evidence · tím: log đang truy vết")
    st.dataframe(logs.style.apply(lambda row: [ROW_HIGHLIGHT if row.log_id in refs else ROW_RELATED if row.log_id in related_ids else ""] * len(row), axis=1),
                 hide_index=True, width="stretch")

# ---------------------------------------------------------------- E. report
st.header("4. Incident Report")
if report.validation is not None and report.validation.passed:
    st.success("Validation passed: mọi FACT có ref tới dữ liệu gốc, mọi INFERENCE trích FACT có thật.")
else:
    st.error("Validation failed")
for issue in report.validation.issues if report.validation else ():
    st.warning(f"{issue.level} {issue.code}: {issue.message}")

tabs = st.tabs(["FACTS", "INFERENCES", "HYPOTHESES / REJECTED", "UNKNOWN & NEXT CHECK", "Summary", "Markdown", "JSON"])
with tabs[0]:
    st.caption("FACT = dữ kiện lấy trực tiếp từ event / metric / log. Chọn một dòng để truy vết về dữ liệu gốc.")
    fact_ids = [fact.fact_id for fact in report.facts]
    key = f"facts_{st.session_state.facts_key}"
    st.dataframe(pd.DataFrame([{
        "ID": fact.fact_id, "Kind": fact.kind.value,
        "Time / Window": fmt_window(fact.window_start, fact.window_end) if fact.window_start and fact.window_end else (fmt_time(fact.ts, ms=True) if fact.ts else "—"),
        "Statement": fact.statement, "Refs": ", ".join(fact.refs),
    } for fact in report.facts]), key=key, on_select=lambda: on_fact_select(key, fact_ids, report),
        selection_mode="single-row", hide_index=True, width="stretch")

with tabs[1]:
    st.caption("INFERENCE = kết luận suy ra từ FACT; luôn có `supported_by`. I1 là kết luận chính.")
    if not report.inferences:
        st.info("Không đủ evidence để đưa ra INFERENCE.")
    for inference in report.inferences:
        with st.container(border=True):
            color = CONFIDENCE_COLORS[inference.confidence.value]
            st.markdown(f"#### {inference.inference_id} · `{inference.rule_id}` · Confidence :{color}[**{inference.confidence.value}**]")
            st.markdown(f"**Kết luận:** {inference.conclusion}")
            st.markdown("**Supported by:** " + " ".join(f"`{fid}`" for fid in inference.supported_by))
            counters = [fid for item in inference.counter_evidence for fid in item.fact_ids]
            trace_button(inference.inference_id, inference.supported_by + counters, report, f"trace_{inference.inference_id}")
            with st.expander("Lý do confidence, counter-evidence, alternatives"):
                st.markdown("\n".join(f"- {reason}" for reason in inference.confidence_reasons))
                st.markdown("**Counter-evidence:** " + ("; ".join(f"{c.description} ({', '.join(c.fact_ids)})" for c in inference.counter_evidence) or "không có"))
                st.markdown("**Alternatives:**\n" + "\n".join(f"- {alt}" for alt in inference.alternatives) if inference.alternatives else "**Alternatives:** —")
            with st.expander("Điều kiện của rule"):
                st.dataframe(pd.DataFrame([{
                    "Condition": c.name, "State": STATE_ICONS[c.state], "Facts": ", ".join(c.fact_ids),
                    "Mô tả": c.description + (f": {c.note}" if c.note else ""),
                } for c in inference.conditions]), hide_index=True, width="stretch")

with tabs[2]:
    st.caption("HYPOTHESIS: thiếu evidence để kết luận. REJECTED: bị loại vì có FACT mâu thuẫn.")
    if not report.hypotheses and not report.rejected:
        st.info("Không có hypothesis hay giả thuyết bị loại.")
    for hypothesis in report.hypotheses:
        with st.container(border=True):
            st.markdown(f"#### {hypothesis.hypothesis_id} · HYPOTHESIS · `{hypothesis.rule_id}`")
            st.markdown(hypothesis.statement)
            st.markdown("**Missing evidence:**\n" + "\n".join(f"- {item}" for item in hypothesis.missing_evidence))
            st.markdown("**How to verify:**\n" + "\n".join(f"- {item}" for item in hypothesis.how_to_verify))
            trace_button(hypothesis.hypothesis_id, hypothesis.supporting_fact_ids, report, f"trace_{hypothesis.hypothesis_id}")
    for rejected in report.rejected:
        with st.container(border=True):
            st.markdown(f"#### {rejected.rejected_id} · REJECTED · `{rejected.rule_id}`")
            st.markdown(f"~~{rejected.statement}~~")
            st.markdown(f"**Lý do loại:** {rejected.reason}")
            st.markdown("**Contradicting facts:** " + " ".join(f"`{fid}`" for fid in rejected.contradicting_fact_ids))
            trace_button(rejected.rejected_id, rejected.contradicting_fact_ids, report, f"trace_{rejected.rejected_id}")

with tabs[3]:
    left, right = st.columns(2)
    left.markdown("**UNKNOWN**\n" + ("\n".join(f"- {item}" for item in report.unknowns) or "\n_Không có._"))
    right.markdown("**NEXT CHECK**\n" + ("\n".join(f"- {item}" for item in report.next_checks) or "\n_Không có._"))
    for evidence in report.evidence:
        st.caption(f"{evidence.evidence_id} · {evidence.focus.value} · window {fmt_window(evidence.window_start, evidence.window_end)} · {evidence.clock_alignment}")

with tabs[4]:
    with st.container(border=True):
        st.markdown("##### 📝 Executive summary")
        st.caption("Cho người không chuyên WebRTC")
        st.markdown(escape_markdown(report.executive_summary))
    with st.container(border=True):
        st.markdown("##### 🛠️ Engineering summary")
        st.caption("Mỗi ý một dòng · nhãn ở cuối là bằng chứng được trích: "
                   ":blue-badge[F] FACT · :violet-badge[I] INFERENCE · :orange-badge[H] HYPOTHESIS · :red-badge[R] REJECTED")
        st.markdown("\n".join(f"- {escape_markdown(text)} {badges(ids)}".rstrip()
                               for text, ids in split_summary(report.engineering_summary)))
    if report.summary_source == "llm":
        st.caption("summary_source = llm · đã qua validator: mọi trích dẫn tồn tại, không có con số ngoài dữ liệu đầu vào")
    else:
        st.caption("summary_source = template" + (" · LLM đã được yêu cầu nhưng bị bỏ qua, xem cảnh báo ở đầu mục 4" if use_llm else ""))

with tabs[5]:
    markdown = render_markdown(report)
    st.download_button("Tải report (.md)", markdown, file_name=f"{sid}.md", mime="text/markdown")
    # The renderer escapes every data cell; raw HTML is only its own <details> wrapper.
    st.markdown(markdown, unsafe_allow_html=True)

with tabs[6]:
    st.download_button("Tải report (.json)", report.model_dump_json(indent=2), file_name=f"{sid}.json", mime="application/json")
    st.json(report.model_dump(mode="json"), expanded=False)
