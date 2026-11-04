# Giải thích Data Contract v0.1 — từng bảng, từng field, vì sao chọn như vậy

> **Tài liệu này dành cho ai?** Cho mọi người: Đoàn, mentor, người mới vào dự án, kể cả người chưa từng làm WebRTC.
> **Quan hệ với contract:** `data-contract-v0.1.md` là bản **chuẩn** (luật). Tài liệu này là bản **giải thích** (vì sao có luật đó). Nếu hai bản khác nhau, bản contract đúng.

**Cách đọc:**
- Người mới: đọc §1 → §2 → §14 (đi qua một cuộc gọi), các phần còn lại tra khi cần.
- Người viết code: đọc §3–§13 theo bảng mình đụng tới.
- Muốn biết "sao không làm cách khác": đọc §15.

Mỗi bảng được giải thích theo cùng một khuôn:
- **Bảng này trả lời câu hỏi gì?**
- **Khi nào sinh ra, ai sinh ra?**
- **Từng field:** nghĩa, ví dụ, và *vì sao cần* (bỏ đi thì mất gì)

---

## 1. Bối cảnh cho người chưa biết WebRTC

### 1.1 Một cuộc gọi đi qua đâu?

Hai điện thoại thường **không nói chuyện trực tiếp được với nhau**, vì chúng nằm sau router, NAT của nhà mạng hoặc tường lửa. Giải pháp là dùng một máy chủ trung gian ở giữa để chuyển tiếp âm thanh và hình ảnh. Máy chủ đó gọi là **TURN server**, hay **relay**.

```
  Người A  ──────►  TURN của A  ──────►  TURN của B  ──────►  Người B
 (HCM, Viettel)    (TA, ở SGN)          (TB, ở HAN)        (Hà Nội, VNPT)
        chặng 1               chặng 2               chặng 3
```

- Mỗi đoạn mũi tên là một **chặng (leg)**. Tổng độ trễ của cuộc gọi ≈ tổng độ trễ 3 chặng.
- Nếu A và B dùng **cùng một TURN** thì chặng 2 không tồn tại (bằng 0).
- Chọn TURN gần nhưng mạng tệ, hoặc xa nhưng nằm cùng nhà mạng, cho ra kết quả rất khác nhau. Vì vậy cần **thuật toán chọn TURN**, phần việc của Đoàn.

### 1.2 Thuật toán làm gì, và vì sao khó đánh giá?

- Thuật toán xếp hạng **4 TURN cho mỗi bên**. Cuộc gọi đi bằng **TURN hạng 1 của A × TURN hạng 1 của B**. Hạng 2–4 là dự phòng khi hạng 1 lỗi.
- Hệ thống **chỉ đo được con đường đã đi**. Những con đường khác không có số liệu, nên không biết chắc thuật toán đã chọn đúng hay chưa. Đây là bài toán **selection bias** (lệch do chính việc lựa chọn), và là lý do contract có nhiều field đặc biệt như `propensity` hay `method`.

### 1.3 Từ điển nhỏ

| Thuật ngữ | Nghĩa dễ hiểu |
|---|---|
| **TURN / relay** | Máy chủ trung gian chuyển tiếp âm thanh và hình ảnh giữa hai người |
| **Allocation** | Thao tác "xin một chỗ" trên TURN trước khi dùng, giống đặt bàn trước ở nhà hàng |
| **ICE** | Quy trình tự động trong WebRTC để thử các đường nối và chọn đường dùng được |
| **P2P** | Hai bên nối thẳng với nhau, không qua TURN |
| **Signaling** | Máy chủ điều phối cuộc gọi: ai gọi ai, đổ chuông, bắt máy. Ở công ty là backend Spring Boot |
| **Selector** | Dịch vụ chọn TURN (thuật toán của Đoàn) |
| **ISP / ASN** | Nhà mạng (Viettel, VNPT, FPT…). ASN là "mã số" của nhà mạng trên Internet, ví dụ Viettel = 7552 |
| **Latency một chiều (one-way)** | Thời gian để gói tin đi **một chiều** từ điểm X tới Y, tính bằng ms |
| **RTT** | Round-trip time: thời gian **đi và về**. Xấp xỉ 2 lần one-way |
| **Packet loss** | % gói tin bị mất dọc đường |
| **Jitter** | Độ "giật" của độ trễ: gói này tới nhanh, gói kia tới chậm. Jitter cao thì tiếng bị rè hoặc đứt quãng |
| **P50 / P95** | P50 là trung vị (một nửa số cuộc gọi tốt hơn mức này). P95: 95% cuộc gọi tốt hơn mức này, thể hiện **phần đuôi xấu** |
| **CST** | Call Setup Time: từ lúc bắt máy tới lúc thật sự nghe được nhau |
| **TTFM** | Time To First Media: từ lúc nối xong tới gói âm thanh đầu tiên |
| **MOS** | Điểm chất lượng cảm nhận, thang 1–5 |
| **Exploration** | Cố ý cho một phần nhỏ cuộc gọi đi TURN hạng 2–4 để thu thêm dữ liệu |
| **Propensity** | Xác suất thuật toán chọn một phương án. Dùng để "cân lại" dữ liệu bị lệch |
| **Snapshot** | Bản chụp dữ liệu thống kê tại một thời điểm. Thuật toán chỉ được đọc snapshot của quá khứ |
| **Segment** | Một nhóm user có chung đặc điểm, ví dụ "Viettel miền Nam dùng 4G" |

---

## 2. Bức tranh tổng

### 2.1 Contract là ba "hợp đồng" ở ba chỗ giao nhau

```
 Nơi sinh dữ liệu               Pipeline (Hiệp)                       Nơi dùng
 (SDK, Signaling, Selector,
  TURN, probe — trên sim
  thì simulator đóng vai)
        │
        │  ① Event schema          raw → clean → fact → mart  ──►  Dashboard
        └──────────────────────►        (nội bộ, tự do sửa)
                                              │ ② Feature store
                                              ▼
                                       Thuật toán của Đoàn
        ▲                                     │
        └──────── ③ API Selector ─────────────┘
```

| Hợp đồng | Bảo vệ điều gì |
|---|---|
| ① **Event schema** | Hôm nay dữ liệu từ simulator, mai là log thật của công ty. Đúng contract thì pipeline **không phải viết lại** |
| ② **Feature store** | Đoàn đọc số liệu Hiệp xử lý. Hiệp đổi cột tùy tiện thì thuật toán của Đoàn hỏng |
| ③ **API Selector** | Simulator gọi thuật toán của Đoàn. Sau này Signaling bằng Java cũng gọi đúng giao diện này |

### 2.2 Bốn nhóm bảng

| Nhóm | Bảng | Đặc điểm |
|---|---|---|
| **Danh mục** (dimension) | `dim_turn`, `dim_asn`, `dim_user` | Ít thay đổi. Mô tả "ai, cái gì" |
| **Sự kiện** (event) | `call_session`, `selector_decision`, `turn_allocation`, `ice_attempt`, `path_leg_measurement`, `call_stats_5s`, `call_outcome`, `turn_health_1m`, `service_health_1m` | Chỉ ghi thêm, không sửa. Mô tả "chuyện gì đã xảy ra, lúc nào" |
| **Feature store** | `feat_*` | Pipeline tính từ sự kiện. Thuật toán đọc |
| **Ẩn** (chỉ simulator) | `truth_leg_5m`, `incident_truth`, `dirt_log` | "Đáp án", chỉ dùng để chấm điểm |

---

## 3. Quy ước chung và lý do

