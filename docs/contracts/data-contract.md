# Data Contract v0.2.0 — TURN Selector Intelligence

- **Ngày:** 2026-11-04 · **Soạn:** Hiệp · **Duyệt:** Hiệp + Đoàn (bắt buộc cả hai)
- **Trạng thái:** v0.2.0 — chờ kiểm tra chéo tự động rồi **FREEZE**
- **Thay thế hoàn toàn:** v0.1.0 (xem lịch sử git). Mọi định nghĩa của v0.1 không xuất hiện ở đây coi như **đã bị hủy**
- **Spec:** `docs/superpowers/specs/2026-11-04-turn-intelligence-design.md` · **Giải thích dễ hiểu:** `data-contract-explained.md`
- **Dạng máy đọc** (sinh ra lúc implement): `contracts/models.py` (Pydantic v2, nguồn gốc) → `contracts/schemas/*.json` (JSON Schema 2020-12) + `contracts/ddl/*.sql` (PostgreSQL) + `contracts/kpi.yaml` (KPI Dictionary §13)

> Tài liệu này là **nguồn sự thật duy nhất** cho schema, bất biến, KPI và luật đánh giá. Nếu code và tài liệu khác nhau, sửa code, hoặc mở PR sửa tài liệu và tăng version.

---

## 0. Bản đồ

```
 call_session (assignment: experiment_id, arm)  ── trước MỌI quyết định
   ├─1:N─ selector_decision ──1:N── turn_allocation (allocation_id)
   ├─1:N─ ice_attempt (ice_generation, allocation_id mỗi bên) ──0:N── ice_candidate_pair  [tùy chọn]
   ├─1:N─ path_leg_measurement   [epoch_summary 100% · window_5s lấy mẫu]
   ├─1:N─ call_stats_epoch       [100% — dữ liệu tính KPI]
   ├─0:N─ call_stats_5s          [lấy mẫu — chẩn đoán]
   └─1:1─ call_outcome
 path_leg_measurement (probe, call_id = null) · turn_health_1m · service_health_1m
 dim_turn · dim_asn · dim_user
 run_manifest (mỗi lần chạy sim / mỗi experiment)
 ─────────── pipeline ───────────► clean-layer (§8) ──► feature store (§9, Đoàn đọc) · KPI (§13)
 truth_leg_5m · incident_truth · dirt_log    (ẨN — chỉ eval/ đọc, §11)
```

### 0.1 Hai loại dữ liệu (quan trọng nhất)

| Loại | Bảng | Độ phủ | Được dùng cho |
|---|---|---|---|
| **KPI-grade** | `call_session`, `selector_decision`, `turn_allocation`, `ice_attempt`, `call_outcome`, `call_stats_epoch`, `path_leg_measurement[granularity=epoch_summary]`, `turn_health_1m`, `service_health_1m` | **100% cuộc gọi** | Mọi KPI chính và guardrail (§13), feature store (§9) |
| **Diagnostic** | `call_stats_5s`, `path_leg_measurement[granularity=window_5s]`, `ice_candidate_pair` | Lấy mẫu (§6.3) hoặc tùy telemetry | Điều tra, Decision Trace, biểu đồ chi tiết. **Không bao giờ** dùng cho KPI quyết định (I16) |

---

## 1. Quy ước chung

| Mục | Quy ước |
|---|---|
| Thời gian | UTC, ISO-8601, ms (`2026-11-12T13:45:01.123Z`); Postgres `timestamptz`. Cột phái sinh `local_hour_vn` (UTC+7) |
| Partition | `dt` = ngày UTC của `event_ts` |
| ID | `event_id`, `decision_id`, `allocation_id`: UUIDv7. `call_id`: UUIDv7 do Signaling cấp |
| Đơn vị | Thời gian/độ trễ **ms** · loss **%** (0–100) · jitter **ms** · bitrate **kbps** · tỉ lệ 0–1 |
| Quốc gia / thành phố | ISO-3166-1 alpha-2 / mã IATA thành phố |
| Vùng VN | `north`, `central`, `south`; `null` = không áp dụng |
| Không biết | Enum dùng **`unknown`**. `null` = không áp dụng hoặc chưa có số đo (kèm `*_missing_reason` khi có) |
| Thiếu số đo | **Không điền 0, không điền trung bình** |
| Privacy | `user_hash` = HMAC-SHA256(user_id, salt), 16 hex đầu. Không lưu IP thô. Geo tới cấp thành phố |
| Hash tất định | Mọi quy tắc dựa trên hash dùng **SHA-256 trên chuỗi UTF-8, lấy 8 byte đầu, big-endian, unsigned** (§6.3). Cấm dùng `hash()` của ngôn ngữ |

### 1.1 Cột chung của mọi bảng event (raw)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `event_id` | uuid | không | Duy nhất. Dùng dedup |
| `contract_version` | text | không | `"0.2.0"` |
| `data_source` | enum | không | `synthetic` · `lab_zenodo` · `public_reference` · `production` |
| `producer` | enum | không | `client_sdk` · `signaling` · `selector` · `turn_server` · `probe_agent` · `simulator` |
| `event_ts` | timestamptz | không | Lúc xảy ra theo đồng hồ producer. **Bất biến — pipeline không bao giờ ghi đè** |
| `ingest_ts` | timestamptz | không | Lúc collector nhận ("thời điểm hệ thống biết") |
| `sim_run_id` | text | có | Bắt buộc khi `data_source=synthetic`; trỏ `run_manifest` |
| `dt` | date | không | Partition |

---

## 2. Enum

| Enum | Giá trị |
|---|---|
| `side` | `caller`, `callee` |
| `network_type` | `wifi`, `4g`, `5g`, `ethernet`, `unknown` |
| `media_kind` | `audio`, `video` |
| `info_level` | `full`, `caller_only`, `country_only`, `none` |
| `decision_phase` | `initial`, `refined`, `restart` |
| `decision_mode` | `live`, `shadow` |
| `decision_source` | `api`, `static_fallback`, `cache` |
| `connection_mode` | `post_answer` (ICE bắt đầu sau khi bắt máy — **mặc định, giả định chưa xác minh**), `pre_connect` (ICE trong lúc đổ chuông) |
| `transport` | `udp`, `tcp`, `tls` |
| `leg_type` | `user_turn`, `turn_turn` |
| `direction` | `forward` (theo chiều caller→callee), `reverse` |
| `measure_method` | `inband`, `mesh_probe`, `idle_probe` |
| `measurement_kind` | `one_way`, `rtt` |
| `measurement_point` | `client`, `turn_server`, `probe_agent` |
| `granularity` | `epoch_summary`, `window_5s` |
| `path_type` | `relay_relay`, `relay_same`, `relay_direct`, `p2p_host`, `p2p_srflx`, `unknown` — **suy từ cặp candidate được chọn** |
| `candidate_type` | `host`, `srflx`, `prflx`, `relay`, `unknown` |
| `ice_trigger` | `initial`, `fallback`, `restart_network_change`, `restart_failure` |
| `ice_state` | `connected`, `failed`, `timeout`, `cancelled` |
| `end_reason` | `normal_hangup`, `invite_undelivered`, `not_answered`, `rejected`, `cancelled_by_caller`, `ice_failed`, `dropped_network`, `dropped_turn`, `app_crash`, `unknown` |
| `pair_group` | `VN_VN`, `VN_INTL`, `INTL_INTL` |
| `health_status` | `healthy`, `degraded`, `overloaded`, `down`, `maintenance` |
| `alloc_error` | `none`, `timeout`, `unauthorized_401`, `forbidden_403`, `quota_486`, `capacity_508`, `unreachable`, `other` |
| `stats_status` | `kept_critical`, `kept_sampled`, `not_sampled`, `truncated`, `lost`, `not_applicable` |
| `quality_assessment_status` | `assessed`, `partially_assessed`, `unclassifiable`, `not_applicable` |
| `randomization_unit` | `run` (sim: cả môi trường), `call`, `user`, `region`, `time_block` |
| `run_kind` | `scripted`, `blind_benchmark`, `dev` |

