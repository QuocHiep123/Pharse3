# Data Contract v0.4.0 — TURN Selector Intelligence

- **Ngày:** 2026-11-04 · **Soạn:** Hiệp · **Duyệt:** Hiệp + Đoàn (bắt buộc cả hai)
- **Trạng thái:** v0.4.0 — **FROZEN**. v0.3.0 và v0.4.0 chỉ **bổ sung** so với v0.2.0 (v0.3.0: kiến trúc hai mặt phẳng §0.2; v0.4.0: sẵn sàng cho production §0.3). v0.4.0 cũng gồm các **sửa lỗi theo audit độc lập**: một số định nghĩa được làm rõ hoặc sửa vì bản cũ mơ hồ hoặc sai. Thay đổi về nghĩa: poor chia thành ba nhánh rời nhau và tính cả cuộc gọi đã bắt máy mà không bao giờ nối được (§13.2); guardrail `ice_fail_rate` → `setup_fail_rate`; KPI chỉ tính cuộc gọi 1-1 (I21). Chi tiết ở changelog
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
 dim_turn · dim_turn_endpoint · dim_asn · dim_user
 run_manifest (mỗi lần chạy sim / mỗi experiment)
 ─────────── pipeline ───────────► clean-layer (§8) ──► feature store (§9, Đoàn đọc) · KPI (§13)
 truth_leg_5m · incident_truth · dirt_log    (ẨN — chỉ eval/ đọc, §11)
```

### 0.1 Hai loại dữ liệu (quan trọng nhất)

| Loại | Bảng | Độ phủ | Được dùng cho |
|---|---|---|---|
| **KPI-grade** | `call_session`, `selector_decision`, `turn_allocation`, `ice_attempt`, `call_outcome`, `call_stats_epoch`, `path_leg_measurement[granularity=epoch_summary]`, `turn_health_1m`, `service_health_1m` | **100% cuộc gọi** | Mọi KPI chính và guardrail (§13), feature store (§9) |
| **Diagnostic** | `call_stats_5s` (trừ khi nó là đầu vào 100% của `call_stats_epoch[derivation=pipeline]`, I22), `path_leg_measurement[granularity=window_5s]`, `ice_candidate_pair` | Lấy mẫu (§6.3) hoặc tùy telemetry | Điều tra, Decision Trace, biểu đồ chi tiết. **Không bao giờ** dùng cho KPI quyết định (I16) |

### 0.2 Kiến trúc: hai mặt phẳng (xác nhận 2026-11-04)

```
 MẶT PHẲNG ĐIỀU KHIỂN — đi qua BE (backend signaling, Spring Boot)
   A ⇄ BE ⇄ B       lời mời, đổ chuông, bắt máy, SDP offer/answer, ICE candidate
   BE → Selector    lúc A bấm gọi (initial) và lúc máy B đổ chuông (refined)

 MẶT PHẲNG MEDIA — KHÔNG đi qua BE (một PeerConnection A↔B)
   A → TURN(A) → TURN(B) → B        relay_relay
   A → TURN(X) → B                  relay_same (hai bên dùng chung một TURN)
   A → TURN(A) → B  ·  A → B        relay_direct · P2P — chỉ khi ice_transport_policy = all
```

- **BE = producer `signaling`** trong toàn bộ contract: tạo `call_session`, gán nhánh thí nghiệm, gọi Selector và ghi `selector_decision`, ghi `ring_ts`, `answer_ts`.
- **BE không nằm trên đường media**, nên không cộng gì vào RTT, loss, jitter và không ảnh hưởng `pcr_itt`. BE chỉ ảnh hưởng **thời gian thiết lập**, vì mọi tin nhắn signaling đi qua BE. Phần này được đo bằng `*_signaling_rtt_ms` và chỉ số chẩn đoán `setup_breakdown_post_answer` (§13.3).
- **Ý nghĩa số đo:** vì chỉ có một PeerConnection A↔B, `media_rtcp_rtt` và `ice_stun_rtt` là RTT **đầu-cuối qua cả hai TURN**; `packetsLost` và `jitter` ở phía nhận phản ánh **toàn đường** (research/06).
- **Coupling giữa hai bên:** TURN(A) và TURN(B) chỉ ràng buộc nhau qua chặng giữa `TURN(A)→TURN(B)` (và trường hợp dùng chung một TURN). Chặng giữa nhỏ (nội địa) thì chọn gần nhất từng bên là xấp xỉ tốt; chặng giữa lớn (xuyên lục địa) thì cần joint ranking (research/07 §3.1).
- **Nếu sau này media đi qua media server (SFU):** mỗi bên có PeerConnection riêng tới server, các số đo trên chỉ còn phản ánh **nửa đường** và định nghĩa PCR phải đổi ⇒ bắt buộc mở **MAJOR** version (research/05, /06 đã phân tích sẵn).

### 0.3 Sẵn sàng cho production (v0.4.0)

Simulator có thể giả định mọi thứ đồng nhất, production thì không. Contract ghi nhận 5 điều sau để dữ liệu production không bị sai:

| # | Ngoài đời | Contract xử lý bằng |
|---|---|---|
| 1 | Nhiều nền tảng, phiên bản app/SDK, OS, thiết bị cùng chạy; getStats khác nhau giữa các nền tảng | Thông tin client trong `ctx` (§4). Mọi KPI cắt được theo `platform`, `app_version`. DQ phát hiện metric đổi đột ngột sau một bản phát hành app (§8.5) |
| 2 | Một hostname TURN có thể trỏ tới nhiều máy (DNS round-robin, geo-DNS, anycast) | Lưu `turn_url` và IP thật (`turn_server_ip`, `relayed_ip`); ánh xạ IP → máy qua `dim_turn_endpoint` (§3.4, §8.6); I19 |
| 3 | Người nghe có nhiều thiết bị cùng đổ chuông | `device_id` trên mọi bảng phía client; `answered_device_id`; I20 |
| 4 | Có cuộc gọi nhóm, hoặc cuộc gọi 1-1 chuyển thành nhóm giữa chừng | `call_type`, `converted_to_group`, `converted_ts`; KPI chỉ tính cuộc gọi 1-1 (§13.2, I21) |
| 5 | SDK có thể không tự tính được histogram theo epoch | Hai cách cung cấp `call_stats_epoch`: SDK tự tính, hoặc pipeline tính từ `call_stats_5s` gửi 100% (`derivation`, I22) |
| — | Dữ liệu IP | Chỉ lưu IP của **máy chủ TURN** (hạ tầng). IP của người dùng (candidate host/srflx/prflx) **không bao giờ** được lưu |

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
| Cột trong khóa | Không bao giờ null: dùng `'unknown'` (không biết) hoặc `'-'` (không áp dụng) |

### 1.1 Cột chung của mọi bảng event (raw)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `event_id` | uuid | không | Duy nhất. Dùng dedup |
| `contract_version` | text | không | Version contract mà producer dùng khi ghi (hiện tại `"0.4.0"`) |
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
| `platform` | `ios`, `android`, `web`, `desktop`, `unknown` |
| `call_type` | `one_to_one`, `group`, `unknown` |
| `stats_derivation` | `sdk` (SDK tự tính trên thiết bị), `pipeline` (pipeline tính từ `call_stats_5s` gửi 100%) |
| `info_level` | `full`, `caller_only`, `country_only`, `none` |
| `decision_phase` | `initial`, `refined`, `restart` |
| `decision_mode` | `live`, `shadow` |
| `decision_source` | `api`, `static_fallback`, `cache` |
| `connection_mode` | `post_answer` (ICE bắt đầu sau khi bắt máy — **mặc định, giả định chưa xác minh**), `pre_connect` (ICE trong lúc đổ chuông) |
| `ice_transport_policy` | `relay` (chỉ dùng relay candidate — **mặc định, suy ra từ mô tả của mentor "ICE đi TURN top 1 của mỗi bên", chưa xác minh**), `all` (cho phép P2P và `relay_direct`) |
| `transport` | `udp`, `tcp`, `tls` |
| `leg_type` | `user_turn`, `turn_turn` |
| `direction` | `forward` (theo chiều caller→callee), `reverse` |
| `measure_method` | `inband`, `mesh_probe`, `idle_probe` |
| `measurement_kind` | `one_way`, `rtt` |
| `measurement_point` | `client`, `turn_server`, `probe_agent` |
| `granularity` | `epoch_summary`, `window_5s` |
| `path_type` | `relay_relay`, `relay_same`, `relay_direct`, `p2p_host`, `p2p_srflx`, `unknown` — **suy từ cặp candidate được chọn**: (relay, relay) → `relay_same` nếu `actual_turn_id` hai đầu trùng (§8.6), ngược lại `relay_relay`; đúng một đầu relay → `relay_direct`; cả hai `host` → `p2p_host`; không đầu nào relay và có `srflx`/`prflx` → `p2p_srflx`; không xác định → `unknown` |
| `candidate_type` | `host`, `srflx`, `prflx`, `relay`, `unknown` |
| `ice_trigger` | `initial`, `fallback`, `restart_network_change`, `restart_failure` |
| `ice_state` | `connected`, `failed`, `timeout`, `cancelled` |
| `end_reason` | `normal_hangup`, `invite_undelivered`, `not_answered`, `rejected`, `cancelled_by_caller`, `ice_failed`, `dropped_network`, `dropped_turn`, `app_crash`, `unknown` |
| `pair_group` | `VN_VN`, `VN_INTL`, `INTL_INTL` |
| `health_status` | `healthy`, `degraded`, `overloaded`, `down`, `maintenance` |
| `alloc_error` | `none`, `timeout`, `unauthorized_401`, `forbidden_403`, `quota_486`, `capacity_508`, `unreachable`, `other` |
| `stats_status` | `kept_critical`, `kept_sampled`, `not_sampled`, `truncated`, `lost`, `not_applicable` |
| `quality_assessment_status` | `assessed`, `partially_assessed`, `unclassifiable`, `not_applicable` (ánh xạ ở §8.4) |
| `randomization_unit` | `run` (sim: cả môi trường), `call`, `user`, `region`, `time_block` |
| `run_kind` | `scripted`, `blind_benchmark`, `dev` |
| `conn_state` | `connected`, `disconnected`, `failed` |

---

## 3. Dimension

### 3.1 `dim_turn` (SCD2)
`turn_id` (`<country>-<city>-<host>-<nn>`), `hostname` (riêng của máy, hoặc chung của một pool — khi đó chỉ IP mới xác định được máy, §3.4), `country`, `vn_region`, `city`, `lat`, `lon`, `host_isp`, `host_asn`, `capacity_alloc`, `transports[]`, `status` {`active`,`maintenance`,`retired`}, `valid_from`, `valid_to` (null = còn hiệu lực).

### 3.2 `dim_asn`
`asn` (PK), `isp`, `country`, `access_kind` {`fixed`,`mobile`,`mixed`}.

### 3.3 `dim_user`
`user_hash` (PK), `home_country`, `home_vn_region`, `home_city`, `home_isp`, `home_asn`, `primary_network`, `cohort` {`normal`,`cold_start`}, `created_at`.

### 3.4 `dim_turn_endpoint` (SCD2 — IP của từng máy TURN)
`ip`, `turn_id`, `role` {`listen` (IP client gửi tới), `relay` (IP dùng cho relayed address), `both`}, `hostname` (hostname trỏ tới IP này, nếu có), `valid_from`, `valid_to`. Một hostname có thể trỏ tới nhiều `turn_id` (pool); một IP chỉ thuộc **một** `turn_id` tại một thời điểm. Đây là cách duy nhất biết chính xác client đã tới **máy** nào (§8.6). Nguồn: đội hạ tầng.

---

## 4. Object `ctx` (bối cảnh một bên tại lúc quyết định)

`user_hash` (null nếu chưa biết) · `country` · `vn_region` · `city` · `isp` · `asn` · `network_type` · `geo_source` {`ip_geo`,`sdk_claimed`,`both`} · `geo_mismatch` (bool) · `segment_key` (§9.0). Field chưa biết = `unknown`. Postgres làm phẳng với prefix `self_` / `peer_` / `caller_` / `callee_`.

**Thông tin client (v0.4.0):** `device_id` (HMAC-SHA256 của id cài đặt app, cùng cách với `user_hash`) · `platform` · `os_version` · `app_version` · `sdk_version` · `device_model` · `browser_name`, `browser_version` (chỉ web). Mục đích: tách lỗi do phiên bản app/nền tảng khỏi lỗi do TURN, và biết nền tảng nào hỗ trợ field nào (getStats khác nhau giữa các nền tảng). Khi gọi mù, các field này của `peer_ctx` là `unknown`.

---

## 5. Event — luồng cuộc gọi

### 5.1 `call_session` (Signaling tạo khi A bấm gọi — **trước mọi quyết định**)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id` | uuid PK | không | |
| `caller_hash`, `callee_hash` | text | không | |
| `initiated_ts` | timestamptz | không | |
| `media_kind` | enum | không | |
| `call_type` | enum | không | `one_to_one`, `group`, hoặc `unknown` (dữ liệu cũ, mặc định). Chỉ `one_to_one` vào KPI (I21); số cuộc gọi bị loại vì `call_type ≠ one_to_one` được báo cáo theo nhánh |
| `caller_device_id` | text | không | Thiết bị của A (`'unknown'` nếu không biết) |
| `connection_mode` | enum | không | |
| `ice_transport_policy` | enum | có | Cấu hình ICE mà BE gửi cho client. null = không rõ |
| `be_region` | text | có | Vùng/datacenter của BE xử lý cuộc gọi (mã IATA thành phố, ví dụ `SGN`) |
| `be_instance` | text | có | Tên máy BE cụ thể (tên, không phải IP) |
| `experiment_id` | text | có | null = không thuộc thí nghiệm nào |
| `arm` | text | có | Bắt buộc khi có `experiment_id`. Trên sim = tên policy của môi trường |
| `randomization_unit` | enum | có | |
| `experiment_cluster_id` | text | có | Cụm ngẫu nhiên hóa (region, time block…). Trên sim = `sim_run_id` |
| `assignment_ts` | timestamptz | có | **Phải ≤ `request_ts` của decision đầu tiên** (I15) |
| `assignment_hash` | text | có | Hash theo quy tắc §1 trên `experiment_id ‖ khóa của đơn vị ngẫu nhiên`; ánh xạ sang `arm` theo tỉ lệ trong experiment registry. Trên sim, `experiment_id` và `arm` là **bắt buộc** |
| `scenario_tag` | text | có | Chỉ sim. **Chỉ mô tả loại cuộc gọi**, không bao giờ mã hóa sự cố ẩn (§12) |

