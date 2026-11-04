# Giải thích Data Contract v0.2.0 — từng bảng, từng field, vì sao chọn như vậy

> **Tài liệu này dành cho ai?** Cho mọi người: Đoàn, mentor, người mới vào dự án, kể cả người chưa từng làm WebRTC.
> **Quan hệ với contract:** `data-contract.md` (v0.2.0) là bản **chuẩn** (luật). Tài liệu này là bản **giải thích** (vì sao có luật đó). Nếu hai bản khác nhau, **`data-contract.md` thắng**.
> **Phiên bản cũ:** v0.1.0 đã bị thay hoàn toàn. Mọi định nghĩa của v0.1 không còn trong contract coi như đã hủy. Chỗ nào tài liệu này nhắc tới thứ cũ thì sẽ ghi rõ là "đã bỏ".

**Cách đọc:**
- Người mới: đọc §1 → §2 → §3 (hai loại dữ liệu) → §22 (đi qua một cuộc gọi), các phần còn lại tra khi cần.
- Người viết code: đọc §4–§19 theo bảng mình đụng tới (bất biến ở §14).
- Người làm đánh giá, KPI: đọc §20 (KPI) và §21 (đánh giá).
- Muốn biết "sao không làm cách khác": đọc §23. Cần tra yêu cầu → field: §24.

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

- Mỗi đoạn mũi tên là một **chặng (leg)**. Độ trễ một chiều của cả đường ≈ tổng độ trễ 3 chặng **theo cùng chiều đó**.
- Nếu A và B dùng **cùng một TURN** thì chặng 2 không tồn tại (bằng 0).
- Chọn TURN gần nhưng mạng tệ, hoặc xa nhưng nằm cùng nhà mạng, cho ra kết quả rất khác nhau. Vì vậy cần **thuật toán chọn TURN**, phần việc của Đoàn.

### 1.2 Thuật toán làm gì, và vì sao khó đánh giá?

- Thuật toán xếp hạng **4 TURN cho mỗi bên**. Cuộc gọi đi bằng **TURN hạng 1 của A × TURN hạng 1 của B**. Hạng 2–4 là dự phòng khi hạng 1 lỗi.
- Hệ thống **chỉ đo được con đường đã đi**. Những con đường khác không có số liệu, nên không biết chắc thuật toán đã chọn đúng hay chưa. Đây là bài toán **selection bias** (lệch do chính việc lựa chọn), và là lý do contract có nhiều field đặc biệt như `propensity`, `granularity`, `measurement_kind`.
- Có thêm một khó khăn: các nhánh thuật toán **dùng chung** các TURN. Nhánh này dồn người vào một TURN thì TURN đó chậm lại, ảnh hưởng cả nhánh kia. Vì vậy cách so sánh thuật toán (§21) phải được thiết kế riêng, không thể chỉ "chia cuộc gọi ngẫu nhiên làm hai nhóm".

### 1.3 Từ điển nhỏ

| Thuật ngữ | Nghĩa dễ hiểu |
|---|---|
| **TURN / relay** | Máy chủ trung gian chuyển tiếp âm thanh và hình ảnh giữa hai người |
| **Allocation** | Thao tác "xin một chỗ" trên TURN trước khi dùng, giống đặt bàn trước ở nhà hàng |
| **ICE** | Quy trình tự động trong WebRTC để thử các đường nối và chọn đường dùng được |
| **ICE candidate** | Một "địa chỉ ứng viên" để nối: `host` (địa chỉ trong mạng nội bộ), `srflx` (địa chỉ công khai qua NAT), `prflx` (học được trong lúc kiểm tra), `relay` (địa chỉ trên TURN) |
| **ICE restart** | Chạy lại ICE giữa cuộc gọi, ví dụ khi đổi Wi-Fi sang 4G. Mỗi lần restart tăng `ice_generation` |
| **P2P** | Hai bên nối thẳng với nhau, không qua TURN |
| **Signaling** | Máy chủ điều phối cuộc gọi: ai gọi ai, đổ chuông, bắt máy. Ở công ty là backend Spring Boot |
| **Selector** | Dịch vụ chọn TURN (thuật toán của Đoàn) |
| **ISP / ASN** | Nhà mạng (Viettel, VNPT, FPT…). ASN là "mã số" của nhà mạng trên Internet, ví dụ Viettel = 7552 |
| **Latency một chiều (one-way)** | Thời gian để gói tin đi **một chiều** từ điểm X tới Y, tính bằng ms. Đo trực tiếp cần hai đồng hồ khớp nhau |
| **RTT** | Round-trip time: thời gian **đi và về**, đo được chỉ bằng một đồng hồ. **Không** tự động bằng 2 lần one-way (xem I9 ở §14) |
| **RTCP** | Kênh "báo cáo" đi kèm luồng âm thanh. Từ báo cáo của bên nhận, bên gửi tính được RTT của chính luồng media |
| **Packet loss** | % gói tin bị mất dọc đường |
| **Jitter** | Độ "giật" của độ trễ: gói này tới nhanh, gói kia tới chậm. Jitter cao thì tiếng bị rè hoặc đứt quãng |
| **Histogram** | Bảng đếm "có bao nhiêu cửa sổ rơi vào từng khoảng giá trị" thay vì một con số trung bình |
| **P50 / P95** | P50 là trung vị (một nửa tốt hơn mức này). P95: 95% tốt hơn mức này, thể hiện **phần đuôi xấu** |
| **PCR** | Poor Call Rate: tỉ lệ cuộc gọi bị xếp là "tệ" (định nghĩa ở §20). **Metric chính** của dự án |
| **ITT** | Intention-to-treat: tính trên **mọi cuộc gọi đã được gán nhánh**, kể cả cuộc gọi sau đó trục trặc ở đâu đó. Không loại bớt sau khi đã biết kết quả |
| **Cohort** | Tập cuộc gọi được đưa vào mẫu số của một KPI |
| **CST** | Call Setup Time: thời gian thiết lập kỹ thuật. Contract dùng `cst_technical` = từ lúc ICE bắt đầu kiểm tra tới lúc ICE nối xong |
| **TTFM** | Time To First Media: từ lúc bắt máy tới khi nhận được gói âm thanh đầu tiên |
| **MOS** | Điểm chất lượng cảm nhận, thang 1–5 (chỉ để chẩn đoán) |
| **Exploration** | Cố ý cho một phần nhỏ cuộc gọi đi TURN hạng 2–4 để thu thêm dữ liệu |
| **Propensity** | Xác suất thuật toán chọn một phương án. Dùng để "cân lại" dữ liệu bị lệch |
| **Snapshot** | Bản chụp dữ liệu thống kê tại một thời điểm. Thuật toán chỉ được đọc snapshot của quá khứ |
| **Segment** | Một nhóm user có chung đặc điểm, ví dụ "Viettel miền Nam dùng 4G" |
| **Arm (nhánh)** | Cuộc gọi thuộc thuật toán nào trong một thí nghiệm (Geo, Historical, Smart) |
| **Seed** | Số khởi tạo của bộ sinh ngẫu nhiên. Cùng seed thì mô phỏng ra cùng thế giới |
| **MDE / power** | Hiệu ứng nhỏ nhất ta muốn phát hiện được / xác suất phát hiện được nó nếu nó có thật |
| **Non-inferiority** | Kiểm tra "không tệ hơn quá một biên cho phép", dùng cho các guardrail |

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

### 2.2 Các nhóm bảng

| Nhóm | Bảng | Đặc điểm |
|---|---|---|
| **Danh mục** (dimension) | `dim_turn`, `dim_asn`, `dim_user` | Ít thay đổi. Mô tả "ai, cái gì" |
| **Sự kiện** (event) | `call_session`, `selector_decision`, `turn_allocation`, `ice_attempt`, `ice_candidate_pair` (tùy chọn), `path_leg_measurement`, `call_stats_epoch`, `call_stats_5s`, `call_outcome`, `turn_health_1m`, `service_health_1m` | Chỉ ghi thêm, không sửa. Mô tả "chuyện gì đã xảy ra, lúc nào" |
| **Run manifest** | `run_manifest` | Một file JSON mô tả mỗi lần chạy simulator / mỗi experiment, commit cùng kết quả |
| **Feature store** | `feat_*` | Pipeline tính từ sự kiện. Thuật toán đọc |
| **Ẩn** (chỉ simulator) | `truth_leg_5m`, `incident_truth`, `dirt_log` | "Đáp án", chỉ dùng để chấm điểm |

Sơ đồ quan hệ (rút gọn): một `call_session` có nhiều `selector_decision`; mỗi decision có nhiều `turn_allocation`; một call có nhiều `ice_attempt`, nhiều `path_leg_measurement`, nhiều `call_stats_epoch`; và đúng một `call_outcome`. Số đo `path_leg_measurement` từ probe thì không thuộc call nào (`call_id = null`).

---

## 3. Hai loại dữ liệu: KPI-grade và diagnostic (phần quan trọng nhất của v0.2)

Vấn đề của v0.1: mọi số đo chất lượng nằm trong `call_stats_5s`, mà bảng này chỉ lưu một phần cuộc gọi. Nếu phần được lưu không đại diện cho toàn bộ (ví dụ cuộc gọi lỗi được lưu nhiều hơn), KPI sẽ **lệch mà không ai biết**. v0.2 chia dữ liệu làm hai loại:

| Loại | Bảng | Độ phủ | Được dùng cho |
|---|---|---|---|
| **KPI-grade** | `call_session`, `selector_decision`, `turn_allocation`, `ice_attempt`, `call_outcome`, `call_stats_epoch`, `path_leg_measurement` với `granularity = epoch_summary`, `turn_health_1m`, `service_health_1m` | **100% cuộc gọi** | Mọi KPI chính và guardrail (§20), feature store (§17) |
| **Diagnostic** | `call_stats_5s`, `path_leg_measurement` với `granularity = window_5s`, `ice_candidate_pair` | Lấy mẫu (§13.3) hoặc tùy telemetry | Điều tra, Decision Trace, biểu đồ chi tiết. **Không bao giờ** dùng cho KPI quyết định |

**Vì sao?** Muốn kết luận "Smart tốt hơn Geo" thì mẫu số và tử số phải đếm trên **mọi** cuộc gọi, không phải trên phần may mắn được lưu chi tiết. Dữ liệu chi tiết vẫn có giá trị để *hiểu vì sao* một cuộc gọi tệ, nhưng không được dùng để *phán* thuật toán. Quy tắc này được kiểm tra tự động (bất biến I16): file `contracts/kpi.yaml` khai báo mỗi KPI đọc bảng nào, test sẽ báo lỗi nếu KPI đọc bảng diagnostic.

---

## 4. Quy ước chung và lý do

| Quy ước | Cụ thể | Vì sao |
|---|---|---|
| **Giờ UTC** | `2026-11-12T13:45:01.123Z` | Server ở nhiều nước. Dùng giờ địa phương thì 2 sự kiện cùng lúc ở VN và Đức bị lệch 6 tiếng. Cần giờ VN để phân tích "giờ cao điểm" thì dùng cột phái sinh `local_hour_vn` (UTC+7) |
| **Chính xác tới ms** | `.123` | CST và TTFM chỉ vài trăm ms. Làm tròn tới giây thì không đo được |
| **Partition theo ngày `dt`** | `raw/call_outcome/dt=2026-11-12/` | Pipeline chạy theo ngày (`dt` = ngày UTC của `event_ts`). Chạy lại một ngày chỉ cần ghi đè thư mục ngày đó |
| **ID dạng UUIDv7** | `0193a4…` | Cho `event_id`, `decision_id`, `allocation_id`, `call_id`. Duy nhất toàn cầu, máy nào cũng tự sinh được mà không trùng. v7 còn **sắp xếp được theo thời gian**. `call_id` do Signaling cấp |
| **Đơn vị cố định** | thời gian/độ trễ ms · loss % (0–100) · jitter ms · bitrate kbps · tỉ lệ 0–1 | Chuẩn W3C trả RTT và jitter bằng **giây**. Không chốt đơn vị thì một nguồn nhân sai ×1000 là dashboard sai theo mà không ai biết |
| **Mã quốc gia ISO, mã thành phố IATA** | `VN`, `HAN`, `SGN` | Chuẩn quốc tế, ngắn, tránh `Vietnam` / `Viet Nam` / `VN` lẫn lộn |
| **Vùng VN** | `north`, `central`, `south`; `null` = không áp dụng | |
| **`unknown` khác `null`** | `"unknown"` = không biết; `null` = không áp dụng hoặc chưa có số đo | User ở Nhật thì "miền Bắc/Trung/Nam" là **không áp dụng** (`null`). User VN mà không xác định được miền là **không biết** (`unknown`). Gộp chung thì không đo được dữ liệu thiếu bao nhiêu. Khi `null` vì thiếu số đo, kèm `*_missing_reason` |
| **Không điền 0 / trung bình khi thiếu số đo** | Để `null` và ghi lý do | Cuộc gọi lỗi mà ghi loss = 0% thì TURN tệ trông lại hoàn hảo. Đây là lỗi nguy hiểm nhất vì **sai mà không báo** |
| **Mã hóa user** | `user_hash` = 16 ký tự hex đầu của HMAC-SHA256(user_id, salt) | Bảo vệ danh tính. Không lưu IP thô, vị trí chỉ tới cấp thành phố |
| **Hash tất định** | Mọi quy tắc dựa trên hash dùng SHA-256 trên chuỗi UTF-8, lấy 8 byte đầu, big-endian, unsigned. Cấm dùng `hash()` có sẵn của ngôn ngữ | `hash()` của Python đổi kết quả theo lần chạy, của Java khác Python. Quy tắc lấy mẫu mà không tái lập được thì không kiểm tra được (I17) |
| **Tên cột tiếng Anh, snake_case** | `alloc_ms` | Java, Python và SQL đều đọc thuận |

---

## 5. Các cột có ở mọi bảng sự kiện

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `event_id` | Mã duy nhất của **một** sự kiện | `0193…e7` | Mạng chập chờn khiến điện thoại gửi lại cùng một sự kiện 2 lần. Có mã thì pipeline **loại được bản trùng** (I11) |
| `contract_version` | Dòng này theo phiên bản contract nào | `0.2.0` | Khi contract nâng cấp, pipeline biết dòng cũ hay mới để đọc cho đúng |
| `data_source` | Dữ liệu từ đâu ra: `synthetic`, `lab_zenodo`, `public_reference`, `production` | `synthetic` | Đề bài **cấm** dùng kết quả giả lập để khẳng định production tốt hơn. Cột này giữ ranh giới đó |
| `producer` | Hệ thống nào sinh ra: `client_sdk`, `signaling`, `selector`, `turn_server`, `probe_agent`, `simulator` | `client_sdk` | Đồng hồ của mỗi hệ thống tin cậy khác nhau. Gặp lỗi thì biết hỏi ai |
| `event_ts` | Lúc sự kiện **xảy ra**, theo đồng hồ của nơi sinh. **Bất biến: pipeline không bao giờ ghi đè** | `13:00:04.412Z` | Mọi tính toán theo thời gian dựa vào đây. Nếu đồng hồ sai thì pipeline ghi bản sửa ở cột khác (§16.1), giữ nguyên bản gốc |
| `ingest_ts` | Lúc hệ thống thu thập **nhận được** ("thời điểm hệ thống biết") | `13:00:05.020Z` | Biết sự kiện đến trễ bao lâu, đồng hồ có sai không, và quan trọng nhất là xác định **hệ thống đã biết điều gì tại thời điểm nào** (I13) |
| `sim_run_id` | Lần chạy simulator nào. Bắt buộc khi `data_source = synthetic`, trỏ tới `run_manifest` | `run-20261112-s42` | Không có cột này thì dữ liệu các lần chạy trộn vào nhau, và dữ liệu giả không truy được về cấu hình sinh ra nó |
| `dt` | Ngày của sự kiện | `2026-11-12` | Chia thư mục theo ngày |

---

## 6. Danh sách giá trị (enum) và ý nghĩa

