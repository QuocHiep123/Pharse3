# Data Contract v0.1.0 — TURN Selector Intelligence

- **Ngày:** 2026-11-04 · **Soạn:** Hiệp · **Duyệt:** Hiệp + Đoàn (bắt buộc cả hai)
- **Trạng thái:** DRAFT. Chốt trước khi hết W1 (10/11)
- **Spec gốc:** `docs/superpowers/specs/2026-11-04-turn-intelligence-design.md`
- **Dạng máy đọc** (sinh ra từ tài liệu này trong lúc implement): `contracts/schemas/*.json` (JSON Schema 2020-12), `contracts/models.py` (Pydantic v2), `contracts/ddl/*.sql` (PostgreSQL)

> Tài liệu này là **nguồn sự thật**. Nếu code và tài liệu khác nhau, sửa code, hoặc mở PR để sửa tài liệu và tăng version.

---

## 0. Đọc nhanh

```
                     ┌──────────── SelectRequest / SelectResponse (§10, API Đoàn) ────────────┐
                     ▼                                                                        │
call_session ──1:N── selector_decision ──1:N── turn_allocation                                │
     │                    (per side, per phase)                                               │
     ├──1:N── ice_attempt ──1:N── path_leg_measurement (method=inband|alloc)                  │
     ├──1:N── call_stats_5s                                                                   │
     └──1:1── call_outcome                                                                    │
                                                                                              │
path_leg_measurement (method=mesh_probe|idle_probe, call_id = null)                           │
turn_health_1m · service_health_1m                                                            │
                                                                                              │
dim_turn · dim_asn · dim_user                     ── pipeline ──► feature store (§9) ─────────┘
truth_* · incident_truth · dirt_log  (CHỈ SIMULATOR, ẨN)
```

| Lớp | Bảng | Ai sinh (producer) | Ai đọc (consumer) |
|---|---|---|---|
| Dimension | `dim_turn`, `dim_asn`, `dim_user` | Hạ tầng / simulator | Pipeline, Đoàn |
| Event (raw) | `call_session`, `selector_decision`, `turn_allocation`, `ice_attempt`, `path_leg_measurement`, `call_stats_5s`, `call_outcome`, `turn_health_1m`, `service_health_1m` | SDK, Signaling, Selector, TURN, probe agent (trên sim là simulator đóng vai) | Pipeline (Hiệp) |
| Feature store | `feat_leg_stats`, `feat_turn_turn`, `feat_turn_health`, `feat_path_history`, `feat_callee_prior` | Pipeline (Hiệp) | Selector (Đoàn), dashboard |
| Ẩn | `truth_leg_5m`, `incident_truth`, `dirt_log` | Simulator | **Chỉ** `eval/` |

---

## 1. Quy ước chung

| Mục | Quy ước |
|---|---|
| Thời gian | UTC, ISO-8601, độ chính xác ms (`2026-11-12T13:45:01.123Z`). Postgres dùng `timestamptz` |
| Partition | Theo `dt` = ngày (UTC) của `event_ts`. Riêng bảng giờ VN dùng cột phái sinh `local_hour_vn` (UTC+7) |
| ID | `event_id`, `decision_id`: UUIDv7 (sắp xếp được theo thời gian). `call_id`: UUIDv7 do Signaling cấp |
| Đơn vị | Thời gian và độ trễ: **ms** (float). Loss: **%** 0–100. Jitter: **ms**. Bitrate: **kbps**. Tỉ lệ: 0–1 |
| Quốc gia | ISO-3166-1 alpha-2 (`VN`, `SG`, `TW`) |
| Thành phố | Mã IATA của thành phố gần nhất (`HAN`, `SGN`, `DAD`, `TPE`, `TYO`, `FRA`) |
| Vùng VN | `north`, `central`, `south`; `null` nếu không ở VN |
| Không biết | Enum dùng giá trị **`unknown`** tường minh. `null` chỉ có nghĩa "không áp dụng" (ví dụ `vn_region` của user Nhật) |
| Thiếu số đo | **Không điền 0, không điền trung bình.** Để `null` và ghi lý do vào `*_missing_reason` nếu có |
| Tên cột | `snake_case`, tiếng Anh |
| Privacy | `user_hash` = HMAC-SHA256(user_id, salt), cắt 16 hex. Không lưu IP thô. Geo chỉ tới cấp thành phố |

