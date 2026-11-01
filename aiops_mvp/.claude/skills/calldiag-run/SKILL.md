---
name: calldiag-run
description: Cài đặt và chạy CallDiag MVP (aiops_mvp) - CLI list/generate/run/eval, Streamlit UI, pytest, bật LLM summary qua .env, và kịch bản demo cho mentor. Dùng khi cần chạy, kiểm tra kết quả, xác nhận một thay đổi chạy đúng end-to-end, hoặc chuẩn bị demo.
---

# Chạy CallDiag

Mọi lệnh chạy từ thư mục `aiops_mvp/` (chứa `pyproject.toml`). Python 3.11+.

## Cài đặt

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # ".[dev,llm]" nếu cần LLM summary
```

Nếu `.venv/` đã có, dùng thẳng `.venv/bin/python -m ...`.

## Lệnh

| Lệnh | Việc | Exit code |
|---|---|---|
| `python -m calldiag list` | Liệt kê S0–S6 | 0 |
| `python -m calldiag generate --scenario all` | Ghi `data/scenarios/S*.json` | 0 |
| `python -m calldiag run --scenario S1` | Ghi `out/reports/S1.{json,md}` và `out/traces/S1.otel.json`, in headline/severity/confidence | 0 |
| `python -m calldiag run --scenario all --strict` | Chạy cả 7 | 1 nếu có report không qua validator |
| `python -m calldiag run --input <file.json>` | Chẩn đoán một file telemetry | 0 / lỗi argparse nếu file sai |
| `python -m calldiag eval` | So với `ExpectedOutcome`, ghi `out/eval.md` | 1 nếu có FAIL |
| `pytest -q` | Toàn bộ test | |
| `streamlit run app/streamlit_app.py` | UI tại `http://localhost:8501/?scenario=S1&trace=I1` | |

## Xác nhận một thay đổi

Một thay đổi chỉ coi là xong khi **cả hai** đều xanh:

1. `pytest -q`: tất cả pass (hiện có khoảng 480 test).
2. `python -m calldiag eval`: `7/7 PASS`.

Đổi UI thì chạy thêm `pytest -q tests/test_app.py` (smoke test bằng `streamlit.testing.v1.AppTest`). Báo kết quả đúng như output, kể cả khi có test fail.

## LLM summary

- Cấu hình nằm trong `aiops_mvp/.env` (git-ignored), mẫu ở `.env.example`: `OPENAI_API_KEY`, `CALLDIAG_LLM_MODEL`, tùy chọn `CALLDIAG_LLM_PROVIDER`, `OPENAI_BASE_URL`.
- **Không bao giờ in, cat, commit hay đưa giá trị trong `.env` vào output.** Chỉ kiểm tra biến có được đặt hay không.
- `python -m calldiag run --scenario S1 --llm`: report có `summary_source=llm` nếu qua validator; ngược lại là `template` kèm warning `W_LLM_*` / `W_SUMMARY_*`.
- Response cache ở `out/llm_cache/`; xóa file cache tương ứng nếu muốn gọi lại thật.
- Test không bao giờ đọc `.env` thật: `tests/conftest.py` đặt `CALLDIAG_ENV_FILE=""`.

## Demo (~10 phút)

S0 (không bịa lỗi) → S1 (TURN quá tải, truy vết I1) → S2 (TURN bị REJECTED vì không nằm trên path) → S4 (relay ≠ lỗi) → S6 (thiếu TURN CPU → HYPOTHESIS, Medium) → S3/S5 (fail sớm, phase sau skipped) → `python -m calldiag eval` 7/7 PASS.