| Enum | Giá trị → nghĩa | Vì sao chia như vậy |
|---|---|---|
| `side` | `caller` = người gọi, `callee` = người nghe | Hai bên có mạng, vị trí và TURN khác nhau |
| `network_type` | `wifi`, `4g`, `5g`, `ethernet`, `unknown` | Đề bài yêu cầu phân tích theo Network Type |
| `media_kind` | `audio`, `video` | KPI chất lượng chỉ tính trên audio |
| `info_level` | `full` = biết cả hai bên; `caller_only`; `country_only` = biết bên kia ở nước nào; `none` | Lúc bấm gọi thường chưa biết người nghe ở đâu (gọi mù). Tách được "quyết định khi thiếu thông tin" ra để đánh giá riêng |
| `decision_phase` | `initial` = lúc bấm gọi; `refined` = sau khi biết thêm; `restart` = chọn lại giữa chừng | Một cuộc gọi có thể được quyết định nhiều lần |
| `decision_mode` | `live` = dùng thật; `shadow` = chạy bóng, chỉ ghi lại | Khi pilot, thuật toán mới thường chạy "bóng" trước |
| `decision_source` | `api`; `static_fallback` = Selector lỗi nên dùng danh sách mặc định; `cache` | Phải biết cuộc gọi đó **không** do thuật toán quyết định, không thì đổ lỗi oan |
| `connection_mode` | `post_answer` = ICE bắt đầu **sau khi bắt máy** (mặc định, **giả định chưa xác minh**); `pre_connect` = ICE chạy ngay lúc đổ chuông | Hai chế độ làm thay đổi thứ tự sự kiện, tải TURN và cả định nghĩa "đã connected mà chưa bắt máy". Chưa chắc công ty dùng kiểu nào nên phải ghi rõ và kiểm tra cả hai (§21.5) |
| `transport` | `udp`, `tcp`, `tls` | Một số mạng chặn UDP nên phải đi TCP hoặc TLS, vốn chậm hơn |
| `leg_type` | `user_turn` = chặng người ↔ TURN; `turn_turn` = chặng giữa hai TURN | Hai loại có bản chất khác nhau |
| `direction` | `forward` = theo chiều caller→callee; `reverse` = ngược lại | Mạng không đối xứng: upload 4G thường kém hơn download |
| `measure_method` | `inband` = đo trong lúc gọi; `mesh_probe` = các TURN ping nhau; `idle_probe` = điện thoại đo lúc rảnh. **Không còn `alloc`** (lý do ở §10.3) | Mỗi cách đo có độ lệch khác nhau |
| `measurement_kind` | `one_way` = đo trực tiếp một chiều (cần đồng bộ đồng hồ); `rtt` = đo đi-về | Trộn hai loại vào một cột số mà không ghi loại thì cột số vô nghĩa |
| `measurement_point` | `client`, `turn_server`, `probe_agent` | Ai đứng ra đo |
| `granularity` | `epoch_summary` = một dòng tóm tắt cho cả epoch (100% cuộc gọi); `window_5s` = từng cửa sổ 5 giây (chỉ cuộc gọi được lấy mẫu) | Tách dữ liệu KPI-grade khỏi diagnostic (§3) |
| `path_type` | `relay_relay` = hai bên dùng 2 TURN khác nhau; `relay_same` = cùng 1 TURN; `relay_direct` = một bên relay, một bên nối thẳng; `p2p_host` / `p2p_srflx` = nối thẳng hoàn toàn; `unknown`. **Suy ra từ cặp candidate được chọn** | Cuộc gọi nối thẳng không dùng TURN. v0.1 ngầm giả định mọi cuộc gọi là relay, v0.2 thì suy từ dữ liệu thật |
| `candidate_type` | `host`, `srflx`, `prflx`, `relay`, `unknown` | Là đầu vào để suy `path_type` |
| `ice_trigger` | `initial`; `fallback` = hạng 1 lỗi nên thử hạng sau; `restart_network_change`; `restart_failure` | Phục vụ kịch bản TURN Failure và Network Change |
| `ice_state` | `connected`, `failed`, `timeout`, `cancelled` | `cancelled` (người dùng tắt giữa chừng) không phải lỗi kỹ thuật |
| `end_reason` | `normal_hangup`; `invite_undelivered` = lời mời không tới được máy B; `not_answered`; `rejected`; `cancelled_by_caller`; `ice_failed`; `dropped_network`; `dropped_turn`; `app_crash`; `unknown` | Tách lý do **xã hội** (không bắt máy) khỏi lý do **kỹ thuật** (không nối được). `invite_undelivered` là mới: lời mời chưa tới thì chưa thể nói người ta "không bắt máy" |
| `pair_group` | `VN_VN`, `VN_INTL`, `INTL_INTL` | Đúng 3 nhóm đề bài yêu cầu |
| `health_status` | `healthy`, `degraded`, `overloaded`, `down`, `maintenance` | Phân biệt bảo trì có kế hoạch với sập bất ngờ |
| `alloc_error` | `none`, `timeout`, `unauthorized_401`, `forbidden_403`, `quota_486`, `capacity_508`, `unreachable`, `other` | Mỗi lỗi có cách xử lý khác nhau. `none` là mới, dùng khi thành công |
| `stats_status` | `kept_critical`, `kept_sampled`, `not_sampled`, `truncated`, `lost`, `not_applicable` | Trạng thái của dữ liệu diagnostic của cuộc gọi (§13.3) |
| `quality_assessment_status` | `assessed`, `partially_assessed`, `unclassifiable`, `not_applicable` | Một cuộc gọi có đủ số đo để phân loại chất lượng không |
| `randomization_unit` | `run` (sim: cả môi trường), `call`, `user`, `region`, `time_block` | Đơn vị được gán nhánh một lúc (§21) |
| `run_kind` | `scripted`, `blind_benchmark`, `dev` | Loại lần chạy (§19.3) |

---

## 7. Bảng danh mục

### 7.1 `dim_turn`: danh sách TURN server

**Trả lời câu hỏi:** "TURN này ở đâu, của nhà mạng nào, chứa được bao nhiêu?"
**Ai sinh:** đội hạ tầng (trên sim là file cấu hình thế giới).

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `turn_id` | Mã TURN: `<nước>-<thành phố>-<nhà host>-<số>` | `VN-SGN-VTL-01` | Đọc mã là biết vị trí, không cần tra |
| `hostname` | Tên miền thật | `turn-sgn-01.vtl.example` | Điện thoại chỉ biết tên miền. Pipeline đổi ngược ra `turn_id` (§15.3) |
| `country`, `vn_region`, `city` | Nước, miền (chỉ TURN ở VN), thành phố | `VN`, `south`, `SGN` | Phân tích theo địa lý |
| `lat`, `lon` | Tọa độ | `10.82, 106.63` | Tính khoảng cách cho Geo Baseline, vẽ bản đồ |
| `host_isp`, `host_asn` | Nhà mạng đặt TURN | `viettel`, `7552` | "User Viettel dùng TURN của Viettel có tốt hơn không?" |
| `capacity_alloc` | Số chỗ tối đa đồng thời | `5000` | Tính % tải |
| `transports` | Giao thức hỗ trợ | `{udp,tcp,tls}` | TURN không hỗ trợ TLS thì vô dụng với user sau tường lửa chặt, và dùng để xác định tính *khả thi* theo sự thật (§21.6) |
| `status` | `active`, `maintenance`, `retired` | `active` | Cũng dùng cho tính khả thi |
| `valid_from`, `valid_to` | Thông tin này đúng trong khoảng thời gian nào (`valid_to = null` là còn hiệu lực) | | **Thêm dòng mới chứ không sửa dòng cũ** (SCD2), để phân tích lại tháng trước vẫn thấy đúng topology tháng trước |

### 7.2 `dim_asn`

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `asn` | Mã số nhà mạng (khóa chính) | `45899` | Từ IP suy ra ASN, cách xác định nhà mạng chính xác nhất |
| `isp` | Tên dễ đọc | `vnpt` | Hiển thị |
| `country` | Nước | `VN` | |
| `access_kind` | `fixed`, `mobile`, `mixed` | `mobile` | Cùng Viettel nhưng cáp quang và 4G khác nhau rất nhiều |

### 7.3 `dim_user` (đã ẩn danh)

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `user_hash` | Mã người dùng đã mã hóa (khóa chính) | `9f2c41ab…` | Đếm số người khác nhau mà không biết là ai |
| `home_country`, `home_vn_region`, `home_city` | Nơi **thường** ở | `VN`, `south`, `SGN` | Chỉ là nơi thường ở. Vị trí **lúc gọi** nằm trong `ctx` |
| `home_isp`, `home_asn` | Nhà mạng thường dùng | `viettel`, `7552` | |
| `primary_network` | Loại mạng hay dùng | `wifi` | Simulator dùng để sinh hành vi |
| `cohort` | `normal` hoặc `cold_start` | `cold_start` | Đánh dấu user cố ý cho ít dữ liệu, để kiểm tra Cold-start |
| `created_at` | Ngày tạo tài khoản | | User mới không có lịch sử |

---

## 8. Object `ctx`: "bối cảnh" của một bên tại lúc quyết định

**Vì sao tách thành object riêng?** Cùng một bộ thông tin xuất hiện ở nhiều chỗ: lúc ra quyết định (`self_ctx`, `peer_ctx`) và lúc kết thúc (`*_ctx_final`). Định nghĩa một lần, dùng lại nhiều nơi thì không bao giờ lệch. Khi lưu trong Postgres, object được làm phẳng với tiền tố `self_` / `peer_` / `caller_` / `callee_`.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `user_hash` | Ai | `9f2c…` hoặc `null` | `null` khi gọi mù |
| `country`, `vn_region`, `city` | Đang ở đâu **lúc này** | `VN`, `south`, `SGN` | Chọn TURN theo vị trí hiện tại, không theo nơi thường ở |
| `isp`, `asn` | Đang dùng nhà mạng nào | `viettel`, `7552` | Bắt Wi-Fi quán cà phê là FPT dù SIM là Viettel |
| `network_type` | Wi-Fi hay 4G… | `4g` | |
| `geo_source` | Vị trí lấy từ đâu: `ip_geo`, `sdk_claimed`, `both` | `both` | Vị trí suy từ IP có thể sai |
| `geo_mismatch` | App báo một nơi, IP chỉ nơi khác | `true` | Dấu hiệu **VPN** hoặc **roaming**; cần tách riêng |
| `segment_key` | Nhãn nhóm đã chuẩn hóa | `VN\|south\|7552\|4g` | Khóa tra feature store (§17) |

Field chưa biết ghi `unknown`.

---

## 9. Bảng sự kiện theo luồng cuộc gọi (phần 1: bắt đầu cuộc gọi)

### 9.1 `call_session`: "giấy khai sinh" của cuộc gọi, kiêm "phiếu gán nhánh"

**Trả lời câu hỏi:** "Cuộc gọi này có tồn tại không, ai gọi ai, lúc nào, thuộc thí nghiệm nào, nhánh nào?"
**Khi nào:** ngay khi A bấm gọi, **trước mọi quyết định của Selector**. **Ai sinh:** Signaling.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | `0193…a1` | **Sợi chỉ xuyên suốt**: mọi bảng đều có `call_id` |
| `caller_hash`, `callee_hash` | Ai gọi ai | | Signaling biết **ai** là người nghe, nhưng chưa chắc biết họ **đang ở đâu** |
| `initiated_ts` | Lúc bấm gọi | | Mốc 0 của cuộc gọi |
| `media_kind` | Thoại hay video | `audio` | |
| `connection_mode` | `post_answer` hay `pre_connect` | `post_answer` | Quyết định thứ tự sự kiện (I5, I6) và cách mô phỏng tải TURN. Không biết chế độ thì không biết "connected mà chưa bắt máy" là bình thường hay là lỗi dữ liệu |
| `experiment_id` | Thí nghiệm nào; `null` = không thuộc thí nghiệm | `exp-w4-geo-vs-smart` | Cuộc gọi trong thí nghiệm mới vào cohort của KPI chính |
| `arm` | Nhánh nào. Bắt buộc khi có `experiment_id`. Trên sim = tên policy của môi trường | `smart` | Biết cuộc gọi thuộc thuật toán nào **ngay từ đầu**, không suy ngược từ kết quả |
| `randomization_unit` | Đơn vị được gán ngẫu nhiên | `run` | Quyết định cách tính độ bất định (§21.3) |
| `experiment_cluster_id` | Cụm ngẫu nhiên hóa (region, time block…). Trên sim = `sim_run_id` | `run-20261112-s42` | Cuộc gọi trong cùng cụm không độc lập với nhau |
| `assignment_ts` | Lúc gán nhánh. **Phải ≤ `request_ts` của decision đầu tiên** (I15) | | Chứng minh việc gán nhánh có trước mọi quyết định, nên cohort không bị chọn lọc theo kết quả |
| `assignment_hash` | Hash dùng để gán nhánh | | Tái lập được việc gán nhánh |
| `scenario_tag` | Chỉ có trên sim. **Chỉ mô tả loại cuộc gọi** | `S02_vn_cross_region` | Lọc dashboard theo kịch bản. **Không bao giờ** mã hóa sự cố ẩn (§19.4), nếu không thuật toán đọc tag là biết đáp án |

**Vì sao `call_session` phải có trước mọi quyết định và chứa cả việc gán nhánh?** Nếu cuộc gọi chết ngay sau khi bấm (app crash, Selector sập), sẽ không có bảng nào khác ghi gì cả. Không có `call_session` thì cuộc gọi đó biến mất khỏi thống kê và hệ thống trông tốt hơn thực tế. Cũng vì thế cohort của KPI chính (§20.2) được định nghĩa là "mọi `call_session` đã được gán nhánh".

### 9.2 `selector_decision`: thuật toán đã quyết định gì, và vì sao

**Trả lời câu hỏi:** "Thuật toán đề xuất 4 TURN nào, theo thứ tự nào, dựa trên thông tin gì, chắc chắn đến đâu?"
**Khi nào:** mỗi lần gọi Selector. **Ai sinh:** bên gọi Selector (Signaling hoặc simulator), **không phải bản thân Selector** (§18.3).
**Một dòng = một (lần quyết định, một bên).** Hai bên dùng chung một `decision_id`.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `decision_id` | Mã của lần quyết định (UUIDv7) | `0193…d1` | Một cuộc gọi có thể được quyết định 2–3 lần |
| `call_id`, `side`, `phase` | Cuộc gọi nào, bên nào, giai đoạn nào | `caller`, `initial` | So sánh quyết định lúc mù với quyết định sau khi biết đủ |
| `request_ts` | Lúc hỏi | | Dùng để chọn đúng snapshot (I12) và kiểm tra thứ tự nhân quả (I5) |
| `response_ts`, `api_latency_ms` | Lúc được trả lời, mất bao lâu | `18` | `null` khi API không trả lời. KPI Service Health |
| `policy_version` | Thuật toán nào, phiên bản nào | `geo_baseline@0.1`, `smart@0.3.1`, `static@1` | So sánh Geo Baseline với Smart Selector |
| `decision_mode`, `decision_source`, `info_level` | Xem §6 | `live`, `api`, `caller_only` | |
| `self_ctx`, `peer_ctx` | Bối cảnh bên được chọn / bên kia | | `peer_ctx` ghi **đúng những gì thuật toán biết lúc đó**, không phải sự thật về sau |
| `k` | Số TURN trả về (mặc định 4) | `4` | Đề bài ghi 8, mentor nói 4, nên là tham số |
| `candidates` | Danh sách `k` TURN, sắp theo rank | | Trái tim của quyết định (§9.2.1) |
| `filtered_out` | TURN bị loại trước khi xếp hạng, kèm lý do: `down`, `overloaded`, `degraded`, `maintenance`, `policy` | `[{SGN-FPT-02, overloaded}]` | Chứng minh thuật toán đã né TURN lỗi |
| `chosen_rank` | Rank client được yêu cầu thử trước | `1` | Thường 1; khi exploration có thể 2–4 |
| `is_exploration`, `exploration_epsilon` | Có phải lần thử nghiệm có chủ đích; tỉ lệ đang bật | `false`, `0.02` | Tách cuộc gọi thử nghiệm khi cần |
| `confidence` (0–1), `confidence_level` (high/medium/low) | Thuật toán chắc chắn tới đâu | `0.62`, `medium` | Kiểm tra: lúc nói "chắc chắn" thì có thật tốt hơn không? |
| `fallback_reason` | Thuật toán phải "lùi" vì thiếu dữ liệu | `backoff_L1` | Biết đã phải đoán ở cấp thô nào |
| `feature_snapshot_id`, `health_snapshot_id` | Đã đọc snapshot nào. `null` chỉ khi `decision_source = static_fallback` | `feat-20261112-v1` | Bảo đảm không nhìn thấy tương lai (I12); điều tra được lúc đó thuật toán thấy gì |
| `error_code` | Lỗi nếu có | | |

#### 9.2.1 `Candidate`: một TURN trong danh sách

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `rank` | Thứ hạng 1..k | `1` | |
| `turn_id` | TURN nào | `VN-SGN-VTL-01` | |
| `score` | Điểm, **cao = tốt**, chỉ so trong một decision | `0.91` | Xếp hạng. Không so điểm giữa các decision khác nhau |
| `score_components` | Điểm thành phần | `{geo:.9, isp:1, health:.95, history:.8}` | **Decision Trace**: giải thích vì sao TURN này đứng đầu |
| `est_leg_ms`, `est_path_ms` | Ước lượng độ trễ chặng / cả đường (có thể `null`) | `9.5`, `26` | Sau cuộc gọi so ước lượng với thực tế để biết thuật toán dự đoán chuẩn tới đâu |
| `reason_codes` | Lý do ngắn | `[same_isp, same_region]` | Lọc nhanh trên dashboard |
| `propensity` | **Xác suất** candidate này là `chosen_rank`; tổng các candidate = 1 | `1.0`/`0.0`; hoặc `0.98`/`0.0067` khi explore | **Field quan trọng nhất cho đánh giá "đường chưa đi"** |