### 1.1 Cột chung cho mọi bảng event

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `event_id` | uuid | không | Duy nhất toàn hệ thống. Dùng để dedup |
| `contract_version` | text | không | `"0.1.0"` |
| `data_source` | enum | không | `synthetic` · `lab_zenodo` · `public_reference` · `production` |
| `producer` | enum | không | `client_sdk` · `signaling` · `selector` · `turn_server` · `probe_agent` · `simulator` |
| `event_ts` | timestamptz | không | Lúc sự kiện xảy ra, **theo đồng hồ của producer** |
| `ingest_ts` | timestamptz | không | Lúc collector nhận. `ingest_ts − event_ts` dùng để đo trễ và lệch đồng hồ |
| `sim_run_id` | text | có | Bắt buộc khi `data_source=synthetic` |
| `dt` | date | không | Partition key, suy ra từ `event_ts` |

---

## 2. Enum dùng chung

| Enum | Giá trị |
|---|---|
| `side` | `caller`, `callee` |
| `network_type` | `wifi`, `4g`, `5g`, `ethernet`, `unknown` |
| `info_level` | `full` (biết cả hai bên), `caller_only`, `country_only` (chỉ biết quốc gia của bên kia), `none` |
| `decision_phase` | `initial`, `refined`, `restart` |
| `decision_mode` | `live` (quyết định này được dùng thật), `shadow` (chỉ ghi log để so sánh) |
| `decision_source` | `api`, `static_fallback` (client không gọi được API nên dùng list tĩnh), `cache` |
| `transport` | `udp`, `tcp`, `tls` |
| `leg_type` | `user_turn`, `turn_turn` |
| `direction` | `forward` (theo chiều A→B: user→TURN của caller, TA→TB, TB→user callee), `reverse` |
| `measure_method` | `inband` (trong lúc media chạy), `alloc` (RTT lúc allocate), `mesh_probe` (TURN↔TURN), `idle_probe` (SDK probe lúc app rảnh) |
| `path_type` | `relay_relay` (TA và TB khác nhau), `relay_same` (TA = TB), `relay_direct` (một bên relay, một bên trực tiếp), `p2p_host`, `p2p_srflx` |
| `ice_trigger` | `initial`, `fallback`, `restart_network_change`, `restart_failure` |
| `ice_state` | `connected`, `failed`, `timeout`, `cancelled` |
| `end_reason` | `normal_hangup`, `not_answered`, `rejected`, `cancelled_by_caller`, `ice_failed`, `dropped_network`, `dropped_turn`, `app_crash`, `unknown` |
| `pair_group` | `VN_VN`, `VN_INTL`, `INTL_INTL` |
| `health_status` | `healthy`, `degraded`, `overloaded`, `down`, `maintenance` |
| `alloc_error` | `none`, `timeout`, `unauthorized_401`, `forbidden_403`, `quota_486`, `capacity_508`, `unreachable`, `other` |

---

## 3. Dimension

### 3.1 `dim_turn` (SCD2: topology thay đổi thì thêm dòng mới, không sửa dòng cũ)

| Cột | Kiểu | Null | Mô tả / ví dụ |
|---|---|---|---|
| `turn_id` | text | không | `VN-SGN-VTL-01`, `SG-SIN-AWS-02`. Quy tắc: `<country>-<city>-<host>-<nn>` |
| `hostname` | text | không | FQDN |
| `country` | char(2) | không | |
| `vn_region` | enum | có | Chỉ khi `country = VN` |
| `city` | text | không | IATA |
| `lat`, `lon` | float | không | |
| `host_isp` | text | không | `viettel`, `vnpt`, `fpt`, `aws`, `gcp`, … |
| `host_asn` | int | không | |
| `capacity_alloc` | int | không | Số allocation đồng thời tối đa |
| `transports` | text[] | không | `{udp,tcp,tls}` |
| `status` | enum | không | `active`, `maintenance`, `retired` |
| `valid_from`, `valid_to` | timestamptz | `valid_to` có | SCD2 |

### 3.2 `dim_asn`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `asn` | int (PK) | 7552, 45899, 18403… |
| `isp` | text | `viettel`, `vnpt`, `fpt`, `singtel`, `chunghwa`… |
| `country` | char(2) | |
| `access_kind` | enum | `fixed`, `mobile`, `mixed` |

