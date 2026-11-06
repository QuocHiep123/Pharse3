# Giải thích các bảng của Data Contract v0.5.0 (đề xuất)

Tài liệu sinh tự động từ [data_contract_v0.5.0_de_xuat.schema.yaml](data_contract_v0.5.0_de_xuat.schema.yaml) và [dac_ta_sau_thu_thap_v0.5.0_de_xuat.schema.yaml](dac_ta_sau_thu_thap_v0.5.0_de_xuat.schema.yaml). Sơ đồ database và danh sách bảng nằm ở [So_do_database_Data_Contract_v0.5.0.md](So_do_database_Data_Contract_v0.5.0.md). Nghĩa và lý do của từng thay đổi nằm ở [đề xuất cho Hiệp](De_xuat_Data_Contract_v0.5.0_cho_Hiep.md). Khi các file khác nhau thì tin YAML.

**Cách đọc:** "Bắt buộc" trống nghĩa là được null. PK là khóa chính, FK là khóa ngoại. Mọi bảng event còn có các cột chung `event_envelope`, không lặp lại trong từng bảng; chi tiết ở mục 1.10.

## Mục lục

1. [Contract thu thập](#1-contract-thu-thập)
2. [Các lớp sau thu thập](#2-các-lớp-sau-thu-thập)

---

## 1. Contract thu thập

### 1.1. Tham chiếu

#### `dim_turn`

Danh mục TURN (SCD2). **Một dòng:** Một phiên bản hiệu lực của một turn_id · **Nguồn ghi:** Hạ tầng · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `turn_id` | string | có | PK | <country>-<city>-<host>-<nn> |
| `hostname` | string | có |  | Riêng của máy, hoặc chung của pool |
| `country` | string | có |  |  |
| `vn_region` | enum: north, central, south, unknown |  |  |  |
| `city` | string | có |  |  |
| `lat` | number | có |  |  |
| `lon` | number | có |  |  |
| `host_isp` | string | có |  |  |
| `host_asn` | integer | có |  |  |
| `capacity_alloc` | integer (≥ 0) |  |  | Null nếu chưa xác định được |
| `transports` | mảng enum: udp, tcp, tls | có |  |  |
| `status` | enum: active, maintenance, retired | có |  |  |
| `valid_from` | date-time | có | PK |  |
| `valid_to` | date-time |  |  |  |
| `failure_domain` | object failure_domain |  |  |  |

- **Cột hoãn:** `hairpin_supported, hairpin_test`: Cặp (A, A) xử lý như mọi cặp; khả năng hairpin là giả định của danh mục
- **Cột hoãn:** `turn_pool_id, turn_instance_id`: Chưa cần khi danh mục tự xây

#### `dim_turn_endpoint`

Ánh xạ IP sang máy TURN (SCD2). **Một dòng:** Một quan hệ IP, turn_id, vai trò trong một khoảng hiệu lực · **Nguồn ghi:** Hạ tầng · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `mapping_id` | string | có | PK | **Mới.** |
| `ip` | string | có |  | Chỉ IP máy chủ TURN |
| `turn_id` | string | có | FK → dim_turn |  |
| `role` | enum: listen, relay, both | có |  |  |
| `hostname` | string |  |  |  |
| `valid_from` | date-time | có |  |  |
| `valid_to` | date-time |  |  |  |
| `source` | string |  |  | **Mới.** Nguồn của ánh xạ |

- **Cột hoãn:** `endpoint_id`: Chưa cần khi danh mục tự xây

#### `dim_asn`

Danh mục ASN. **Một dòng:** Một ASN · **Mức nguồn:** B

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `asn` | integer | có | PK |  |
| `isp` | string | có |  |  |
| `country` | string | có |  |  |
| `access_kind` | enum: fixed, mobile, mixed | có |  |  |

#### `dim_country_area`

Quốc gia sang khu vực. **Một dòng:** Một quốc gia trong một phiên bản bảng · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `country` | string | có | PK |  |
| `area` | string | có |  |  |
| `area_map_version` | string | có | PK |  |

### 1.2. Call logs

#### `call_session`

Cuộc gọi, tạo khi A bấm gọi. **Một dòng:** Một cuộc gọi · **Nguồn ghi:** signaling · **Mức nguồn:** A · **Mức thu:** required · **Phạm vi:** all_calls

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK |  |
| `caller_hash` | string | có |  |  |
| `callee_hash` | string | có |  |  |
| `initiated_ts` | date-time | có |  |  |
| `media_kind` | enum: audio, video | có |  |  |
| `call_type` | enum: one_to_one, group, unknown | có |  |  |
| `caller_device_id` | string | có |  |  |
| `connection_mode` | enum: post_answer, pre_connect | có |  |  |
| `ice_transport_policy` | enum: relay, all |  |  | Cấu hình BE gửi. Cuộc gọi thật là all, giả lập là relay |
| `be_region` | string |  |  |  |
| `be_instance` | string |  |  |  |

- **Cột hoãn:** `experiment_id, arm, randomization_unit, experiment_cluster_id, assignment_ts, assignment_hash`: Tạm thời chưa thử nghiệm trên traffic thật
- **Cột chuyển đi:** `scenario_tag`: sim_call_tag
- **Cột chuyển đi:** `observation_profile`: run_manifest

#### `client_applied_config`

Cấu hình client đã áp dụng. **Một dòng:** Một lần áp dụng cấu hình trên một PC và generation · **Nguồn ghi:** client_sdk · **Mức nguồn:** B · **Mức thu:** conditional · **Phạm vi:** all_calls

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `applied_config_id` | uuid | có | PK |  |
| `call_id` | uuid | có | FK → call_session |  |
| `applied_decision_id` | uuid |  | FK → selector_decision | Null nếu dùng cấu hình không từ decision |
| `list_hash` | string | có |  |  |
| `applied_ts` | date-time | có |  |  |
| `side` | enum: caller, callee | có |  |  |
| `endpoint_id` | string | có |  |  |
| `device_id` | string | có |  |  |
| `pc_id` | string | có |  |  |
| `ice_generation` | integer (≥ 0) | có |  |  |
| `applied_ice_transport_policy` | enum: relay, all |  |  | Căn cứ của I18 |
| `config_source` | enum: selector, static_config, static_fallback, cache, unknown | có |  |  |
| `is_fallback_config` | boolean |  |  |  |
| `applied_entries` | mảng object applied_entry |  |  | **Mới.** Chỉ khi cấu hình không tra được qua applied_decision_id |
| `decision_device_id` | string |  |  | device_id trong khóa của selector_decision; khác device_id client thực khi danh sách ban đầu dùng '-' |

- **Cột hoãn:** `ice_trickle`: Giả định có trickle ICE theo WebRTC chuẩn

### 1.3. getStats và ICE

#### `endpoint_network_context`

Context mạng của endpoint tại mỗi network epoch. **Một dòng:** Một call_id × side × device_id × network_epoch × context_version · **Nguồn ghi:** signaling (BE ghi snapshot từ client report và GeoIP lúc nhận; simulator tự tạo) · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK |  |
| `side` | enum: caller, callee | có | PK |  |
| `device_id` | string | có | PK |  |
| `network_epoch` | integer (≥ 0) | có | PK |  |
| `context_version` | integer (≥ 1) | có | PK |  |
| `epoch_start_ts` | date-time |  |  |  |
| `observed_ts` | date-time | có |  |  |
| `country` | string | có |  | ISO country hoặc unknown |
| `city` | string | có |  |  |
| `vn_region` | enum: north, central, south, unknown |  |  |  |
| `isp` | string | có |  |  |
| `asn` | integer |  |  |  |
| `network_type` | enum: wifi, 4g, 5g, ethernet, unknown | có |  |  |
| `geo_source` | enum: ip_geo, sdk_claimed, both, unknown | có |  |  |
| `context_status` | enum: complete, partial, unknown | có |  |  |
| `network_type_source` | enum: client_report, synthetic, unknown | có |  |  |
| `epoch_clock_source` | enum: client, synthetic, unknown | có |  | Đồng hồ của epoch_start_ts; observed_ts luôn theo BE producer |
| `missing_reason` | string |  |  |  |

#### `ice_event`

Dòng thời gian ICE theo từng endpoint. **Một dòng:** Một sự kiện quan sát trên một endpoint · **Nguồn ghi:** client_sdk · **Mức nguồn:** B · **Mức thu:** required · **Phạm vi:** all_calls

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | FK → call_session |  |
| `attempt_seq` | integer (≥ 0) |  |  |  |
| `pc_id` | string | có |  |  |
| `ice_generation` | integer (≥ 0) | có |  |  |
| `side` | enum: caller, callee | có |  |  |
| `device_id` | string | có |  |  |
| `event_type` | enum: ice_state_change, selected_pair_change, dtls_state_change, restart_requested | có |  |  |
| `event_mono_ms` | number (≥ 0) |  |  |  |
| `clock_session_id` | string |  |  |  |
| `ice_state` | enum: new, checking, connected, completed, disconnected, failed, closed |  |  |  |
| `dtls_state` | enum: new, connecting, connected, closed, failed |  |  |  |
| `local_candidate_type` | enum: host, srflx, prflx, relay, unknown |  |  |  |
| `remote_candidate_type` | enum: host, srflx, prflx, relay, unknown |  |  |  |
| `client_turn_transport` | enum: udp, tcp, tls |  |  | Chỉ của đầu quan sát |
| `candidate_protocol` | enum: udp, tcp |  |  |  |
| `relayed_ip_local` | string |  |  | Chỉ khi là relay |
| `relayed_ip_remote` | string |  |  | Chỉ khi là relay; có thể null |
| `selected_pair_changes` | integer (≥ 0) |  |  | selectedCandidatePairChanges; không phải lần tăng nào cũng là đổi đường |
| `ice_role` | enum: controlling, controlled, unknown |  |  |  |
| `trigger` | enum: initial, restart_network_change, restart_failure, restart_disconnected, restart_quality |  |  | Khi event_type = restart_requested |
| `reason` | string |  |  |  |
| `source` | enum: event, polling | có |  |  |
| `poll_interval_ms` | number (≥ 0) |  |  |  |
| `local_turn_url` | string |  |  | **Mới.** url của local candidate trong cặp được chọn; chỉ có ở đầu quan sát |
| `prev_pair_rtt_total_s` | number (≥ 0) |  |  | **Mới.** candidate-pair.totalRoundTripTime của cặp vừa rời; chỉ khi selected_pair_change |
| `prev_pair_responses` | integer (≥ 0) |  |  | **Mới.** candidate-pair.responsesReceived của cặp vừa rời |
| `audio_rtcp_rtt_total_s` | number (≥ 0) |  |  | **Mới.** remote-inbound-rtp.totalRoundTripTime của stream audio tại lúc đổi cặp |
| `audio_rtcp_rtt_measurements` | integer (≥ 0) |  |  | **Mới.** remote-inbound-rtp.roundTripTimeMeasurements |
| `audio_packets_received_total` | integer (≥ 0) |  |  | **Mới.** inbound-rtp.packetsReceived |
| `audio_packets_lost_total` | integer |  |  | **Mới.** inbound-rtp.packetsLost; có thể âm |
| `audio_jitter_sum_ms` | number (≥ 0) |  |  | **Mới.** Tổng các lần đọc inbound-rtp.jitter |
| `audio_jitter_samples` | integer (≥ 0) |  |  | **Mới.** |
| `audio_stats_stream_ref` | string |  |  | **Mới.** Chỉ trừ bộ đếm khi cùng stream |

- **Cột chuyển đi:** `local_turn_id, remote_turn_id`: clean_ice_event_columns

#### `call_stats_epoch`

Tóm tắt getStats theo epoch. **Một dòng:** Một call_id × endpoint_side × device_id × media_kind × network_epoch × sequence_no · **Nguồn ghi:** client_sdk · **Mức nguồn:** B · **Mức thu:** required · **Phạm vi:** relay_or_failed

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK FK → call_session |  |
| `endpoint_side` | enum: caller, callee | có | PK |  |
| `device_id` | string | có | PK |  |
| `media_kind` | enum: audio, video | có | PK |  |
| `network_epoch` | integer (≥ 0) | có | PK |  |
| `sequence_no` | integer (≥ 0) | có | PK | **Mới.** Tăng theo mỗi lần gửi; dòng có số lớn nhất là dòng hiện hành |
| `epoch_start_ts` | date-time | có |  |  |
| `epoch_end_ts` | date-time | có |  |  |
| `is_checkpoint` | boolean |  |  | **Mới.** |
| `network_type` | enum: wifi, 4g, 5g, ethernet, unknown |  |  |  |
| `audio_active_duration_s` | number (≥ 0) |  |  |  |
| `first_media_sent_ts` | date-time |  |  |  |
| `first_media_received_ts` | date-time |  |  |  |
| `first_media_definition` | enum: rtp_first_packet, decoded_frame, playout |  |  | **Mới.** |
| `first_media_observation_status` | string |  |  | **Mới.** |
| `media_rtcp_rtt_total_s` | number (≥ 0) |  |  | **Mới.** remote-inbound-rtp.totalRoundTripTime tại cuối epoch |
| `media_rtcp_rtt_measurements` | integer (≥ 0) |  |  | **Mới.** remote-inbound-rtp.roundTripTimeMeasurements |
| `ice_stun_rtt_total_s` | number (≥ 0) |  |  | **Mới.** candidate-pair.totalRoundTripTime của cặp đang chọn lúc cuối epoch |
| `ice_stun_responses` | integer (≥ 0) |  |  | **Mới.** candidate-pair.responsesReceived của cặp đó |
| `packets_received_total` | integer (≥ 0) |  |  | **Mới.** inbound-rtp.packetsReceived |
| `packets_lost_total` | integer |  |  | **Mới.** inbound-rtp.packetsLost; có thể âm |
| `jitter_estimate_sum_ms` | number (≥ 0) |  |  | **Mới.** Tổng các lần đọc inbound-rtp.jitter; W3C chỉ có giá trị hiện tại nên phải lấy mẫu |
| `jitter_estimate_samples` | integer (≥ 0) |  |  | **Mới.** |
| `stats_stream_ref` | string |  |  | **Mới.** Định danh stream của bộ đếm, để phát hiện đổi stream hoặc reset |
| `derivation` | enum: sdk, pipeline |  |  |  |
| `window_s` | integer (≥ 0) |  |  |  |
| `media_rtcp_rtt_hist` | histogram |  |  |  |
| `loss_hist` | histogram |  |  |  |
| `jitter_estimate_hist` | histogram |  |  |  |
| `rtt_windows_assessable` | integer (≥ 0) |  |  |  |
| `loss_windows_assessable` | integer (≥ 0) |  |  |  |
| `jitter_windows_assessable` | integer (≥ 0) |  |  |  |
| `valid_rtt_samples` | integer (≥ 0) |  |  |  |
| `valid_jitter_samples` | integer (≥ 0) |  |  |  |
| `media_rtcp_rtt_p50` | number (≥ 0) |  |  |  |
| `media_rtcp_rtt_p95` | number (≥ 0) |  |  |  |
| `ice_stun_rtt_p50` | number (≥ 0) |  |  |  |
| `ice_stun_rtt_p95` | number (≥ 0) |  |  |  |
| `jitter_estimate_p95` | number (≥ 0) |  |  |  |
| `measurement_coverage` | number (≥ 0, ≤ 1) |  |  |  |
| `quality_rule_version` | string |  |  |  |

- **Cột hoãn:** `window_anchor_ts, first_window_idx, stream_scope, rtp_recv_window_status, rtp_send_window_status, rtp_no_receive_window_count, rtp_recv_active_window_count, rtp_recv_unknown_window_count`: Phát hiện gián đoạn không có trong đề bài hay VIA
- **Cột chuyển đi:** `path_attribution_status`: clean_stats_columns
- **Cột bỏ:** `packets_expected, packets_lost`: packets_received_total, packets_lost_total
- **Cột có điều kiện:** 17 cột tổng hợp ở client (Tổng hợp ở client, phục vụ PoorFraction ở §13.2 của v0.4.0, không phải VIA. Chỉ giữ nếu WebRTC core xác nhận chi phí trên web và mobile)

#### `call_stats_5s`

Thống kê theo cửa sổ, chẩn đoán. **Một dòng:** Một call_id × endpoint_side × device_id × media_kind × window_idx · **Nguồn ghi:** client_sdk · **Mức nguồn:** B · **Mức thu:** sampled · **Phạm vi:** relay_or_failed

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK FK → call_session |  |
| `endpoint_side` | enum: caller, callee | có | PK |  |
| `device_id` | string | có | PK |  |
| `media_kind` | enum: audio, video | có | PK |  |
| `window_idx` | integer (≥ 0) | có | PK |  |
| `window_s` | integer (≥ 0) | có |  |  |
| `window_start_ts` | date-time | có |  |  |
| `network_epoch` | integer (≥ 0) | có |  |  |
| `network_type` | enum: wifi, 4g, 5g, ethernet, unknown |  |  |  |
| `media_rtcp_rtt_ms` | number (≥ 0) |  |  |  |
| `ice_stun_rtt_ms` | number (≥ 0) |  |  |  |
| `jitter_estimate_ms` | number (≥ 0) |  |  |  |
| `packets_lost` | integer |  |  |  |
| `audio_active_s` | number (≥ 0) |  |  |  |
| `first_media_sent_ts` | date-time |  |  |  |
| `first_media_received_ts` | date-time |  |  |  |
| `bitrate_send_kbps` | number (≥ 0) |  |  |  |
| `bitrate_recv_kbps` | number (≥ 0) |  |  |  |
| `conn_state` | enum: connected, disconnected, failed |  |  |  |
| `rtt_measurements_delta` | integer (≥ 0) |  |  | **Mới.** Delta của roundTripTimeMeasurements |
| `packets_received` | integer (≥ 0) |  |  | **Mới.** Số gói nhận trong cửa sổ |

- **Cột hoãn:** `rtp_recv_status, rtp_send_status`: Phát hiện gián đoạn không có trong đề bài hay VIA; mở lại thì cần thêm packets_sent
- **Cột chuyển đi:** `packets_expected, loss_pct, rtt_sample_valid, jitter_sample_valid, quality_rule_version, path_attribution_status, restart_gap`: clean_stats_columns

### 1.4. TURN metrics

#### `turn_health_1m`

Sức khỏe TURN theo phút. **Một dòng:** Một turn_id × minute_ts · **Nguồn ghi:** turn_server hoặc health checker · **Mức nguồn:** B · **Mức thu:** required · **Phạm vi:** not_call

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `turn_id` | string | có | PK FK → dim_turn |  |
| `minute_ts` | date-time | có | PK |  |
| `active_allocations` | integer (≥ 0) |  |  |  |
| `cpu_pct` | number (≥ 0, ≤ 100) |  |  |  |
| `bandwidth_mbps` | number (≥ 0) |  |  | Không lấy từ turn_traffic_* hay turn_total_traffic_*, vì chỉ cập nhật khi session kết thúc |
| `alloc_attempts` | integer (≥ 0) |  |  | Không lấy từ delta của gauge allocation |
| `alloc_failures` | integer (≥ 0) |  |  |  |
| `observation_state` | enum: measured, not_measured, stale, lost, ambiguous, not_applicable |  |  | **Mới.** |
| `alloc_failures_by_code` | object |  |  | 486 là quota theo username, 508 là thiếu capacity |
| `last_observed_ts` | date-time |  |  | **Mới.** |
| `sample_count` | integer (≥ 0) |  |  | **Mới.** |
| `source` | string |  |  | **Mới.** Nguồn và phiên bản của từng nhóm metric |
| `ingest_delay_ms` | number (≥ 0) |  |  | **Mới.** |
| `liveness_ok` | boolean |  |  | **Mới.** Tín hiệu sống quan sát trực tiếp; null là không có phép kiểm tra |
| `liveness_method` | enum: exporter_scrape, allocate_check, none | có |  | **Mới.** |

- **Cột chuyển đi:** `health_status, health_score, health_rule_version, assigned_by, utilization_pct`: health_snapshot, feat_turn_health

#### `turn_allocation`

Giao dịch allocation theo log của TURN. **Một dòng:** Một session allocation trong log của một TURN, với kết quả cuối · **Nguồn ghi:** turn_server · **Mức nguồn:** C · **Mức thu:** conditional · **Phạm vi:** not_call

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `turn_id` | string | có | PK FK → dim_turn |  |
| `transport` | enum: udp, tcp, tls |  |  |  |
| `turn_server_ip` | string |  |  |  |
| `relayed_ip` | string |  |  |  |
| `response_ts` | date-time |  |  |  |
| `allocation_result` | enum: success, failure, unknown | có |  | **Mới.** Thay success |
| `error_code` | enum: none, timeout, unauthorized_401, forbidden_403, quota_486, capacity_508, redirect_300, unreachable, other |  |  |  |
| `source` | enum: turn_log | có |  | **Mới.** |
| `released_ts` | date-time |  |  |  |
| `server_session_id` | string | có | PK | **Mới.** Định danh session trong log của TURN |
| `credential_ref` | string |  |  | **Mới.** Định danh theo cuộc gọi trích từ username, không phải secret; null nếu nhiều cuộc gọi dùng chung username |
| `release_reason` | string |  |  | Chỉ điều log của TURN cho biết; không suy ra call_end hay other_device_answered |

- **Cột chuyển đi:** `allocation_id, call_id, decision_id, side, device_id, match_method`: clean_allocation_columns
- **Cột bỏ:** `success`: allocation_result
- **Cột bỏ:** `request_ts, alloc_ms, attempt_seq, is_preallocation, turn_url, rank, ice_generation`: bỏ, vì chỉ có khi client có hook

### 1.5. Probe

#### `turn_probe`

Probe giữa các TURN. **Một dòng:** Một cặp TURN có hướng × cửa sổ đo × phương pháp × giao thức · **Nguồn ghi:** probe_agent · **Mức nguồn:** C · **Mức thu:** conditional · **Phạm vi:** not_call

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `src_turn_id` | string | có | PK FK → dim_turn |  |
| `dst_turn_id` | string | có | PK FK → dim_turn |  |
| `src_ip` | string |  |  | Chỉ IP máy chủ TURN |
| `dst_ip` | string |  |  | Chỉ IP máy chủ TURN |
| `window_start_ts` | date-time | có | PK |  |
| `window_end_ts` | date-time | có |  |  |
| `method_version` | string | có | PK |  |
| `protocol` | enum: udp, tcp, tls, icmp | có | PK |  |
| `target_port` | integer (≥ 0, ≤ 65535) |  |  |  |
| `measurement_kind` | enum: one_way, rtt | có |  | Nên đo rtt; một chiều cần đồng bộ đồng hồ |
| `measurement_point` | enum: client, turn_server, probe_agent | có |  |  |
| `value_ms` | number (≥ 0, ≤ 10000) |  |  |  |
| `value_ms_p95` | number (≥ 0, ≤ 10000) |  |  |  |
| `loss_pct` | number (≥ 0, ≤ 100) |  |  |  |
| `jitter_ms` | number (≥ 0) |  |  |  |
| `n_samples` | integer (≥ 0) | có |  |  |
| `clock_sync_err_ms` | number (≥ 0) |  |  |  |
| `observation_state` | enum: measured, not_measured, stale, lost, ambiguous, not_applicable |  |  |  |
| `missing_reason` | string |  |  |  |

### 1.6. Decision Log

#### `selector_decision_request`

Header chung của một quyết định Selector hoặc cấu hình tĩnh. **Một dòng:** Một decision_id, dùng chung cho danh sách hai bên và dự đoán cặp · **Nguồn ghi:** signaling · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `decision_id` | uuid | có | PK |  |
| `call_id` | uuid | có |  |  |
| `parent_decision_id` | uuid |  |  |  |
| `phase` | enum: initial, restart | có |  |  |
| `request_ts` | date-time | có |  |  |
| `policy_version` | string | có |  |  |
| `info_level` | enum: full, caller_only, country_only, none | có |  |  |

#### `selector_decision`

Hành động của Selector cho một bên. **Một dòng:** Một decision_id × side × device_id · **Nguồn ghi:** signaling (BE ghi, Selector không tự ghi) · **Mức nguồn:** A · **Mức thu:** required · **Phạm vi:** all_calls

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `decision_id` | uuid | có | PK | Chung cho hai bên của một request; không phải PK riêng |
| `parent_decision_id` | uuid |  | FK → selector_decision | **Mới.** |
| `call_id` | uuid | có | FK → call_session |  |
| `side` | enum: caller, callee | có | PK |  |
| `phase` | enum: initial, restart | có |  |  |
| `device_id` | string | có | PK |  |
| `request_ts` | date-time | có |  |  |
| `response_ts` | date-time |  |  | Null khi timeout |
| `api_latency_ms` | number (≥ 0) |  |  | Do BE đo |
| `policy_version` | string | có |  |  |
| `decision_source` | enum: api, static_config, static_fallback, cache | có |  |  |
| `info_level` | enum: full, caller_only, country_only, none | có |  |  |
| `self_ctx` | object ctx | có |  |  |
| `peer_ctx` | object ctx | có |  | Những gì biết lúc đó |
| `selection_method` | enum: deterministic, greedy, thompson, ucb, epsilon, static | có |  | **Mới.** |
| `requested_max_list_size` | integer (≥ 0) | có |  | **Mới.** Trần cho bên này |
| `returned_list_size` | integer (≥ 0) | có |  | **Mới.** Số mục thực trả |
| `entries` | mảng object list_entry | có |  | Thay candidates |
| `filtered_out` | mảng object filtered_turn | có |  |  |
| `topk_pair_count` | integer (≥ 0) |  |  | **Mới.** Đếm theo cặp, khác list size |
| `topk_capped` | boolean |  |  | **Mới.** |
| `is_exploration` | boolean | có |  |  |
| `exploration_epsilon` | number (≥ 0, ≤ 1) |  |  | Null nếu policy không có ε |
| `action_propensity` | number (≥ 0, ≤ 1) |  |  | **Mới.** Xác suất của cả hành động. Chưa ước lượng được thì null, không điền 1/k |
| `propensity_method` | enum: exact, monte_carlo, not_estimated | có |  | **Mới.** |
| `propensity_n_samples` | integer (≥ 0) |  |  | **Mới.** Khi monte_carlo |
| `eligible_action_set` | object eligible_action_set |  |  | **Mới.** |
| `confidence` | number (≥ 0, ≤ 1) |  |  |  |
| `confidence_level` | enum: high, medium, low | có |  |  |
| `confidence_evidence` | object confidence_evidence |  |  | **Mới.** |
| `fallback_reason` | string |  |  |  |
| `fallback_type` | enum: data_backoff, health_missing, selector_error, insufficient_candidates |  |  |  |
| `feature_snapshot_id` | string |  |  | Null khi policy không dùng feature, như Geo Baseline hay danh sách tĩnh |
| `health_snapshot_id` | string |  |  | Null khi static_config, static_fallback hoặc fallback_type = health_missing |
| `error_code` | string |  |  |  |

- **Cột hoãn:** `decision_mode`: Tạm thời chưa chạy bóng
- **Cột bỏ:** `k`: requested_max_list_size, returned_list_size, topk_pair_count
- **Cột bỏ:** `candidates`: entries
- **Cột bỏ:** `chosen_rank`: selector_decision_pair.is_lead
- **Cột bỏ:** `candidates[].propensity`: action_propensity, propensity_method
- **Cột bỏ:** `candidates[].est_leg_ms, est_path_ms`: selector_decision_pair

#### `selector_decision_pair`

Cặp được mô hình cân nhắc. **Một dòng:** Một decision_id × cặp × metric · **Nguồn ghi:** signaling (từ response của Selector) · **Mức nguồn:** D · **Mức thu:** conditional · **Phạm vi:** all_calls

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `decision_id` | uuid | có | PK FK → selector_decision |  |
| `call_id` | uuid | có |  |  |
| `turn_caller` | string | có | PK |  |
| `turn_callee` | string | có | PK |  |
| `transport_caller` | enum: udp, tcp, tls | có | PK |  |
| `transport_callee` | enum: udp, tcp, tls | có | PK |  |
| `metric` | string | có | PK |  |
| `unit` | string | có |  |  |
| `est_value` | number |  |  |  |
| `interval_low` | number |  |  |  |
| `interval_high` | number |  |  |  |
| `interval_kind` | enum: mean_ci, prediction, other |  |  |  |
| `interval_level` | number (≥ 0, ≤ 1) |  |  |  |
| `in_topk` | boolean | có |  |  |
| `is_lead` | boolean | có |  |  |
| `estimate_source` | string |  |  |  |
| `estimator_version` | string |  |  |  |
| `input_snapshot_id` | string |  |  | Cutoff hoặc snapshot nguồn |
| `gate_status` | enum: passed, failed, not_evaluated, not_applicable | có |  |  |
| `gate_reason` | string |  |  |  |
| `gate_rule_version` | string |  |  | Cần nếu policy_version không tham chiếu bất biến tới quy tắc |

### 1.7. Đầu vào Outcome Log

#### `call_outcome`

Điều BE quan sát về kết quả cuộc gọi. **Một dòng:** Một cuộc gọi · **Nguồn ghi:** signaling · **Mức nguồn:** A · **Mức thu:** required · **Phạm vi:** all_calls

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK FK → call_session |  |
| `ring_ts` | date-time |  |  | Lúc BE nhận tin đổ chuông, không phải lúc thiết bị bắt đầu đổ |
| `answer_received_at_be` | date-time |  |  | **Mới.** Thay answer_ts |
| `answered` | boolean |  |  |  |
| `answered_device_id` | string |  |  |  |
| `end_ts` | date-time |  |  |  |
| `end_signal` | enum: hangup, rejected, cancelled, not_answered_timeout, invite_undelivered, signaling_lost, unknown | có |  | **Mới.** |
| `end_signal_side` | enum: caller, callee |  |  | **Mới.** Bên phát tín hiệu kết thúc, nếu biết |
| `caller_ctx_final` | object ctx |  |  |  |
| `callee_ctx_final` | object ctx |  |  |  |
| `converted_to_group` | boolean |  |  |  |
| `converted_ts` | date-time |  |  |  |

- **Cột hoãn:** `caller_signaling_rtt_ms, callee_signaling_rtt_ms, n_devices_rung`: Không mô hình hóa đổ chuông và tín hiệu trong phạm vi hiện tại
- **Cột chuyển đi:** `outcome_version, outcome_status, outcome_provenance, finalized_ts, ice_connected, dtls_connected, media_connected, media_connected_rule_version, setup_failure_observed, end_reason, dropped, n_ice_attempts, n_network_changes, duration_s, pair_group`: outcome_log
- **Cột bỏ:** `connected`: outcome_log.ice_connected, dtls_connected, media_connected, outcome_status
- **Cột bỏ:** `answer_ts`: answer_received_at_be

#### `client_call_report`

Điều mỗi đầu gửi về cuộc gọi. **Một dòng:** Một call_id × side × device_id · **Nguồn ghi:** client_sdk · **Mức nguồn:** B · **Mức thu:** required · **Phạm vi:** all_calls

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK FK → call_session |  |
| `side` | enum: caller, callee | có | PK |  |
| `device_id` | string | có | PK |  |
| `answer_clicked_at_client` | date-time |  |  | **Mới.** |
| `answer_observed_at_peer` | date-time |  |  | **Mới.** |
| `client_end_reason` | string |  |  | **Mới.** Lý do app báo nếu có, chưa phân loại |
| `stats_status` | enum: kept_critical, kept_sampled, not_sampled, truncated, lost, not_applicable |  |  |  |
| `stats_sampling_prob` | number (≥ 0, ≤ 1) |  |  |  |
| `stats_sampling_reason` | string |  |  |  |
| `sampling_rule_version` | string |  |  |  |

### 1.8. Hoãn

#### `candidate_observation`

**Trạng thái:** hoãn. Quan sát relay candidate. **Một dòng:** Một candidate quan sát được, hoặc một dòng not_observed cho một mục cấu hình trong một chu kỳ thu · **Nguồn ghi:** client_sdk · **Mức nguồn:** B · **Phạm vi:** relay_or_failed

**Lý do hoãn:** Chưa dùng thời điểm nhận candidate và không sửa SDK. Đây là nguồn trực tiếp duy nhất theo từng TURN, nên mở lại nếu feature chặng ước lượng không đủ tốt

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `observation_id` | uuid | có | PK |  |
| `call_id` | uuid | có | FK → call_session |  |
| `side` | enum: caller, callee | có |  |  |
| `device_id` | string | có |  |  |
| `endpoint_id` | string | có |  |  |
| `pc_id` | string | có |  |  |
| `gathering_cycle_id` | string | có |  |  |
| `ice_generation` | integer (≥ 0) | có |  |  |
| `applied_config_id` | uuid |  | FK → client_applied_config |  |
| `clock_session_id` | string |  |  | Đồng hồ monotonic của phiên app hoặc process |
| `gathering_anchor_mono_ms` | number (≥ 0) |  |  |  |
| `anchor_kind` | enum: set_local_description, peer_connection_created, ice_restart_requested, other |  |  |  |
| `candidate_observed_mono_ms` | number (≥ 0) |  |  |  |
| `candidate_id` | string |  |  |  |
| `server_config_id` | string |  |  |  |
| `turn_url` | string |  |  |  |
| `client_turn_transport` | enum: udp, tcp, tls |  |  | Local relayProtocol |
| `candidate_protocol` | enum: udp, tcp |  |  |  |
| `candidate_type` | enum: host, srflx, prflx, relay, unknown |  |  |  |
| `relayed_ip` | string |  |  | Chỉ IP máy chủ TURN |
| `observation_status` | enum: observed, error_reported, not_observed, unsupported, session_closed, telemetry_lost | có |  |  |
| `missing_reason` | string |  |  |  |
| `collection_method` | enum: icecandidate_callback, sdk_hook, polling |  |  |  |
| `reported_error_code` | integer |  |  | Mã từ icecandidateerror, gồm cả 701 do trình duyệt báo |
| `candidate_latency_ms` | number (≥ 0) |  |  | Chênh lệch hai mốc trên cùng đồng hồ. Không phải RTT |

#### `ice_candidate_pair`

**Trạng thái:** hoãn. Cặp candidate, chỉ để chẩn đoán. **Một dòng:** Một cặp trong một attempt · **Nguồn ghi:** client_sdk · **Mức nguồn:** B · **Phạm vi:** relay_or_failed

**Lý do hoãn:** Lab chỉ thấy 1 trên 32 cặp có RTT trong 90 giây, trong khi danh sách 8 mục tạo đến 64 dòng mỗi lần thử. Cặp được chọn đã có ở ice_event

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK |  |
| `attempt_seq` | integer (≥ 0) | có | PK |  |
| `ice_generation` | integer (≥ 0) | có |  |  |
| `pair_id` | string | có | PK |  |
| `local_candidate_id` | string | có |  |  |
| `remote_candidate_id` | string | có |  |  |
| `local_candidate_type` | enum: host, srflx, prflx, relay, unknown | có |  |  |
| `remote_candidate_type` | enum: host, srflx, prflx, relay, unknown | có |  |  |
| `local_turn_id` | string |  |  |  |
| `remote_turn_id` | string |  |  |  |
| `pair_priority` | number |  |  |  |
| `check_state` | enum: waiting, in_progress, succeeded, failed |  |  |  |
| `check_count` | integer (≥ 0) |  |  |  |
| `nominated` | boolean |  |  |  |
| `selected` | boolean |  |  |  |
| `current_rtt_ms` | number (≥ 0) |  |  |  |
| `telemetry_support` | enum: full, partial |  |  |  |

### 1.9. Object dùng trong cột `json`

#### `ctx`

Bối cảnh một bên lúc quyết định (§4). Field chưa biết ghi unknown. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `user_hash` | string |  |  |  |
| `country` | string | có |  |  |
| `vn_region` | enum: north, central, south, unknown |  |  |  |
| `city` | string | có |  |  |
| `isp` | string | có |  |  |
| `asn` | integer |  |  |  |
| `network_type` | enum: wifi, 4g, 5g, ethernet, unknown | có |  |  |
| `geo_source` | enum: ip_geo, sdk_claimed, both, unknown | có |  |  |
| `geo_mismatch` | boolean |  |  |  |
| `device_id` | string | có |  |  |
| `platform` | enum: ios, android, web, desktop, unknown | có |  |  |
| `os_version` | string |  |  |  |
| `app_version` | string |  |  |  |
| `sdk_version` | string |  |  |  |
| `device_model` | string |  |  |  |
| `browser_name` | string |  |  |  |
| `browser_version` | string |  |  |  |

- **Cột chuyển đi:** `segment_key`: Feature Engineering

#### `list_entry`

Một mục trong danh sách đã cấp: một TURN server, kèm transport được cấu hình. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `entry_id` | string | có |  | **Mới.** Khóa trong một danh sách |
| `rank` | integer (≥ 1) | có |  | Vị trí trong danh sách, liên tục từ 1 |
| `turn_id` | string |  |  | Có thể null nếu mục là endpoint hoặc pool chưa gắn máy |
| `config_ref` | string |  |  | **Mới.** URL hoặc tham chiếu cấu hình |
| `normalized_config_key` | string | có |  | **Mới.** Định nghĩa duplicate trong một danh sách |
| `client_turn_transport` | enum: udp, tcp, tls | có |  | **Mới.** Selector muốn dùng giao thức nào tới TURN |
| `roles` | mảng enum: lead, topk, failure_domain_backup, transport_backup, padding | có |  | **Mới.** |
| `score` | number |  |  | Chỉ so trong một decision |
| `score_components` | object |  |  | Gồm backoff_level; hạ ưu tiên do tải ghi tại đây theo quy ước |
| `reason_codes` | mảng string |  |  |  |

#### `applied_entry`

Một mục của danh sách client đã áp dụng. Không lưu credential. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `rank` | integer (≥ 1) | có |  |  |
| `turn_url` | string | có |  |  |
| `client_turn_transport` | enum: udp, tcp, tls | có |  |  |

#### `filtered_turn`

TURN bị lọc. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `turn_id` | string | có |  |  |
| `reason` | enum: down, overloaded, degraded, maintenance, policy, health_stale | có |  |  |

#### `confidence_evidence`

Căn cứ của mức tin cậy. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `segment_level` | enum: L4, L3, L2, L1, LA, L0 |  |  |  |
| `n_calls` | integer (≥ 0) |  |  |  |
| `note` | string |  |  |  |

#### `eligible_action_set`

Tham chiếu tới tập hành động đủ điều kiện. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `ref` | string | có |  | Object hoặc snapshot bất biến, định vị được |
| `content_hash` | string |  |  | Chỉ để kiểm tra nội dung, không tự dựng lại hành động |

#### `failure_domain`

Miền lỗi; chỉ ghi chiều có nguồn hạ tầng, tuyến cáp để null nếu chưa có chứng cứ. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `provider` | string |  |  |  |
| `site` | string |  |  |  |
| `zone` | string |  |  |  |
| `host` | string |  |  |  |
| `network` | string |  |  |  |
| `cable_route` | string |  |  |  |

### 1.10. Cột chung của bảng event

#### `event_envelope`

Cột chung của mọi bảng event thô. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `event_id` | uuid | có |  | Duy nhất, dùng dedup |
| `contract_version` | string | có |  |  |
| `data_source` | enum: synthetic, lab_zenodo, lab_controlled, public_reference, production | có |  |  |
| `producer` | enum: client_sdk, signaling, selector, turn_server, probe_agent, simulator | có |  |  |
| `event_ts` | date-time | có |  | Theo đồng hồ producer; pipeline không ghi đè |
| `ingest_ts` | date-time | có |  | Lúc collector nhận |
| `sim_run_id` | string |  |  | Bắt buộc khi data_source = synthetic |
| `dt` | date | có |  | Ngày UTC của event_ts |

---

## 2. Các lớp sau thu thập

Đây là bản chuyển tiếp, giữ nội dung để không mất khi tách contract. Đặc tả đầy đủ của từng lớp viết sau.

### 2.1. Pipeline làm sạch

#### `outcome_log`

Outcome Log: view sau pipeline. **Một dòng:** Một phiên bản outcome của một cuộc gọi; view hiện hành có một dòng · **Nguồn ghi:** pipeline, từ call_outcome, client_call_report, ice_event, call_stats_epoch

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK FK → call_session |  |
| `outcome_version` | integer (≥ 0) | có | PK | **Mới.** |
| `outcome_status` | enum: complete, partial, missing | có |  | **Mới.** |
| `outcome_provenance` | enum: event, placeholder | có |  | **Mới.** |
| `finalized_ts` | date-time |  |  | **Mới.** |
| `ring_ts` | date-time |  |  | Lúc BE nhận tin đổ chuông, không phải lúc thiết bị bắt đầu đổ |
| `answer_clicked_at_client` | date-time |  |  | **Mới.** |
| `answer_received_at_be` | date-time |  |  | **Mới.** Thay answer_ts |
| `answer_observed_at_peer` | date-time |  |  | **Mới.** |
| `answered` | boolean |  |  |  |
| `answered_device_id` | string |  |  |  |
| `ice_connected` | enum: true, false, unknown | có |  | **Mới.** Thay connected |
| `dtls_connected` | enum: true, false, unknown | có |  | **Mới.** |
| `media_connected` | enum: true, false, unknown | có |  | **Mới.** false là đã xác nhận không đạt tiêu chí media trong khoảng đánh giá |
| `media_connected_rule_version` | string |  |  | **Mới.** Một hay hai endpoint, chiều và loại media, mốc đánh giá |
| `setup_failure_observed` | boolean |  |  | **Mới.** |
| `end_ts` | date-time |  |  |  |
| `duration_s` | number (≥ 0) |  |  |  |
| `end_reason` | enum: normal_hangup, invite_undelivered, not_answered, rejected, cancelled_by_caller, ice_failed, media_setup_failed, dropped_network, dropped_turn, app_crash, unknown | có |  |  |
| `dropped` | boolean |  |  |  |
| `caller_ctx_final` | object ctx |  |  |  |
| `callee_ctx_final` | object ctx |  |  |  |
| `pair_group` | enum: VN_VN, VN_INTL, INTL_INTL |  |  |  |
| `converted_to_group` | boolean |  |  |  |
| `converted_ts` | date-time |  |  |  |
| `n_ice_attempts` | integer (≥ 0) |  |  |  |
| `n_network_changes` | integer (≥ 0) |  |  |  |
| `stats_status` | enum: kept_critical, kept_sampled, not_sampled, truncated, lost, not_applicable |  |  |  |
| `stats_sampling_prob` | number (≥ 0, ≤ 1) |  |  |  |
| `stats_sampling_reason` | string |  |  |  |
| `sampling_rule_version` | string |  |  |  |
| `end_reason_rule_version` | string |  |  | **Mới.** Quy tắc phân loại end_reason từ end_signal, client_end_reason và sự kiện ICE |

#### `ice_attempt`

Một lần thử ICE, do pipeline dựng. **Một dòng:** Một call_id × attempt_seq · **Nguồn ghi:** pipeline, từ ice_event · **Mức nguồn:** B

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK FK → call_session |  |
| `attempt_seq` | integer (≥ 0) | có | PK |  |
| `ice_generation` | integer (≥ 0) | có |  |  |
| `caller_device_id` | string | có |  |  |
| `callee_device_id` | string | có |  |  |
| `trigger` | enum: initial, restart_network_change, restart_failure, restart_disconnected, restart_quality | có |  |  |
| `caller_decision_id` | uuid |  |  | **Mới.** |
| `callee_decision_id` | uuid |  |  | **Mới.** |
| `caller_applied_config_id` | uuid |  | FK → client_applied_config | **Mới.** |
| `callee_applied_config_id` | uuid |  | FK → client_applied_config | **Mới.** |
| `network_epoch` | integer (≥ 0) | có |  |  |
| `state` | enum: connected, failed, timeout, cancelled, unknown | có |  |  |
| `turn_used` | boolean |  |  |  |
| `caller_candidate_type` | enum: host, srflx, prflx, relay, unknown |  |  | **Mới.** Local candidate của đầu Caller |
| `callee_candidate_type` | enum: host, srflx, prflx, relay, unknown |  |  | **Mới.** Local candidate của đầu Callee |
| `path_type` | enum: relay_relay, relay_same, relay_unresolved, relay_direct, p2p_host, p2p_srflx, unknown |  |  | Null chỉ khi chưa có selected path |
| `relay_turn_caller` | string |  |  |  |
| `relay_turn_callee` | string |  |  |  |
| `relayed_ip_caller` | string |  |  | Chỉ IP máy chủ TURN |
| `relayed_ip_callee` | string |  |  | Chỉ IP máy chủ TURN |
| `caller_allocation_id` | uuid |  |  |  |
| `callee_allocation_id` | uuid |  |  |  |
| `rank_caller` | integer (≥ 0) |  |  | Theo danh sách đã áp dụng |
| `rank_callee` | integer (≥ 0) |  |  | Theo danh sách đã áp dụng |
| `client_turn_transport_caller` | enum: udp, tcp, tls |  |  | **Mới.** |
| `client_turn_transport_callee` | enum: udp, tcp, tls |  |  | **Mới.** |
| `candidate_protocol_caller` | enum: udp, tcp |  |  | **Mới.** |
| `candidate_protocol_callee` | enum: udp, tcp |  |  | **Mới.** |
| `ice_connected_any_ts` | date-time |  |  | **Mới.** Sớm nhất giữa hai endpoint. Không dùng để tính duration |
| `failure_reason` | string |  |  |  |

- **Cột bỏ:** `decision_id`: caller_decision_id, callee_decision_id
- **Cột bỏ:** `transport`: client_turn_transport_caller, client_turn_transport_callee
- **Cột bỏ:** `selected_local_candidate_type, selected_remote_candidate_type`: caller_candidate_type, callee_candidate_type; ice_attempt_endpoint
- **Cột bỏ:** `start_ts, checks_start_ts, ice_connected_ts, dtls_connected_ts, end_ts`: ice_attempt_endpoint

#### `ice_attempt_endpoint`

Tóm tắt một lần thử theo từng endpoint, do pipeline dựng. **Một dòng:** Một call_id × attempt_seq × side × device_id · **Nguồn ghi:** pipeline, từ ice_event · **Mức nguồn:** B

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK FK → ice_attempt |  |
| `attempt_seq` | integer (≥ 0) | có | PK FK → ice_attempt |  |
| `side` | enum: caller, callee | có | PK |  |
| `device_id` | string | có | PK |  |
| `pc_id` | string | có |  |  |
| `ice_generation` | integer (≥ 0) | có |  |  |
| `clock_session_id` | string |  |  |  |
| `start_ts` | date-time |  |  |  |
| `ice_checking_observed_ts` | date-time |  |  | Proxy khi không có hook; không gọi là STUN check đầu tiên |
| `checks_start_ts` | date-time |  |  | Chỉ khi có hook thấp tầng |
| `ice_connected_ts` | date-time |  |  |  |
| `dtls_connected_ts` | date-time |  |  |  |
| `end_ts` | date-time |  |  |  |
| `checking_to_connected_ms` | number (≥ 0) |  |  | Trừ trên cùng đồng hồ của endpoint |
| `state` | enum: connected, failed, timeout, cancelled, unknown | có |  |  |
| `ice_role` | enum: controlling, controlled, unknown |  |  |  |
| `local_candidate_type` | enum: host, srflx, prflx, relay, unknown |  |  |  |
| `remote_candidate_type` | enum: host, srflx, prflx, relay, unknown |  |  |  |
| `local_turn_id` | string |  |  |  |
| `relayed_ip_local` | string |  |  |  |
| `client_turn_transport` | enum: udp, tcp, tls |  |  |  |
| `candidate_protocol` | enum: udp, tcp |  |  |  |
| `selected_pair_changes` | integer (≥ 0) |  |  |  |

#### `telemetry_coverage`

Phần dữ liệu thiếu khi không có dòng. **Một dòng:** Một nguồn × phạm vi × khoảng thời gian · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `window_start_ts` | date-time | có |  |  |
| `window_end_ts` | date-time | có |  |  |
| `source_table` | string | có |  |  |
| `field_group` | string |  |  |  |
| `observation_profile` | enum: obs_base, obs_active, obs_infra |  |  |  |
| `capability` | enum: supported, unsupported, not_configured | có |  |  |
| `observation_method` | string |  |  | Có thể khai báo ở cấp profile hoặc nguồn |
| `platform` | enum: ios, android, web, desktop, unknown |  |  |  |
| `app_version` | string |  |  |  |
| `policy_version` | string |  |  |  |
| `call_id` | uuid |  |  | Khi tính coverage cho một cuộc gọi |
| `n_expected` | integer (≥ 0) |  |  |  |
| `n_observed` | integer (≥ 0) |  |  |  |
| `n_not_measured` | integer (≥ 0) |  |  |  |
| `n_stale` | integer (≥ 0) |  |  |  |
| `n_lost` | integer (≥ 0) |  |  |  |
| `n_ambiguous` | integer (≥ 0) |  |  |  |
| `n_not_applicable` | integer (≥ 0) |  |  |  |

#### `dq_results`

Kết quả kiểm tra chất lượng dữ liệu. **Một dòng:** Một lần chạy × check × bảng · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `pipeline_run_id` | string | có | PK |  |
| `dt` | date | có |  |  |
| `check_id` | string | có | PK |  |
| `table` | string | có | PK |  |
| `level` | enum: FAIL, WARN | có |  |  |
| `status` | enum: pass, fail, warn, not_evaluable | có |  |  |
| `n_checked` | integer (≥ 0) | có |  |  |
| `n_bad` | integer (≥ 0) | có |  |  |
| `n_not_evaluable` | integer (≥ 0) | có |  | **Mới.** |
| `sample_event_ids` | mảng uuid |  |  |  |
| `correction_rule_version` | string |  |  | Khi metric bị cách ly theo §8.5 |

#### `clean_clock_columns`

Cột pipeline thêm cho bảng có mốc thời gian. **Một dòng:** Đi kèm dòng event · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `event_ts_corrected` | date-time |  |  |  |
| `clock_skew_ms` | number |  |  |  |
| `clock_correction_version` | string |  |  |  |
| `clock_quality_flag` | enum: ok, corrected, unreliable |  |  |  |

#### `clean_stats_columns`

Cột pipeline tính từ getStats. **Một dòng:** Đi kèm dòng call_stats_5s hoặc call_stats_epoch · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `packets_expected` | integer (≥ 0) |  |  |  |
| `loss_pct` | number (≥ 0, ≤ 100) |  |  |  |
| `rtt_sample_valid` | boolean |  |  |  |
| `jitter_sample_valid` | boolean |  |  |  |
| `quality_rule_version` | string |  |  |  |
| `path_attribution_status` | enum: single_path, mixed, unknown |  |  | **Mới.** |
| `restart_gap` | boolean |  |  |  |

#### `clean_ice_event_columns`

Cột pipeline tra từ ice_event. **Một dòng:** Đi kèm dòng ice_event · **Nguồn ghi:** pipeline, tra relayed_ip_* qua dim_turn_endpoint · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `local_turn_id` | string |  |  |  |
| `remote_turn_id` | string |  |  |  |

#### `clean_allocation_columns`

Cột pipeline thêm cho turn_allocation. **Một dòng:** Đi kèm dòng event · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `used_by_ice` | boolean |  |  |  |
| `match_method` | enum: id, rule, token, ambiguous |  |  |  |
| `allocation_id` | uuid |  |  |  |
| `call_id` | uuid |  |  |  |
| `decision_id` | uuid |  |  |  |
| `side` | enum: caller, callee |  |  |  |
| `device_id` | string |  |  |  |

#### `clean_leg_columns`

Cột pipeline thêm cho path_leg_measurement. **Một dòng:** Đi kèm dòng event · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `one_way_ms_observed` | number (≥ 0, ≤ 10000) |  |  |  |
| `one_way_ms_estimated` | number (≥ 0, ≤ 10000) |  |  |  |
| `symmetric_assumption` | boolean |  |  |  |

### 2.2. Feature Engineering

#### `feature_snapshot`

Metadata snapshot feature. **Một dòng:** Một snapshot · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `snapshot_id` | string | có | PK |  |
| `cutoff_ts` | date-time | có |  |  |
| `published_ts` | date-time | có |  |  |
| `pipeline_version` | string | có |  |  |
| `content_hash` | string | có |  |  |
| `parent_snapshot_id` | string |  |  |  |

#### `feat_leg_stats`

Chặng user↔TURN. **Một dòng:** Một snapshot × segment × TURN × hướng × metric × giờ · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `snapshot_id` | string | có | PK |  |
| `segment_level` | enum: L4, L3, L2, L1, LA, L0 | có | PK |  |
| `segment_key` | string | có | PK |  |
| `turn_id` | string | có | PK |  |
| `direction` | enum: user_to_turn, turn_to_user | có | PK |  |
| `metric` | enum: one_way_observed, rtt | có | PK |  |
| `hour_bucket` | string | có | PK |  |
| `n_raw` | integer (≥ 0) | có |  |  |
| `n_eff` | number (≥ 0) | có |  | Khối lượng mẫu đã decay (Σw). Không phải cỡ mẫu độc lập |
| `p50` | number (≥ 0) |  |  |  |
| `p95` | number (≥ 0) |  |  |  |
| `loss_mean` | number (≥ 0, ≤ 100) |  |  |  |
| `jitter_p95` | number (≥ 0) |  |  |  |
| `p50_shrunk` | number (≥ 0) |  |  |  |
| `source_mix` | object |  |  |  |
| `last_observed_ts` | date-time |  |  |  |
| `sum_w` | number (≥ 0) |  |  |  |
| `sum_w2` | number (≥ 0) |  |  |  |
| `n_calls_independent` | integer (≥ 0) |  |  |  |
| `n_endpoints` | integer (≥ 0) |  |  |  |
| `n_windows` | integer (≥ 0) |  |  |  |
| `log_mean` | number |  |  |  |
| `log_sd` | number (≥ 0) |  |  |  |
| `coverage` | number (≥ 0, ≤ 1) |  |  |  |
| `value_kind` | hằng: estimated | có |  | **Mới.** Luôn là số ước lượng, vì getStats không đo từng chặng |
| `estimator_version` | string |  |  | **Mới.** |

#### `feat_turn_turn`

Chặng TURN↔TURN. **Một dòng:** Một snapshot × cặp TURN có hướng × metric × giờ · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `snapshot_id` | string | có | PK |  |
| `src_turn` | string | có | PK |  |
| `dst_turn` | string | có | PK |  |
| `metric` | enum: one_way_observed, rtt | có | PK |  |
| `hour_bucket` | string | có | PK |  |
| `n_raw` | integer (≥ 0) | có |  |  |
| `n_eff` | number (≥ 0) | có |  | Khối lượng mẫu đã decay (Σw). Không phải cỡ mẫu độc lập |
| `p50` | number (≥ 0) |  |  |  |
| `p95` | number (≥ 0) |  |  |  |
| `loss_mean` | number (≥ 0, ≤ 100) |  |  |  |
| `jitter_p95` | number (≥ 0) |  |  |  |
| `source_mix` | object |  |  |  |
| `last_observed_ts` | date-time |  |  |  |
| `sum_w` | number (≥ 0) |  |  |  |
| `sum_w2` | number (≥ 0) |  |  |  |
| `n_calls_independent` | integer (≥ 0) |  |  |  |
| `n_endpoints` | integer (≥ 0) |  |  |  |
| `n_windows` | integer (≥ 0) |  |  |  |
| `log_mean` | number |  |  |  |
| `log_sd` | number (≥ 0) |  |  |  |
| `coverage` | number (≥ 0, ≤ 1) |  |  |  |
| `value_kind` | enum: measured, estimated | có |  | **Mới.** measured khi từ turn_probe. estimated chỉ khi có mẫu dùng chung TURN; không có thì không tách được khỏi chặng |
| `estimator_version` | string |  |  | **Mới.** |

#### `feat_turn_health`

Sức khỏe TURN theo ngày. **Một dòng:** Một snapshot × TURN · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `snapshot_id` | string | có | PK |  |
| `turn_id` | string | có | PK |  |
| `health_status` | enum: healthy, degraded, overloaded, down, maintenance, unknown | có |  |  |
| `health_score` | number (≥ 0, ≤ 1) |  |  |  |
| `utilization_p95_24h` | number (≥ 0, ≤ 150) |  |  |  |
| `alloc_success_24h` | number (≥ 0, ≤ 1) |  |  |  |
| `ci_low` | number (≥ 0, ≤ 1) |  |  |  |
| `ci_high` | number (≥ 0, ≤ 1) |  |  |  |
| `incidents_detected_7d` | integer (≥ 0) |  |  |  |
| `stability_cv_24h` | number (≥ 0) |  |  |  |

#### `feat_path_history`

Lịch sử theo đường. **Một dòng:** Một snapshot × hai segment × cặp TURN · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `snapshot_id` | string | có | PK |  |
| `caller_segment_key` | string | có | PK |  |
| `callee_segment_key` | string | có | PK |  |
| `segment_level` | enum: L4, L3, L2, L1, LA, L0 |  |  | Thêm L3 × L3 cho Việt Nam, có backoff |
| `turn_caller` | string | có | PK |  |
| `turn_callee` | string | có | PK |  |
| `n_calls` | integer (≥ 0) | có |  |  |
| `n_eff` | number (≥ 0) | có |  | Khối lượng mẫu đã decay (Σw). Không phải cỡ mẫu độc lập |
| `poor_rate` | number (≥ 0, ≤ 1) |  |  |  |
| `poor_rate_ci_low` | number (≥ 0, ≤ 1) |  |  |  |
| `poor_rate_ci_high` | number (≥ 0, ≤ 1) |  |  |  |
| `drop_rate` | number (≥ 0, ≤ 1) |  |  |  |
| `setup_fail_rate` | number (≥ 0, ≤ 1) |  |  |  |
| `last_observed_ts` | date-time |  |  |  |
| `rtt_p50` | number (≥ 0) |  |  |  |
| `rtt_p95` | number (≥ 0) |  |  |  |
| `loss_mean` | number (≥ 0, ≤ 100) |  |  |  |
| `jitter_p95` | number (≥ 0) |  |  |  |
| `sum_w` | number (≥ 0) |  |  |  |
| `sum_w2` | number (≥ 0) |  |  |  |
| `n_calls_independent` | integer (≥ 0) |  |  |  |
| `n_endpoints` | integer (≥ 0) |  |  |  |
| `n_windows` | integer (≥ 0) |  |  |  |
| `log_mean` | number |  |  |  |
| `log_sd` | number (≥ 0) |  |  |  |
| `coverage` | number (≥ 0, ≤ 1) |  |  |  |

#### `health_snapshot`

Snapshot health mỗi phút. **Một dòng:** Một health_snapshot_id × TURN · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `health_snapshot_id` | string | có | PK |  |
| `cutoff_ts` | date-time | có |  |  |
| `published_ts` | date-time | có |  |  |
| `turn_id` | string | có | PK |  |
| `health_status` | enum: healthy, degraded, overloaded, down, maintenance, unknown | có |  |  |
| `health_score` | number (≥ 0, ≤ 1) |  |  |  |
| `utilization_pct_5m` | number (≥ 0, ≤ 150) |  |  |  |
| `alloc_fail_rate_5m` | number (≥ 0, ≤ 1) |  |  |  |
| `last_observed_ts` | date-time |  |  | **Mới.** Snapshot mới không làm số đo cũ trở thành mới |
| `source` | string |  |  | **Mới.** |
| `health_rule_version` | string |  |  | **Mới.** |
| `observation_state` | enum: measured, not_measured, stale, lost, ambiguous, not_applicable |  |  | **Mới.** |
| `assigned_by` | string |  |  | **Mới.** Nơi gán health_status |

#### `dim_user`

Danh mục user. **Một dòng:** Một user_hash · **Mức nguồn:** B

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `user_hash` | string | có | PK |  |
| `home_country` | string | có |  |  |
| `home_vn_region` | enum: north, central, south, unknown |  |  |  |
| `home_city` | string | có |  |  |
| `home_isp` | string | có |  |  |
| `home_asn` | integer |  |  |  |
| `primary_network` | enum: wifi, 4g, 5g, ethernet, unknown | có |  |  |
| `cohort` | enum: normal, cold_start | có |  |  |
| `created_at` | date-time | có |  |  |

#### `feat_callee_prior`

**Trạng thái:** hoãn. Phân bố Callee khi gọi mù. **Một dòng:** Một snapshot × segment Caller × nơi Callee · **Nguồn ghi:** pipeline · **Mức nguồn:** D

**Lý do hoãn:** Chỉ phục vụ gọi mù; Selector biết Callee ngay từ đầu

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `snapshot_id` | string | có | PK |  |
| `caller_segment_key` | string | có | PK |  |
| `callee_country` | string | có | PK |  |
| `callee_vn_region` | enum: north, central, south, unknown |  | PK |  |
| `n` | integer (≥ 0) | có |  |  |
| `share` | number (≥ 0, ≤ 1) | có |  |  |

#### `feat_turn_alloc_latency`

**Trạng thái:** hoãn. Độ trễ allocation. **Một dòng:** Một snapshot × segment × TURN × transport · **Nguồn ghi:** pipeline · **Mức nguồn:** D

**Lý do hoãn:** Mất đầu vào, vì alloc_ms đã bỏ

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `snapshot_id` | string | có | PK |  |
| `segment_key` | string | có | PK |  |
| `turn_id` | string | có | PK |  |
| `transport` | enum: udp, tcp, tls | có | PK |  |
| `n` | integer (≥ 0) | có |  |  |
| `n_known` | integer (≥ 0) |  |  | **Mới.** |
| `n_unknown` | integer (≥ 0) |  |  | **Mới.** |
| `alloc_ms_p50` | number (≥ 0) |  |  |  |
| `alloc_ms_p95` | number (≥ 0) |  |  |  |
| `alloc_success_rate` | number (≥ 0, ≤ 1) |  |  | Có điều kiện trên giao dịch đã biết kết quả |
| `alloc_success_ci_low` | number (≥ 0, ≤ 1) |  |  |  |
| `alloc_success_ci_high` | number (≥ 0, ≤ 1) |  |  |  |

#### `feat_estimated_user_turn_rtt`

**Trạng thái:** hoãn. RTT user↔TURN ước lượng từ candidate. **Một dòng:** Một snapshot × segment × TURN × transport × đại lượng · **Nguồn ghi:** pipeline · **Mức nguồn:** D

**Lý do hoãn:** Mất đầu vào, vì candidate_observation đã hoãn

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `snapshot_id` | string | có | PK |  |
| `segment_level` | enum: L4, L3, L2, L1, LA, L0 | có | PK |  |
| `segment_key` | string | có | PK |  |
| `turn_id` | string | có | PK |  |
| `client_turn_transport` | enum: udp, tcp, tls | có | PK |  |
| `estimand` | enum: network_rtt, transaction_time, candidate_total_time | có | PK |  |
| `unit` | string | có |  |  |
| `estimated_user_turn_rtt_ms` | number (≥ 0) |  |  |  |
| `interval_low` | number (≥ 0) |  |  |  |
| `interval_high` | number (≥ 0) |  |  |  |
| `interval_kind` | enum: mean_ci, prediction, other |  |  |  |
| `interval_level` | number (≥ 0, ≤ 1) |  |  |  |
| `estimate_source` | string | có |  |  |
| `estimator_version` | string | có |  |  |
| `input_snapshot_id` | string |  |  |  |
| `validation_status` | enum: not_validated, validated, rejected | có |  |  |
| `gate_status` | enum: passed, failed, not_evaluated, not_applicable | có |  |  |
| `gate_reason` | string |  |  |  |
| `gate_rule_version` | string |  |  |  |

### 2.3. Labeled Data và Evaluation

#### `fact_call`

**Trạng thái:** chưa đủ cột. Một dòng mỗi cuộc gọi. **Một dòng:** Một call_id trong cohort · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK FK → call_session |  |
| `local_hour_vn` | integer (≥ 0) |  |  | Suy từ initiated_ts |
| `pcr_group` | enum: K, G, U_quality, U_outcome |  |  | **Mới.** Null khi cohort chưa chốt |
| `poor_category` | enum: setup_fail, drop, quality, poor_unattributed, none |  |  |  |
| `quality_assessment_status` | enum: assessed, partially_assessed, unclassifiable, not_applicable |  |  |  |
| `outcome_status` | enum: complete, partial, missing | có |  | **Mới.** |
| `policy_version` | string |  |  |  |
| `action_propensity` | number (≥ 0, ≤ 1) |  |  | **Mới.** Của hành động trong decision mà attempt nối đầu tiên dùng; hai bên khác decision thì null |
| `propensity_decision_id` | uuid |  |  | **Mới.** |
| `rank_used_caller` | integer (≥ 0) |  |  |  |
| `rank_used_callee` | integer (≥ 0) |  |  |  |
| `lead_pair_matched` | enum: true, false, unknown |  |  |  |
| `actual_turn_id_caller` | string |  |  | Chỉ khi identified |
| `actual_turn_id_callee` | string |  |  | Chỉ khi identified |
| `turn_identity_status_caller` | enum: identified, ambiguous, unmapped, unknown | có |  | **Mới.** |
| `turn_identity_status_callee` | enum: identified, ambiguous, unmapped, unknown | có |  | **Mới.** |
| `turn_identity_method_caller` | enum: ip, hostname, server_evidence, none |  |  |  |
| `turn_identity_method_callee` | enum: ip, hostname, server_evidence, none |  |  |  |
| `identity_check_caller` | enum: match, mismatch, not_evaluable | có |  | **Mới.** Kết quả I19 |
| `identity_check_callee` | enum: match, mismatch, not_evaluable | có |  | **Mới.** Kết quả I19 |
| `platform_caller` | enum: ios, android, web, desktop, unknown |  |  |  |
| `platform_callee` | enum: ios, android, web, desktop, unknown |  |  |  |
| `app_version_caller` | string |  |  |  |
| `app_version_callee` | string |  |  |  |
| `device_class_caller` | string |  |  |  |
| `device_class_callee` | string |  |  |  |
| `cohort_name` | string | có |  |  |
| `pair_group` | enum: VN_VN, VN_INTL, INTL_INTL |  |  | Null khi chưa đủ địa lý hai bên |
| `initiated_ts` | date-time | có |  |  |
| `answer_received_at_be` | date-time |  |  |  |
| `end_ts` | date-time |  |  |  |
| `answered` | enum: true, false, unknown | có |  |  |
| `ice_connected` | enum: true, false, unknown | có |  |  |
| `dtls_connected` | enum: true, false, unknown | có |  |  |
| `media_connected` | enum: true, false, unknown | có |  |  |
| `setup_failure_observed` | boolean |  |  |  |
| `dropped` | boolean |  |  |  |
| `end_reason` | enum: normal_hangup, invite_undelivered, not_answered, rejected, cancelled_by_caller, ice_failed, media_setup_failed, dropped_network, dropped_turn, app_crash, unknown | có |  |  |
| `outcome_version` | integer (≥ 0) |  |  | Null khi outcome thiếu |
| `outcome_provenance` | enum: event, placeholder |  |  |  |
| `n_ice_attempts` | integer (≥ 0) |  |  |  |
| `n_network_changes` | integer (≥ 0) |  |  |  |
| `cst_technical_ms` | number (≥ 0) |  |  | Max CST cục bộ hai endpoint khi cả hai measured |
| `cst_assessment` | enum: measured, not_measured, lost, stale, ambiguous, not_applicable | có |  |  |
| `ttfm_post_answer_ms` | number (≥ 0) |  |  | Max TTFM cục bộ hai endpoint khi cả hai measured |
| `ttfm_assessment` | enum: measured, not_measured, lost, stale, ambiguous, not_applicable | có |  |  |
| `quality_poor` | enum: true, false, unknown | có |  | unknown khi không đủ telemetry |
| `quality_rule_version` | string |  |  |  |
| `stats_expected_endpoint_count` | integer (≥ 0) |  |  |  |
| `stats_observed_endpoint_count` | integer (≥ 0) | có |  |  |
| `stats_endpoint_coverage` | number (≥ 0) |  |  |  |
| `caller_decision_id` | uuid |  |  |  |
| `callee_decision_id` | uuid |  |  |  |
| `first_connected_attempt_seq` | integer (≥ 0) |  |  |  |
| `as_of_ts` | date-time | có |  | Cutoff của lần dựng. Bảng giữ bản hiện hành (fact_version lớn nhất đã ingest tại cutoff); lịch sử các bản nằm ở log của pipeline |
| `fact_version` | integer (≥ 1) | có |  | Tăng khi dữ liệu đến muộn làm đổi dòng |
| `call_path_scope` | enum: p2p, relay, failed, unknown | có |  |  |
| `path_type` | enum: relay_relay, relay_same, relay_unresolved, relay_direct, p2p_host, p2p_srflx, unknown |  |  | Từ outcome_log/ice_attempt; null khi không có selected path |
| `path_attribution_status` | enum: single_path, mixed, unknown |  |  |  |
| `observation_profile` | enum: obs_base, obs_active, obs_infra |  |  | Synthetic lấy từ run_manifest; production null hoặc theo cấu hình thu |
| `connection_mode` | enum: post_answer, pre_connect |  |  |  |
| `ice_transport_policy` | enum: relay, all |  |  | Cấu hình, không chứng minh đường thực tế |
| `decision_source_caller` | string |  |  | api, static_config, static_fallback hoặc cache từ selector_decision |
| `decision_source_callee` | string |  |  |  |
| `policy_version_caller` | string |  |  |  |
| `policy_version_callee` | string |  |  |  |
| `fallback_type_caller` | enum: data_backoff, health_missing, selector_error, insufficient_candidates |  |  |  |
| `fallback_type_callee` | enum: data_backoff, health_missing, selector_error, insufficient_candidates |  |  |  |
| `returned_list_size_caller` | integer (≥ 0) |  |  |  |
| `returned_list_size_callee` | integer (≥ 0) |  |  |  |
| `lead_turn_caller` | string |  |  | turn_id của cặp dẫn đầu phía caller; null khi static_config |
| `lead_turn_callee` | string |  |  |  |
| `country_caller` | string |  |  | Bối cảnh đầu tiên biết được; lịch sử đổi mạng ở fact_call_endpoint |
| `country_callee` | string |  |  |  |
| `vn_region_caller` | enum: north, central, south, unknown |  |  |  |
| `vn_region_callee` | enum: north, central, south, unknown |  |  |  |
| `isp_caller` | string |  |  |  |
| `isp_callee` | string |  |  |  |
| `network_type_caller` | enum: wifi, 4g, 5g, ethernet, unknown |  |  |  |
| `network_type_callee` | enum: wifi, 4g, 5g, ethernet, unknown |  |  |  |
| `turn_availability_status_caller` | enum: local_turn_available, no_healthy_turn, no_turn_observed, unknown |  |  |  |
| `turn_availability_status_callee` | enum: local_turn_available, no_healthy_turn, no_turn_observed, unknown |  |  |  |
| `used_fallback_turn_caller` | enum: true, false, unknown |  |  |  |
| `used_fallback_turn_callee` | enum: true, false, unknown |  |  |  |
| `quality_assessed_endpoint_count` | integer (≥ 0) | có |  | Số endpoint có quality_assessment_status = assessed; cùng mẫu số stats_expected_endpoint_count |
| `confidence_level_caller` | enum: high, medium, low |  |  | Lọc kịch bản Historical Cold-start |
| `confidence_level_callee` | enum: high, medium, low |  |  |  |
| `n_ice_restarts` | integer (≥ 0) |  |  | Số lần restart_requested; null khi nền tảng không báo |
| `n_selected_pair_changes` | integer (≥ 0) |  |  | Tổng lần tăng selected_pair_changes; không phải lần nào cũng là đổi đường |
| `failure_phase` | enum: none, pre_allocation, post_allocation, mid_call, unknown | có |  |  |
| `detected_to_ice_recovery_ms` | number (≥ 0) |  |  | Từ lúc client phát hiện disconnected/failed đến khi ICE nối lại; từ ice_event, cùng clock_session_id. Max khi nhiều lần phục hồi |
| `recovery_assessment` | enum: measured, not_measured, lost, stale, ambiguous, not_applicable | có |  |  |
| `fault_to_recovery_ms` | number (≥ 0) |  |  | Chỉ synthetic hoặc thí nghiệm có kiểm soát (biết mốc fault từ incident_truth); production luôn null |

- **Cột hoãn:** `arm`: Hoãn cùng các cột thí nghiệm
- **Cột bỏ:** `joint_propensity`: action_propensity
- **Cột bỏ:** `turn_identity_method`: turn_identity_status_*, turn_identity_method_*

#### `fact_call_endpoint`

Một dòng cho một endpoint tham gia cuộc gọi, gồm metric tổng hợp và tham chiếu lịch sử. **Một dòng:** Một call_id × side × device_id · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có | PK |  |
| `side` | enum: caller, callee | có | PK |  |
| `device_id` | string | có | PK |  |
| `country` | string |  |  |  |
| `vn_region` | enum: north, central, south, unknown |  |  |  |
| `city` | string |  |  |  |
| `isp` | string |  |  |  |
| `asn` | integer |  |  |  |
| `network_type_initial` | enum: wifi, 4g, 5g, ethernet, unknown |  |  |  |
| `context_source` | string |  |  |  |
| `network_epoch_refs` | mảng integer (≥ 0) | có |  | Join call_stats_epoch bằng call_id/side/device_id/network_epoch |
| `attempt_refs` | mảng integer (≥ 0) | có |  | Join ice_attempt_endpoint bằng call_id/attempt_seq/side/device_id |
| `first_connected_attempt_seq` | integer (≥ 0) |  |  |  |
| `first_connected_turn_id` | string |  |  | Chỉ khi identity được xác nhận; không thay cho toàn bộ history |
| `first_connected_transport` | enum: udp, tcp, tls |  |  |  |
| `turn_identity_status` | enum: identified, ambiguous, unmapped, unknown | có |  |  |
| `turn_availability_status` | enum: local_turn_available, no_healthy_turn, no_turn_observed, unknown |  |  | Tra dim_turn/dim_turn_endpoint theo country và turn_health_1m tại as_of của decision; thiếu thì unknown |
| `used_fallback_turn` | enum: true, false, unknown |  |  | true khi TURN thực tế không thuộc country của endpoint; chỉ xét khi turn_identity_status = identified |
| `answer_local_ts` | date-time |  |  | answer_clicked_at_client hoặc answer_observed_at_peer của chính endpoint |
| `first_media_received_ts` | date-time |  |  |  |
| `cst_technical_ms` | number (≥ 0) |  |  | checking_to_connected_ms của attempt thành công đầu tiên |
| `cst_assessment` | enum: measured, not_measured, lost, stale, ambiguous, not_applicable | có |  |  |
| `ttfm_post_answer_ms` | number (≥ 0) |  |  | first_media_received_ts trừ answer_local_ts trên cùng đồng hồ endpoint |
| `ttfm_assessment` | enum: measured, not_measured, lost, stale, ambiguous, not_applicable | có |  |  |
| `rtt_ms` | object metric_observation | có |  |  |
| `packet_loss_pct` | object | có |  |  |
| `jitter_ms` | object metric_observation | có |  |  |
| `quality_assessment_status` | enum: assessed, partially_assessed, unclassifiable, not_applicable | có |  |  |
| `quality_poor` | enum: true, false, unknown | có |  |  |
| `quality_rule_version` | string |  |  |  |

#### `fact_pair_evaluation`

Đánh giá một dự đoán cặp so với kết quả quan sát. **Một dòng:** Một decision_id × metric × cặp (TURN và transport hai phía), bản hiện hành tại cutoff · **Nguồn ghi:** pipeline · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có |  |  |
| `decision_id` | uuid | có | PK |  |
| `metric` | string | có | PK | Đại lượng dự đoán, ví dụ media_rtcp_rtt_ms hoặc connection_success |
| `unit` | string |  |  |  |
| `turn_caller` | string | có | PK |  |
| `transport_caller` | enum: udp, tcp, tls | có | PK |  |
| `turn_callee` | string | có | PK |  |
| `transport_callee` | enum: udp, tcp, tls | có | PK |  |
| `is_lead` | boolean | có |  |  |
| `in_topk` | boolean | có |  |  |
| `est_value` | number |  |  |  |
| `interval_low` | number |  |  |  |
| `interval_high` | number |  |  |  |
| `interval_kind` | enum: mean_ci, prediction, other |  |  |  |
| `interval_level` | number (≥ 0) |  |  |  |
| `estimator_version` | string |  |  |  |
| `actual_pair_matches` | enum: true, false, unknown | có |  | true khi cặp thực tế (hai TURN identified và transport) trùng cặp này; unknown khi chưa xác định |
| `label_status` | enum: observed, not_observable, setup_failed, identity_unresolved, not_actual_pair | có |  |  |
| `observed_metric_name` | string |  |  | Tên đại lượng đo được; phải bằng metric khi observed |
| `observed_value` | number |  |  |  |
| `observed_sample_count` | integer (≥ 0) |  |  |  |
| `observed_coverage` | number (≥ 0) |  |  |  |
| `in_interval` | enum: true, false, unknown | có |  | observed_value nằm trong [interval_low, interval_high]; unknown khi không có nhãn hoặc khoảng |
| `error_value` | number |  |  | observed_value trừ est_value |
| `label_rule_version` | string | có |  |  |
| `as_of_ts` | date-time | có |  |  |

#### `metric_config`

Metadata của một metric. **Một dòng:** Một metric × phiên bản định nghĩa · **Nguồn ghi:** contracts/kpi.yaml · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `metric_name` | string | có | PK |  |
| `metric_definition_version` | string | có | PK |  |
| `detector_version` | string |  |  |  |
| `mode` | enum: active, reporting_only | có |  |  |
| `applies_to_sources` | mảng string |  |  |  |
| `applies_to_platforms` | mảng enum: ios, android, web, desktop, unknown |  |  |  |
| `unit` | string |  |  |  |
| `denominator` | string |  |  |  |
| `min_coverage_ref` | string |  |  | Tham số có version; bản này không chọn giá trị |
| `scope` | enum: outcome_all_calls, telemetry_observed | có |  |  |
| `cohort_rule` | string | có |  | Quy tắc chọn call_session |
| `numerator_rule` | string | có |  | Công thức và cách xử lý unknown |
| `denominator_rule` | string | có |  | Outcome dùng toàn cohort; telemetry dùng eligible observation count |
| `missingness_rule` | string | có |  | Không thay null hoặc unknown bằng false |
| `coverage_rule` | string | có |  | Công thức coverage và cách xử lý mẫu số bằng 0 |
| `source_tables` | mảng string | có |  |  |
| `stratification_rule` | string | có |  | Cách tách P2P |
| `compare_guardrail` | string | có |  | Điều kiện so sánh khi coverage của hai nhóm khác nhau |

### 2.4. Giả lập

#### `sim_decision_oracle`

Đáp án tối ưu của simulator cho một quyết định, chỉ dùng để đánh giá. **Một dòng:** Một decision_id × metric · **Nguồn ghi:** simulator · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có |  |  |
| `decision_id` | uuid | có | PK |  |
| `metric` | string | có | PK | Đại lượng truth, ví dụ truth_rtt_ms, truth_loss_pct, truth_jitter_ms hoặc truth_success |
| `unit` | string | có |  |  |
| `lower_is_better` | boolean | có |  |  |
| `truth_version` | string | có |  |  |
| `truth_cutoff_ts` | date-time | có |  |  |
| `eligible_pair_count` | integer (≥ 0) | có |  | Số cặp (TURN, transport) hai phía còn available theo truth tại thời điểm quyết định |
| `oracle_turn_caller` | string |  |  |  |
| `oracle_transport_caller` | enum: udp, tcp, tls |  |  |  |
| `oracle_turn_callee` | string |  |  |  |
| `oracle_transport_callee` | enum: udp, tcp, tls |  |  |  |
| `oracle_value` | number |  |  | Null khi không có cặp nào available |
| `oracle_in_lists` | enum: true, false, unknown | có |  | Cặp tối ưu có thể tạo được từ hai danh sách đã trả (cả hai mục có mặt) |
| `oracle_in_topk` | enum: true, false, unknown | có |  | Cặp tối ưu thuộc top-k của policy; unknown khi static_config |
| `best_in_lists_value` | number |  |  | Giá trị truth tốt nhất trong các cặp tạo được từ hai danh sách |
| `list_regret` | number |  |  | best_in_lists_value trừ oracle_value theo hướng tốt hơn; ≥ 0 |
| `lead_value` | number |  |  | Giá trị truth của cặp dẫn đầu |
| `lead_regret` | number |  |  |  |
| `actual_value` | number |  |  | Giá trị truth của cặp ICE thực tế; null khi chưa xác định hoặc call thất bại |
| `actual_regret` | number |  |  |  |
| `actual_pair_matches_oracle` | enum: true, false, unknown | có |  |  |

#### `truth_leg_5m`

Truth của chặng, ẩn. **Một dòng:** Một ts_bucket × chặng × hướng × mạng · **Nguồn ghi:** simulator · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `ts_bucket` | date-time | có |  |  |
| `src_id` | string | có |  |  |
| `dst_id` | string | có |  |  |
| `direction` | enum: forward, reverse | có |  |  |
| `network_type` | enum: wifi, 4g, 5g, ethernet, unknown |  |  |  |
| `exo_one_way_ms` | number (≥ 0) | có |  |  |
| `load_one_way_ms` | number (≥ 0) | có |  |  |
| `true_loss_pct` | number (≥ 0, ≤ 100) | có |  |  |
| `true_jitter_ms` | number (≥ 0) | có |  |  |
| `available` | boolean | có |  |  |

#### `incident_truth`

Sự cố thật, ẩn. **Một dòng:** Một sự cố · **Nguồn ghi:** simulator · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `incident_id` | string | có | PK |  |
| `type` | string | có |  |  |
| `target_kind` | string | có |  |  |
| `target_id` | string | có |  |  |
| `start_ts` | date-time | có |  |  |
| `end_ts` | date-time | có |  |  |
| `severity` | string |  |  |  |
| `params` | object |  |  |  |

#### `dirt_log`

Dữ liệu bẩn đã tiêm, ẩn. **Một dòng:** Một event bị tiêm lỗi · **Nguồn ghi:** simulator · **Mức nguồn:** D

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `event_id` | uuid | có |  |  |
| `table` | string | có |  |  |
| `dirt_type` | string | có |  |  |
| `params` | object |  |  |  |

#### `run_manifest`

Hồ sơ một lần chạy. **Một dòng:** Một lần chạy · **Nguồn ghi:** simulator · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `sim_run_id` | string | có | PK |  |
| `run_kind` | enum: scripted, blind_benchmark, dev | có |  |  |
| `benchmark_id` | string |  |  |  |
| `replicate_seed` | integer |  |  |  |
| `simulator_version` | string | có |  |  |
| `git_commit` | string | có |  |  |
| `config_hash` | string | có |  |  |
| `contract_version` | string | có |  |  |
| `topology_version` | string | có |  |  |
| `network_profile_version` | string | có |  |  |
| `scenario_version` | string | có |  |  |
| `incident_schedule_version` | string |  |  |  |
| `incidents_sha256` | string |  |  |  |
| `root_seeds` | object | có |  |  |
| `policy_version` | string | có |  |  |
| `exploration_epsilon` | number (≥ 0, ≤ 1) |  |  |  |
| `connection_mode` | enum: post_answer, pre_connect | có |  |  |
| `ice_transport_policy` | enum: relay, all | có |  |  |
| `be_region` | string |  |  |  |
| `initial_snapshot_hash` | string | có |  |  |
| `burn_in_days` | integer (≥ 0) | có |  |  |
| `environment_dir` | string | có |  |  |
| `started_at` | date-time | có |  |  |
| `completed_at` | date-time |  |  |  |
| `observation_profile` | enum: obs_base, obs_active, obs_infra | có |  | **Mới.** |
| `ice_model_version` | string |  |  | **Mới.** Chỉ để truy nguyên dữ liệu synthetic |
| `inventory_scope` | object |  |  | Issue #5. Khai báo country có TURN và country không có TURN trong thế giới giả lập, để dựng scenario VN-quốc tế không có TURN |

#### `benchmark_manifest`

Hồ sơ bộ seed. **Một dòng:** Một benchmark · **Nguồn ghi:** simulator · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `benchmark_id` | string | có | PK |  |
| `n_replicates_planned` | integer (≥ 0) | có |  |  |
| `mde_pp` | number (≥ 0) |  |  |  |
| `alpha` | number (≥ 0, ≤ 1) |  |  |  |
| `power` | number (≥ 0, ≤ 1) |  |  |  |
| `power_analysis_ref` | string |  |  |  |
| `kpi_yaml_hash` | string |  |  |  |
| `decision_rule_version` | string |  |  |  |

#### `sim_call_tag`

Thẻ kịch bản của cuộc gọi giả lập. **Một dòng:** Một cuộc gọi trong một lần chạy · **Nguồn ghi:** simulator · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `sim_run_id` | string | có | PK |  |
| `call_id` | uuid | có | PK |  |
| `scenario_tag` | string | có |  |  |

### 2.5. API và vận hành Selector

#### `select_request`

SelectRequest. **Một dòng:** Một request tới POST /v1/turn/select · **Nguồn ghi:** signaling · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `call_id` | uuid | có |  |  |
| `phase` | enum: initial, restart | có |  |  |
| `request_ts` | date-time | có |  |  |
| `caller_ctx` | object ctx | có |  |  |
| `callee_ctx` | object ctx |  |  | Null khi gọi mù |
| `info_level` | enum: full, caller_only, country_only, none | có |  |  |
| `requested_max_list_size_caller` | integer (≥ 0) | có |  | **Mới.** Thay k |
| `requested_max_list_size_callee` | integer (≥ 0) | có |  | **Mới.** Thay k |
| `exploration_epsilon` | number (≥ 0, ≤ 1) |  |  |  |
| `exclude_turns` | mảng object excluded_turn |  |  |  |
| `parent_decision_id` | uuid |  |  | **Mới.** |
| `requested_policy_version` | string |  |  | Chọn phiên bản thuật toán |
| `idempotency_key` | string |  |  |  |

- **Cột hoãn:** `locked_side, locked_list_hash`: Selector biết Callee ngay từ đầu; mở lại nếu cần giữ TURN bên kia khi đổi mạng
- **Cột bỏ:** `k`: requested_max_list_size_caller, requested_max_list_size_callee

#### `select_response`

SelectResponse. **Một dòng:** Một response của Selector · **Nguồn ghi:** selector · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `decision_id` | uuid | có |  |  |
| `policy_version` | string | có |  |  |
| `caller` | object side_list | có |  |  |
| `callee` | object side_list |  |  |  |
| `lead_pair` | object list_lead_pair |  |  | **Mới.** |
| `topk_pair_count` | integer (≥ 0) |  |  | **Mới.** |
| `topk_capped` | boolean |  |  | **Mới.** |
| `selection_method` | enum: deterministic, greedy, thompson, ucb, epsilon, static | có |  | **Mới.** |
| `action_propensity` | number (≥ 0, ≤ 1) |  |  | **Mới.** |
| `propensity_method` | enum: exact, monte_carlo, not_estimated | có |  | **Mới.** |
| `confidence` | number (≥ 0, ≤ 1) |  |  |  |
| `confidence_level` | enum: high, medium, low | có |  |  |
| `fallback_reason` | string |  |  |  |
| `fallback_type` | enum: data_backoff, health_missing, selector_error, insufficient_candidates |  |  |  |
| `feature_snapshot_id` | string |  |  |  |
| `health_snapshot_id` | string |  |  |  |
| `expires_at` | date-time |  |  |  |
| `pairs` | mảng object pair_prediction |  |  | **Mới.** Để BE ghi selector_decision_pair |
| `propensity_n_samples` | integer (≥ 0) |  |  | **Mới.** |
| `eligible_action_set` | object eligible_action_set |  |  | **Mới.** |
| `confidence_evidence` | object confidence_evidence |  |  | **Mới.** |

- **Cột bỏ:** `chosen_rank`: lead_pair, roles

#### `service_health_1m`

Sức khỏe service theo phút. **Một dòng:** Một minute_ts × service × instance · **Nguồn ghi:** selector · **Mức nguồn:** A

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `minute_ts` | date-time | có | PK |  |
| `service` | string | có | PK |  |
| `instance` | string | có | PK |  |
| `req_count` | integer (≥ 0) | có |  |  |
| `error_count` | integer (≥ 0) | có |  |  |
| `timeout_count` | integer (≥ 0) | có |  |  |
| `p50_ms` | number (≥ 0) |  |  |  |
| `p95_ms` | number (≥ 0) |  |  |  |
| `p99_ms` | number (≥ 0) |  |  |  |
| `static_fallback_count` | integer (≥ 0) | có |  |  |
| `algo_fallback_count` | integer (≥ 0) | có |  |  |
| `active_snapshot_id` | string |  |  |  |
| `feature_snapshot_age_s` | number (≥ 0) |  |  |  |

- **Cột hoãn:** `shadow_req_count`: Tạm thời chưa chạy bóng

### 2.6. Object dùng trong file đi kèm

#### `derived_meta`

Cột chung của bảng do pipeline dựng. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `contract_version` | string | có |  |  |
| `data_source` | enum: synthetic, lab_zenodo, lab_controlled, public_reference, production | có |  |  |
| `sim_run_id` | string |  |  |  |
| `pipeline_run_id` | string | có |  |  |
| `dt` | date | có |  |  |

#### `side_list`

Danh sách cho một bên trong SelectResponse. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `entries` | mảng object list_entry | có |  |  |
| `filtered_out` | mảng object filtered_turn | có |  |  |
| `returned_list_size` | integer (≥ 0) | có |  |  |
| `is_exploration` | boolean | có |  |  |

#### `list_lead_pair`

Cặp dẫn đầu. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `turn_caller` | string | có |  |  |
| `turn_callee` | string | có |  |  |
| `transport_caller` | enum: udp, tcp, tls |  |  |  |
| `transport_callee` | enum: udp, tcp, tls |  |  |  |

#### `pair_prediction`

Một cặp được cân nhắc trong SelectResponse; BE chép vào selector_decision_pair. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `turn_caller` | string | có |  |  |
| `turn_callee` | string | có |  |  |
| `transport_caller` | enum: udp, tcp, tls | có |  |  |
| `transport_callee` | enum: udp, tcp, tls | có |  |  |
| `metric` | string | có |  |  |
| `unit` | string | có |  |  |
| `est_value` | number |  |  |  |
| `interval_low` | number |  |  |  |
| `interval_high` | number |  |  |  |
| `interval_kind` | enum: mean_ci, prediction, other |  |  |  |
| `interval_level` | number (≥ 0, ≤ 1) |  |  |  |
| `in_topk` | boolean | có |  |  |
| `is_lead` | boolean | có |  |  |
| `estimate_source` | string |  |  |  |
| `estimator_version` | string |  |  |  |
| `input_snapshot_id` | string |  |  | Cutoff hoặc snapshot nguồn |
| `gate_status` | enum: passed, failed, not_evaluated, not_applicable | có |  |  |
| `gate_reason` | string |  |  |  |
| `gate_rule_version` | string |  |  | Cần nếu policy_version không tham chiếu bất biến tới quy tắc |

#### `excluded_turn`

TURN client yêu cầu loại. 

| Cột | Kiểu | Bắt buộc | Khóa | Ghi chú |
|---|---|---|---|---|
| `turn_id` | string | có |  |  |
| `reason` | string |  |  |  |
