---
name: calldiag-diagnosis-contract
description: Hợp đồng dữ liệu và các invariant của CallDiag - FACT / INFERENCE / HYPOTHESIS / REJECTED / UNKNOWN, refs, confidence High/Medium/Low, missing khác 0, validator và các mã lỗi E_* / W_*. Dùng trước khi sửa models.py, pipeline/facts.py, pipeline/reasoning.py, pipeline/validator.py, pipeline/report.py hoặc bất cứ code nào tạo hay đọc report.
---

# Hợp đồng chẩn đoán của CallDiag

Nguồn sự thật cho model, enum và ID là code (`calldiag/models.py`, `calldiag/config.py`); mô tả tổng quan ở mục 4–5 của `docs/MVP_PLAN.md`. Đổi contract thì cập nhật `docs/MVP_PLAN.md` **trong cùng thay đổi**.

## Năm loại kết quả

| Loại | Model (`calldiag/models.py`) | Bắt buộc |
|---|---|---|
| FACT | `Fact` (`fact_id` F1…, `kind: FactKind`, `refs`) | Chỉ tạo trong `pipeline/facts.py` qua `FactStore`; `refs` khác rỗng và resolve được tới `ev-` / `m-` / `log-` / `an-` / `inc-`; statement không chứa `config.BANNED_FACT_WORDS` |
| INFERENCE | `Inference` (`inference_id` I1…, `rule_id`, `supported_by`) | `supported_by` khác rỗng và chỉ chứa FACT có thật; có `confidence`, `confidence_reasons`, `conditions` |
| HYPOTHESIS | `Hypothesis` (H1…) | `missing_evidence` khác rỗng, `how_to_verify` |
| REJECTED | `RejectedHypothesis` (R1…) | `contradicting_fact_ids` là FACT có thật, `reason` |
| UNKNOWN | `ReasoningResult.unknowns` + `next_checks` | |

`FactKind`: `phase_status`, `selected_path`, `ice_checks`, `trace_timing`, `metric_change`, `metric_level`, `missing_data`, `log_event`.

## Invariant (không được vi phạm)

1. FACT ghi điều code **chứng minh được**, không suy diễn. Viết "không ghi nhận anomaly theo rule", không viết "không vượt ngưỡng". Log có từ cấm vẫn giữ trong evidence nhưng không thành FACT.
2. Pipeline không đọc `meta.scenario_id`, `meta.title`, không rẽ nhánh theo `call_id`. `run_pipeline` trả `report.scenario_id=""`; CLI / `run_scenario` gắn nhãn ở biên.
3. Dữ liệu thiếu là `None`, **không bao giờ** thay bằng 0. Thiếu dữ liệu thì condition trả `UNKNOWN`, sinh FACT `missing_data`, và kết luận thành HYPOTHESIS hoặc bị trừ confidence. Không suy ra "khỏe" từ dữ liệu thiếu.
4. Confidence chỉ là `High` / `Medium` / `Low` (không phải phần trăm); severity (`critical` / `major` / `minor` / `none`) là trường riêng.
5. Dùng TURN không phải là lỗi. TURN chỉ bị quy trách nhiệm khi **nằm trên selected path** và có anomaly chồng lấn incident.
6. Mọi ngưỡng / hằng số ở `calldiag/config.py`. Dữ liệu theo kịch bản ở `calldiag/scenarios/` (test `test_config_holds_no_scenario_data` khóa điều này).
7. Tất định: cùng input → cùng output, trừ `generated_at`.
8. Hàm trong `pipeline/` là hàm thuần: không I/O, không `print`. I/O chỉ ở `io.py`, `cli.py`, `app/`.

## Validator (`pipeline/validator.py`)

`validate_report(report, bundle)` dựng lại anomaly từ telemetry gốc để kiểm refs, không tin ID mà FACT tự khai. `apply_validation` loại INFERENCE lỗi, chọn lại primary và headline, và quay về summary template nếu cần.

- Lỗi (làm `passed=False`, `--strict` exit 1): `E_DUP_ID`, `E_FACT_NO_REF`, `E_FACT_BAD_REF`, `E_FACT_BANNED_WORD`, `E_INF_NO_SUPPORT`, `E_INF_BAD_SUPPORT`, `E_COUNTER_BAD_REF`, `E_CONFIDENCE`, `E_HYP_NO_MISSING`, `E_PRIMARY`.
- Cảnh báo summary: `W_SUMMARY_UNKNOWN_CITE`, `W_SUMMARY_NEW_NUMBER`, `W_SUMMARY_BAD_CITE`, `W_SUMMARY_NO_CITE`, `W_SUMMARY_EXEC_CITE`, `W_SUMMARY_TOO_LONG`; cảnh báo LLM: `W_LLM_UNAVAILABLE`, `W_LLM_FAILED`.

Không nới lỏng validator, không xóa hay skip test để cho pass. Thêm loại kiểm tra mới thì thêm test cố tình làm sai để chứng minh nó bắt được lỗi.

## Style

Identifier tiếng Anh; nội dung report (statement, conclusion, summary) tiếng Việt, giữ thuật ngữ kỹ thuật tiếng Anh. Python 3.11, type hint đầy đủ, pydantic v2. Không thêm dependency ngoài `pyproject.toml` (extra `llm` cho SDK openai).