### 5.2 `selector_decision` (một dòng cho mỗi `decision_id` × `side` × thiết bị)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `decision_id` | uuid | không | Chung cho hai bên của một request |
| `call_id`, `side`, `phase` | | không | |
| `device_id` | text | không | Thiết bị mà quyết định này dành cho (= `self_ctx.device_id`; `'unknown'` nếu không biết). Mỗi thiết bị của B đổ chuông là **một request `refined` riêng, một `decision_id` riêng**; dòng `caller` trong request đó áp dụng cho đúng cặp thiết bị này. ICE attempt trỏ `decision_id` của thiết bị đã bắt máy (I20) |
| `request_ts` | timestamptz | không | |
| `response_ts`, `api_latency_ms` | | có | null khi API không trả lời. `api_latency_ms` do **BE** đo (BE là bên gọi Selector, §0.2) |
| `policy_version` | text | không | `geo_baseline@0.1`, `smart@0.3.1`, `static@1` |
| `decision_mode`, `decision_source`, `info_level` | enum | không | |
| `self_ctx`, `peer_ctx` | ctx | không | `peer_ctx` = **những gì biết lúc đó** |
| `k` | int | không | Mặc định 4 |
| `candidates` | array[Candidate] | không | Đúng `min(k, số TURN khả dụng sau khi lọc)`, sắp theo rank; thiếu thì `fallback_reason = insufficient_candidates` |
| `filtered_out` | array[{turn_id, reason}] | không | reason: `down`, `overloaded`, `degraded`, `maintenance`, `policy` |
| `chosen_rank` | int | không | Rank client được yêu cầu thử trước |
| `is_exploration` | bool | không | |
| `exploration_epsilon` | float | không | |
| `confidence` (0–1), `confidence_level` {high, medium, low} | | không | |
| `fallback_reason` | text | có | Backoff thiếu dữ liệu, ví dụ `backoff_L1` |
| `feature_snapshot_id`, `health_snapshot_id` | text | không* | *null chỉ khi `decision_source=static_fallback` |
| `error_code` | text | có | |

**Candidate:** `rank`, `turn_id`, `score` (cao = tốt, chỉ so trong một decision), `score_components` map (gồm `backoff_level`: cấp segment §9.0 đã dùng cho candidate này), `est_leg_ms` (null), `est_path_ms` (null), `reason_codes[]`, `propensity` (P(candidate này là `chosen_rank`); tổng = 1).

### 5.3 `turn_allocation` (một dòng cho mỗi allocation)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `allocation_id` | uuid PK | không | Do client sinh. Dùng để gắn với ICE |
| `call_id`, `decision_id`, `side` | | không | |
| `device_id` | text | không | Thiết bị tạo allocation (`'unknown'` nếu không biết) |
| `turn_id`, `rank`, `transport` | | không | |
| `turn_url` | text | có | URL TURN mà client thực sự dùng (`turn:`/`turns:` + hostname hoặc IP + port) |
| `turn_server_ip` | text | có | IP của máy TURN mà client gửi tới (sau khi phân giải hostname), nếu lấy được |
| `relayed_ip` | text | có | IP của relayed address mà TURN cấp (local candidate loại `relay`). Là IP của **máy chủ TURN**, không phải của người dùng |
| `ice_generation` | int | không | Thế hệ ICE lúc tạo allocation (0, tăng mỗi ICE restart) |
| `attempt_seq` | int | có | null nếu chưa gắn với lần thử cụ thể |
| `is_preallocation` | bool | không | |
| `request_ts` | timestamptz | không | |
| `response_ts`, `alloc_ms` | | có | null nếu timeout. `alloc_ms` là **allocation latency** (gồm cả vòng 401 và thời gian server xử lý), **không phải RTT, không phải one-way** |
| `success` | bool | không | `success = true` ⇔ `error_code = none` |
| `error_code` | enum `alloc_error` | không | |
| `released_ts`, `release_reason` {`not_needed`,`call_end`,`kept_for_failover`,`expired`,`unanswered`,`other_device_answered`} | | có | |