| Quy ước | Cụ thể | Vì sao |
|---|---|---|
| **Giờ UTC** | `2026-11-12T13:45:01.123Z` | Server ở nhiều nước. Dùng giờ địa phương thì 2 sự kiện cùng lúc ở VN và Đức bị lệch 6 tiếng. Cần giờ VN để phân tích "giờ cao điểm" thì dùng cột phái sinh `local_hour_vn` |
| **Chính xác tới ms** | `.123` | CST và TTFM chỉ vài trăm ms. Làm tròn tới giây thì không đo được |
| **Partition theo ngày `dt`** | `raw/call_outcome/dt=2026-11-12/` | Pipeline chạy theo ngày. Chạy lại một ngày chỉ cần ghi đè thư mục ngày đó |
| **ID dạng UUIDv7** | `0193a4…` | Duy nhất toàn cầu, máy nào cũng tự sinh được mà không trùng. Phiên bản v7 còn **sắp xếp được theo thời gian**, nên tra cứu nhanh |
| **Đơn vị cố định** | ms, %, kbps | Chuẩn W3C trả RTT và jitter bằng **giây**, có thư viện trả đơn vị khác. Không chốt đơn vị thì một nguồn nhân sai ×1000 là dashboard sai theo mà không ai biết |
| **Mã quốc gia ISO** | `VN`, `TW` | Chuẩn quốc tế, tránh `Vietnam` / `Viet Nam` / `VN` lẫn lộn |
| **Mã thành phố IATA** | `HAN`, `SGN`, `DAD` | Ngắn, chuẩn, mỗi thành phố một mã duy nhất |
| **`unknown` khác `null`** | `"unknown"` = không biết; `null` = không áp dụng | User ở Nhật thì "miền Bắc/Trung/Nam" là **không áp dụng** (`null`). User VN mà không xác định được miền là **không biết** (`unknown`). Gộp chung thì không đo được dữ liệu thiếu bao nhiêu |
| **Không điền 0 khi thiếu số đo** | Để `null` và ghi lý do | Cuộc gọi lỗi mà ghi loss = 0% thì TURN tệ trông lại hoàn hảo. Đây là lỗi nguy hiểm nhất vì **sai mà không báo** |
| **Mã hóa user** | `user_hash` = HMAC của user_id | Bảo vệ danh tính. Không lưu IP thô, vị trí chỉ tới cấp thành phố |
| **Tên cột tiếng Anh, snake_case** | `alloc_ms` | Java, Python và SQL đều đọc thuận |

---

## 4. Các cột có ở mọi bảng sự kiện

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `event_id` | Mã duy nhất của **một** sự kiện | `0193…e7` | Mạng chập chờn khiến điện thoại gửi lại cùng một sự kiện 2 lần. Có mã thì pipeline **loại được bản trùng** |
| `contract_version` | Dòng này theo phiên bản contract nào | `0.1.0` | Khi contract nâng cấp, pipeline biết dòng cũ hay dòng mới để đọc cho đúng |
| `data_source` | Dữ liệu từ đâu ra | `synthetic`, `production` | Đề bài **cấm** dùng kết quả giả lập để khẳng định production tốt hơn. Cột này giữ ranh giới đó |
| `producer` | Hệ thống nào sinh ra | `client_sdk`, `signaling` | Đồng hồ của mỗi hệ thống tin cậy khác nhau (đồng hồ điện thoại hay sai). Gặp lỗi thì biết hỏi ai |
| `event_ts` | Lúc sự kiện **xảy ra**, theo đồng hồ của nơi sinh | `13:00:04.412Z` | Dùng để tính mọi thứ theo thời gian: CST, giờ cao điểm |
| `ingest_ts` | Lúc hệ thống thu thập **nhận được** | `13:00:05.020Z` | So với `event_ts` thì biết: (1) sự kiện đến **trễ** bao lâu; (2) đồng hồ điện thoại có **sai** không (nếu `event_ts` nằm ở tương lai so với `ingest_ts` thì chắc chắn đồng hồ sai) |
| `sim_run_id` | Lần chạy simulator nào | `run-20261112-s42` | Chạy simulator nhiều lần với cấu hình khác nhau. Không có cột này thì dữ liệu các lần chạy trộn vào nhau |
| `dt` | Ngày của sự kiện | `2026-11-12` | Để chia thư mục theo ngày (xem §3) |

---

## 5. Danh sách giá trị (enum) và ý nghĩa

| Enum | Giá trị → nghĩa | Vì sao chia như vậy |
|---|---|---|
| `side` | `caller` = người gọi, `callee` = người nghe | Hai bên có mạng, vị trí và TURN khác nhau. Mọi số liệu phải biết thuộc bên nào |
| `network_type` | `wifi`, `4g`, `5g`, `ethernet`, `unknown` | Đề bài yêu cầu phân tích theo Network Type. 4G thường trễ và mất gói nhiều hơn Wi-Fi |
| `info_level` | `full` = biết cả hai bên; `caller_only` = chỉ biết người gọi; `country_only` = biết bên kia ở nước nào; `none` = không biết gì | Lúc bấm gọi, hệ thống thường **chưa biết người nghe ở đâu** (gọi mù). Cột này tách được "quyết định khi thiếu thông tin" ra để đánh giá riêng |
| `decision_phase` | `initial` = lúc bấm gọi; `refined` = sau khi bên kia bắt máy; `restart` = phải chọn lại giữa chừng | Một cuộc gọi có thể được quyết định nhiều lần |
| `decision_mode` | `live` = quyết định được dùng thật; `shadow` = chạy thử song song, chỉ ghi lại | Khi pilot ở công ty, thuật toán mới thường chạy "bóng" trước. Có cột này thì không lẫn hai loại |
| `decision_source` | `api` = Selector trả lời bình thường; `static_fallback` = Selector lỗi nên điện thoại dùng danh sách mặc định; `cache` = dùng kết quả cũ | Selector sập thì cuộc gọi vẫn diễn ra. Phải biết cuộc gọi đó **không** do thuật toán quyết định, không thì đổ lỗi oan cho thuật toán |
| `transport` | `udp`, `tcp`, `tls` | Một số mạng (công ty, quán cà phê) chặn UDP nên phải đi TCP hoặc TLS, vốn chậm hơn. Không ghi lại thì đổ lỗi oan cho TURN |
| `leg_type` | `user_turn` = chặng giữa người và TURN; `turn_turn` = chặng giữa hai TURN | Hai loại chặng có bản chất khác nhau: chặng có người phụ thuộc mạng của user, chặng giữa TURN thì không |
| `direction` | `forward` = theo chiều A→B; `reverse` = chiều ngược lại | Mạng không đối xứng: chiều tải lên (upload) của 4G thường kém hơn chiều tải xuống |
| `measure_method` | `inband` = đo trong lúc đang gọi; `alloc` = đo lúc xin chỗ TURN; `mesh_probe` = các TURN tự ping nhau; `idle_probe` = điện thoại tự đo lúc rảnh | Mỗi cách đo có độ tin cậy và độ lệch khác nhau. Trộn mà không biết nguồn thì kết luận sai (§8.5) |
| `path_type` | `relay_relay` = hai bên dùng 2 TURN khác nhau; `relay_same` = cùng 1 TURN; `relay_direct` = một bên qua TURN, một bên nối thẳng; `p2p_host` / `p2p_srflx` = nối thẳng hoàn toàn | Cuộc gọi nối thẳng **không dùng TURN**, nên không được tính vào thành tích tốt hay xấu của TURN nào |
| `ice_trigger` | `initial` = lần thử đầu; `fallback` = hạng 1 lỗi nên thử hạng sau; `restart_network_change` = đổi Wi-Fi↔4G; `restart_failure` = mạng rớt nên nối lại | Phục vụ kịch bản TURN Failure và Network Change |
| `ice_state` | `connected`, `failed`, `timeout`, `cancelled` | `cancelled` (người dùng tắt máy giữa chừng) không phải lỗi kỹ thuật |
| `end_reason` | `normal_hangup` = cúp máy bình thường; `not_answered` = không bắt máy; `rejected` = từ chối; `cancelled_by_caller` = người gọi hủy; `ice_failed` = không nối được; `dropped_network` = rớt do mạng; `dropped_turn` = rớt do TURN; `app_crash`; `unknown` | Tách lý do **xã hội** (không bắt máy) khỏi lý do **kỹ thuật** (không nối được). Gộp chung thì tỉ lệ lỗi bị thổi phồng |
| `pair_group` | `VN_VN`, `VN_INTL`, `INTL_INTL` | Đúng 3 nhóm đề bài yêu cầu phân tích |
| `health_status` | `healthy`, `degraded` = chậm hơn bình thường, `overloaded` = quá tải, `down` = sập, `maintenance` = đang bảo trì | Phân biệt "đang bảo trì có kế hoạch" với "sập bất ngờ" |
| `alloc_error` | `timeout`, `unauthorized_401` / `forbidden_403` = lỗi xác thực, `quota_486` = hết hạn mức, `capacity_508` = server hết chỗ, `unreachable` = không tới được | Mỗi lỗi có cách xử lý khác nhau: hết chỗ thì cần thêm server, lỗi xác thực là lỗi cấu hình |

