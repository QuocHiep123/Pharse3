# W1 của Hiệp: một cuộc gọi chạy xuyên suốt simulator

**Mục tiêu:** Làm được một simulator synthetic có thể chạy lại, giải thích từng bản ghi và kiểm tra dữ liệu trước khi có log thật. Mentor chưa giao field production. [README contract cho simulator](w2-data-contract/README.md) là quyết định làm việc hiện tại; schema thu thật cần xác minh sau.

## Đầu ra nên bàn giao cuối W1

1. **World config có version:** tập user và TURN giả lập, vùng Bắc/Trung/Nam, ISP, quốc gia không có TURN, độ trễ/loss/jitter và sự cố theo thời gian. Mỗi con số ghi nguồn là giả định hoặc lab; không gán thành số production.
2. **Một generator có seed:** cùng config + seed → cùng ID, event và outcome. Truth về từng chặng nằm riêng với raw quan sát. Có profile `obs_base` không probe và `obs_active` có probe.
3. **Một policy thay thế được:** Geo Baseline hoặc static config trả hai danh sách TURN. Mentor xác nhận tối đa 8 TURN server mỗi bên. Ghi header decision, danh sách từng bên, và cặp được xét nếu có.
4. **Trace một cuộc gọi:** từ `call_id` xem được quyết định lúc đó, danh sách client thực áp dụng, cặp ICE đã chọn, stats và báo cáo kết thúc. Có ca bình thường, ca TURN lỗi/thiếu telemetry. Ca setup thất bại vẫn nằm trong cohort.
5. **Báo cáo kiểm tra:** event nối đúng khóa, không dùng dữ liệu tương lai, thống kê coverage, kết quả KPI có `unknown` khi thiếu chứng cứ, và danh sách giả định cần Đoàn/mentor xác nhận.

## Data model tối thiểu

Data model mô tả **một dòng đại diện cho gì**, khóa nối, ai tạo, thời điểm quan sát và trường hợp dữ liệu thiếu. ERD là cách vẽ quan hệ; workflow là trình tự xảy ra. Cần cả hai để simulator sinh event hợp lý.

| Bản ghi | Một dòng là gì | Khóa cần theo dõi |
|---|---|---|
| `dim_turn`, `dim_turn_endpoint` | TURN và endpoint có khoảng hiệu lực | `turn_id`, endpoint, thời gian hiệu lực |
| `call_session` | Một cuộc gọi bắt đầu | `call_id` |
| `selector_decision_request` | Một yêu cầu quyết định cấp call | `decision_id`, `call_id` |
| `selector_decision` | Danh sách cấp cho một bên/thiết bị trong decision | `decision_id`, `side`, `device_id` |
| `selector_decision_pair` | Một cặp được chấm theo một metric, khi đủ ngữ cảnh | `decision_id`, TURN/transport hai phía, metric |
| `client_applied_config` | Một client thực áp dụng cấu hình | `call_id`, `side`, `device_id`, `decision_device_id` |
| `endpoint_network_context` | Snapshot BE ghi khi nhận context ban đầu hoặc đổi mạng | `call_id`, `side`, `device_id`, epoch, `context_version` |
| `ice_event`, `call_stats_epoch` | Sự kiện ICE và cửa sổ thống kê tại endpoint | `call_id`, `side`, `pc_id`, `ice_generation`, thời gian |
| `call_outcome`, `client_call_report` | Tín hiệu BE / báo cáo từng client | `call_id`; client thêm `side`, `device_id` |
| `truth_leg_5m`, `run_manifest` | Thế giới ẩn và cấu hình lần chạy | `sim_run_id`, bucket/chặng |

Nếu chưa có thuật toán, BE ghi decision `static_config`; không tự bịa pair prediction, confidence hay propensity. Khi chưa biết Callee, `info_level` và context ghi đúng điều đã biết; không tạo row `selector_decision_pair` với khóa Callee null. BE là emitter của network context snapshot: GeoIP/ISP do BE tra, network type và mốc epoch do client báo; giữ provenance từng loại và không trừ timestamp của hai đồng hồ.

## Thứ tự triển khai một sample

1. Tạo `run_manifest`, catalog TURN và hai user; gắn `sim_run_id`, config version, seed.
2. Sinh `call_session` và network truth ẩn, rồi tạo request decision từ context **có trước** `request_ts`.
3. Policy trả hai danh sách. Lưu header một lần, list theo bên/thiết bị, pair prediction nếu thực sự có. Ghi `decision_id` vào cấu hình gửi cho client.
4. Client báo `client_applied_config` và tín hiệu mạng cho BE. BE ghi `endpoint_network_context` với `context_version` mới nếu cần; mô hình ICE chọn cặp thực tế theo giả định ICE của simulator. Sinh `ice_event` và getStats từ đường thực đi; không điền RTT cho mọi TURN không được đo.
5. BE tạo `call_outcome`; client tạo `client_call_report` nếu báo cáo về được. Pipeline nối theo key và thời gian để tạo outcome và coverage.
6. Đánh giá một `call_id`: quyết định có dùng future data không; cặp lead và cặp thực tế có gì khác; nhãn poor/good/unknown có đủ bằng chứng không.

## Điều kiện hoàn thành demo

- Cùng seed + config cho trace giống nhau; thay sự cố TURN làm kết quả thay đổi có lý do.
- Một decision có một header, nhiều list theo bên/thiết bị; applied config trỏ đúng `decision_device_id`, kể cả khi thiết bị áp dụng khác thiết bị đích ban đầu.
- Cặp lead thống nhất qua metric và hai mục rank 1; cặp ICE thực tế được ghi riêng. Thiếu Callee thì không tạo prediction hai phía.
- Tắt probe hoặc thiếu một báo cáo client không tự tạo số đo, `false` hay 0; coverage/KPI báo trạng thái thiếu.
- Feature và health sử dụng event đã đến và đã publish trước `request_ts`; log TURN chỉ join với call khi đủ bằng chứng.

## Phần cần xác nhận sau khi có nguồn thật

Mentor xác nhận cách đo từng chặng và quyền biến thiên danh sách. BE xác nhận thời điểm biết Callee và khóa nối. WebRTC core/client xác nhận getStats, network context, ICE event và clock trên từng nền tảng. Các câu hỏi được theo dõi ở [#5](https://github.com/QuocHiep123/Pharse3/issues/5), [#6](https://github.com/QuocHiep123/Pharse3/issues/6), [#7](https://github.com/QuocHiep123/Pharse3/issues/7), [#8](https://github.com/QuocHiep123/Pharse3/issues/8). Khi chưa có câu trả lời, giữ chúng thành assumption/config của simulator.