---

## 3. Dimension

### 3.1 `dim_turn` (SCD2)
`turn_id` (`<country>-<city>-<host>-<nn>`), `hostname`, `country`, `vn_region`, `city`, `lat`, `lon`, `host_isp`, `host_asn`, `capacity_alloc`, `transports[]`, `status` {`active`,`maintenance`,`retired`}, `valid_from`, `valid_to` (null = còn hiệu lực).

### 3.2 `dim_asn`
`asn` (PK), `isp`, `country`, `access_kind` {`fixed`,`mobile`,`mixed`}.

### 3.3 `dim_user`
`user_hash` (PK), `home_country`, `home_vn_region`, `home_city`, `home_isp`, `home_asn`, `primary_network`, `cohort` {`normal`,`cold_start`}, `created_at`.

---

## 4. Object `ctx` (bối cảnh một bên tại lúc quyết định)

`user_hash` (null nếu chưa biết) · `country` · `vn_region` · `city` · `isp` · `asn` · `network_type` · `geo_source` {`ip_geo`,`sdk_claimed`,`both`} · `geo_mismatch` (bool) · `segment_key` (§9.0). Field chưa biết = `unknown`. Postgres làm phẳng với prefix `self_` / `peer_` / `caller_` / `callee_`.

---

## 5. Event — luồng cuộc gọi

### 5.1 `call_session` (Signaling tạo khi A bấm gọi — **trước mọi quyết định**)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id` | uuid PK | không | |
| `caller_hash`, `callee_hash` | text | không | |
| `initiated_ts` | timestamptz | không | |
| `media_kind` | enum | không | |
| `connection_mode` | enum | không | |
| `experiment_id` | text | có | null = không thuộc thí nghiệm nào |
| `arm` | text | có | Bắt buộc khi có `experiment_id`. Trên sim = tên policy của môi trường |
| `randomization_unit` | enum | có | |
| `experiment_cluster_id` | text | có | Cụm ngẫu nhiên hóa (region, time block…). Trên sim = `sim_run_id` |
| `assignment_ts` | timestamptz | có | **Phải ≤ `request_ts` của decision đầu tiên** (I15) |
| `assignment_hash` | text | có | Hash dùng để gán nhánh (tái lập được) |
| `scenario_tag` | text | có | Chỉ sim. **Chỉ mô tả loại cuộc gọi**, không bao giờ mã hóa sự cố ẩn (§12) |

### 5.2 `selector_decision` (một dòng cho mỗi `decision_id` × `side`)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `decision_id` | uuid | không | Chung cho hai bên của một request |
| `call_id`, `side`, `phase` | | không | |
| `request_ts` | timestamptz | không | |
| `response_ts`, `api_latency_ms` | | có | null khi API không trả lời |
| `policy_version` | text | không | `geo_baseline@0.1`, `smart@0.3.1`, `static@1` |
| `decision_mode`, `decision_source`, `info_level` | enum | không | |
| `self_ctx`, `peer_ctx` | ctx | không | `peer_ctx` = **những gì biết lúc đó** |
| `k` | int | không | Mặc định 4 |
| `candidates` | array[Candidate] | không | Đúng `k`, sắp theo rank |
| `filtered_out` | array[{turn_id, reason}] | không | reason: `down`, `overloaded`, `degraded`, `maintenance`, `policy` |
| `chosen_rank` | int | không | Rank client được yêu cầu thử trước |
| `is_exploration` | bool | không | |
| `exploration_epsilon` | float | không | |
| `confidence` (0–1), `confidence_level` {high, medium, low} | | không | |
| `fallback_reason` | text | có | Backoff thiếu dữ liệu, ví dụ `backoff_L1` |
| `feature_snapshot_id`, `health_snapshot_id` | text | không* | *null chỉ khi `decision_source=static_fallback` |
| `error_code` | text | có | |

**Candidate:** `rank`, `turn_id`, `score` (cao = tốt, chỉ so trong một decision), `score_components` map, `est_leg_ms` (null), `est_path_ms` (null), `reason_codes[]`, `propensity` (P(candidate này là `chosen_rank`); tổng = 1).

### 5.3 `turn_allocation` (một dòng cho mỗi allocation)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `allocation_id` | uuid PK | không | Do client sinh. Dùng để gắn với ICE |
| `call_id`, `decision_id`, `side` | | không | |
| `turn_id`, `rank`, `transport` | | không | |
| `ice_generation` | int | không | Thế hệ ICE lúc tạo allocation (0, tăng mỗi ICE restart) |
| `attempt_seq` | int | có | null nếu chưa gắn với lần thử cụ thể |
| `is_preallocation` | bool | không | |
| `request_ts` | timestamptz | không | |
| `response_ts`, `alloc_ms` | | có | null nếu timeout. `alloc_ms` là **allocation latency** (gồm cả vòng 401 và thời gian server xử lý), **không phải RTT, không phải one-way** |
| `success` | bool | không | |
| `error_code` | enum `alloc_error` | không | |
| `released_ts`, `release_reason` {`not_needed`,`call_end`,`kept_for_failover`,`expired`,`unanswered`} | | có | |

### 5.4 `ice_attempt` (một dòng cho mỗi lần thử: lần đầu, fallback, restart)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id`, `attempt_seq`, `ice_generation` | | không | |
| `trigger` | enum | không | |
| `decision_id` | uuid | không | |
| `network_epoch` | int | không | |
| `start_ts` | timestamptz | không | |
| `checks_start_ts` | timestamptz | có | ICE connectivity check đầu tiên |
| `ice_connected_ts` | timestamptz | có | |
| `dtls_connected_ts` | timestamptz | có | Tùy telemetry |
| `end_ts` | timestamptz | có | |
| `state` | enum | không | |
| `turn_used` | bool | có | null khi thất bại |
| `selected_local_candidate_type`, `selected_remote_candidate_type` | enum `candidate_type` | có | Từ cặp candidate được chọn (`transport.selectedCandidatePairId`) |
| `path_type` | enum | có | **Suy từ hai field trên** — không giả định luôn là relay_relay |
| `relay_turn_caller`, `relay_turn_callee` | text | có | TURN thực dùng (null nếu bên đó không đi relay) |
| `caller_allocation_id`, `callee_allocation_id` | uuid | có | Allocation thực dùng. Thiếu thì pipeline dùng quy tắc ghép §8.3 |
| `rank_caller`, `rank_callee` | int | có | Rank của TURN thực dùng trong decision |
| `transport` | enum | có | |
| `failure_reason` | text | có | |

