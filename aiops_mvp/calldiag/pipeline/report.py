"""Assemble an evidence-backed incident report and template summaries."""

from datetime import UTC, datetime

from calldiag import config
from calldiag.models import (
    PHASE_LABELS, AnomalyResult, CallTelemetry, FactKind, IncidentReport,
    PathContext, Phase, PhaseSpan, PhaseStatus, ReasoningResult, ReportScope,
    ReportSummary, Severity, TimelineItem, TraceMetrics, EvidenceBundle,
)
from calldiag.pipeline.facts import FactStore
from calldiag.utils import fmt_window


def compute_severity(phases: list[PhaseSpan], anomalies: AnomalyResult) -> Severity:
    if any(p.phase != Phase.TERMINATION and p.status == PhaseStatus.FAILED for p in phases):
        return Severity.CRITICAL
    if not anomalies.incidents:
        return Severity.NONE
    if any(i.duration_sec >= config.MAJOR_INCIDENT_MIN_SEC for i in anomalies.incidents) or any(
        a.metric == "packet_loss_pct" and a.peak_value >= config.MAJOR_LOSS_PCT for a in anomalies.anomalies
    ):
        return Severity.MAJOR
    return Severity.MINOR


def build_headline(reasoning: ReasoningResult, window: str) -> str:
    primary = next((item for item in reasoning.inferences if item.inference_id == reasoning.primary_inference_id), None)
    return config.REPORT_HEADLINES.get(primary.rule_id, "Không đủ evidence để kết luận").format(window=window) if primary else "Không đủ evidence để kết luận"


def report_window(report: IncidentReport) -> str:
    summary = report.summary
    return fmt_window(summary.incident_window_start, summary.incident_window_end) if summary.incident_window_start is not None and summary.incident_window_end is not None else "không xác định"


def build_engineering_summary(report: IncidentReport) -> str:
    parts: list[str] = []
    phases = [fact for fact in report.facts if fact.kind == FactKind.PHASE_STATUS]
    failed = [fact for fact in phases if fact.data["status"] == "failed"]
    if failed:
        for fact in failed:
            parts.append(f"Cuộc gọi dừng ở phase {PHASE_LABELS[Phase(fact.data['phase'])]} [{fact.fact_id}].")
        skipped = [fact for fact in phases if fact.data["status"] == "skipped"]
        if skipped:
            parts.append("Các phase được đánh dấu skipped: " + ", ".join(f"{PHASE_LABELS[Phase(f.data['phase'])]} [{f.fact_id}]" for f in skipped) + ".")
    else:
        ok = [f for f in phases if f.data["status"] in {"ok", "degraded"}]
        if ok:
            parts.append("Các phase hoàn tất: " + ", ".join(f"{PHASE_LABELS[Phase(f.data['phase'])]} [{f.fact_id}]" for f in ok) + ".")
    for fact in report.facts:
        if fact.kind == FactKind.SELECTED_PATH:
            parts.append(f"{fact.statement.rstrip('.')} [{fact.fact_id}].")
    changes = [f for f in report.facts if f.kind == FactKind.METRIC_CHANGE]
    qos = sorted((f for f in changes if f.data["category"] == "qos"),
                 key=lambda f: config.QOS_SUMMARY_PRIORITY.index(f.data["metric"]))
    selected = qos[:config.ENGINEERING_MAX_QOS_FACTS] + [f for f in changes if f.data["category"] == "resource"]
    # Tell the story in time order, e.g. TURN CPU rises before RTT.
    for fact in sorted(selected, key=lambda f: (f.ts, f.fact_id)):
        parts.append(f"{fact.statement.rstrip('.')} [{fact.fact_id}].")
    primary = next((i for i in report.inferences if i.inference_id == report.summary.primary_inference_id), None)
    if primary is not None:
        parts.append(f"Nhận định: {primary.conclusion.rstrip('.')} [{primary.inference_id}] (confidence {primary.confidence.value}, severity {report.summary.severity.value}).")
    else:
        parts.append("Chưa đủ evidence để đưa ra kết luận chính.")
    if report.unknowns:
        parts.append("Chưa xác định: " + "; ".join(report.unknowns[:config.ENGINEERING_MAX_UNKNOWNS]) + ".")
    return " ".join(parts)