---

## 6. Bảng danh mục

### 6.1 `dim_turn`: danh sách TURN server

**Trả lời câu hỏi:** "TURN này ở đâu, của nhà mạng nào, chứa được bao nhiêu?"
**Ai sinh:** đội hạ tầng (trên sim là file `world.yaml`).

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `turn_id` | Mã TURN, theo quy tắc `<nước>-<thành phố>-<nhà host>-<số>` | `VN-SGN-VTL-01` | Đọc mã là biết vị trí, không cần tra |
| `hostname` | Tên miền thật | `turn-sgn-01.vtl.example` | Điện thoại chỉ biết tên miền. Pipeline cần tên miền để đổi ngược ra `turn_id` (§12) |
| `country` | Nước đặt TURN | `VN` | Phân tích TURN quốc tế theo Country |
| `vn_region` | Miền (chỉ với TURN ở VN) | `south` | Phân tích theo Bắc/Trung/Nam |
| `city` | Thành phố | `SGN` | Mức chi tiết hơn miền |
| `lat`, `lon` | Tọa độ | `10.82, 106.63` | Tính khoảng cách địa lý cho Geo Baseline và vẽ bản đồ |
| `host_isp`, `host_asn` | Nhà mạng nào đặt TURN này | `viettel`, `7552` | Câu hỏi "user Viettel dùng TURN của Viettel có tốt hơn không?" (cùng ISP hay khác ISP) |
| `capacity_alloc` | Số chỗ tối đa đồng thời | `5000` | Tính % tải để biết khi nào quá tải |
| `transports` | Giao thức hỗ trợ | `{udp,tcp,tls}` | TURN không hỗ trợ TLS thì vô dụng với user sau tường lửa chặt |
| `status` | Đang chạy / bảo trì / đã gỡ | `active` | |
| `valid_from`, `valid_to` | Thông tin này đúng trong khoảng thời gian nào | | TURN có thể bị chuyển hoặc gỡ. **Thêm dòng mới chứ không sửa dòng cũ** (gọi là SCD2), để khi phân tích lại tháng trước vẫn thấy đúng topology của tháng trước |

### 6.2 `dim_asn`: danh sách nhà mạng

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `asn` | Mã số nhà mạng | `45899` | Thiết bị chỉ biết IP, từ IP suy ra ASN. Đây là cách xác định nhà mạng chính xác nhất. Paper Via của Microsoft cũng gom nhóm theo ASN |
| `isp` | Tên dễ đọc | `vnpt` | Hiển thị trên dashboard |
| `country` | Nước | `VN` | |
| `access_kind` | Mạng cố định, di động hay cả hai | `mobile` | Cùng là Viettel nhưng cáp quang và 4G khác nhau rất nhiều |

### 6.3 `dim_user`: thông tin người dùng (đã ẩn danh)

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `user_hash` | Mã người dùng đã mã hóa | `9f2c41ab…` | Đếm được "bao nhiêu người khác nhau" mà không biết là ai |
| `home_country`, `home_vn_region`, `home_city` | Nơi **thường** ở | `VN`, `south`, `SGN` | Chỉ là nơi thường ở. Vị trí **tại lúc gọi** nằm trong `ctx` (§7), vì người dùng có thể đi công tác hoặc roaming |
| `home_isp`, `home_asn` | Nhà mạng thường dùng | `viettel`, `7552` | |
| `primary_network` | Loại mạng hay dùng | `wifi` | Simulator dùng để sinh hành vi |
| `cohort` | `normal` hoặc `cold_start` | `cold_start` | Simulator đánh dấu các user cố ý cho ít dữ liệu, để kiểm tra kịch bản Cold-start |
| `created_at` | Ngày tạo tài khoản | | User mới không có lịch sử |

---

## 7. Object `ctx`: "bối cảnh" của một bên tại lúc quyết định

**Vì sao tách thành object riêng?** Cùng một bộ thông tin (nước, miền, nhà mạng, loại mạng) xuất hiện ở nhiều chỗ: lúc ra quyết định (`self_ctx`, `peer_ctx`) và lúc kết thúc (`*_ctx_final`). Định nghĩa một lần, dùng lại nhiều nơi, thì không bao giờ lệch.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `user_hash` | Ai | `9f2c…` hoặc `null` | `null` khi gọi mù, lúc chưa biết bên kia là thiết bị nào |
| `country`, `vn_region`, `city` | Đang ở đâu **lúc này** | `VN`, `south`, `SGN` | Thuật toán chọn TURN theo vị trí hiện tại, không theo nơi thường ở |
| `isp`, `asn` | Đang dùng nhà mạng nào | `viettel`, `7552` | Bắt Wi-Fi quán cà phê là FPT dù SIM là Viettel |
| `network_type` | Wi-Fi hay 4G… | `4g` | |
| `geo_source` | Vị trí lấy từ đâu: suy từ IP, app tự báo, hay cả hai | `both` | Vị trí suy từ IP có thể sai |
| `geo_mismatch` | App báo một nơi, IP lại chỉ nơi khác | `true` | Dấu hiệu dùng **VPN** hoặc **roaming** (SIM Việt ở Nhật). Những cuộc gọi này cần tách riêng, không thì làm bẩn thống kê |
| `segment_key` | Nhãn nhóm đã chuẩn hóa | `VN\|south\|7552\|4g` | Khóa để tra feature store (§11) |

---

## 8. Bảng sự kiện theo luồng cuộc gọi

### 8.1 `call_session`: "giấy khai sinh" của cuộc gọi

**Trả lời câu hỏi:** "Cuộc gọi này có tồn tại không, ai gọi ai, lúc nào?"
**Khi nào:** ngay khi A bấm gọi. **Ai sinh:** Signaling.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | `0193…a1` | **Sợi chỉ xuyên suốt**: mọi bảng khác đều có `call_id` để nối lại với nhau |
| `caller_hash`, `callee_hash` | Ai gọi ai | | Signaling biết **ai** là người nghe, nhưng chưa chắc biết người đó **đang ở đâu** |
| `initiated_ts` | Lúc bấm gọi | | Mốc thời gian 0 của cuộc gọi |
| `media_kind` | Gọi thoại hay video | `audio` | Video cần băng thông lớn hơn nhiều |
| `scenario_tag` | Thuộc kịch bản nào trong 10 kịch bản (chỉ có trên sim) | `S02_vn_cross_region` | Lọc nhanh dashboard theo từng kịch bản bắt buộc |

**Vì sao cần bảng riêng chỉ để "khai sinh"?** Nếu cuộc gọi chết ngay sau khi bấm (app crash, Selector sập), sẽ **không có bảng nào khác** ghi gì cả. Không có `call_session` thì cuộc gọi đó biến mất khỏi thống kê, và hệ thống trông tốt hơn thực tế.

### 8.2 `selector_decision`: thuật toán đã quyết định gì, và vì sao

