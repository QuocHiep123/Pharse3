# Khảo sát nguồn dữ liệu cho Data Contract v0.5.0

Sản phẩm W1 của Hiệp: khảo sát nguồn dữ liệu **TURN / Selector / SDK / Call** và trả lời mỗi bảng của [Data Contract v0.5.0](../contracts/data-contract-v0.5.0.md) lấy từ đâu, đã kiểm chứng đến mức nào, còn phải hỏi ai.

> **Tình trạng chung (06/11/2026):** chưa có log thật, danh sách field hay mẫu `getStats` từ hệ thống Call. Bằng chứng duy nhất đã kiểm chứng là (1) lab ICE trên Chromium 156 + coturn 4.6.1 một máy, và (2) đọc mã nguồn coturn (`prom_server.c`, bản 4.6.1 và `master`). Mọi thứ còn lại là **giả định của simulator**. Chưa có số liệu nào ở đây dùng để khẳng định kết quả production.

## 1. Tóm tắt theo nguồn

| Nguồn | Sinh dữ liệu ở đâu | Bảng được nuôi | Mức nguồn | Đã kiểm chứng | Việc phải xác nhận |
|---|---|---|---|---|---|
| **BE signaling (Spring Boot)** | Server của hệ thống Call | `call_session`, `selector_decision_request`, `selector_decision`, `selector_decision_pair`, `call_outcome`, `endpoint_network_context`, `select_request` | A | Chưa. Mới có mô tả trong tài liệu | Trace invite → kết thúc; thời điểm gọi Selector; timeout; ngữ cảnh Callee |
| **Selector** | Dịch vụ Selector (chưa tồn tại) | `select_response`, `service_health_1m`, nội dung Decision Log | A | Không áp dụng. Hiện chưa có Selector; Geo Baseline là baseline | Interface request/response với Đoàn |
| **SDK / client (web, mobile)** | App đọc `getStats`/ICE API chuẩn, không sửa SDK | `client_applied_config`, `ice_event`, `call_stats_epoch`, `call_stats_5s`, `client_call_report` | B | Lab Chromium 156 đọc được `selectedCandidatePairId`, `selectedCandidatePairChanges`, `relayProtocol`, `protocol`, `priority`, `currentRoundTripTime` (data channel, một máy) | Mobile, Firefox, Safari; `url`, `address`, `iceRole`; bộ đếm RTP; chi phí gửi; phát hiện đổi mạng trên web |
| **TURN server (coturn)** | Exporter Prometheus và log | `turn_health_1m`, `turn_allocation` | B (health), C (allocation) | Đọc mã coturn: **không có bộ đếm lỗi allocation**; `turn_traffic_*` chỉ tính session đã kết thúc | Bản công ty đang chạy; nguồn CPU, băng thông; log có khóa nối với call không |
| **Hạ tầng (inventory)** | Danh mục máy TURN | `dim_turn`, `dim_turn_endpoint`, `dim_asn`, `dim_country_area` | A, B | Chưa | Sơ đồ IP, DNS, VIP, anycast; capacity; quota; phạm vi inventory có đầy đủ không |
| **Probe giữa các TURN** | Tác tử đo, hệ thống mới | `turn_probe` | C | Chưa có gì | Đặt probe ở đâu, đo IP/port/giao thức nào, chu kỳ |
| **GeoIP / ASN** | BE tra từ IP | Các trường trong `ctx`, `endpoint_network_context` | B | Chưa | Nhà cung cấp GeoIP, độ chính xác theo ISP |
| **Simulator** | Hiệp dựng | Mọi bảng raw (synthetic) và `truth_leg_5m`, `incident_truth`, `sim_decision_oracle` | A, D | Hiệp tự kiểm bằng seed và trace một call | Giả định phân bố mạng có version |
| **Pipeline** | Hiệp dựng | `outcome_log`, `ice_attempt*`, `telemetry_coverage`, `feat_*`, `health_snapshot`, `fact_*` | D | Hiệp tự kiểm bằng validator | Không có nguồn ngoài |

