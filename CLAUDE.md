# callops — WebRTC Call Platform AIOps (OJT AI20K Batch 4)

PoC mô phỏng luồng cuộc gọi WebRTC → sinh log + QoS metric → chẩn đoán AIOps tách bạch **FACT vs INFERENCE**.
Đọc `README.md` để biết luồng 7 bước và cách chạy.

## Phân vai

| Người | Mảng | Thư mục dự kiến |
|---|---|---|
| **doandd** (Đặng Đỉnh Đoàn) | Data pipeline, anomaly detection, XAI (SHAP), FastAPI, OpenSearch query | `src/callops/pipeline/`, `src/callops/anomaly/`, `src/callops/api/` |
| **hiepdq** (Đặng Quốc Hiệp) | Multi-agent (LangGraph supervisor), grounded reasoning, causal check, sampling policy | `src/callops/agents/`, `src/callops/sampling/` |

Phần dùng chung (không tự ý đổi schema khi chưa báo người kia): `models.py` (`Fact`, `Inference`, `QoSSample`, `CallEvent`), `qos.py` (`THRESHOLDS`), `storage.py` (`TelemetryStore`).

## Quy chuẩn bắt buộc

- Python 3.10+, OOP, type hint đầy đủ; model dữ liệu dùng Pydantic v2 (`BaseModel`) hoặc `@dataclass(frozen=True)` cho value object.
- Mọi khẳng định chẩn đoán phải trích dẫn FACT id (`[F03]`) — xem skill `grounded-diagnosis`. `DiagnosisReport` đã validate điều này, đừng bỏ validator.
- Test: `pytest`, mỗi tính năng mới có unit test; test không được phụ thuộc Docker/LLM thật (dùng `--backend memory`, fake LLM).
- Commit: Conventional Commits, scope theo module — `feat(agents): ...`, `fix(anomaly): ...`, `test(api): ...`.
- Branch: `feat/<mô-tả>` từ `main`, PR review chéo giữa 2 người.

## Lệnh hay dùng

```powershell
.venv\Scripts\python -m pytest                   # test
.venv\Scripts\callops --backend memory run-all   # chạy không cần Docker
docker compose up -d --wait                      # Redis + OpenSearch
docker compose --profile ui up -d                # + OpenSearch Dashboards :5601
```

## Workflow với sub-agent

Custom agent trong `.claude/agents/`:

1. **`task-planner`** (Opus, effort high): đọc yêu cầu + code, suy nghĩ thiết kế, chia task → ghi `docs/plans/YYYY-MM-DD-<slug>.md`.
2. Người dùng duyệt plan / trả lời câu hỏi mở.
3. **`task-coder`** (Sonnet): mỗi lần làm 1 task (truyền đường dẫn plan + task id), TDD, chạy pytest, không commit. Task `parallel-safe: yes` có thể chạy song song nhiều coder.
4. Review diff (`code-review`) → người dùng commit.

Ví dụ: "Dùng task-planner lập kế hoạch task 2: Supervisor + Metric/Log Agent" → "Dùng task-coder làm T1 trong docs/plans/...".

## Bản đồ skill

Project skills (`.claude/skills/`, dùng chung qua git):

| Skill | Dùng khi | Ai |
|---|---|---|
| `callops-domain` | Bất cứ việc gì đụng tới call flow, ICE/STUN/TURN/SFU, ngưỡng QoS, MOS | Cả hai |
| `grounded-diagnosis` | Viết rule/prompt/agent sinh INFERENCE, kiểm định giả thuyết nhân quả | Cả hai (Hiệp chính) |
| `langgraph-supervisor` | Xây Supervisor + Metric Agent + Log Agent bằng LangGraph | Hiệp |
| `representative-sampling` | Chọn mẫu ca lỗi đại diện, dựng benchmark, active learning | Hiệp |
| `timeseries-anomaly-xai` | Resample/rolling, Z-score, EWMA, tương quan, SHAP | Đoàn |
| `opensearch-query` | Viết query DSL vào `callops-events` / `callops-qos` | Đoàn |
| `fastapi-service` | Expose pipeline/chẩn đoán qua REST API async | Đoàn |

Global skills nên gọi kèm:

- Quy trình: `superpowers:brainstorming` (trước khi thiết kế tính năng mới) → `superpowers:writing-plans` → `superpowers:test-driven-development` → `superpowers:verification-before-completion`. Bug: `superpowers:systematic-debugging`.
- LangGraph/LLM (Hiệp): `langgraph-fundamentals`, `langchain-fundamentals`, `prompt-engineering-patterns`, `llm-evaluation`, `claude-api` (nếu dùng Claude làm LLM).
- Data (Đoàn): `python-performance-optimization`, `dataviz` (vẽ biểu đồ metric / SHAP).
- Git: `git-commit` (Conventional Commits), `gh-cli`, `code-review` trước khi merge.
- Tài liệu/sơ đồ cho mentor: `diagram-design`.

Plugin bật ở project (`.claude/settings.json`, tự có khi clone):

| Việc | Plugin / lệnh |
|---|---|
| Hiểu codebase | `understand-anything` (knowledge graph), `feature-dev` (explorer/architect agents) |
| Debug | `superpowers:systematic-debugging`; type check: `pyright-lsp` (cần `npm i -g pyright`) |
| Review | `pr-review-toolkit` (review PR theo nhiều góc: test, error handling, type design), `code-review`, `security-guidance` |
| Refactor | `code-simplifier`, `simplify` |
| Git | `commit-commands` (`/commit`, `/commit-push-pr`) |
| Docs thư viện mới nhất | `context7` (LangGraph, FastAPI, OpenSearch, SHAP...) |
| Giữ CLAUDE.md gọn, đúng | `claude-md-management` |
