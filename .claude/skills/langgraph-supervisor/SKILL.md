---
name: langgraph-supervisor
description: Architecture and conventions for the callops multi-agent diagnosis system built with LangGraph - Supervisor pattern routing to Metric Agent and Log Agent sub-agents, typed shared state, conditional edges, checkpointer memory, a grounding-validation node, and testing graphs with fake LLMs. Use when designing or writing any code under src/callops/agents/. Load the global langgraph-fundamentals skill alongside for API details.
---

# LangGraph supervisor cho callops

Gọi kèm skill global `langgraph-fundamentals` (API StateGraph/Command/Send) và `grounded-diagnosis` (contract output).

## Kiến trúc mục tiêu

```
START -> extract_facts (code, không LLM)
      -> supervisor ──(conditional)──> metric_agent ─┐
                    ├────────────────> log_agent ────┤ -> supervisor (lặp tới khi đủ)
                    └──> synthesize -> validate_grounding ──fail──> synthesize (retry ≤ 2)
                                                        └─ok──> END (DiagnosisReport)
```

| Node | Vào | Ra | LLM? |
|---|---|---|---|
| `extract_facts` | events, samples từ `TelemetryStore` | `facts` | Không — dùng `FactExtractor` |
| `supervisor` | facts, findings đã có | `next` ∈ {metric_agent, log_agent, synthesize} | Có (hoặc rule) |
| `metric_agent` | FACT source=metric, windows, anomaly scores (của Đoàn) | `findings` | Có |
| `log_agent` | FACT source=log, timeline error_code | `findings` | Có |
| `synthesize` | findings | `inferences` | Có |
| `validate_grounding` | inferences, facts | errors / report | Không |

## State

```python
class DiagnosisState(TypedDict):
    call_id: str
    facts: list[Fact]
    findings: Annotated[list[Finding], operator.add]  # sub-agents append
    inferences: list[Inference]
    next: Literal["metric_agent", "log_agent", "synthesize"]
    grounding_errors: list[str]
    retries: int
```

- State giữ dữ liệu thô (FACT), format prompt bên trong node.
- Sub-agent chỉ nhìn phần FACT của mình (giảm nhiễu, dễ kiểm tra).
- Mỗi `Finding` cũng bắt buộc `derived_from` FACT id — cùng luật với `Inference`.

## Quy ước code

- `src/callops/agents/state.py`, `nodes/*.py`, `graph.py` (`build_graph(llm) -> CompiledGraph`).
- LLM được **inject** qua tham số, không khởi tạo cứng trong node → test dùng fake LLM.
- Supervisor có giới hạn bước (`recursion_limit` hoặc đếm trong state) để không lặp vô hạn.
- Memory phiên: `MemorySaver` cho dev, `thread_id = call_id`.
- Rule-based `InferenceEngine` là fallback khi LLM lỗi/timeout.

## Test

- Unit test từng node với state giả.
- Test graph với fake LLM (`langchain_core.language_models.fake_chat_models.GenericFakeChatModel`) trả output cố định → kiểm tra routing và validate_grounding bắt được citation sai.
- So sánh với baseline: chạy các scenario trong `scenarios.py`, agent phải ra nguyên nhân gốc đúng như rule-based.

## Dependency (thêm khi bắt đầu code)

`langgraph`, `langchain-core` (+ provider LLM đã chọn) vào optional group `agents` trong `pyproject.toml`.