### 3.3 `dim_user`

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `user_hash` | text (PK) | không | |
| `home_country`, `home_vn_region`, `home_city` | | `home_vn_region` có | Nơi "thường trú". Vị trí của từng cuộc gọi nằm trong `ctx` của decision |
| `home_isp`, `home_asn` | | không | |
| `primary_network` | enum `network_type` | không | |
| `cohort` | enum | không | `normal`, `cold_start` (sim cố ý cho ít dữ liệu) |
| `created_at` | timestamptz | không | |

---

## 4. Object con: `ctx` (context của một bên tại thời điểm quyết định)

Nhúng trong `selector_decision` và `call_outcome` dưới dạng JSONB. Khi đổ vào Postgres thì làm phẳng với prefix `self_` hoặc `peer_`.

| Field | Kiểu | Mô tả |
|---|---|---|
| `user_hash` | text / null | null nếu bên kia chưa biết (gọi mù) |
| `country` | char(2) / `"unknown"` | |
| `vn_region` | enum / null / `"unknown"` | |
| `city` | text / `"unknown"` | |
| `isp`, `asn` | text, int / `"unknown"`, null | |
| `network_type` | enum | |
| `geo_source` | enum | `ip_geo`, `sdk_claimed`, `both` |
| `geo_mismatch` | bool | Vị trí SDK báo khác vị trí suy ra từ IP (VPN, roaming) |
| `segment_key` | text | Do pipeline hoặc selector chuẩn hóa: `VN|south|7552|4g` (§9.0) |

---

## 5. Event: luồng cuộc gọi

### 5.1 `call_session` (Signaling tạo khi A bấm gọi)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id` | uuid (PK) | không | |
| `caller_hash`, `callee_hash` | text | không | Signaling biết cả hai user_hash, nhưng chưa chắc biết vị trí của B |
| `initiated_ts` | timestamptz | không | t0 |
| `media_kind` | enum | không | `audio`, `video` |
| `scenario_tag` | text | có | Chỉ có trên sim: `S01_hcm_vtl_hcm_vtl`… (§13) |

### 5.2 `selector_decision` (**một dòng cho mỗi (decision_id, side)**)

Một request tới Selector sinh **1 `decision_id`** và tối đa 2 dòng, mỗi bên một dòng. Gọi mù ở pha `initial` thì chỉ có dòng `caller`.

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `decision_id` | uuid | không | Chung cho cả hai bên trong một request |
| `call_id` | uuid | không | |
| `side` | enum | không | |
| `phase` | enum `decision_phase` | không | |
| `request_ts`, `response_ts` | timestamptz | `response_ts` có | null nếu API lỗi |
| `api_latency_ms` | float | có | |
| `policy_version` | text | không | `geo_baseline@0.1`, `smart@0.3.1` |
| `decision_mode` | enum | không | |
| `decision_source` | enum | không | |
| `info_level` | enum | không | |
| `self_ctx` | ctx | không | |
| `peer_ctx` | ctx | không | Các field chưa biết để `unknown` |
| `k` | int | không | Số candidate trả về (mặc định 4) |
| `candidates` | array[Candidate] | không | Đúng `k` phần tử, sắp theo `rank` (§5.2.1) |
| `filtered_out` | array[{turn_id, reason}] | không | TURN bị health filter loại. `reason`: `down`, `overloaded`, `degraded`, `maintenance`, `policy` |
| `chosen_rank` | int | không | Rank mà client **được yêu cầu** thử trước. Thường là 1; khi explore thì là 2–4 |
| `is_exploration` | bool | không | |
| `exploration_epsilon` | float | không | ε lúc quyết định (0 nếu không explore) |
| `confidence` | float 0–1 | không | |
| `confidence_level` | enum | không | `high`, `medium`, `low` |
| `fallback_reason` | text | có | Lý do dùng fallback ở cấp thuật toán, ví dụ `no_history_backoff_country` |
| `feature_snapshot_id`, `health_snapshot_id` | text | không | Snapshot đã dùng. **Bắt buộc**, phục vụ point-in-time |
| `error_code` | text | có | |

#### 5.2.1 `Candidate`