def build_executive_summary(report: IncidentReport) -> str:
    summary = report.summary
    if summary.failed_phase == Phase.OFFER_ANSWER:
        return "Cuộc gọi không kết nối được: hai bên chưa trao đổi xong thông tin thiết lập. Cần kiểm tra bản ghi máy chủ và kết nối của người nhận."
    if summary.failed_phase == Phase.ICE:
        if summary.primary_rule_id != "ICE_CONNECTIVITY_FAILURE":
            return "Cuộc gọi thất bại khi thiết lập đường truyền giữa hai thiết bị. Chưa đủ dữ liệu để xác định kết quả và nguyên nhân của từng đường kết nối."
        return "Cuộc gọi không kết nối được: các đường kết nối đã thử giữa hai thiết bị đều thất bại. Cần kiểm tra tường lửa và khả năng truy cập máy chủ trung chuyển."
    if summary.failed_phase is not None:
        return "Cuộc gọi thất bại trong quá trình thiết lập. Cần kiểm tra các sự kiện và bản ghi tương ứng với giai đoạn thất bại."
    if summary.has_incident:
        text = f"Cuộc gọi kết nối thành công nhưng chất lượng giảm trong khoảng {report_window(report)}."
        if summary.primary_rule_id == "TURN_OVERLOAD_DEGRADATION":
            text += " Thời điểm này trùng với lúc máy chủ trung chuyển có tải cao; quá tải máy chủ là một khả năng được dữ liệu ủng hộ."
        if summary.confidence in {None, "Medium", "Low"}:
            text += " Nguyên nhân chính xác chưa xác định được do thiếu dữ liệu hoặc còn phản chứng."
        return text
    if summary.primary_rule_id in {"HEALTHY_CALL", "RELAY_NOT_A_FAULT"}:
        return "Cuộc gọi diễn ra bình thường, không phát hiện suy giảm chất lượng theo các điều kiện kiểm tra."
    return "Chưa đủ dữ liệu để kết luận về chất lượng cuộc gọi. Cần bổ sung dữ liệu ở các giai đoạn chưa được quan sát đầy đủ."


def assemble_report(
    *, bundle: CallTelemetry, phases: list[PhaseSpan], trace: TraceMetrics,
    path_ctx: PathContext, anomalies: AnomalyResult, evidence: list[EvidenceBundle],
    facts: FactStore, reasoning: ReasoningResult, timeline: list[TimelineItem],
) -> IncidentReport:
    failed = next((p for p in phases if p.phase != Phase.TERMINATION and p.status == PhaseStatus.FAILED), None)
    intervals = anomalies.incidents
    start = failed.start_ts if failed else min((i.start_ts for i in intervals), default=None)
    end = failed.end_ts if failed else max((i.end_ts for i in intervals), default=None)
    primary = next((i for i in reasoning.inferences if i.inference_id == reasoning.primary_inference_id), None)
    logs = {log.log_id: log for item in reversed(evidence) for log in item.related_logs}
    report = IncidentReport(
        generated_at=datetime.now(UTC),
        # The CLI/run_scenario boundary supplies the display/file label.
        # Analysis never reads meta.scenario_id or meta.title.
        scenario_id="",
        summary=ReportSummary(
            headline=build_headline(reasoning, fmt_window(start, end) if start is not None and end is not None else "không xác định"),
            has_incident=failed is not None or bool(intervals), failed_phase=failed.phase if failed else None,
            incident_window_start=start, incident_window_end=end, severity=compute_severity(phases, anomalies),
            primary_inference_id=primary.inference_id if primary else None,
            primary_rule_id=primary.rule_id if primary else None, confidence=primary.confidence if primary else None,
        ),
        scope=ReportScope(
            call_id=bundle.meta.call_id, participants=[bundle.meta.caller, bundle.meta.callee],
            measured_endpoint=bundle.meta.measured_endpoint,
            direction=f"inbound media tại {bundle.meta.measured_endpoint} + candidate-pair RTT", path=path_ctx.description,
        ),
        phases=phases, trace_metrics=trace, incident_intervals=intervals,
        timeline=[item for item in timeline if item.kind != "log" or item.ref_id in logs],
        facts=facts.all(), related_logs=sorted(logs.values(), key=lambda log: (log.ts, log.log_id)),
        inferences=reasoning.inferences, hypotheses=reasoning.hypotheses, rejected=reasoning.rejected,
        unknowns=reasoning.unknowns, next_checks=reasoning.next_checks, evidence=evidence,
        engineering_summary="", executive_summary="",
    ).model_copy(deep=True)
    report.engineering_summary = build_engineering_summary(report)
    report.executive_summary = build_executive_summary(report)
    return report
