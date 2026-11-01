"""Let an LLM reword the two report summaries; nothing else in the report comes from it (plan 10).

The LLM only sees FACT statements, INFERENCE conclusions and the other already-validated parts of
the report, never the scenario label. Its text then goes through the validator (plan 07): a citation
to a missing FACT, a number absent from the evidence, an over-long executive summary or a missing
citation sends the report back to the template summaries, with the warning kept.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from calldiag import config
from calldiag.llm.client import LLMClient, resolve_client
from calldiag.models import IncidentReport, ValidationIssue, ValidationResult
from calldiag.pipeline.report import report_window

SYSTEM_PROMPT = f"""Bạn là trợ lý viết báo cáo sự cố cuộc gọi WebRTC. Bạn CHỈ được dùng thông tin trong JSON đầu vào.
JSON đầu vào đã được kiểm chứng: "facts" là dữ kiện quan sát được (FACT), "inferences" là kết luận suy ra từ FACT,
"hypotheses" là giả thuyết chưa xác nhận, "rejected" là giả thuyết đã bị loại, "unknowns" là điều chưa biết.

Quy tắc:
1. Không thêm dữ kiện, con số, thời điểm, mã lỗi hay tên thành phần nào không có nguyên văn trong JSON. Không tự tính thêm (ví dụ thời lượng).
2. Không nâng mức chắc chắn: giữ nguyên confidence của inference; hypothesis phải được nói là "chưa xác nhận"; giả thuyết trong "rejected" không được trình bày như nguyên nhân.
3. engineering_summary: tiếng Việt, giữ thuật ngữ kỹ thuật tiếng Anh; mỗi câu kết thúc bằng trích dẫn ID có trong JSON, dạng [F9] hoặc [I1] hoặc [F8, F12].
4. executive_summary: tiếng Việt cho người không chuyên, không thuật ngữ kỹ thuật, không trích dẫn ID, tối đa {config.EXEC_SUMMARY_MAX_WORDS} từ.
5. Nếu "unknowns" khác rỗng, mỗi summary phải nhắc ít nhất một điều chưa biết.

Trả về DUY NHẤT một JSON object: {{"engineering_summary": "...", "executive_summary": "..."}}"""


def build_llm_input(report: IncidentReport) -> dict[str, Any]:
    """What the LLM may see. No scenario ID, title or call ID (they could leak the answer)."""
    summary = report.summary
    return {
        "headline": summary.headline,
        "severity": summary.severity.value,
        "confidence": summary.confidence.value if summary.confidence is not None else None,
        "incident_window": report_window(report) if summary.has_incident else None,
        "path": report.scope.path,
        "phases": [{"label": phase.label, "status": phase.status.value} for phase in report.phases],
        "facts": [{"id": fact.fact_id, "statement": fact.statement} for fact in report.facts],
        "inferences": [{"id": i.inference_id, "conclusion": i.conclusion, "confidence": i.confidence.value,
                        "supported_by": i.supported_by} for i in report.inferences],
        "hypotheses": [{"id": h.hypothesis_id, "statement": h.statement, "missing_evidence": h.missing_evidence}
                       for h in report.hypotheses],
        "rejected": [{"id": r.rejected_id, "statement": r.statement, "reason": r.reason} for r in report.rejected],
        "unknowns": report.unknowns,
    }


def _parse(text: str) -> tuple[str, str]:
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rsplit("```", 1)[0]
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("LLM không trả về JSON object")
    engineering, executive = data.get("engineering_summary"), data.get("executive_summary")
    if not isinstance(engineering, str) or not engineering.strip() or not isinstance(executive, str) or not executive.strip():
        raise ValueError("thiếu engineering_summary hoặc executive_summary")
    return engineering.strip(), executive.strip()


def _cache_path(cache_dir: Path, model: str, user: str) -> Path:
    key = json.dumps({"prompt_version": config.LLM_PROMPT_VERSION, "model": model, "system": SYSTEM_PROMPT, "user": user},
                     ensure_ascii=False, sort_keys=True)
    return cache_dir / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"


def _warn(report: IncidentReport, code: str, message: str) -> IncidentReport:
    issues = list(report.validation.issues) if report.validation else []
    issues.append(ValidationIssue(level="warning", code=code, message=message))
    report.validation = ValidationResult(passed=report.validation.passed if report.validation else True, issues=issues)
    return report


def add_llm_summary(
    report: IncidentReport, client: LLMClient | None = None, *,
    cache_dir: Path | None = Path(config.LLM_CACHE_DIR),
) -> IncidentReport:
    """Return a copy whose summaries come from the LLM, or the template copy plus a warning."""
    output = report.model_copy(deep=True)
    if client is None:
        client, reason = resolve_client()
        if client is None:
            return _warn(output, "W_LLM_UNAVAILABLE", f"Không gọi LLM: {reason}. Giữ summary template.")
    user = json.dumps(build_llm_input(output), ensure_ascii=False, indent=2)
    path = _cache_path(cache_dir, client.model, user) if cache_dir is not None else None
    try:
        cached = path is not None and path.is_file()
        raw = json.loads(path.read_text(encoding="utf-8"))["response"] if cached else client.complete(SYSTEM_PROMPT, user)
        engineering, executive = _parse(raw)
    except Exception as exc:  # an LLM problem must never break the report
        return _warn(output, "W_LLM_FAILED", f"LLM summary lỗi ({type(exc).__name__}: {exc}). Giữ summary template.")
    if path is not None and not cached:
        try:  # best effort: a read-only disk only costs a repeat call next time
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": client.model, "response": raw}, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    output.engineering_summary, output.executive_summary, output.summary_source = engineering, executive, "llm"
    return output