### 5.5 `ice_candidate_pair` (**tùy chọn** — chẩn đoán)

`call_id`, `attempt_seq`, `ice_generation`, `pair_id`, `local_candidate_id`, `remote_candidate_id`, `local_candidate_type`, `remote_candidate_type`, `local_turn_id`, `remote_turn_id`, `pair_priority`, `check_state` {`waiting`,`in_progress`,`succeeded`,`failed`}, `check_count`, `nominated`, `selected`, `current_rtt_ms`, `telemetry_support` {`full`,`partial`}.
Không suy diễn bảng này từ `relay_turn_*`. Không có thì không có.

### 5.6 `path_leg_measurement` (phân rã chặng)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `granularity` | enum | không | `epoch_summary` (100% cuộc gọi, một dòng / call × epoch × leg × direction) hoặc `window_5s` (chỉ cuộc gọi được lấy mẫu) |
| `method` | enum | không | `inband`, `mesh_probe`, `idle_probe` (**không có `alloc`**) |
| `measurement_kind` | enum | không | `one_way` (đo trực tiếp, cần đồng bộ đồng hồ) hoặc `rtt` |
| `measurement_point` | enum | không | |
| `method_version` | text | không | |
| `window_start_ts`, `window_end_ts` | timestamptz | không | |
| `call_id`, `attempt_seq`, `ice_generation`, `network_epoch` | | có | null với probe |
| `leg_type`, `direction` | enum | không | |
| `side` | enum | có | Với `user_turn` |
| `src_id`, `dst_id` | text | không | Theo chiều gói tin |
| `user_segment_key`, `network_type` | | có | Với `user_turn` |
| `value_ms` | float | có | Trung bình trong cửa sổ hoặc epoch, **đúng loại `measurement_kind`** |
| `value_ms_p95` | float | có | Chỉ với `epoch_summary`: P95 trong epoch |
| `n_samples` | int | không | |
| `clock_sync_err_ms` | float | có | Bắt buộc khi `measurement_kind=one_way` |
| `loss_pct`, `jitter_ms`, `packets` | | có | |
| `missing_reason` | text | có | |

Đường A→B = `user_turn(caller, forward)` + `turn_turn(TA→TB, forward)` + `user_turn(callee, forward)`. Khi `path_type=relay_same` không có dòng `turn_turn` (= 0). **Bảng này chỉ dùng cho phân rã, chẩn đoán và feature — không bao giờ dùng làm nhãn PCR** (§13).

### 5.7 `call_stats_epoch` (**KPI-grade, 100%**)

Một dòng cho mỗi (`call_id`, `endpoint_side`, `media_kind`, `network_epoch`). SDK tính trên thiết bị và gửi khi epoch kết thúc.

**Cửa sổ 5 giây:** neo tại `anchor_ts` = `ice_connected_ts` **đầu tiên** của cuộc gọi; cửa sổ thứ *i* = [anchor + 5i, anchor + 5(i+1)). Neo **không** đặt lại sau ICE restart. Cửa sổ thuộc epoch chứa phần lớn thời gian của nó. Một cửa sổ chỉ **đánh giá được** khi nằm trọn trong [`answer_ts`, `end_ts`] (người dùng thực sự nghe) và không có gián đoạn media do restart. Vì vậy với `pre_connect`, các cửa sổ trong lúc đổ chuông không bao giờ được đánh giá.

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id`, `endpoint_side`, `media_kind`, `network_epoch` | | không | `endpoint_side` = endpoint báo cáo |
| `epoch_start_ts`, `epoch_end_ts` | timestamptz | không | |
| `audio_active_duration_s` | float | không | Thời gian có media audio thực sự |
| `first_media_sent_ts`, `first_media_received_ts` | timestamptz | có | Tại endpoint này, trong epoch này |
| `packets_expected`, `packets_lost` | int | có | **Luồng inbound** tại endpoint này |
| `media_rtcp_rtt_hist` | map<bucket, int> | có | Số cửa sổ theo bucket `<100,100–200,200–300,300–400,≥400` ms. RTT của **luồng outbound** của endpoint này (`remote-inbound-rtp.roundTripTime`, theo SSRC) |
| `loss_hist` | map<bucket, int> | có | Bucket `<1,1–3,3–5,≥5` %, loss inbound của cửa sổ = Δlost / Δexpected |
| `jitter_estimate_hist` | map<bucket, int> | có | Bucket `<10,10–30,30–50,≥50` ms, jitter estimate inbound (`inbound-rtp.jitter`) |
| `rtt_windows_assessable`, `loss_windows_assessable`, `jitter_windows_assessable` | int | không | Số cửa sổ có số đo hợp lệ **cho từng metric** |
| `valid_rtt_samples`, `valid_jitter_samples` | int | không | Số mẫu hợp lệ. RTT chỉ hợp lệ sau khi có RTCP RR với DLSR ≠ 0 |
| `media_rtcp_rtt_p50`, `media_rtcp_rtt_p95` | float | có | Chẩn đoán |
| `ice_stun_rtt_p50`, `ice_stun_rtt_p95` | float | có | `candidate-pair.currentRoundTripTime` — RTT của STUN check, **metric riêng, không thay cho media RTT** |
| `jitter_estimate_p95` | float | có | P95 của **các ước lượng jitter đã lấy mẫu**, không phải packet jitter |
| `measurement_coverage` | float 0–1 | không | Tỉ lệ cửa sổ đánh giá được / tổng cửa sổ của epoch |
| `quality_rule_version` | text | không | Phiên bản bộ bucket |

### 5.8 `call_stats_5s` (**diagnostic, lấy mẫu**)
PK (`call_id`, `endpoint_side`, `media_kind`, `window_idx`). `network_epoch`, `network_type`, `media_rtcp_rtt_ms`, `ice_stun_rtt_ms`, `jitter_estimate_ms`, `loss_pct`, `packets_expected`, `packets_lost`, `bitrate_send_kbps`, `bitrate_recv_kbps`, `conn_state`. Cùng quy tắc neo cửa sổ như §5.7.

### 5.9 `call_outcome` (một dòng mỗi cuộc gọi)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id` | uuid PK | không | |
| `ring_ts` | timestamptz | có | Máy B nhận lời mời và đổ chuông. null nếu `invite_undelivered` |
| `answer_ts` | timestamptz | có | Người dùng B **bấm nghe** (sự kiện Signaling, không phải SDP Answer) |
| `answered` | bool | không | |
| `connected` | bool | không | Có ít nhất một ICE attempt `connected` |
| `end_ts` | timestamptz | không | |
| `duration_s` | float | có | Từ `answer_ts` tới `end_ts` |
| `end_reason` | enum | không | |
| `dropped` | bool | không | Kết thúc bất thường **sau khi đã bắt máy và đã connected** |
| `caller_ctx_final`, `callee_ctx_final` | ctx | không | Context thật, join muộn |
| `pair_group` | enum | không | |
| `n_ice_attempts`, `n_network_changes` | int | không | |
| `stats_status` | enum | không | Trạng thái của dữ liệu **diagnostic** (`call_stats_5s`, window_5s) |
| `stats_sampling_prob` | float | không | 1.0 / 0.1 / 0.0 (§6.3) |
| `stats_sampling_reason` | text | không | `critical:<lý do>`, `hash_sample`, `not_selected` |
| `sampling_rule_version` | text | không | |

