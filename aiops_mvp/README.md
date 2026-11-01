# CallDiag — chẩn đoán sự cố cuộc gọi WebRTC (MVP)

CallDiag đọc telemetry của **một cuộc gọi WebRTC 1:1** (P2P hoặc qua TURN) và xuất **Incident Report** có thể truy vết tới từng dòng dữ liệu gốc. Report tách rõ:

- **FACT**: dữ kiện do code trích ra, luôn có `refs` tới event / metric sample / log / anomaly có thật.
- **INFERENCE**: kết luận do rule suy ra, luôn trích FACT (`supported_by`), có confidence High/Medium/Low và lý do.
- **HYPOTHESIS**: giả thuyết thiếu dữ liệu để xác nhận, ghi rõ thiếu gì và cách kiểm tra.
- **REJECTED**: giả thuyết bị FACT bác bỏ, kèm FACT phản chứng.
- **UNKNOWN**: điều hệ thống chưa biết, cùng danh sách next check.

Vòng đời cuộc gọi được dựng lại theo 5 phase và hiển thị như một trace:

```
Call Setup → Offer/Answer SDP → ICE Candidate Exchange → Media Established → Call Termination
```

Dữ liệu là synthetic và tất định (seed cố định): cùng input luôn cho cùng report.

## Yêu cầu

- Python **3.11+**
- Lệnh bên dưới viết cho Linux / macOS / WSL. Trên Windows PowerShell: `.venv\Scripts\activate` thay cho `source .venv/bin/activate`.

## Cài đặt

```bash
cd aiops_mvp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # thêm ".[dev,llm]" nếu muốn dùng LLM summary
```

## Chạy nhanh

```bash
python -m calldiag list                          # liệt kê 7 kịch bản S0–S6
python -m calldiag run --scenario S1             # chẩn đoán 1 kịch bản
python -m calldiag run --scenario all --strict   # cả 7; exit 1 nếu report nào không qua validator
python -m calldiag eval                          # benchmark 7 kịch bản → bảng PASS/FAIL
streamlit run app/streamlit_app.py               # UI tại http://localhost:8501
pytest -q                                        # toàn bộ test (không cần mạng, không cần API key)
```

Các lệnh khác:

```bash
python -m calldiag generate --scenario all       # ghi telemetry ra data/scenarios/S*.json
python -m calldiag run --input data/scenarios/S1.json   # chẩn đoán từ một file telemetry
```

Link mở thẳng một kịch bản và truy vết một ID: `http://localhost:8501/?scenario=S1&trace=I1` (`trace` nhận ID FACT, INFERENCE, HYPOTHESIS hoặc REJECTED, ví dụ `F12`, `I1`, `H1`, `R1`).

### Đầu ra

| File | Nội dung |
|---|---|
| `out/reports/<S>.json` | Incident Report đầy đủ (FACT, INFERENCE, HYPOTHESIS, REJECTED, UNKNOWN, validation) |
| `out/reports/<S>.md` | Report dạng Markdown để đọc hoặc gửi |
| `out/traces/<S>.otel.json` | Vòng đời cuộc gọi dạng OpenTelemetry trace (1 root span + 5 span phase) |
| `out/eval.md` | Kết quả `eval`: bảng PASS/FAIL, kết luận của hệ thống, các check trượt |
| `data/scenarios/<S>.json` | Telemetry đầu vào (meta, trace events, metric samples, logs) |

`out/` không được commit; chạy lại lệnh là có.

## Pipeline

```
scenarios/*  →  CallTelemetry  (meta + trace events + metric samples + logs)
  [1] timeline + localize_phases   5 phase: ok / degraded / failed / skipped / incomplete, trace metrics
  [2] detect_anomalies             baseline median 20 s đầu Media + ngưỡng tuyệt đối & tương đối + rolling 5 s
  [3] correlate                    log trong [incident ± 10 s], đánh dấu component có nằm trên media path
  [4] extract_facts                F1…Fn; mỗi FACT có refs ev-… / m-… / log-… / an-… / inc-…
  [5] reason (6 rule)              INFERENCE / HYPOTHESIS / REJECTED, confidence High/Medium/Low
  [6] assemble_report + validator  loại INFERENCE trích FACT không tồn tại, kiểm refs, từ cấm, summary LLM
```

Mỗi bước là hàm thuần trong `calldiag/pipeline/`; điều phối ở `calldiag/pipeline/run.py`. Mọi ngưỡng và hằng số nằm trong `calldiag/config.py`.

### Rule