### 5.4 `ice_attempt` (một dòng cho mỗi lần thử: lần đầu, fallback, restart — PK (`call_id`, `attempt_seq`))

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id`, `attempt_seq`, `ice_generation` | | không | |
| `caller_device_id`, `callee_device_id` | text | không | Hai thiết bị của kết nối này (callee = thiết bị đã bắt máy, I20); `'unknown'` nếu không biết |
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
| `path_type` | enum | có | **Suy từ hai field trên** theo bảng ở §2 — không giả định luôn là relay_relay. `unknown` khi không xác định; null chỉ khi attempt không `connected` (áp dụng cả cho `selected_*_candidate_type`) |
| `relay_turn_caller`, `relay_turn_callee` | text | có | `turn_id` suy từ URL/hostname khi hostname chỉ trỏ **một** máy; null nếu bên đó không đi relay hoặc hostname là pool. **Máy thực tế** luôn được xác định lại từ IP (§8.6) |
| `relayed_ip_caller`, `relayed_ip_callee` | text | có | IP relayed address của hai đầu trong cặp candidate được chọn. **Chỉ ghi khi candidate là `relay`** (IP máy chủ TURN); candidate host/srflx/prflx không bao giờ được lưu IP, và không lưu `relatedAddress`/`relatedPort` (chứa IP người dùng) |
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
| `granularity` | enum | không | `epoch_summary` (100% cuộc gọi: một dòng / call × epoch × leg × direction; với probe: một dòng / khoảng tổng hợp) hoặc `window_5s` (chỉ cuộc gọi được lấy mẫu) |
| `method` | enum | không | `inband`, `mesh_probe`, `idle_probe` (**không có `alloc`**) |
| `measurement_kind` | enum | không | `one_way` (đo trực tiếp, cần đồng bộ đồng hồ) hoặc `rtt` |
| `measurement_point` | enum | không | |
| `method_version` | text | không | |
| `window_start_ts`, `window_end_ts` | timestamptz | không | |
| `call_id`, `attempt_seq`, `ice_generation`, `network_epoch` | | có | null với probe |
| `leg_type`, `direction` | enum | không | |
| `side` | enum | có | Với `user_turn` |
| `src_id`, `dst_id` | text | không | Theo chiều gói tin |
| `device_id` | text | không | Với `user_turn`: thiết bị của user; `'-'` với `turn_turn` |
| `user_segment_key`, `network_type` | | có | Với `user_turn` |
| `value_ms` | float | có | Trung bình trong cửa sổ hoặc epoch, **đúng loại `measurement_kind`** |
| `value_ms_p95` | float | có | Chỉ với `epoch_summary`: P95 trong epoch |
| `n_samples` | int | không | |
| `clock_sync_err_ms` | float | có | Bắt buộc khi `measurement_kind=one_way` |
| `loss_pct`, `jitter_ms`, `packets` | | có | |
| `missing_reason` | text | có | |

Đường A→B = `user_turn(caller, forward)` + `turn_turn(TA→TB, forward)` + `user_turn(callee, forward)`. Khi `path_type=relay_same` không có dòng `turn_turn` (= 0). **Bảng này chỉ dùng cho phân rã, chẩn đoán và feature — không bao giờ dùng làm nhãn PCR** (§13).

**Khóa duy nhất** (ngoài `event_id`): (`call_id`, `attempt_seq`, `network_epoch`, `leg_type`, `side`, `device_id`, `src_id`, `dst_id`, `direction`, `method`, `measurement_kind`, `granularity`, `window_start_ts`). **Probe** (`call_id = null`) dùng `granularity = epoch_summary` với khoảng [`window_start_ts`, `window_end_ts`] (ví dụ 5 phút) và `network_epoch = null`; probe là nguồn hợp lệ cho **feature** (§9) nhưng không cho KPI §13.

### 5.7 `call_stats_epoch` (**KPI-grade, 100%**)

Một dòng cho mỗi (`call_id`, `endpoint_side`, `device_id`, `media_kind`, `network_epoch`). Có **hai cách cung cấp** (field `derivation`): SDK tự tính trên thiết bị và gửi khi epoch kết thúc (`sdk`), hoặc SDK gửi `call_stats_5s` cho **100%** cuộc gọi và pipeline tính bảng này theo đúng cùng quy tắc (`pipeline`, I22). Hai cách phải cho ra kết quả giống hệt trên cùng dữ liệu (có test, §14.2). Mỗi (cuộc gọi, endpoint, thiết bị) chỉ có **một** `derivation` được dùng cho KPI: endpoint tự gửi epoch thì dùng `sdk`; chỉ endpoint ở chế độ gửi thô mới có dòng `pipeline`. Dòng `pipeline` tính thêm cho một endpoint `sdk` chỉ tồn tại trong test tương đương (S24) và không bao giờ vào KPI.

**Cửa sổ** (độ dài `window_s`, mặc định 5 giây):
- **Neo theo từng endpoint, trên đồng hồ của endpoint đó:** `anchor_ts` = thời điểm endpoint ghi nhận `ice_connected` **lần đầu** trong cuộc gọi; cửa sổ thứ *i* = [anchor + i·w, anchor + (i+1)·w). Neo **không** đặt lại sau ICE restart.
- **Thuộc epoch nào:** epoch chứa **điểm giữa** của cửa sổ (epoch là khoảng [bắt đầu, kết thúc)).
- **Đánh giá được** khi đồng thời: (a) nằm trọn trong [`answer_ts`, min(`end_ts`, `converted_ts`)] — người dùng thực sự nghe, trước khi chuyển thành gọi nhóm; (b) không giao với khoảng gián đoạn do restart [`end_ts` của attempt cũ, `ice_connected_ts` của attempt mới); (c) metric có số đo hợp lệ trong cửa sổ: RTT cần RTCP RR với DLSR ≠ 0; loss cần Δexpected > 0 và Δlost ≥ 0; jitter cần giá trị không null. Vì vậy với `pre_connect`, cửa sổ trong lúc đổ chuông không bao giờ được đánh giá.
- **Mốc thời gian:** SDK dùng thời điểm nó quan sát cục bộ (`answer` nhận qua signaling, kết thúc cuộc gọi); pipeline dùng `event_ts_corrected` (§8.1). Test tương đương (§14.2) chạy với độ lệch đồng hồ bằng 0.
- **Bucket:** đóng trái, mở phải. Key chuẩn: RTT `lt100|100_200|200_300|300_400|ge400`; loss `lt1|1_3|3_5|ge5`; jitter `lt10|10_30|30_50|ge50`. Histogram là `{}` (không null) khi không có cửa sổ đánh giá được.
- **Dòng do pipeline tính** (`derivation = pipeline`): `producer = client_sdk` (kế thừa), `event_ts = epoch_end_ts`, `ingest_ts` = max `ingest_ts` của các dòng 5s đầu vào, `event_id` = UUIDv5 tất định từ (`call_id`, `endpoint_side`, `device_id`, `media_kind`, `network_epoch`, `derivation`).

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id`, `endpoint_side`, `media_kind`, `network_epoch` | | không | `endpoint_side` = endpoint báo cáo |
| `device_id` | text | không | Thiết bị báo cáo (`'unknown'` nếu không biết) |
| `derivation` | enum `stats_derivation` | không | |
| `window_s` | int | không | Độ dài cửa sổ, mặc định 5. Dữ liệu khác `window_s` không được gộp chung |
| `epoch_start_ts`, `epoch_end_ts` | timestamptz | không | |
| `audio_active_duration_s` | float | có | Thời gian có media audio thực sự (null với `media_kind = video`) |
| `first_media_sent_ts`, `first_media_received_ts` | timestamptz | có | Tại endpoint này, trong epoch này |
| `packets_expected`, `packets_lost` | int | có | **Luồng inbound** tại endpoint này |
| `media_rtcp_rtt_hist` | map<bucket, int> | không | Số cửa sổ theo bucket `<100,100–200,200–300,300–400,≥400` ms. RTT của **luồng outbound** của endpoint này (`remote-inbound-rtp.roundTripTime`, theo SSRC) |
| `loss_hist` | map<bucket, int> | không | Bucket `<1,1–3,3–5,≥5` %, loss inbound của cửa sổ = Δlost / Δexpected |
| `jitter_estimate_hist` | map<bucket, int> | không | Bucket `<10,10–30,30–50,≥50` ms, jitter estimate inbound (`inbound-rtp.jitter`) |
| `rtt_windows_assessable`, `loss_windows_assessable`, `jitter_windows_assessable` | int | không | Số cửa sổ có số đo hợp lệ **cho từng metric** |
| `valid_rtt_samples`, `valid_jitter_samples` | int | không | Số mẫu hợp lệ. RTT chỉ hợp lệ sau khi có RTCP RR với DLSR ≠ 0 |
| `media_rtcp_rtt_p50`, `media_rtcp_rtt_p95` | float | có | Chẩn đoán |
| `ice_stun_rtt_p50`, `ice_stun_rtt_p95` | float | có | `candidate-pair.currentRoundTripTime` — RTT của STUN check, **metric riêng, không thay cho media RTT** |
| `jitter_estimate_p95` | float | có | P95 của **các ước lượng jitter đã lấy mẫu**, không phải packet jitter |
| `measurement_coverage` | float 0–1 | không | Tỉ lệ cửa sổ đánh giá được cho **cả ba** metric / tổng cửa sổ của epoch |
| `quality_rule_version` | text | không | Phiên bản bộ bucket |

### 5.8 `call_stats_5s` (**diagnostic, lấy mẫu**)
Một dòng mỗi cửa sổ: PK (`call_id`, `endpoint_side`, `device_id`, `media_kind`, `window_idx`). Cùng quy tắc cửa sổ như §5.7. Khi `derivation = pipeline`, bảng này được gửi cho 100% cuộc gọi và là đầu vào của KPI-grade (I22), nên phải có đủ các cột dưới đây để pipeline tính lại đúng §5.7.

| Cột | Mô tả |
|---|---|
| `window_s`, `quality_rule_version` | Như §5.7 |
| `window_start_ts` | Đầu cửa sổ, theo đồng hồ endpoint |
| `network_epoch`, `network_type` | |
| `media_rtcp_rtt_ms`, `rtt_sample_valid` | RTT của luồng outbound; `rtt_sample_valid` = có RTCP RR với DLSR ≠ 0 trong cửa sổ |
| `ice_stun_rtt_ms` | Chẩn đoán |
| `jitter_estimate_ms`, `jitter_sample_valid` | |
| `packets_expected`, `packets_lost`, `loss_pct` | **Δ trong cửa sổ** (không phải giá trị cộng dồn); `loss_pct` = Δlost / Δexpected khi hợp lệ |
| `audio_active_s` | Số giây có audio thật trong cửa sổ |
| `first_media_sent_ts`, `first_media_received_ts` | Chỉ có ở cửa sổ chứa sự kiện đó |
| `restart_gap` | bool: cửa sổ giao với khoảng gián đoạn do restart |
| `bitrate_send_kbps`, `bitrate_recv_kbps` | |
| `conn_state` | enum `conn_state` |

### 5.9 `call_outcome` (một dòng mỗi cuộc gọi — BE ghi, gồm các mốc signaling của BE và số liệu SDK gửi lúc kết thúc)