---

## 6. Event — hạ tầng, và quy tắc thu thập

### 6.1 `turn_health_1m`
PK (`turn_id`, `minute_ts`). `active_allocations`, `utilization_pct`, `cpu_pct`, `bandwidth_mbps`, `alloc_attempts`, `alloc_failures`, `health_status`, `health_score`.

### 6.2 `service_health_1m`
PK (`minute_ts`, `service`, `instance`). `req_count`, `error_count`, `timeout_count`, `p50_ms`, `p95_ms`, `p99_ms`, `static_fallback_count`, `algo_fallback_count`, `active_snapshot_id`, `feature_snapshot_age_s` (now − `cutoff_ts` của snapshot đang phục vụ), `shadow_req_count`.

### 6.3 Quy tắc lấy mẫu dữ liệu diagnostic
1. Trong cuộc gọi, SDK ghi `call_stats_5s` vào **ring buffer** trên thiết bị: tối đa 360 cửa sổ (30 phút) và tối đa 256 KB mỗi cuộc gọi. Tràn thì giữ cửa sổ mới nhất và đặt `stats_status=truncated`.
2. Khi kết thúc, phân tầng:
   - **critical**: `end_reason ∈ {ice_failed, dropped_network, dropped_turn}` hoặc `n_ice_attempts > 1` hoặc có fallback hoặc restart → giữ toàn bộ, `prob = 1.0`, `kept_critical`.
   - **normal**: giữ nếu `u64(sha256(utf8(call_id))[0:8], big-endian) mod 1000 < 100` → `prob = 0.1`, `kept_sampled`; ngược lại xóa buffer, `prob = 0.0`, `not_sampled`.
3. Đã chọn giữ nhưng gửi thất bại → `lost` (phân biệt với `not_sampled`). `truncated` là **trạng thái**, không phải lý do: cuộc gọi bị cắt buffer vẫn giữ `stats_sampling_reason` và `stats_sampling_prob` của tầng đã chọn nó.
4. **Dữ liệu KPI-grade (§0.1) luôn được gửi 100%, không phụ thuộc quy tắc này.**
5. Aggregate chẩn đoán trên dữ liệu lấy mẫu phải dùng trọng số Horvitz-Thompson `1/prob` ở **cấp cuộc gọi**. Độ bất định tính theo cụm cuộc gọi.

---

## 7. Bất biến

Mức: **FAIL** (dữ liệu sai, phải sửa) · **WARN** (đáng ngờ, hiện lên trang Data Quality).

| ID | Mức | Bất biến |
|---|---|---|
| I1 | FAIL | Mọi event có `call_id` đều có `call_session` tương ứng |
| I2 | WARN | Mỗi `call_session` có đúng 1 `call_outcome` trong 72 giờ (thiếu thì là orphan) |
| I3 | FAIL | `len(candidates)=k`; rank liên tục 1..k; không trùng `turn_id`; Σ propensity = 1 ± 1e-6 |
| I4 | WARN | TURN thực dùng nằm trong `candidates` cùng side (trừ `static_fallback`) |
| I5 | WARN | **Chỉ các quan hệ nhân quả** (dung sai lệch đồng hồ 2 s, vượt thì cắm cờ): (a) `initiated_ts ≤` `request_ts` đầu tiên; (b) `decision.response_ts ≤ alloc.request_ts` với allocation của decision đó; (c) `alloc.response_ts ≤ ice_connected_ts` khi attempt dùng allocation đó; (d) `ring_ts ≤ ice_connected_ts`; (e) với `post_answer`: `answer_ts ≤ checks_start_ts`; (f) `ice_connected_ts ≤ dtls_connected_ts ≤ first_media_sent_ts`; (g) mọi mốc `≤ end_ts`. **Không** ràng buộc thứ tự giữa allocation, signaling và ICE checks ngoài các mục trên |
| I6 | FAIL | `answered=false` ⇒ `end_reason ∈ {invite_undelivered, not_answered, rejected, cancelled_by_caller}`; `connected` chỉ có thể true khi `connection_mode=pre_connect` |
| I7 | FAIL | `dropped=true` ⇒ `answered ∧ connected` |
| I8 | FAIL | `path_type=relay_same` ⇔ `relay_turn_caller = relay_turn_callee ≠ null` |
| I9 | WARN | Chỉ khi cả 3 chặng forward **và** 3 chặng reverse là `one_way`, cùng cửa sổ, `clock_sync_err_ms ≤ 2`: Σforward + Σreverse ≈ `media_rtcp_rtt` (lệch ≤ 20% hoặc ≤ 15 ms) |
| I10 | FAIL | `0 ≤ value_ms ≤ 10000`; `0 ≤ loss_pct ≤ 100`; jitter ≥ 0; `0 ≤ utilization_pct ≤ 150`; tổng histogram = số cửa sổ assessable tương ứng |
| I11 | WARN | `event_id` duy nhất (bản trùng bị dedup và đếm) |
| I12 | FAIL | Decision dùng snapshot S ⇒ `S.published_ts ≤ request_ts` |
| I13 | FAIL | Mọi event đóng góp vào snapshot S thỏa `event_ts < S.cutoff_ts` **và** `ingest_ts < S.cutoff_ts`. Snapshot đã publish là **bất biến**; tính lại thì tạo `snapshot_id` mới |
| I14 | FAIL | Selector **không được chặn** lời mời gọi. Selector lỗi hoặc timeout ⇒ `decision_source=static_fallback`; không bao giờ có `end_reason` do Selector |
| I15 | FAIL | Nếu `experiment_id ≠ null`: `arm ≠ null` và `assignment_ts ≤` `request_ts` đầu tiên của cuộc gọi |
| I16 | FAIL | KPI chính và guardrail (§13) chỉ đọc bảng KPI-grade (§0.1). Kiểm tra tự động từ `contracts/kpi.yaml` |
| I17 | FAIL | `stats_sampling_prob` khớp quy tắc §6.3 khi tính lại từ `call_id` và outcome |

---

## 8. Clean-layer — pipeline cam kết xuất ra (producer **không** gửi)