Mức nguồn: **A** service tự tạo; **B** thu có điều kiện (getStats, exporter); **C** cần phép đo hoặc hệ thống mới; **D** suy ra bằng pipeline. Mức nguồn không quyết định field bắt buộc hay nullable.

## 2. Chi tiết từng nguồn

### 2.1. BE signaling

| Dữ liệu | Bảng | Ghi chú |
|---|---|---|
| Cuộc gọi bắt đầu, loại cuộc gọi, `ice_transport_policy`, `be_region` | `call_session` | `call_id` do BE sinh |
| Context ban đầu và khi đổi mạng (Country, vùng, ISP, ASN, loại mạng) | `endpoint_network_context` | BE ghi snapshot từ report của client và GeoIP lúc nhận. Loại mạng phải do client báo, trên web có thể thường là `unknown` |
| Lần gọi Selector và kết quả | `selector_decision_request`, `selector_decision`, `selector_decision_pair` | Selector **không tự ghi**; BE ghi từ response. Chưa có Selector thì `decision_source = static_config`, `policy_version = static@1` |
| Tín hiệu kết thúc, bắt máy, chuyển nhóm | `call_outcome` | BE chỉ ghi điều quan sát trực tiếp (`end_signal`). `dropped_turn`, `dropped_network` là suy luận ở pipeline |

**Điều chưa chắc:** BE có ngữ cảnh Callee ngay request đầu không, kể cả Callee offline chỉ được đánh thức bằng thông báo hoặc có nhiều thiết bị (A3).

### 2.2. SDK / client

| Dữ liệu | Bảng | Đã kiểm chứng |
|---|---|---|
| Cấu hình client thực áp dụng | `client_applied_config` | Do app ghi, theo thiết kế |
| Dòng thời gian ICE, cặp được chọn, đổi cặp | `ice_event` | Lab Chromium đọc được các trường chọn cặp. `url`, `address`, `iceRole` mới theo W3C, chưa đo |
| RTT, loss, jitter theo epoch và theo cửa sổ 5 giây | `call_stats_epoch`, `call_stats_5s` | Mới theo đặc tả. Lab dùng data channel nên chưa đo RTP |
| Báo cáo từng đầu về bắt máy, lý do kết thúc, trạng thái stats | `client_call_report` | Do app ghi |

**Quy ước chung:** app đọc API chuẩn rồi gửi, không sửa SDK. Duration chỉ hợp lệ khi trừ trên cùng một đồng hồ của cùng endpoint.

### 2.3. TURN server

| Dữ liệu | Bảng | Nguồn khả dĩ | Giới hạn |
|---|---|---|---|
| Số allocation đang chạy, CPU, băng thông | `turn_health_1m` | Exporter hoặc health checker | `bandwidth_mbps` không lấy từ `turn_traffic_*`; có thể null |
| Allocation thành công hoặc lỗi, mã lỗi | `turn_allocation` | **Log của TURN**, không phải SDK | Coturn không có bộ đếm lỗi allocation. 486 là quota theo username, 508 là thiếu capacity |
| Nối allocation với call | `turn_allocation` | `credential_ref`, `server_session_id` | Cần credential theo cuộc gọi; không có thì chỉ dùng được thống kê theo TURN (`match_method = ambiguous`) |

Không có `alloc_ms` và `request_ts`: cần hook SDK nên đã bỏ. **Latency của TURN trong dashboard là RTT qua TURN, không phải thời gian cấp phát.**

### 2.4. Hạ tầng và probe

- **Inventory** (`dim_turn`, `dim_turn_endpoint`): trong MVP tự xây trong simulator. Cấu trúc giữ nguyên để hạ tầng điền sau. `no_turn_observed` không có nghĩa `not_deployed` trừ khi `inventory_scope` đã xác nhận đầy đủ.
- **Probe** (`turn_probe`): nguồn có rủi ro khả thi lớn nhất, vì coturn không tự đo giữa các TURN. Cần tác tử đo riêng, số cặp tăng theo bình phương số TURN. Profile `obs_base` không có probe; `obs_active` bật probe để so sánh.