| Cột | Kiểu | Null | Mô tả |
|---|---|---|---|
| `call_id` | uuid PK | không | |
| `ring_ts` | timestamptz | có | Máy B nhận lời mời và đổ chuông. null nếu `invite_undelivered` |
| `answer_ts` | timestamptz | có | Người dùng B **bấm nghe** (sự kiện Signaling, không phải SDP Answer) |
| `caller_signaling_rtt_ms`, `callee_signaling_rtt_ms` | float | có | RTT giữa app và BE trên kênh signaling (ví dụ ping/pong websocket), đo gần lúc gọi. Chẩn đoán: giải thích phần thời gian thiết lập do BE (§13.3) |
| `answered` | bool | không | |
| `answered_device_id` | text | có | Thiết bị đã bắt máy. Null chỉ khi `answered = false`; đã bắt máy mà không biết thiết bị thì `'unknown'` |
| `n_devices_rung` | int | có | Số thiết bị của B đã đổ chuông |
| `connected` | bool | không | Có ít nhất một ICE attempt `connected` |
| `end_ts` | timestamptz | không | |
| `duration_s` | float | có | Từ `answer_ts` tới `end_ts` |
| `end_reason` | enum | không | `ice_failed` chỉ khi đã bắt máy nhưng **chưa bao giờ** nối được media (I23); restart thất bại sau khi đã nối là `dropped_network` |
| `dropped` | bool | không | Kết thúc bất thường do mạng/TURN **sau khi đã bắt máy và đã connected**. `dropped = true` ⇔ `end_reason ∈ {dropped_network, dropped_turn}` (I24); `app_crash` không phải drop |
| `caller_ctx_final`, `callee_ctx_final` | ctx | không | Context thật, join muộn |
| `pair_group` | enum | không | |
| `converted_to_group` | bool | có | Cuộc gọi 1-1 chuyển thành nhóm giữa chừng (null ≡ false) |
| `converted_ts` | timestamptz | có | Thời điểm chuyển. Cửa sổ sau mốc này không được đánh giá (I21) |
| `n_ice_attempts`, `n_network_changes` | int | không | |
| `stats_status` | enum | không | Trạng thái dữ liệu **diagnostic** (`call_stats_5s`, window_5s) của các endpoint `derivation = sdk` (§6.3) |
| `stats_sampling_prob` | float | không | 1.0 / 0.1 / 0.0 cho endpoint `derivation = sdk`. Endpoint `derivation = pipeline` luôn gửi 100% (I22) |
| `stats_sampling_reason` | text | không | `critical:<lý do>`, `hash_sample`, `not_selected`, `raw_full` (mọi endpoint của cuộc gọi đều `derivation = pipeline`) |
| `sampling_rule_version` | text | không | |

---

## 6. Event — hạ tầng, và quy tắc thu thập

### 6.1 `turn_health_1m`
PK (`turn_id`, `minute_ts`). `active_allocations`, `utilization_pct`, `cpu_pct`, `bandwidth_mbps`, `alloc_attempts`, `alloc_failures`, `health_status`, `health_score` (0–1, cao = tốt, do health checker gán).

### 6.2 `service_health_1m`
PK (`minute_ts`, `service`, `instance`). `req_count`, `error_count`, `timeout_count`, `p50_ms`, `p95_ms`, `p99_ms`, `static_fallback_count`, `algo_fallback_count`, `active_snapshot_id`, `feature_snapshot_age_s` (now − `cutoff_ts` của snapshot đang phục vụ), `shadow_req_count`.

### 6.3 Quy tắc lấy mẫu dữ liệu diagnostic
1. Trong cuộc gọi, SDK ghi `call_stats_5s` vào **ring buffer** trên thiết bị: tối đa 360 cửa sổ (30 phút) và tối đa 256 KB mỗi cuộc gọi. Tràn thì giữ cửa sổ mới nhất và đặt `stats_status=truncated`.
2. Khi kết thúc, phân tầng:
   - **critical**: `end_reason ∈ {ice_failed, dropped_network, dropped_turn}` hoặc `n_ice_attempts > 1` hoặc có fallback hoặc restart → giữ toàn bộ, `prob = 1.0`, `kept_critical`. SDK tự xác định tầng từ những gì nó quan sát (ICE thất bại, rớt, restart, fallback); BE gửi `end_reason` trong tin nhắn kết thúc nếu có.
   - **normal**: giữ nếu `u64(sha256(utf8(call_id))[0:8], big-endian) mod 1000 < 100` → `prob = 0.1`, `kept_sampled`; ngược lại xóa buffer, `prob = 0.0`, `not_sampled`.
3. Đã chọn giữ nhưng gửi thất bại → `lost` (phân biệt với `not_sampled`). `truncated` là **trạng thái**, không phải lý do: cuộc gọi bị cắt buffer vẫn giữ `stats_sampling_reason` và `stats_sampling_prob` của tầng đã chọn nó.
4. **Dữ liệu KPI-grade (§0.1) luôn được gửi 100%, không phụ thuộc quy tắc này.**
5. Aggregate chẩn đoán trên dữ liệu lấy mẫu phải dùng trọng số Horvitz-Thompson `1/prob` ở **cấp cuộc gọi**. Độ bất định tính theo cụm cuộc gọi.
6. Endpoint `derivation = pipeline` gửi `call_stats_5s` cho **mọi** cuộc gọi. Quy tắc 1 (ring buffer) và 2 (lấy mẫu) **không áp dụng** cho endpoint đó: SDK gửi liên tục từng lô cửa sổ; lô gửi thất bại thì các cửa sổ đó thiếu và `measurement_coverage` phản ánh. Cuộc gọi có một endpoint `sdk` và một endpoint `pipeline`: quy tắc 2 chỉ áp dụng cho endpoint `sdk`.

---

## 7. Bất biến

Mức: **FAIL** (dữ liệu sai, phải sửa) · **WARN** (đáng ngờ, hiện lên trang Data Quality).

| ID | Mức | Bất biến |
|---|---|---|
| I1 | FAIL | Mọi event có `call_id` đều có `call_session` tương ứng |
| I2 | WARN | Mỗi `call_session` có đúng 1 `call_outcome` trong 72 giờ (thiếu thì là orphan) |
| I3 | FAIL | `len(candidates) = min(k, số TURN khả dụng sau lọc)`; rank liên tục 1..len; không trùng `turn_id`; Σ propensity = 1 ± 1e-6 |
| I4 | WARN | Với `decision_mode = live`: TURN thực dùng (`actual_turn_id`, §8.6; thiếu thì `relay_turn_*`) nằm trong `candidates` cùng side (trừ `static_fallback`). `turn_identity_method = ambiguous` ⇒ bỏ qua |
| I5 | WARN | **Chỉ các quan hệ nhân quả** (dung sai lệch đồng hồ 2 s, vượt thì cắm cờ): (a) `initiated_ts ≤` `request_ts` đầu tiên; (b) `decision.response_ts ≤ alloc.request_ts` với allocation của decision đó; (c) `alloc.response_ts ≤ ice_connected_ts` khi attempt dùng allocation đó; (d) `ring_ts ≤ ice_connected_ts`; (e) với `post_answer`: `answer_ts ≤ checks_start_ts`; (f) `ice_connected_ts ≤ dtls_connected_ts ≤ first_media_sent_ts`; (g) mọi mốc `≤ end_ts`. **Không** ràng buộc thứ tự giữa allocation, signaling và ICE checks ngoài các mục trên |
| I6 | FAIL | `answered = false` ⇒ `end_reason ∈ {invite_undelivered, not_answered, rejected, cancelled_by_caller}`; và `answered = false ∧ connected = true` chỉ hợp lệ khi `connection_mode = pre_connect` |
| I7 | FAIL | `dropped=true` ⇒ `answered ∧ connected` |
| I8 | FAIL | `path_type = relay_same` ⇔ `actual_turn_id_caller = actual_turn_id_callee ≠ null` (thiếu `actual_turn_id` thì dùng `relay_turn_*`; `ambiguous` ⇒ bỏ qua) |
| I9 | WARN | Trên **cùng một cửa sổ 5s** (`window_5s`), khi mọi chặng của cả hai chiều là `one_way` và `clock_sync_err_ms ≤ 2` (3 chặng mỗi chiều; `relay_same` là 2): \|Σforward + Σreverse − `media_rtcp_rtt_ms`\| ≤ max(0.2 × `media_rtcp_rtt_ms`, 15 ms) |
| I10 | FAIL | `0 ≤ value_ms ≤ 10000`; `0 ≤ loss_pct ≤ 100`; jitter ≥ 0; `0 ≤ utilization_pct ≤ 150`; tổng histogram = số cửa sổ assessable tương ứng; `success = true` ⇔ `error_code = none` |
| I11 | WARN | `event_id` duy nhất (bản trùng bị dedup và đếm) |
| I12 | FAIL | Decision dùng snapshot S ⇒ `S.published_ts ≤ request_ts` |
| I13 | FAIL | Mọi event đóng góp vào snapshot S thỏa `event_ts < S.cutoff_ts` **và** `ingest_ts < S.cutoff_ts`. Snapshot đã publish là **bất biến**; tính lại thì tạo `snapshot_id` mới |
| I14 | FAIL | Selector **không được chặn** lời mời gọi: BE gửi lời mời song song với việc gọi Selector. Selector lỗi hoặc timeout ⇒ `decision_source=static_fallback`; không bao giờ có `end_reason` do Selector |
| I15 | FAIL | Nếu `experiment_id ≠ null`: `arm ≠ null` và `assignment_ts ≤` `request_ts` đầu tiên của cuộc gọi |
| I16 | FAIL | KPI chính và guardrail (§13) chỉ đọc dữ liệu KPI-grade (§0.1), kiểm tra ở **cấp dòng**: dòng `call_stats_5s` chỉ được làm đầu vào khi endpoint đó `derivation = pipeline`. Kiểm tra tự động từ `contracts/kpi.yaml` |
| I17 | FAIL | Với endpoint `derivation = sdk`: `stats_sampling_prob` và `stats_sampling_reason` khớp §6.3 mục 2 khi tính lại từ `call_id` và outcome. Endpoint `derivation = pipeline` được kiểm tra bằng I22 |
| I18 | FAIL | `ice_transport_policy = relay` ⇒ mọi attempt `connected` có `path_type ∈ {relay_relay, relay_same}` |
| I19 | WARN | Nếu có `relayed_ip` hoặc `turn_server_ip`: máy suy ra từ `dim_turn_endpoint` phải trùng `turn_id` mà Selector chọn. Lệch ⇒ ghi nhận `turn_identity_mismatch` (hostname chung hoặc geo-DNS đưa client tới máy khác). Đây là **phát hiện vận hành**, không phải lỗi dữ liệu |
| I20 | FAIL | Attempt `connected` có `callee_device_id = call_outcome.answered_device_id`. Decision và allocation của thiết bị không bắt máy không được ghép vào attempt đó (`release_reason = other_device_answered`) |
| I21 | FAIL | KPI (§13) chỉ gồm cuộc gọi `call_type = one_to_one` lúc tạo. Với `converted_to_group = true`, mọi cửa sổ sau `converted_ts` không đánh giá được. Guardrail hạ tầng (`turn_utilization_p95`) được miễn: tính trên **toàn bộ** tải, kể cả cuộc gọi nhóm |
| I22 | FAIL | Endpoint `derivation = pipeline` ⇒ `call_stats_5s` của endpoint đó có mọi cửa sổ đã gửi (không lấy mẫu), cùng `window_s` và `quality_rule_version`; cửa sổ thiếu chỉ do gửi thất bại và được phản ánh trong `measurement_coverage`; mỗi endpoint chỉ có **một** `derivation` được dùng cho KPI (§5.7) |
| I23 | FAIL | `end_reason = ice_failed` ⇒ `answered ∧ ¬connected`. Và `answered ∧ ¬connected` ⇒ `end_reason ∈ {ice_failed, normal_hangup, app_crash, unknown}` (bắt máy nhưng media chưa bao giờ nối được) |
| I24 | FAIL | `dropped = true` ⇔ `end_reason ∈ {dropped_network, dropped_turn}` |