### 8.1 Đồng hồ
`event_ts_corrected`, `clock_skew_ms` (với `client_sdk`: offset ước lượng theo thiết bị × ngày, là trung vị độ lệch giữa client và Signaling trên các mốc tương ứng; với `turn_server`, `probe_agent`, `selector`, `signaling`: theo `instance` × giờ, giả định đồng bộ NTP, offset = 0 trừ khi độ lệch `ingest_ts − event_ts` bất thường thì cắm cờ `unreliable`), `clock_correction_version`, `clock_quality_flag` {`ok`,`corrected`,`unreliable`}. `event_ts` gốc giữ nguyên. Không dùng correction để khẳng định độ chính xác vượt quá khả năng đồng bộ thực tế.

### 8.2 Độ trễ chặng
- `one_way_ms_observed` = `value_ms` khi `measurement_kind=one_way` và `clock_sync_err_ms ≤ 2`; ngược lại null.
- `one_way_ms_estimated` = `value_ms / 2` khi `measurement_kind=rtt`, cắm cờ `symmetric_assumption=true`.
- **`alloc_ms` không bao giờ được đổi sang one-way.** Thống kê riêng ở `feat_turn_alloc_latency` (§9.6). Chỉ được dùng làm predictor của chặng sau khi mô hình hiệu chỉnh đã được kiểm chứng trên dữ liệu tách riêng (thí nghiệm W5).

### 8.3 Ghép allocation với ICE
- Ưu tiên `*_allocation_id` trong `ice_attempt`.
- Thiếu thì ghép theo (`call_id`, `decision_id`, `side`, `turn_id`, `transport`, `ice_generation`), với điều kiện allocation còn hiệu lực (`response_ts ≤ ice_connected_ts < released_ts`). Không bao giờ ghép allocation của generation cũ vào attempt mới chỉ vì cùng `turn_id`.
- Xuất ra: `used_by_ice` (bool), `match_method` {`id`,`rule`,`ambiguous`}.

### 8.4 `fact_call`
Một dòng mỗi cuộc gọi: các cột KPI ở §13 (tính từ KPI-grade), `rank_used_*`, `joint_propensity = p_caller × p_callee`, `arm`, `blind_cost_ms` (chỉ sim).

### 8.5 `dq_results`
`(run_id, dt, check_id, table, level, status, n_checked, n_bad, sample_event_ids[])`.

---

## 9. Feature store (Hiệp sinh — Đoàn đọc)

### 9.0 Snapshot và segment
- **Cutoff:** `cutoff_ts` = 00:00 giờ VN (17:00 UTC ngày hôm trước). Mỗi ngày một snapshot.
- **Metadata:** `snapshot_id` (`feat-YYYYMMDD-v<n>`), `cutoff_ts`, `published_ts`, `pipeline_version`, `content_hash`, `parent_snapshot_id`.
- **Quy tắc dùng:** tại thời điểm t, Selector dùng snapshot mới nhất có `published_ts ≤ t` (I12). Nội dung thỏa I13. Từ `cutoff_ts` tới `published_ts`, Selector **dùng snapshot cũ**.
- **Bất biến:** snapshot đã publish không sửa. Backfill hoặc sửa logic thì tạo `v<n+1>`. Dựng lại snapshot từ raw và cấu hình đã lưu phải cho ra cùng `content_hash`.
- **Segment, backoff 5 cấp:** `L4 country|vn_region|asn|network_type` → `L3 country|vn_region|asn` → `L2 country|vn_region` → `L1 country` → `L0 *`. Selector dùng cấp chi tiết nhất có `n_eff ≥ 30` và ghi cấp đã dùng vào `fallback_reason`.

### 9.1 `feat_leg_stats` (chặng user↔TURN)
`snapshot_id`, `segment_level`, `segment_key`, `turn_id`, `direction`, `metric` {`one_way_observed`,`rtt`}, `hour_bucket` (0–23 giờ VN hoặc `all`), `n_raw`, `n_eff` (decay half-life 7 ngày), `p50`, `p95` (quantile có trọng số trên giá trị **cấp cuộc gọi** từ `epoch_summary`), `loss_mean`, `jitter_p95`, `p50_shrunk`, `source_mix`, `last_observed_ts`.

### 9.2 `feat_turn_turn`
`snapshot_id`, `src_turn`, `dst_turn`, `direction`, `metric`, `hour_bucket`, `n_raw`, `n_eff`, `p50`, `p95`, `loss_mean`, `jitter_p95`, `source_mix`, `last_observed_ts`.

### 9.3 `feat_turn_health`
`snapshot_id`, `turn_id`, `health_status`, `health_score`, `utilization_p95_24h`, `alloc_success_24h` (+ Wilson `ci_low`, `ci_high`), `incidents_detected_7d`, `stability_cv_24h`.

### 9.4 `feat_path_history`
`snapshot_id`, `caller_segment_key` (L2), `callee_segment_key` (L2), `turn_caller`, `turn_callee`, `n_calls`, `n_eff`, `poor_rate` (+ CI, theo định nghĩa §13.2), `drop_rate`, `ice_fail_rate`, `last_observed_ts`.

### 9.5 `feat_callee_prior`
`snapshot_id`, `caller_segment_key` (L2), `callee_country`, `callee_vn_region`, `n`, `share`.

### 9.6 `feat_turn_alloc_latency`
`snapshot_id`, `segment_key`, `turn_id`, `transport`, `n`, `alloc_ms_p50`, `alloc_ms_p95`, `alloc_success_rate` (+ CI). **Không** phải độ trễ chặng.

---

## 10. API Selector

**HTTP** `POST /v1/turn/select` (production và demo):
- **SelectRequest:** `call_id`, `phase`, `request_ts`, `caller_ctx`, `callee_ctx` (null khi gọi mù), `info_level`, `k`, `exploration_epsilon`, `exclude_turns[]`.
- **SelectResponse:** `decision_id`, `policy_version`, `caller` {candidates[k], filtered_out[], chosen_rank, is_exploration}, `callee` (như trên, hoặc null), `confidence`, `confidence_level`, `fallback_reason`, `feature_snapshot_id`, `health_snapshot_id`.
- Không có tham số randomness nào do client truyền vào. Randomness ở production lấy từ `sha256(server_secret ‖ call_id ‖ side ‖ purpose)`.

**Interface nội bộ simulator:** `select(req, rng)`. `rng` do simulator cấp, khóa theo `(run_seed, call_id, side, "policy")`. Policy **không được** tạo RNG toàn cục.

**Quy định:** Selector không tự ghi `selector_decision`. Bên gọi ghi, kể cả khi lỗi (I14).

---

## 11. Bảng ẩn và cách ly

| Bảng | Cột |
|---|---|
| `truth_leg_5m` | `ts_bucket`, `src_id`, `dst_id`, `direction`, `network_type`, `exo_one_way_ms` (thành phần ngoại sinh, giống nhau giữa các policy), `load_one_way_ms` (thành phần do tải, riêng từng môi trường), `true_loss_pct`, `true_jitter_ms`, `available` (bool) |
| `incident_truth` | `incident_id`, `type`, `target_kind`, `target_id`, `start_ts`, `end_ts`, `severity`, `params` |
| `dirt_log` | `event_id`, `table`, `dirt_type`, `params` |