**Trả lời câu hỏi:** "Thuật toán đề xuất 4 TURN nào, theo thứ tự nào, dựa trên thông tin gì, chắc chắn đến đâu?"
**Khi nào:** mỗi lần gọi Selector. **Ai sinh:** bên gọi Selector (Signaling hoặc simulator), **không phải bản thân Selector** (xem §12).
**Một dòng = một (lần quyết định, một bên).** Hai bên dùng chung một `decision_id`.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `decision_id` | Mã của lần quyết định | `0193…d1` | Một cuộc gọi có thể được quyết định 2–3 lần |
| `call_id` | Thuộc cuộc gọi nào | | |
| `side` | Danh sách này cho bên nào | `caller` | Khi gọi mù, lúc đầu chỉ có danh sách cho người gọi |
| `phase` | Quyết định lúc nào | `initial` | So sánh: quyết định lúc mù với quyết định sau khi biết đủ, chênh nhau bao nhiêu? |
| `request_ts`, `response_ts` | Lúc hỏi và lúc được trả lời | | `response_ts = null` nghĩa là Selector không trả lời |
| `api_latency_ms` | Selector trả lời mất bao lâu | `18` | KPI **Service Health: API Latency** |
| `policy_version` | Thuật toán nào, phiên bản nào | `geo_baseline@0.1`, `smart@0.3.1` | Để **so sánh Geo Baseline với Smart Selector**, yêu cầu chính của đề bài |
| `decision_mode` | Dùng thật hay chạy bóng | `live` | Xem §5 |
| `decision_source` | Từ API, danh sách mặc định, hay cache | `api` | Xem §5. KPI **Fallback Rate** |
| `info_level` | Lúc đó biết bao nhiêu thông tin | `caller_only` | Xem §5 |
| `self_ctx` | Bối cảnh của bên được chọn TURN | `{VN, south, viettel, 4g}` | Đầu vào chính của thuật toán |
| `peer_ctx` | Bối cảnh của **bên kia**, theo những gì biết được lúc đó | `{unknown…}` | Ghi lại **đúng những gì thuật toán biết**, không phải sự thật về sau. Không vậy thì không đánh giá công bằng được |
| `k` | Trả về bao nhiêu TURN | `4` | Đề bài ghi 8, mentor nói 4, nên để thành tham số |
| `candidates` | Danh sách TURN đã xếp hạng (§8.2.1) | | Trái tim của quyết định |
| `filtered_out` | TURN bị **loại** trước khi xếp hạng, kèm lý do | `[{SGN-FPT-02, overloaded}]` | Kịch bản **TURN Failure**: chứng minh thuật toán đã né TURN lỗi |
| `chosen_rank` | Thuật toán yêu cầu thử hạng mấy trước | `1` (hoặc 3 khi explore) | Thường là 1. Khi exploration thì có thể là 2–4 |
| `is_exploration` | Đây có phải lần "thử nghiệm có chủ đích" không | `false` | Tách cuộc gọi thử nghiệm ra khi tính KPI, nếu cần |
| `exploration_epsilon` | Tỉ lệ thử nghiệm đang bật | `0.02` | Biết thí nghiệm đang chạy ở mức nào |
| `confidence`, `confidence_level` | Thuật toán chắc chắn tới đâu (0–1, và high/medium/low) | `0.62`, `medium` | Đề bài yêu cầu cơ chế **confidence**. Dashboard kiểm tra: lúc thuật toán nói "chắc chắn" thì có thật sự tốt hơn không? |
| `fallback_reason` | Thuật toán phải "lùi" vì thiếu dữ liệu | `no_history_backoff_country` | Kịch bản **Cold-start**: biết thuật toán đã phải đoán ở cấp thô |
| `feature_snapshot_id`, `health_snapshot_id` | Thuật toán đã đọc bản dữ liệu nào | `feat-20261111-r1` | Bảo đảm thuật toán **không nhìn thấy tương lai**. Khi điều tra một quyết định tệ, biết lúc đó nó nhìn thấy gì |
| `error_code` | Lỗi nếu có | | |

#### 8.2.1 `Candidate`: một TURN trong danh sách

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `rank` | Thứ hạng, từ 1 tới k | `1` | |
| `turn_id` | TURN nào | `VN-SGN-VTL-01` | |
| `score` | Điểm. **Càng cao càng tốt**, thang đo do Đoàn định | `0.91` | Xếp hạng. Điểm sát nhau thì thuật toán đang lưỡng lự |
| `score_components` | Điểm thành phần | `{geo:.9, isp:1, health:.95, history:.8}` | **Decision Trace**: giải thích *vì sao* TURN này đứng đầu. Đề bài yêu cầu giải thích scoring |
| `est_leg_ms` | Ước lượng độ trễ từ user tới TURN này | `9.5` | Sau cuộc gọi, so ước lượng với thực tế để biết thuật toán dự đoán chuẩn tới đâu |
| `est_path_ms` | Ước lượng cả đường (khi đã biết bên kia) | `26` | Như trên, cho cả đường |
| `reason_codes` | Lý do ngắn gọn | `[same_isp, same_region]` | Lọc nhanh trên dashboard: "những quyết định dựa trên same_isp có tốt không?" |
| `propensity` | **Xác suất** TURN này được chọn để đi | `1.0` / `0.0` (bình thường), `0.98` / `0.0067` (có explore) | **Field quan trọng nhất cho việc đánh giá.** Xem bên dưới |

**Vì sao `propensity` quan trọng như vậy?**
Giả sử 98% cuộc gọi đi hạng 1, chỉ 2% được thử hạng 3. Muốn biết "nếu mọi cuộc gọi đều đi hạng 3 thì sao", mình phải **cân lại**: mỗi cuộc gọi hiếm hoi đi hạng 3 phải "đại diện" cho nhiều cuộc gọi. Mức đại diện = 1 / xác suất. Đây là phương pháp IPS / Doubly Robust. **Không ghi propensity thì không cân lại được**, và mọi đánh giá về "đường chưa đi" đều chỉ là đoán.

### 8.3 `turn_allocation`: xin chỗ trên TURN