---

## 8. Clean-layer — pipeline cam kết xuất ra (producer **không** gửi)

### 8.1 Đồng hồ
`event_ts_corrected`, `clock_skew_ms` (với `client_sdk`: offset ước lượng theo thiết bị × ngày, là trung vị độ lệch giữa client và Signaling trên các mốc tương ứng; với `turn_server`, `probe_agent`, `selector`, `signaling`: theo `instance` × giờ, giả định đồng bộ NTP, offset = 0 trừ khi độ lệch `ingest_ts − event_ts` bất thường thì cắm cờ `unreliable`), `clock_correction_version`, `clock_quality_flag` {`ok`,`corrected`,`unreliable`}. `event_ts` gốc giữ nguyên. Không dùng correction để khẳng định độ chính xác vượt quá khả năng đồng bộ thực tế. Áp dụng cho mọi bảng event có cột `*_ts` dùng trong KPI. `local_hour_vn` của một cuộc gọi suy từ `initiated_ts`.

### 8.2 Độ trễ chặng
- `one_way_ms_observed` = `value_ms` khi `measurement_kind=one_way` và `clock_sync_err_ms ≤ 2`; ngược lại null.
- `one_way_ms_estimated` = `value_ms / 2` khi `measurement_kind=rtt`, cắm cờ `symmetric_assumption=true`.
- **`alloc_ms` không bao giờ được đổi sang one-way.** Thống kê riêng ở `feat_turn_alloc_latency` (§9.6). Chỉ được dùng làm predictor của chặng sau khi mô hình hiệu chỉnh đã được kiểm chứng trên dữ liệu tách riêng (thí nghiệm W5).

### 8.3 Ghép allocation với ICE
- Ưu tiên `*_allocation_id` trong `ice_attempt`.
- Thiếu thì ghép theo (`call_id`, `decision_id`, `side`, `device_id`, `turn_id`, `transport`, `ice_generation`), với điều kiện allocation còn hiệu lực (`response_ts ≤ mốc < released_ts`; mốc = `ice_connected_ts`, hoặc `start_ts` nếu attempt thất bại; `released_ts` null = vẫn còn hiệu lực). Không bao giờ ghép allocation của generation cũ vào attempt mới chỉ vì cùng `turn_id`.
- Xuất ra: `used_by_ice` (bool), `match_method` {`id`,`rule`,`ambiguous`}.

### 8.4 `fact_call`
Một dòng mỗi cuộc gọi: các cột KPI ở §13 (tính từ KPI-grade), `poor_category` {`setup_fail`, `drop`, `quality`, `none`}, `quality_assessment_status` (enum §2: `not_applicable` nếu ¬(answered ∧ connected); `assessed` nếu mọi (side, metric) đều xác định; `partially_assessed` nếu chỉ một phần; `unclassifiable` nếu không có cái nào), `rank_used_*`, `joint_propensity = p_caller × p_callee` (p_side = `propensity` của candidate có `rank = chosen_rank` trong decision mà attempt `connected` đầu tiên dùng — hành động của policy là `chosen_rank`, còn fallback là một phần kết quả), `arm`, `blind_cost_ms` (chỉ sim), `actual_turn_id_*`, `turn_identity_method` (§8.6), thông tin client của hai đầu (`platform`, `app_version`, `device_class`).

### 8.5 `dq_results`
`(pipeline_run_id, dt, check_id, table, level, status, n_checked, n_bad, sample_event_ids[])` (`pipeline_run_id` là lần chạy pipeline, khác `sim_run_id`). Có check phân phối theo `app_version`: metric lệch đột ngột ngay sau một bản phát hành app ⇒ WARN `release_regression`, để không đổ lỗi nhầm cho TURN. Khi lệch **nghiêm trọng** (ngưỡng trong `kpi.yaml`, ví dụ trung vị lệch ≥ 10 lần so với các bản khác cùng nền tảng), metric đó của các dòng thuộc `app_version` đó bị **cách ly**: coi là không hợp lệ (cửa sổ không đánh giá được cho metric đó), cho tới khi có quy tắc sửa được duyệt và có version (`correction_rule_version`). Pipeline **không tự động** nhân hay chia để sửa đơn vị. Hệ quả mong đợi (S25): `unclassifiable_rate` của bản app đó tăng; PCR theo TURN của lần chạy không lỗi luôn nằm trong khoảng [`pcr_itt_low`, `pcr_itt_high`] của lần chạy có lỗi (khoảng rộng ra, không lệch giả). Chuyển đổi đơn vị theo **đặc tả của nguồn** (ví dụ W3C trả giây ⇒ × 1000 ở adapter) vẫn làm bình thường; điều bị cấm là **đoán** đơn vị từ phân phối số liệu.

### 8.6 Danh tính TURN thực và thông tin client
- `actual_turn_id_caller`, `actual_turn_id_callee`: tra theo thứ tự ưu tiên trong `dim_turn_endpoint` có hiệu lực tại thời điểm đó: (1) `relayed_ip_*` của cặp candidate được chọn (`ice_attempt`); (2) `relayed_ip` của allocation đã dùng; (3) `turn_server_ip`; (4) hostname theo `dim_turn_endpoint.hostname`, chỉ khi hostname trỏ tới đúng **một** máy. Còn lại để null. Các nguồn mâu thuẫn nhau ⇒ WARN (I19). Xuất `turn_identity_method` {`ip`, `hostname`, `ambiguous`}.
- **Mọi KPI theo TURN dùng `actual_turn_id`.** Khi `ambiguous`, gắn vào nhóm "pool" chứ không gán bừa cho một máy. KPI theo TURN tính **theo từng đầu**: cuộc gọi `relay_relay` góp vào TURN của mỗi bên; `relay_same` góp một lần.
- `device_class` {`low`, `mid`, `high`, `unknown`} suy từ `device_model` theo bảng tra có version.

---

## 9. Feature store (Hiệp sinh — Đoàn đọc)

### 9.0 Snapshot và segment
- **Cutoff:** `cutoff_ts` = 00:00 giờ VN (17:00 UTC ngày hôm trước). Mỗi ngày một snapshot.
- **Metadata:** `snapshot_id` (`feat-YYYYMMDD-v<n>`), `cutoff_ts`, `published_ts`, `pipeline_version`, `content_hash`, `parent_snapshot_id`.
- **Quy tắc dùng:** tại thời điểm t, Selector dùng snapshot mới nhất có `published_ts ≤ t` (I12). Nội dung thỏa I13. Từ `cutoff_ts` tới `published_ts`, Selector **dùng snapshot cũ**.
- **Bất biến:** snapshot đã publish không sửa. Backfill hoặc sửa logic thì tạo `v<n+1>`. Dựng lại snapshot từ raw và cấu hình đã lưu phải cho ra cùng `content_hash`.
- **Segment, backoff 5 cấp:** `L4 country|vn_region|asn|network_type` → `L3 country|vn_region|asn` → `L2 country|vn_region` → `L1 country` → `L0 *`. Feature store cung cấp **mọi cấp**. Cách Selector chọn cấp là thiết kế của Đoàn. Khuyến nghị: cấp chi tiết nhất mà **mọi** candidate đều có `n_eff ≥ 30`, để điểm các candidate so sánh được với nhau. Cấp đã dùng phải ghi vào `score_components.backoff_level` của từng candidate và vào `fallback_reason`.
- **Định nghĩa thống kê** (tham số tạm thời nằm trong `kpi.yaml`): trọng số mỗi cuộc gọi `w = 0.5^(tuổi_ngày / 7)`; `n_eff = Σ w`. Giá trị chặng cấp cuộc gọi = Σ(`value_ms` × `n_samples`) / Σ `n_samples` qua các epoch của cuộc gọi. `p50_shrunk = (n_eff · p50 + m · p50_cha) / (n_eff + m)` với `m = 30`, cha = cấp backoff kế tiếp.
- **Health snapshot** (`health_snapshot_id` = `hl-YYYYMMDDTHHMM`): mỗi phút một bản, dựng từ `turn_health_1m`. I12 và I13 áp dụng như feature snapshot (cutoff = đầu phút). Bất biến. Nội dung ở §9.7.