| Field | Kiểu | Mô tả |
|---|---|---|
| `rank` | int 1..k | |
| `turn_id` | text | |
| `score` | float | Càng **cao** càng tốt. Thang đo do Đoàn định nghĩa, chỉ dùng để so trong cùng một decision |
| `score_components` | map<text, float> | Ví dụ `{geo: .., isp: .., health: .., history: ..}`. Dashboard dùng cho Decision Trace |
| `est_leg_ms` | float / null | Ước lượng độ trễ một chiều của chặng user→TURN |
| `est_path_ms` | float / null | Ước lượng cả đường (nếu đã biết bên kia) |
| `reason_codes` | text[] | `same_isp`, `same_region`, `nearest_intl`, `history_good`, `cold_start_prior`… |
| `propensity` | float 0–1 | **P(policy chọn candidate này làm `chosen_rank`)**. Tổng propensity của k candidate = 1. Policy deterministic: rank 1 = 1.0, còn lại 0.0 |

### 5.3 `turn_allocation` (một dòng cho mỗi lần allocate)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `event_id` | uuid | không | |
| `call_id`, `decision_id` | uuid | không | |
| `side` | enum | không | |
| `turn_id` | text | không | |
| `rank` | int | không | Rank của TURN này trong decision |
| `transport` | enum | không | |
| `request_ts` | timestamptz | không | |
| `alloc_ms` | float | có | null nếu timeout |
| `success` | bool | không | |
| `error_code` | enum `alloc_error` | không | |
| `is_preallocation` | bool | không | true: allocate trước để dự phòng hoặc đo (§5.1 spec) |
| `released_ts` | timestamptz | có | |
| `release_reason` | enum | có | `not_needed`, `call_end`, `kept_for_failover`, `expired` |

### 5.4 `ice_attempt` (một dòng cho mỗi lần ICE thử: lần đầu, mỗi lần fallback, mỗi lần restart)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `event_id` | uuid | không | |
| `call_id` | uuid | không | |
| `attempt_seq` | int | không | 1, 2, 3… |
| `trigger` | enum `ice_trigger` | không | |
| `decision_id` | uuid | không | Decision được dùng cho lần thử này |
| `network_epoch` | int | không | Bắt đầu từ 0, tăng mỗi lần đổi mạng |
| `start_ts`, `end_ts` | timestamptz | `end_ts` có | |
| `state` | enum `ice_state` | không | |
| `turn_used` | bool | không | false nếu P2P |
| `path_type` | enum | có | null nếu thất bại |
| `relay_turn_caller`, `relay_turn_callee` | text | có | TURN mà **ICE thực sự dùng** |
| `rank_caller`, `rank_callee` | int | có | Rank của chính các TURN đó trong decision. null nếu TURN không nằm trong list (vi phạm I4) |
| `transport` | enum | có | |
| `cst_ms` | float | có | Từ lúc B bắt máy (hoặc lúc bắt đầu restart) tới `connected` |
| `ttfm_ms` | float | có | Từ `connected` tới gói media đầu tiên |
| `failure_reason` | text | có | |

### 5.5 `path_leg_measurement` (**bảng trung tâm** cho phân rã chặng)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `event_id` | uuid | không | |
| `measured_ts` | timestamptz | không | Cuối cửa sổ đo |
| `window_s` | float | không | 5 với `inband`; 0 với một lần đo đơn (`alloc`, probe) |
| `method` | enum `measure_method` | không | |
| `call_id` | uuid | có | null với `mesh_probe` và `idle_probe` |
| `attempt_seq`, `network_epoch` | int | có | Chỉ khi có `call_id` |
| `leg_type` | enum | không | |
| `side` | enum | có | Với `user_turn`: user là caller hay callee. null với `turn_turn` |
| `direction` | enum | không | |
| `src_id`, `dst_id` | text | không | `user_hash` hoặc `turn_id`. Thứ tự đúng theo **chiều gói tin đi** |
| `user_segment_key` | text | có | Với `user_turn`: segment của user tại thời điểm đo |
| `network_type` | enum | có | Với `user_turn` |
| `one_way_ms` | float | có | Trung bình trong cửa sổ |
| `one_way_ms_max` | float | có | |
| `one_way_estimated` | bool | không | true nếu = RTT/2 (không đồng bộ được đồng hồ) |
| `clock_sync_err_ms` | float | có | Sai số đồng bộ ước tính |
| `loss_pct`, `jitter_ms` | float | có | |
| `packets` | int | có | Số gói trong cửa sổ |
| `missing_reason` | text | có | Ví dụ `no_packets`, `stats_unavailable` |