**Vì sao `propensity` quan trọng?** Giả sử 98% cuộc gọi đi hạng 1, chỉ 2% thử hạng 3. Muốn biết "nếu mọi cuộc gọi đều đi hạng 3 thì sao", phải **cân lại**: mỗi cuộc gọi hiếm hoi đi hạng 3 "đại diện" cho nhiều cuộc gọi, với mức đại diện = 1 / xác suất. Không ghi propensity thì không cân lại được.

### 9.3 `turn_allocation`: xin chỗ trên TURN

**Trả lời câu hỏi:** "Xin chỗ trên TURN này có được không, mất bao lâu?"
**Khi nào:** sau khi có danh sách. **Ai sinh:** SDK trên điện thoại. **Một dòng = một allocation.**

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `allocation_id` | Mã allocation (UUIDv7, **do client sinh**) | `0193…a7` | Là "dây buộc" để `ice_attempt` nói chính xác allocation nào đã được dùng (§16.3). Trước đây chỉ ghép được theo `turn_id`, dễ ghép nhầm |
| `call_id`, `decision_id`, `side` | Thuộc cuộc gọi, quyết định, bên nào | | Nối với quyết định để biết "TURN hạng mấy" |
| `turn_id`, `rank`, `transport` | TURN nào, hạng mấy, giao thức gì | `VN-SGN-VTL-01`, `1`, `udp` | Hạng 1 có hay lỗi hơn hạng 2 không? |
| `ice_generation` | Thế hệ ICE lúc tạo allocation (0, +1 mỗi ICE restart) | `0` | Allocation của thế hệ cũ không được gán cho attempt của thế hệ mới chỉ vì cùng `turn_id` |
| `attempt_seq` | Gắn với lần thử cụ thể nào; `null` nếu chưa gắn | `1` | |
| `is_preallocation` | Xin trước để dự phòng, chưa chắc dùng | `true` | Không lẫn với lần xin để dùng thật; để tính chi phí tài nguyên của xin trước |
| `request_ts` | Lúc gửi yêu cầu | | |
| `response_ts`, `alloc_ms` | Lúc có trả lời; thời gian cấp. `null` nếu timeout | `38` | Xem khung bên dưới |
| `success`, `error_code` | Có được cấp không; lỗi gì (enum `alloc_error`) | `true`, `none` | KPI Allocation Success |
| `released_ts`, `release_reason` | Lúc trả chỗ; lý do: `not_needed`, `call_end`, `kept_for_failover`, `expired`, `unanswered` | `not_needed` | Chi phí tài nguyên. `unanswered` nghĩa là giữ chỗ xong mà không ai bắt máy |

> **`alloc_ms` là gì, và không là gì?** `alloc_ms` là **allocation latency**: thời gian từ lúc gửi yêu cầu xin chỗ tới lúc có kết quả, **gồm cả vòng 401** (TURN yêu cầu xác thực, client gửi lại kèm thông tin xác thực) **và thời gian server xử lý**. Nó **không phải RTT, cũng không phải one-way** của chặng người↔TURN. Một lần xin chỗ có ít nhất hai vòng đi-về, cộng thêm xử lý ở server, nên con số lớn hơn RTT thật và không thể "chia đôi" để ra một chiều. v0.1 coi `alloc_ms` là "số đo chặng miễn phí" nên đã bỏ; nó có bảng thống kê riêng (§17.6).

### 9.4 `ice_attempt`: mỗi lần thử nối

**Trả lời câu hỏi:** "Đã thử nối bằng đường nào, mất bao lâu từng bước, có thành công không, **thực tế dùng TURN nào**?"
**Khi nào:** mỗi lần ICE chạy: lần đầu, mỗi lần dự phòng, mỗi lần restart. **Ai sinh:** SDK. Một dòng = một lần thử.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id`, `attempt_seq`, `ice_generation` | Cuộc gọi, lần thử thứ mấy, thế hệ ICE | `1`, `0` | Lần 2 trở đi là có trục trặc |
| `trigger` | Vì sao phải thử | `fallback` | Phân biệt "hạng 1 lỗi" với "user đổi mạng" |
| `decision_id` | Dùng danh sách nào | | Nối lại có thể dùng quyết định mới |
| `network_epoch` | "Giai đoạn mạng" thứ mấy, +1 mỗi lần đổi mạng | `0`, `1` | Tách số liệu Wi-Fi khỏi 4G trong cùng một cuộc gọi |
| `start_ts` | Bắt đầu ICE | | |
| `checks_start_ts` | Lúc ICE connectivity check **đầu tiên** (null được) | | Mốc đầu của `cst_technical` (§20.4). Dùng mốc "bắt đầu thật sự kiểm tra" thay vì "lúc bấm" để không tính thời gian chờ người bắt máy vào thời gian thiết lập kết nối |
| `ice_connected_ts` | ICE nối xong (null được) | | Mốc cuối của `cst_technical`; **mốc neo của cửa sổ 5 giây** (§11.1) |
| `dtls_connected_ts` | DTLS (bước mã hóa) xong, tùy telemetry | | Đủ chuỗi mốc để kiểm tra thứ tự nhân quả (I5f) |
| `end_ts` | Kết thúc lần thử | | |
| `state` | `connected`, `failed`, `timeout`, `cancelled` | `connected` | |
| `turn_used` | Có dùng TURN không; `null` khi thất bại | `true` | `false` = nối thẳng, không tính vào thành tích TURN |
| `selected_local_candidate_type`, `selected_remote_candidate_type` | Loại candidate của cặp được chọn (lấy từ cặp mà `transport.selectedCandidatePairId` trỏ tới) | `relay`, `relay` | **Nguồn gốc của `path_type`** |
| `path_type` | Kiểu đường, **suy ra từ hai field trên** | `relay_relay` | v0.1 mặc định relay_relay; v0.2 không giả định |
| `relay_turn_caller`, `relay_turn_callee` | TURN thực dùng (`null` nếu bên đó không đi relay) | `VN-SGN-VTL-01` | So với danh sách đề xuất |
| `caller_allocation_id`, `callee_allocation_id` | Allocation thực dùng. Thiếu thì pipeline dùng quy tắc §16.3 | | Ghép allocation ↔ ICE chính xác |
| `rank_caller`, `rank_callee` | Rank của TURN thực dùng trong decision | `1`, `3` | Thường xuyên phải dùng hạng 3 = dấu hiệu xếp sai thứ tự |
| `transport` | Giao thức thực dùng | `udp` | |
| `failure_reason` | Vì sao thất bại | | |

**Thay đổi so với v0.1:** `cst_ms` và `ttfm_ms` nằm sẵn trong bảng này đã bị bỏ. Thay vào đó lưu **các mốc thời gian** (`checks_start_ts`, `ice_connected_ts`, `dtls_connected_ts`) và tính CST/TTFM trong pipeline. Lưu mốc thì tính lại được theo nhiều định nghĩa; lưu sẵn kết quả thì kẹt với một định nghĩa.

### 9.5 `ice_candidate_pair` (tùy chọn, chẩn đoán)

**Trả lời câu hỏi:** "Trong lần ICE đó, đã thử những cặp địa chỉ nào, cặp nào thành công, cặp nào được chọn?"
**Khi nào có:** chỉ khi SDK/telemetry cung cấp. **Không** suy diễn bảng này từ `relay_turn_*`. Không có thì không có.

Field: `call_id`, `attempt_seq`, `ice_generation`, `pair_id`, `local_candidate_id`, `remote_candidate_id`, `local_candidate_type`, `remote_candidate_type`, `local_turn_id`, `remote_turn_id`, `pair_priority`, `check_state` (`waiting`, `in_progress`, `succeeded`, `failed`), `check_count`, `nominated`, `selected`, `current_rtt_ms`, `telemetry_support` (`full`/`partial`).

**Vì sao tùy chọn?** Không phải SDK nào cũng lấy được. Cho nó bắt buộc thì phải bịa dữ liệu. Nó phục vụ chẩn đoán, ví dụ KPI chẩn đoán `allocation_never_checked_rate` ("xin chỗ TURN nhưng ICE chưa từng kiểm tra cặp nào dùng TURN đó"), chỉ tính được khi có bảng này. Vì là diagnostic nên **không** vào KPI chính.

---

## 10. Bảng sự kiện theo luồng cuộc gọi (phần 2: đo đạc)

### 10.1 Hai cách nhìn một cuộc gọi tệ

Có hai nhóm bảng đo đạc, đừng nhầm:

| Nhóm | Bảng | Trả lời | Vai trò |
|---|---|---|---|
| **Góc nhìn người dùng** | `call_stats_epoch`, `call_stats_5s` | "Người dùng cảm thấy cuộc gọi thế nào?" | Dùng để **phân loại cuộc gọi tệ hay không** (nhãn PCR) |
| **Phân rã chặng** | `path_leg_measurement` | "Đoạn nào trong đường đi chậm?" | Dùng để **giải thích và dự đoán** (feature, chẩn đoán). **Không bao giờ làm nhãn PCR** |

### 10.2 Vì sao số đo chặng không được làm nhãn?

Nhãn cần phản ánh trải nghiệm thật của cả cuộc gọi. Số đo chặng là thứ thuật toán cố **dự đoán**; nếu dùng chính nó chấm điểm thì thuật toán "tự chấm bài mình". Ngoài ra phương pháp đo chặng ở production còn chưa xác minh (Q4 trong contract).

### 10.3 `path_leg_measurement`: phân rã chặng

**Trả lời câu hỏi:** "Đoạn đường từ X tới Y, vào lúc này, trễ bao nhiêu?"
**Khi nào:** tóm tắt mỗi epoch cho **mọi** cuộc gọi; từng cửa sổ 5 giây cho cuộc gọi được lấy mẫu; probe của TURN/điện thoại lúc rảnh.
**Một dòng = một chặng, một chiều, một khoảng đo.** Đường A→B = `user_turn(caller, forward)` + `turn_turn(TA→TB, forward)` + `user_turn(callee, forward)`. Khi `path_type = relay_same` không có dòng `turn_turn` (coi là 0).

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `granularity` | `epoch_summary` (một dòng cho mỗi call × epoch × leg × direction, **100% cuộc gọi**) hoặc `window_5s` (từng cửa sổ, **chỉ cuộc gọi được lấy mẫu**) | `epoch_summary` | Feature store và KPI chỉ đọc `epoch_summary` (I16) |
| `method` | `inband`, `mesh_probe`, `idle_probe`. **Không có `alloc`** | `inband` | Mỗi cách đo có độ lệch khác nhau. Đã bỏ `alloc` vì `alloc_ms` không phải số đo chặng (§9.3) |
| `measurement_kind` | `one_way` hoặc `rtt` | `one_way` | Cho phép lưu cả hai loại mà không lẫn |
| `measurement_point` | `client`, `turn_server`, `probe_agent` | `client` | Ai đo |
| `method_version` | Phiên bản phương pháp đo | `inband-1` | Đổi cách đo thì số liệu cũ/mới không trộn |
| `window_start_ts`, `window_end_ts` | Khoảng đo | | Phân tích theo giờ; kiểm tra I9 "cùng cửa sổ" |
| `call_id`, `attempt_seq`, `ice_generation`, `network_epoch` | Thuộc cuộc gọi, lần thử, thế hệ ICE, epoch nào. `null` với probe | | `call_id = null` cho số đo không thuộc cuộc gọi nào |
| `leg_type`, `direction` | Loại chặng, chiều | `user_turn`, `forward` | |
| `side` | Với `user_turn`: bên nào | `caller` | |
| `src_id`, `dst_id` | Từ đâu tới đâu, **đúng theo chiều gói tin** | `user 9f2c…` → `VN-SGN-VTL-01` | |
| `user_segment_key`, `network_type` | Nhóm user, loại mạng (với `user_turn`) | `VN\|south\|7552\|4g` | Gộp số đo của nhiều người cùng nhóm |
| `value_ms` | Giá trị **trung bình** trong cửa sổ/epoch, **đúng loại `measurement_kind`** | `9.1` | Thay cho `one_way_ms` của v0.1. Cột một tên nhưng hai nghĩa là nguy hiểm, nên nghĩa nằm ở `measurement_kind` |
| `value_ms_p95` | P95 trong epoch (chỉ với `epoch_summary`) | `14` | Thấy "cú giật" mà trung bình che đi |
| `n_samples` | Số mẫu | `36` | Cỡ mẫu |
| `clock_sync_err_ms` | Sai số đồng bộ đồng hồ. **Bắt buộc** khi `measurement_kind = one_way` | `0.8` | One-way mà không biết sai số đồng hồ thì không biết đáng tin tới đâu |
| `loss_pct`, `jitter_ms`, `packets` | Mất gói, độ giật, số gói | | 3 gói mà loss 33% có thể chỉ là ngẫu nhiên |
| `missing_reason` | Vì sao thiếu | `no_packets` | Thay cho điền 0 |

**Hai mức độ chi tiết (`granularity`):** nếu lưu từng cửa sổ 5 giây cho mọi cuộc gọi thì dung lượng rất lớn. Vì vậy mọi cuộc gọi chỉ lưu **bản tóm tắt theo epoch** (giá trị trung bình + P95), còn từng cửa sổ chỉ lưu cho cuộc gọi được lấy mẫu (§13.3). Feature store chỉ dùng bản tóm tắt nên không bị lệch theo việc lấy mẫu.

**Vì sao vẫn là bảng trung tâm của phần dự đoán?** Hệ thống chỉ đo được đường đã đi. Muốn biết đường **chưa ai đi** thì ghép các chặng đã đo ở các cuộc gọi khác ("Viettel miền Nam → DAD" từ 1.000 cuộc gọi, "VNPT Hà Nội → DAD" từ 800 cuộc gọi). Muốn ghép thì mỗi chặng phải là một dòng riêng có nhãn nhóm user (như paper Via của Microsoft).

### 10.4 `call_stats_epoch`: chất lượng nhìn từ điện thoại — **KPI-grade, 100% cuộc gọi**

**Trả lời câu hỏi:** "Với mỗi bên, trong mỗi giai đoạn mạng, bao nhiêu cửa sổ 5 giây có độ trễ/mất gói/jitter tệ?"
**Ai sinh:** SDK, **tính ngay trên thiết bị** từ W3C getStats rồi gửi khi epoch kết thúc. **Một dòng = (call, endpoint_side, media_kind, network_epoch).**

**Vì sao tính trên thiết bị và gửi dạng histogram?** Gửi từng cửa sổ 5 giây của mọi cuộc gọi quá nặng, mà lấy mẫu thì lệch KPI. Histogram nhỏ (vài chục số) mà vẫn cho phép đếm "bao nhiêu cửa sổ tệ", nên gửi được **100% cuộc gọi**.

**Cửa sổ 5 giây cố định:**
- Mốc neo `anchor_ts` = `ice_connected_ts` **đầu tiên** của cả cuộc gọi. Cửa sổ thứ *i* = [anchor + 5i, anchor + 5(i+1)).
- Neo **không** đặt lại sau ICE restart. Nhờ vậy cửa sổ của hai bên và của mọi epoch đều nằm trên cùng một lưới thời gian, ghép được với nhau. Nếu mỗi bên tự chọn mốc, hai bên sẽ lệch lưới và không so sánh được.
- Cửa sổ thuộc epoch nào chứa phần lớn thời gian của nó. Cửa sổ có khoảng gián đoạn media do restart → **không đánh giá được** (không tính là tốt, không tính là tệ).

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id`, `endpoint_side`, `media_kind`, `network_epoch` | Khóa. `endpoint_side` = endpoint báo cáo | `C1`, `caller`, `audio`, `0` | |
| `epoch_start_ts`, `epoch_end_ts` | Khoảng của epoch | | |
| `audio_active_duration_s` | Thời gian có media audio thực sự | `183.6` | Phân biệt "nối được" với "có tiếng thật" |
| `first_media_sent_ts`, `first_media_received_ts` | Gói media đầu tiên gửi/nhận tại endpoint này trong epoch này | | Tính `ttfm_post_answer` (§20.4); kiểm tra I5f |
| `packets_expected`, `packets_lost` | Gói dự kiến và gói mất, **luồng inbound** (luồng đi vào endpoint này) | | Loss do người nghe cảm nhận là loss của luồng họ nhận |
| `media_rtcp_rtt_hist` | Histogram **số cửa sổ** theo bucket `<100`, `100–200`, `200–300`, `300–400`, `≥400` ms. Là RTT của **luồng outbound** (luồng endpoint này gửi đi) lấy từ `remote-inbound-rtp.roundTripTime` theo SSRC | `{<100: 33, 100–200: 3}` | Metric RTT chính cho PCR |
| `loss_hist` | Bucket `<1`, `1–3`, `3–5`, `≥5` %. Loss inbound của cửa sổ = Δlost / Δexpected | | Metric loss chính |
| `jitter_estimate_hist` | Bucket `<10`, `10–30`, `30–50`, `≥50` ms; jitter estimate inbound (`inbound-rtp.jitter`) | | Metric jitter chính |
| `rtt_windows_assessable`, `loss_windows_assessable`, `jitter_windows_assessable` | Số cửa sổ có số đo hợp lệ, **riêng cho từng metric** | `34`, `36`, `36` | Mẫu số của PoorFraction. Riêng từng metric vì RTT cần báo cáo RTCP nên thiếu nhiều hơn loss |
| `valid_rtt_samples`, `valid_jitter_samples` | Số mẫu hợp lệ. RTT chỉ hợp lệ sau khi có báo cáo RTCP RR với DLSR ≠ 0 | | Chống tin vào số RTT khi chưa có báo cáo đầu tiên |
| `media_rtcp_rtt_p50`, `media_rtcp_rtt_p95` | Chẩn đoán | | |
| `ice_stun_rtt_p50`, `ice_stun_rtt_p95` | RTT của gói STUN check (`candidate-pair.currentRoundTripTime`). **Metric riêng, không thay cho media RTT** | | Xem khung bên dưới |
| `jitter_estimate_p95` | P95 của **các ước lượng jitter đã lấy mẫu**, không phải jitter của từng gói | | Tên nói rõ nó là P95 của *ước lượng* |
| `measurement_coverage` | Tỉ lệ cửa sổ đánh giá được / tổng số cửa sổ của epoch (0–1) | `0.97` | Biết số liệu đáng tin tới đâu |
| `quality_rule_version` | Phiên bản bộ bucket | | Đổi bucket thì dữ liệu cũ vẫn hiểu được |