**Trả lời câu hỏi:** "Xin chỗ trên TURN này có được không, mất bao lâu?"
**Khi nào:** ngay sau khi có danh sách. **Ai sinh:** SDK trên điện thoại.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id`, `decision_id`, `side` | Thuộc cuộc gọi nào, quyết định nào, bên nào | | Nối với quyết định để biết "TURN hạng mấy" |
| `turn_id`, `rank` | TURN nào, đang ở hạng mấy | `VN-SGN-VTL-01`, `1` | Thống kê: TURN hạng 1 có hay lỗi hơn hạng 2 không? |
| `transport` | Đi bằng giao thức gì | `udp` | Xem §5 |
| `request_ts` | Lúc gửi yêu cầu | | |
| `alloc_ms` | Mất bao lâu mới được cấp | `38` | Gần đúng bằng **RTT từ user tới TURN**: một số đo chặng miễn phí |
| `success` | Có được cấp không | `true` | KPI **Allocation Success** |
| `error_code` | Lỗi gì | `capacity_508` | Biết TURN lỗi vì hết chỗ hay vì mạng |
| `is_preallocation` | Xin trước để dự phòng hoặc đo, không nhất thiết sẽ dùng | `true` | Ý tưởng "xin cả 4 TURN" (spec §5.1). Phải đánh dấu để không lẫn với lần xin để dùng thật |
| `released_ts`, `release_reason` | Lúc trả chỗ, vì sao trả | `not_needed` | Biết chi phí tài nguyên của việc xin trước |

### 8.4 `ice_attempt`: mỗi lần thử nối

**Trả lời câu hỏi:** "Đã thử nối bằng đường nào, có thành công không, **thực tế dùng TURN nào**?"
**Khi nào:** mỗi lần ICE chạy: lần đầu, mỗi lần dự phòng, mỗi lần nối lại. **Ai sinh:** SDK.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `attempt_seq` | Lần thử thứ mấy | `1`, `2` | Lần 2 trở đi nghĩa là có trục trặc |
| `trigger` | Vì sao phải thử | `fallback` | Phân biệt "hạng 1 lỗi" với "user đổi mạng" |
| `decision_id` | Dùng danh sách nào để thử | | Khi nối lại có thể dùng quyết định mới |
| `network_epoch` | "Giai đoạn mạng" thứ mấy. Mỗi lần đổi Wi-Fi↔4G thì +1 | `0`, `1` | Kịch bản **Network Change**: tách số liệu lúc dùng Wi-Fi khỏi lúc dùng 4G trong **cùng một cuộc gọi** |
| `start_ts`, `end_ts` | Bắt đầu và kết thúc lần thử | | |
| `state` | Kết quả | `connected` | KPI **Connection Success** |
| `turn_used` | Có dùng TURN không | `true` | `false` = nối thẳng. Những cuộc gọi này không tính vào thành tích của TURN |
| `path_type` | Kiểu đường | `relay_relay` | Xem §5 |
| `relay_turn_caller`, `relay_turn_callee` | TURN mà **thực tế đã dùng** | `VN-SGN-VTL-01` | So với danh sách thuật toán đề xuất. Đây là yêu cầu **"TURN được xếp hạng so với TURN ICE thực sự dùng"** |
| `rank_caller`, `rank_callee` | TURN thực dùng đứng hạng mấy trong danh sách | `1`, `3` | Thường xuyên phải dùng hạng 3 là dấu hiệu **thuật toán xếp sai thứ tự** |
| `transport` | Giao thức thực dùng | `tls` | |
| `cst_ms` | Từ lúc bắt máy tới lúc nghe được nhau | `412` | KPI **CST** |
| `ttfm_ms` | Từ lúc nối xong tới gói âm thanh đầu tiên | `95` | KPI **TTFM** |
| `failure_reason` | Vì sao thất bại | | Phân tích các trường hợp kết nối kém |

### 8.5 `path_leg_measurement`: số đo từng chặng (bảng trung tâm)

**Trả lời câu hỏi:** "Đoạn đường từ X tới Y, vào lúc này, trễ bao nhiêu, mất bao nhiêu gói?"
**Khi nào:** mỗi 5 giây trong cuộc gọi, lúc xin chỗ TURN, khi TURN ping nhau, khi điện thoại đo lúc rảnh.
**Một dòng = một chặng, theo một chiều, trong một khoảng đo.**

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `measured_ts` | Thời điểm đo, tính ở cuối khoảng đo | | Phân tích theo giờ |
| `window_s` | Khoảng đo dài bao lâu | `5` (đo liên tục) / `0` (đo một lần) | Số đo 5 giây đáng tin hơn số đo một gói tin |
| `method` | Đo bằng cách nào | `inband` | **Mỗi cách đo có độ lệch khác nhau.** Đo lúc đang gọi phản ánh đúng trải nghiệm, nhưng chỉ có ở đường đã đi (bị lệch theo thuật toán). TURN tự ping nhau thì đều và không lệch, nhưng chỉ cho chặng giữa |
| `call_id` | Thuộc cuộc gọi nào | `C1` hoặc `null` | `null` với số đo **không thuộc cuộc gọi nào** (probe). Đây là chỗ dạng bảng này mạnh hơn dạng "3 cột" |
| `attempt_seq`, `network_epoch` | Lần thử nào, giai đoạn mạng nào | | Đổi mạng thì số đo phải tách riêng |
| `leg_type` | Chặng có người hay chặng giữa hai TURN | `user_turn` | |
| `side` | Với chặng có người: người gọi hay người nghe | `caller` | |
| `direction` | Chiều đi | `forward` | Mạng không đối xứng |
| `src_id`, `dst_id` | Từ đâu tới đâu, **đúng theo chiều gói tin đi** | `user 9f2c…` → `VN-SGN-VTL-01` | |
| `user_segment_key` | Nhóm của user lúc đo | `VN\|south\|7552\|4g` | Gộp số đo của **nhiều người cùng nhóm** để thống kê |
| `network_type` | Loại mạng lúc đo | `4g` | |
| `one_way_ms` | Độ trễ một chiều trung bình trong khoảng đo | `9.1` | Số đo chính |
| `one_way_ms_max` | Độ trễ cao nhất trong khoảng đo | `21` | Thấy được các "cú giật" mà trung bình che đi |
| `one_way_estimated` | Số này là đo thật, hay chỉ là RTT chia đôi | `false` | Muốn đo một chiều thật thì đồng hồ hai đầu phải khớp nhau. Không khớp thì chỉ ước lượng được, nên phải đánh dấu |
| `clock_sync_err_ms` | Sai số đồng hồ ước tính | `0.4` | Sai số lớn thì số đo một chiều kém tin cậy |
| `loss_pct`, `jitter_ms` | Mất gói, độ giật | `0.0`, `1.2` | |
| `packets` | Số gói trong khoảng đo | `250` | 3 gói thì loss 33% có thể chỉ là ngẫu nhiên. Cần biết cỡ mẫu |
| `missing_reason` | Vì sao thiếu số đo | `no_packets` | Thay cho việc điền 0 (§3) |

**Vì sao đây là bảng trung tâm?**
Hệ thống chỉ đo được đường đã đi. Muốn biết đường **chưa ai đi** (ví dụ DAD×DAD) tốt hay xấu, cách duy nhất là **ghép các chặng đã đo ở những cuộc gọi khác**. Chặng "Viettel miền Nam → DAD" có thể đã được đo trong 1.000 cuộc gọi khác. Chặng "VNPT Hà Nội → DAD" có trong 800 cuộc gọi khác. Ghép lại là ra ước lượng. Muốn ghép được thì mỗi chặng phải là một dòng riêng, có nhãn nhóm user. Đây cũng là cách paper **Via** (Microsoft, SIGCOMM 2016) làm cho Skype.

### 8.6 `call_stats_5s`: chất lượng nhìn từ phía điện thoại

**Trả lời câu hỏi:** "Người dùng thực sự cảm thấy cuộc gọi thế nào, từng 5 giây một?"
**Ai sinh:** SDK, theo chuẩn W3C getStats (chuẩn chung của mọi trình duyệt và WebRTC).

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id`, `side`, `t_offset_s` | Cuộc gọi nào, bên nào, giây thứ mấy | `C1`, `caller`, `35` | |
| `network_epoch`, `network_type` | Giai đoạn mạng | `0`, `4g` | |
| `rtt_ms` | Độ trễ đi-về **đầu-cuối** | `51` | KPI **RTT** |
| `jitter_ms`, `loss_pct` | | | KPI **Jitter**, **Packet Loss** |
| `bitrate_send_kbps`, `bitrate_recv_kbps` | Tốc độ gửi và nhận | `32` | Bitrate tụt là dấu hiệu mạng nghẽn |
| `conn_state` | Trạng thái kết nối lúc đó | `connected` | Thấy được những khoảnh khắc "rớt rồi tự nối lại" |

**Đã có `path_leg_measurement` rồi, sao còn cần bảng này?**
1. Đây là **góc nhìn của người dùng**. Đề bài đòi các KPI Call Quality theo chuẩn này.
2. Nó dùng để **kiểm tra chéo**: tổng 3 chặng phải xấp xỉ RTT/2 đầu-cuối. Lệch nhiều nghĩa là một trong hai nguồn đo sai (bất biến I9).

### 8.7 `call_outcome`: kết cục cuộc gọi