Đường `A→B` tại một thời điểm = `user_turn(caller, forward)` + `turn_turn(TA→TB, forward)` + `user_turn(callee, forward)`. Khi `path_type = relay_same` thì **không có** dòng `turn_turn`, coi là 0.

### 5.6 `call_stats_5s` (stats đầu-cuối phía endpoint, tương đương getStats)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id`, `side`, `t_offset_s` | | không | PK là (call_id, side, t_offset_s) |
| `event_ts` | timestamptz | không | |
| `network_epoch` | int | không | |
| `network_type` | enum | không | |
| `rtt_ms` | float | có | RTT đầu-cuối (`candidate-pair.currentRoundTripTime` × 1000) |
| `jitter_ms`, `loss_pct` | float | có | |
| `bitrate_send_kbps`, `bitrate_recv_kbps` | float | có | |
| `conn_state` | enum | không | `connected`, `disconnected`, `failed` |

Simulator chỉ lưu đầy đủ bảng này cho khoảng 10% cuộc gọi (`sampled=true` trong `call_outcome`).

### 5.7 `call_outcome` (một dòng mỗi cuộc gọi, phát khi kết thúc)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id` | uuid (PK) | không | |
| `answered` | bool | không | |
| `answer_ts`, `connected_ts`, `end_ts` | timestamptz | có | |
| `connected` | bool | không | |
| `duration_s` | float | có | Từ `connected_ts` tới `end_ts` |
| `end_reason` | enum | không | |
| `dropped` | bool | không | Kết thúc bất thường **sau khi** đã connected |
| `caller_ctx_final`, `callee_ctx_final` | ctx | không | Context **thật** của hai bên, join muộn. Dùng để đo "chi phí của gọi mù" |
| `pair_group` | enum | không | |
| `n_ice_attempts`, `n_network_changes` | int | không | |
| `stats_sampled` | bool | không | Cuộc gọi này có `call_stats_5s` đầy đủ hay không |

> Các aggregate (P50/P95, MOS, cờ PNR) **không** nằm ở đây. Pipeline tính chúng trong `fact_call` (§8) để công thức chỉ có một chỗ.

---

## 6. Event: hạ tầng

### 6.1 `turn_health_1m`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `minute_ts` | timestamptz | PK là (turn_id, minute_ts) |
| `turn_id` | text | |
| `active_allocations` | int | |
| `utilization_pct` | float | active / capacity × 100 |
| `cpu_pct`, `bandwidth_mbps` | float | |
| `alloc_attempts`, `alloc_failures` | int | Trong phút đó |
| `health_status` | enum | Do health checker gán |
| `health_score` | float 0–1 | |

### 6.2 `service_health_1m`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `minute_ts`, `service`, `instance` | | PK. `service = selector_api` |
| `req_count`, `error_count`, `timeout_count` | int | |
| `p50_ms`, `p95_ms`, `p99_ms` | float | Latency của API |
| `static_fallback_count` | int | Client phải dùng list tĩnh vì API lỗi |
| `algo_fallback_count` | int | Thuật toán phải backoff vì thiếu dữ liệu |
| `feature_snapshot_age_s` | float | **Data freshness**: now − `as_of_ts` của snapshot đang phục vụ |

---

## 7. Bất biến (pipeline kiểm tra, vi phạm thì ghi vào `dq_results`)

| ID | Bất biến |
|---|---|
| I1 | Mọi `selector_decision`, `turn_allocation`, `ice_attempt`, `call_outcome` đều có `call_session` tương ứng |
| I2 | Mỗi `call_session` có đúng 1 `call_outcome` sau tối đa 72 giờ, nếu không thì là `orphan` |
| I3 | `len(candidates) = k`; các rank liên tục 1..k; `turn_id` không trùng; tổng propensity = 1 ± 1e-6 |
| I4 | `relay_turn_<side>` của `ice_attempt` phải nằm trong `candidates` của decision cùng side (trừ `decision_source=static_fallback`) |
| I5 | `initiated_ts ≤ request_ts ≤ alloc.request_ts ≤ ice.start_ts ≤ connected_ts ≤ end_ts` (cho phép lệch đồng hồ ≤ 2 s; quá thì gắn cờ) |
| I6 | `answered = false` thì `connected = false` và `end_reason ∈ {not_answered, rejected, cancelled_by_caller}` |
| I7 | `dropped = true` thì `connected = true` |
| I8 | `path_type = relay_same` ⇔ `relay_turn_caller = relay_turn_callee` |
| I9 | Với `inband`: tổng một chiều của 3 chặng ≈ `rtt_ms / 2` của `call_stats_5s` cùng cửa sổ, lệch ≤ 20% hoặc ≤ 15 ms |
| I10 | Range: `0 ≤ one_way_ms ≤ 5000`; `0 ≤ loss_pct ≤ 100`; `jitter_ms ≥ 0`; `0 ≤ utilization_pct ≤ 150` |
| I11 | `event_id` là duy nhất; bản trùng bị dedup và đếm |
| I12 | `feature_snapshot_id` của decision ngày *d* phải có `as_of_ts` < `request_ts` (không được nhìn tương lai) |