### 9.1 `feat_leg_stats` (chặng user↔TURN)
Nguồn: `path_leg_measurement[epoch_summary]` với `leg_type = user_turn`, `method ∈ {inband, idle_probe}`. Cột: `snapshot_id`, `segment_level`, `segment_key`, `turn_id`, `direction` {`user_to_turn`, `turn_to_user`} (suy từ `side` + `direction` của §5.6: caller/forward và callee/reverse là `user_to_turn`, còn lại là `turn_to_user`), `metric` {`one_way_observed`,`rtt`}, `hour_bucket` (0–23 giờ VN hoặc `all`), `n_raw`, `n_eff` (decay half-life 7 ngày), `p50`, `p95` (quantile có trọng số trên giá trị **cấp cuộc gọi** từ `epoch_summary`), `loss_mean`, `jitter_p95`, `p50_shrunk`, `source_mix`, `last_observed_ts`.

### 9.2 `feat_turn_turn`
Nguồn: `path_leg_measurement[epoch_summary]` với `leg_type = turn_turn`, `method ∈ {inband, mesh_probe}`. Cột: `snapshot_id`, `src_turn`, `dst_turn` (chiều gói tin đi từ `src_turn` tới `dst_turn`), `metric`, `hour_bucket`, `n_raw`, `n_eff`, `p50`, `p95`, `loss_mean`, `jitter_p95`, `source_mix`, `last_observed_ts`.

### 9.3 `feat_turn_health`
`snapshot_id`, `turn_id`, `health_status`, `health_score`, `utilization_p95_24h`, `alloc_success_24h` (+ Wilson `ci_low`, `ci_high`), `incidents_detected_7d`, `stability_cv_24h`.

### 9.4 `feat_path_history`
`snapshot_id`, `caller_segment_key` (L2), `callee_segment_key` (L2), `turn_caller`, `turn_callee`, `n_calls`, `n_eff`, `poor_rate` (+ CI, theo định nghĩa §13.2), `drop_rate`, `setup_fail_rate`, `last_observed_ts`.

### 9.5 `feat_callee_prior`
`snapshot_id`, `caller_segment_key` (L2), `callee_country`, `callee_vn_region`, `n`, `share`.

### 9.6 `feat_turn_alloc_latency`
`snapshot_id`, `segment_key`, `turn_id`, `transport`, `n`, `alloc_ms_p50`, `alloc_ms_p95`, `alloc_success_rate` (+ CI). **Không** phải độ trễ chặng.

### 9.7 `health_snapshot` (mỗi phút — dùng cho health filtering lúc runtime)
`health_snapshot_id`, `cutoff_ts`, `published_ts`, `turn_id`, `health_status`, `health_score` (0–1, cao = tốt), `utilization_pct_5m`, `alloc_fail_rate_5m`. Selector dùng bản mới nhất có `published_ts ≤ request_ts` (I12).

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
`sim_run_id`, `run_kind`, `benchmark_id`, `replicate_seed`, `simulator_version`, `git_commit`, `config_hash`, `contract_version`, `topology_version`, `network_profile_version`, `scenario_version`, `incident_schedule_version`, `incidents_sha256`, `root_seeds` {traffic, network, incidents, noise, behavior, policy} (seed gốc cho từng miền ngẫu nhiên; mọi lần rút cụ thể dùng RNG có khóa theo thực thể và thời điểm, §14.2 — không có luồng tuần tự), `policy_version`, `exploration_epsilon`, `connection_mode`, `ice_transport_policy`, `be_region`, `initial_snapshot_hash`, `burn_in_days`, `environment_dir`, `started_at`, `completed_at`. Ở cấp benchmark (`benchmark_manifest`, một file cho cả bộ seed): `benchmark_id`, `n_replicates_planned`, `mde_pp`, `alpha`, `power`, `power_analysis_ref` (đường dẫn tới kết quả chạy thử 3 seed), `kpi_yaml_hash` (ngưỡng đã đóng băng), `decision_rule_version`.

| Loại | Dùng cho | Sự cố |
|---|---|---|
| `scripted` | Test tự động, demo các kịch bản S01–S25 | Công khai, có kỳ vọng rõ |
| `blind_benchmark` | So sánh policy, insight report | Ẩn. `incidents_sha256` được commit **trước** khi phân tích |
| `dev` | Phát triển | Tùy ý |

**10 kịch bản bắt buộc của đề bài** = S01–S10. Trong đó S08 (TURN failure) là kịch bản hệ thống, còn lại là kịch bản cuộc gọi.

**Kịch bản cuộc gọi** (`scenario_tag`): `S01_vn_same_region_same_isp`, `S02_vn_cross_region`, `S03_vn_same_region_cross_isp`, `S04_vn_intl_with_turn`, `S05_vn_intl_no_turn`, `S06_intl_same_area`, `S07_intl_cross_area`, `S09_cold_start`, `S10_network_change`, `S00_background`.

**Kịch bản hệ thống** (chỉ trong manifest của `scripted`, không bao giờ là tag cuộc gọi): `S08_turn_failure`, `S11_turn_overload`, `S12_isp_congestion`, `S13_regional_outage`, `S14_asymmetric_path`, `S15_selector_timeout`, `S16_stale_snapshot`, `S17_delayed_telemetry`, `S18_turn_recovery`, `S19_p2p_preferred` (chạy với `ice_transport_policy = all`), `S20_call_burst`, và các kịch bản production (v0.4.0): `S21_multi_device_ring`, `S22_group_call_filtered`, `S23_turn_pool_hostname`, `S24_raw_stats_derivation`, `S25_app_release_regression`. Phải có kịch bản Geo thắng, kịch bản Historical thắng và kịch bản Smart thắng. Kỳ vọng kiểm tra của từng kịch bản nằm ở spec §10.

---

## 13. KPI Dictionary (nguồn định nghĩa duy nhất; bản máy đọc `contracts/kpi.yaml`)

### 13.1 Quy tắc chung
- Mọi KPI ở §13.2–13.3 đọc **KPI-grade** (I16).
- Ngưỡng ghi là *tạm thời* được **đóng băng** trong `kpi.yaml` trước `blind_benchmark` đầu tiên; sau đó chỉ đổi bằng version mới.
- Ngữ nghĩa percentile: `call_*` = trong một cuộc gọi; `population_*` = giữa các cuộc gọi, tính trên giá trị cấp cuộc gọi. **Không bao giờ lấy trung bình các P95.**
- Phân vị dùng nội suy tuyến tính trên giá trị gốc (`quantile_cont`).
- Mọi phép tính thời gian dùng `event_ts_corrected` (§8.1). Mọi KPI theo TURN dùng `actual_turn_id` (§8.6).

### 13.2 Phân loại một cuộc gọi

```
Chỉ cuộc gọi call_type = one_to_one (I21).
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

  setup_fail(c)   = answered ∧ ¬connected ∧ end_reason ≠ app_crash
                    (gồm ice_failed và người dùng bỏ máy khi media chưa nối được — I23)
  drop(c)         = dropped        (⇔ end_reason ∈ {dropped_network, dropped_turn} — I24)
  quality_bad(c)  = answered ∧ connected ∧ ¬dropped ∧ quality_poor(c)

  poor(c)           = setup_fail(c) ∨ drop(c) ∨ quality_bad(c)       (ba nhánh rời nhau)
  unclassifiable(c) = answered ∧ connected ∧ ¬dropped ∧ quality_unknown(c)
                      (rời với poor ⇒ pcr_itt_high − pcr_itt_low = unclassifiable_rate)
```

Lý do ngoài phạm vi TURN (`invite_undelivered`, `not_answered`, `rejected`, `cancelled_by_caller`, `app_crash`) và `normal_hangup` của cuộc gọi đã nối mà chất lượng ok **không** làm cuộc gọi bị tính tệ, nhưng cuộc gọi **vẫn ở trong cohort**. Với `pre_connect`, cuộc gọi đã connected nhưng không được bắt máy thì **không bao giờ** là poor hay unclassifiable (người dùng không trải nghiệm media). Chi phí của chúng được đo qua `allocation_seconds_unanswered` và guardrail `turn_utilization_p95`.

### 13.3 KPI theo tầng

**Tầng 1 — Metric chính**

| KPI | Định nghĩa |
|---|---|
| **`pcr_itt`** — Poor Call Rate, intention-to-treat | **Cohort** = mọi `call_session` có `call_type = one_to_one` của experiment đã được gán `arm` (I15, I21), **kể cả** khi sau đó Selector timeout, static fallback, P2P (khi `all`), allocation lỗi, không gửi được lời mời hay không bắt máy. **Hai cận:** `pcr_itt_low` = Σ poor / \|cohort\|; `pcr_itt_high` = Σ (poor ∨ unclassifiable) / \|cohort\|. Đơn vị %, **càng thấp càng tốt** |

**Tầng 1b — Metric phụ quan trọng (có điều kiện)**

| KPI | Định nghĩa |
|---|---|
| `pcr_answered` (low/high) | Như trên nhưng mẫu số = cuộc gọi đã bắt máy trong cohort. Diễn giải là chất lượng **có điều kiện**, với giả định policy không ảnh hưởng việc bắt máy. Giả định này được **kiểm tra và báo cáo** (`answer_rate` theo nhánh), **không bao giờ dùng để đổi metric chính** |
| Thành phần (rời nhau, cùng mẫu số cohort) | `setup_fail_rate` = Σ setup_fail / \|cohort\| (tách tiếp `ice_fail_rate` = Σ[`end_reason = ice_failed`] / \|cohort\| và `setup_abandon_rate` = phần còn lại); `drop_rate` = Σ drop / \|cohort\|; `quality_poor_rate` = Σ quality_bad / \|cohort\|; `unclassifiable_rate` = Σ unclassifiable / \|cohort\|. `pcr_itt_low` = tổng ba thành phần đầu |
| Phễu (cùng mẫu số cohort) | `invite_delivered_rate` = Σ[`ring_ts` ≠ null]; `answer_rate` = Σ answered; `selector_timeout_rate` = Σ cuộc gọi có ≥ 1 decision không có `response_ts`; `static_fallback_rate` = Σ cuộc gọi có ≥ 1 decision `static_fallback`; `p2p_rate` (= 0 theo định nghĩa khi `ice_transport_policy = relay`, I18); `app_crash_rate` = Σ[`end_reason = app_crash`] (không poor, không unclassifiable; báo riêng theo nhánh để phát hiện nếu policy có liên quan) |

**Tầng 2 — Guardrail** (non-inferiority, §14.4)