**Trả lời câu hỏi:** "Cuộc gọi kết thúc ra sao?"
**Khi nào:** lúc kết thúc. **Ai sinh:** SDK hoặc Signaling.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `answered` | Người nghe có bắt máy không | `true` | **Không bắt máy không phải lỗi kỹ thuật.** Phải loại ra khi tính tỉ lệ lỗi |
| `answer_ts`, `connected_ts`, `end_ts` | Các mốc thời gian | | Tính CST, thời lượng |
| `connected` | Có nối được không | `true` | KPI **Connection Success** = nối được / **đã bắt máy** |
| `duration_s` | Gọi được bao lâu | `184` | Cuộc gọi quá ngắn sau khi nối có thể là dấu hiệu chất lượng tệ (người dùng bỏ cuộc) |
| `end_reason` | Vì sao kết thúc | `normal_hangup` | Xem §5 |
| `dropped` | Bị rớt bất thường **sau khi** đã nối | `false` | KPI **Drop Rate**. Chưa nối được mà kết thúc thì không gọi là "rớt" |
| `caller_ctx_final`, `callee_ctx_final` | Bối cảnh **thật** của hai bên, biết được sau cùng | | So với `peer_ctx` lúc quyết định thì đo được **"cái giá của gọi mù"**: nếu biết trước người nghe ở Hà Nội thì đã chọn khác thế nào |
| `pair_group` | VN-VN, VN-Quốc tế, hay Quốc tế-Quốc tế | `VN_VN` | 3 nhóm đề bài yêu cầu |
| `n_ice_attempts`, `n_network_changes` | Số lần thử nối, số lần đổi mạng | `1`, `0` | Đánh giá độ ổn định |
| `stats_sampled` | Cuộc gọi này có lưu đủ `call_stats_5s` không | `false` | Simulator chỉ lưu đầy đủ 10% để tiết kiệm dung lượng. Phải biết để không tưởng nhầm là thiếu dữ liệu |

**Vì sao không có MOS, P95, PNR trong bảng này?** Đó là những con số **tính ra**, không phải **đo được**. Nếu mỗi phiên bản app tự tính rồi gửi lên, mỗi bản tính một kiểu và không so sánh được. Pipeline tính chúng ở **một chỗ duy nhất** (`fact_call`), dùng một công thức.

---

## 9. Bảng sự kiện về hạ tầng

### 9.1 `turn_health_1m`: sức khỏe từng TURN, mỗi phút

**Vì sao theo phút mà không theo cuộc gọi?** TURN quá tải là chuyện của **cả server trong một khoảng thời gian**, không thuộc riêng một cuộc gọi nào.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `minute_ts`, `turn_id` | Phút nào, TURN nào | | |
| `active_allocations` | Đang phục vụ bao nhiêu chỗ | `4100` | KPI **Usage** |
| `utilization_pct` | % công suất đang dùng | `82` | Trên 80% thường bắt đầu chậm. Đây cũng là chỗ phát hiện **thuật toán dồn hết người vào một TURN** |
| `cpu_pct`, `bandwidth_mbps` | CPU, băng thông | | Nguyên nhân gốc của chậm |
| `alloc_attempts`, `alloc_failures` | Số lần xin chỗ, số lần lỗi trong phút | | Phát hiện lỗi nhanh hơn chờ tổng hợp từng cuộc gọi |
| `health_status`, `health_score` | Đánh giá tổng thể | `degraded`, `0.6` | Đầu vào cho **health filtering** của thuật toán |

### 9.2 `service_health_1m`: sức khỏe dịch vụ Selector, mỗi phút

| Field | Nghĩa | Vì sao cần (KPI Service Health của đề bài) |
|---|---|---|
| `minute_ts`, `service`, `instance` | Phút nào, dịch vụ nào, máy nào | |
| `req_count`, `error_count`, `timeout_count` | Số yêu cầu, số lỗi, số lần quá hạn | **Availability**, **Error Rate** |
| `p50_ms`, `p95_ms`, `p99_ms` | Thời gian trả lời | **API Latency** |
| `static_fallback_count` | Số lần điện thoại phải dùng danh sách mặc định vì Selector không trả lời | **Fallback Rate** (lỗi hạ tầng) |
| `algo_fallback_count` | Số lần thuật toán phải "lùi" vì thiếu dữ liệu | **Fallback Rate** (thiếu dữ liệu). Hai loại fallback này có nguyên nhân khác nhau nên tách ra |
| `feature_snapshot_age_s` | Dữ liệu thuật toán đang dùng đã cũ bao lâu | **Data Freshness**. Pipeline chết thì con số này tăng dần, báo động sớm |

---

## 10. Mười hai bất biến: "luật" dữ liệu phải tuân theo

Pipeline tự kiểm tra các luật này mỗi ngày. Vi phạm thì ghi vào `dq_results` và hiện trên trang Data Quality. Đây là cách thực hiện yêu cầu *"bảo đảm tính nhất quán giữa Selection, Allocation, ICE và Call Outcome"*.

| ID | Luật (nói đơn giản) | Nếu vi phạm thì thường là do |
|---|---|---|
| I1 | Mọi sự kiện đều thuộc về một cuộc gọi có "giấy khai sinh" | Mất event `call_session`, hoặc `call_id` bị ghi sai |
| I2 | Cuộc gọi nào cũng có kết cục, trong vòng 72 giờ | App crash, mất mạng trước khi gửi kết cục. Gọi là **orphan** |
| I3 | Danh sách có đúng k TURN, hạng liên tục 1..k, không trùng TURN, tổng xác suất = 1 | Lỗi code thuật toán |
| I4 | TURN thực dùng phải nằm trong danh sách được đề xuất | Client tự ý dùng TURN khác, hoặc lỗi tra hostname |
| I5 | Thứ tự thời gian hợp lý: gọi → quyết định → xin chỗ → nối → kết thúc | **Đồng hồ điện thoại sai** |
| I6 | Không bắt máy thì không thể "đã nối" | Lỗi logic ở SDK |
| I7 | "Rớt" chỉ có khi đã từng nối | Lỗi gán nhãn |
| I8 | "Cùng TURN" khi và chỉ khi hai bên dùng cùng một TURN | Lỗi gán nhãn |
| I9 | Tổng 3 chặng ≈ RTT đầu-cuối / 2 | Một trong hai nguồn đo sai, hoặc sai đơn vị |
| I10 | Số liệu nằm trong khoảng hợp lý (trễ 0–5000 ms, loss 0–100%…) | Sai đơn vị (giây và ms), counter âm |
| I11 | Mỗi sự kiện chỉ có một bản | Gửi lại do mạng chập chờn |
| I12 | Thuật toán chỉ dùng dữ liệu của quá khứ | Lỗi pipeline hoặc backtest làm rò dữ liệu tương lai |

---

## 11. Feature store: dữ liệu đã "nấu chín" cho thuật toán

**Ai sinh:** pipeline của Hiệp, mỗi ngày một lần. **Ai đọc:** thuật toán của Đoàn, dashboard.
**Vì sao Hiệp nấu mà không để Đoàn tự tính từ dữ liệu thô?** Để **dashboard và thuật toán nhìn cùng một con số**. Nếu mỗi người tự tính, dashboard nói "TURN X tốt" còn thuật toán lại thấy "TURN X tệ", rất khó điều tra.

### 11.0 Nhóm user và cơ chế "lùi cấp"

```
Cấp 4: VN | south | 7552 | 4g     (Viettel miền Nam dùng 4G)  ← chi tiết nhất
Cấp 3: VN | south | 7552          (Viettel miền Nam)
Cấp 2: VN | south                 (miền Nam)
Cấp 1: VN                         (Việt Nam)
Cấp 0: *                          (toàn bộ)                    ← thô nhất
```

**Vì sao?** Nhóm càng chi tiết thì càng sát thực tế, nhưng càng ít dữ liệu. "Viettel 4G ở Cần Thơ" có thể chỉ có 5 cuộc gọi, quá ít để tin. Khi đó thuật toán **lùi lên cấp cha** cho tới khi đủ dữ liệu (mặc định ≥ 30 mẫu), và ghi lại đã phải lùi tới đâu. Đây là lời giải cho kịch bản **Cold-start**: nước hoặc nhà mạng mới không có dữ liệu thì dùng số liệu của khu vực.

### 11.1 `feat_leg_stats`: thống kê chặng user ↔ TURN

