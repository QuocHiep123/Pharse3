---
name: grounded-diagnosis
description: FACT vs INFERENCE contract and anti-hallucination rules for callops AIOps diagnosis - grounded generation with mandatory evidence citations, LLM prompt templates that force [F01]-style citations, post-generation citation validation, and causal hypothesis testing by cross-checking log event timelines against metric windows. Use when writing diagnosis rules, LLM prompts, agent nodes that output hypotheses, or reviewing a DiagnosisReport.
---

# Grounded diagnosis: FACT vs INFERENCE

Contract đã có trong code — giữ nguyên, mở rộng chứ không nới lỏng:
- `Fact` (`models.py`): có `id`, `ts`, `source` ("log" | "metric"), `evidence` (dòng log gốc / giá trị metric, không rỗng).
- `Inference`: `reasoning` không rỗng, `derived_from` ≥ 1 FACT id, `confidence` ∈ [0, 1].
- `DiagnosisReport._inferences_must_cite_existing_facts` từ chối INFERENCE trích FACT không tồn tại.
- Rule-based baseline: `InferenceEngine` trong `diagnosis.py`. Agent LLM phải **thắng hoặc bằng** baseline này trên benchmark, không được tệ hơn.

## Quy tắc

1. **FACT chỉ đến từ dữ liệu**: trích xuất bằng code (`FactExtractor`), không bao giờ để LLM tạo FACT.
2. **Mọi câu khẳng định trong INFERENCE phải kèm citation** `[F03]` (FACT id). Khi cần trỏ thẳng nguồn gốc: `[log:<ts>|<event>]` hoặc `[metric:<participant>@<ts>]`, nhưng vẫn phải map được về FACT id.
3. **Không có FACT → không có INFERENCE**. Thiếu dữ kiện thì trả "INSUFFICIENT_EVIDENCE" kèm FACT còn thiếu, không đoán.
4. **Confidence có căn cứ**: tăng khi nhiều FACT độc lập (log + metric) cùng chỉ một hướng; giảm khi chỉ có 1 nguồn.

## Prompt template cho LLM

```text
Bạn là kỹ sư chẩn đoán cuộc gọi WebRTC. Chỉ dùng các FACT dưới đây.
FACTS:
[F01] 2026-10-30T10:00:01Z log ICE_FAILED nat=symmetric ...
[F02] ...
Yêu cầu:
- Mỗi giả thuyết: hypothesis, reasoning, derived_from (list FACT id), confidence 0..1.
- Mỗi câu trong reasoning phải có ít nhất một [Fxx].
- Không nhắc tới thông tin không có trong FACTS. Nếu không đủ căn cứ, trả về INSUFFICIENT_EVIDENCE.
Trả về JSON đúng schema Inference.
```

Dùng structured output (Pydantic `Inference`) thay vì parse text tự do.

## Validate sau khi sinh (bắt buộc)

```python
CITE = re.compile(r"\[(F\d+)\]")

def validate_grounding(inf: Inference, facts: dict[str, Fact]) -> list[str]:
    errors: list[str] = []
    cited = set(CITE.findall(inf.reasoning))
    if not cited:
        errors.append(f"{inf.id}: reasoning không có citation")
    if unknown := (cited | set(inf.derived_from)) - facts.keys():
        errors.append(f"{inf.id}: FACT không tồn tại {sorted(unknown)}")
    if cited - set(inf.derived_from):
        errors.append(f"{inf.id}: cite trong reasoning nhưng thiếu ở derived_from")
    return errors
```

Lỗi → trả về cho agent sửa (tối đa N lần) hoặc loại INFERENCE đó; không âm thầm cho qua.

## Kiểm định giả thuyết nhân quả

Trước khi chấp nhận "A gây ra B", kiểm tra trên FACT:

| Check | Cách làm |
|---|---|
| Thứ tự thời gian | Sự kiện nguyên nhân (log) xảy ra **trước hoặc trùng** cửa sổ metric xấu (`Window.overlaps`) |
| Đồng biến | Metric nguyên nhân và triệu chứng cùng xấu trong cửa sổ; ngoài cửa sổ thì bình thường |
| Phạm vi | Chỉ 1 participant xấu → nghi uplink riêng; mọi participant → nghi server/TURN/SFU |
| Giả thuyết đối chứng | Liệt kê ít nhất 1 nguyên nhân thay thế và FACT nào loại trừ nó |
| Tương quan ≠ nhân quả | Correlation (từ `timeseries-anomaly-xai`) chỉ nâng confidence, không tự nó là kết luận |

Ghi kết quả từng check vào `reasoning` kèm citation.