| Guardrail | Hướng | Margin δ |
|---|---|---|
| `setup_fail_rate` (mẫu số cohort ITT) | thấp | +0.2 điểm % |
| `drop_rate` (mẫu số cohort ITT) | thấp | +0.2 điểm % |
| `cst_technical_p95` = P95(`ice_connected_ts − checks_start_ts`) trên attempt `connected` có `attempt_seq` nhỏ nhất của mỗi cuộc gọi; attempt thiếu `checks_start_ts` bị loại và tỉ lệ thiếu được báo cáo kèm | thấp | +10% |
| `ttfm_post_answer_p95` = P95(max(0, max_side(`first_media_received_ts`) − `answer_ts`)), chỉ khi `connection_mode = post_answer`. `first_media_received_ts` của một bên = min trên mọi epoch của thiết bị tham gia kết nối; cuộc gọi thiếu một bên bị loại, tỉ lệ loại được báo kèm | thấp | +10% |
| `selector_api_p95` — nguồn: `selector_decision.api_latency_ms`, mỗi `decision_id` tính một lần, `decision_mode = live`, bỏ null (tỉ lệ null báo kèm). Mục đích: chặn timeout/static fallback và quá tải; với `post_answer`, người dùng gần như không cảm nhận độ trễ này vì nó bị che bởi thời gian đổ chuông (§0.2) | thấp | ≤ 50 ms (tuyệt đối) |
| `selector_availability` = 1 − Σ(decision không có `response_ts`) / Σ decision, trên cùng tập với `selector_api_p95` | cao | ≥ 99.9% (tuyệt đối) |
| `static_fallback_rate` (định nghĩa ở Phễu) | thấp | +0.2 điểm % |
| `turn_utilization_p95` (mọi TURN, mọi phút) | thấp | ≤ 85% (tuyệt đối) |
| `unclassifiable_rate` (độ đầy đủ telemetry) | thấp | +1.0 điểm % |
| `pcr_itt_high` theo từng `pair_group` (ΔG tính chéo bất lợi: `pcr_itt_high(Smart) − pcr_itt_low(Geo)`) | thấp | +0.5 điểm % |

**Tầng 3 — Chẩn đoán** (không dùng để kết luận thắng/thua; công thức chi tiết của từng chỉ số chẩn đoán được viết trong `contracts/kpi.yaml` lúc implement — chúng không ảnh hưởng luật kết luận §14.4)
`pnr` = Σ quality_bad / Σ (answered ∧ connected ∧ ¬dropped ∧ ¬quality_unknown) — chất lượng có điều kiện trên cuộc gọi đã nối, cùng quy tắc §13.2 · `population_media_rtcp_rtt_p50/p95` · `population_ice_stun_rtt_p95` · `population_loss` · `population_jitter_estimate_p95` · `mos_est` (E-model) · `max_epoch_p95` · `rank_of_used` · `est_vs_observed_mae` · `confidence_calibration` · `coverage_7d` · `ess` · `hhi_turn` · `alloc_success_rate` · `allocation_not_selected_rate` · `allocation_never_checked_rate` (khi có `ice_candidate_pair`) · `reserve_allocation_seconds` · `allocation_seconds_unanswered` · `blind_cost_ms` · regret (§14.6) · `setup_breakdown_post_answer` (P50/P95 từng đoạn, trên `event_ts_corrected`, chỉ khi `connection_mode = post_answer`: `answer_ts → checks_start_ts` = signaling qua BE + gathering (một đoạn, vì không có mốc riêng cho gathering); `checks_start_ts → ice_connected_ts` = ICE; `ice_connected_ts → dtls_connected_ts` = DTLS; `dtls_connected_ts → first_media_received_ts` = media bắt đầu) · `signaling_overhead_est_ms` = (`caller_signaling_rtt_ms` + `callee_signaling_rtt_ms`) / 2, xấp xỉ một lượt tin nhắn B → BE → A (null nếu SDK không đo; khi đó `setup_breakdown_post_answer` vẫn tính được từ các mốc thời gian) · `poor_bottleneck_share` (trong các cuộc gọi poor: tỉ lệ có chặng tệ nhất là `user_turn` — last mile, đổi TURN ít giúp được — so với `turn_turn` — chặng giữa, đổi TURN có thể giúp; tính từ `path_leg_measurement[epoch_summary]`) · `turn_identity_mismatch_rate` (I19) · mọi KPI chính và guardrail được **cắt theo `platform`, `app_version`, `device_class`** trên dashboard (chẩn đoán, không đổi luật kết luận).

---

## 14. Đánh giá (Evaluation)

### 14.1 Estimand
Hiệu ứng ITT: `Δ = PCR_itt(Smart) − PCR_itt(Geo)` trên **cùng các yếu tố ngoại sinh**. Vì PCR có hai cận, Δ là một **khoảng** [`best`, `worst`] tính chéo theo §14.4. So sánh với Historical theo cùng cách. Các họ policy: `geo_baseline@*`, `historical@*`, `smart@*`.

### 14.2 Thiết kế trên simulator
- **Môi trường cô lập theo policy:** mỗi (policy, seed) là một lần chạy riêng, có `environment_dir` riêng chứa feature store, health state, tải TURN và cache riêng.
- **Yếu tố ngoại sinh dùng chung:** traffic (ai gọi ai, lúc nào, có bắt máy không, thời lượng dự định, thời điểm đổi mạng), lịch sự cố, mạng nền. Sinh trước, hoặc rút từ RNG có khóa theo thực thể và thời điểm, ví dụ `(seed, call_id, "answer")`, `(seed, call_id, leg, direction, window_idx, "noise")`, `(seed, turn_id, ts_bucket, "net")`. Số event do policy sinh ra **không được** làm xê dịch bất kỳ luồng ngẫu nhiên nào.
- **Yếu tố nội sinh** (tải, lịch sử, snapshot) được phép khác nhau. Đó là hiệu ứng cần đo.
- **Khởi đầu:** mọi policy dùng cùng `initial_snapshot_hash`. **Burn-in 3 ngày** bị loại khỏi đánh giá.
- **Tái lập:** cùng manifest thì ra cùng hash dữ liệu (có test).
- **BE-invariance:** BE chỉ được ảnh hưởng các mốc thời gian signaling (`ring_ts`, `answer_ts`, `checks_start_ts`…) và `*_signaling_rtt_ms`. BE không được đi vào truth media hay bất kỳ RNG nào của media. Vì BE làm dịch thời điểm media bắt đầu, phép thử chạy trên kịch bản scripted có truth **không đổi theo thời gian** và health không đổi: cùng seed và policy, đổi `be_region` thì `pcr_itt` và mọi metric chất lượng phải **giống hệt**; chỉ các chỉ số thời gian thiết lập được phép đổi (có test). Nhiễu đo khóa theo `window_idx` (tương đối với neo của endpoint) nên không đổi khi neo dịch. Độ trễ BE ↔ Selector trong sim không phụ thuộc `be_region` (giả định đặt cùng chỗ), nên quyết định của Selector không đổi.
- **Derivation-equivalence:** trên cùng dữ liệu, `call_stats_epoch` do SDK tính và do pipeline tính từ `call_stats_5s` phải giống hệt (có test).
- **Mặc định production-like của simulator:** thông tin client theo phân bố nền tảng; một thiết bị mỗi user; chỉ cuộc gọi 1-1; mỗi máy TURN một IP dùng cho cả hai vai trò (`role = both`). Các trường hợp còn lại được kiểm tra bằng kịch bản scripted S21–S25 (§12).

### 14.3 Đơn vị độc lập và cỡ mẫu
- **Đơn vị độc lập = seed.** Với mỗi seed *r*, tính `d_r` trên **toàn bộ cuộc gọi gộp chung** có `initiated_ts` sau burn-in (không lấy trung bình các tỉ lệ theo ngày).
- **Power analysis trên đúng estimand ITT:** chạy 3 seed thử nghiệm **chỉ để ước lượng phương sai** của `d_r`, rồi tính R cần thiết cho **MDE = 0.5 điểm %** với α = 0.05 hai phía, power 0.8. R cuối được ghi vào manifest trước khi chạy. Không đủ ngân sách thì báo cáo MDE thực tế.
- **Kiểm tra chéo** trong một lần chạy: block bootstrap theo (ngày × miền), giữ cặp Geo–Smart.

### 14.4 Luật kết luận (đóng băng trước `blind_benchmark`)
Với mỗi seed: `worst_r = pcr_itt_high(Smart) − pcr_itt_low(Geo)` và `best_r = pcr_itt_low(Smart) − pcr_itt_high(Geo)` (so sánh **chéo** hai cận).

- **CI:** `UpperCI95` / `LowerCI95` là hai đầu của khoảng tin cậy **hai phía** 95% (98.33% cho guardrail theo `pair_group`), dùng t-interval trên R giá trị theo seed.
- **Guardrail tương đối** (δ dạng "+x điểm %" hoặc "+x%"): ΔG_j = G_j(Smart) − G_j(Geo); "+x%" nghĩa là δ_j = x% × trung bình qua các seed của G_j(Geo). **Đạt** ⇔ `UpperCI95(ΔG_j) < δ_j`; **vi phạm** ⇔ `LowerCI95(ΔG_j) > δ_j`. Guardrail tính từ hai cận PCR dùng hiệu chéo bất lợi.
- **Guardrail tuyệt đối** (δ dạng "≤ x" hoặc "≥ x"): kiểm tra trên G_j(Smart). **Đạt** ⇔ `UpperCI95(G_j) ≤ x` (hoặc `LowerCI95(G_j) ≥ x` với guardrail "cao = tốt"); **vi phạm** ⇔ `LowerCI95(G_j) > x` (hoặc `UpperCI95(G_j) < x`).
- **Smart tốt hơn** ⇔ `UpperCI95(worst) < 0` **và** mọi guardrail **đạt**.
- **Smart tệ hơn** ⇔ `LowerCI95(best) > 0` **hoặc** có ít nhất một guardrail **vi phạm**.
- **Ngược lại: INCONCLUSIVE**, kể cả khi CI chỉ chạm margin.
- Guardrail theo `pair_group` dùng CI 98.33% (Bonferroni cho 3 nhóm).
- Kết luận chỉ áp dụng cho `data_source=synthetic` với các giả định trong sổ giả định của spec.

