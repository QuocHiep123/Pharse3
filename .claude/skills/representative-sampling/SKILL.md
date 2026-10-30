---
name: representative-sampling
description: Selecting representative and anomalous call failure cases from large log/metric stores to build a compact, balanced benchmark for the callops diagnosis agents, plus active-learning loops that pick the most informative cases for labeling. Use when building test sets, benchmarks, golden datasets, or deciding which calls to label or review.
---

# Representative sampling & active learning

Mục tiêu: từ kho log lớn, chọn **ít ca nhưng phủ đủ kiểu lỗi** để làm benchmark cho agent (và baseline rule-based).

## Pipeline

1. **Featurize mỗi cuộc gọi** (1 vector / call_id):
   - Từ FACT/log: tập `error_code`, `media_path`, NAT type, số participant, có `QOS_ALERT` không.
   - Từ metric: p50/p95/max của rtt, jitter, loss, min MOS, tổng thời gian vượt ngưỡng, số window.
2. **Chuẩn hóa** (StandardScaler cho số, one-hot cho categorical).
3. **Phân cụm**: KMeans (k theo silhouette) hoặc HDBSCAN (tự tìm cụm + nhãn noise = ca lạ).
4. **Chọn mẫu**:
   - Mỗi cụm: lấy medoid (đại diện) + 1–2 điểm biên (xa tâm nhất).
   - Toàn bộ điểm noise / anomaly score cao → giữ lại (ca hiếm, giá trị cao).
   - Stratify theo `error_code` để lỗi hiếm không bị nuốt.
5. **Ghi benchmark**: `benchmarks/<version>/cases.jsonl` với `call_id`, `scenario`, `expected_root_cause`, `expected_fact_ids`, `cluster_id`, lý do được chọn. Version hóa, không sửa đè.

## Active learning

- Uncertainty sampling: ưu tiên ca agent cho `confidence` thấp hoặc agent ≠ rule-based.
- Disagreement: chạy 2 cấu hình (vd. 2 prompt/model) → ca bất đồng đi review người.
- Diversity: trong batch review, không lấy 2 ca cùng cụm.
- Sau mỗi vòng review → bổ sung nhãn vào benchmark version mới.

## Metric đánh giá trên benchmark

- Root-cause accuracy (top-1, top-3).
- Grounding rate: % INFERENCE qua `validate_grounding` (xem `grounded-diagnosis`).
- Hallucination rate: % câu khẳng định không truy được về FACT.
- Coverage theo cụm: đúng bao nhiêu % ở mỗi cụm (tránh chỉ giỏi lỗi phổ biến).

Gọi kèm skill global `llm-evaluation` khi thiết kế harness đánh giá.

## Quy tắc

- Seed cố định cho clustering & sampling (tái lập được).
- Không để ca trong benchmark rò sang few-shot example của prompt.
- Dữ liệu sinh từ `simulator.py` dùng được ngay; nhớ ghi rõ benchmark là synthetic.
