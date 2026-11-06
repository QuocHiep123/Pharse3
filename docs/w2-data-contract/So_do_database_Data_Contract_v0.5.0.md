# Sơ đồ database của Data Contract v0.5.0

Sơ đồ sinh tự động từ [data_contract_v0.5.0.schema.yaml](data_contract_v0.5.0.schema.yaml) và [dac_ta_sau_thu_thap_v0.5.0.schema.yaml](dac_ta_sau_thu_thap_v0.5.0.schema.yaml). Giải thích từng bảng, từng cột và giá trị enum nằm ở [Bang_du_lieu_Data_Contract_v0.5.0.md](Bang_du_lieu_Data_Contract_v0.5.0.md). Khi các file khác nhau thì tin YAML.

## Mục lục

1. [Cách đọc](#1-cách-đọc)
2. [Danh sách bảng](#2-danh-sách-bảng)
3. [Contract thu thập](#3-contract-thu-thập)
4. [Các lớp sau thu thập](#4-các-lớp-sau-thu-thập)

---

## 1. Cách đọc

- Mỗi khung là một bảng, mỗi dòng trong khung là `kiểu tên_cột`. Kiểu được quy về dạng SQL: `varchar`, `int`, `float`, `bool`, `datetime`, `date`, `uuid`, `enum`, `json`.
- `PK` là khóa chính, `FK` là khóa ngoại. Cột ghi `"null"` là được null; các cột còn lại bắt buộc.
- `enum` là danh sách giá trị cố định; `json` là object hoặc mảng, ví dụ ngữ cảnh `ctx` hay danh sách `entries`. Giá trị cụ thể xem ở file giải thích.
- Đường nối là khóa ngoại khai báo trong YAML, nhãn là tên cột dùng để nối. Quan hệ do pipeline tra, như IP sang máy TURN, được nêu riêng dưới sơ đồ.
- Sơ đồ dùng mermaid. GitHub hiển thị trực tiếp; trong VS Code cần extension hỗ trợ mermaid cho Markdown Preview.

**Cột chung của mọi bảng event**, không vẽ lại trong từng khung:

```mermaid
erDiagram
    event_envelope {
        uuid event_id
        varchar contract_version
        enum data_source
        enum producer
        datetime event_ts
        datetime ingest_ts
        varchar sim_run_id "null"
        date dt
    }
    derived_meta {
        varchar contract_version
        enum data_source
        varchar sim_run_id "null"
        varchar pipeline_run_id
        date dt
    }
```

Bảng do pipeline dựng dùng `derived_meta` thay cho `event_envelope`.

---

## 2. Danh sách bảng

| Lớp | Bảng | Một dòng | Khóa chính | Trạng thái |
|---|---|---|---|---|
| Contract, Tham chiếu | [`dim_turn`](Bang_du_lieu_Data_Contract_v0.5.0.md#dim_turn) | Một phiên bản hiệu lực của một turn_id | turn_id, valid_from | Dùng |
| Contract, Tham chiếu | [`dim_turn_endpoint`](Bang_du_lieu_Data_Contract_v0.5.0.md#dim_turn_endpoint) | Một quan hệ IP, turn_id, vai trò trong một khoảng hiệu lực | mapping_id | Dùng |
| Contract, Tham chiếu | [`dim_asn`](Bang_du_lieu_Data_Contract_v0.5.0.md#dim_asn) | Một ASN | asn | Dùng |
| Contract, Tham chiếu | [`dim_country_area`](Bang_du_lieu_Data_Contract_v0.5.0.md#dim_country_area) | Một quốc gia trong một phiên bản bảng | country, area_map_version | Dùng |
| Contract, Call logs | [`call_session`](Bang_du_lieu_Data_Contract_v0.5.0.md#call_session) | Một cuộc gọi | call_id | Dùng |
| Contract, Call logs | [`client_applied_config`](Bang_du_lieu_Data_Contract_v0.5.0.md#client_applied_config) | Một lần áp dụng cấu hình trên một PC và generation | applied_config_id | Dùng |
| Contract, getStats và ICE | [`ice_event`](Bang_du_lieu_Data_Contract_v0.5.0.md#ice_event) | Một sự kiện quan sát trên một endpoint | event_id | Dùng |
| Contract, Call logs | [`endpoint_network_context`](Bang_du_lieu_Data_Contract_v0.5.0.md#endpoint_network_context) | Một call_id × side × device_id × network_epoch × context_version | call_id, side, device_id, network_epoch, context_version | Dùng (#6) |
| Contract, getStats và ICE | [`call_stats_epoch`](Bang_du_lieu_Data_Contract_v0.5.0.md#call_stats_epoch) | Một call_id × endpoint_side × device_id × media_kind × network_epoch × sequence_no | call_id, endpoint_side, device_id, media_kind, network_epoch, sequence_no | Dùng |
| Contract, getStats và ICE | [`call_stats_5s`](Bang_du_lieu_Data_Contract_v0.5.0.md#call_stats_5s) | Một call_id × endpoint_side × device_id × media_kind × window_idx | call_id, endpoint_side, device_id, media_kind, window_idx | Dùng |
| Contract, TURN metrics | [`turn_health_1m`](Bang_du_lieu_Data_Contract_v0.5.0.md#turn_health_1m) | Một turn_id × minute_ts | turn_id, minute_ts | Dùng |
| Contract, TURN metrics | [`turn_allocation`](Bang_du_lieu_Data_Contract_v0.5.0.md#turn_allocation) | Một session allocation trong log của một TURN, với kết quả cuối | turn_id, server_session_id | Dùng |
| Contract, Probe | [`turn_probe`](Bang_du_lieu_Data_Contract_v0.5.0.md#turn_probe) | Một cặp TURN có hướng × cửa sổ đo × phương pháp × giao thức | src_turn_id, dst_turn_id, window_start_ts, method_version, protocol | Dùng |
| Contract, Decision Log | [`selector_decision`](Bang_du_lieu_Data_Contract_v0.5.0.md#selector_decision) | Một decision_id × side × device_id | decision_id, side, device_id | Dùng |
| Contract, Decision Log | [`selector_decision_request`](Bang_du_lieu_Data_Contract_v0.5.0.md#selector_decision_request) | Một decision_id (header cấp call) | decision_id | Dùng |
| Contract, Decision Log | [`selector_decision_pair`](Bang_du_lieu_Data_Contract_v0.5.0.md#selector_decision_pair) | Một decision_id × cặp × metric | decision_id, turn_caller, turn_callee, transport_caller, transport_callee, metric | Dùng |
| Contract, Đầu vào Outcome Log | [`call_outcome`](Bang_du_lieu_Data_Contract_v0.5.0.md#call_outcome) | Một cuộc gọi | call_id | Dùng |
| Contract, Đầu vào Outcome Log | [`client_call_report`](Bang_du_lieu_Data_Contract_v0.5.0.md#client_call_report) | Một call_id × side × device_id | call_id, side, device_id | Dùng |
| Contract, Hoãn | [`candidate_observation`](Bang_du_lieu_Data_Contract_v0.5.0.md#candidate_observation) | Một candidate quan sát được, hoặc một dòng not_observed cho một mục cấu hình trong một chu kỳ thu | observation_id | Hoãn |
| Contract, Hoãn | [`ice_candidate_pair`](Bang_du_lieu_Data_Contract_v0.5.0.md#ice_candidate_pair) | Một cặp trong một attempt | call_id, attempt_seq, pair_id | Hoãn |
| Pipeline làm sạch | [`outcome_log`](Bang_du_lieu_Data_Contract_v0.5.0.md#outcome_log) | Một phiên bản outcome của một cuộc gọi; view hiện hành có một dòng | call_id, outcome_version | Dùng |
| Pipeline làm sạch | [`ice_attempt`](Bang_du_lieu_Data_Contract_v0.5.0.md#ice_attempt) | Một call_id × attempt_seq | call_id, attempt_seq | Dùng |
| Pipeline làm sạch | [`ice_attempt_endpoint`](Bang_du_lieu_Data_Contract_v0.5.0.md#ice_attempt_endpoint) | Một call_id × attempt_seq × side × device_id | call_id, attempt_seq, side, device_id | Dùng |
| Pipeline làm sạch | [`telemetry_coverage`](Bang_du_lieu_Data_Contract_v0.5.0.md#telemetry_coverage) | Một nguồn × phạm vi × khoảng thời gian |  | Dùng |
| Pipeline làm sạch | [`dq_results`](Bang_du_lieu_Data_Contract_v0.5.0.md#dq_results) | Một lần chạy × check × bảng | pipeline_run_id, check_id, table | Dùng |
| Pipeline làm sạch | [`clean_clock_columns`](Bang_du_lieu_Data_Contract_v0.5.0.md#clean_clock_columns) | Đi kèm dòng event |  | Dùng |
| Pipeline làm sạch | [`clean_stats_columns`](Bang_du_lieu_Data_Contract_v0.5.0.md#clean_stats_columns) | Đi kèm dòng call_stats_5s hoặc call_stats_epoch |  | Dùng |
| Pipeline làm sạch | [`clean_ice_event_columns`](Bang_du_lieu_Data_Contract_v0.5.0.md#clean_ice_event_columns) | Đi kèm dòng ice_event |  | Dùng |
| Pipeline làm sạch | [`clean_allocation_columns`](Bang_du_lieu_Data_Contract_v0.5.0.md#clean_allocation_columns) | Đi kèm dòng event |  | Dùng |
| Pipeline làm sạch | [`clean_leg_columns`](Bang_du_lieu_Data_Contract_v0.5.0.md#clean_leg_columns) | Đi kèm dòng event |  | Dùng |
| Feature Engineering | [`feature_snapshot`](Bang_du_lieu_Data_Contract_v0.5.0.md#feature_snapshot) | Một snapshot | snapshot_id | Dùng |
| Feature Engineering | [`feat_leg_stats`](Bang_du_lieu_Data_Contract_v0.5.0.md#feat_leg_stats) | Một snapshot × segment × TURN × hướng × metric × giờ | snapshot_id, segment_level, segment_key, turn_id, direction, metric, hour_bucket | Dùng |
| Feature Engineering | [`feat_turn_turn`](Bang_du_lieu_Data_Contract_v0.5.0.md#feat_turn_turn) | Một snapshot × cặp TURN có hướng × metric × giờ | snapshot_id, src_turn, dst_turn, metric, hour_bucket | Dùng |
| Feature Engineering | [`feat_turn_health`](Bang_du_lieu_Data_Contract_v0.5.0.md#feat_turn_health) | Một snapshot × TURN | snapshot_id, turn_id | Dùng |
| Feature Engineering | [`feat_path_history`](Bang_du_lieu_Data_Contract_v0.5.0.md#feat_path_history) | Một snapshot × hai segment × cặp TURN | snapshot_id, caller_segment_key, callee_segment_key, turn_caller, turn_callee | Dùng |
| Feature Engineering | [`health_snapshot`](Bang_du_lieu_Data_Contract_v0.5.0.md#health_snapshot) | Một health_snapshot_id × TURN | health_snapshot_id, turn_id | Dùng |
| Feature Engineering | [`dim_user`](Bang_du_lieu_Data_Contract_v0.5.0.md#dim_user) | Một user_hash | user_hash | Dùng |
| Feature Engineering | [`feat_callee_prior`](Bang_du_lieu_Data_Contract_v0.5.0.md#feat_callee_prior) | Một snapshot × segment Caller × nơi Callee | snapshot_id, caller_segment_key, callee_country, callee_vn_region | Hoãn |
| Feature Engineering | [`feat_turn_alloc_latency`](Bang_du_lieu_Data_Contract_v0.5.0.md#feat_turn_alloc_latency) | Một snapshot × segment × TURN × transport | snapshot_id, segment_key, turn_id, transport | Hoãn |
| Feature Engineering | [`feat_estimated_user_turn_rtt`](Bang_du_lieu_Data_Contract_v0.5.0.md#feat_estimated_user_turn_rtt) | Một snapshot × segment × TURN × transport × đại lượng | snapshot_id, segment_level, segment_key, turn_id, client_turn_transport, estimand | Hoãn |
| Labeled Data và Evaluation | [`fact_call`](Bang_du_lieu_Data_Contract_v0.5.0.md#fact_call) | Một call_id trong cohort | call_id | Đủ cột (#8); bản hiện hành theo as_of_ts, fact_version |
| Labeled Data và Evaluation | [`fact_call_endpoint`](Bang_du_lieu_Data_Contract_v0.5.0.md#fact_call_endpoint) | Một call_id × side × device_id | call_id, side, device_id | Dùng (#8) |
| Labeled Data và Evaluation | [`fact_pair_evaluation`](Bang_du_lieu_Data_Contract_v0.5.0.md#fact_pair_evaluation) | Một decision_id × metric × cặp, bản hiện hành | decision_id, metric, turn_caller, transport_caller, turn_callee, transport_callee | Dùng (#8) |
| Labeled Data và Evaluation | [`metric_config`](Bang_du_lieu_Data_Contract_v0.5.0.md#metric_config) | Một metric × phiên bản định nghĩa | metric_name, metric_definition_version | Dùng |
| Giả lập | [`sim_decision_oracle`](Bang_du_lieu_Data_Contract_v0.5.0.md#sim_decision_oracle) | Một decision_id × metric (đáp án tối ưu theo truth, chỉ synthetic) | decision_id, metric | Dùng (I34) |
| Giả lập | [`truth_leg_5m`](Bang_du_lieu_Data_Contract_v0.5.0.md#truth_leg_5m) | Một ts_bucket × chặng × hướng × mạng |  | Dùng |
| Giả lập | [`incident_truth`](Bang_du_lieu_Data_Contract_v0.5.0.md#incident_truth) | Một sự cố | incident_id | Dùng |
| Giả lập | [`dirt_log`](Bang_du_lieu_Data_Contract_v0.5.0.md#dirt_log) | Một event bị tiêm lỗi |  | Dùng |
| Giả lập | [`run_manifest`](Bang_du_lieu_Data_Contract_v0.5.0.md#run_manifest) | Một lần chạy | sim_run_id | Dùng |
| Giả lập | [`benchmark_manifest`](Bang_du_lieu_Data_Contract_v0.5.0.md#benchmark_manifest) | Một benchmark | benchmark_id | Dùng |
| Giả lập | [`sim_call_tag`](Bang_du_lieu_Data_Contract_v0.5.0.md#sim_call_tag) | Một cuộc gọi trong một lần chạy | sim_run_id, call_id | Dùng |
| API và vận hành Selector | [`select_request`](Bang_du_lieu_Data_Contract_v0.5.0.md#select_request) | Một request tới POST /v1/turn/select |  | Dùng |
| API và vận hành Selector | [`select_response`](Bang_du_lieu_Data_Contract_v0.5.0.md#select_response) | Một response của Selector |  | Dùng |
| API và vận hành Selector | [`service_health_1m`](Bang_du_lieu_Data_Contract_v0.5.0.md#service_health_1m) | Một minute_ts × service × instance | minute_ts, service, instance | Dùng |

---

## 3. Contract thu thập

### 3.1. Cuộc gọi, Decision Log và Outcome

```mermaid
erDiagram
    call_session ||--o{ selector_decision : "call_id"
    selector_decision ||--o{ selector_decision_pair : "decision_id"
    call_session ||--o{ client_applied_config : "call_id"
    selector_decision ||--o{ client_applied_config : "applied_decision_id"
    call_session ||--|| call_outcome : "call_id"
    call_session ||--o{ client_call_report : "call_id"
    call_session {
        uuid call_id PK
        varchar caller_hash
        varchar callee_hash
        datetime initiated_ts
        enum media_kind
        enum call_type
        varchar caller_device_id
        enum connection_mode
        enum ice_transport_policy "null"
        varchar be_region "null"
        varchar be_instance "null"
    }
    selector_decision {
        uuid decision_id PK
        uuid parent_decision_id FK "null"
        uuid call_id FK
        enum side PK
        enum phase
        varchar device_id PK
        datetime request_ts
        datetime response_ts "null"
        float api_latency_ms "null"
        varchar policy_version
        enum decision_source
        enum info_level
        json self_ctx
        json peer_ctx
        enum selection_method
        int requested_max_list_size
        int returned_list_size
        json entries
        json filtered_out
        int topk_pair_count "null"
        bool topk_capped "null"
        bool is_exploration
        float exploration_epsilon "null"
        float action_propensity "null"
        enum propensity_method
        int propensity_n_samples "null"
        json eligible_action_set "null"
        float confidence "null"
        enum confidence_level
        json confidence_evidence "null"
        varchar fallback_reason "null"
        enum fallback_type "null"
        varchar feature_snapshot_id "null"
        varchar health_snapshot_id "null"
        varchar error_code "null"
    }
    selector_decision_pair {
        uuid decision_id PK,FK
        uuid call_id
        varchar turn_caller PK
        varchar turn_callee PK
        enum transport_caller PK
        enum transport_callee PK
        varchar metric PK
        varchar unit
        float est_value "null"
        float interval_low "null"
        float interval_high "null"
        enum interval_kind "null"
        float interval_level "null"
        bool in_topk
        bool is_lead
        varchar estimate_source "null"
        varchar estimator_version "null"
        varchar input_snapshot_id "null"
        enum gate_status
        varchar gate_reason "null"
        varchar gate_rule_version "null"
    }
    client_applied_config {
        uuid applied_config_id PK
        uuid call_id FK
        uuid applied_decision_id FK "null"
        varchar list_hash
        datetime applied_ts
        enum side
        varchar endpoint_id
        varchar device_id
        varchar pc_id
        int ice_generation
        enum applied_ice_transport_policy "null"
        enum config_source
        bool is_fallback_config "null"
        json applied_entries "null"
    }
    call_outcome {
        uuid call_id PK,FK
        datetime ring_ts "null"
        datetime answer_received_at_be "null"
        bool answered "null"
        varchar answered_device_id "null"
        datetime end_ts "null"
        enum end_signal
        enum end_signal_side "null"
        json caller_ctx_final "null"
        json callee_ctx_final "null"
        bool converted_to_group "null"
        datetime converted_ts "null"
    }
    client_call_report {
        uuid call_id PK,FK
        enum side PK
        varchar device_id PK
        datetime answer_clicked_at_client "null"
        datetime answer_observed_at_peer "null"
        varchar client_end_reason "null"
        enum stats_status "null"
        float stats_sampling_prob "null"
        varchar stats_sampling_reason "null"
        varchar sampling_rule_version "null"
    }
```

`ctx`, `entries`, `filtered_out` là `json`; cấu trúc của chúng nằm ở mục 1.9 của file giải thích.

### 3.1b. Bảng bổ sung sau phản hồi #5–#8

```mermaid
erDiagram
    call_session ||--o{ endpoint_network_context : "call_id, side, device_id, network_epoch"
    call_session ||--|| selector_decision_request : "call_id"
    selector_decision_request ||--|{ selector_decision : "decision_id"
    call_session ||--|| fact_call : "call_id"
    fact_call ||--o{ fact_call_endpoint : "call_id"
    endpoint_network_context {
        uuid call_id PK,FK
        enum side PK
        varchar device_id PK
        int network_epoch PK
        int context_version PK
        datetime observed_ts
        varchar country "null"
        varchar isp "null"
        enum network_type "null"
    }
    fact_call_endpoint {
        uuid call_id PK,FK
        enum side PK
        varchar device_id PK
        enum turn_availability_status "null"
        enum used_fallback_turn "tristate"
        enum turn_identity_status
    }
```

Chi tiết cột nằm ở [Bang_du_lieu](Bang_du_lieu_Data_Contract_v0.5.0.md). `turn_availability_status` và `used_fallback_turn` theo issue #5; `inventory_scope` nằm ở `run_manifest`.

### 3.2. getStats và sự kiện ICE

```mermaid
erDiagram
    call_session ||--o{ ice_event : "call_id"
    call_session ||--o{ call_stats_epoch : "call_id"
    call_session ||--o{ call_stats_5s : "call_id"
    ice_event {
        uuid call_id FK
        int attempt_seq "null"
        varchar pc_id
        int ice_generation
        enum side
        varchar device_id
        enum event_type
        float event_mono_ms "null"
        varchar clock_session_id "null"
        enum ice_state "null"
        enum dtls_state "null"
        enum local_candidate_type "null"
        enum remote_candidate_type "null"
        enum client_turn_transport "null"
        enum candidate_protocol "null"
        varchar relayed_ip_local "null"
        varchar relayed_ip_remote "null"
        int selected_pair_changes "null"
        enum ice_role "null"
        enum trigger "null"
        varchar reason "null"
        enum source
        float poll_interval_ms "null"
        varchar local_turn_url "null"
        float prev_pair_rtt_total_s "null"
        int prev_pair_responses "null"
        float audio_rtcp_rtt_total_s "null"
        int audio_rtcp_rtt_measurements "null"
        int audio_packets_received_total "null"
        int audio_packets_lost_total "null"
        float audio_jitter_sum_ms "null"
        int audio_jitter_samples "null"
        varchar audio_stats_stream_ref "null"
    }
    call_stats_epoch {
        uuid call_id PK,FK
        enum endpoint_side PK
        varchar device_id PK
        enum media_kind PK
        int network_epoch PK
        int sequence_no PK
        datetime epoch_start_ts
        datetime epoch_end_ts
        bool is_checkpoint "null"
        enum network_type "null"
        float audio_active_duration_s "null"
        datetime first_media_sent_ts "null"
        datetime first_media_received_ts "null"
        enum first_media_definition "null"
        varchar first_media_observation_status "null"
        float media_rtcp_rtt_total_s "null"
        int media_rtcp_rtt_measurements "null"
        float ice_stun_rtt_total_s "null"
        int ice_stun_responses "null"
        int packets_received_total "null"
        int packets_lost_total "null"
        float jitter_estimate_sum_ms "null"
        int jitter_estimate_samples "null"
        varchar stats_stream_ref "null"
        enum derivation "null"
        int window_s "null"
        json media_rtcp_rtt_hist "null"
        json loss_hist "null"
        json jitter_estimate_hist "null"
        int rtt_windows_assessable "null"
        int loss_windows_assessable "null"
        int jitter_windows_assessable "null"
        int valid_rtt_samples "null"
        int valid_jitter_samples "null"
        float media_rtcp_rtt_p50 "null"
        float media_rtcp_rtt_p95 "null"
        float ice_stun_rtt_p50 "null"
        float ice_stun_rtt_p95 "null"
        float jitter_estimate_p95 "null"
        float measurement_coverage "null"
        varchar quality_rule_version "null"
    }
    call_stats_5s {
        uuid call_id PK,FK
        enum endpoint_side PK
        varchar device_id PK
        enum media_kind PK
        int window_idx PK
        int window_s
        datetime window_start_ts
        int network_epoch
        enum network_type "null"
        float media_rtcp_rtt_ms "null"
        float ice_stun_rtt_ms "null"
        float jitter_estimate_ms "null"
        int packets_lost "null"
        float audio_active_s "null"
        datetime first_media_sent_ts "null"
        datetime first_media_received_ts "null"
        float bitrate_send_kbps "null"
        float bitrate_recv_kbps "null"
        enum conn_state "null"
        int rtt_measurements_delta "null"
        int packets_received "null"
    }
```

`call_session` đã vẽ đủ cột ở mục 3.1.

### 3.3. Danh mục TURN, TURN metrics và probe

```mermaid
erDiagram
    dim_turn ||--o{ dim_turn_endpoint : "turn_id"
    dim_turn ||--o{ turn_health_1m : "turn_id"
    dim_turn ||--o{ turn_allocation : "turn_id"
    dim_turn ||--o{ turn_probe : "src_turn_id"
    dim_turn ||--o{ turn_probe : "dst_turn_id"
    dim_turn {
        varchar turn_id PK
        varchar hostname
        varchar country
        enum vn_region "null"
        varchar city
        float lat
        float lon
        varchar host_isp
        int host_asn
        int capacity_alloc "null"
        json transports
        enum status
        datetime valid_from PK
        datetime valid_to "null"
        json failure_domain "null"
    }
    dim_turn_endpoint {
        varchar mapping_id PK
        varchar ip
        varchar turn_id FK
        enum role
        varchar hostname "null"
        datetime valid_from
        datetime valid_to "null"
        varchar source "null"
    }
    turn_health_1m {
        varchar turn_id PK,FK
        datetime minute_ts PK
        int active_allocations "null"
        float cpu_pct "null"
        float bandwidth_mbps "null"
        int alloc_attempts "null"
        int alloc_failures "null"
        enum observation_state "null"
        json alloc_failures_by_code "null"
        datetime last_observed_ts "null"
        int sample_count "null"
        varchar source "null"
        float ingest_delay_ms "null"
        bool liveness_ok "null"
        enum liveness_method
    }
    turn_allocation {
        varchar turn_id PK,FK
        enum transport "null"
        varchar turn_server_ip "null"
        varchar relayed_ip "null"
        datetime response_ts "null"
        enum allocation_result
        enum error_code "null"
        enum source
        datetime released_ts "null"
        varchar server_session_id PK
        varchar credential_ref "null"
        varchar release_reason "null"
    }
    turn_probe {
        varchar src_turn_id PK,FK
        varchar dst_turn_id PK,FK
        varchar src_ip "null"
        varchar dst_ip "null"
        datetime window_start_ts PK
        datetime window_end_ts
        varchar method_version PK
        enum protocol PK
        int target_port "null"
        enum measurement_kind
        enum measurement_point
        float value_ms "null"
        float value_ms_p95 "null"
        float loss_pct "null"
        float jitter_ms "null"
        int n_samples
        float clock_sync_err_ms "null"
        enum observation_state "null"
        varchar missing_reason "null"
    }
    dim_asn {
        int asn PK
        varchar isp
        varchar country
        enum access_kind
    }
    dim_country_area {
        varchar country PK
        varchar area
        varchar area_map_version PK
    }
```

**Quan hệ do pipeline tra hoặc nối, không có khóa ngoại trực tiếp:**

- `ice_event.relayed_ip_local`, `relayed_ip_remote` và thời điểm → `dim_turn_endpoint.ip` → `dim_turn.turn_id`.
- `ice_event.local_turn_url` → mục trong `selector_decision.entries`.
- `turn_allocation.credential_ref` → `call_session.call_id`, nếu credential gắn theo cuộc gọi.
- `turn_probe.src_turn_id`, `dst_turn_id` → hai TURN của một cặp trong `selector_decision_pair`.

### 3.4. Bảng hoãn

```mermaid
erDiagram
    call_session ||--o{ candidate_observation : "call_id"
    client_applied_config ||--o{ candidate_observation : "applied_config_id"
    candidate_observation {
        uuid observation_id PK
        uuid call_id FK
        enum side
        varchar device_id
        varchar endpoint_id
        varchar pc_id
        varchar gathering_cycle_id
        int ice_generation
        uuid applied_config_id FK "null"
        varchar clock_session_id "null"
        float gathering_anchor_mono_ms "null"
        enum anchor_kind "null"
        float candidate_observed_mono_ms "null"
        varchar candidate_id "null"
        varchar server_config_id "null"
        varchar turn_url "null"
        enum client_turn_transport "null"
        enum candidate_protocol "null"
        enum candidate_type "null"
        varchar relayed_ip "null"
        enum observation_status
        varchar missing_reason "null"
        enum collection_method "null"
        int reported_error_code "null"
        float candidate_latency_ms "null"
    }
    ice_candidate_pair {
        uuid call_id PK
        int attempt_seq PK
        int ice_generation
        varchar pair_id PK
        varchar local_candidate_id
        varchar remote_candidate_id
        enum local_candidate_type
        enum remote_candidate_type
        varchar local_turn_id "null"
        varchar remote_turn_id "null"
        float pair_priority "null"
        enum check_state "null"
        int check_count "null"
        bool nominated "null"
        bool selected "null"
        float current_rtt_ms "null"
        enum telemetry_support "null"
    }
```

---

## 4. Các lớp sau thu thập

Đây là bản chuyển tiếp, giữ nội dung để không mất khi tách contract. Bảng `call_session`, `client_applied_config` ở các sơ đồ dưới thuộc contract, chỉ vẽ tên.

### 4.1. Pipeline làm sạch

```mermaid
erDiagram
    call_session ||--o{ outcome_log : "call_id"
    call_session ||--o{ ice_attempt : "call_id"
    client_applied_config ||--o{ ice_attempt : "caller_applied_config_id"
    client_applied_config ||--o{ ice_attempt : "callee_applied_config_id"
    ice_attempt ||--o{ ice_attempt_endpoint : "call_id, attempt_seq"
    outcome_log {
        uuid call_id PK,FK
        int outcome_version PK
        enum outcome_status
        enum outcome_provenance
        datetime finalized_ts "null"
        datetime ring_ts "null"
        datetime answer_clicked_at_client "null"
        datetime answer_received_at_be "null"
        datetime answer_observed_at_peer "null"
        bool answered "null"
        varchar answered_device_id "null"
        enum ice_connected
        enum dtls_connected
        enum media_connected
        varchar media_connected_rule_version "null"
        bool setup_failure_observed "null"
        datetime end_ts "null"
        float duration_s "null"
        enum end_reason
        bool dropped "null"
        json caller_ctx_final "null"
        json callee_ctx_final "null"
        enum pair_group "null"
        bool converted_to_group "null"
        datetime converted_ts "null"
        int n_ice_attempts "null"
        int n_network_changes "null"
        enum stats_status "null"
        float stats_sampling_prob "null"
        varchar stats_sampling_reason "null"
        varchar sampling_rule_version "null"
        varchar end_reason_rule_version "null"
    }
    ice_attempt {
        uuid call_id PK,FK
        int attempt_seq PK
        int ice_generation
        varchar caller_device_id
        varchar callee_device_id
        enum trigger
        uuid caller_decision_id "null"
        uuid callee_decision_id "null"
        uuid caller_applied_config_id FK "null"
        uuid callee_applied_config_id FK "null"
        int network_epoch
        enum state
        bool turn_used "null"
        enum caller_candidate_type "null"
        enum callee_candidate_type "null"
        enum path_type "null"
        varchar relay_turn_caller "null"
        varchar relay_turn_callee "null"
        varchar relayed_ip_caller "null"
        varchar relayed_ip_callee "null"
        uuid caller_allocation_id "null"
        uuid callee_allocation_id "null"
        int rank_caller "null"
        int rank_callee "null"
        enum client_turn_transport_caller "null"
        enum client_turn_transport_callee "null"
        enum candidate_protocol_caller "null"
        enum candidate_protocol_callee "null"
        datetime ice_connected_any_ts "null"
        varchar failure_reason "null"
    }
    ice_attempt_endpoint {
        uuid call_id PK,FK
        int attempt_seq PK,FK
        enum side PK
        varchar device_id PK
        varchar pc_id
        int ice_generation
        varchar clock_session_id "null"
        datetime start_ts "null"
        datetime ice_checking_observed_ts "null"
        datetime checks_start_ts "null"
        datetime ice_connected_ts "null"
        datetime dtls_connected_ts "null"
        datetime end_ts "null"
        float checking_to_connected_ms "null"
        enum state
        enum ice_role "null"
        enum local_candidate_type "null"
        enum remote_candidate_type "null"
        varchar local_turn_id "null"
        varchar relayed_ip_local "null"
        enum client_turn_transport "null"
        enum candidate_protocol "null"
        int selected_pair_changes "null"
    }
    telemetry_coverage {
        datetime window_start_ts
        datetime window_end_ts
        varchar source_table
        varchar field_group "null"
        enum observation_profile "null"
        enum capability
        varchar observation_method "null"
        enum platform "null"
        varchar app_version "null"
        varchar policy_version "null"
        uuid call_id "null"
        int n_expected "null"
        int n_observed "null"
        int n_not_measured "null"
        int n_stale "null"
        int n_lost "null"
        int n_ambiguous "null"
        int n_not_applicable "null"
    }
    dq_results {
        varchar pipeline_run_id PK
        date dt
        varchar check_id PK
        varchar table PK
        enum level
        enum status
        int n_checked
        int n_bad
        int n_not_evaluable
        json sample_event_ids "null"
        varchar correction_rule_version "null"
    }
    clean_clock_columns {
        datetime event_ts_corrected "null"
        float clock_skew_ms "null"
        varchar clock_correction_version "null"
        enum clock_quality_flag "null"
    }
    clean_stats_columns {
        int packets_expected "null"
        float loss_pct "null"
        bool rtt_sample_valid "null"
        bool jitter_sample_valid "null"
        varchar quality_rule_version "null"
        enum path_attribution_status "null"
        bool restart_gap "null"
    }
    clean_ice_event_columns {
        varchar local_turn_id "null"
        varchar remote_turn_id "null"
    }
    clean_allocation_columns {
        bool used_by_ice "null"
        enum match_method "null"
        uuid allocation_id "null"
        uuid call_id "null"
        uuid decision_id "null"
        enum side "null"
        varchar device_id "null"
    }
    clean_leg_columns {
        float one_way_ms_observed "null"
        float one_way_ms_estimated "null"
        bool symmetric_assumption "null"
    }
```

### 4.2. Feature Engineering

```mermaid
erDiagram

    feature_snapshot {
        varchar snapshot_id PK
        datetime cutoff_ts
        datetime published_ts
        varchar pipeline_version
        varchar content_hash
        varchar parent_snapshot_id "null"
    }
    feat_leg_stats {
        varchar snapshot_id PK
        enum segment_level PK
        varchar segment_key PK
        varchar turn_id PK
        enum direction PK
        enum metric PK
        varchar hour_bucket PK
        int n_raw
        float n_eff
        float p50 "null"
        float p95 "null"
        float loss_mean "null"
        float jitter_p95 "null"
        float p50_shrunk "null"
        json source_mix "null"
        datetime last_observed_ts "null"
        float sum_w "null"
        float sum_w2 "null"
        int n_calls_independent "null"
        int n_endpoints "null"
        int n_windows "null"
        float log_mean "null"
        float log_sd "null"
        float coverage "null"
        varchar value_kind
        varchar estimator_version "null"
    }
    feat_turn_turn {
        varchar snapshot_id PK
        varchar src_turn PK
        varchar dst_turn PK
        enum metric PK
        varchar hour_bucket PK
        int n_raw
        float n_eff
        float p50 "null"
        float p95 "null"
        float loss_mean "null"
        float jitter_p95 "null"
        json source_mix "null"
        datetime last_observed_ts "null"
        float sum_w "null"
        float sum_w2 "null"
        int n_calls_independent "null"
        int n_endpoints "null"
        int n_windows "null"
        float log_mean "null"
        float log_sd "null"
        float coverage "null"
        enum value_kind
        varchar estimator_version "null"
    }
    feat_turn_health {
        varchar snapshot_id PK
        varchar turn_id PK
        enum health_status
        float health_score "null"
        float utilization_p95_24h "null"
        float alloc_success_24h "null"
        float ci_low "null"
        float ci_high "null"
        int incidents_detected_7d "null"
        float stability_cv_24h "null"
    }
    feat_path_history {
        varchar snapshot_id PK
        varchar caller_segment_key PK
        varchar callee_segment_key PK
        enum segment_level "null"
        varchar turn_caller PK
        varchar turn_callee PK
        int n_calls
        float n_eff
        float poor_rate "null"
        float poor_rate_ci_low "null"
        float poor_rate_ci_high "null"
        float drop_rate "null"
        float setup_fail_rate "null"
        datetime last_observed_ts "null"
        float rtt_p50 "null"
        float rtt_p95 "null"
        float loss_mean "null"
        float jitter_p95 "null"
        float sum_w "null"
        float sum_w2 "null"
        int n_calls_independent "null"
        int n_endpoints "null"
        int n_windows "null"
        float log_mean "null"
        float log_sd "null"
        float coverage "null"
    }
    health_snapshot {
        varchar health_snapshot_id PK
        datetime cutoff_ts
        datetime published_ts
        varchar turn_id PK
        enum health_status
        float health_score "null"
        float utilization_pct_5m "null"
        float alloc_fail_rate_5m "null"
        datetime last_observed_ts "null"
        varchar source "null"
        varchar health_rule_version "null"
        enum observation_state "null"
        varchar assigned_by "null"
    }
    dim_user {
        varchar user_hash PK
        varchar home_country
        enum home_vn_region "null"
        varchar home_city
        varchar home_isp
        int home_asn "null"
        enum primary_network
        enum cohort
        datetime created_at
    }
    feat_callee_prior {
        varchar snapshot_id PK
        varchar caller_segment_key PK
        varchar callee_country PK
        enum callee_vn_region PK
        int n
        float share
    }
    feat_turn_alloc_latency {
        varchar snapshot_id PK
        varchar segment_key PK
        varchar turn_id PK
        enum transport PK
        int n
        int n_known "null"
        int n_unknown "null"
        float alloc_ms_p50 "null"
        float alloc_ms_p95 "null"
        float alloc_success_rate "null"
        float alloc_success_ci_low "null"
        float alloc_success_ci_high "null"
    }
    feat_estimated_user_turn_rtt {
        varchar snapshot_id PK
        enum segment_level PK
        varchar segment_key PK
        varchar turn_id PK
        enum client_turn_transport PK
        enum estimand PK
        varchar unit
        float estimated_user_turn_rtt_ms "null"
        float interval_low "null"
        float interval_high "null"
        enum interval_kind "null"
        float interval_level "null"
        varchar estimate_source
        varchar estimator_version
        varchar input_snapshot_id "null"
        enum validation_status
        enum gate_status
        varchar gate_reason "null"
        varchar gate_rule_version "null"
    }
```

### 4.3. Labeled Data và Evaluation

```mermaid
erDiagram
    call_session ||--o{ fact_call : "call_id"
    fact_call {
        uuid call_id PK,FK
        int local_hour_vn "null"
        enum pcr_group "null"
        enum poor_category "null"
        enum quality_assessment_status "null"
        enum outcome_status
        varchar policy_version "null"
        float action_propensity "null"
        uuid propensity_decision_id "null"
        int rank_used_caller "null"
        int rank_used_callee "null"
        enum lead_pair_matched "null"
        varchar actual_turn_id_caller "null"
        varchar actual_turn_id_callee "null"
        enum turn_identity_status_caller
        enum turn_identity_status_callee
        enum turn_identity_method_caller "null"
        enum turn_identity_method_callee "null"
        enum identity_check_caller
        enum identity_check_callee
        enum platform_caller "null"
        enum platform_callee "null"
        varchar app_version_caller "null"
        varchar app_version_callee "null"
        varchar device_class_caller "null"
        varchar device_class_callee "null"
    }
    metric_config {
        varchar metric_name PK
        varchar metric_definition_version PK
        varchar detector_version "null"
        enum mode
        json applies_to_sources "null"
        json applies_to_platforms "null"
        varchar unit "null"
        varchar denominator "null"
        varchar min_coverage_ref "null"
    }
```

### 4.4. Giả lập

```mermaid
erDiagram

    truth_leg_5m {
        datetime ts_bucket
        varchar src_id
        varchar dst_id
        enum direction
        enum network_type "null"
        float exo_one_way_ms
        float load_one_way_ms
        float true_loss_pct
        float true_jitter_ms
        bool available
    }
    incident_truth {
        varchar incident_id PK
        varchar type
        varchar target_kind
        varchar target_id
        datetime start_ts
        datetime end_ts
        varchar severity "null"
        json params "null"
    }
    dirt_log {
        uuid event_id
        varchar table
        varchar dirt_type
        json params "null"
    }
    run_manifest {
        varchar sim_run_id PK
        enum run_kind
        varchar benchmark_id "null"
        int replicate_seed "null"
        varchar simulator_version
        varchar git_commit
        varchar config_hash
        varchar contract_version
        varchar topology_version
        varchar network_profile_version
        varchar scenario_version
        varchar incident_schedule_version "null"
        varchar incidents_sha256 "null"
        json root_seeds
        varchar policy_version
        float exploration_epsilon "null"
        enum connection_mode
        enum ice_transport_policy
        varchar be_region "null"
        varchar initial_snapshot_hash
        int burn_in_days
        varchar environment_dir
        datetime started_at
        datetime completed_at "null"
        enum observation_profile
        varchar ice_model_version "null"
    }
    benchmark_manifest {
        varchar benchmark_id PK
        int n_replicates_planned
        float mde_pp "null"
        float alpha "null"
        float power "null"
        varchar power_analysis_ref "null"
        varchar kpi_yaml_hash "null"
        varchar decision_rule_version "null"
    }
    sim_call_tag {
        varchar sim_run_id PK
        uuid call_id PK
        varchar scenario_tag
    }
```

### 4.5. API và vận hành Selector

```mermaid
erDiagram

    select_request {
        uuid call_id
        enum phase
        datetime request_ts
        json caller_ctx
        json callee_ctx "null"
        enum info_level
        int requested_max_list_size_caller
        int requested_max_list_size_callee
        float exploration_epsilon "null"
        json exclude_turns "null"
        uuid parent_decision_id "null"
        varchar requested_policy_version "null"
        varchar idempotency_key "null"
    }
    select_response {
        uuid decision_id
        varchar policy_version
        json caller
        json callee "null"
        json lead_pair "null"
        int topk_pair_count "null"
        bool topk_capped "null"
        enum selection_method
        float action_propensity "null"
        enum propensity_method
        float confidence "null"
        enum confidence_level
        varchar fallback_reason "null"
        enum fallback_type "null"
        varchar feature_snapshot_id "null"
        varchar health_snapshot_id "null"
        datetime expires_at "null"
        json pairs "null"
        int propensity_n_samples "null"
        json eligible_action_set "null"
        json confidence_evidence "null"
    }
    service_health_1m {
        datetime minute_ts PK
        varchar service PK
        varchar instance PK
        int req_count
        int error_count
        int timeout_count
        float p50_ms "null"
        float p95_ms "null"
        float p99_ms "null"
        int static_fallback_count
        int algo_fallback_count
        varchar active_snapshot_id "null"
        float feature_snapshot_age_s "null"
    }
```