> **`media_rtcp_rtt` khác `ice_stun_rtt` thế nào?**
> - `media_rtcp_rtt` đo RTT **của chính luồng âm thanh/hình** đi qua đường thật mà người dùng nghe, dựa trên báo cáo RTCP. Đây là cái người dùng cảm nhận, nên dùng để phân loại cuộc gọi.
> - `ice_stun_rtt` đo RTT của **gói kiểm tra STUN** của ICE trên cặp địa chỉ đã chọn. Gói này nhỏ, gửi thưa, đôi khi qua đường/hàng đợi khác, nên không đại diện cho độ trễ media. Chỉ dùng để chẩn đoán.
>
> **`jitter_estimate` nghĩa là gì?** Đây là giá trị jitter mà bộ đếm của WebRTC (`inbound-rtp.jitter`) báo ở thời điểm lấy mẫu, một ước lượng đã làm mượt, không phải độ lệch của từng gói. Vì thế contract gọi là "estimate" và P95 của nó là "P95 của các ước lượng đã lấy mẫu".

### 10.5 `call_stats_5s`: chi tiết từng cửa sổ — **diagnostic, lấy mẫu**

**Trả lời câu hỏi:** "Trong cuộc gọi cụ thể này, đúng lúc nào bị giật?"
Khóa: (`call_id`, `endpoint_side`, `media_kind`, `window_idx`). Field: `network_epoch`, `network_type`, `media_rtcp_rtt_ms`, `ice_stun_rtt_ms`, `jitter_estimate_ms`, `loss_pct`, `packets_expected`, `packets_lost`, `bitrate_send_kbps`, `bitrate_recv_kbps`, `conn_state`. Dùng **cùng quy tắc neo cửa sổ** như `call_stats_epoch`, nên một cửa sổ ở đây khớp đúng một cửa sổ trong histogram.

**Có `call_stats_epoch` rồi, sao còn cần bảng này?** Histogram chỉ cho biết *bao nhiêu* cửa sổ tệ, không cho biết *khi nào*. Để vẽ biểu đồ và điều tra Decision Trace cần từng cửa sổ. Nhưng bảng này chỉ có ở cuộc gọi được lấy mẫu nên **không dùng cho KPI quyết định**. Aggregate trên bảng này phải dùng trọng số Horvitz-Thompson (§13.3).

### 10.6 `call_outcome`: kết cục cuộc gọi