| Rule | Khi nào thành INFERENCE |
|---|---|
| `SIGNALING_FAILURE` | Phase Offer/Answer failed và quan sát được ANSWER timeout |
| `ICE_CONNECTIVITY_FAILURE` | Phase ICE failed và mọi candidate pair đã thử đều thất bại |
| `TURN_OVERLOAD_DEGRADATION` | Có QoS incident, path đi qua TURN, TURN CPU **của server trên path** cao trong incident |
| `NETWORK_PATH_DEGRADATION` | Có QoS incident với RTT hoặc packet loss bất thường |
| `RELAY_NOT_A_FAULT` | Đi qua TURN, đủ 5 phase, không có QoS anomaly: dùng TURN ≠ lỗi |
| `HEALTHY_CALL` | Media thiết lập, đủ 5 phase, không có QoS anomaly |

Một rule thiếu điều kiện bắt buộc vì **thiếu dữ liệu** thành HYPOTHESIS; thiếu vì **FACT nói ngược lại** thành REJECTED. Confidence bắt đầu ở High, trừ một bậc khi không có booster nào được xác minh, khi có counter-evidence, hoặc khi thiếu dữ liệu quan trọng (ví dụ thiếu metric TURN trên path relay). INFERENCE được xếp theo độ cụ thể của rule rồi theo confidence; `I1` là kết luận chính.

## 7 kịch bản

| ID | Kịch bản | Kết luận của hệ thống |
|---|---|---|
| S0 | P2P bình thường | Không có incident (`HEALTHY_CALL`) |
| S1 | Qua TURN; TURN CPU 40→95 % rồi RTT 80→310 ms, loss 12 % | `TURN_OVERLOAD_DEGRADATION`, High |
| S2 | P2P suy giảm; TURN cũng quá tải nhưng không nằm trên path | `NETWORK_PATH_DEGRADATION`, High · giả thuyết TURN bị **REJECTED** |
| S3 | Mọi candidate pair timeout | `ICE_CONNECTIVITY_FAILURE`, High · Media skipped |
| S4 | Qua TURN, chất lượng tốt | `RELAY_NOT_A_FAULT` |
| S5 | Không nhận được ANSWER | `SIGNALING_FAILURE`, High · ICE và Media skipped |
| S6 | Giống S1 nhưng collector không gửi TURN CPU | `NETWORK_PATH_DEGRADATION`, **Medium** · TURN chỉ là **HYPOTHESIS** |

## Kịch bản demo (~10 phút)

1. **S0**: 5 phase xanh, report "Không có incident". Hệ thống không bịa lỗi khi không có lỗi.
2. **S1**: phase Media vàng (degraded); chart có vùng đỏ (QoS incident) và vùng vàng (TURN CPU). Tab INFERENCES → I1 → **🔎 Truy vết**: sample RTT/loss/TURN CPU và log TURN được tô sáng. Chỉ ra FACT (mỗi dòng có refs) và INFERENCE (conclusion, `supported_by`, lý do confidence).
3. **S2**: TURN cũng quá tải nhưng path là `srflx↔srflx`. Tab HYPOTHESES / REJECTED → R1 giải thích vì sao không đổ lỗi cho TURN.
4. **S4**: đi relay nhưng không có incident.
5. **S6**: thiếu metric TURN → TURN chỉ là HYPOTHESIS, kết luận chính xuống Medium, UNKNOWN ghi rõ phần thiếu.
6. **S3 / S5**: fail sớm → các phase sau skipped, không có chart QoS.
7. **Terminal**: `python -m calldiag eval` → 7/7 PASS.

## Eval

`python -m calldiag eval` so report của từng kịch bản với `ExpectedOutcome` trong `calldiag/scenarios/expected.py`: trạng thái 5 phase, có incident hay không, khoảng incident (±5 s), rule chính, confidence, severity, rule bắt buộc / cấm, metric phải được báo thiếu, validator và khả năng truy vết. Ký hiệu: ✓ đạt · ✗ trượt · – không áp dụng. Lệnh trả exit 1 nếu có kịch bản FAIL.

## LLM summary (tùy chọn)

LLM chỉ **viết lại** engineering summary và executive summary từ FACT/INFERENCE đã có. Nó không tạo FACT, INFERENCE, confidence hay severity, và không thấy nhãn kịch bản. Summary của LLM phải qua validator; nếu trích ID không tồn tại, thêm con số không có trong đầu vào, executive summary quá 80 từ hoặc có trích dẫn, engineering summary không trích gì, thì report quay về bản template và giữ cảnh báo.