---

## 8. Bảng phái sinh của pipeline (để tham khảo, schema chi tiết nằm trong plan)

- `fact_call`: một dòng mỗi cuộc gọi. Join session + decision (initial/refined) + ICE (lần cuối thành công) + outcome. Thêm: `e2e_one_way_p50/p95`, `loss_mean`, `jitter_p95`, `mos_est` (E-model), `pnr_flag`, `rank_used_caller/callee`, `explored`, `joint_propensity = p_caller × p_callee`, `blind_cost_ms` (khi có).
- `fact_leg_window`: `path_leg_measurement` đã làm sạch và gắn segment.
- `dq_results`: `(run_id, dt, check_id, table, status, n_checked, n_bad, sample_event_ids[])`.

---

## 9. Feature store (Hiệp sinh, **Đoàn đọc**)

Mỗi ngày publish một snapshot. `snapshot_id = feat-YYYYMMDD-<run>`, `as_of_ts` = cuối ngày *d−1*. Đoàn **chỉ** đọc snapshot có `as_of_ts` < thời điểm quyết định.

### 9.0 Segment key và backoff

```
L4: country | vn_region | asn | network_type     ví dụ VN|south|7552|4g
L3: country | vn_region | asn                    VN|south|7552
L2: country | vn_region                          VN|south
L1: country                                      VN
L0: global                                       *
```
Mỗi bảng feature có `segment_level` và `segment_key`. Selector tra từ L4 xuống, dùng cấp đầu tiên có `n_eff ≥ n_min` (mặc định 30), và **ghi lại cấp đã dùng** vào `fallback_reason`.

### 9.1 `feat_leg_stats` (chặng user↔TURN)

| Cột | Mô tả |
|---|---|
| `snapshot_id`, `as_of_ts` | |
| `segment_level`, `segment_key` | |
| `turn_id`, `direction` | |
| `hour_bucket` | 0–23 (giờ VN), hoặc `all` |
| `n_raw` | Số cửa sổ đo |
| `n_eff` | Số mẫu hiệu dụng sau decay (half-life 7 ngày) |
| `one_way_p50`, `one_way_p95` | ms, tính trên dữ liệu gốc có trọng số |
| `loss_mean`, `jitter_p95` | |
| `alloc_success_rate`, `alloc_success_ci_low`, `alloc_success_ci_high` | Wilson 95% |
| `one_way_p50_shrunk` | Đã shrink về prior của cấp segment cha |
| `source_mix` | `{inband: .., alloc: .., idle_probe: ..}`, tỉ lệ theo từng method |
| `last_observed_ts` | Phục vụ staleness |

### 9.2 `feat_turn_turn` (chặng TURN↔TURN)

`snapshot_id, src_turn, dst_turn, hour_bucket, n_raw, n_eff, one_way_p50, one_way_p95, loss_mean, jitter_p95, source_mix, last_observed_ts`

### 9.3 `feat_turn_health`

`snapshot_id, turn_id, health_status, health_score, utilization_p95_24h, alloc_success_24h, alloc_success_ci_low, incidents_detected_7d, stability_cv_24h`

> `health_snapshot_id` dùng lúc runtime là snapshot "nóng", 1 phút một lần, lấy từ `turn_health_1m`. Bảng này là phiên bản theo ngày dùng cho ranking.

### 9.4 `feat_path_history` (lịch sử theo cả đường, cấp L2)

`snapshot_id, caller_segment_key, callee_segment_key, turn_caller, turn_callee, n_calls, n_eff, success_rate (+CI), drop_rate, pnr_rate, mos_mean, e2e_one_way_p50, e2e_one_way_p95, last_observed_ts`