- Lưu ở `data/truth/`. Chỉ package `eval/` được đọc. Có test tự động cấm `selector`, `pipeline`, `features`, `dashboard` import hoặc mở các file này.
- Riêng trang dashboard "Sim Validation" được đọc, và có nhãn rõ.

---

## 12. Run manifest và các loại lần chạy

**`run_manifest`** (một file JSON mỗi lần chạy, được commit cùng kết quả):
`sim_run_id`, `run_kind`, `benchmark_id`, `replicate_seed`, `simulator_version`, `git_commit`, `config_hash`, `contract_version`, `topology_version`, `network_profile_version`, `scenario_version`, `incident_schedule_version`, `incidents_sha256`, `root_seeds` {traffic, network, incidents, noise, behavior, policy} (seed gốc cho từng miền ngẫu nhiên; mọi lần rút cụ thể dùng RNG có khóa theo thực thể và thời điểm, §14.2 — không có luồng tuần tự), `policy_version`, `exploration_epsilon`, `connection_mode`, `initial_snapshot_hash`, `burn_in_days`, `environment_dir`, `started_at`, `completed_at`. Ở cấp benchmark (`benchmark_manifest`, một file cho cả bộ seed): `benchmark_id`, `n_replicates_planned`, `mde_pp`, `alpha`, `power`, `power_analysis_ref` (đường dẫn tới kết quả chạy thử 3 seed), `kpi_yaml_hash` (ngưỡng đã đóng băng), `decision_rule_version`.

| Loại | Dùng cho | Sự cố |
|---|---|---|
| `scripted` | Test tự động, demo các kịch bản S01–S20 | Công khai, có kỳ vọng rõ |
| `blind_benchmark` | So sánh policy, insight report | Ẩn. `incidents_sha256` được commit **trước** khi phân tích |
| `dev` | Phát triển | Tùy ý |

**10 kịch bản bắt buộc của đề bài** = S01–S10. Trong đó S08 (TURN failure) là kịch bản hệ thống, còn lại là kịch bản cuộc gọi.

**Kịch bản cuộc gọi** (`scenario_tag`): `S01_vn_same_region_same_isp`, `S02_vn_cross_region`, `S03_vn_same_region_cross_isp`, `S04_vn_intl_with_turn`, `S05_vn_intl_no_turn`, `S06_intl_same_area`, `S07_intl_cross_area`, `S09_cold_start`, `S10_network_change`, `S00_background`.

**Kịch bản hệ thống** (chỉ trong manifest của `scripted`, không bao giờ là tag cuộc gọi): `S08_turn_failure`, `S11_turn_overload`, `S12_isp_congestion`, `S13_regional_outage`, `S14_asymmetric_path`, `S15_selector_timeout`, `S16_stale_snapshot`, `S17_delayed_telemetry`, `S18_turn_recovery`, `S19_p2p_preferred`, `S20_call_burst`. Phải có kịch bản Geo thắng, kịch bản Historical thắng và kịch bản Smart thắng.

---

## 13. KPI Dictionary (nguồn định nghĩa duy nhất; bản máy đọc `contracts/kpi.yaml`)

### 13.1 Quy tắc chung
- Mọi KPI ở §13.2–13.3 đọc **KPI-grade** (I16).
- Ngưỡng ghi là *tạm thời* được **đóng băng** trong `kpi.yaml` trước `blind_benchmark` đầu tiên; sau đó chỉ đổi bằng version mới.
- Ngữ nghĩa percentile: `call_*` = trong một cuộc gọi; `population_*` = giữa các cuộc gọi, tính trên giá trị cấp cuộc gọi. **Không bao giờ lấy trung bình các P95.**

### 13.2 Phân loại một cuộc gọi

```
Với cuộc gọi c, metric m ∈ {rtt, loss, jitter}, chỉ trên media_kind = audio,
gộp mọi epoch và cả hai endpoint_side, TÍNH RIÊNG từng bên:

  PoorFraction_m(c, side) = Σ_epochs PoorWindows_m / Σ_epochs AssessableWindows_m
      chỉ xác định khi Σ AssessableWindows_m ≥ 4

  PoorWindow:  rtt    → bucket ≥ 300 ms   (media_rtcp_rtt — SLO nội bộ tạm thời, KHÔNG suy ra từ G.114)
               loss   → bucket ≥ 3 %
               jitter → bucket ≥ 30 ms    (jitter estimate)

  quality_poor(c)   = ∃ side, ∃ m xác định: PoorFraction_m(c, side) ≥ 0.20   (tạm thời)
  quality_ok(c)     = mọi m của mọi side đều xác định và < 0.20
  ngược lại (không có side/m nào xác định, hoặc chỉ một phần xác định mà không poor)
                    → quality_unknown(c)

  poor(c) =  end_reason = ice_failed
          ∨  end_reason ∈ {dropped_network, dropped_turn}
          ∨  (answered ∧ connected ∧ quality_poor(c))

  unclassifiable(c) = answered ∧ connected ∧ ¬dropped ∧ quality_unknown(c)
```

Lý do ngoài phạm vi TURN (`invite_undelivered`, `not_answered`, `rejected`, `cancelled_by_caller`, `app_crash`, `normal_hangup` mà chất lượng ok) **không** làm cuộc gọi bị tính tệ, nhưng cuộc gọi **vẫn ở trong cohort**. Với `pre_connect`, cuộc gọi đã connected nhưng không được bắt máy thì **không bao giờ** là poor hay unclassifiable (người dùng không trải nghiệm media). Chi phí của chúng được đo qua `allocation_seconds_unanswered` và guardrail `turn_utilization_p95`.

### 13.3 KPI theo tầng

**Tầng 1 — Metric chính**

| KPI | Định nghĩa |
|---|---|
| **`pcr_itt`** — Poor Call Rate, intention-to-treat | **Cohort** = mọi `call_session` của experiment đã được gán `arm` (I15), **kể cả** khi sau đó Selector timeout, static fallback, P2P, allocation lỗi, không gửi được lời mời hay không bắt máy. **Hai cận:** `pcr_itt_low` = Σ poor / \|cohort\|; `pcr_itt_high` = Σ (poor ∨ unclassifiable) / \|cohort\|. Đơn vị %, **càng thấp càng tốt** |

**Tầng 1b — Metric phụ quan trọng (có điều kiện)**

| KPI | Định nghĩa |
|---|---|
| `pcr_answered` (low/high) | Như trên nhưng mẫu số = cuộc gọi đã bắt máy trong cohort. Diễn giải là chất lượng **có điều kiện**, với giả định policy không ảnh hưởng việc bắt máy. Giả định này được **kiểm tra và báo cáo** (`answer_rate` theo nhánh), **không bao giờ dùng để đổi metric chính** |
| Thành phần | `ice_fail_rate`, `drop_rate`, `quality_poor_rate`, `unclassifiable_rate` (cùng mẫu số cohort) |
| Phễu | `invite_delivered_rate`, `answer_rate`, `selector_timeout_rate`, `static_fallback_rate`, `p2p_rate` |