| Field | Nghĩa | Vì sao cần |
|---|---|---|
| `snapshot_id`, `as_of_ts` | Bản dữ liệu nào, tính tới thời điểm nào | Thuật toán chỉ được đọc bản có `as_of_ts` trước lúc quyết định |
| `segment_level`, `segment_key` | Nhóm user, cấp mấy | Xem §11.0 |
| `turn_id`, `direction` | TURN nào, chiều nào | |
| `hour_bucket` | Giờ trong ngày (giờ VN) hoặc `all` | 21h tối khác 3h sáng. Có giờ thì thuật toán né được giờ cao điểm |
| `n_raw` | Số lần đo thật | |
| `n_eff` | Số mẫu "hiệu dụng" sau khi giảm trọng số dữ liệu cũ | Dữ liệu 3 tuần trước kém tin hơn hôm qua. Mỗi 7 ngày, trọng số giảm một nửa |
| `one_way_p50`, `one_way_p95` | Độ trễ điển hình và độ trễ ở phần đuôi xấu | P95 cho biết "những lúc tệ thì tệ tới đâu" |
| `loss_mean`, `jitter_p95` | | |
| `alloc_success_rate` + `ci_low`, `ci_high` | Tỉ lệ xin chỗ thành công, kèm **khoảng tin cậy** | 3/3 thành công (100%) khác hẳn 3000/3000 (100%). Khoảng tin cậy cho thấy cái đầu **chưa chắc**: thật ra có thể chỉ khoảng 44–100% |
| `one_way_p50_shrunk` | Con số đã được "kéo về" mức trung bình của cấp cha | Nhóm ít mẫu hay cho số cực đoan do ngẫu nhiên. Kéo về trung bình giúp tránh tin nhầm. Đây là kỹ thuật shrinkage |
| `source_mix` | Tỷ lệ số liệu đến từ mỗi cách đo | `{inband: 0.7, alloc: 0.3}`. Nếu 90% là probe thì số này chưa phản ánh người dùng thật |
| `last_observed_ts` | Lần cuối có dữ liệu | Lâu không có dữ liệu là **vùng mù**, nên ưu tiên thử nghiệm ở đó |

### 11.2 `feat_turn_turn`: thống kê chặng giữa hai TURN

Các field tương tự 11.1, thay nhóm user bằng `src_turn` → `dst_turn`.
**Vì sao cần:** cuộc gọi quốc tế (Nhật ↔ Đức) có chặng giữa chiếm phần lớn độ trễ. Đề bài yêu cầu *"tối ưu kết hợp hai đầu, không chỉ chọn TURN gần nhất cho từng user"*. Muốn vậy thì phải biết độ trễ giữa các cặp TURN.

### 11.3 `feat_turn_health`: sức khỏe TURN theo ngày

| Field | Vì sao cần |
|---|---|
| `health_status`, `health_score` | Lọc TURN tệ |
| `utilization_p95_24h` | TURN hay bị đầy giờ cao điểm thì nên hạ hạng |
| `alloc_success_24h`, `alloc_success_ci_low` | |
| `incidents_detected_7d` | TURN hay gặp sự cố thì kém tin cậy |
| `stability_cv_24h` | Độ dao động. TURN lúc nhanh lúc chậm còn tệ hơn TURN chậm đều. KPI **Stability** |

### 11.4 `feat_path_history`: lịch sử theo cả đường

Thống kê theo bộ (nhóm người gọi, nhóm người nghe, TURN bên gọi, TURN bên nghe): số cuộc gọi, tỉ lệ thành công, tỉ lệ rớt, PNR, MOS, độ trễ đầu-cuối.
**Vì sao cần:** đây là **Historical Connection** mà đề bài yêu cầu. Có những thứ chỉ thấy được ở mức cả đường, ví dụ một cặp TURN cụ thể hay rớt do lỗi tương thích.

### 11.5 `feat_callee_prior`: người nghe thường ở đâu

Ví dụ: "người gọi ở miền Nam thì 62% người nghe ở miền Nam, 25% miền Bắc, 8% Singapore…"
**Vì sao cần:** khi **gọi mù**, thuật toán dùng phân phối này để chọn TURN **tốt nhất xét trên trung bình** các khả năng. Bảng chỉ chứa **số đếm**, không có ai gọi ai, nên an toàn về riêng tư.

---

## 12. API Selector: cách hỏi và nhận câu trả lời từ thuật toán

### 12.1 Câu hỏi (`SelectRequest`)

| Field | Nghĩa | Vì sao cần |
|---|---|---|
| `call_id` | Cuộc gọi nào | |
| `phase` | Hỏi lúc nào: đầu cuộc gọi, sau bắt máy, hay nối lại | |
| `request_ts` | Lúc hỏi | Thuật toán dùng để chọn đúng snapshot và đúng khung giờ |
| `caller_ctx`, `callee_ctx` | Bối cảnh hai bên | `callee_ctx = null` khi gọi mù |
| `info_level` | Biết bao nhiêu | |
| `k` | Muốn bao nhiêu TURN | |
| `exploration_epsilon` | Tỉ lệ thử nghiệm | **Bên gọi quyết định** tỉ lệ này. Nhờ vậy simulator chạy được các thí nghiệm 0%, 2%, 5% mà Đoàn không phải sửa code |
| `exclude_turns` | TURN không được trả lại | Khi dự phòng: TURN vừa lỗi thì đừng đề xuất lại |

### 12.2 Câu trả lời (`SelectResponse`)

Gồm `decision_id`, `policy_version`, danh sách cho `caller` và `callee` (mỗi bên có `candidates`, `filtered_out`, `chosen_rank`, `is_exploration`), cùng `confidence`, `fallback_reason`, `feature_snapshot_id`, `health_snapshot_id`. Ý nghĩa giống như ở §8.2.

### 12.3 Vì sao Selector **không tự ghi** log quyết định?

Nếu Selector tự ghi thì **lúc Selector sập sẽ không có bản ghi nào**, đúng vào lúc cần dữ liệu nhất. Bên gọi Selector (Signaling hoặc simulator) luôn biết mình đã hỏi gì, nhận được gì hay không nhận được gì, và mất bao lâu. Vì vậy bên gọi mới là bên ghi, kể cả trường hợp lỗi (`decision_source = static_fallback`).

### 12.4 Vì sao có hai dạng (hàm Python và HTTP)?

- **Hàm Python** để simulator gọi khoảng 600.000 lần một cách nhanh chóng. HTTP sẽ chậm hơn rất nhiều.
- **HTTP** (`POST /v1/turn/select`) để demo, và sau này cho Spring Boot của công ty gọi.

Cả hai **cùng nội dung**, nên đổi qua lại không phải sửa logic.

---

## 13. Bảng ẩn: "đáp án" chỉ simulator có

| Bảng | Chứa gì | Dùng để chấm cái gì |
|---|---|---|
| `truth_leg_5m` | Độ trễ, mất gói **thật** của mọi chặng, kể cả đường chưa ai đi | Ước lượng đường chưa đi có đúng không? Thuật toán cách lựa chọn tối ưu bao xa (regret thật)? |
| `incident_truth` | Sự cố nào, ở đâu, lúc nào, nặng bao nhiêu | Dashboard có **phát hiện đúng** sự cố không, sau bao lâu, có báo động nhầm không? |
| `dirt_log` | Những lỗi dữ liệu nào đã được cố tình tiêm vào | Pipeline có **bắt được** lỗi không (mục tiêu ≥ 95%)? |

**Vì sao phải giấu kỹ?** Nếu dashboard hoặc thuật toán "nhìn trộm" được đáp án:
- Insight trở thành "biết trước rồi mới tìm", nên không còn giá trị.
- Thuật toán học từ đáp án, cho kết quả đẹp giả.

Vì vậy ba bảng này nằm ở thư mục riêng, chỉ module chấm điểm (`eval/`) được đọc, có test tự động cấm import. File sự cố do script sinh ngẫu nhiên, và Hiệp **không mở** cho tới khi viết xong insight.

---

## 14. Đi qua một cuộc gọi từ đầu tới cuối

**Kịch bản 2:** A ở **TP.HCM, Viettel, 4G** gọi B ở **Hà Nội, VNPT, Wi-Fi**.

