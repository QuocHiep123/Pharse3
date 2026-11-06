# Data Contract v0.5 cho simulator: quyết định áp dụng

Tài liệu này chốt **interface dữ liệu để Hiệp và Đoàn cùng chạy simulator**. Nó không xác nhận field production có thể thu được. Hai YAML mang tên `de_xuat` vì giữ đường dẫn tham chiếu hiện tại; trạng thái dự kiến là `simulator_ready`, còn triển khai thu thật phải qua xác minh nguồn. Nếu câu chữ ở đây khác YAML, cần sửa YAML và kiểm tra lại trước khi gọi schema final. Số liệu lab là bằng chứng cơ chế trên Chromium/coturn một máy, không phải tham số production.

## Đọc tài liệu

1. [Data Contract v0.5.0 (bản chốt)](DATA_CONTRACT_v0.5.0.md): quyết định, assumption, danh sách bảng, bằng chứng nền.
2. [Schema raw](data_contract_v0.5.0.schema.yaml) và [schema lớp sau thu thập](dac_ta_sau_thu_thap_v0.5.0.schema.yaml).
3. [Khảo sát nguồn dữ liệu](KHAO_SAT_NGUON_DU_LIEU.md), [định nghĩa metric](metric_config_v0.5.0.yaml) và [KPI MVP](KPI_MVP_v0.5.0.md) (4 nhóm chỉ số, 10 kịch bản thành bộ lọc).
4. [Sơ đồ bảng](So_do_database_Data_Contract_v0.5.0.md), [giải thích field](Bang_du_lieu_Data_Contract_v0.5.0.md), [hướng thuật toán](Huong_giai_quyet_Smart_TURN_Selector.md).

Sơ đồ và bảng được sinh từ YAML; khi đổi schema, sửa YAML trước rồi sinh lại hai tài liệu đó.

> **Bản chốt tổng hợp:** [`DATA_CONTRACT_v0.5.0.md`](DATA_CONTRACT_v0.5.0.md). `Bang_du_lieu` và `So_do_database` đã đồng bộ với YAML cho #5–#8; khi khác nhau thì tin YAML.

## Những quyết định dùng ngay trong simulator

| Chủ đề | Quyết định mô phỏng |
|---|---|
| Nguồn dữ liệu | Mọi raw synthetic có `data_source = synthetic`, `sim_run_id` và version cấu hình/seed trong `run_manifest`. Network truth nằm ở bảng truth, không chép thành raw quan sát khi profile không có nguồn đo đó. |
| Hai lớp | Raw gồm event một nguồn ghi, Decision Log và bảng tham chiếu. Clean, feature, outcome, labeled data, KPI và API nằm ở lớp sau thu thập. Field derived ghi lineage và cutoff thời gian. |
| “8 TURN” | Giả định cấu hình **tối đa 8 mục URL/transport mỗi bên**, không phải 8 máy; UDP/TCP/TLS trên cùng máy là mục riêng và **cùng chia sẻ tổng 8 chỗ**. Geo/Historical Baseline trả đúng 8 nếu đủ mục hợp lệ. Policy cải tiến trả 1–8; thiếu mục thì `insufficient_candidates`, không nhân bản server. Đây là config để mô phỏng, chưa gán cho mentor. |
| Bối cảnh mạng | `endpoint_network_context` là snapshot **BE ghi** khi nhận context ban đầu hoặc tín hiệu đổi mạng. BE lấy GeoIP/ISP và ghi network type do client báo, với provenance của từng nhóm field (`network_type_source`, `epoch_clock_source`). `context_version` giữ phiên bản khi enrich đến muộn; tại cutoff chỉ dùng bản có version lớn nhất **đã ingest**. `epoch_start_ts` thuộc đồng hồ client, `observed_ts` thuộc BE; không trừ chéo hai mốc. |
| Bối cảnh Callee | `info_level` cho biết mức thông tin có thật tại lúc quyết định. Khi chưa biết Callee, ghi `unknown` hoặc bỏ field theo schema; không lấy ngữ cảnh tương lai để chấm điểm. `selector_decision_pair` chỉ có dòng khi đủ hai phía để định danh cặp; không để null trong khóa cặp. |
| Decision và ICE | Header `selector_decision_request` có một dòng mỗi `decision_id`; `selector_decision` giữ danh sách từng bên/thiết bị. Pair xét và `is_lead` cùng một decision. Cặp lead là **một cặp chung** trên mọi metric; hai entry rank 1 phải tương ứng lead. Client ghi danh sách đã áp dụng; `ice_event` ghi cặp thực tế, có thể khác lead. |
| Applied config | `decision_device_id` là thiết bị mà danh sách được cấp cho và dùng để tham chiếu đúng hàng decision; `device_id` của client áp dụng là thiết bị thực tế, có thể khác. Không nối chỉ bằng `decision_id` khi một quyết định có nhiều thiết bị. |
| Probe | `obs_base` không có `turn_probe`; `obs_active` bật probe để so sánh. Probe đo giữa TURN, có nguồn, thời điểm, giao thức và sai số mô phỏng; không tự gọi là RTT media. Thiếu probe không điền 0. |
| Labeled data | `fact_call` có grain **một dòng mỗi `call_id` trong cohort** để tính KPI ITT. Dự đoán theo từng decision/cặp/metric cần bảng hoặc view riêng, không ép nhiều cặp vào một dòng call. Failed setup giữ lại dù không có cặp ICE thực tế. |
| Chất lượng và KPI | Phân biệt `K` poor, `G` biết chắc không poor, `U_quality` thiếu bằng chứng chất lượng, `U_outcome` thiếu kết quả. `pcr_itt_low = K/N`, `pcr_itt_high = (K+U_quality+U_outcome)/N`; báo riêng coverage, mẫu số, metric definition version, nguồn và nền tảng. `N=0` thì undefined; missing không phải 0/false. |
| Thời gian và khóa nối | Nối bằng `call_id`, `decision_id`, `side`, `decision_device_id`/`device_id`, `pc_id`, `ice_generation` theo đúng grain; TURN log chỉ nối khi có khóa đáng tin. Trước mỗi decision, feature/health chỉ dùng event đã quan sát và công bố trước cutoff, tránh đọc tương lai. |