**Tầng 2 — Guardrail** (non-inferiority, §14.4)

| Guardrail | Hướng | Margin δ |
|---|---|---|
| `ice_fail_rate` (mẫu số cohort ITT) | thấp | +0.2 điểm % |
| `drop_rate` (mẫu số cohort ITT) | thấp | +0.2 điểm % |
| `cst_technical_p95` = P95(`ice_connected_ts − checks_start_ts`) trên attempt `connected` **đầu tiên** của mỗi cuộc gọi; attempt thiếu `checks_start_ts` bị loại và tỉ lệ thiếu được báo cáo kèm | thấp | +10% |
| `ttfm_post_answer_p95` = P95(max(0, max_side(`first_media_received_ts`) − `answer_ts`)) | thấp | +10% |
| `selector_api_p95` | thấp | ≤ 50 ms (tuyệt đối) |
| `selector_availability` = 1 − (error + timeout)/req | cao | ≥ 99.9% (tuyệt đối) |
| `static_fallback_rate` | thấp | +0.2 điểm % |
| `turn_utilization_p95` (mọi TURN, mọi phút) | thấp | ≤ 85% (tuyệt đối) |
| `unclassifiable_rate` (độ đầy đủ telemetry) | thấp | +1.0 điểm % |
| `pcr_itt_high` theo từng `pair_group` | thấp | +0.5 điểm % |

**Tầng 3 — Chẩn đoán** (không dùng để kết luận thắng/thua; công thức chi tiết của từng chỉ số chẩn đoán được viết trong `contracts/kpi.yaml` lúc implement — chúng không ảnh hưởng luật kết luận §14.4)
`pnr` = Σ quality_poor / Σ (answered ∧ connected ∧ ¬quality_unknown) — chất lượng có điều kiện trên cuộc gọi đã nối, cùng quy tắc §13.2 · `population_media_rtcp_rtt_p50/p95` · `population_ice_stun_rtt_p95` · `population_loss` · `population_jitter_estimate_p95` · `mos_est` (E-model) · `max_epoch_p95` · `rank_of_used` · `est_vs_observed_mae` · `confidence_calibration` · `coverage_7d` · `ess` · `hhi_turn` · `alloc_success_rate` · `allocation_not_selected_rate` · `allocation_never_checked_rate` (khi có `ice_candidate_pair`) · `reserve_allocation_seconds` · `allocation_seconds_unanswered` · `blind_cost_ms` · regret (§14.6).

---

## 14. Đánh giá (Evaluation)

### 14.1 Estimand
Hiệu ứng ITT: `Δ = PCR_itt(Smart) − PCR_itt(Geo)` trên **cùng các yếu tố ngoại sinh**. Vì PCR có hai cận, Δ là một **khoảng** [`best`, `worst`] tính chéo theo §14.4. So sánh với Historical theo cùng cách.

### 14.2 Thiết kế trên simulator
- **Môi trường cô lập theo policy:** mỗi (policy, seed) là một lần chạy riêng, có `environment_dir` riêng chứa feature store, health state, tải TURN và cache riêng.
- **Yếu tố ngoại sinh dùng chung:** traffic (ai gọi ai, lúc nào, có bắt máy không, thời lượng dự định, thời điểm đổi mạng), lịch sự cố, mạng nền. Sinh trước, hoặc rút từ RNG có khóa theo thực thể và thời điểm, ví dụ `(seed, call_id, "answer")`, `(seed, call_id, leg, direction, window_idx, "noise")`, `(seed, turn_id, ts_bucket, "net")`. Số event do policy sinh ra **không được** làm xê dịch bất kỳ luồng ngẫu nhiên nào.
- **Yếu tố nội sinh** (tải, lịch sử, snapshot) được phép khác nhau. Đó là hiệu ứng cần đo.
- **Khởi đầu:** mọi policy dùng cùng `initial_snapshot_hash`. **Burn-in 3 ngày** bị loại khỏi đánh giá.
- **Tái lập:** cùng manifest thì ra cùng hash dữ liệu (có test).

### 14.3 Đơn vị độc lập và cỡ mẫu
- **Đơn vị độc lập = seed.** Với mỗi seed *r*, tính `d_r` trên các ngày sau burn-in.
- **Power analysis trên đúng estimand ITT:** chạy 3 seed thử nghiệm **chỉ để ước lượng phương sai** của `d_r`, rồi tính R cần thiết cho **MDE = 0.5 điểm %** với α = 0.05 hai phía, power 0.8. R cuối được ghi vào manifest trước khi chạy. Không đủ ngân sách thì báo cáo MDE thực tế.
- **Kiểm tra chéo** trong một lần chạy: block bootstrap theo (ngày × miền), giữ cặp Geo–Smart.

### 14.4 Luật kết luận (đóng băng trước `blind_benchmark`)
Với mỗi seed: `worst_r = pcr_itt_high(Smart) − pcr_itt_low(Geo)` và `best_r = pcr_itt_low(Smart) − pcr_itt_high(Geo)` (so sánh **chéo** hai cận).

- **Guardrail có hai loại.** *Tương đối* (δ dạng "+x điểm %" hoặc "+x%"): kiểm tra trên ΔG_j = G_j(Smart) − G_j(Geo), với "+x%" tính theo G_j(Geo). *Tuyệt đối* (δ dạng "≤ x" hoặc "≥ x"): kiểm tra trên chính G_j(Smart) — đạt khi `UpperCI95(G_j) < x` (hoặc `LowerCI95(G_j) > x` với guardrail "cao = tốt"); vi phạm khi CI nằm hoàn toàn phía sai.
- **Smart tốt hơn** ⇔ `UpperCI95(worst) < 0` **và** mọi guardrail đạt theo đúng loại của nó (guardrail có hai cận thì dùng cận bất lợi).
- **Smart tệ hơn** ⇔ `LowerCI95(best) > 0` **hoặc** tồn tại guardrail vi phạm (tương đối: `LowerCI95(ΔG_j) > δ_j`; tuyệt đối: CI nằm hoàn toàn phía sai ngưỡng).
- **Ngược lại: INCONCLUSIVE**, kể cả khi CI chỉ chạm margin.
- Guardrail theo `pair_group` dùng CI 98.33% (Bonferroni cho 3 nhóm).
- Kết luận chỉ áp dụng cho `data_source=synthetic` với các giả định trong sổ giả định của spec.

### 14.5 Sensitivity bắt buộc
Ngưỡng RTT 200/300/400 · loss 1/3/5 · jitter 10/30/50 · `PoorFraction` 0.1/0.2/0.3 · `connection_mode = pre_connect` (**chạy lại toàn bộ** KPI chính, guardrail và tải TURN; mô phỏng allocation sống trong lúc đổ chuông, kể cả cuộc gọi không được bắt máy, có TTL). Thứ hạng đổi chiều ⇒ kết luận ghi "phụ thuộc giả định".