### 14.5 Sensitivity bắt buộc
Ngưỡng RTT 200/300/400 · loss 1/3/5 · jitter 10/30/50 · `PoorFraction` 0.1/0.2/0.3 · `connection_mode = pre_connect` (**chạy lại toàn bộ** KPI chính, guardrail và tải TURN; mô phỏng allocation sống trong lúc đổ chuông, kể cả cuộc gọi không được bắt máy, có TTL) · `ice_transport_policy = all` (bật lại P2P và `relay_direct`, **chạy lại toàn bộ**). Thứ hạng đổi chiều ⇒ kết luận ghi "phụ thuộc giả định".

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
| Assignment, lifecycle | BE (Spring Boot, signaling) | I14, I15 là yêu cầu kiến trúc |
| `be_region`, `be_instance`, `ice_transport_policy` | Cấu hình của BE khi tạo cuộc gọi | |
| `*_signaling_rtt_ms` | Ping/pong trên kênh signaling app ↔ BE | Chưa xác minh SDK có đo |
| Thông tin client (`platform`, `app_version`, `sdk_version`, `os_version`, `device_model`, `browser_*`) | App gửi kèm mọi event | |
| `device_id` | HMAC của id cài đặt app | |
| `relayed_ip_*` | `local-candidate.address` / `remote-candidate.address` khi `candidateType = relay` | Chỉ IP máy chủ TURN. Không lưu `relatedAddress`/`relatedPort` (chứa IP người dùng) |
| `turn_server_ip` | SDK (nếu lấy được IP đã phân giải) hoặc log của TURN server | Chưa xác minh. Log TURN có chứa IP client: chỉ trích IP của chính server |
| `call_type`, `converted_*`, `answered_device_id`, `n_devices_rung` | BE | |
| `dim_turn_endpoint` | Đội hạ tầng (danh sách IP của từng máy TURN) | |

---

## 16. Version và quy trình thay đổi

- **SemVer.** MAJOR: xóa hoặc đổi tên cột, đổi nghĩa hoặc đơn vị. MINOR: thêm cột nullable hoặc giá trị enum. PATCH: sửa mô tả.
- Mọi thay đổi: PR sửa tài liệu này **và** `contracts/` cùng lúc, cập nhật changelog, **Hiệp và Đoàn cùng approve**, CI xanh (schema + `kpi.yaml` + test bất biến).
- Sau FREEZE (v0.2.0; v0.3.0 và v0.4.0 chỉ bổ sung theo quy tắc MINOR): vấn đề mới vào **assumption log** (sổ giả định A1…An, spec §16) hoặc issue; chỉ mở version mới khi vấn đề làm sai dữ liệu hoặc kết luận.

## 17. Câu hỏi mở (không chặn freeze — có mặc định)

| # | Câu hỏi | Ai | Mặc định |
|---|---|---|---|
| Q1 | Đoàn cần thêm feature nào ngoài §9? | Đoàn | Như §9 |
| Q2 | Thang `score` và cách tính `confidence` | Đoàn | 0–1, cao = tốt |
| Q3 | k = 4 hay 8 | Mentor / Đoàn | 4 |
| Q4 | Production đo ms từng chặng bằng cách nào | Mentor | `measurement_kind` + `clock_sync_err_ms` bắt buộc |
| Q5 | ICE bắt đầu lúc đổ chuông hay sau khi bắt máy | Mentor / đội WebRTC | `post_answer` (giả định chưa xác minh) |
| Q6 | Có bao nhiêu BE, đặt ở đâu, gán BE cho cuộc gọi thế nào | Mentor | Một cụm BE; vị trí là tham số, mặc định `SGN`. Chỉ ảnh hưởng thời gian thiết lập |
| Q7 | ICE chỉ dùng relay hay cho phép P2P | Mentor / đội WebRTC | `relay` (suy ra từ mô tả của mentor); `all` là sensitivity |
| Q8 | SDK có đo RTT kênh signaling không | Mentor | Field nullable, không chặn |
| Q9 | TURN được cấp cho client bằng hostname riêng từng máy, hostname chung của pool, hay IP? | Đội hạ tầng | Hostname riêng; xác định máy bằng IP khi có (§3.4) |
| Q10 | SDK tự tính được `call_stats_epoch` hay chỉ gửi được getStats thô? | Đội mobile/web | Hỗ trợ cả hai (`derivation`) |
| Q11 | Người nghe có nhiều thiết bị cùng đổ chuông không? | Mentor | Có thể; contract đã hỗ trợ |
| Q12 | Có cuộc gọi nhóm không, đánh dấu thế nào, cuộc gọi 1-1 có chuyển thành nhóm được không? | Mentor | `call_type`; chỉ cuộc gọi 1-1 vào KPI |

## Changelog

- **0.4.0** (2026-11-04), sẵn sàng cho production, chỉ bổ sung (MINOR):
  - §0.3 tổng hợp 5 điều production không được giả định.
  - Thông tin client trong `ctx` (`device_id`, `platform`, `os_version`, `app_version`, `sdk_version`, `device_model`, `browser_*`); enum `platform`.
  - Danh tính TURN thực: `dim_turn_endpoint` (§3.4); `turn_url`, `turn_server_ip`, `relayed_ip` trong `turn_allocation`; `relayed_ip_*` trong `ice_attempt` (chỉ IP máy chủ TURN); §8.6 `actual_turn_id_*`; I19.
  - Nhiều thiết bị: `device_id` trên `selector_decision`, `turn_allocation`, `ice_attempt`, `path_leg_measurement`, `call_stats_*`; `answered_device_id`, `n_devices_rung`; `release_reason = other_device_answered`; I20.
  - Loại cuộc gọi: enum `call_type`; `call_session.call_type`; `converted_to_group`, `converted_ts`; I21. **Làm rõ phạm vi:** cohort `pcr_itt` và §13.2 ghi rõ chỉ tính cuộc gọi 1-1 (trước đây chỉ ngầm định trong spec; trên simulator không đổi kết quả vì mọi cuộc gọi đều là 1-1).
  - Hai cách cung cấp `call_stats_epoch` (`derivation`, `window_s`); `stats_sampling_reason = raw_full`; §6.3 mục 6; I22; test derivation-equivalence.
  - DQ `release_regression`; chẩn đoán `turn_identity_mismatch_rate`; KPI cắt theo `platform`, `app_version`, `device_class`.
  - Kịch bản scripted S21–S25. Câu hỏi mở Q9–Q12.
  - **Sửa theo audit độc lập (2 P0, 24 P1, 21 P2):**
    - I6 viết lại cho đúng ý; I17 kiểm tra theo endpoint; thêm I23 (ice_failed ⇔ bắt máy mà chưa nối) và I24 (`dropped` ⇔ end_reason drop).
    - §13.2 định nghĩa lại poor thành **ba nhánh rời nhau** (setup_fail, drop, quality_bad); cuộc gọi đã bắt máy mà không bao giờ nối được giờ được tính là poor; thành phần và phễu có công thức. Guardrail `ice_fail_rate` đổi thành `setup_fail_rate` (định nghĩa cũ thiếu tử số).
    - §5.7 quy tắc cửa sổ chặt hơn: neo theo endpoint, epoch theo điểm giữa, khoảng gián đoạn restart, điều kiện hợp lệ từng metric, key bucket chuẩn, metadata của dòng do pipeline tính. §5.8 có đủ cột để pipeline tính lại §5.7.
    - Khóa có `device_id` không bao giờ null (`'unknown'`/`'-'`); PK `ice_attempt`; khóa duy nhất `path_leg_measurement`; một request `refined` cho mỗi thiết bị đổ chuông.
    - Bảng ánh xạ `path_type`; I4/I8 dùng `actual_turn_id`; thứ tự ưu tiên xác định máy TURN; probe đi vào feature store; `direction` của `feat_leg_stats`; định nghĩa `n_eff`, `p50_shrunk`; health snapshot mỗi phút (§9.7).
    - Nguồn và cách đếm của các guardrail Selector; mốc thời gian KPI dùng `event_ts_corrected`; §14.4 định nghĩa CI, điều kiện "đạt" và "vi phạm"; `d_r` gộp toàn bộ cuộc gọi; propensity cho OPE theo `chosen_rank`.
    - BE-invariance chạy trên truth không đổi theo thời gian; `call_type` không null (`unknown`); `derivation` mặc định `sdk`, `window_s` mặc định 5 cho dữ liệu cũ. Việc mở rộng khóa vẫn coi là MINOR vì chưa có dữ liệu production nào ở v0.2/v0.3.
    - `release_regression` nghiêm trọng ⇒ **cách ly** metric của bản app đó, không tự sửa đơn vị (§8.5, S25).
    - Mỗi endpoint chỉ có một `derivation` dùng cho KPI; thêm `app_crash_rate` vào phễu; `caller_device_id`, `callee_device_id` và `answered_device_id` theo quy ước `'unknown'`.
- **0.3.0** (2026-11-04), chỉ bổ sung (MINOR), không đổi định nghĩa nào của v0.2.0:
  - §0.2 kiến trúc hai mặt phẳng: BE = backend signaling, **không** nằm trên đường media A → TURN(A) → TURN(B) → B (xác nhận 2026-11-04; research/05–07).
  - Enum `ice_transport_policy`. `call_session` + `ice_transport_policy`, `be_region`, `be_instance`. `call_outcome` + `caller_signaling_rtt_ms`, `callee_signaling_rtt_ms`.
  - I18 (chỉ relay ⇒ không có P2P). I14 ghi rõ BE gửi lời mời song song với việc gọi Selector.
  - KPI chẩn đoán: `setup_breakdown_post_answer`, `signaling_overhead_est_ms`, `poor_bottleneck_share`.
  - Sensitivity `ice_transport_policy = all`. Câu hỏi mở Q6–Q8.
  - `run_manifest` + `ice_transport_policy`, `be_region` (tái lập được các lần chạy sensitivity). S19 chạy với `all`. Quy tắc BE-invariance (§14.2).
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
