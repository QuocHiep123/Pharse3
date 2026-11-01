# Gradio Demo UI — Design

Branch: `feat/webrtc-call-aiops-poc` (không merge `main`).

## Mục tiêu
Demo Gradio giúp hiểu *vì sao cuộc gọi WebRTC lỗi và cách sửa*: xem từng bước call flow (animation),
QoS theo thời gian, và mỗi INFERENCE dựa trên FACT nào. Chạy hoàn toàn với `InMemoryStore`, không cần Docker/LLM.

## Phạm vi (đã duyệt)
Tab: Run/Playground · Call Flow Animation · QoS Timeline · Diagnosis (FACT vs INFERENCE) · Logs/Export · Upload/Re-analyze.
Chế độ "Giải thích cho người mới" (tiếng Việt) bật mặc định.

## Kiến trúc
Package mới `src/callops/ui/`; KHÔNG sửa `models.py`, `qos.py`, `storage.py`.

| File | Trách nhiệm |
|---|---|
| `runner.py` | `RunResult` (frozen dataclass: events, samples, report, facts, scenario). `run_scenario(Scenario, seed)`, `reanalyze(events, samples)` dùng `InMemoryStore` + `FactExtractor`/`InferenceEngine`/`DiagnosisService` |
| `loaders.py` | `load_jsonl(path)`, `load_qos_csv(path)`, `load_scenario(path)` (YAML/JSON → `Scenario`); lỗi → `UiInputError` có thông điệp rõ |
| `flow.py` | `build_timeline(events)` → danh sách bước (`FlowStep`: t, step_no, actor→actor, title, explain_vi, log_ref); `render_flow_svg(steps, upto)` SVG + CSS animation |
| `charts.py` | `qos_figure(samples, thresholds, windows)` Plotly: RTT/jitter/loss/MOS, vạch ngưỡng, vùng sự cố |
| `explain.py` | Từ điển giải thích ICE/STUN/TURN/SFU/NAT/SDP… (tiếng Việt) |
| `app.py` | `build_app()` Gradio Blocks; thanh trượt thời gian đồng bộ flow + chart |
| `cli.py` (sửa nhỏ) | lệnh `callops ui [--port]` |

`pyproject.toml`: extra `ui = ["gradio>=4", "plotly>=5", "pyyaml>=6"]`.

## Luồng dữ liệu
Scenario (chọn/chỉnh/upload) → `CallSimulator` → store → events+samples → `FactExtractor` → FACT → `InferenceEngine` → INFERENCE.
Upload JSONL/CSV bỏ qua simulator, vào thẳng `reanalyze`. Mọi tab render từ cùng một `RunResult`.

## Diagnosis tab
FACT trái, INFERENCE phải; chọn INFERENCE → highlight FACT id trích dẫn + tên rule; mục "rule không khớp và lý do".

## Lỗi
File sai định dạng/thiếu cột → `UiInputError` → hiển thị cảnh báo trong UI, không crash. Không có sự kiện → thông báo rỗng.

## Test
pytest, không cần Gradio server: `runner` (mọi scenario có sẵn chạy ra report hợp lệ), `loaders` (hợp lệ + lỗi),
`flow` (số bước, thứ tự, SVG chứa actor), `charts` (figure có đủ trace), `app` smoke (`build_app()` không lỗi).
Kiểm UI thật bằng chụp màn hình (browser-automation).

## Ngoài phạm vi
Đổi schema dùng chung, LLM/agents, Docker backend trong UI, auth/deploy.