### 14.6 Regret (chỉ sim, chẩn đoán; null khi không có truth hợp lệ)
Loss của một đường = PoorFraction tổng hợp theo truth trong thời gian cuộc gọi (định nghĩa trong `kpi.yaml`).
- `in_list_regret` = loss(đường đã đi) − min loss trên các tổ hợp trong `candidates`.
- `feasible_global_regret` = loss(đường đã đi) − min loss trên các tổ hợp **khả thi theo sự thật** tại thời điểm đó (`truth.available` ∧ `dim_turn.status=active` ∧ hỗ trợ transport). **Không** dùng health snapshot của Selector để xác định tính khả thi.
- `joint_path_regret` là **chính**. Regret từng bên chỉ tính khi cố định bên kia theo lựa chọn thực tế.
- Báo cáo kèm số tổ hợp khả thi. Giả định: một cuộc gọi đơn lẻ không làm thay đổi tải.

### 14.7 Pilot production (định hướng — chi tiết hóa ở W6)
- Ngẫu nhiên hóa ở cấp cuộc gọi **không** cho kết luận nhân quả khi các nhánh dùng chung TURN pool. Ưu tiên `randomization_unit ∈ {region, time_block}` (switchback).
- **Washout** phải bao phủ toàn bộ horizon carryover: TTL allocation, P99 thời lượng cuộc gọi, cửa sổ health rolling, TTL cache, và tuổi snapshot/state của policy. Hoặc **cô lập / reset** các state đó khi chuyển nhánh. Cuộc gọi trong washout bị loại khỏi phân tích.
- Shadow mode: không được chấm bằng PCR, chỉ OPE/regret. Workload shadow phải được **giới hạn tài nguyên** (theo dõi `shadow_req_count`).
- Không kiểm soát được interference ⇒ pilot chỉ là **đánh giá vận hành**.

---

## 15. Ánh xạ sang telemetry thật

| Field | Nguồn W3C / production | Ghi chú |
|---|---|---|
| `media_rtcp_rtt_*` | `remote-inbound-rtp.roundTripTime` (giây) × 1000, theo SSRC audio | Chỉ có sau RTCP RR với DLSR ≠ 0. Không có thì null |
| `ice_stun_rtt_*` | `candidate-pair.currentRoundTripTime` × 1000 | RTT của STUN check |
| `jitter_estimate_*` | `inbound-rtp.jitter` (giây) × 1000 | Ước lượng tại thời điểm lấy mẫu |
| loss | Δ`packetsLost` / Δ(`packetsReceived` + `packetsLost`) | `packetsLost` có thể âm; counter reset sau restart → bỏ cửa sổ |
| `selected_*_candidate_type`, `relay_turn_*` | `transport.selectedCandidatePairId` → `local-candidate` / `remote-candidate` (`candidateType`, `url`) → `dim_turn.hostname` | |
| `path_leg_measurement` | Hệ thống đo của công ty (mentor) và mesh probe | Phương pháp đo **chưa xác minh** |
| Assignment, lifecycle | Spring Boot Signaling | I14, I15 là yêu cầu kiến trúc |

---

## 16. Version và quy trình thay đổi

- **SemVer.** MAJOR: xóa hoặc đổi tên cột, đổi nghĩa hoặc đơn vị. MINOR: thêm cột nullable hoặc giá trị enum. PATCH: sửa mô tả.
- Mọi thay đổi: PR sửa tài liệu này **và** `contracts/` cùng lúc, cập nhật changelog, **Hiệp và Đoàn cùng approve**, CI xanh (schema + `kpi.yaml` + test bất biến).
- Sau FREEZE v0.2.0: vấn đề mới vào **assumption log** (sổ giả định A1…An, spec §16) hoặc issue; chỉ mở version mới khi vấn đề làm sai dữ liệu hoặc kết luận.

## 17. Câu hỏi mở (không chặn freeze — có mặc định)

| # | Câu hỏi | Ai | Mặc định |
|---|---|---|---|
| Q1 | Đoàn cần thêm feature nào ngoài §9? | Đoàn | Như §9 |
| Q2 | Thang `score` và cách tính `confidence` | Đoàn | 0–1, cao = tốt |
| Q3 | k = 4 hay 8 | Mentor / Đoàn | 4 |
| Q4 | Production đo ms từng chặng bằng cách nào | Mentor | `measurement_kind` + `clock_sync_err_ms` bắt buộc |
| Q5 | ICE bắt đầu lúc đổ chuông hay sau khi bắt máy | Mentor / đội WebRTC | `post_answer` (giả định chưa xác minh) |

## Changelog

- **0.2.0** (2026-11-04), tổng hợp 5 vòng review:
  - **Thay** I5 tuyến tính bằng các quan hệ nhân quả; sửa I6 (pre_connect) và I9 (WARN, hai chiều, so với media RTT).
  - Thêm I13 (event + ingest < cutoff, snapshot bất biến), I12 (`published_ts`), I14 (Selector không chặn), I15 (gán nhánh trước quyết định), I16 (KPI chỉ từ KPI-grade), I17 (sampling).
  - Bảng mới `call_stats_epoch` (100%, histogram theo cửa sổ neo cố định), `ice_candidate_pair` (tùy chọn), `run_manifest`.
  - `path_leg_measurement`: bỏ `one_way_ms` và `method=alloc`; thêm `value_ms` + `measurement_kind`, `granularity`, `measurement_point`, `method_version`.
  - `turn_allocation` + `allocation_id`, `ice_generation`. `ice_attempt` + `checks_start_ts`, `ice_connected_ts`, `dtls_connected_ts`, loại candidate được chọn, `*_allocation_id`.
  - `call_session` + `connection_mode`, các field experiment. `call_outcome` + `ring_ts`, metadata sampling. Bỏ aggregate khỏi `call_outcome`.
  - **Bỏ** `ice_attempt.cst_ms` và `ttfm_ms`: thay bằng các timestamp gốc, còn CST/TTFM được tính trong KPI (`cst_technical_p95`, `ttfm_post_answer_p95`). Bỏ `call_stats_5s.rtt_ms` chung chung: thay bằng `media_rtcp_rtt_ms` và `ice_stun_rtt_ms`.
  - Sampling: critical 100%, bình thường 10% theo SHA-256, ring buffer.
  - Metric chính: **`pcr_itt`** (cohort gán trước quyết định, hai cận) thay cho PNR; RTT dùng `media_rtcp_rtt`; PoorFraction gộp theo cửa sổ thay cho max P95 theo epoch.
  - Mục Evaluation mới: môi trường cô lập, RNG có khóa, seed là đơn vị, power analysis, luật kết luận chéo hai cận, non-inferiority, regret 3 loại, pilot switchback.
  - Feature store: cutoff 00:00 giờ VN, `published_ts`, `content_hash`, `feat_turn_alloc_latency` tách riêng.
- **0.1.0** (2026-11-04): bản nháp đầu tiên.