```bash
pip install -e ".[llm]"
cp .env.example .env            # điền OPENAI_API_KEY và CALLDIAG_LLM_MODEL
python -m calldiag run --scenario S1 --llm
streamlit run app/streamlit_app.py   # sidebar: bật "Dùng LLM cho summary"
```

- Hiện chỉ hỗ trợ OpenAI, đứng sau Protocol `LLMClient` (`calldiag/llm/client.py`) để thêm provider khác.
- `.env` nằm trong `.gitignore`; CLI và UI tự đọc file này lúc khởi động. Biến đã `export` trong shell được ưu tiên; `CALLDIAG_ENV_FILE=<đường dẫn>` để dùng file khác.
- Response được cache ở `out/llm_cache/` theo model + prompt + input, nên chạy lại cho cùng kết quả.
- Thiếu key hoặc model thì hệ thống vẫn chạy bằng template và ghi lý do (`W_LLM_UNAVAILABLE`).

## Nguyên tắc bất biến

- FACT chỉ được tạo trong `calldiag/pipeline/facts.py`; mọi FACT có `refs` resolve được và không chứa từ nhân quả (`BANNED_FACT_WORDS`).
- Mọi INFERENCE có `supported_by` khác rỗng, trỏ tới FACT có thật.
- Pipeline không đọc `meta.scenario_id`, `meta.title` và không rẽ nhánh theo `call_id`.
- Dữ liệu thiếu là `None`, không bao giờ thay bằng 0.
- Confidence ∈ {High, Medium, Low}; severity là trường riêng.
- Mọi ngưỡng / hằng số nằm trong `calldiag/config.py`; dữ liệu theo kịch bản nằm trong `calldiag/scenarios/`.

## Cấu trúc

```
aiops_mvp/
  calldiag/
    models.py, config.py, io.py, envfile.py, utils.py, cli.py, eval.py
    scenarios/    7 kịch bản (s0…s6), builder, data dùng chung, ExpectedOutcome
    pipeline/     timeline, phases, anomaly, correlate, facts, rules, reasoning, validator, report, render, run
    llm/          client (OpenAI + FakeLLM), summary
  app/
    streamlit_app.py   UI một trang
    charts.py          hàm vẽ Plotly (thuần, có test)
    summary_view.py    tách summary thành gạch đầu dòng + badge trích dẫn
  data/scenarios/      telemetry đã sinh S0–S6
  tests/               pytest, gồm smoke test UI bằng streamlit.testing.AppTest
  docs/MVP_PLAN.md     bài toán, phạm vi, luồng chạy chi tiết, nguyên tắc thiết kế
  .claude/skills/      skill cho Claude Code khi làm việc trong thư mục này
  CLAUDE.md            hướng dẫn cho Claude Code: invariant, quy trình, bản đồ skill
```

## Làm việc với Claude Code

`CLAUDE.md` và thư mục `.claude/skills/` là hướng dẫn riêng của dự án này cho Claude Code; Claude Code tự nhận khi bạn làm việc trong `aiops_mvp/`. Chi tiết xem `CLAUDE.md`.

| Skill | Dùng khi |
|---|---|
| `calldiag-run` | Cài đặt, chạy CLI / eval / UI, chuẩn bị demo, bật LLM summary |
| `calldiag-diagnosis-contract` | Sửa bất cứ thứ gì đụng tới FACT / INFERENCE / HYPOTHESIS / REJECTED / validator |
| `calldiag-add-rule` | Thêm hoặc sửa rule chẩn đoán, condition, cách tính confidence |
| `calldiag-add-scenario` | Thêm kịch bản telemetry mới cùng `ExpectedOutcome` |
| `calldiag-llm-summary` | Sửa prompt, provider, cache hoặc guardrail của LLM summary |

Quy trình khi đổi code: đọc `docs/MVP_PLAN.md` và skill liên quan → sửa code + test → `pytest -q` và `python -m calldiag eval` đều xanh → cập nhật `docs/MVP_PLAN.md` / README nếu luồng hoặc contract thay đổi.

Bài toán, luồng chạy từng bước và lý do thiết kế: xem [`docs/MVP_PLAN.md`](docs/MVP_PLAN.md).

## Giới hạn của MVP

- Chỉ cuộc gọi 1:1 (P2P hoặc TURN); chưa có SFU / gọi nhóm.
- Chỉ có stats phía caller (alice); stats phía bob không được thu thập.
- Telemetry synthetic, một synthetic clock chung cho mọi nguồn; chưa đọc từ storage thật (OpenSearch / Elasticsearch).
- Rule-based; chưa có ML anomaly detection hay SHAP.
