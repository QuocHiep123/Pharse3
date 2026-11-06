# KPI MVP cho Data Contract v0.5.0

Tài liệu này chốt **định nghĩa phân tích cho simulator** theo issues [#7](https://github.com/QuocHiep123/Pharse3/issues/7) và [#8](https://github.com/QuocHiep123/Pharse3/issues/8). Khả năng thu thập production vẫn phụ thuộc xác nhận của BE, WebRTC core và mentor. Các field cùng grain nằm trong `dac_ta_sau_thu_thap_v0.5.0_de_xuat.schema.yaml`.

## Cohort và các trạng thái thiếu

- Cohort `one_to_one` bắt đầu từ `call_session`, lọc `call_type = one_to_one`, `initiated_ts` trong kỳ báo cáo, rồi **left join** phiên bản `outcome_log` hiện hành. Không loại call vì thiếu outcome hoặc stats. Cutoff và phiên bản pipeline phải đi cùng kết quả.
- `fact_call` có đúng một dòng mỗi `call_id`; nếu outcome không đến sau cutoff, `outcome_status = missing`, các kết quả chưa biết là `unknown` hoặc `null`. Không mặc định `false`, `0` hay chất lượng tốt.
- `fact_call_endpoint` có tối đa một dòng cho một `call_id × side × device_id` đã biết. Đầu callee chưa xác định thiết bị thì không tạo một `device_id` giả. `fact_call` vẫn có mặt. Mỗi endpoint giữ `network_epoch_refs` và `attempt_refs`; drill-down dùng `call_stats_epoch` và `ice_attempt_endpoint`. Context địa lý/mạng của fact endpoint là bối cảnh đầu tiên biết được, không ghi đè lịch sử khi đổi mạng.
- Chia kết quả theo `data_source`; synthetic có `sim_run_id` và không gộp với production. Chia đường thực tế thành P2P, relay, failed/không xác định theo evidence từ ICE; `ice_transport_policy = relay` không tự chứng minh đường thực tế là relay.

## Định nghĩa metric

`N` là số call trong cohort. Với trạng thái ba giá trị, `T/F/U` lần lượt là số true/false/unknown và `N=T+F+U`. Khi `N=0`, tỷ lệ là `null`. Dashboard luôn trình bày `T`, `F`, `U`, `N`; tỷ lệ bảo thủ `T/N` và khoảng `[T/N, (T+U)/N]`. Có thể trình bày thêm `T/(T+F)` với nhãn “trong nhóm biết kết quả”, không gọi đó là tỷ lệ toàn cohort.

| Metric | Định nghĩa và mẫu số | Thiếu dữ liệu |
| --- | --- | --- |
| Connection Success Rate | `media_connected = true` trên toàn `N`; ICE connected và DTLS connected là hai metric riêng cùng cách tính | `unknown` vào U; không đổi thành thất bại |
| Setup Failure Rate | `setup_failure_observed = true` theo quy tắc `x-metrics.setup_fail`; mẫu số toàn `N` | Thiếu bằng chứng vào U |
| Drop Rate | Trong các call xác nhận đã kết nối media, `dropped = true` / số call media connected đã biết; báo thêm số call chưa rõ kết nối | Call chưa rõ kết nối hoặc dropped vào U, không mặc định không rớt |
| CST technical | `checking_to_connected_ms` của attempt ICE thành công đầu tiên ở từng endpoint, cùng đồng hồ; giá trị cấp call là `max` hai endpoint khi cả hai đo được | Nếu thiếu một bên, call-level `null`; ghi `cst_assessment` và số endpoint đo được. Proxy từ state checking phải ghi phương pháp |
| TTFM sau answer | Callee: `first_media_received_ts - answer_clicked_at_client`; Caller: `first_media_received_ts - answer_observed_at_peer`, đều trên đồng hồ của chính endpoint. Cấp call lấy `max` hai duration đã đo | Không lấy `answer_received_at_be` trừ mốc client; thiếu một bên thì call-level `null` |
| RTT P50/P95 | Phân vị trên **mẫu RTT hợp lệ** của endpoint trong phạm vi thu thập; phân biệt `media_rtcp_rtt` và `ice_stun_rtt` bằng `metric_name`/version | Không lấy trung bình các P95 của epoch; nếu chỉ có percentile gộp sẵn mà không có mẫu/hist đủ để gộp thì không công bố P95 toàn call |
| Packet Loss | `100 × lost / (received + lost)` trên các delta cùng stream và epoch, chỉ khi mẫu số dương; giá trị âm của bộ đếm loss phải xử lý theo quy tắc pipeline đã version | Stream reset, thiếu counter hoặc attribution không rõ thì không tự điền 0 |
| Jitter | Tổng jitter mẫu hợp lệ / số mẫu; đơn vị ms. P95 chỉ khi có các mẫu hoặc histogram gộp hợp lệ | Không coi không nhận gói là jitter bằng 0 |
| Media Quality | `quality_poor` và `quality_assessment_status` theo detector version, chỉ trong phạm vi telemetry đủ đánh giá | Thiếu stats là `unknown`/unclassifiable, không phải good |

RTT, loss và jitter nằm trong ba object `fact_call_endpoint.rtt_ms`, `packet_loss_pct`, `jitter_ms`; **mỗi metric có** `sample_count`, `eligible_count`, `measurement_coverage`, `assessment`, `metric_definition_version` và `source_table`. `measurement_coverage = sample_count / eligible_count` khi mẫu số dương; nếu không biết hoặc bằng 0 thì `null`. `sample_count=0` là số mẫu quan sát được bằng không, không phải giá trị metric bằng không.

## Phạm vi và so sánh dashboard

`call_stats_epoch` và `call_stats_5s` hiện giới hạn `relay_or_failed`. Vì vậy P2P thành công có thể không có telemetry chất lượng. Dashboard phải hiển thị cả **coverage theo call của toàn cohort** (số call có phép đo / số call trong cohort) và coverage theo cửa sổ của phần được thu. Trình bày `sample_count`, `eligible_count`, `measurement_coverage` cạnh từng metric RTT/loss/jitter. Không suy rộng chất lượng của mẫu relay/failed sang toàn bộ call.

Khi lọc Country, Region, ISP, Network hoặc TURN, hiển thị số call P2P thành công, relay thành công, failed và unknown riêng. So sánh hai nhóm địa lý chỉ được gọi là so sánh **trên mẫu quan sát được** nếu coverage khác nhau hoặc không biết; không đưa kết luận cho toàn cohort. Nếu cần quality đại diện cho mọi call, mở quyết định thu telemetry P2P thành công.

Một metric đưa lên dashboard phải có một dòng `metric_config` với `metric_definition_version`, `scope`, `cohort_rule`, `numerator_rule`, `denominator_rule`, `missingness_rule`, `coverage_rule` và `source_tables`. Cùng một phiên bản định nghĩa phải được dùng ở simulator, pipeline và dashboard.

## Bốn nhóm chỉ số của dashboard

Định nghĩa máy đọc được của mọi metric nằm ở [`metric_config_v0.5.0.yaml`](metric_config_v0.5.0.yaml) (30 dòng, đã validate với `$defs/metric_config`). Bảng dưới là bản đọc nhanh theo đề của mentor.

| Nhóm | Metric | Nguồn chính | Ghi chú |
|---|---|---|---|
| Call Quality | Connection Success, Setup Failure, Drop, CST, TTFM, RTT, Loss, Jitter, `pcr_itt` | `fact_call`, `fact_call_endpoint` | Phần trên của tài liệu này |
| TURN Performance | Allocation Success, Failure Rate, Latency P50/P95, Stability, Health, Usage | `turn_allocation`, `turn_health_1m`, `fact_call_endpoint` | Mục dưới |
| Service Health | Availability, API Latency, Error Rate, Fallback Rate, Data Freshness | `service_health_1m`, `selector_decision`, `health_snapshot` | Mục dưới |
| Algorithm Quality | Lead match, rank used, top-k size, list churn, load concentration, interval coverage; synthetic: oracle in top-k, regret, so policy | `fact_call`, `fact_pair_evaluation`, `sim_decision_oracle` | Mục dưới |

### Latency của TURN là RTT qua TURN

Đề của mentor yêu cầu Latency P50/P95 cho TURN Performance. Cách hiểu đã chốt: **RTT đo được trên đường đi qua TURN** (từ `getStats`), không phải thời gian cấp phát. `alloc_ms` và `request_ts` đã bị bỏ khỏi contract vì cần hook SDK.

- `turn_path_rtt_relay_same_ms`: RTT đầu cuối của call mà hai đầu dùng **cùng một TURN**. Đây là thước đo sạch nhất vì chỉ một TURN nằm trên đường.
- `turn_path_rtt_involved_ms`: RTT đầu cuối của call `relay_relay` có TURN X trên đường. RTT này gồm hai chặng và chặng giữa, **không phải độ trễ riêng của X**. Chỉ dùng xếp hạng tương đối, mặc định `reporting_only`.
- Không gán RTT cho TURN khi `path_attribution_status` là `mixed` hoặc `unknown`, hoặc danh tính TURN chưa `identified`.
- Latency của chặng giữa hai TURN chỉ có khi bật `turn_probe` (`obs_active`).

### TURN Performance

- **Allocation Success và Failure Rate** tính từ `turn_allocation`, bỏ `unknown` khỏi mẫu số và báo coverage. Tách `server_failures` (bỏ 486, vì 486 là quota theo username) khỏi `all_failures` (giữ 508, thiếu capacity).
- **Usage** có bốn thành phần riêng: tải (`active_allocations`, `bandwidth_mbps`), `utilization` theo `capacity_alloc`, `selection_share` (được chọn) và `actual_use_share` (được ICE dùng thật).
- **Stability** gồm `rtt_cv_24h` (độ biến động P50 RTT theo giờ) và `health_flaps_24h`.
- **Health** là tỷ lệ phút ở từng `health_status`; thiếu snapshot tính là `unknown`, không phải `healthy`.

### Service Health

- **Availability** = Σ(req − error − timeout) / Σ req, tính trên tổng chứ không trung bình các phút. `static_config` không đi qua Selector nên loại khỏi mẫu số.
- **API Latency** lấy percentile từ `selector_decision.api_latency_ms`; timeout không vào percentile mà báo qua `timeout_rate`.
- **Fallback Rate** tách theo `fallback_type`. `data_backoff` phản ánh thiếu dữ liệu lịch sử, không phải lỗi dịch vụ.
- **Data Freshness** = tuổi quan sát của health snapshot (`request_ts − last_observed_ts`), kèm tuổi feature snapshot và `stale_share`.

### Algorithm Quality

- **TURN xếp hạng so với TURN ICE dùng:** `lead_pair_match_rate`, `rank_used_distribution`. Trong simulator giả định candidate về kịp, tỷ lệ gần 100 % khi TURN khỏe, nên không coi đây là thành tích.
- **Độ tin cậy:** `interval_coverage` so tỷ lệ khoảng chứa giá trị thật với mức công bố (ví dụ 95 %).
- **Chỉ synthetic (`sim_decision_oracle`):** `oracle_in_topk_rate` (VIA báo trên 90 %), `decision_regret` (lead, actual, list), và `policy_comparison_delta` giữa Geo Baseline và Smart Selector trên cùng world và seed.
- Bảng `sim_decision_oracle` đọc truth nên **không** vào policy, feature hay health (I34). **Dashboard được đọc** để hiển thị regret và top-k có chứa cặp tốt nhất, với điều kiện: trang ghi rõ synthetic-only, mọi biểu đồ gắn `data_source = synthetic`, và không dùng kết quả này để khẳng định cải thiện production. Các trang production-ready (Call Quality, TURN Performance, Service Health) không phụ thuộc bảng này.

## Mười kịch bản bắt buộc thành bộ lọc

Trong simulator, `sim_call_tag.scenario_tag` là nhãn chính thức. Cột "Bộ lọc trên fact" cho phép dashboard và production dựng lại cùng nhóm mà không cần nhãn.

| # | Kịch bản | Bộ lọc trên `fact_call` / `fact_call_endpoint` |
|---|---|---|
| 1 | VN↔VN cùng miền, cùng ISP | `pair_group = VN_VN`, `vn_region_caller = vn_region_callee`, `isp_caller = isp_callee` |
| 2 | VN↔VN khác miền | `pair_group = VN_VN`, `vn_region_caller ≠ vn_region_callee` |
| 3 | VN↔VN cùng miền, khác ISP | `pair_group = VN_VN`, cùng `vn_region`, `isp_caller ≠ isp_callee` |
| 4 | VN↔Quốc tế có TURN | `pair_group = VN_INTL`, `turn_availability_status` của đầu quốc tế = `local_turn_available` |
| 5 | VN↔Quốc tế không có TURN | `pair_group = VN_INTL`, đầu quốc tế `turn_availability_status in {no_turn_observed, no_healthy_turn}`; xem `used_fallback_turn` |
| 6 | Quốc tế↔Quốc tế cùng khu vực | `pair_group = INTL_INTL`, `dim_country_area.area` hai đầu bằng nhau |
| 7 | Quốc tế↔Quốc tế khác khu vực | `pair_group = INTL_INTL`, `area` khác nhau; so `path_type` `relay_same` và `relay_relay` |
| 8 | TURN Failure | `failure_phase ≠ none`, hoặc `health_status in {degraded, overloaded, down}` của TURN trong danh sách; recovery từ `detected_to_ice_recovery_ms` |
| 9 | Historical Cold-start | `confidence_level` thấp hoặc `fallback_type = data_backoff`; nhóm có ít cuộc gọi lịch sử trong `feat_path_history` |
| 10 | Network Change | `n_network_changes > 0` (cần `endpoint_network_context` có epoch mới) |

Ở production, kịch bản 8 và 9 không có nhãn truth; chỉ dùng được khi bộ lọc đủ bằng chứng, nếu không thì để `unknown`.

## Mẫu bằng chứng cho một insight

Đề yêu cầu tối thiểu 3 insight có bằng chứng dữ liệu (W5). Một insight chỉ được ghi vào báo cáo khi có đủ:

1. **Nhóm:** Country / Region / ISP / Network / TURN và kịch bản.
2. **Metric** và `metric_definition_version`, `data_source`.
3. **So sánh:** kỳ cơ sở và kỳ so, hoặc nhóm đối chứng.
4. **n, coverage** và số mẫu unknown của cả hai bên.
5. **Độ lớn hiệu ứng** kèm khoảng tin cậy hoặc dao động giữa các replicate.
6. **Ngưỡng phát hiện bất thường** (ví dụ độ lệch so với baseline có hiệu chỉnh theo mùa giờ) và số nhóm đã thử, để tránh chọn lọc nhiều lần.
7. **Giả thuyết giải thích** và dữ liệu cần thêm để kiểm chứng.

Insight trên dữ liệu synthetic phải ghi rõ không suy ra production.