## 3. Dữ liệu thật hay giả lập, theo từng bảng

| Nhóm bảng | Production có thể lấy | Chỉ synthetic | Ghi chú |
|---|---|---|---|
| Call logs, Decision Log | Có, sau khi BE xác nhận | | `data_source = production` khi có |
| getStats, ICE | Có điều kiện, theo nền tảng | | Coverage báo qua `telemetry_coverage` |
| TURN health, allocation | Có điều kiện | | Allocation cần log TURN |
| Inventory | Có | | Tự xây trong MVP |
| Probe | Chưa | | Hệ thống mới |
| `truth_leg_5m`, `incident_truth`, `sim_decision_oracle`, `dirt_log` | | **Chỉ synthetic** | Production không có truth |
| `fact_call`, `fact_call_endpoint`, `fact_pair_evaluation` | Có, từ raw | | Cùng schema cho cả hai nguồn |

Kết quả trên dữ liệu synthetic **không** dùng để khẳng định thuật toán đã cải thiện chất lượng production.

## 4. Câu hỏi cho từng bên

### Mentor

1. "8 TURN mỗi bên" là 8 máy hay 8 mục URL/transport? Bắt buộc đủ 8 hay tối đa 8? (A1) Hiện simulator giả định tối đa 8 mục.
2. Công ty đo từng chặng thế nào: đo trực tiếp, RTT probe, giá trị suy ra hay số đầu cuối? Có mẫu log thật không? (A2)
3. Khi thu thật, danh sách có được biến thiên không? Không có thì dữ liệu không dự đoán được đường chưa dùng. (A7)
4. "Latency P50/P95" của TURN trong đề: xác nhận là RTT qua TURN.
5. Có được dùng dữ liệu thật từ hệ thống Call không, ở mức nào? Đề ưu tiên dữ liệu thật; hiện tạm giả lập vì chưa có.

### BE

1. Một trace từ invite đến kết thúc; thời điểm gọi Selector; timeout và fallback.
2. Ngữ cảnh Callee lấy từ đâu khi offline hoặc nhiều thiết bị? (A3)
3. Tín hiệu kết thúc nào BE quan sát được? Credential TURN có theo cuộc gọi không? (A6)
4. Nhà cung cấp GeoIP và ISP/ASN.

### WebRTC core, web, mobile

1. Mẫu `getStats` của cuộc gọi thành công, thất bại và có restart, trên từng nền tảng. (A4, issue #3)
2. Chi phí đọc bộ đếm, tổng hợp histogram và gửi.
3. Web phát hiện đổi mạng bằng gì? (A5)
4. `url`, `address`, `iceRole` và bộ đếm RTP có đọc được không?

### Hạ tầng TURN và mạng

1. Phiên bản coturn, `/metrics`, log mẫu; sơ đồ IP, DNS, VIP, anycast; capacity và quota; nguồn CPU và băng thông. (A6, A8)
2. Đặt probe ở đâu, đo IP/port/giao thức nào, chu kỳ bao nhiêu.

## 5. Khi chưa có câu trả lời

| Chưa có | Hành vi |
|---|---|
| Danh mục TURN thật | Simulator tự xây, có version; cấu trúc `dim_turn` giữ nguyên |
| Log allocation có khóa nối | `match_method = ambiguous`; chỉ thống kê theo TURN |
| `getStats` trên một nền tảng | Cột để null; `telemetry_coverage` báo không hỗ trợ; không coi là tốt |
| Phát hiện đổi mạng trên web | `network_epoch = 0` kèm coverage "không hỗ trợ"; không hiểu là không đổi mạng |
| Probe | Không có `turn_probe`; chặng giữa chỉ là số ước lượng |
| Ngữ cảnh Callee | Ghi `info_level`, không dùng thông tin tương lai để chấm điểm |
