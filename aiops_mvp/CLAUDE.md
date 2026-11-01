# CallDiag MVP — hướng dẫn cho Claude Code

MVP chẩn đoán sự cố cuộc gọi WebRTC 1:1 (P2P / TURN) từ telemetry giả lập. Kết quả là Incident Report tách rõ FACT / INFERENCE / HYPOTHESIS / REJECTED / UNKNOWN, mọi khẳng định truy ngược được về dữ liệu gốc.

- Cách chạy: `README.md`.
- Bài toán, phạm vi, luồng chạy từng bước, lý do thiết kế: `docs/MVP_PLAN.md`.

## Bản đồ skill

Project skills nằm ở `.claude/skills/`. Gọi skill tương ứng **trước** khi bắt tay vào việc:

| Skill | Gọi khi | Nội dung chính |
|---|---|---|
| `calldiag-run` | Cài đặt, chạy CLI / eval / UI, xác nhận một thay đổi chạy đúng, chuẩn bị demo | Bảng lệnh và exit code, tiêu chí "xong" (`pytest -q` + `eval` 7/7), bật LLM qua `.env`, kịch bản demo |
| `calldiag-diagnosis-contract` | Sửa `models.py`, `pipeline/facts.py`, `reasoning.py`, `validator.py`, `report.py` hoặc bất cứ code nào tạo / đọc report | 5 loại kết quả, các invariant, mã lỗi `E_*` / `W_*` của validator, style |
| `calldiag-add-rule` | Thêm / sửa rule, condition, cách tính confidence, câu conclusion hoặc rejection | Cấu trúc `RuleSpec`, condition TRUE/FALSE/UNKNOWN, logic INFERENCE / HYPOTHESIS / REJECTED, checklist |
| `calldiag-add-scenario` | Thêm kịch bản telemetry mới (S7…) hoặc biến thể của kịch bản có sẵn | Builder / Profile / Plateau, đăng ký `REGISTRY`, `ExpectedOutcome`, các test đếm cứng 7 kịch bản |
| `calldiag-llm-summary` | Sửa prompt, đổi model, thêm provider, debug summary bị quay về template | Vai trò của LLM, guardrail, cache, `LLM_PROMPT_VERSION`, `FakeLLM` |

Việc đụng nhiều mảng thì gọi nhiều skill. Ví dụ thêm một loại sự cố mới thường cần `calldiag-add-scenario` + `calldiag-add-rule` + `calldiag-diagnosis-contract`.

## Invariant (tóm tắt — chi tiết trong `calldiag-diagnosis-contract`)

1. FACT chỉ tạo trong `calldiag/pipeline/facts.py`, luôn có `refs` resolve được, không chứa từ nhân quả (`config.BANNED_FACT_WORDS`).
2. INFERENCE luôn có `supported_by` trỏ tới FACT có thật.
3. Pipeline không đọc `meta.scenario_id` / `meta.title`, không rẽ nhánh theo `call_id`.
4. Thiếu dữ liệu là `None`, không bao giờ thay bằng 0.
5. Confidence chỉ là High / Medium / Low; severity là trường riêng.
6. Ngưỡng / hằng số ở `calldiag/config.py`; dữ liệu theo kịch bản ở `calldiag/scenarios/`.
7. LLM chỉ viết lại summary, không tạo FACT / kết luận / confidence.

## Quy trình làm việc

1. Đọc phần liên quan trong `docs/MVP_PLAN.md` và gọi skill phù hợp.
2. Đọc code xung quanh trước khi sửa; viết theo đúng phong cách sẵn có (hàm thuần trong `pipeline/`, I/O chỉ ở `io.py` / `cli.py` / `app/`, type hint đầy đủ, pydantic v2).
3. Sửa code kèm test. Không nới lỏng validator, không xóa / skip test để cho pass.
4. Xác nhận: `pytest -q` pass **và** `python -m calldiag eval` toàn PASS. Đổi UI thì chạy thêm `pytest -q tests/test_app.py`.
5. Luồng hoặc contract thay đổi thì cập nhật `docs/MVP_PLAN.md` và `README.md` trong cùng thay đổi.
6. Báo kết quả đúng như output, kể cả khi có test fail.

## Lưu ý

- `.env` chứa API key thật: **không đọc ra, in, hay commit giá trị**. Chỉ kiểm tra biến có được đặt hay không.
- Test không phụ thuộc mạng hay key (`tests/conftest.py` đặt `CALLDIAG_ENV_FILE=""`; LLM dùng `FakeLLM`).
- Identifier tiếng Anh; nội dung report tiếng Việt, giữ thuật ngữ kỹ thuật tiếng Anh.
- Không thêm dependency ngoài `pyproject.toml` (extra `llm` cho SDK openai).
- Commit theo Conventional Commits, scope theo module: `feat(pipeline): ...`, `fix(scenarios): ...`, `docs(calldiag): ...`.

## Lệnh hay dùng

```bash
pip install -e ".[dev]"
pytest -q
python -m calldiag eval
python -m calldiag run --scenario S1
streamlit run app/streamlit_app.py
```