### 9.5 `feat_callee_prior` (cho gọi mù)

`snapshot_id, caller_segment_key (L2), callee_country, callee_vn_region, n, share`. Chỉ chứa số đếm, không có danh tính.

---

## 10. API Selector (giao diện giữa simulator / Signaling và thuật toán của Đoàn)

Dạng Python, dùng trong simulator: `select(req: SelectRequest) -> SelectResponse`. Dạng HTTP: `POST /v1/turn/select` với cùng payload JSON.

**SelectRequest**

| Field | Kiểu | Mô tả |
|---|---|---|
| `call_id` | uuid | |
| `phase` | enum | |
| `request_ts` | timestamptz | |
| `caller_ctx` | ctx | |
| `callee_ctx` | ctx / null | null hoặc các field `unknown` nếu gọi mù |
| `info_level` | enum | |
| `k` | int | Mặc định 4 |
| `exploration_epsilon` | float | Simulator truyền vào. Policy phải trả propensity tương ứng |
| `exclude_turns` | text[] | Dùng khi fallback hoặc restart: TURN đã lỗi trong cuộc gọi này |

**SelectResponse**

| Field | Kiểu | Mô tả |
|---|---|---|
| `decision_id` | uuid | |
| `policy_version` | text | |
| `caller` | {candidates[k], filtered_out[], chosen_rank, is_exploration} | |
| `callee` | như trên / null | null nếu gọi mù ở pha initial |
| `confidence`, `confidence_level` | | |
| `fallback_reason` | text / null | |
| `feature_snapshot_id`, `health_snapshot_id` | text | |

Quy định: Selector **không** tự ghi `selector_decision`. Người gọi (Signaling hoặc simulator) ghi event từ Request + Response + latency đo được. Nhờ vậy decision được log kể cả khi API lỗi (`decision_source = static_fallback`).

---

## 11. Bảng ẩn (chỉ simulator, chỉ `eval/` đọc)

| Bảng | Cột |
|---|---|
| `truth_leg_5m` | `ts_bucket, src_id, dst_id, direction, network_type, true_one_way_ms, true_loss_pct, true_jitter_ms` (src là segment hoặc TURN) |
| `incident_truth` | `incident_id, type, target_kind{turn, isp, region, route}, target_id, start_ts, end_ts, severity, params` |
| `dirt_log` | `event_id, table, dirt_type{drop, duplicate, late, clock_skew, unit_error, null_injection, orphan}, params` |

Lưu ở `data/truth/` (gitignore). Dashboard và feature store **bị cấm** đọc (có test kiểm tra import).

---

## 12. Ánh xạ sang telemetry thật (cho pilot)

| Field contract | Nguồn production dự kiến | Ghi chú |
|---|---|---|
| `call_stats_5s.rtt_ms` | W3C `candidate-pair.currentRoundTripTime` (giây) × 1000 | |
| `call_stats_5s.jitter_ms` | `inbound-rtp.jitter` (giây) × 1000 | aiortc dùng đơn vị RTP timestamp |
| `call_stats_5s.loss_pct` | Δ`packetsLost` / Δ(`packetsReceived` + `packetsLost`) × 100 | `packetsLost` có thể âm; counter có thể reset sau ICE restart |
| `ice_attempt.relay_turn_*` | `local-candidate.candidateType = relay` + `url` → tra `dim_turn.hostname` | `url` chỉ có ở local candidate |
| `path_leg_measurement` (user_turn, inband) | Theo mentor: hệ thống đo ms từng chặng | Cách đo **chưa rõ** (giả định A2) |
| `path_leg_measurement` (turn_turn) | Mesh probe agent (đề xuất §5.2 spec) | Chưa có ở production |
| `turn_allocation.alloc_ms` | SDK đo thời gian Allocate request → success | |
| `selector_decision` | Spring Boot Signaling ghi sau khi gọi Selector | Bảng Postgres theo `contracts/ddl` |

---

## 13. Scenario tag (chỉ sim)

`S01_vn_same_region_same_isp`, `S02_vn_cross_region`, `S03_vn_same_region_cross_isp`, `S04_vn_intl_with_turn`, `S05_vn_intl_no_turn`, `S06_intl_same_area`, `S07_intl_cross_area`, `S08_turn_failure`, `S09_cold_start`, `S10_network_change`, `S00_background`.