**Trả lời câu hỏi:** "Cuộc gọi kết thúc ra sao?"
**Khi nào:** lúc kết thúc. **Ai sinh:** SDK hoặc Signaling. Một dòng mỗi cuộc gọi.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id` | Khóa | | |
| `ring_ts` | Lúc máy B **nhận lời mời và đổ chuông**. `null` nếu `invite_undelivered` | `13:00:00.900` | Phân biệt "lời mời không tới" với "tới rồi mà không ai nghe". Rất khác nhau: cái đầu có thể là lỗi hạ tầng, cái sau là hành vi người dùng |
| `answer_ts` | Lúc **người dùng B bấm nghe** (sự kiện Signaling, **không phải** SDP Answer) | `13:00:04.000` | SDP Answer là bước kỹ thuật, có thể xảy ra trước khi người dùng bấm nghe (nhất là `pre_connect`). Mốc "bấm nghe" mới là mốc người dùng cảm nhận |
| `answered` | Có bắt máy không | `true` | Không bắt máy không phải lỗi kỹ thuật |
| `connected` | Có ít nhất một ICE attempt `connected` | `true` | Với `pre_connect`, có thể `connected = true` mà `answered = false` (I6) |
| `end_ts` | Kết thúc | | |
| `duration_s` | Từ `answer_ts` tới `end_ts` | `184` | Cuộc gọi quá ngắn sau khi nối có thể là dấu hiệu chất lượng tệ |
| `end_reason` | Xem §6 | `normal_hangup` | |
| `dropped` | Kết thúc bất thường **sau khi đã bắt máy và đã connected** | `false` | Chưa nối được mà kết thúc thì không gọi là "rớt" |
| `caller_ctx_final`, `callee_ctx_final` | Bối cảnh **thật**, join muộn | | So với `peer_ctx` lúc quyết định thì đo được "cái giá của gọi mù" |
| `pair_group` | VN_VN, VN_INTL, INTL_INTL | | |
| `n_ice_attempts`, `n_network_changes` | Số lần thử nối, số lần đổi mạng | `1`, `0` | Độ ổn định; cũng là điều kiện "critical" khi lấy mẫu |
| `stats_status` | Trạng thái dữ liệu **diagnostic** của cuộc gọi | `kept_sampled` | Phân biệt "không lưu có chủ đích" với "lưu rồi mà mất" |
| `stats_sampling_prob` | 1.0 / 0.1 / 0.0 | `0.1` | Trọng số để cân lại (`1/prob`) |
| `stats_sampling_reason` | `critical:<lý do>`, `hash_sample`, `not_selected` | `hash_sample` | Giải thích vì sao có/không có dữ liệu chi tiết |
| `sampling_rule_version` | Phiên bản quy tắc lấy mẫu | | I17 kiểm tra quy tắc này |

**Thay đổi so với v0.1:** `connected_ts` và cờ `stats_sampled` đã bỏ; `connected_ts` suy ra từ `ice_attempt.ice_connected_ts`. `call_outcome` cũng **không chứa aggregate** (MOS, P95, tỉ lệ…): đó là con số *tính ra*, không phải *đo được*. Nếu mỗi phiên bản app tự tính thì không so sánh được; pipeline tính ở một chỗ (`fact_call`, §16.4) bằng một công thức.

---

## 11. Bảng sự kiện về hạ tầng

### 11.1 `turn_health_1m`: sức khỏe từng TURN, mỗi phút (KPI-grade)

**Vì sao theo phút mà không theo cuộc gọi?** TURN quá tải là chuyện của cả server trong một khoảng thời gian. Khóa: (`turn_id`, `minute_ts`).

| Field | Nghĩa | Vì sao cần |
|---|---|---|
| `active_allocations` | Đang phục vụ bao nhiêu chỗ | KPI Usage |
| `utilization_pct` | % công suất đang dùng (0–150) | Trên 80% thường bắt đầu chậm; cũng phát hiện thuật toán dồn người vào một TURN. Guardrail `turn_utilization_p95 ≤ 85%` |
| `cpu_pct`, `bandwidth_mbps` | CPU, băng thông | Nguyên nhân gốc của chậm |
| `alloc_attempts`, `alloc_failures` | Số lần xin chỗ / lỗi trong phút | Phát hiện lỗi nhanh |
| `health_status`, `health_score` | Đánh giá tổng thể | Đầu vào health filtering |

### 11.2 `service_health_1m`: sức khỏe dịch vụ Selector, mỗi phút (KPI-grade)

Khóa: (`minute_ts`, `service`, `instance`).

| Field | Vì sao cần |
|---|---|
| `req_count`, `error_count`, `timeout_count` | Availability, Error Rate |
| `p50_ms`, `p95_ms`, `p99_ms` | API Latency |
| `static_fallback_count` | Fallback do hạ tầng (Selector không trả lời) |
| `algo_fallback_count` | Fallback do thuật toán thiếu dữ liệu. Hai loại có nguyên nhân khác nhau nên tách |
| `active_snapshot_id` | Đang phục vụ snapshot nào |
| `feature_snapshot_age_s` | `now − cutoff_ts` của snapshot đang phục vụ. Pipeline chết thì tăng dần |
| `shadow_req_count` | Số request shadow, để kiểm tra workload chạy bóng có bị giới hạn tài nguyên (§21.7) |

---

## 12. Cửa sổ 5 giây và epoch: tóm tắt một lần cho dễ nhớ

- **Epoch** = một giai đoạn mạng (đổi Wi-Fi↔4G thì sang epoch mới).
- **Cửa sổ** = 5 giây, lưới cố định neo tại ICE connected **đầu tiên**.
- **Một cuộc gọi, một lưới.** Không đặt lại neo sau restart.
- **Cửa sổ "không đánh giá được"** không nằm trong tử số hay mẫu số của PoorFraction. Mỗi metric có số cửa sổ assessable riêng.
- Cuộc gọi `pre_connect` có thể đã connected từ lúc đổ chuông; neo vẫn là ICE connected đầu tiên. Cửa sổ trước khi có media thuộc nhóm không có số đo hợp lệ, nên không làm sai PoorFraction.

---

## 13. Quy tắc thu thập dữ liệu

### 13.1 Dữ liệu KPI-grade luôn gửi 100%
Không phụ thuộc bất kỳ quy tắc lấy mẫu nào.

### 13.2 Vì sao có ring buffer?
Trong cuộc gọi, SDK ghi `call_stats_5s` vào bộ nhớ đệm vòng trên thiết bị: tối đa 360 cửa sổ (30 phút) và 256 KB mỗi cuộc gọi. Tràn thì giữ cửa sổ **mới nhất**, đặt `stats_status = truncated`. Lý do: **quyết định có gửi hay không chỉ biết được khi cuộc gọi kết thúc** (cuộc gọi có tệ không?), mà lúc đó cần dữ liệu từ đầu cuộc gọi. Bộ đệm giữ lại tạm thời để đủ dữ liệu khi cần quyết định.

### 13.3 Quy tắc lấy mẫu dữ liệu diagnostic (khi cuộc gọi kết thúc)

| Tầng | Điều kiện | Kết quả |
|---|---|---|
| **critical** | `end_reason ∈ {ice_failed, dropped_network, dropped_turn}`, hoặc `n_ice_attempts > 1`, hoặc có fallback hoặc restart | Giữ **toàn bộ**, `prob = 1.0`, `stats_status = kept_critical`, `stats_sampling_reason = critical:<lý do>` |
| **normal** | `u64(sha256(utf8(call_id))[0:8], big-endian) mod 1000 < 100` | Giữ, `prob = 0.1`, `kept_sampled`, `hash_sample` |
| **normal, không trúng** | ngược lại | Xóa buffer, `prob = 0.0`, `not_sampled`, `not_selected` |

- **Chọn bằng hash của `call_id`**, không bằng số ngẫu nhiên: ai cũng tính lại được cuộc gọi X có được chọn không, nên kiểm tra được tự động (I17), và quyết định không phụ thuộc may rủi lúc chạy.
- **Cuộc gọi lỗi giữ 100%**: những cuộc gọi tệ là thứ ta muốn điều tra nhất, giữ ít thì không có gì để xem. Nhưng vì vậy tập dữ liệu diagnostic **không đại diện**: cuộc gọi lỗi chiếm tỉ lệ cao hơn thực tế. Đây là lý do nó không dùng cho KPI.
- **`lost` khác `not_sampled`:** đã chọn giữ nhưng gửi thất bại → `lost`. `not_sampled` là không chọn có chủ đích. Cả hai đều "không có dữ liệu" nhưng ý nghĩa ngược nhau: `lost` là lỗi hạ tầng, đáng điều tra; `not_sampled` là bình thường.
- **Aggregate dùng trọng số Horvitz-Thompson `1/prob` ở cấp cuộc gọi** (cuộc gọi lỗi trọng số 1, cuộc gọi thường trọng số 10), và độ bất định tính **theo cụm cuộc gọi**, không theo từng cửa sổ (các cửa sổ trong một cuộc gọi tương quan nhau).

---

## 14. Bất biến: "luật" dữ liệu phải tuân theo

Pipeline tự kiểm tra mỗi ngày. Mức **FAIL** = dữ liệu sai, phải sửa; **WARN** = đáng ngờ, hiện lên trang Data Quality. Ghi vào `dq_results`. Đây là cách thực hiện yêu cầu "bảo đảm tính nhất quán giữa Selection, Allocation, ICE và Call Outcome".

| ID | Mức | Luật (nói đơn giản) | Nếu vi phạm thì thường là do |
|---|---|---|---|
| I1 | FAIL | Mọi event có `call_id` đều có `call_session` | Mất event `call_session`, hoặc `call_id` ghi sai |
| I2 | WARN | Mỗi `call_session` có đúng 1 `call_outcome` trong 72 giờ | App crash, mất mạng trước khi gửi kết cục. Gọi là **orphan** |
| I3 | FAIL | `len(candidates) = k`; rank liên tục 1..k; không trùng `turn_id`; tổng propensity = 1 (sai số 1e-6) | Lỗi code thuật toán |
| I4 | WARN | TURN thực dùng phải nằm trong `candidates` của cùng bên (trừ `static_fallback`) | Client tự ý dùng TURN khác, hoặc lỗi tra hostname |
| I5 | WARN | **Chỉ kiểm tra thứ tự nhân quả** (xem bên dưới) | Đồng hồ điện thoại lệch quá 2 giây, hoặc lỗi gắn event |
| I6 | FAIL | `answered = false` thì `end_reason` chỉ được là `invite_undelivered`, `not_answered`, `rejected`, `cancelled_by_caller`. `connected = true` mà chưa bắt máy chỉ hợp lệ khi `connection_mode = pre_connect` | Lỗi logic ở SDK, hoặc `connection_mode` ghi sai |
| I7 | FAIL | `dropped = true` thì phải `answered` và `connected` | Lỗi gán nhãn |
| I8 | FAIL | `path_type = relay_same` khi và chỉ khi `relay_turn_caller = relay_turn_callee ≠ null` | Lỗi gán nhãn |
| I9 | WARN | Khi cả 3 chặng forward **và** 3 chặng reverse đều là `one_way`, cùng cửa sổ, `clock_sync_err_ms ≤ 2`: tổng forward + tổng reverse ≈ `media_rtcp_rtt` (lệch ≤ 20% hoặc ≤ 15 ms) | Một trong hai nguồn đo sai, sai đơn vị, hoặc chặng đo không cùng cửa sổ |
| I10 | FAIL | Số liệu hợp lệ: `0 ≤ value_ms ≤ 10000`; `0 ≤ loss_pct ≤ 100`; jitter ≥ 0; `0 ≤ utilization_pct ≤ 150`; **tổng histogram = số cửa sổ assessable tương ứng** | Sai đơn vị (giây/ms), counter âm, lỗi cộng histogram |
| I11 | WARN | `event_id` duy nhất (bản trùng bị loại và đếm) | Gửi lại do mạng chập chờn |
| I12 | FAIL | Decision dùng snapshot S thì `S.published_ts ≤ request_ts` | Selector đọc snapshot chưa được publish |
| I13 | FAIL | Mọi event đóng góp vào snapshot S phải có `event_ts < S.cutoff_ts` **và** `ingest_ts < S.cutoff_ts`. Snapshot đã publish là bất biến | Lỗi pipeline hoặc backtest rò dữ liệu tương lai |
| I14 | FAIL | Selector không được chặn lời mời gọi. Selector lỗi/timeout thì `decision_source = static_fallback`; không bao giờ có `end_reason` do Selector | Signaling chờ Selector rồi mới gửi lời mời |
| I15 | FAIL | Nếu `experiment_id ≠ null` thì `arm ≠ null` và `assignment_ts ≤ request_ts` đầu tiên | Gán nhánh sau khi đã biết kết quả/quyết định |
| I16 | FAIL | KPI chính và guardrail chỉ đọc bảng KPI-grade | Ai đó viết KPI đọc `call_stats_5s` |
| I17 | FAIL | `stats_sampling_prob` khớp quy tắc §13.3 khi tính lại từ `call_id` và outcome | Cài đặt hash sai ngôn ngữ, quy tắc đổi mà không nâng `sampling_rule_version` |

### 14.1 I5: vì sao chỉ kiểm tra thứ tự nhân quả?

v0.1 ép một thứ tự tuyến tính "gọi → quyết định → xin chỗ → nối → kết thúc". Trong WebRTC thật, các việc này **chồng lấn**: ICE có thể bắt đầu thu thập candidate trong lúc allocation đang xin; allocation có thể xin trước cho cả 4 TURN; signaling và ICE chạy song song. Ép thứ tự cứng sẽ báo lỗi oan cho dữ liệu hoàn toàn đúng.

v0.2 chỉ kiểm tra những cặp mà **cái này phải có trước cái kia** (đúng nhân quả), với dung sai lệch đồng hồ 2 giây:

| Cặp | Vì sao bắt buộc |
|---|---|
| (a) `initiated_ts` ≤ `request_ts` đầu tiên | Không có cuộc gọi thì không có quyết định |
| (b) `decision.response_ts` ≤ `alloc.request_ts` (allocation thuộc decision đó) | Phải có danh sách rồi mới xin chỗ |
| (c) `alloc.response_ts` ≤ `ice_connected_ts` (khi attempt dùng allocation đó) | Chưa được cấp chỗ thì chưa nối qua TURN đó được |
| (d) `ring_ts` ≤ `ice_connected_ts` | Chưa đổ chuông thì chưa nối được |
| (e) với `post_answer`: `answer_ts` ≤ `checks_start_ts` | Chế độ này ICE chỉ bắt đầu sau khi bắt máy |
| (f) `ice_connected_ts` ≤ `dtls_connected_ts` ≤ `first_media_sent_ts` | Nối xong → mã hóa xong → mới gửi media |
| (g) mọi mốc ≤ `end_ts` | Không có gì xảy ra sau khi kết thúc |

Mọi thứ khác (thứ tự allocation, signaling, ICE checks) **không bị ràng buộc**.

### 14.2 I6: vì sao có ngoại lệ `pre_connect`?
Ở `pre_connect`, ICE chạy trong lúc đổ chuông, nên cuộc gọi có thể `connected = true` trong khi người nghe chưa bấm nghe (`answered = false`) hoặc không bao giờ bấm nghe. Ở `post_answer` thì tình huống đó là lỗi dữ liệu.

### 14.3 I9: vì sao phải đủ forward **và** reverse, và vì sao RTT/2 là sai?
RTT là thời gian đi **cộng** về, đo bằng `media_rtcp_rtt`. Để kiểm tra chéo với số đo chặng, cần tổng thời gian đi cộng tổng thời gian về của các chặng, nên phải có **cả hai chiều** (3 chặng forward + 3 chặng reverse), đều là `one_way`, đo cùng cửa sổ, đồng hồ đủ khớp.

v0.1 so tổng 3 chặng một chiều với RTT/2. Cách đó **chỉ đúng nếu mạng đối xứng**, mà mạng thật thường không (4G upload khác download). Ví dụ minh họa: một đường có forward 140 ms + reverse 160 ms (RTT 300, RTT/2 = 150) và một đường khác forward 150 ms + reverse 10 ms (RTT 160, RTT/2 = 80). RTT/2 báo hai chiều bằng nhau trong khi thực tế một chiều dài hơn hẳn chiều kia. Kiểm tra chéo bằng RTT/2 sẽ báo lỗi oan hoặc bỏ sót lỗi thật. Vì I9 chỉ chạy khi đủ điều kiện, nên mức là WARN: không đủ điều kiện thì bỏ qua chứ không coi là sai.

### 14.4 I12 và I13: "thời điểm hệ thống biết"
Có ba mốc thời gian dễ lẫn:
- `event_ts`: sự việc xảy ra lúc nào (đồng hồ của nơi sinh).
- `ingest_ts`: hệ thống **nhận được** lúc nào.
- `published_ts` (của snapshot): snapshot **bắt đầu được dùng** lúc nào.

Quy tắc: Selector tại thời điểm *t* chỉ được dùng snapshot đã publish trước *t* (I12). Và snapshot chỉ chứa event mà hệ thống **đã biết trước cutoff** — tức cả `event_ts` lẫn `ingest_ts` đều < `cutoff_ts` (I13).

**Ví dụ sự kiện đến muộn:** Một cuộc gọi kết thúc lúc 23:58 giờ VN ngày D. Điện thoại mất sóng, tới 00:20 ngày D+1 mới gửi được `call_outcome`. Với snapshot có cutoff 00:00 ngày D+1: `event_ts` = 23:58 < cutoff, nhưng `ingest_ts` = 00:20 > cutoff. Hệ thống *chưa biết* điều này lúc cutoff, nên event **không** được vào snapshot đó mà vào snapshot hôm sau. Nếu bỏ điều kiện `ingest_ts`, thì dựng lại snapshot sau này sẽ khác bản đã publish, và backtest sẽ "biết" những thứ mà hệ thống thật chưa biết, cho kết quả đẹp giả.

**Snapshot bất biến:** đã publish thì không sửa. Sửa logic hay bổ sung dữ liệu muộn thì tạo `v<n+1>` với `snapshot_id` mới (`parent_snapshot_id` trỏ về bản cũ). Quyết định đã ghi `feature_snapshot_id` cũ vẫn truy được chính xác bản cũ đó.

### 14.5 I14, I15, I16, I17: giải thích ngắn
- **I14 (Selector không chặn):** nếu Selector sập mà cuộc gọi cũng chết theo thì thuật toán "gây ra" lỗi, không phải "tối ưu" cuộc gọi. Selector chỉ được là cố vấn; hỏng thì dùng danh sách mặc định.
- **I15 (gán nhánh trước quyết định):** nếu gán nhánh sau khi đã biết cuộc gọi diễn ra thế nào thì có thể (cố ý hoặc vô tình) chọn cuộc gọi dễ cho nhánh mình thích.
- **I16:** xem §3.
- **I17:** xem §13.3.

---

## 15. Cách các bảng nối với nhau
(Xem walkthrough ở §22. Mục này ghi các "dây buộc".)

### 15.1 Các khóa nối
- `call_id`: nối mọi bảng cuộc gọi.
- `decision_id`: nối `selector_decision` ↔ `turn_allocation` ↔ `ice_attempt`.
- `allocation_id`: nối `turn_allocation` ↔ `ice_attempt` (qua `caller_allocation_id`, `callee_allocation_id`).
- `ice_generation` + `attempt_seq`: nối allocation, ICE attempt, số đo chặng với nhau theo từng lần thử.

### 15.2 Vì sao cần `ice_generation`?
Sau ICE restart, TURN có thể được xin lại (đôi khi cùng `turn_id`). Nếu không có thế hệ, không phân biệt được allocation cũ (đã hết hạn) với mới.

### 15.3 Đổi hostname thành `turn_id`
SDK chỉ biết `hostname` của candidate relay. Pipeline tra `dim_turn.hostname` để ra `turn_id`.

---

## 16. Clean-layer: pipeline cam kết xuất ra (producer **không** gửi)

### 16.1 Đồng hồ
Các cột `event_ts_corrected`, `clock_skew_ms` (offset ước lượng theo thiết bị × ngày, là trung vị độ lệch giữa client và Signaling trên các mốc tương ứng), `clock_correction_version`, `clock_quality_flag` (`ok`, `corrected`, `unreliable`).
**`event_ts` gốc giữ nguyên.** Bản sửa nằm ở cột riêng. Lý do: sửa đè thì không phân biệt được "dữ liệu thật" với "dữ liệu đã chỉnh bằng một giả định", và nếu thuật toán sửa sai thì không có đường lui. Cũng không dùng bản sửa để khẳng định độ chính xác vượt quá khả năng đồng bộ thực tế.

### 16.2 Độ trễ chặng: quan sát khác ước lượng
- `one_way_ms_observed` = `value_ms` khi `measurement_kind = one_way` **và** `clock_sync_err_ms ≤ 2`; ngược lại `null`.
- `one_way_ms_estimated` = `value_ms / 2` khi `measurement_kind = rtt`, kèm cờ `symmetric_assumption = true`.
- **`alloc_ms` không bao giờ được đổi sang one-way.** Thống kê riêng ở `feat_turn_alloc_latency`. Chỉ được dùng làm predictor của chặng sau khi mô hình hiệu chỉnh đã được kiểm chứng trên dữ liệu tách riêng (thí nghiệm W5).

**Vì sao tách "quan sát" và "ước lượng"?** Hai cột này khác bản chất: cái đầu là đo thật, cái sau là suy luận dựa trên giả định đối xứng. Trộn chung thì người dùng dữ liệu không biết số nào là thật. Cờ `symmetric_assumption` nhắc luôn kèm theo giả định.

### 16.3 Ghép allocation với ICE
1. Ưu tiên `*_allocation_id` trong `ice_attempt`.
2. Thiếu thì ghép theo (`call_id`, `decision_id`, `side`, `turn_id`, `transport`, `ice_generation`), với điều kiện allocation còn hiệu lực: `response_ts ≤ ice_connected_ts < released_ts`. **Không bao giờ** ghép allocation của thế hệ cũ vào attempt mới chỉ vì cùng `turn_id`.
3. Xuất ra `used_by_ice` (bool) và `match_method` (`id`, `rule`, `ambiguous`).

### 16.4 `fact_call`
Một dòng mỗi cuộc gọi: các cột KPI (tính từ dữ liệu KPI-grade), `rank_used_*`, `joint_propensity = p_caller × p_callee` (xác suất cả hai bên cùng được chọn như vậy), `arm`, `blind_cost_ms` (chỉ sim).

### 16.5 `dq_results`
`(run_id, dt, check_id, table, level, status, n_checked, n_bad, sample_event_ids[])`: kết quả mọi kiểm tra bất biến.

---

## 17. Feature store: dữ liệu đã "nấu chín" cho thuật toán

**Ai sinh:** pipeline của Hiệp, mỗi ngày một lần. **Ai đọc:** thuật toán của Đoàn, dashboard.
**Vì sao Hiệp nấu mà không để Đoàn tự tính?** Để dashboard và thuật toán nhìn **cùng một con số**.

### 17.0 Snapshot, cutoff, và nhóm user

**Snapshot:**
- **Cutoff** = **00:00 giờ VN** (17:00 UTC ngày hôm trước). Mỗi ngày một snapshot.
- Metadata: `snapshot_id` (`feat-YYYYMMDD-v<n>`), `cutoff_ts`, `published_ts`, `pipeline_version`, `content_hash`, `parent_snapshot_id`.
- **Luật dùng:** tại thời điểm *t*, Selector dùng snapshot mới nhất có `published_ts ≤ t` (I12). Từ `cutoff_ts` tới `published_ts` (pipeline đang chạy), Selector **vẫn dùng snapshot cũ**.
- **Bất biến:** đã publish thì không sửa. Backfill hoặc sửa logic thì tạo `v<n+1>`. Dựng lại snapshot từ dữ liệu thô và cấu hình đã lưu phải cho ra cùng `content_hash`. Đây là cách chứng minh "không rò dữ liệu".

**Vì sao cutoff 00:00 giờ VN?** Contract chốt giờ này; lý do hợp lý (không phải câu chữ của contract) là đa số người dùng ở VN và thời điểm nửa đêm là lúc ít cuộc gọi nhất, nên ranh giới ngày cắt vào lúc yên tĩnh, ít sự kiện "đang dở" bị chia đôi. Pipeline cần thời gian để chạy, nên có khoảng thời gian từ cutoff tới `published_ts` trong đó Selector dùng dữ liệu cũ hơn một ngày; `feature_snapshot_age_s` (§11.2) theo dõi độ cũ này.

**Nhóm user và lùi cấp (backoff 5 cấp):**

```
Cấp 4: country | vn_region | asn | network_type   (Viettel miền Nam dùng 4G)  ← chi tiết nhất
Cấp 3: country | vn_region | asn
Cấp 2: country | vn_region
Cấp 1: country
Cấp 0: *                                                                       ← thô nhất
```

Nhóm càng chi tiết càng sát thực tế nhưng càng ít dữ liệu. Selector dùng cấp chi tiết nhất có `n_eff ≥ 30` và ghi cấp đã dùng vào `fallback_reason` (ví dụ `backoff_L1`). Đây là lời giải cho kịch bản Cold-start.

### 17.1 `feat_leg_stats`: chặng user ↔ TURN

| Field | Nghĩa | Vì sao cần |
|---|---|---|
| `snapshot_id`, `segment_level`, `segment_key` | Snapshot nào, nhóm user cấp nào | Xem §17.0 |
| `turn_id`, `direction` | TURN nào, chiều nào | |
| `metric` | `one_way_observed` hoặc `rtt` | Không trộn hai loại. Không có metric nào tên `alloc` |
| `hour_bucket` | Giờ VN (0–23) hoặc `all` | 21h khác 3h sáng |
| `n_raw` | Số lần đo thật | |
| `n_eff` | Số mẫu hiệu dụng sau khi giảm trọng số dữ liệu cũ (nửa trọng số sau 7 ngày) | Dữ liệu 3 tuần trước kém tin hơn hôm qua |
| `p50`, `p95` | Quantile có trọng số trên giá trị **cấp cuộc gọi** lấy từ `epoch_summary` | Mỗi cuộc gọi đóng góp một giá trị, không để một cuộc gọi dài chiếm hết trọng số. Không bao giờ lấy trung bình các P95 |
| `loss_mean`, `jitter_p95` | | |
| `p50_shrunk` | P50 đã "kéo về" mức của cấp cha | Nhóm ít mẫu hay cho số cực đoan do ngẫu nhiên (shrinkage) |
| `source_mix` | Tỷ lệ số liệu từ mỗi cách đo | Nếu 90% là probe thì chưa phản ánh người dùng thật |
| `last_observed_ts` | Lần cuối có dữ liệu | Lâu không có dữ liệu là vùng mù, nên ưu tiên thử nghiệm ở đó |

### 17.2 `feat_turn_turn`: chặng giữa hai TURN
Field: `snapshot_id`, `src_turn`, `dst_turn`, `direction`, `metric`, `hour_bucket`, `n_raw`, `n_eff`, `p50`, `p95`, `loss_mean`, `jitter_p95`, `source_mix`, `last_observed_ts`. Cuộc gọi quốc tế (Nhật ↔ Đức) có chặng giữa chiếm phần lớn độ trễ; đề bài yêu cầu tối ưu kết hợp hai đầu.

### 17.3 `feat_turn_health`
`snapshot_id`, `turn_id`, `health_status`, `health_score`, `utilization_p95_24h`, `alloc_success_24h` (+ khoảng tin cậy Wilson `ci_low`, `ci_high`), `incidents_detected_7d`, `stability_cv_24h`. Khoảng tin cậy cho thấy 3/3 thành công khác hẳn 3000/3000 dù cùng 100%.

### 17.4 `feat_path_history`
`snapshot_id`, `caller_segment_key` (cấp 2), `callee_segment_key` (cấp 2), `turn_caller`, `turn_callee`, `n_calls`, `n_eff`, `poor_rate` (+ khoảng tin cậy, theo **đúng định nghĩa §20.1**), `drop_rate`, `ice_fail_rate`, `last_observed_ts`. Đây là Historical Connection mà đề bài yêu cầu: có những thứ chỉ thấy ở mức cả đường (một cặp TURN hay rớt do lỗi tương thích). `poor_rate` dùng cùng định nghĩa PCR nên feature và KPI không lệch nhau.

### 17.5 `feat_callee_prior`
`snapshot_id`, `caller_segment_key` (cấp 2), `callee_country`, `callee_vn_region`, `n`, `share`. Ví dụ "người gọi miền Nam thì 62% người nghe ở miền Nam…". Khi gọi mù, thuật toán dùng phân phối này để chọn TURN tốt nhất xét trên trung bình các khả năng. Chỉ chứa số đếm, an toàn về riêng tư.

### 17.6 `feat_turn_alloc_latency`: tách riêng, **không phải độ trễ chặng**
`snapshot_id`, `segment_key`, `turn_id`, `transport`, `n`, `alloc_ms_p50`, `alloc_ms_p95`, `alloc_success_rate` (+ khoảng tin cậy). Đây là chỗ duy nhất `alloc_ms` được thống kê, vì nó là chỉ báo "TURN này phản hồi allocation nhanh/chậm" chứ không phải độ trễ truyền media. Nằm trong bảng riêng để không ai vô tình ghép nó vào độ trễ chặng.

---

## 18. API Selector

### 18.1 Câu hỏi và câu trả lời

**HTTP** `POST /v1/turn/select` (production và demo).

**`SelectRequest`:**

| Field | Nghĩa | Vì sao cần |
|---|---|---|
| `call_id` | Cuộc gọi nào | |
| `phase` | Hỏi lúc nào | |
| `request_ts` | Lúc hỏi | Thuật toán chọn đúng snapshot |
| `caller_ctx`, `callee_ctx` | Bối cảnh hai bên | `callee_ctx = null` khi gọi mù |
| `info_level` | Biết bao nhiêu | |
| `k` | Muốn bao nhiêu TURN | |
| `exploration_epsilon` | Tỉ lệ thử nghiệm | Do **bên gọi** quyết định, để simulator chạy 0%, 2%, 5% mà không sửa code Selector |
| `exclude_turns` | TURN không được trả lại | Khi dự phòng: TURN vừa lỗi thì đừng đề xuất lại |

**`SelectResponse`:** `decision_id`, `policy_version`, `caller` {candidates[k], filtered_out[], chosen_rank, is_exploration}, `callee` (như trên, hoặc `null`), `confidence`, `confidence_level`, `fallback_reason`, `feature_snapshot_id`, `health_snapshot_id`.

### 18.2 Không có tham số randomness do client truyền vào
Nếu client được truyền "hạt giống ngẫu nhiên" thì client có thể (cố ý hay do lỗi) chọn được kết quả mình muốn, làm hỏng propensity. Ở production, randomness lấy từ `sha256(server_secret ‖ call_id ‖ side ‖ purpose)`: server bí mật, nhưng tất định theo cuộc gọi nên tái hiện được. Ở simulator, hàm nội bộ `select(req, rng)` nhận `rng` do simulator cấp, **khóa theo** `(run_seed, call_id, side, "policy")`. Policy **không được** tạo RNG toàn cục (lý do ở §21.2).

### 18.3 Vì sao Selector **không tự ghi** log quyết định?
Nếu Selector tự ghi thì lúc Selector sập sẽ không có bản ghi nào, đúng lúc cần dữ liệu nhất. Bên gọi (Signaling hoặc simulator) luôn biết mình đã hỏi gì, nhận được gì hay không, và mất bao lâu. Bên gọi ghi, kể cả khi lỗi (`static_fallback`). Phối hợp với I14: Selector lỗi thì cuộc gọi vẫn tiếp tục.

### 18.4 Hai dạng: hàm Python và HTTP
Hàm Python để simulator gọi hàng trăm nghìn lần nhanh chóng. HTTP để demo và cho Spring Boot sau này. Cả hai cùng nội dung.

---

## 19. Bảng ẩn, run manifest, loại lần chạy, kịch bản

### 19.1 Bảng ẩn: "đáp án" chỉ simulator có

| Bảng | Chứa gì | Dùng để chấm cái gì |
|---|---|---|
| `truth_leg_5m` | Cho mỗi (`ts_bucket`, `src_id`, `dst_id`, `direction`, `network_type`): `exo_one_way_ms`, `load_one_way_ms`, `true_loss_pct`, `true_jitter_ms`, `available` | Ước lượng đường chưa đi có đúng không? Regret thật (§21.6) |
| `incident_truth` | Sự cố nào, ở đâu, lúc nào, nặng bao nhiêu (`incident_id`, `type`, `target_kind`, `target_id`, `start_ts`, `end_ts`, `severity`, `params`) | Dashboard có **phát hiện đúng** sự cố không, sau bao lâu |
| `dirt_log` | Lỗi dữ liệu nào đã được cố tình tiêm vào (`event_id`, `table`, `dirt_type`, `params`) | Pipeline có **bắt được** lỗi không |

**Hai thành phần của độ trễ thật: `exo_one_way_ms` và `load_one_way_ms`.**
- `exo_one_way_ms` = phần **ngoại sinh**: do khoảng cách, sự cố, mạng nền, giờ cao điểm của người dùng... Phần này **giống nhau giữa các policy** (cùng thế giới).
- `load_one_way_ms` = phần **do tải**: do chính policy dồn bao nhiêu người vào TURN đó. Phần này **riêng cho từng môi trường** (mỗi policy một môi trường).

Tách như vậy để so sánh Geo và Smart công bằng: thế giới bên ngoài giống nhau, chỉ khác những hậu quả do chính thuật toán gây ra (§21.2).

**Vì sao giấu?** Nếu dashboard hoặc thuật toán nhìn trộm được đáp án thì insight thành "biết trước rồi mới tìm", và thuật toán học từ đáp án cho kết quả đẹp giả. Ba bảng ở `data/truth/`, chỉ package `eval/` được đọc, có test tự động cấm `selector`, `pipeline`, `features`, `dashboard` import hoặc mở. Ngoại lệ: trang dashboard "Sim Validation" được đọc và có nhãn rõ.

### 19.2 `run_manifest`: "hộ chiếu" của mỗi lần chạy

Một file JSON cho mỗi lần chạy, commit cùng kết quả. Field: `sim_run_id`, `run_kind`, `benchmark_id`, `replicate_seed`, `simulator_version`, `git_commit`, `config_hash`, `contract_version`, `topology_version`, `network_profile_version`, `scenario_version`, `incident_schedule_version`, `incidents_sha256`, `root_seeds` {traffic, network, incidents, noise, behavior, policy} — seed gốc; việc rút số dùng RNG có khóa, `policy_version`, `exploration_epsilon`, `connection_mode`, `initial_snapshot_hash`, `burn_in_days`, `environment_dir`, `started_at`, `completed_at`.

**Vì sao cần?** Dữ liệu giả vô giá trị nếu không biết nó sinh ra thế nào. Manifest cho phép tái lập (cùng manifest → cùng hash dữ liệu, có test), biết phiên bản mọi thành phần, và chứng minh các cam kết trước khi chạy.

### 19.3 `scripted` và `blind_benchmark`

| Loại | Dùng cho | Sự cố |
|---|---|---|
| `scripted` | Test tự động, demo các kịch bản S01–S20 | **Công khai**, có kỳ vọng rõ (ví dụ "TURN X sập lúc 10:00, thuật toán phải né") |
| `blind_benchmark` | So sánh policy, insight report | **Ẩn**. `incidents_sha256` (hash của lịch sự cố) được **commit trước khi phân tích** |
| `dev` | Phát triển | Tùy ý |

**Vì sao `incidents_sha256`?** Lịch sự cố của benchmark mù được giữ kín. Cam kết hash trước chứng minh sau này: "lịch sự cố này đã cố định từ trước khi ta nhìn kết quả", tức không ai chỉnh sự cố cho hợp với kết luận. Khi công bố, ai cũng kiểm tra lại bằng cách băm file sự cố.

### 19.4 Tag cuộc gọi khác với kịch bản hệ thống

- **Tag cuộc gọi** (`scenario_tag`, ghi trong `call_session`): chỉ mô tả *loại cuộc gọi*: `S01_vn_same_region_same_isp`, `S02_vn_cross_region`, `S03_vn_same_region_cross_isp`, `S04_vn_intl_with_turn`, `S05_vn_intl_no_turn`, `S06_intl_same_area`, `S07_intl_cross_area`, `S09_cold_start`, `S10_network_change`, `S00_background`.
- **Kịch bản hệ thống** (chỉ nằm trong manifest của `scripted`, **không bao giờ** là tag cuộc gọi): `S08_turn_failure`, `S11_turn_overload`, `S12_isp_congestion`, `S13_regional_outage`, `S14_asymmetric_path`, `S15_selector_timeout`, `S16_stale_snapshot`, `S17_delayed_telemetry`, `S18_turn_recovery`, `S19_p2p_preferred`, `S20_call_burst`.

**Vì sao tách?** Nếu một cuộc gọi mang tag `S08_turn_failure` thì bất kỳ ai đọc `call_session` đều biết "TURN đang sập" mà không cần tự phát hiện. Tag cuộc gọi chỉ được nói loại cuộc gọi (vùng nào, ISP nào), còn sự cố nằm ở `incident_truth` bị giấu. Bộ kịch bản phải có ít nhất một kịch bản Geo thắng, một Historical thắng, một Smart thắng, để chứng tỏ benchmark không thiên vị.

---

## 20. KPI Dictionary (§13 của contract): đo "tốt" như thế nào

Bản máy đọc là `contracts/kpi.yaml`. Mọi KPI ở mục này **chỉ đọc dữ liệu KPI-grade** (I16). Ngưỡng ghi ở đây là *tạm thời* và được đóng băng trong `kpi.yaml` trước `blind_benchmark` đầu tiên; sau đó chỉ đổi bằng version mới.

**Ngữ nghĩa percentile:** `call_*` = trong một cuộc gọi; `population_*` = giữa các cuộc gọi, tính trên giá trị cấp cuộc gọi. **Không bao giờ lấy trung bình các P95.**

### 20.1 Phân loại một cuộc gọi: "tệ" nghĩa là gì?

Với cuộc gọi *c*, metric *m* ∈ {RTT, loss, jitter}, **chỉ trên audio**, gộp mọi epoch và tính **riêng từng bên** (caller, callee):

```
PoorFraction_m(c, bên) = Σ cửa sổ tệ_m / Σ cửa sổ đánh giá được_m     (chỉ xác định khi Σ cửa sổ đánh giá được ≥ 4)