Giá trị `null` và field **vắng mặt** khác nhau trong JSON Schema. “Không có trong `required`” chỉ có nghĩa là có thể bỏ field; field nhận `null` chỉ khi type/schema cho phép. Simulator phải biểu diễn thiếu dữ liệu theo schema và lưu `telemetry_coverage` để giải thích vì sao thiếu.

## Phạm vi chưa chốt cho dữ liệu thật

- Mentor chưa cung cấp log thật, cách đo từng chặng, hoặc xác nhận “8 TURN” là 8 mục cấu hình. Các giá trị này hiện là **assumption của simulator**.
- BE và client chưa xác nhận thời điểm biết Callee, network context lấy ở đâu, khóa nối TURN allocation với call, và getStats có mặt trên nền tảng nào. Theo dõi [#3](https://github.com/QuocHiep123/Pharse3/issues/3) (telemetry tối thiểu) và [#6](https://github.com/QuocHiep123/Pharse3/issues/6) (network context). Quy tắc country không có TURN (`turn_availability_status`, `inventory_scope`) đã đưa vào schema theo [#5](https://github.com/QuocHiep123/Pharse3/issues/5).
- Ngưỡng KPI, trạng thái coverage và định nghĩa chất lượng cần đối chiếu telemetry có thể thu. Theo dõi [#7](https://github.com/QuocHiep123/Pharse3/issues/7).
- `fact_call` đã đủ cột và có `fact_pair_evaluation` cho đánh giá dự đoán theo cặp ([#8](https://github.com/QuocHiep123/Pharse3/issues/8)). Còn lại: dashboard dùng các bảng này và test dữ liệu 6 loại cuộc gọi.
- Các nhãn `x-review` và bảng hoãn trong YAML vẫn cần kiểm tra. Bản để BE/WebRTC thu thật cần xác nhận nguồn, event mẫu, đơn vị, khóa join, nền tảng, hành vi thiếu và cập nhật spec/ERD/schema đồng bộ. Downstream còn mở không cản trở sinh raw synthetic theo profile đã chốt.

## Bài kiểm tra bàn giao một cuộc gọi

Với cùng config và seed, sinh lại cùng `call_id` và thứ tự event. Trace phải cho thấy decision → cấu hình client áp dụng → cặp ICE thực tế → báo cáo BE/client → outcome, gồm một ca thành công và một ca thất bại. Tắt probe hoặc thiếu getStats rồi chạy lại: KPI chuyển sang nhóm unknown khi không đủ bằng chứng, không tự thành tốt. Mọi giá trị dùng lúc quyết định phải có timestamp/cutoff trước `request_ts`.