---

## 14. Ví dụ: một cuộc gọi đầy đủ (rút gọn)

```json
{"table":"call_session","call_id":"0193…a1","caller_hash":"9f2c…","callee_hash":"41ab…","initiated_ts":"2026-11-12T13:00:00.000Z","media_kind":"audio","scenario_tag":"S02_vn_cross_region"}
{"table":"selector_decision","decision_id":"0193…d1","call_id":"0193…a1","side":"caller","phase":"initial","policy_version":"geo_baseline@0.1","decision_mode":"live","decision_source":"api","info_level":"caller_only",
 "self_ctx":{"country":"VN","vn_region":"south","city":"SGN","isp":"viettel","asn":7552,"network_type":"4g","segment_key":"VN|south|7552|4g"},
 "peer_ctx":{"country":"unknown","vn_region":"unknown","city":"unknown","isp":"unknown","asn":null,"network_type":"unknown"},
 "k":4,"candidates":[{"rank":1,"turn_id":"VN-SGN-VTL-01","score":0.91,"propensity":1.0,"reason_codes":["same_isp","same_region"]},{"rank":2,"turn_id":"VN-SGN-FPT-01","score":0.84,"propensity":0.0},{"rank":3,"turn_id":"VN-DAD-VTL-01","score":0.66,"propensity":0.0},{"rank":4,"turn_id":"SG-SIN-AWS-01","score":0.52,"propensity":0.0}],
 "chosen_rank":1,"is_exploration":false,"exploration_epsilon":0.0,"confidence":0.62,"confidence_level":"medium","feature_snapshot_id":"feat-20261111-r1","health_snapshot_id":"hl-20261112T1259"}
{"table":"selector_decision","decision_id":"0193…d2","call_id":"0193…a1","side":"callee","phase":"refined","info_level":"full","self_ctx":{"country":"VN","vn_region":"north","city":"HAN","isp":"vnpt","asn":45899,"network_type":"wifi"},"…":"…"}
{"table":"ice_attempt","call_id":"0193…a1","attempt_seq":1,"trigger":"initial","decision_id":"0193…d2","network_epoch":0,"state":"connected","turn_used":true,"path_type":"relay_relay","relay_turn_caller":"VN-SGN-VTL-01","relay_turn_callee":"VN-HAN-VNP-01","rank_caller":1,"rank_callee":1,"cst_ms":412,"ttfm_ms":95}
{"table":"path_leg_measurement","method":"inband","call_id":"0193…a1","leg_type":"turn_turn","direction":"forward","src_id":"VN-SGN-VTL-01","dst_id":"VN-HAN-VNP-01","window_s":5,"one_way_ms":13.8,"loss_pct":0.0,"jitter_ms":1.2}
{"table":"call_outcome","call_id":"0193…a1","answered":true,"connected":true,"duration_s":184.2,"end_reason":"normal_hangup","dropped":false,"pair_group":"VN_VN","n_ice_attempts":1,"n_network_changes":0,"stats_sampled":false}
```

---

## 15. Version và quy trình thay đổi

- **SemVer:**
  - MAJOR: xóa hoặc đổi tên cột, đổi nghĩa hoặc đơn vị.
  - MINOR: thêm cột nullable, thêm giá trị enum.
  - PATCH: sửa mô tả.
- Mọi thay đổi: PR sửa tài liệu này **và** `contracts/` cùng lúc, cập nhật changelog ở dưới, **Hiệp và Đoàn cùng approve**. Test contract chạy trong CI.
- Reader (pipeline, selector) phải đọc được dữ liệu cùng MAJOR và bỏ qua cột lạ.

## 16. Câu hỏi mở để chốt trong W1

| # | Câu hỏi | Ai trả lời | Mặc định nếu chưa trả lời |
|---|---|---|---|
| Q1 | Đoàn có cần thêm feature nào ngoài §9 (ví dụ theo ngày trong tuần, theo transport)? | Đoàn | Như §9 |
| Q2 | Thang `score` và cách tính `confidence` | Đoàn | Score 0–1, càng cao càng tốt |
| Q3 | `k` = 4 hay 8 | Mentor / Đoàn | 4 |
| Q4 | Production đo ms từng chặng bằng cách nào | Mentor | Giả định A2 của spec |

## Changelog

- **0.1.0** (2026-11-04): bản nháp đầu tiên.