Cửa sổ tệ:  RTT     → bucket ≥ 300 ms   (media_rtcp_rtt)
            loss    → bucket ≥ 3 %
            jitter  → bucket ≥ 30 ms    (jitter estimate)

quality_poor(c)    = tồn tại bên nào, metric nào xác định mà PoorFraction ≥ 0.20
quality_ok(c)      = mọi metric của mọi bên đều xác định và đều < 0.20
còn lại            → quality_unknown(c)   (không có gì xác định, hoặc chỉ một phần xác định mà không có cái nào poor)

poor(c) = end_reason = ice_failed
        ∨ end_reason ∈ {dropped_network, dropped_turn}
        ∨ (answered ∧ connected ∧ quality_poor(c))

unclassifiable(c) = answered ∧ connected ∧ ¬dropped ∧ quality_unknown(c)
```

Lý do kết thúc ngoài phạm vi TURN (`invite_undelivered`, `not_answered`, `rejected`, `cancelled_by_caller`, `app_crash`, `normal_hangup` mà chất lượng ok) **không** làm cuộc gọi bị tính tệ, nhưng cuộc gọi **vẫn ở trong cohort**.

**Giải thích từng quyết định:**
- **Gộp theo cửa sổ (PoorFraction) thay vì lấy P95 theo epoch:** một cú giật 5 giây trong cuộc gọi 30 phút làm P95 của một epoch xấu đi, nhưng người dùng gần như không nhận ra. Còn nếu 20% thời gian bị tệ thì chắc chắn người dùng thấy. Đếm tỉ lệ cửa sổ tệ gần với cảm nhận hơn, và histogram làm việc đếm này rẻ.
- **"Chỉ xác định khi ≥ 4 cửa sổ":** 1 cửa sổ tệ trên 2 cửa sổ đo được là 50% nhưng chẳng đủ cơ sở. Cần tối thiểu 4 cửa sổ (20 giây) cho mỗi metric mỗi bên.
- **Tính riêng từng bên, bên xấu hơn quyết định:** cuộc gọi là hai chiều. Nếu callee nghe rất tệ còn caller nghe tốt, cuộc gọi vẫn tệ. Gộp trung bình hai bên sẽ che mất bên tệ.
- **Ngưỡng 20%:** tạm thời; sensitivity thử 10/20/30% (§21.5).
- **Ngưỡng RTT 300 ms (và loss 3%, jitter 30 ms) là SLO nội bộ tạm thời, KHÔNG suy ra từ khuyến nghị G.114.** G.114 nói về độ trễ **một chiều** khoảng 150 ms. RTT 300 ms chỉ tình cờ trông giống "2 × 150", nhưng RTT không cho biết từng chiều. Phản ví dụ (minh họa của tài liệu này): đường forward 140 + reverse 160 có RTT 300 (RTT/2 = 150, "vừa đạt" nếu cứ chia đôi) trong khi chiều reverse đã 160 > 150; đường forward 150 + reverse 10 có RTT 160, nằm xa dưới ngưỡng 300 dù một chiều đã sát 150. Cùng RTT có thể ứng với nhiều trạng thái một chiều rất khác nhau. Vì vậy contract nói rõ đây là ngưỡng nội bộ, đóng băng trước benchmark, thử nhạy với 200/300/400.
- **`unclassifiable` và `quality_unknown`:** cuộc gọi đã nối, bắt máy, không rớt, nhưng thiếu số đo đủ để phân loại. Không thể gọi là tốt, cũng không thể gọi là tệ. Đây là lý do có **hai cận** ở mục sau.

### 20.2 Tầng 1: Metric chính **`pcr_itt`**

| | Định nghĩa |
|---|---|
| **Cohort** | Mọi `call_session` của experiment đã được gán `arm` (I15), **kể cả** khi sau đó Selector timeout, static fallback, P2P, allocation lỗi, không gửi được lời mời, hoặc không ai bắt máy |
| `pcr_itt_low` | Σ poor / \|cohort\| (cho rằng mọi cuộc gọi unclassifiable đều tốt) |
| `pcr_itt_high` | Σ (poor ∨ unclassifiable) / \|cohort\| (cho rằng mọi unclassifiable đều tệ) |
| Đơn vị | %, **càng thấp càng tốt** |

**Vì sao cohort xác định trước quyết định (ITT)?** Nếu chỉ tính cuộc gọi "đã nối được qua TURN", thuật toán có thể "thắng" nhờ để những cuộc gọi khó rơi ra ngoài mẫu (ví dụ cuộc gọi phải static fallback, chuyển sang P2P hay không gửi được lời mời thì không được đếm). ITT đếm *mọi* cuộc gọi được giao cho nhánh đó, nên không thể thắng bằng cách đẩy vấn đề ra ngoài mẫu. Cohort được định nghĩa ở lúc gán nhánh (trước mọi quyết định), tức trước khi biết kết quả.

**Vì sao hai cận (low/high)?** Có những cuộc gọi không đủ số đo để phân loại. Tính chúng là tốt hay là tệ đều là giả định. Thay vì chọn bừa, báo cáo cả hai cực đoan: kết luận chỉ mạnh khi đúng ở cả hai. Nếu `low` và `high` chênh nhau nhiều tức là telemetry thiếu, và bản thân điều đó là thông tin (có guardrail `unclassifiable_rate`).

### 20.3 Tầng 1b: Metric phụ quan trọng (có điều kiện)

| KPI | Định nghĩa |
|---|---|
| `pcr_answered` (low/high) | Như trên nhưng mẫu số = cuộc gọi đã bắt máy trong cohort. Diễn giải là chất lượng **có điều kiện**, với giả định policy không ảnh hưởng việc bắt máy. Giả định này được **kiểm tra và báo cáo** (`answer_rate` theo nhánh), **không bao giờ dùng để đổi metric chính** |
| Thành phần | `ice_fail_rate`, `drop_rate`, `quality_poor_rate`, `unclassifiable_rate` (cùng mẫu số cohort) |
| Phễu | `invite_delivered_rate`, `answer_rate`, `selector_timeout_rate`, `static_fallback_rate`, `p2p_rate` |

### 20.4 Tầng 2: Guardrail (non-inferiority)

Guardrail là "đừng làm hỏng thứ khác". Smart chỉ được gọi là tốt hơn nếu mọi guardrail không tệ hơn Geo quá biên cho phép δ.

| Guardrail | Hướng | Margin δ |
|---|---|---|
| `ice_fail_rate` (mẫu số cohort ITT) | thấp | +0.2 điểm % |
| `drop_rate` (mẫu số cohort ITT) | thấp | +0.2 điểm % |
| `cst_technical_p95` = P95(`ice_connected_ts − checks_start_ts`) | thấp | +10% |
| `ttfm_post_answer_p95` = P95(max(0, max_bên(`first_media_received_ts`) − `answer_ts`)) | thấp | +10% |
| `selector_api_p95` | thấp | ≤ 50 ms (tuyệt đối) |
| `selector_availability` = 1 − (error + timeout)/req | cao | ≥ 99.9% (tuyệt đối) |
| `static_fallback_rate` | thấp | +0.2 điểm % |
| `turn_utilization_p95` (mọi TURN, mọi phút) | thấp | ≤ 85% (tuyệt đối) |
| `unclassifiable_rate` (độ đầy đủ telemetry) | thấp | +1.0 điểm % |
| `pcr_itt_high` theo từng `pair_group` | thấp | +0.5 điểm % |

- "Điểm %" = hiệu số tuyệt đối (từ 1.0% lên 1.2% là +0.2 điểm %). "+10%" là tương đối.
- `max(0, …)` trong `ttfm_post_answer`: với `pre_connect`, media có thể đã tới trước khi người dùng bấm nghe, nên khoảng thời gian âm bị chặn về 0.
- Guardrail `unclassifiable_rate` bảo vệ chống "thắng bằng cách làm mất telemetry".
- Guardrail theo `pair_group` bảo vệ chống việc thắng tổng thể bằng cách hy sinh một nhóm.

### 20.5 Tầng 3: Chẩn đoán (không dùng để kết luận thắng/thua)

`pnr` (chỉ trên cuộc gọi đã connected — **đã hạ cấp, không còn là metric chính**) · `population_media_rtcp_rtt_p50/p95` · `population_ice_stun_rtt_p95` · `population_loss` · `population_jitter_estimate_p95` · `mos_est` (E-model) · `max_epoch_p95` · `rank_of_used` · `est_vs_observed_mae` · `confidence_calibration` · `coverage_7d` · `ess` · `hhi_turn` · `alloc_success_rate` · `allocation_not_selected_rate` · `allocation_never_checked_rate` (khi có `ice_candidate_pair`) · `reserve_allocation_seconds` · `allocation_seconds_unanswered` · `blind_cost_ms` · regret.

Mấy chỉ số cần giải thích: `mos_est` là điểm chất lượng ước lượng từ công thức E-model; `ess` = effective sample size, số mẫu hiệu dụng sau khi cân trọng số; `hhi_turn` = chỉ số dồn tập trung vào ít TURN (càng cao càng dồn); `coverage_7d` = tỉ lệ phân khúc có đủ dữ liệu trong 7 ngày; `reserve_allocation_seconds` và `allocation_seconds_unanswered` = chi phí giữ chỗ TURN dự phòng và giữ chỗ cho cuộc gọi không ai nghe.

---

## 21. Đánh giá (Evaluation): làm sao biết Smart thật sự tốt hơn Geo

### 21.1 Estimand: ta đang đo cái gì?
`Δ = PCR_itt(Smart) − PCR_itt(Geo)` trên **cùng các yếu tố ngoại sinh**. So sánh với Historical theo cùng cách. Hiệu ứng này là hiệu ứng **ITT**: "nếu giao nhánh này cho mọi cuộc gọi thì tỉ lệ cuộc gọi tệ khác nhau bao nhiêu".

### 21.2 Thiết kế trên simulator

1. **Mỗi policy một môi trường cô lập.** Mỗi (policy, seed) là một lần chạy riêng với `environment_dir` riêng, có feature store, health state, tải TURN và cache riêng. Vì sao: nếu hai policy chạy chung một thế giới, Smart dồn người vào TURN X làm X chậm và Geo cũng chịu hậu quả (interference), nên không đo được hiệu ứng riêng của từng policy.
2. **Yếu tố ngoại sinh dùng chung.** Traffic (ai gọi ai, lúc nào, có bắt máy không, thời lượng dự định, thời điểm đổi mạng), lịch sự cố, mạng nền. Mọi policy phải gặp *đúng cùng một thế giới bên ngoài*.
3. **Yếu tố nội sinh được phép khác nhau** (tải TURN, lịch sử, snapshot): đó là hiệu ứng cần đo.
4. **RNG có khóa, không phải luồng tuần tự.** Giá trị ngẫu nhiên là hàm của (seed, thực thể, thời điểm), ví dụ `(seed, call_id, "answer")` cho việc bắt máy, `(seed, call_id, leg, direction, window_idx, "noise")` cho nhiễu, `(seed, turn_id, ts_bucket, "net")` cho mạng nền. **Số event do policy sinh ra không được làm xê dịch bất kỳ luồng ngẫu nhiên nào.**

**Vì sao "mỗi loại một luồng riêng" (traffic, network…) vẫn chưa đủ?** Luồng ngẫu nhiên tuần tự là một dãy số rút lần lượt. Dù đã tách luồng cho `network`, nếu Smart sinh ra 5.000 mẫu nhiễu còn Geo sinh 4.000 mẫu thì mẫu thứ 4.001 trở đi của hai nhánh **lệch nhau**: cùng thời điểm nhưng ra nhiễu khác, và từ đó hai nhánh sống trong "thế giới khác" chỉ vì số lần rút khác nhau. RNG có khóa tính giá trị trực tiếp từ (seed, call_id, ...) nên nhiễu của cuộc gọi X ở thời điểm Y luôn như nhau bất kể có bao nhiêu event khác. (`root_seeds` trong manifest vẫn ghi lại seed gốc của từng nhóm, nhưng việc rút số phải theo khóa.)

5. **Khởi đầu giống nhau.** Mọi policy dùng cùng `initial_snapshot_hash`. **Burn-in 3 ngày** bị loại khỏi đánh giá, vì lúc đầu hệ thống còn đang ấm lên.
6. **Tái lập:** cùng manifest → cùng hash dữ liệu (có test).

### 21.3 Đơn vị độc lập = seed, và power analysis

- **Đơn vị độc lập là seed, không phải cuộc gọi.** Với mỗi seed *r*, tính `d_r` (hiệu PCR giữa hai policy) trên các ngày sau burn-in. Mỗi seed là một thế giới độc lập.
- **Vì sao bootstrap theo từng cuộc gọi là sai?** Trong một lần chạy, các cuộc gọi dùng chung TURN và chung tải. Một đợt quá tải ảnh hưởng hàng ngàn cuộc gọi cùng lúc, nên các cuộc gọi **không độc lập**. Bootstrap theo cuộc gọi coi 1 triệu cuộc gọi như 1 triệu bằng chứng độc lập, cho khoảng tin cậy quá hẹp và kết luận "có ý nghĩa" giả. Thông tin độc lập thật nằm ở số seed (số thế giới).
- **Power analysis trên đúng estimand ITT:** chạy **3 seed thử nghiệm chỉ để ước lượng phương sai** của `d_r`, rồi tính số seed R cần thiết để phát hiện **MDE = 0.5 điểm %** với α = 0.05 hai phía, power 0.8. R cuối được ghi vào manifest **trước khi chạy**. Không đủ ngân sách thì báo cáo MDE thực tế đạt được. Vì sao trên ITT: phương sai của hiệu PCR_itt khác phương sai của các metric khác, nên phải tính trên đúng cái sẽ kết luận.
- **Kiểm tra chéo trong một lần chạy:** block bootstrap theo (ngày × miền), giữ cặp Geo–Smart. Chỉ là kiểm tra thêm, không thay cho seed.

### 21.4 Luật kết luận (đóng băng trước `blind_benchmark`)

Với mỗi seed:
- `worst_r = pcr_itt_high(Smart) − pcr_itt_low(Geo)` (Smart ở kịch bản xấu nhất, Geo ở kịch bản tốt nhất)
- `best_r = pcr_itt_low(Smart) − pcr_itt_high(Geo)` (Smart ở kịch bản tốt nhất, Geo ở kịch bản xấu nhất)

**So sánh chéo hai cận** nghĩa là: muốn khẳng định Smart *chắc chắn* tốt hơn thì ta so Smart ở trường hợp xấu với Geo ở trường hợp tốt. Nếu ngay cả khi đó Smart vẫn tốt hơn thì kết luận không phụ thuộc vào cách xử lý các cuộc gọi unclassifiable. Ngược lại, muốn khẳng định Smart *chắc chắn* tệ hơn thì lấy Smart tốt nhất so Geo xấu nhất.

| Kết luận | Điều kiện |
|---|---|
| **Smart tốt hơn** | `UpperCI95(worst) < 0` **và** với mọi guardrail *j*: `UpperCI95(ΔG_j) < δ_j` (guardrail có hai cận thì dùng cận bất lợi) |
| **Smart tệ hơn** | `LowerCI95(best) > 0` **hoặc** tồn tại guardrail với `LowerCI95(ΔG_j) > δ_j` |
| **INCONCLUSIVE** | Mọi trường hợp còn lại, kể cả khi CI chỉ chạm margin |

- **Non-inferiority:** guardrail không đòi Smart *tốt hơn*, chỉ đòi *không tệ hơn quá δ*. `UpperCI95(ΔG_j) < δ_j` nghĩa là ngay cả cận trên của khoảng tin cậy về mức chênh lệch vẫn nằm trong biên cho phép.
- **Vì sao INCONCLUSIVE là kết luận hợp lệ:** thà nói "chưa đủ bằng chứng" còn hơn kết luận sai. Cũng vì vậy chạm margin vẫn là inconclusive.
- Guardrail theo `pair_group` dùng khoảng tin cậy **98.33%** (hiệu chỉnh Bonferroni cho 3 nhóm: 1 − 0.05/3).
- Kết luận chỉ áp dụng cho `data_source = synthetic` với các giả định trong sổ giả định của spec.

### 21.5 Sensitivity bắt buộc
Thử lại với: ngưỡng RTT 200/300/400 · loss 1/3/5 · jitter 10/30/50 · PoorFraction 0.1/0.2/0.3 · **`connection_mode = pre_connect`**.

Với `pre_connect`, **chạy lại toàn bộ** KPI chính, guardrail và tải TURN (không chỉ đổi nhãn): allocation phải sống trong lúc đổ chuông, kể cả cuộc gọi không được bắt máy, và có TTL. Vì `pre_connect` thay đổi lượng allocation, thời gian giữ chỗ và thứ tự sự kiện nên có thể đổi cả thứ hạng policy. Thứ hạng đổi chiều ở bất kỳ kịch bản nào ⇒ kết luận ghi "phụ thuộc giả định".

### 21.6 Regret (chỉ sim, chẩn đoán)
**Regret** = chênh lệch giữa đường đã đi và đường tốt hơn mà lẽ ra có thể đi. Loss của một đường = PoorFraction tổng hợp theo truth trong thời gian cuộc gọi. Null khi không có truth hợp lệ.

| Loại | Định nghĩa | Ý nghĩa |
|---|---|---|
| `in_list_regret` | loss(đường đã đi) − min loss trên các tổ hợp trong `candidates` | Thuật toán có xếp đúng thứ tự trong chính danh sách của nó không? |
| `feasible_global_regret` | loss(đường đã đi) − min loss trên các tổ hợp **khả thi theo sự thật** | Danh sách có bỏ sót đường tốt hơn không? |
| `joint_path_regret` | Như trên nhưng cho cả hai bên cùng lúc. **Là chính** | Cuộc gọi cần cả hai đầu |

- **Khả thi theo sự thật:** `truth.available ∧ dim_turn.status = active ∧ hỗ trợ transport`. **Không** dùng health snapshot của Selector, vì snapshot là niềm tin (có thể sai) của Selector. Nếu dùng niềm tin của Selector để loại đường thì Selector "tự cho mình đúng": TURN đang thật sự khỏe nhưng bị Selector nghĩ nhầm là hỏng sẽ bị loại khỏi tập so sánh và regret trông nhỏ.
- Regret từng bên chỉ tính khi cố định bên kia theo lựa chọn thực tế.
- Báo cáo kèm số tổ hợp khả thi. Giả định: một cuộc gọi đơn lẻ không làm thay đổi tải.

### 21.7 Pilot production (định hướng, chi tiết hóa ở W6)
- **Ngẫu nhiên hóa theo cuộc gọi không cho kết luận nhân quả** khi các nhánh dùng chung TURN pool (cùng lý do như §21.3). Ưu tiên `randomization_unit ∈ {region, time_block}` — **switchback**: luân phiên nhánh theo vùng hoặc theo khối thời gian.
- **Washout** phải bao phủ toàn bộ horizon "ảnh hưởng còn sót lại" khi chuyển nhánh: TTL allocation, P99 thời lượng cuộc gọi, cửa sổ health rolling, TTL cache, tuổi snapshot/state của policy. Hoặc **cô lập / reset** các state đó khi chuyển nhánh. Cuộc gọi trong washout bị loại khỏi phân tích. Nếu không, nhánh sau thừa hưởng (hoặc gánh) tải và lịch sử do nhánh trước để lại.
- **Shadow mode** (chạy bóng, không ảnh hưởng cuộc gọi thật): không được chấm bằng PCR, chỉ OPE/regret. Workload shadow phải được **giới hạn tài nguyên** (theo dõi `shadow_req_count`).
- Không kiểm soát được interference ⇒ pilot chỉ là **đánh giá vận hành**, không phải kết luận nhân quả.

---

## 22. Đi qua một cuộc gọi từ đầu tới cuối (v0.2)

**Kịch bản S02:** A ở **TP.HCM, Viettel, 4G** gọi B ở **Hà Nội, VNPT, Wi-Fi**. Chế độ `post_answer`. Cuộc gọi thuộc thí nghiệm Geo vs Smart, nhánh Smart. Các con số dưới đây là **ví dụ minh họa**.

| Thời điểm (UTC) | Chuyện gì xảy ra | Bảng được ghi | Field đáng chú ý |
|---|---|---|---|
| 12:59:59.990 | Hệ thống gán nhánh | (nằm trong `call_session`) | `assignment_ts` ≤ `request_ts` đầu tiên (I15) |
| 13:00:00.000 | A bấm gọi | `call_session` | `call_id = C1`, `connection_mode = post_answer`, `experiment_id = exp-w4-geo-vs-smart`, `arm = smart`, `randomization_unit = run`, `experiment_cluster_id = sim_run_id`, `scenario_tag = S02_vn_cross_region` |
| 13:00:00.020 | Hỏi Selector cho phía A. Chưa biết B ở đâu | `selector_decision` (caller) | `phase = initial`, `info_level = caller_only`, `peer_ctx` toàn `unknown`, `policy_version = smart@0.3.1`, `feature_snapshot_id = feat-20261112-v1`; 4 TURN: SGN-VTL-01 (propensity 1.0), SGN-FPT-01, DAD-VTL-01, SG-SIN-01 |
| 13:00:00.100 | Điện thoại A xin chỗ trên TURN hạng 1 | `turn_allocation` (A) | `allocation_id = AL-A`, `ice_generation = 0`, `alloc_ms = 38` (gồm vòng 401 + xử lý), `success = true`, `error_code = none` |
| 13:00:00.900 | Máy B nhận lời mời, đổ chuông | `call_outcome.ring_ts` (ghi khi kết thúc) | `ring_ts = 13:00:00.900` |
| 13:00:04.000 | B bấm nghe. Giờ đã biết B ở Hà Nội | `call_outcome.answer_ts` | `answer_ts = 13:00:04.000` |
| 13:00:04.030 | Hỏi Selector cho phía B | `selector_decision` (callee) | `phase = refined`, `info_level = full`, hạng 1 là HAN-VNP-01 |
| 13:00:04.090 | Điện thoại B xin chỗ | `turn_allocation` (B) | `allocation_id = AL-B`, `alloc_ms = 41` |
| 13:00:04.150 | ICE bắt đầu kiểm tra | `ice_attempt` | `checks_start_ts = 04.150` (sau `answer_ts`, thỏa I5e) |
| 13:00:04.412 | ICE nối xong | `ice_attempt` | `ice_connected_ts = 04.412` → **neo cửa sổ**; `cst_technical = 262 ms`; `selected_local_candidate_type = relay`, `selected_remote_candidate_type = relay` → `path_type = relay_relay`; `relay_turn_caller = SGN-VTL-01`, `relay_turn_callee = HAN-VNP-01`; `caller_allocation_id = AL-A`, `callee_allocation_id = AL-B`; `rank_caller = 1`, `rank_callee = 1`; `attempt_seq = 1`, `ice_generation = 0` |
| 13:00:04.470 | DTLS xong | `ice_attempt` | `dtls_connected_ts = 04.470` |
| 13:00:04.540 | Gói media đầu tiên được nhận ở A | `call_stats_epoch` | `first_media_received_ts = 04.540` → `ttfm_post_answer = 540 ms` |
| Hết epoch 0 | Số đo chặng tóm tắt (6 dòng) | `path_leg_measurement` (`epoch_summary`, `inband`, `one_way`, `clock_sync_err_ms = 0.8`) | forward: A→SGN 9.1, SGN→HAN 13.8, HAN→B 2.3 (tổng 25.2 ms). reverse: B→HAN 2.5, HAN→SGN 14.2, SGN→A 10.9 (tổng 27.6 ms) |
| Hết epoch 0 | SDK hai bên gửi histogram | `call_stats_epoch` ×2 (audio) | Xem bên dưới |
| 13:03:08 | Cúp máy | `call_outcome` | `answered`, `connected`, `end_reason = normal_hangup`, `duration_s = 184`, `pair_group = VN_VN`, `n_ice_attempts = 1`, `stats_status = kept_sampled`, `stats_sampling_prob = 0.1`, `stats_sampling_reason = hash_sample` |

**Kiểm tra chéo I9 (WARN):** cả 3 chặng forward và 3 chặng reverse đều `one_way`, cùng cửa sổ, sai số đồng hồ 0.8 ≤ 2. Tổng forward + reverse = 25.2 + 27.6 = **52.8 ms**. `media_rtcp_rtt` (P50) của luồng A khoảng 51 ms. Lệch 1.8 ms, nằm trong ≤ 15 ms nên I9 thỏa. Lưu ý chiều reverse (27.6) lớn hơn chiều forward (25.2): đúng là mạng không đối xứng, nếu lấy RTT/2 = 25.5 làm "one-way" thì cả hai chiều đều bị đánh giá sai.

**Hai histogram của cuộc gọi.** Neo = 04.412, cuộc gọi kéo dài tới 13:03:08, tức 183.6 giây ≈ 36 cửa sổ 5 giây hoàn chỉnh.

| Metric | A (caller, 4G) | B (callee, Wi-Fi) |
|---|---|---|
| `media_rtcp_rtt_hist` (cửa sổ) | `<100`: 33, `100–200`: 3, còn lại 0 (tổng 36) | `<100`: 34 (tổng 34) |
| `rtt_windows_assessable` | 36 | 34 (2 cửa sổ chưa có RTCP RR hợp lệ) |
| `loss_hist` | `<1`: 31, `1–3`: 3, `3–5`: 2, `≥5`: 0 (tổng 36) | `<1`: 36 |
| `loss_windows_assessable` | 36 | 36 |
| `jitter_estimate_hist` | `<10`: 28, `10–30`: 7, `30–50`: 1, `≥50`: 0 (tổng 36) | `<10`: 35, `10–30`: 1 (tổng 36) |
| `jitter_windows_assessable` | 36 | 36 |

Kiểm tra I10: tổng mỗi histogram bằng đúng số cửa sổ assessable tương ứng.

**Cách tính PCR cho cuộc gọi này (§20.1):**
1. Cửa sổ tệ: RTT bucket ≥ 300 ms, loss bucket ≥ 3%, jitter bucket ≥ 30 ms.
2. Phía A: RTT tệ = 0 (không có bucket ≥ 300), mẫu số 36 → 0/36 = **0.000**. Loss tệ = 2 + 0 = 2, mẫu số 36 → 2/36 = **0.056**. Jitter tệ = 1 + 0 = 1 → 1/36 = **0.028**.
3. Phía B: RTT 0/34 = **0.000**; loss 0/36 = **0.000**; jitter 0/36 = **0.000**.
4. Điều kiện xác định: mọi mẫu số ≥ 4 → cả 6 PoorFraction đều xác định.
5. Không có PoorFraction nào ≥ 0.20 → `quality_poor = false`. Mọi metric của mọi bên xác định và < 0.20 → `quality_ok = true`, `quality_unknown = false`.
6. `end_reason = normal_hangup`, không `ice_failed`, không dropped → `poor(C1) = false`. `unclassifiable(C1)` = answered ∧ connected ∧ ¬dropped ∧ quality_unknown = **false**.
7. Cuộc gọi vẫn nằm trong cohort (mẫu số) của `pcr_itt_low` và `pcr_itt_high`, đóng góp 0 vào tử số của cả hai.

*Nếu* loss phía A có 8 cửa sổ tệ thay vì 2 thì PoorFraction = 8/36 = 0.222 ≥ 0.20 → `quality_poor = true` → `poor(C1) = true`, dù phía B hoàn hảo. Bên xấu hơn quyết định.

**Lấy mẫu diagnostic:** cuộc gọi bình thường (`normal_hangup`, 1 lần thử ICE, không fallback/restart) nên không thuộc tầng critical. Giả sử `u64(sha256(utf8(C1))[0:8]) mod 1000 = 73 < 100` → được giữ, `prob = 0.1`, nên `call_stats_5s` của C1 được lưu và dùng cho Decision Trace. Nó vẫn **không** được dùng để tính PCR (I16): PCR ở trên đọc `call_stats_epoch`. Với aggregate chẩn đoán, C1 mang trọng số 1/0.1 = 10.

**Sau đó, đêm hôm đó, pipeline của Hiệp:**
1. Gom các mảnh trên thành **một dòng** trong `fact_call`, tính PCR, `used_by_ice = true`/`match_method = id` cho cả hai allocation.
2. Cộng giá trị cấp cuộc gọi của C1 từ `epoch_summary` vào `feat_leg_stats` cho nhóm "Viettel miền Nam 4G → SGN-VTL-01". Event nào có `ingest_ts` sau cutoff 00:00 VN thì chờ snapshot sau (I13).
3. Xuất bản snapshot mới (`published_ts` sau cutoff). Từ thời điểm đó, thuật toán của Đoàn đọc snapshot mới; trước đó vẫn dùng snapshot cũ.

**Còn đường DAD×DAD mà chưa ai đi?** Pipeline ghép số đo chặng "Viettel miền Nam → DAD" với "VNPT Hà Nội → DAD" từ các cuộc gọi khác để ước lượng.

---

## 23. Câu hỏi thường gặp: "Sao không làm cách khác?"

**Sao không gộp hết vào một bảng `calls` cho dễ?**
Ngoài đời không hệ thống nào biết hết mọi thứ cùng lúc. Signaling biết lúc bấm gọi, điện thoại biết lúc nối, TURN biết tải. Gộp chung còn **mất dấu các bước bị đứt**. Bảng một dòng mỗi cuộc gọi **vẫn có** (`fact_call`), do pipeline ráp lại.

**Sao số đo chặng không lưu thành 3 cột `leg1`, `leg2`, `leg3`?**
Vì có số đo không thuộc cuộc gọi nào (probe), và vì phải ghép chặng giữa các cuộc gọi để ước lượng đường chưa đi.

**Sao phải tách `answered` và `connected`, và thêm cả `ring_ts`?**
Người ta không bắt máy vì đang bận, không phải vì TURN tệ. `ring_ts` cho biết lời mời có tới nơi không: không tới là lỗi hạ tầng (`invite_undelivered`), tới mà không bắt là chuyện người dùng. Còn `answer_ts` là lúc người dùng **bấm nghe**, không phải lúc có SDP Answer, để mốc đúng với cảm nhận.

**Sao cần cả `event_ts` lẫn `ingest_ts`?**
Đồng hồ điện thoại có thể sai, sự kiện có thể tới trễ nhiều giờ. `ingest_ts` còn là mốc "hệ thống biết" để chặn rò rỉ tương lai (I13).

**Sao không điền 0 cho số đo bị thiếu?**
0 ms và 0% loss là kết quả hoàn hảo. Cuộc gọi lỗi mà bị điền 0 sẽ làm TURN tệ trông như TURN tốt nhất.

**Sao phải lưu `propensity` khi thuật toán luôn chọn hạng 1?**
Khi bật exploration, xác suất là thứ duy nhất cho phép sửa độ lệch trong đánh giá. Thêm về sau rất tốn công vì dữ liệu cũ không có.

**Sao thuật toán chỉ đọc snapshot, và vì sao snapshot không được sửa?**
Ngoài đời không ai biết trước tương lai. Nếu snapshot sửa được, không chứng minh được thuật toán đã không nhìn thấy dữ liệu của tương lai. Cần sửa thì tạo version mới.

**Sao PCR mà không phải PNR (tỉ lệ không nối được/kém)?**
PNR chỉ tính trên cuộc gọi đã connected, nên một policy làm cho nhiều cuộc gọi khó nối bị loại ra khỏi mẫu số thì PNR của nó trông đẹp. PCR (ITT) tính trên mọi cuộc gọi đã gán nhánh, và đếm cả lỗi ICE, rớt, lẫn chất lượng tệ trong một con số. PNR còn có trong danh sách chẩn đoán nhưng không dùng để phán thắng thua.

**Sao dùng ITT mà không chỉ tính cuộc gọi thực sự đi qua TURN?**
Vì "đi qua TURN" là kết quả sau quyết định, có thể bị chính policy ảnh hưởng. Loại các cuộc gọi sau khi đã biết kết quả (Selector timeout, static fallback, P2P) tạo ra thiên lệch chọn lọc. ITT giữ nguyên cohort từ lúc gán nhánh, nên so sánh công bằng.

**Sao `pcr_itt` có hai cận (low/high)?**
Vì một phần cuộc gọi không phân loại được do thiếu số đo. Chọn "tính là tốt" hay "tính là tệ" đều là giả định. Báo cả hai, và chỉ kết luận mạnh khi đúng ở cả hai (so chéo `high(Smart)` với `low(Geo)`).

**Sao gộp histogram theo cửa sổ mà không lấy max P95 theo epoch?**
Max của P95 các epoch bị chi phối bởi một epoch xấu duy nhất, và lấy P95 xong rồi trung bình/max các P95 là sai thống kê. Đếm tỉ lệ cửa sổ tệ (PoorFraction) phản ánh "bao nhiêu phần thời gian người dùng bị tệ", cộng được qua epoch và qua cuộc gọi. `max_epoch_p95` chỉ còn là chẩn đoán.

**Sao nhãn dùng RTT của media chứ không dùng one-way của số đo chặng?**
RTT media (`media_rtcp_rtt`) đo được chỉ bằng một đồng hồ, trên chính luồng người dùng nghe, nên không cần đồng bộ đồng hồ. One-way cần hai đồng hồ khớp nhau nên kém tin cậy, và số đo chặng lại là thứ thuật toán cố dự đoán (dùng làm nhãn là tự chấm bài). Cũng không thể suy one-way từ RTT bằng cách chia đôi, vì mạng không đối xứng.

**Sao `alloc_ms` không được coi là RTT hay one-way?**
Allocation gồm ít nhất hai vòng đi-về (vòng 401 xác thực rồi gửi lại) cộng thời gian server xử lý, nên lớn hơn RTT thật, và phụ thuộc cả tải server. Coi nó là số đo chặng sẽ ước lượng chặng bị lệch. Nó chỉ đi vào `feat_turn_alloc_latency`.

**Sao không dùng một tỉ lệ lấy mẫu chung cho mọi cuộc gọi?**
Cuộc gọi lỗi là thứ cần điều tra nhất; nếu dùng chung một tỉ lệ thì phần lớn cuộc gọi lỗi mất chi tiết. Nên lỗi giữ 100% (critical), cuộc gọi thường mới chọn theo hash. Cái giá là tập chi tiết lệch về phía cuộc gọi lỗi, và đây là lý do KPI không đọc nó mà đọc `call_stats_epoch` gửi 100%.

**Sao chọn bằng hash của `call_id` mà không bốc thăm ngẫu nhiên?**
Hash tất định kiểm tra lại được (I17) và không phụ thuộc may rủi lúc chạy. Cũng vì thế phải cố định thuật toán băm (SHA-256, 8 byte đầu, big-endian) và cấm `hash()` của ngôn ngữ.

**Sao tính độ bất định theo seed mà không theo từng cuộc gọi?**
Các cuộc gọi trong một lần chạy dùng chung TURN và tải, nên không độc lập. Bootstrap theo cuộc gọi coi chúng độc lập và cho khoảng tin cậy hẹp giả tạo. Mỗi seed là một thế giới độc lập thật.

**Sao không chia cuộc gọi ngẫu nhiên làm hai nhóm Geo/Smart chạy cùng một môi trường?**
Vì hai nhóm chia sẻ TURN: Smart dồn người vào một TURN làm TURN đó chậm đi ảnh hưởng cả Geo. Do đó mỗi policy phải chạy trong môi trường cô lập riêng (cùng yếu tố ngoại sinh), và ở production dùng switchback theo vùng/khối thời gian.

**Sao RNG phải "có khóa" mà không chỉ tách luồng cho từng loại?**
Xem §21.2: luồng tuần tự vẫn bị xê dịch khi hai policy sinh số event khác nhau. RNG có khóa theo (seed, thực thể, thời điểm) cho cùng giá trị bất kể số event khác.

**Sao không đổi mẫu số (ví dụ chỉ tính cuộc gọi đã bắt máy) sau khi kiểm tra thấy hai nhánh không cân bằng?**
Đổi mẫu số sau khi đã thấy dữ liệu là tự do chọn kết quả (p-hacking). Kiểm tra cân bằng (ví dụ `answer_rate` theo nhánh) vẫn được làm và báo cáo, nhưng nó chỉ diễn giải thêm cho `pcr_answered`, **không bao giờ** thay metric chính. Metric chính và luật kết luận đóng băng trước benchmark.

**Sao có hai cận cho luật kết luận mà không dùng một ngưỡng hòa?**
Vì ta muốn kết luận "tốt hơn" chỉ khi đúng ngay cả trong kịch bản bất lợi nhất cho Smart, và "tệ hơn" chỉ khi đúng ngay cả trong kịch bản thuận lợi nhất cho Smart. Còn lại là INCONCLUSIVE.

**Sao khả thi của regret xác định theo sự thật mà không theo health snapshot?**
Snapshot là niềm tin của Selector. Dùng niềm tin của Selector làm thước đo khả thi sẽ "tha" cho chính các sai lầm của nó (loại oan một TURN khỏe khỏi tập so sánh).

**Sao ngưỡng 300 ms không lấy từ G.114?**
G.114 nói về độ trễ một chiều, còn ngưỡng ở đây áp cho RTT, mà RTT không quyết định từng chiều. Nên contract gọi đây là SLO nội bộ tạm thời, đóng băng trước benchmark, và thử nhạy 200/300/400.

**Sao thêm `pre_connect` vào sensitivity mà không chỉ chạy `post_answer`?**
Vì `post_answer` là giả định chưa xác minh (Q5). Nếu hệ thống thật chạy ICE lúc đổ chuông thì tải TURN, lượng allocation và mốc thời gian đều khác; thứ hạng policy có thể đổi. Phải chạy lại toàn bộ, không chỉ đổi nhãn.

**Sao API Selector không nhận tham số ngẫu nhiên từ client?**
Xem §18.2.

**Sao TURN dùng mã IATA thành phố mà không ghi tên tỉnh?**
Mã ngắn, chuẩn quốc tế, không bị lỗi dấu tiếng Việt, dùng được cho TURN quốc tế.

**Contract nhiều bảng như vậy có quá nặng cho 6 tuần không?**
Simulator sinh tất cả bảng từ cùng một mô hình nên thêm bảng không tốn nhiều công. Mỗi bảng ứng với đúng một hệ thống ngoài đời, nên lúc pilot chỉ cần nối từng nguồn vào đúng bảng của nó.

---

## 24. Bảng tra nhanh: yêu cầu đề bài → lấy từ đâu (v0.2)

| Yêu cầu | Bảng · field |
|---|---|
| TURN VN theo miền / ISP / TURN Server / Network / thời gian | `ctx.vn_region`, `ctx.isp`/`asn`, `turn_id`, `ctx.network_type`, `event_ts` |
| TURN quốc tế theo Country / Region / TURN Location | `ctx.country`, `dim_turn.country`/`city` |
| User ở nước có và không có TURN | `ctx.country` so với danh sách `dim_turn.country` |
| VN↔VN, VN↔Quốc tế, Quốc tế↔Quốc tế | `call_outcome.pair_group` |
| Allocation Success | `turn_allocation.success`, `error_code`; `feat_turn_alloc_latency.alloc_success_rate` |
| Độ trễ cấp chặng, P50/P95 | `path_leg_measurement.value_ms` + `measurement_kind` + `granularity = epoch_summary`; `feat_leg_stats.p50`/`p95` |
| Độ trễ allocation | `turn_allocation.alloc_ms`; `feat_turn_alloc_latency.alloc_ms_p50`/`p95` (không phải độ trễ chặng) |
| Failure Rate, Connection Success | `call_outcome.answered`, `connected`, `end_reason`; KPI `ice_fail_rate`, `invite_delivered_rate`, `answer_rate` |
| **Chất lượng cuộc gọi tổng thể (metric chính)** | **`pcr_itt_low`/`pcr_itt_high`** từ `call_session` (cohort) + `call_outcome` + `call_stats_epoch` |
| Stability, Health, Usage | `turn_health_1m`, `feat_turn_health.stability_cv_24h` |
| TURN được xếp hạng so với TURN ICE thực dùng | `selector_decision.candidates` so với `ice_attempt.relay_turn_*`, `rank_*`, `*_allocation_id` |
| Kiểu đường (relay / P2P) | `ice_attempt.selected_*_candidate_type` → `path_type` |
| Geo Baseline so với Historical / Smart | `call_session.arm`, `selector_decision.policy_version`; luật kết luận §21.4 |
| Availability, API Latency, Error, Fallback, Freshness | `service_health_1m` |
| CST (thiết lập kỹ thuật) | `ice_attempt.ice_connected_ts − checks_start_ts` (KPI `cst_technical_p95`) |
| TTFM | `call_stats_epoch.first_media_received_ts` − `call_outcome.answer_ts` (KPI `ttfm_post_answer_p95`) |
| RTT, Packet Loss, Jitter | `call_stats_epoch.media_rtcp_rtt_hist`, `loss_hist`, `jitter_estimate_hist` (KPI-grade); `call_stats_5s` (chi tiết, lấy mẫu) |
| Drop Rate | `call_outcome.dropped`; KPI `drop_rate` |
| Decision Trace theo Call ID | Mọi bảng sự kiện, nối qua `call_id`; chi tiết từng cửa sổ ở `call_stats_5s` (nếu được lấy mẫu) |
| TURN Failure | `selector_decision.filtered_out`, `turn_health_1m`, `ice_attempt.trigger = fallback` |
| Cold-start | `feat_*.segment_level`, `n_eff`, `selector_decision.fallback_reason` |
| Network Change | `ice_attempt.network_epoch`, `trigger = restart_network_change`, `ice_generation`; `call_stats_epoch.network_epoch` |
| Phân biệt dữ liệu thật và giả lập | `data_source` |
| Confidence | `selector_decision.confidence` |
| Thí nghiệm / gán nhánh | `call_session.experiment_id`, `arm`, `assignment_ts`, `randomization_unit` |
| Dữ liệu chi tiết có được lưu không | `call_outcome.stats_status`, `stats_sampling_prob`, `stats_sampling_reason` |
| Tái lập một lần chạy sim | `run_manifest` (qua `sim_run_id`) |
| Đánh giá đường chưa đi (sim) | `truth_leg_5m` (chỉ `eval/`), regret §21.6 |
| Chất lượng dữ liệu | `dq_results` (bất biến I1–I17) |
