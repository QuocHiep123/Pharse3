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
