---
name: calldiag-llm-summary
description: LLM summary của CallDiag - LLM chỉ viết lại engineering/executive summary từ report đã kiểm chứng; LLMClient Protocol, OpenAIClient, FakeLLM, prompt, cache out/llm_cache, LLM_PROMPT_VERSION và guardrail của validator. Dùng khi sửa prompt, đổi model, thêm provider, hoặc debug summary bị quay về template.
---

# LLM summary

Đọc trước: mục 5 bước [7] trong `docs/MVP_PLAN.md`. Code: `calldiag/llm/client.py`, `calldiag/llm/summary.py`; guardrail ở `calldiag/pipeline/validator.py`.

## Vai trò

LLM **chỉ viết lại** hai đoạn `engineering_summary` và `executive_summary`. Nó không tạo hay sửa FACT, INFERENCE, HYPOTHESIS, REJECTED, confidence, severity. Pipeline vẫn chạy đầy đủ khi không có LLM.

- Đầu vào LLM là `build_llm_input(report)`: headline, severity, confidence, window, path, phases, facts, inferences, hypotheses, rejected, unknowns. **Không** có scenario ID, title hay call ID (để không lộ đáp án).
- Đầu ra phải là JSON object `{"engineering_summary": ..., "executive_summary": ...}`.
- Mọi lỗi (thiếu cấu hình, SDK lỗi, refusal, bị cắt do token, JSON sai) → giữ summary template và thêm `W_LLM_UNAVAILABLE` hoặc `W_LLM_FAILED`. LLM không bao giờ được làm hỏng report.

## Guardrail (validator)

Khi `summary_source == "llm"`, bất kỳ cảnh báo nào sau đây làm report quay về template:
`W_SUMMARY_UNKNOWN_CITE` (trích ID không có), `W_SUMMARY_NEW_NUMBER` (số > 5 không có trong đầu vào), `W_SUMMARY_BAD_CITE` (ngoặc vuông không phải danh sách ID, ví dụ `[unknowns]`), `W_SUMMARY_NO_CITE` (engineering không trích gì), `W_SUMMARY_EXEC_CITE` (executive có trích dẫn), `W_SUMMARY_TOO_LONG` (executive > `EXEC_SUMMARY_MAX_WORDS`).

## Cấu hình

- Biến môi trường: `CALLDIAG_LLM_PROVIDER` (mặc định `openai`, hiện chỉ có provider này), `CALLDIAG_LLM_MODEL` (bắt buộc, không hard-code), `OPENAI_API_KEY`, tùy chọn `OPENAI_BASE_URL`.
- `.env` được `calldiag/envfile.py` đọc chỉ ở CLI và UI; shell thắng file. **Không in hay commit giá trị trong `.env`.**
- Không gửi `temperature` (một số model từ chối); tính tất định đến từ cache.

## Khi sửa

- Đổi `SYSTEM_PROMPT` hoặc cấu trúc `build_llm_input` → tăng `config.LLM_PROMPT_VERSION` để cache cũ không còn khớp.
- Thêm provider: tạo class có `model` và `complete(system, user) -> str` theo Protocol `LLMClient`, thêm tên vào `config.LLM_PROVIDERS`, rẽ nhánh trong `resolve_client()`. Import SDK lazy để extra vẫn là tùy chọn.
- Test luôn dùng `FakeLLM(response=..., error=...)` hoặc stub SDK, không gọi API thật, không cần key (`tests/test_llm_summary.py`). Mỗi guardrail mới cần một test với response cố tình vi phạm.
- Chạy thật để so model: `python -m calldiag run --scenario all --llm`, rồi xem `summary_source` và warning của từng report; báo lại cho người dùng kết quả so sánh (model nào qua validator, warning gì).
