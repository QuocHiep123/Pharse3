---
name: calldiag-add-rule
description: Thêm hoặc sửa rule chẩn đoán của CallDiag - RuleSpec trong pipeline/rules.py, condition trả TRUE/FALSE/UNKNOWN từ FactStore, booster/counter/missing penalty, cách reasoning.py quyết định INFERENCE / HYPOTHESIS / REJECTED và tính confidence. Dùng khi đổi logic kết luận, thêm root cause mới, hoặc sửa câu conclusion / rejection.
---

# Thêm / sửa rule

Đọc trước: mục 5 bước [5] trong `docs/MVP_PLAN.md` và skill `calldiag-diagnosis-contract`.

## Rule là dữ liệu

`RULES` trong `calldiag/pipeline/rules.py` là tuple `RuleSpec`:

```python
RuleSpec(
    rule_id, title, specificity,          # specificity lấy từ config.RULE_SPECIFICITY[rule_id]
    preconditions,                        # tất cả phải TRUE, nếu không rule bị bỏ qua
    required,                             # FALSE → REJECTED, UNKNOWN → HYPOTHESIS, TRUE hết → INFERENCE
    conclusion, hypothesis_statement,     # Callable[[Ctx], str]
    boosters=(), counters=(), missing_penalties=(),
    alternatives=(), unknowns=(), next_checks=..., rejection_reason=None,
)
```

## Condition

Condition là `Callable[[Ctx], ConditionResult]`, **chỉ đọc FACT** qua `ctx.facts.query(FactKind..., **filters)` hoặc `ctx.changes(...)` (METRIC_CHANGE thuộc incident đang xét). Trả kết quả bằng `_condition(name, description, state, facts, note)` để `fact_ids` được gắn vào.

- `TRUE`: có FACT chứng minh.
- `FALSE`: có FACT chứng minh điều ngược lại (ví dụ METRIC_LEVEL bình thường trong incident, path không qua TURN).
- `UNKNOWN`: thiếu FACT hoặc có FACT `missing_data`. Không được coi thiếu là FALSE.

Condition về resource phải giới hạn theo incident đang xét (`ctx.focus_ref`) và theo TURN server trên selected path, không trộn evidence của server hay call khác.

## Reasoning (`pipeline/reasoning.py`)

1. Precondition không TRUE hết → bỏ qua rule.
2. Có required FALSE → REJECTED (`rejection_reason` nếu có, không thì nối các condition FALSE).
3. Có required UNKNOWN → HYPOTHESIS với `missing_evidence` và `how_to_verify = next_checks`.
4. Còn lại → INFERENCE. Confidence bắt đầu ở High, trừ một bậc nếu rule có booster mà không booster nào TRUE, một bậc cho mỗi counter TRUE, một bậc cho mỗi missing penalty TRUE; thấp nhất là Low. Mọi lần trừ đều ghi vào `confidence_reasons`.
5. INFERENCE xếp theo specificity giảm dần, rồi confidence, rồi thứ tự trong `RULES`; `I1` là primary.

## Checklist khi thêm rule

- [ ] Thêm `RuleSpec` vào `RULES`, đặt đúng thứ tự.
- [ ] Thêm `rule_id` vào `config.RULE_SPECIFICITY` và `config.REPORT_HEADLINES` (headline có thể dùng `{window}`).
- [ ] Ngưỡng mới để trong `config.py`, không hard-code trong rule.
- [ ] Conclusion nói "có khả năng liên quan", không khẳng định nhân quả vượt evidence; câu REJECTED nêu FACT phản chứng.
- [ ] Test trong `tests/test_reasoning.py`: trường hợp TRUE, FALSE (REJECTED) và UNKNOWN (HYPOTHESIS), kiểm `supported_by` và confidence.
- [ ] Cập nhật `ExpectedOutcome` liên quan (`required_*` / `forbidden_inferences`) trong `calldiag/scenarios/expected.py`.
- [ ] Bảng rule trong `README.md` và `docs/MVP_PLAN.md`.
- [ ] `pytest -q` và `python -m calldiag eval` đều xanh.