| Thời điểm | Chuyện gì xảy ra | Bảng được ghi | Field đáng chú ý |
|---|---|---|---|
| 13:00:00.000 | A bấm gọi | `call_session` | `call_id = C1`, `scenario_tag = S02` |
| 13:00:00.020 | Hỏi Selector. Chưa biết B ở đâu | `selector_decision` (caller) | `phase = initial`, `info_level = caller_only`, `peer_ctx` toàn `unknown`, 4 TURN: SGN-VTL-01 (p = 1.0), SGN-FPT-01, DAD-VTL-01, SG-SIN-01 |
| 13:00:00.100 | Điện thoại A xin chỗ trên TURN hạng 1 | `turn_allocation` | `alloc_ms = 38`, `success = true` |
| 13:00:04.000 | B bắt máy, giờ đã biết B ở Hà Nội | | |
| 13:00:04.030 | Hỏi Selector cho phía B | `selector_decision` (callee) | `phase = refined`, `info_level = full`, hạng 1 là HAN-VNP-01 |
| 13:00:04.090 | Điện thoại B xin chỗ | `turn_allocation` | |
| 13:00:04.412 | ICE nối xong | `ice_attempt` | `relay_relay`, SGN-VTL-01 × HAN-VNP-01, hạng 1 × 1, `cst_ms = 412` |
| Mỗi 5 giây | Đo 3 chặng | `path_leg_measurement` ×3 | A→SGN 9.1 ms (4G) · SGN→HAN 13.8 ms · HAN→B 2.3 ms |
| Mỗi 5 giây | Đo đầu-cuối | `call_stats_5s` | `rtt_ms = 51` ≈ 2 × (9.1 + 13.8 + 2.3) = 50.4, nên luật I9 thỏa |
| 13:03:08 | Cúp máy | `call_outcome` | `connected`, 184 giây, `normal_hangup`, `VN_VN` |

**Sau đó, đêm hôm đó, pipeline của Hiệp:**
1. Gom các mảnh trên thành **một dòng** trong `fact_call`, tính MOS và PNR.
2. Cộng 36 số đo mới vào `feat_leg_stats` cho nhóm "Viettel miền Nam 4G → SGN-VTL-01".
3. Xuất bản snapshot mới. **Sáng hôm sau** thuật toán của Đoàn đọc snapshot này, và vòng lặp khép kín.

**Còn đường DAD×DAD mà chưa ai đi thì sao?** Pipeline ghép số đo chặng "Viettel miền Nam → DAD" từ các cuộc gọi khác với chặng "VNPT Hà Nội → DAD" để ước lượng. Nhờ vậy dashboard trả lời được câu hỏi "lẽ ra đi đường khác có tốt hơn không".

---

## 15. Câu hỏi thường gặp: "Sao không làm cách khác?"

**Sao không gộp hết vào một bảng `calls` cho dễ?**
Ngoài đời không hệ thống nào biết hết mọi thứ cùng lúc để ghi ra một dòng. Signaling biết lúc bấm gọi, điện thoại biết lúc nối, TURN biết tải. Gộp chung còn làm **mất dấu các bước bị đứt**: có quyết định nhưng không có kết cục sẽ biến thành vài ô trống, không ai để ý. Bảng một dòng mỗi cuộc gọi **vẫn có** (`fact_call`), nhưng do pipeline ráp lại sau.

**Sao số đo chặng không lưu thành 3 cột `leg1`, `leg2`, `leg3`?**
Vì có những số đo **không thuộc cuộc gọi nào** (TURN tự ping nhau, điện thoại đo lúc rảnh), và vì phải **ghép chặng giữa các cuộc gọi khác nhau** để ước lượng đường chưa đi. Dạng 3 cột không làm được cả hai việc này.

**Sao phải tách `answered` và `connected`?**
Người ta không bắt máy vì đang bận, không phải vì TURN tệ. Gộp chung thì tỉ lệ lỗi bị thổi phồng, và có thể đổ oan cho TURN của vùng có nhiều người hay bỏ lỡ cuộc gọi.

**Sao cần cả `event_ts` lẫn `ingest_ts`?**
Đồng hồ điện thoại có thể sai vài giây tới vài phút, và sự kiện có thể tới trễ vài giờ khi người dùng mất mạng. Chỉ có một mốc thời gian thì không phát hiện được cả hai chuyện này.

**Sao không điền 0 cho số đo bị thiếu? Như vậy dễ tính hơn mà.**
Vì 0 ms và 0% loss là **kết quả hoàn hảo**. Cuộc gọi lỗi không đo được bị điền 0 sẽ làm TURN tệ trông như TURN tốt nhất.

**Sao phải lưu `propensity`? Thuật toán luôn chọn hạng 1 thì cần gì xác suất?**
Hiện tại đúng là luôn chọn hạng 1, tức xác suất bằng 1. Nhưng khi bật thử nghiệm (exploration) để có dữ liệu cho đường chưa đi, xác suất là thứ **duy nhất** cho phép sửa độ lệch trong đánh giá. Thêm cột này về sau sẽ rất tốn công, vì dữ liệu cũ không có.

**Sao thuật toán chỉ được đọc dữ liệu "tới hết hôm qua"?**
Để mô phỏng đúng thực tế: ngoài đời không ai biết trước tương lai. Nếu lúc thử nghiệm thuật toán vô tình đọc được dữ liệu của chính ngày đang đánh giá, kết quả sẽ đẹp giả. Ra production thì không bao giờ đạt được mức đó.

**Sao TURN dùng mã IATA thành phố mà không ghi tên tỉnh?**
Mã ngắn, chuẩn quốc tế, không bị lỗi dấu tiếng Việt, và dùng được cho cả TURN quốc tế.

**Contract nhiều bảng như vậy có quá nặng cho 6 tuần không?**
Simulator sinh tất cả bảng **từ cùng một mô hình**, nên thêm bảng không tốn nhiều công. Đổi lại, mỗi bảng ứng với đúng một hệ thống ngoài đời, nên lúc pilot ở công ty chỉ cần nối từng nguồn vào đúng bảng của nó.

---

## 16. Bảng tra nhanh: yêu cầu đề bài → lấy từ đâu

| Yêu cầu | Bảng · field |
|---|---|
| TURN VN theo miền / ISP / TURN Server / Network / thời gian | `ctx.vn_region`, `ctx.isp`/`asn`, `turn_id`, `ctx.network_type`, `event_ts` |
| TURN quốc tế theo Country / Region / TURN Location | `ctx.country`, `dim_turn.country`/`city` |
| User ở nước có và không có TURN | `ctx.country` so với danh sách `dim_turn.country` |
| VN↔VN, VN↔Quốc tế, Quốc tế↔Quốc tế | `call_outcome.pair_group` |
| Allocation Success | `turn_allocation.success` |
| Latency P50/P95 | `path_leg_measurement.one_way_ms` (tính trong pipeline) |
| Failure Rate, Connection Success | `call_outcome.answered`, `connected` |
| Stability, Health, Usage | `turn_health_1m`, `feat_turn_health.stability_cv_24h` |
| TURN được xếp hạng so với TURN ICE thực dùng | `selector_decision.candidates` so với `ice_attempt.relay_turn_*`, `rank_*` |
| Geo Baseline so với Historical / Smart | `selector_decision.policy_version` |
| Availability, API Latency, Error, Fallback, Freshness | `service_health_1m` |
| CST, TTFM | `ice_attempt.cst_ms`, `ttfm_ms` |
| RTT, Packet Loss, Jitter | `call_stats_5s` |
| Drop Rate | `call_outcome.dropped` |
| Decision Trace theo Call ID | Mọi bảng sự kiện, nối qua `call_id` |
| TURN Failure | `selector_decision.filtered_out`, `turn_health_1m`, `ice_attempt.trigger = fallback` |
| Cold-start | `feat_*.segment_level`, `n_eff`, `selector_decision.fallback_reason` |
| Network Change | `ice_attempt.network_epoch`, `trigger = restart_network_change` |
| Phân biệt dữ liệu thật và giả lập | `data_source` |
| Confidence | `selector_decision.confidence` |
