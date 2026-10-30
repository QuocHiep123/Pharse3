---
name: opensearch-query
description: Querying callops telemetry in OpenSearch/Elasticsearch - index layout (callops-events, callops-qos), query DSL for time-range filters, term filters on call_id and error_code, terms/date_histogram/percentiles aggregations, and the Python client conventions used in storage.py. Use when writing search/aggregation code, dashboards, or debugging indexed data.
---

# OpenSearch query cho callops

Hạ tầng: `docker-compose.yml` (OpenSearch 2.13, security tắt, port 9200; Dashboards :5601 với `--profile ui`).
Code hiện có: `DockerStore` trong `storage.py` gọi REST qua `httpx` (bulk index, `_refresh`, `term` theo `call_id`).

## Index

| Index | Document | Field chính |
|---|---|---|
| `callops-events` | `CallEvent` | `ts` (date), `call_id` (keyword), `level`, `event`, `state`, `error_code`, `message`, `detail.*` |
| `callops-qos` | `QoSSample` | `ts`, `call_id`, `participant_id`, `t_s`, `rtt_ms`, `jitter_ms`, `packet_loss_pct`, `mos`, `video_freeze_count`, `concealment_pct` |

Mapping hiện chỉ khai báo `ts` và `call_id`; field khác là dynamic (string → `text` + `.keyword`). Khi aggregation theo chuỗi dùng `error_code.keyword`, `event.keyword`, `participant_id.keyword` — hoặc bổ sung mapping explicit trong `DockerStore.__init__`.

## Mẫu query

Range theo thời gian + lọc lỗi:
```json
{"query": {"bool": {"filter": [
  {"range": {"ts": {"gte": "now-15m", "lte": "now"}}},
  {"exists": {"field": "error_code"}}
]}}, "sort": [{"ts": "asc"}]}
```

Đếm theo mã lỗi:
```json
{"size": 0, "aggs": {"by_error": {"terms": {"field": "error_code.keyword", "size": 20}}}}
```

Metric theo thời gian cho 1 cuộc gọi:
```json
{"size": 0, "query": {"term": {"call_id": "<id>"}},
 "aggs": {"per_10s": {"date_histogram": {"field": "ts", "fixed_interval": "10s"},
   "aggs": {"rtt_p95": {"percentiles": {"field": "rtt_ms", "percents": [95]}},
            "loss_max": {"max": {"field": "packet_loss_pct"}},
            "mos_min": {"min": {"field": "mos"}}}}}}
```

Cuộc gọi có MOS dưới ngưỡng critical:
```json
{"size": 0, "query": {"range": {"mos": {"lte": 3.1}}},
 "aggs": {"calls": {"terms": {"field": "call_id", "size": 100}}}}
```

## Quy tắc

- Dùng `filter` (không tính score) cho mọi điều kiện lọc.
- Đọc sau khi ghi: gọi `store.flush()` (đã `_refresh`) trước khi search.
- `size: 10000` là trần mặc định; nhiều hơn thì dùng `search_after` + `sort` theo `ts`.
- Ngưỡng lấy từ `THRESHOLDS`, không hard-code trong query builder.
- Logic query đặt sau interface `TelemetryStore` để `InMemoryStore` vẫn chạy được trong test; method mới phải có bản in-memory tương đương.
- Kiểm tra nhanh: `curl "localhost:9200/callops-events/_search?q=error_code:ICE_FAILED&pretty"`.
