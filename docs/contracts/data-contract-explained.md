# Giải thích Data Contract v0.4.0 — từng bảng, từng field, vì sao chọn như vậy

> **Tài liệu này dành cho ai?** Cho mọi người: Đoàn, mentor, người mới vào dự án, kể cả người chưa từng làm WebRTC.
> **Quan hệ với contract:** `data-contract.md` (v0.4.0) là bản **chuẩn** (luật). Tài liệu này giải thích v0.4.0 và là bản **giải thích** (vì sao có luật đó). Nếu hai bản khác nhau, **`data-contract.md` thắng**.
> **Phiên bản cũ:** v0.1.0 đã bị thay hoàn toàn. Mọi định nghĩa của v0.1 không còn trong contract coi như đã hủy. Chỗ nào tài liệu này nhắc tới thứ cũ thì sẽ ghi rõ là "đã bỏ".
> **v0.3.0 so với v0.2.0:** chỉ **bổ sung**, không đổi định nghĩa nào đã đóng băng: kiến trúc hai mặt phẳng (BE signaling tách khỏi đường media, §2A), chính sách ICE `ice_transport_policy`, các field đo phần signaling, bất biến I18 và ba chỉ số chẩn đoán mới.
> **v0.4.0 so với v0.3.0:** cũng chỉ **bổ sung** (MINOR), để dữ liệu không sai khi đem ra production (§2B): thông tin client (`platform`, `app_version`, `device_id`…), IP của máy chủ TURN (`dim_turn_endpoint`, `turn_url`, `turn_server_ip`, `relayed_ip`) và `actual_turn_id`, nhiều thiết bị cùng đổ chuông, `call_type` cho cuộc gọi nhóm, hai cách cung cấp `call_stats_epoch` (`derivation`), bất biến I19–I22, check DQ `release_regression`, KPI chẩn đoán `turn_identity_mismatch_rate`, kịch bản S21–S25, câu hỏi mở Q9–Q12. Ngoài ra v0.4.0 (cùng số version) **gồm các sửa lỗi theo một đợt audit độc lập**, và một số sửa **đổi nghĩa** so với bản nháp v0.4.0 trước đó (tài liệu này đã cập nhật theo bản hiện hành):
> - **Poor chia thành ba nhánh rời nhau** (`setup_fail`, `drop`, `quality_bad`), và cuộc gọi **đã bắt máy mà không bao giờ nối được** giờ được tính là poor (§20.1, FAQ §23).
> - Guardrail `ice_fail_rate` đổi thành `setup_fail_rate`; `ice_fail_rate` và `setup_abandon_rate` là hai thành phần của nó.
> - KPI chỉ tính cuộc gọi 1-1 (§20, I21): đây là chỗ **làm rõ phạm vi**. Trên simulator kết quả không đổi vì mọi cuộc gọi mô phỏng đều là 1-1.
> - Thêm I23, I24; viết lại I3, I4, I6, I8, I9, I10, I16, I17, I21, I22 (§14); quy tắc cửa sổ 5 giây chặt hơn (§10.4); khóa không bao giờ null (§4); thứ tự xác định máy TURN thực (§16.6); các định nghĩa thống kê của feature store (§17).

**Cách đọc:**
- Người mới: đọc §1 → §2 → §2A (BE và đường media) → §2B (production khác simulator thế nào) → §3 (hai loại dữ liệu) → §22 (đi qua một cuộc gọi), các phần còn lại tra khi cần.
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
| **BE** | Backend Spring Boot của công ty, **chỉ làm signaling**. Chuyển lời mời, SDP, ICE candidate giữa A và B, và gọi Selector. **Media không đi qua BE** (§2A) |
| **ICE transport policy** | Cấu hình ICE: chỉ dùng relay (`relay`) hay cho phép cả nối thẳng (`all`). Xem §6 |
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
| **Danh mục** (dimension) | `dim_turn`, `dim_turn_endpoint` (mới ở v0.4.0), `dim_asn`, `dim_user` | Ít thay đổi. Mô tả "ai, cái gì" |
| **Sự kiện** (event) | `call_session`, `selector_decision`, `turn_allocation`, `ice_attempt`, `ice_candidate_pair` (tùy chọn), `path_leg_measurement`, `call_stats_epoch`, `call_stats_5s`, `call_outcome`, `turn_health_1m`, `service_health_1m` | Chỉ ghi thêm, không sửa. Mô tả "chuyện gì đã xảy ra, lúc nào" |
| **Run manifest** | `run_manifest` | Một file JSON mô tả mỗi lần chạy simulator / mỗi experiment, commit cùng kết quả |
| **Feature store** | `feat_*` | Pipeline tính từ sự kiện. Thuật toán đọc |
| **Ẩn** (chỉ simulator) | `truth_leg_5m`, `incident_truth`, `dirt_log` | "Đáp án", chỉ dùng để chấm điểm |

Sơ đồ quan hệ (rút gọn): một `call_session` có nhiều `selector_decision`; mỗi decision có nhiều `turn_allocation`; một call có nhiều `ice_attempt`, nhiều `path_leg_measurement`, nhiều `call_stats_epoch`; và đúng một `call_outcome`. Số đo `path_leg_measurement` từ probe thì không thuộc call nào (`call_id = null`).

---

## 2A. Hai mặt phẳng: BE (signaling) và đường media (mới ở v0.3.0, contract §0.2)

Đã xác nhận ngày 2026-11-04: **BE** (backend Spring Boot của công ty) **chỉ làm signaling**. Media **không** đi qua BE. Hai việc chạy trên hai "mặt phẳng" khác nhau:

```
 MẶT PHẲNG ĐIỀU KHIỂN — đi qua BE (backend signaling, Spring Boot)
   A ⇄ BE ⇄ B       lời mời, đổ chuông, bắt máy, SDP offer/answer, ICE candidate
   BE → Selector    lúc A bấm gọi (initial) và lúc máy B đổ chuông (refined)

 MẶT PHẲNG MEDIA — KHÔNG đi qua BE (một PeerConnection A↔B)
   A → TURN(A) → TURN(B) → B        relay_relay
   A → TURN(X) → B                  relay_same (hai bên dùng chung một TURN)
   A → TURN(A) → B  ·  A → B        relay_direct · P2P — chỉ khi ice_transport_policy = all
```

Hiểu đơn giản: BE giống "tổng đài" nối máy, còn tiếng nói đi trên đường dây riêng giữa hai điện thoại (qua TURN), không đi qua tổng đài. Trong contract, BE là producer `signaling`: tạo `call_session`, gán nhánh thí nghiệm, gọi Selector và ghi `selector_decision`, ghi `ring_ts` và `answer_ts`.

### 2A.1 BE ảnh hưởng gì, và không ảnh hưởng gì?

- **Không ảnh hưởng chất lượng media.** BE không nằm trên đường media nên không cộng gì vào RTT, loss, jitter, và **không thể làm đổi `pcr_itt`**. *Vì sao quan trọng:* đổi chỗ đặt BE hay BE chậm đi không được phép làm thuật toán chọn TURN trông tốt hơn hay tệ hơn.
- **Chỉ ảnh hưởng thời gian thiết lập cuộc gọi**, vì mọi tin nhắn signaling đều đi A → BE → B. Với `post_answer`, sau khi B bấm nghe cần **ít nhất một lượt tin nhắn B → BE → A** thì ICE mới bắt đầu kiểm tra được. Lượt đó mất khoảng:

  `(RTT(A↔BE) + RTT(B↔BE)) / 2 + thời gian BE xử lý`

- **Ví dụ minh họa (là ước tính từ bảng đo WonderNetwork trong `docs/research/01`, KHÔNG phải số đo thật):**

| Tình huống | Ước tính một lượt B → BE → A |
|---|---|
| Cuộc gọi trong nước, BE đặt ở VN | vài chục ms, đã tính cả mạng truy cập 4G |
| Cuộc gọi Nhật ↔ Đức, BE đặt ở Hà Nội (HN↔Tokyo RTT 93 ms, HN↔Frankfurt RTT 189 ms) | ≈ (93 + 189) / 2 ≈ **141 ms** |

  *Vì sao ví dụ thứ hai đáng chú ý:* BE ở xa cả hai người gọi thì mỗi lượt signaling tốn khoảng 141 ms. Con số này nằm trong thời gian thiết lập, **không** nằm trong chất lượng tiếng.
- **Đánh thức máy bằng push notification** (khi B đang chạy nền) ảnh hưởng **thời gian đổ chuông** (`ring_ts`), không ảnh hưởng thời gian thiết lập sau khi bắt máy.

### 2A.2 Selector được gọi lúc nào, chậm thì sao?

BE gọi Selector hai lần: lúc A bấm gọi (`initial`) và lúc máy B đổ chuông (`refined`). Ở `post_answer`, độ trễ của Selector **nằm gọn trong vài giây đổ chuông** nên người dùng gần như không thấy. Vì vậy guardrail `selector_api_p95` chủ yếu bảo vệ trước **timeout / `static_fallback` và năng lực chịu tải của dịch vụ**, không phải thời gian thiết lập mà người dùng cảm nhận. Còn I14 (§14) bảo đảm BE không chờ Selector rồi mới gửi lời mời. Lưu ý `api_latency_ms` trong `selector_decision` do **BE** đo, vì BE là bên gọi Selector.

### 2A.3 Số đo media nghĩa là gì khi chỉ có một PeerConnection?

Vì chỉ có **một PeerConnection A↔B**, `media_rtcp_rtt` và `ice_stun_rtt` là RTT **đầu-cuối qua cả hai TURN** (A → TURN(A) → TURN(B) → B và về). `packetsLost` và `jitter` ở phía nhận phản ánh **toàn đường** (`docs/research/06`). *Vì sao quan trọng:* một con số RTT/loss/jitter không tách được riêng "nửa của TURN A" hay "nửa của TURN B". Muốn tách thì dùng `path_leg_measurement`.

### 2A.4 Hai bên ràng buộc nhau ở đâu?

Lựa chọn TURN của caller và callee chỉ ràng buộc nhau qua **chặng giữa `TURN(A) → TURN(B)`** (hoặc trường hợp dùng chung một TURN). Cuộc gọi nội địa có chặng giữa nhỏ, nên chọn TURN gần nhất cho từng bên là xấp xỉ tốt. Cuộc gọi xuyên lục địa (Nhật ↔ Đức) có chặng giữa lớn, nên cần **xếp hạng kết hợp (joint ranking)** hai bên cùng lúc (`docs/research/07` §3.1).

### 2A.5 Nếu sau này media đi qua SFU thì sao?

Khi đó mỗi bên sẽ có PeerConnection riêng tới media server, các số đo RTT/loss/jitter chỉ còn phản ánh **nửa đường**, và định nghĩa PCR phải đổi. Đó là thay đổi **MAJOR**, phải mở version contract mới (`docs/research/05`, `/06` đã phân tích sẵn). Contract hiện hành (v0.4.0) **không** hỗ trợ kiểu này.

---

## 2B. Sẵn sàng cho production (mới ở v0.4.0, contract §0.3)

Simulator có thể giả định mọi thứ đồng nhất: một loại app, một hostname một máy, một thiết bị mỗi người, chỉ có cuộc gọi 1-1. **Production không như vậy.** Contract v0.4.0 ghi nhận 5 điều ngoài đời để dữ liệu thật không bị đọc sai. Cả năm đều chỉ **bổ sung** field, không đổi định nghĩa cũ. Các câu chuyện dưới đây là **ví dụ minh họa tự đặt**, không phải sự cố có thật.

| # | Ngoài đời | Contract xử lý bằng |
|---|---|---|
| 1 | Nhiều nền tảng, phiên bản app/SDK, OS, thiết bị; getStats khác nhau giữa các nền tảng | Thông tin client trong `ctx` (§8). KPI cắt được theo `platform`, `app_version`. DQ `release_regression` (§16.5) |
| 2 | Một hostname TURN có thể trỏ tới nhiều máy | `turn_url` + IP thật, `dim_turn_endpoint` (§7.4), `actual_turn_id` (§16.6), I19 |
| 3 | Người nghe có nhiều thiết bị cùng đổ chuông | `device_id` ở mọi bảng phía client, `answered_device_id`, I20 |
| 4 | Có cuộc gọi nhóm, hoặc 1-1 chuyển thành nhóm giữa chừng | `call_type`, `converted_to_group`, `converted_ts`, I21 |
| 5 | SDK có thể không tự tính được histogram theo epoch | `derivation` (`sdk` hoặc `pipeline`), I22 |

### 2B.1 Điều 1: app và nền tảng không giống nhau

**Chuyện minh họa.** Bản Android 3.12.0 phát hành thứ Hai. Do một lỗi, bản này tính `inbound-rtp.jitter` sai (ví dụ quên đổi đơn vị), nên mọi cuộc gọi có người dùng Android 3.12.0 đều có histogram jitter rơi vào bucket `≥50` ms. Thứ Ba, dashboard thấy PCR của cuộc gọi đi qua TURN SGN tăng vọt, và đội vận hành bắt đầu điều tra SGN. Nhưng SGN không hỏng: chỉ vì phần lớn user miền Nam dùng Android và cập nhật bản mới.

**Cách contract chặn.** Mỗi bên ghi `platform`, `app_version`, `sdk_version`, `device_model` (trong `ctx`). Mọi KPI cắt được theo `platform` / `app_version` / `device_class`. Check DQ `release_regression` cắm cờ WARN khi một metric lệch đột ngột **ngay sau** một bản phát hành. Nhờ đó nhìn ra "lỗi nằm ở app 3.12.0" thay vì đổ nhầm cho TURN. Ngoài ra mỗi nền tảng hỗ trợ getStats khác nhau (web khác iOS khác Android), nên biết `platform` cũng giúp hiểu vì sao một field bị `null`.

### 2B.2 Điều 2: hostname không phải là máy

**Chuyện minh họa.** Công ty cấp cho client `turn:turn-pool-sgn.example:3478`, một hostname chung trỏ tới ba máy SGN-1, SGN-2, SGN-3 (DNS round-robin hoặc geo-DNS). Selector chọn SGN-1, nhưng DNS trả về IP của SGN-3. Nếu pipeline chỉ tin "Selector chọn SGN-1 thì cuộc gọi đi SGN-1" thì mọi số đo của SGN-3 bị ghi cho SGN-1: SGN-3 quá tải thì SGN-1 bị chê, thuật toán học sai, và không ai biết vì hostname trông giống nhau.

**Cách contract chặn.** Lưu `turn_url` (client thực sự dùng gì) và **IP thật** (`turn_server_ip`, `relayed_ip`). Bảng `dim_turn_endpoint` ánh xạ IP → máy (`turn_id`). Pipeline tính `actual_turn_id` theo thứ tự ưu tiên IP rồi tới hostname (§16.6). Nếu máy suy ra khác máy Selector chọn thì ghi `turn_identity_mismatch` (I19). Đây là một **phát hiện vận hành** ("DNS đang đưa client tới máy khác với dự định"), không phải dữ liệu sai.

### 2B.3 Điều 3: người nghe có nhiều thiết bị

**Chuyện minh họa.** B có điện thoại và bản web đang mở. Cả hai đổ chuông, BE hỏi Selector cho cả hai thiết bị và hai thiết bị đều xin allocation. Bản web bấm nghe. Nếu pipeline ghép "decision của callee" với attempt chỉ theo `call_id` + `side`, nó có thể ghép nhầm decision và allocation của **điện thoại** (không bắt máy) vào kết nối của **web**: sai hạng TURN, sai khả năng "TURN được đề xuất có được dùng không", và allocation của điện thoại bị tính là "đã dùng".

**Cách contract chặn.** `device_id` có mặt ở decision, allocation, attempt, số đo chặng, stats. `call_outcome.answered_device_id` ghi thiết bị đã bắt máy, `n_devices_rung` ghi số thiết bị đã đổ chuông. Mỗi thiết bị của B đang đổ chuông có **request `refined` riêng và `decision_id` riêng**, nên không có chuyện hai thiết bị dùng chung một decision. Allocation của thiết bị không bắt máy có `release_reason = other_device_answered`. I20 buộc attempt `connected` phải có `callee_device_id = answered_device_id`.

### 2B.4 Điều 4: cuộc gọi nhóm và SFU

**Chuyện minh họa.** Có thêm tính năng gọi nhóm chạy qua SFU (media server). Ở đó mỗi người có PeerConnection riêng tới SFU, nên RTT, loss, jitter chỉ phản ánh **nửa đường** (§2A.5). Nếu cuộc gọi nhóm lọt vào `pcr_itt`, số RTT "nửa đường" bị trộn với RTT "cả đường" của cuộc gọi 1-1, và PCR không còn nghĩa. Tệ hơn: một cuộc gọi 1-1 được nâng lên thành nhóm giữa chừng, nửa sau cuộc gọi đi qua SFU.

**Cách contract chặn.** `call_session.call_type` (`one_to_one` / `group`); `converted_to_group` và `converted_ts` trong `call_outcome`. KPI **chỉ** tính cuộc gọi `one_to_one`; với cuộc gọi đã chuyển thành nhóm, mọi cửa sổ sau `converted_ts` không đánh giá được (I21). Lưu ý: contract **chưa** hỗ trợ SFU (đó vẫn là thay đổi MAJOR); nó chỉ bảo đảm cuộc gọi nhóm **không làm bẩn** KPI hiện có.

### 2B.5 Điều 5: SDK không tự tính được histogram

**Chuyện minh họa.** Thiết kế ban đầu: SDK tự tính `call_stats_epoch` (các histogram) ngay trên điện thoại. Nhưng đội mobile báo: gói SDK hiện tại chưa tính được histogram theo cửa sổ neo cố định, chỉ có thể gửi getStats thô. Nếu contract bắt buộc histogram từ SDK thì không có dữ liệu KPI-grade.

**Cách contract chặn.** Cho **hai cách** cung cấp `call_stats_epoch`, phân biệt bằng `derivation`: `sdk` (SDK tự tính) hoặc `pipeline` (SDK gửi `call_stats_5s` cho **100%** cuộc gọi, pipeline tự dựng histogram theo đúng cùng quy tắc). Lúc đó `call_stats_5s` của endpoint đó được gửi 100% (`stats_sampling_reason = raw_full` khi mọi endpoint của cuộc gọi đều `pipeline`), **không qua ring buffer và không lấy mẫu**, nên I22 yêu cầu mọi cửa sổ đã gửi phải có mặt (cửa sổ thiếu chỉ được do gửi thất bại, và `measurement_coverage` phản ánh). Một cuộc gọi có thể có một endpoint `sdk` và một endpoint `pipeline`. Hai cách phải cho kết quả **giống hệt** trên cùng dữ liệu (test derivation-equivalence). Cái giá của `pipeline` là tốn băng thông hơn, bù lại không phụ thuộc SDK.

### 2B.6 Quy tắc IP: IP máy chủ TURN được lưu, IP người dùng thì không

| Loại IP | Lưu không | Lý do |
|---|---|---|
| IP của **máy chủ TURN** (`turn_server_ip`, `relayed_ip`, `relayed_ip_caller/callee`, `dim_turn_endpoint.ip`) | **Có** | Là hạ tầng của công ty, không phải dữ liệu cá nhân. Cần để biết chính xác client đã tới máy nào |
| IP của **người dùng** (candidate `host`, `srflx`, `prflx`) | **Không bao giờ** | Là dữ liệu cá nhân. Quy tắc "không lưu IP thô" (§4) giữ nguyên |

`ice_attempt.relayed_ip_*` **chỉ ghi khi candidate là `relay`**, vì địa chỉ của candidate `relay` là địa chỉ **trên máy TURN**. Nếu candidate là `host` / `srflx` / `prflx` thì không được ghi IP, dù trường đó tồn tại. Cũng **không lưu `relatedAddress` / `relatedPort`** của candidate (hai trường này chứa IP người dùng). Log của TURN server có IP client, nên chỉ được trích IP của chính server. Mọi ví dụ IP trong tài liệu này lấy từ dải dành riêng cho tài liệu (RFC 5737: `192.0.2.x`, `198.51.100.x`, `203.0.113.x`), không phải IP thật.

---

## 3. Hai loại dữ liệu: KPI-grade và diagnostic (phần quan trọng nhất của v0.2)

Vấn đề của v0.1: mọi số đo chất lượng nằm trong `call_stats_5s`, mà bảng này chỉ lưu một phần cuộc gọi. Nếu phần được lưu không đại diện cho toàn bộ (ví dụ cuộc gọi lỗi được lưu nhiều hơn), KPI sẽ **lệch mà không ai biết**. v0.2 chia dữ liệu làm hai loại:

| Loại | Bảng | Độ phủ | Được dùng cho |
|---|---|---|---|
| **KPI-grade** | `call_session`, `selector_decision`, `turn_allocation`, `ice_attempt`, `call_outcome`, `call_stats_epoch`, `path_leg_measurement` với `granularity = epoch_summary`, `turn_health_1m`, `service_health_1m` | **100% cuộc gọi** | Mọi KPI chính và guardrail (§20), feature store (§17) |
| **Diagnostic** | `call_stats_5s` (trừ khi endpoint đó có `derivation = pipeline`, xem dưới), `path_leg_measurement` với `granularity = window_5s`, `ice_candidate_pair` | Lấy mẫu (§13.3) hoặc tùy telemetry | Điều tra, Decision Trace, biểu đồ chi tiết. **Không bao giờ** dùng cho KPI quyết định |

**Ngoại lệ v0.4.0:** khi một endpoint có `derivation = pipeline`, `call_stats_5s` của endpoint đó được gửi 100% và là **đầu vào** để pipeline dựng `call_stats_epoch` (KPI-grade). Khi đó nó không còn là dữ liệu lấy mẫu. Bất biến I16 kiểm tra ở **cấp dòng**: một dòng `call_stats_5s` chỉ được làm đầu vào KPI nếu endpoint của dòng đó là `pipeline`.

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
| **Cột nằm trong khóa không bao giờ null** (v0.4.0) | `'unknown'` = không biết; `'-'` = không áp dụng. Ví dụ `device_id` của chặng `turn_turn` là `'-'` | Trong SQL, `NULL` không bằng `NULL`, nên hai dòng khóa chứa null không bao giờ "trùng nhau": dedup và join sẽ im lặng sai. Dùng giá trị thật thì khóa so sánh được |

---

## 5. Các cột có ở mọi bảng sự kiện

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `event_id` | Mã duy nhất của **một** sự kiện | `0193…e7` | Mạng chập chờn khiến điện thoại gửi lại cùng một sự kiện 2 lần. Có mã thì pipeline **loại được bản trùng** (I11) |
| `contract_version` | Dòng này theo phiên bản contract nào (version contract mà producer dùng khi ghi) | `0.4.0` | Khi contract nâng cấp, pipeline biết dòng cũ hay mới để đọc cho đúng |
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
| `platform` (mới ở v0.4.0) | `ios`, `android`, `web`, `desktop`, `unknown` | getStats khác nhau giữa các nền tảng, và lỗi của một bản app thường chỉ nằm ở một nền tảng. Cắt KPI theo nền tảng để tách lỗi app khỏi lỗi TURN (§2B.1) |
| `call_type` (mới ở v0.4.0) | `one_to_one` = cuộc gọi 1-1; `group` = cuộc gọi nhóm; `unknown` = dữ liệu cũ (giá trị mặc định, field không null) | Chỉ `one_to_one` vào KPI (I21). Cuộc gọi nhóm qua SFU có số đo "nửa đường", trộn vào sẽ làm sai PCR (§2B.4) |
| `stats_derivation` (mới ở v0.4.0) | `sdk` = SDK tự tính histogram trên thiết bị; `pipeline` = SDK gửi `call_stats_5s` 100%, pipeline tính histogram | Cho phép nền tảng chưa tính được histogram vẫn cung cấp dữ liệu KPI-grade (§2B.5). Dữ liệu cũ (v0.2/v0.3) mặc định `sdk`, `window_s` mặc định 5 |
| `conn_state` (mới ở v0.4.0) | `connected`, `disconnected`, `failed` | Trạng thái kết nối trong một cửa sổ của `call_stats_5s` |
| `info_level` | `full` = biết cả hai bên; `caller_only`; `country_only` = biết bên kia ở nước nào; `none` | Lúc bấm gọi thường chưa biết người nghe ở đâu (gọi mù). Tách được "quyết định khi thiếu thông tin" ra để đánh giá riêng |
| `decision_phase` | `initial` = lúc bấm gọi; `refined` = sau khi biết thêm; `restart` = chọn lại giữa chừng | Một cuộc gọi có thể được quyết định nhiều lần |
| `decision_mode` | `live` = dùng thật; `shadow` = chạy bóng, chỉ ghi lại | Khi pilot, thuật toán mới thường chạy "bóng" trước |
| `decision_source` | `api`; `static_fallback` = Selector lỗi nên dùng danh sách mặc định; `cache` | Phải biết cuộc gọi đó **không** do thuật toán quyết định, không thì đổ lỗi oan |
| `connection_mode` | `post_answer` = ICE bắt đầu **sau khi bắt máy** (mặc định, **giả định chưa xác minh**); `pre_connect` = ICE chạy ngay lúc đổ chuông | Hai chế độ làm thay đổi thứ tự sự kiện, tải TURN và cả định nghĩa "đã connected mà chưa bắt máy". Chưa chắc công ty dùng kiểu nào nên phải ghi rõ và kiểm tra cả hai (§21.5) |
| `ice_transport_policy` (mới ở v0.3.0) | `relay` = chỉ dùng relay candidate (**mặc định**; suy ra từ việc mentor mô tả "ICE đi TURN top 1 của mỗi bên", **chưa xác minh**); `all` = cho phép cả P2P và `relay_direct` | Quyết định cuộc gọi có thể nối thẳng hay không. Mặc định `relay` nên cuộc gọi luôn đi qua TURN và thuật toán chọn TURN mới có tác dụng với mọi cuộc gọi. `all` là một bài kiểm tra độ nhạy (§21.5). Vì là giả định chưa xác minh (Q7, §25) nên phải ghi rõ trong dữ liệu |
| `transport` | `udp`, `tcp`, `tls` | Một số mạng chặn UDP nên phải đi TCP hoặc TLS, vốn chậm hơn |
| `leg_type` | `user_turn` = chặng người ↔ TURN; `turn_turn` = chặng giữa hai TURN | Hai loại có bản chất khác nhau |
| `direction` | `forward` = theo chiều caller→callee; `reverse` = ngược lại | Mạng không đối xứng: upload 4G thường kém hơn download |
| `measure_method` | `inband` = đo trong lúc gọi; `mesh_probe` = các TURN ping nhau; `idle_probe` = điện thoại đo lúc rảnh. **Không còn `alloc`** (lý do ở §10.3) | Mỗi cách đo có độ lệch khác nhau |
| `measurement_kind` | `one_way` = đo trực tiếp một chiều (cần đồng bộ đồng hồ); `rtt` = đo đi-về | Trộn hai loại vào một cột số mà không ghi loại thì cột số vô nghĩa |
| `measurement_point` | `client`, `turn_server`, `probe_agent` | Ai đứng ra đo |
| `granularity` | `epoch_summary` = một dòng tóm tắt cho cả epoch (100% cuộc gọi); `window_5s` = từng cửa sổ 5 giây (chỉ cuộc gọi được lấy mẫu) | Tách dữ liệu KPI-grade khỏi diagnostic (§3) |
| `path_type` | `relay_relay` = hai bên dùng 2 TURN khác nhau; `relay_same` = cùng 1 TURN; `relay_direct` = một bên relay, một bên nối thẳng; `p2p_host` / `p2p_srflx` = nối thẳng hoàn toàn; `unknown`. **Suy ra từ cặp candidate được chọn** theo bảng ánh xạ ngay dưới | Cuộc gọi nối thẳng không dùng TURN. v0.1 ngầm giả định mọi cuộc gọi là relay, v0.2 thì suy từ dữ liệu thật. Với `ice_transport_policy = relay` (mặc định) chỉ có `relay_relay` và `relay_same` (I18); các kiểu còn lại chỉ xuất hiện khi policy là `all` |
| `candidate_type` | `host`, `srflx`, `prflx`, `relay`, `unknown` | Là đầu vào để suy `path_type` |
| `ice_trigger` | `initial`; `fallback` = hạng 1 lỗi nên thử hạng sau; `restart_network_change`; `restart_failure` | Phục vụ kịch bản TURN Failure và Network Change |
| `ice_state` | `connected`, `failed`, `timeout`, `cancelled` | `cancelled` (người dùng tắt giữa chừng) không phải lỗi kỹ thuật |
| `end_reason` | `normal_hangup`; `invite_undelivered` = lời mời không tới được máy B; `not_answered`; `rejected`; `cancelled_by_caller`; `ice_failed` = **đã bắt máy nhưng media chưa bao giờ nối được** (I23); `dropped_network`; `dropped_turn` (rớt **sau khi đã nối**; restart thất bại sau khi đã nối cũng là `dropped_network`); `app_crash` (không phải drop); `unknown` | Tách lý do **xã hội** (không bắt máy) khỏi lý do **kỹ thuật** (không nối được). `invite_undelivered` là mới: lời mời chưa tới thì chưa thể nói người ta "không bắt máy" |
| `pair_group` | `VN_VN`, `VN_INTL`, `INTL_INTL` | Đúng 3 nhóm đề bài yêu cầu |
| `health_status` | `healthy`, `degraded`, `overloaded`, `down`, `maintenance` | Phân biệt bảo trì có kế hoạch với sập bất ngờ |
| `alloc_error` | `none`, `timeout`, `unauthorized_401`, `forbidden_403`, `quota_486`, `capacity_508`, `unreachable`, `other` | Mỗi lỗi có cách xử lý khác nhau. `none` là mới, dùng khi thành công |
| `stats_status` | `kept_critical`, `kept_sampled`, `not_sampled`, `truncated`, `lost`, `not_applicable` | Trạng thái của dữ liệu diagnostic của cuộc gọi (§13.3) |
| `quality_assessment_status` | `assessed`, `partially_assessed`, `unclassifiable`, `not_applicable` | Một cuộc gọi có đủ số đo để phân loại chất lượng không |
| `randomization_unit` | `run` (sim: cả môi trường), `call`, `user`, `region`, `time_block` | Đơn vị được gán nhánh một lúc (§21) |
| `run_kind` | `scripted`, `blind_benchmark`, `dev` | Loại lần chạy (§19.3) |

**Bảng ánh xạ `path_type` (contract §2, thứ tự đọc từ trên xuống):**

| Cặp candidate được chọn (local, remote) | `path_type` | Ghi chú |
|---|---|---|
| (`relay`, `relay`) và `actual_turn_id` hai đầu **trùng nhau** (§16.6) | `relay_same` | Cùng một máy TURN, không có chặng `turn_turn` |
| (`relay`, `relay`) còn lại | `relay_relay` | Hai máy TURN khác nhau |
| Đúng một đầu là `relay` | `relay_direct` | |
| Cả hai đầu `host` | `p2p_host` | |
| Không đầu nào `relay` và có `srflx` / `prflx` | `p2p_srflx` | |
| Không xác định được | `unknown` | `path_type` và `selected_*_candidate_type` chỉ là null khi attempt **không** `connected` |

*Vì sao `relay_same` dựa vào `actual_turn_id` chứ không dựa vào hostname:* hai bên cùng nhận hostname pool chưa chắc dùng cùng máy; chỉ IP mới nói được (§2B.2).

---

## 7. Bảng danh mục

### 7.1 `dim_turn`: danh sách TURN server

**Trả lời câu hỏi:** "TURN này ở đâu, của nhà mạng nào, chứa được bao nhiêu?"
**Ai sinh:** đội hạ tầng (trên sim là file cấu hình thế giới).

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `turn_id` | Mã TURN: `<nước>-<thành phố>-<nhà host>-<số>` | `VN-SGN-VTL-01` | Đọc mã là biết vị trí, không cần tra |
| `hostname` | Tên miền: riêng của một máy, **hoặc chung của một pool** nhiều máy (v0.4.0) | `turn-sgn-01.vtl.example` | Điện thoại chỉ biết tên miền. Pipeline đổi ngược ra `turn_id` (§15.3) nhưng chỉ khi hostname trỏ tới đúng một máy; hostname pool thì chỉ IP mới xác định được máy (§7.4) |
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

### 7.4 `dim_turn_endpoint`: IP của từng máy TURN (mới ở v0.4.0, SCD2)

**Trả lời câu hỏi:** "IP này thuộc máy TURN nào?"
**Ai sinh:** đội hạ tầng (danh sách IP của từng máy). Thêm dòng mới khi đổi, không sửa dòng cũ (SCD2).
**Vì sao cần:** hostname không nói được máy (§2B.2). IP là cách **duy nhất** biết client đã tới máy nào. Đây là hạ tầng của công ty nên được phép lưu (§2B.6). IP dưới đây là **ví dụ minh họa** từ dải RFC 5737.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `ip` | Địa chỉ IP của máy TURN | `203.0.113.10` | Khóa tra cứu từ `relayed_ip` / `turn_server_ip` |
| `turn_id` | Máy nào (khớp `dim_turn`) | `VN-SGN-VTL-03` | Một IP chỉ thuộc **một** `turn_id` tại một thời điểm |
| `role` | `listen` = IP mà client gửi yêu cầu tới; `relay` = IP dùng cho relayed address; `both` = một IP làm cả hai việc | `both` | Có máy tách hai IP (nghe một IP, cấp relay trên IP khác), có máy dùng chung một IP. Cần biết vai trò để tra đúng loại IP |
| `hostname` | Hostname trỏ tới IP này, nếu có | `turn-pool-sgn.example` | Một hostname có thể xuất hiện ở nhiều dòng với nhiều `turn_id` (pool). Dùng để biết hostname có "mơ hồ" không |
| `valid_from`, `valid_to` | Khoảng thời gian dòng này đúng | | Máy bị đổi IP thì dữ liệu tháng trước vẫn tra đúng |

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

**Thông tin client (mới ở v0.4.0)**, nằm trong cùng object `ctx`. Mục đích: tách lỗi do phiên bản app/nền tảng khỏi lỗi do TURN (§2B.1), và biết nền tảng nào hỗ trợ field nào. Khi gọi mù, các field này của `peer_ctx` là `unknown`. Mọi giá trị dưới đây là ví dụ minh họa.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `device_id` | HMAC-SHA256 của id cài đặt app (cùng cách làm với `user_hash`) | `c41d07e9…` | Phân biệt các thiết bị của cùng một người (§2B.3) mà không lưu id thật |
| `platform` | Enum `platform` | `android` | Cắt KPI theo nền tảng; getStats khác nhau giữa các nền tảng |
| `os_version` | Phiên bản hệ điều hành | `14` | Lỗi chỉ xảy ra trên một đời OS |
| `app_version` | Phiên bản app | `3.12.0` | Bắt lỗi theo bản phát hành (`release_regression`, §16.5) |
| `sdk_version` | Phiên bản SDK WebRTC | `2.7.1` | Có khi SDK đổi mà app không đổi |
| `device_model` | Mẫu thiết bị | `SM-A546E` | Đầu vào để suy ra `device_class` (bên dưới) |
| `browser_name`, `browser_version` | Trình duyệt, **chỉ với web** | `chrome`, `126` | Mỗi trình duyệt báo getStats một kiểu |
| `device_class` (phái sinh, **pipeline tính**, producer không gửi) | `low` / `mid` / `high` / `unknown`, suy từ `device_model` theo bảng tra có version | `mid` | Máy yếu thường jitter cao hơn vì CPU chứ không vì TURN; cắt KPI theo lớp máy để không đổ nhầm. Có trong `fact_call` (§16.4, §16.6) |

---

## 9. Bảng sự kiện theo luồng cuộc gọi (phần 1: bắt đầu cuộc gọi)

### 9.1 `call_session`: "giấy khai sinh" của cuộc gọi, kiêm "phiếu gán nhánh"

**Trả lời câu hỏi:** "Cuộc gọi này có tồn tại không, ai gọi ai, lúc nào, thuộc thí nghiệm nào, nhánh nào?"
**Khi nào:** ngay khi A bấm gọi, **trước mọi quyết định của Selector**. **Ai sinh:** Signaling (BE).

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id` | Mã cuộc gọi | `0193…a1` | **Sợi chỉ xuyên suốt**: mọi bảng đều có `call_id` |
| `caller_hash`, `callee_hash` | Ai gọi ai | | Signaling biết **ai** là người nghe, nhưng chưa chắc biết họ **đang ở đâu** |
| `initiated_ts` | Lúc bấm gọi | | Mốc 0 của cuộc gọi |
| `media_kind` | Thoại hay video | `audio` | |
| `call_type` (mới ở v0.4.0) | `one_to_one`, `group` hoặc `unknown`. **Không null**: dữ liệu cũ ghi `unknown` (mặc định) | `one_to_one` | Chỉ `one_to_one` vào KPI (I21). Số cuộc gọi bị loại vì `call_type ≠ one_to_one` được báo cáo theo nhánh, để thấy việc loại không lệch giữa các nhánh |
| `caller_device_id` (mới ở v0.4.0) | Thiết bị của A (null được) | `c41d07e9…` | Biết A gọi từ máy nào để cắt theo `platform` / `app_version` của A |
| `connection_mode` | `post_answer` hay `pre_connect` | `post_answer` | Quyết định thứ tự sự kiện (I5, I6) và cách mô phỏng tải TURN. Không biết chế độ thì không biết "connected mà chưa bắt máy" là bình thường hay là lỗi dữ liệu |
| `ice_transport_policy` (mới ở v0.3.0) | Cấu hình ICE mà BE gửi cho client (`relay` / `all`). `null` = không rõ | `relay` | Biết cuộc gọi có được phép nối thẳng không. I18 dựa vào field này để kiểm tra `path_type`. Không có thì không phân biệt được "không có P2P vì bị cấm" với "không có P2P vì không nối được" |
| `be_region` (mới ở v0.3.0) | Vùng/datacenter của BE xử lý cuộc gọi (mã IATA thành phố). `null` = không rõ | `SGN` | BE ở đâu quyết định thời gian các lượt signaling (§2A). Chỉ ảnh hưởng thời gian thiết lập, **không** ảnh hưởng PCR. Có field này mới giải thích được vì sao setup chậm ở một vùng |
| `be_instance` (mới ở v0.3.0) | Máy BE cụ thể, ghi bằng **tên, không phải IP**. `null` = không rõ | `be-sgn-03` | Một máy BE chậm hay lỗi thì tìm ra được, không đổ nhầm cho TURN |
| `experiment_id` | Thí nghiệm nào; `null` = không thuộc thí nghiệm | `exp-w4-geo-vs-smart` | Cuộc gọi trong thí nghiệm mới vào cohort của KPI chính |
| `arm` | Nhánh nào. Bắt buộc khi có `experiment_id`. Trên sim = tên policy của môi trường | `smart` | Biết cuộc gọi thuộc thuật toán nào **ngay từ đầu**, không suy ngược từ kết quả |
| `randomization_unit` | Đơn vị được gán ngẫu nhiên | `run` | Quyết định cách tính độ bất định (§21.3) |
| `experiment_cluster_id` | Cụm ngẫu nhiên hóa (region, time block…). Trên sim = `sim_run_id` | `run-20261112-s42` | Cuộc gọi trong cùng cụm không độc lập với nhau |
| `assignment_ts` | Lúc gán nhánh. **Phải ≤ `request_ts` của decision đầu tiên** (I15) | | Chứng minh việc gán nhánh có trước mọi quyết định, nên cohort không bị chọn lọc theo kết quả |
| `assignment_hash` | Hash (quy tắc §4) trên `experiment_id ‖ khóa của đơn vị ngẫu nhiên`, ánh xạ sang `arm` theo tỉ lệ trong experiment registry. Trên sim `experiment_id` và `arm` là **bắt buộc** | | Tái lập được việc gán nhánh |
| `scenario_tag` | Chỉ có trên sim. **Chỉ mô tả loại cuộc gọi** | `S02_vn_cross_region` | Lọc dashboard theo kịch bản. **Không bao giờ** mã hóa sự cố ẩn (§19.4), nếu không thuật toán đọc tag là biết đáp án |

**Vì sao `call_session` phải có trước mọi quyết định và chứa cả việc gán nhánh?** Nếu cuộc gọi chết ngay sau khi bấm (app crash, Selector sập), sẽ không có bảng nào khác ghi gì cả. Không có `call_session` thì cuộc gọi đó biến mất khỏi thống kê và hệ thống trông tốt hơn thực tế. Cũng vì thế cohort của KPI chính (§20.2) được định nghĩa là "mọi `call_session` đã được gán nhánh".

### 9.2 `selector_decision`: thuật toán đã quyết định gì, và vì sao

**Trả lời câu hỏi:** "Thuật toán đề xuất 4 TURN nào, theo thứ tự nào, dựa trên thông tin gì, chắc chắn đến đâu?"
**Khi nào:** mỗi lần gọi Selector. **Ai sinh:** bên gọi Selector (Signaling hoặc simulator), **không phải bản thân Selector** (§18.3).
**Một dòng = một (lần quyết định, một bên, một thiết bị).** Hai bên của cùng một request dùng chung một `decision_id`. Từ v0.4.0, **mỗi thiết bị của B đang đổ chuông là một request `refined` riêng với `decision_id` riêng**; dòng `caller` trong request đó áp dụng cho đúng cặp thiết bị này.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `decision_id` | Mã của lần quyết định (UUIDv7) | `0193…d1` | Một cuộc gọi có thể được quyết định 2–3 lần (hoặc nhiều hơn khi B có nhiều thiết bị) |
| `call_id`, `side`, `phase` | Cuộc gọi nào, bên nào, giai đoạn nào | `caller`, `initial` | So sánh quyết định lúc mù với quyết định sau khi biết đủ |
| `device_id` (mới ở v0.4.0) | Thiết bị mà quyết định này dành cho (= `self_ctx.device_id`). **Không null**: `'unknown'` nếu không biết (nó nằm trong khóa, §4) | `c41d07e9…` | **Khóa mới** của bảng là (`decision_id`, `side`, `device_id`). Người nghe có nhiều thiết bị thì mỗi thiết bị có một quyết định riêng. `ice_attempt.decision_id` trỏ tới decision của thiết bị **đã bắt máy** (I20) |
| `request_ts` | Lúc hỏi | | Dùng để chọn đúng snapshot (I12) và kiểm tra thứ tự nhân quả (I5) |
| `response_ts`, `api_latency_ms` | Lúc được trả lời, mất bao lâu. `api_latency_ms` do **BE** đo (BE là bên gọi Selector) | `18` | `null` khi API không trả lời. KPI Service Health. Vì là số đo từ phía BE nên gồm cả mạng giữa BE và Selector, không chỉ thời gian Selector tính toán |
| `policy_version` | Thuật toán nào, phiên bản nào | `geo_baseline@0.1`, `smart@0.3.1`, `static@1` | So sánh Geo Baseline với Smart Selector |
| `decision_mode`, `decision_source`, `info_level` | Xem §6 | `live`, `api`, `caller_only` | |
| `self_ctx`, `peer_ctx` | Bối cảnh bên được chọn / bên kia | | `peer_ctx` ghi **đúng những gì thuật toán biết lúc đó**, không phải sự thật về sau |
| `k` | Số TURN trả về (mặc định 4) | `4` | Đề bài ghi 8, mentor nói 4, nên là tham số |
| `candidates` | Danh sách TURN, sắp theo rank: đúng `min(k, số TURN khả dụng sau khi lọc)` (v0.4.0). Thiếu so với `k` thì `fallback_reason = insufficient_candidates` | | Trái tim của quyết định (§9.2.1). Nếu sau khi lọc `down`/`overloaded`... chỉ còn 2 TURN thì trả 2, không bịa thêm cho đủ 4 |
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
| `score_components` | Điểm thành phần; từ v0.4.0 gồm cả `backoff_level` = cấp segment (§17.0) đã dùng cho candidate này | `{geo:.9, isp:1, health:.95, history:.8, backoff_level:3}` | **Decision Trace**: giải thích vì sao TURN này đứng đầu. Ghi cấp backoff **từng candidate** vì cách chọn cấp là thiết kế của Đoàn, có thể khác nhau giữa các candidate; không ghi thì không biết hai điểm có so sánh được không |
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
| `device_id` (mới ở v0.4.0) | Thiết bị tạo allocation. **Không null** (`'unknown'` nếu không biết) | `5ae2b8c0…` | Khi B có hai thiết bị đổ chuông, mỗi thiết bị xin allocation riêng; phải biết cái nào là của thiết bị nào để ghép đúng vào attempt (I20, §16.3) |
| `turn_id`, `rank`, `transport` | TURN nào, hạng mấy, giao thức gì | `VN-SGN-VTL-01`, `1`, `udp` | Hạng 1 có hay lỗi hơn hạng 2 không? `turn_id` là máy **Selector chọn**, có thể khác máy thật (xem `relayed_ip` bên dưới) |
| `turn_url` (mới ở v0.4.0) | URL TURN client **thực sự dùng**: `turn:`/`turns:` + hostname hoặc IP + port (null được) | `turn:turn-pool-sgn.example:3478` | Biết client được cấp hostname riêng, hostname pool hay IP (câu hỏi Q9). Là đầu vào của bước hostname trong `actual_turn_id` (§16.6) |
| `turn_server_ip` (mới ở v0.4.0) | IP máy TURN mà client gửi tới, **sau khi phân giải hostname**, nếu lấy được | `203.0.113.10` | Dấu vết hostname pool dẫn tới máy nào. Là hạ tầng nên được lưu (§2B.6) |
| `relayed_ip` (mới ở v0.4.0) | IP của relayed address mà TURN cấp (local candidate loại `relay`). **IP máy chủ TURN, không phải IP người dùng** | `203.0.113.10` | Nguồn chính xác nhất để biết máy thật (ưu tiên thứ hai trong §16.6) |
| `ice_generation` | Thế hệ ICE lúc tạo allocation (0, +1 mỗi ICE restart) | `0` | Allocation của thế hệ cũ không được gán cho attempt của thế hệ mới chỉ vì cùng `turn_id` |
| `attempt_seq` | Gắn với lần thử cụ thể nào; `null` nếu chưa gắn | `1` | |
| `is_preallocation` | Xin trước để dự phòng, chưa chắc dùng | `true` | Không lẫn với lần xin để dùng thật; để tính chi phí tài nguyên của xin trước |
| `request_ts` | Lúc gửi yêu cầu | | |
| `response_ts`, `alloc_ms` | Lúc có trả lời; thời gian cấp. `null` nếu timeout | `38` | Xem khung bên dưới |
| `success`, `error_code` | Có được cấp không; lỗi gì (enum `alloc_error`). **`success = true` ⇔ `error_code = none`** (I10) | `true`, `none` | KPI Allocation Success |
| `released_ts`, `release_reason` | Lúc trả chỗ; lý do: `not_needed`, `call_end`, `kept_for_failover`, `expired`, `unanswered`, `other_device_answered` (mới ở v0.4.0) | `not_needed` | Chi phí tài nguyên. `unanswered` nghĩa là giữ chỗ xong mà không ai bắt máy. `other_device_answered` nghĩa là người nghe có nhiều thiết bị và **thiết bị khác** đã bắt máy, nên allocation này bị bỏ; không được ghép vào attempt (I20) |

> **`alloc_ms` là gì, và không là gì?** `alloc_ms` là **allocation latency**: thời gian từ lúc gửi yêu cầu xin chỗ tới lúc có kết quả, **gồm cả vòng 401** (TURN yêu cầu xác thực, client gửi lại kèm thông tin xác thực) **và thời gian server xử lý**. Nó **không phải RTT, cũng không phải one-way** của chặng người↔TURN. Một lần xin chỗ có ít nhất hai vòng đi-về, cộng thêm xử lý ở server, nên con số lớn hơn RTT thật và không thể "chia đôi" để ra một chiều. v0.1 coi `alloc_ms` là "số đo chặng miễn phí" nên đã bỏ; nó có bảng thống kê riêng (§17.6).

### 9.4 `ice_attempt`: mỗi lần thử nối

**Trả lời câu hỏi:** "Đã thử nối bằng đường nào, mất bao lâu từng bước, có thành công không, **thực tế dùng TURN nào**?"
**Khi nào:** mỗi lần ICE chạy: lần đầu, mỗi lần dự phòng, mỗi lần restart. **Ai sinh:** SDK. Một dòng = một lần thử. Khóa chính (v0.4.0): (`call_id`, `attempt_seq`).

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id`, `attempt_seq`, `ice_generation` | Cuộc gọi, lần thử thứ mấy, thế hệ ICE | `1`, `0` | Lần 2 trở đi là có trục trặc |
| `caller_device_id`, `callee_device_id` (mới ở v0.4.0) | Hai thiết bị của kết nối này (null được). `callee_device_id` là thiết bị **đã bắt máy** | `c41d07e9…`, `5ae2b8c0…` | I20 so `callee_device_id` với `call_outcome.answered_device_id` để chắc không ghép nhầm thiết bị |
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
| `path_type` | Kiểu đường, **suy ra từ hai field trên** theo bảng ánh xạ ở §6. `unknown` khi không xác định; `null` chỉ khi attempt không `connected` | `relay_relay` | v0.1 mặc định relay_relay; v0.2 không giả định |
| `relay_turn_caller`, `relay_turn_callee` | `turn_id` suy từ URL/hostname, **chỉ khi hostname trỏ tới đúng một máy**. `null` nếu bên đó không đi relay **hoặc hostname là pool** (v0.4.0). Máy thực tế luôn được xác định lại từ IP (§16.6) | `VN-SGN-VTL-01` | So với danh sách đề xuất. Trước đây cột này bị hiểu là "máy thật"; với hostname pool nó không thể |
| `relayed_ip_caller`, `relayed_ip_callee` (mới ở v0.4.0) | IP relayed address của hai đầu trong **cặp candidate được chọn** (null được). **Chỉ ghi khi candidate là `relay`**; candidate host/srflx/prflx không bao giờ được lưu IP, và không lưu `relatedAddress`/`relatedPort` | `203.0.113.10`, `198.51.100.20` | Bằng chứng mạnh nhất về máy TURN thực tế: ưu tiên số 1 trong `actual_turn_id` (§16.6). Là IP máy chủ TURN (§2B.6) |
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
| `granularity` | `epoch_summary` (một dòng cho mỗi call × epoch × leg × direction, **100% cuộc gọi**; với probe thì một dòng cho mỗi khoảng tổng hợp) hoặc `window_5s` (từng cửa sổ, **chỉ cuộc gọi được lấy mẫu**) | `epoch_summary` | Feature store và KPI chỉ đọc `epoch_summary` (I16) |
| `method` | `inband`, `mesh_probe`, `idle_probe`. **Không có `alloc`** | `inband` | Mỗi cách đo có độ lệch khác nhau. Đã bỏ `alloc` vì `alloc_ms` không phải số đo chặng (§9.3) |
| `measurement_kind` | `one_way` hoặc `rtt` | `one_way` | Cho phép lưu cả hai loại mà không lẫn |
| `measurement_point` | `client`, `turn_server`, `probe_agent` | `client` | Ai đo |
| `method_version` | Phiên bản phương pháp đo | `inband-1` | Đổi cách đo thì số liệu cũ/mới không trộn |
| `window_start_ts`, `window_end_ts` | Khoảng đo | | Phân tích theo giờ; kiểm tra I9 "cùng cửa sổ" |
| `call_id`, `attempt_seq`, `ice_generation`, `network_epoch` | Thuộc cuộc gọi, lần thử, thế hệ ICE, epoch nào. `null` với probe | | `call_id = null` cho số đo không thuộc cuộc gọi nào |
| `leg_type`, `direction` | Loại chặng, chiều | `user_turn`, `forward` | |
| `side` | Với `user_turn`: bên nào | `caller` | |
| `src_id`, `dst_id` | Từ đâu tới đâu, **đúng theo chiều gói tin** | `user 9f2c…` → `VN-SGN-VTL-01` | |
| `device_id` (mới ở v0.4.0) | Với `user_turn`: thiết bị của user. **Không null**: `'-'` với chặng `turn_turn` (không áp dụng), `'unknown'` nếu không biết | `c41d07e9…` | Một người có hai thiết bị (Wi-Fi và 4G) thì số đo chặng của hai máy khác nhau; cũng là một phần của khóa duy nhất bên dưới |
| `user_segment_key`, `network_type` | Nhóm user, loại mạng (với `user_turn`) | `VN\|south\|7552\|4g` | Gộp số đo của nhiều người cùng nhóm |
| `value_ms` | Giá trị **trung bình** trong cửa sổ/epoch, **đúng loại `measurement_kind`** | `9.1` | Thay cho `one_way_ms` của v0.1. Cột một tên nhưng hai nghĩa là nguy hiểm, nên nghĩa nằm ở `measurement_kind` |
| `value_ms_p95` | P95 trong epoch (chỉ với `epoch_summary`) | `14` | Thấy "cú giật" mà trung bình che đi |
| `n_samples` | Số mẫu | `36` | Cỡ mẫu |
| `clock_sync_err_ms` | Sai số đồng bộ đồng hồ. **Bắt buộc** khi `measurement_kind = one_way` | `0.8` | One-way mà không biết sai số đồng hồ thì không biết đáng tin tới đâu |
| `loss_pct`, `jitter_ms`, `packets` | Mất gói, độ giật, số gói | | 3 gói mà loss 33% có thể chỉ là ngẫu nhiên |
| `missing_reason` | Vì sao thiếu | `no_packets` | Thay cho điền 0 |

**Khóa duy nhất (v0.4.0, ngoài `event_id`):** (`call_id`, `attempt_seq`, `network_epoch`, `leg_type`, `side`, `device_id`, `src_id`, `dst_id`, `direction`, `method`, `measurement_kind`, `granularity`, `window_start_ts`). *Vì sao:* để dedup được số đo chặng mà không nhầm hai chặng khác nhau thành một. **Probe** (`call_id = null`) cũng ghi bằng `granularity = epoch_summary` với khoảng [`window_start_ts`, `window_end_ts`] (ví dụ 5 phút) và `network_epoch = null`. Probe là nguồn hợp lệ cho **feature** (§17) nhưng **không** cho KPI.

**Hai mức độ chi tiết (`granularity`):** nếu lưu từng cửa sổ 5 giây cho mọi cuộc gọi thì dung lượng rất lớn. Vì vậy mọi cuộc gọi chỉ lưu **bản tóm tắt theo epoch** (giá trị trung bình + P95), còn từng cửa sổ chỉ lưu cho cuộc gọi được lấy mẫu (§13.3). Feature store chỉ dùng bản tóm tắt nên không bị lệch theo việc lấy mẫu.

**Vì sao vẫn là bảng trung tâm của phần dự đoán?** Hệ thống chỉ đo được đường đã đi. Muốn biết đường **chưa ai đi** thì ghép các chặng đã đo ở các cuộc gọi khác ("Viettel miền Nam → DAD" từ 1.000 cuộc gọi, "VNPT Hà Nội → DAD" từ 800 cuộc gọi). Muốn ghép thì mỗi chặng phải là một dòng riêng có nhãn nhóm user (như paper Via của Microsoft).

### 10.4 `call_stats_epoch`: chất lượng nhìn từ điện thoại — **KPI-grade, 100% cuộc gọi**

**Trả lời câu hỏi:** "Với mỗi bên, trong mỗi giai đoạn mạng, bao nhiêu cửa sổ 5 giây có độ trễ/mất gói/jitter tệ?"
**Ai sinh:** có **hai cách** (v0.4.0, field `derivation`):
- `sdk`: SDK **tính ngay trên thiết bị** từ W3C getStats rồi gửi khi epoch kết thúc.
- `pipeline`: SDK gửi `call_stats_5s` cho **100%** cuộc gọi, pipeline dựng bảng này theo đúng cùng quy tắc (§2B.5, I22). Dòng do pipeline dựng mang `producer = client_sdk` (kế thừa từ dữ liệu gốc), `event_ts = epoch_end_ts`, `ingest_ts` = `ingest_ts` lớn nhất của các dòng 5s đầu vào, và `event_id` là **UUIDv5 tất định** từ (`call_id`, `endpoint_side`, `device_id`, `media_kind`, `network_epoch`, `derivation`). *Vì sao UUIDv5:* chạy lại pipeline cho ra cùng `event_id`, nên dedup (I11) không sinh bản trùng.

Hai cách phải cho kết quả **giống hệt** trên cùng dữ liệu (test derivation-equivalence, chạy với độ lệch đồng hồ bằng 0). Mỗi (cuộc gọi, endpoint, thiết bị) chỉ có **một** `derivation` được dùng cho KPI: endpoint tự gửi epoch thì dùng `sdk`; chỉ endpoint gửi thô mới có dòng `pipeline`. Dòng `pipeline` tính thêm cho một endpoint `sdk` chỉ có trong test S24 và không bao giờ vào KPI. *Vì sao:* nếu cả hai dòng cùng vào KPI thì một endpoint bị đếm hai lần.

**Một dòng = (call, endpoint_side, device_id, media_kind, network_epoch).**

**Vì sao gửi dạng histogram?** Gửi từng cửa sổ 5 giây của mọi cuộc gọi quá nặng, mà lấy mẫu thì lệch KPI. Histogram nhỏ (vài chục số) mà vẫn cho phép đếm "bao nhiêu cửa sổ tệ", nên gửi được **100% cuộc gọi** (với `derivation = pipeline` thì đổi lại bằng việc gửi cửa sổ thô).

**Cửa sổ (độ dài `window_s`, mặc định 5 giây):**
- **Neo theo từng endpoint, trên đồng hồ của endpoint đó** (v0.4.0): `anchor_ts` = lúc endpoint ghi nhận `ice_connected` **lần đầu** trong cuộc gọi. Cửa sổ thứ *i* = [anchor + i·w, anchor + (i+1)·w). *Vì sao theo endpoint:* mỗi điện thoại chỉ tin đồng hồ của chính nó, và chỉ cần bảo đảm cửa sổ của **chính nó** liền mạch; không cần hai bên chung một lưới (bản nháp trước đòi chung một lưới, nhưng hai đồng hồ lệch nhau thì lưới chung là ảo).
- Neo **không** đặt lại sau ICE restart, nên cửa sổ của mọi epoch của endpoint đó nằm trên cùng một lưới.
- **Cửa sổ thuộc epoch chứa điểm giữa của nó** (epoch là khoảng [bắt đầu, kết thúc)). *Vì sao điểm giữa:* "chứa phần lớn thời gian" mơ hồ khi cửa sổ vắt qua ranh giới đúng một nửa; điểm giữa luôn cho đúng một đáp án.
- **Cửa sổ "đánh giá được" khi đồng thời thỏa ba điều kiện:**
  - (a) nằm trọn trong [`answer_ts`, min(`end_ts`, `converted_ts`)]: người dùng thực sự nghe, và chưa chuyển thành cuộc gọi nhóm. Vì vậy với `pre_connect`, cửa sổ lúc đổ chuông không bao giờ được đánh giá.
  - (b) không giao với khoảng gián đoạn do restart [`end_ts` của attempt cũ, `ice_connected_ts` của attempt mới).
  - (c) **metric đó** có số đo hợp lệ trong cửa sổ: RTT cần RTCP RR với DLSR ≠ 0; loss cần Δexpected > 0 và Δlost ≥ 0; jitter cần giá trị không null. Điều kiện này xét **riêng từng metric**, nên cùng một cửa sổ có thể assessable với loss mà không assessable với RTT.
- **Mốc thời gian:** SDK dùng thời điểm nó quan sát cục bộ (nhận `answer` qua signaling, kết thúc cuộc gọi); pipeline dùng `event_ts_corrected` (§16.1).
- **Bucket đóng trái, mở phải; key chuẩn** (dùng đúng chuỗi này, không viết `<100` hay `≥400` trong dữ liệu): RTT `lt100`, `100_200`, `200_300`, `300_400`, `ge400`; loss `lt1`, `1_3`, `3_5`, `ge5`; jitter `lt10`, `10_30`, `30_50`, `ge50`. Một cửa sổ có RTT đúng 300 ms rơi vào `300_400` (đóng trái). Histogram **không có cửa sổ nào đánh giá được** là `{}` (map rỗng, **không phải null**). *Vì sao key chuẩn:* hai bên viết `<100` và `lt100` thì `derivation-equivalence` không so được, và ký tự `<`, `≥` dễ hỏng ở JSON/SQL.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id`, `endpoint_side`, `media_kind`, `network_epoch` | Khóa. `endpoint_side` = endpoint báo cáo | `C1`, `caller`, `audio`, `0` | |
| `device_id` (mới ở v0.4.0) | Thiết bị báo cáo. **Không null** (`'unknown'` nếu không biết); nằm trong khóa | `c41d07e9…` | Một endpoint là một thiết bị. Neo cửa sổ theo endpoint nên cần biết endpoint nào |
| `derivation` (mới ở v0.4.0) | Enum `stats_derivation`: `sdk` hoặc `pipeline` | `sdk` | Biết dòng này do ai tính; test hai cách giống nhau; kiểm I22. Dữ liệu cũ mặc định `sdk` |
| `window_s` (mới ở v0.4.0) | Độ dài cửa sổ, mặc định 5 | `5` | **Dữ liệu khác `window_s` không được gộp chung**: histogram 5 giây và 10 giây đếm đơn vị khác nhau. Dữ liệu cũ mặc định 5 |
| `epoch_start_ts`, `epoch_end_ts` | Khoảng của epoch | | |
| `audio_active_duration_s` | Thời gian có media audio thực sự (`null` với `media_kind = video`) | `183.6` | Phân biệt "nối được" với "có tiếng thật" |
| `first_media_sent_ts`, `first_media_received_ts` | Gói media đầu tiên gửi/nhận tại endpoint này trong epoch này | | Tính `ttfm_post_answer` (§20.4); kiểm tra I5f |
| `packets_expected`, `packets_lost` | Gói dự kiến và gói mất, **luồng inbound** (luồng đi vào endpoint này) | | Loss do người nghe cảm nhận là loss của luồng họ nhận |
| `media_rtcp_rtt_hist` | Histogram **số cửa sổ** theo bucket `lt100`, `100_200`, `200_300`, `300_400`, `ge400` (ms). Là RTT của **luồng outbound** (luồng endpoint này gửi đi) lấy từ `remote-inbound-rtp.roundTripTime` theo SSRC. **Không null** (rỗng là `{}`) | `{"lt100": 33, "100_200": 3}` | Metric RTT chính cho PCR |
| `loss_hist` | Bucket `lt1`, `1_3`, `3_5`, `ge5` (%). Loss inbound của cửa sổ = Δlost / Δexpected. Không null | | Metric loss chính |
| `jitter_estimate_hist` | Bucket `lt10`, `10_30`, `30_50`, `ge50` (ms); jitter estimate inbound (`inbound-rtp.jitter`). Không null | | Metric jitter chính |
| `rtt_windows_assessable`, `loss_windows_assessable`, `jitter_windows_assessable` | Số cửa sổ có số đo hợp lệ, **riêng cho từng metric** | `34`, `36`, `36` | Mẫu số của PoorFraction. Riêng từng metric vì RTT cần báo cáo RTCP nên thiếu nhiều hơn loss |
| `valid_rtt_samples`, `valid_jitter_samples` | Số mẫu hợp lệ. RTT chỉ hợp lệ sau khi có báo cáo RTCP RR với DLSR ≠ 0 | | Chống tin vào số RTT khi chưa có báo cáo đầu tiên |
| `media_rtcp_rtt_p50`, `media_rtcp_rtt_p95` | Chẩn đoán | | |
| `ice_stun_rtt_p50`, `ice_stun_rtt_p95` | RTT của gói STUN check (`candidate-pair.currentRoundTripTime`). **Metric riêng, không thay cho media RTT** | | Xem khung bên dưới |
| `jitter_estimate_p95` | P95 của **các ước lượng jitter đã lấy mẫu**, không phải jitter của từng gói | | Tên nói rõ nó là P95 của *ước lượng* |
| `measurement_coverage` | Tỉ lệ cửa sổ đánh giá được cho **cả ba** metric / tổng số cửa sổ của epoch (0–1) | `0.97` | Biết số liệu đáng tin tới đâu. Với `derivation = pipeline`, cửa sổ thiếu do gửi thất bại cũng được phản ánh ở đây |
| `quality_rule_version` | Phiên bản bộ bucket | | Đổi bucket thì dữ liệu cũ vẫn hiểu được |

> **`media_rtcp_rtt` khác `ice_stun_rtt` thế nào?**
> - `media_rtcp_rtt` đo RTT **của chính luồng âm thanh/hình** đi qua đường thật mà người dùng nghe, dựa trên báo cáo RTCP. Đây là cái người dùng cảm nhận, nên dùng để phân loại cuộc gọi.
> - `ice_stun_rtt` đo RTT của **gói kiểm tra STUN** của ICE trên cặp địa chỉ đã chọn. Gói này nhỏ, gửi thưa, đôi khi qua đường/hàng đợi khác, nên không đại diện cho độ trễ media. Chỉ dùng để chẩn đoán.
>
> **`jitter_estimate` nghĩa là gì?** Đây là giá trị jitter mà bộ đếm của WebRTC (`inbound-rtp.jitter`) báo ở thời điểm lấy mẫu, một ước lượng đã làm mượt, không phải độ lệch của từng gói. Vì thế contract gọi là "estimate" và P95 của nó là "P95 của các ước lượng đã lấy mẫu".

### 10.5 `call_stats_5s`: chi tiết từng cửa sổ — **diagnostic, lấy mẫu**

**Trả lời câu hỏi:** "Trong cuộc gọi cụ thể này, đúng lúc nào bị giật?"
Khóa (v0.4.0): (`call_id`, `endpoint_side`, `device_id`, `media_kind`, `window_idx`). Dùng **cùng quy tắc cửa sổ** như `call_stats_epoch`, nên một cửa sổ ở đây khớp đúng một cửa sổ trong histogram.

Từ v0.4.0, bảng này là **bảng đầy đủ** chứ không còn là danh sách field gợi ý, vì khi `derivation = pipeline` nó là **đầu vào** để pipeline tính lại `call_stats_epoch`: phải đủ cột để tính lại đúng quy tắc §10.4.

| Field | Nghĩa | Vì sao cần |
|---|---|---|
| `window_s`, `quality_rule_version` | Như `call_stats_epoch` | Không trộn dữ liệu khác độ dài cửa sổ hoặc khác bộ bucket |
| `window_start_ts` | Đầu cửa sổ, theo đồng hồ endpoint | Tính epoch theo điểm giữa và kiểm tra cửa sổ có nằm trong [`answer_ts`, …] |
| `network_epoch`, `network_type` | Giai đoạn mạng và loại mạng | Tách Wi-Fi khỏi 4G |
| `media_rtcp_rtt_ms`, `rtt_sample_valid` | RTT luồng outbound; `rtt_sample_valid` = trong cửa sổ có RTCP RR với DLSR ≠ 0 | Cờ hợp lệ riêng cho RTT, để không tin RTT trước báo cáo RTCP đầu tiên |
| `ice_stun_rtt_ms` | RTT của STUN check | Chẩn đoán |
| `jitter_estimate_ms`, `jitter_sample_valid` | Jitter estimate và cờ hợp lệ | Cờ hợp lệ riêng cho jitter |
| `packets_expected`, `packets_lost`, `loss_pct` | **Δ trong cửa sổ**, không phải giá trị cộng dồn; `loss_pct` = Δlost / Δexpected khi hợp lệ | Cộng dồn thì loss bị che bởi cả cuộc gọi dài; Δ mới cho loss của đúng cửa sổ |
| `audio_active_s` | Số giây có audio thật trong cửa sổ | Dựng lại `audio_active_duration_s` |
| `first_media_sent_ts`, `first_media_received_ts` | Chỉ có ở cửa sổ chứa sự kiện đó | Dựng lại hai mốc của epoch (dùng cho `ttfm`) |
| `restart_gap` | bool: cửa sổ giao với khoảng gián đoạn do restart | Điều kiện (b) của "đánh giá được" |
| `bitrate_send_kbps`, `bitrate_recv_kbps` | Bitrate gửi/nhận | Chẩn đoán |
| `conn_state` | Enum `conn_state` (`connected`, `disconnected`, `failed`) | Chẩn đoán |

**Có `call_stats_epoch` rồi, sao còn cần bảng này?** Histogram chỉ cho biết *bao nhiêu* cửa sổ tệ, không cho biết *khi nào*. Để vẽ biểu đồ và điều tra Decision Trace cần từng cửa sổ. Với endpoint `sdk`, bảng này chỉ có ở cuộc gọi được lấy mẫu nên **không dùng cho KPI quyết định**. Aggregate trên bảng này phải dùng trọng số Horvitz-Thompson (§13.3). Với endpoint `pipeline`, bảng này được gửi 100% và là đầu vào KPI-grade.

### 10.6 `call_outcome`: kết cục cuộc gọi

**Trả lời câu hỏi:** "Cuộc gọi kết thúc ra sao?"
**Khi nào:** lúc kết thúc. **Ai sinh:** SDK hoặc Signaling. Một dòng mỗi cuộc gọi.

| Field | Nghĩa | Ví dụ | Vì sao cần |
|---|---|---|---|
| `call_id` | Khóa | | |
| `ring_ts` | Lúc máy B **nhận lời mời và đổ chuông**. `null` nếu `invite_undelivered` | `13:00:00.900` | Phân biệt "lời mời không tới" với "tới rồi mà không ai nghe". Rất khác nhau: cái đầu có thể là lỗi hạ tầng, cái sau là hành vi người dùng |
| `answer_ts` | Lúc **người dùng B bấm nghe** (sự kiện Signaling, **không phải** SDP Answer) | `13:00:04.000` | SDP Answer là bước kỹ thuật, có thể xảy ra trước khi người dùng bấm nghe (nhất là `pre_connect`). Mốc "bấm nghe" mới là mốc người dùng cảm nhận |
| `caller_signaling_rtt_ms`, `callee_signaling_rtt_ms` (mới ở v0.3.0) | RTT giữa app và BE trên kênh signaling (ví dụ ping/pong websocket), đo gần lúc gọi. `null` nếu SDK không đo | `45`, `38` | Chẩn đoán: giải thích **phần thời gian thiết lập do BE** (§2A, và chỉ số `signaling_overhead_est_ms` ở §20.5). Chưa xác minh SDK có đo được không (Q8) nên cho phép `null`, không chặn |
| `answered` | Có bắt máy không | `true` | Không bắt máy không phải lỗi kỹ thuật |
| `answered_device_id` (mới ở v0.4.0) | Thiết bị đã bắt máy (null được: không ai bắt máy) | `5ae2b8c0…` | Khi B có nhiều thiết bị, biết thiết bị nào đã nghe để ghép đúng decision/allocation/attempt (I20) |
| `n_devices_rung` (mới ở v0.4.0) | Số thiết bị của B đã đổ chuông (null được) | `1` | Cho biết cuộc gọi có rơi vào trường hợp nhiều thiết bị không (S21); `> 1` nghĩa là có allocation bị bỏ (`other_device_answered`) |
| `connected` | Có ít nhất một ICE attempt `connected` | `true` | Với `pre_connect`, có thể `connected = true` mà `answered = false` (I6) |
| `end_ts` | Kết thúc | | |
| `duration_s` | Từ `answer_ts` tới `end_ts` | `184` | Cuộc gọi quá ngắn sau khi nối có thể là dấu hiệu chất lượng tệ |
| `end_reason` | Xem §6. `ice_failed` chỉ khi đã bắt máy nhưng **chưa bao giờ** nối được media (I23); restart thất bại sau khi đã nối là `dropped_network` | `normal_hangup` | |
| `dropped` | Kết thúc bất thường do mạng/TURN **sau khi đã bắt máy và đã connected**. `dropped = true` ⇔ `end_reason ∈ {dropped_network, dropped_turn}` (I24); `app_crash` **không** phải drop | `false` | Chưa nối được mà kết thúc thì không gọi là "rớt" (đó là `setup_fail`, §20.1) |
| `caller_ctx_final`, `callee_ctx_final` | Bối cảnh **thật**, join muộn | | So với `peer_ctx` lúc quyết định thì đo được "cái giá của gọi mù" |
| `pair_group` | VN_VN, VN_INTL, INTL_INTL | | |
| `converted_to_group` (mới ở v0.4.0) | Cuộc gọi 1-1 chuyển thành nhóm giữa chừng. null ≡ false | `false` | Cuộc gọi chuyển thành nhóm thì nửa sau đi qua SFU, số đo không còn là "cả đường" (§2B.4) |
| `converted_ts` (mới ở v0.4.0) | Thời điểm chuyển. Cửa sổ sau mốc này **không đánh giá được** (I21) | | Là cận trên của vùng cửa sổ hợp lệ: min(`end_ts`, `converted_ts`) (§10.4) |
| `n_ice_attempts`, `n_network_changes` | Số lần thử nối, số lần đổi mạng | `1`, `0` | Độ ổn định; cũng là điều kiện "critical" khi lấy mẫu |
| `stats_status` | Trạng thái dữ liệu **diagnostic** của các endpoint `derivation = sdk` | `kept_sampled` | Phân biệt "không lưu có chủ đích" với "lưu rồi mà mất" |
| `stats_sampling_prob` | 1.0 / 0.1 / 0.0 cho endpoint `sdk`. Endpoint `pipeline` luôn gửi 100% (I22) | `0.1` | Trọng số để cân lại (`1/prob`) |
| `stats_sampling_reason` | `critical:<lý do>`, `hash_sample`, `not_selected`, và **`raw_full`** (mới ở v0.4.0) | `hash_sample` | Giải thích vì sao có/không có dữ liệu chi tiết. `raw_full` nghĩa là mọi endpoint của cuộc gọi đều `derivation = pipeline`, gửi 100% để pipeline tính `call_stats_epoch` |
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
- **Cửa sổ** = `window_s` giây (mặc định 5), lưới cố định neo tại lúc **endpoint đó** ghi nhận ICE connected **đầu tiên** (v0.4.0: neo theo từng endpoint, trên đồng hồ của endpoint). Cửa sổ thuộc epoch chứa **điểm giữa** của nó.
- **Một endpoint, một lưới.** Không đặt lại neo sau restart.
- **Cửa sổ "không đánh giá được"** không nằm trong tử số hay mẫu số của PoorFraction. Mỗi metric có số cửa sổ assessable riêng.
- Cuộc gọi `pre_connect` có thể đã connected từ lúc đổ chuông; neo vẫn là ICE connected đầu tiên. Cửa sổ trước khi có media thuộc nhóm không có số đo hợp lệ, nên không làm sai PoorFraction.

---

## 13. Quy tắc thu thập dữ liệu

### 13.1 Dữ liệu KPI-grade luôn gửi 100%
Không phụ thuộc bất kỳ quy tắc lấy mẫu nào.

### 13.2 Vì sao có ring buffer?
**Phạm vi:** ring buffer và lấy mẫu (§13.3) chỉ áp dụng cho endpoint `derivation = sdk`. Endpoint `derivation = pipeline` (v0.4.0) gửi `call_stats_5s` liên tục từng lô, **không có ring buffer, không lấy mẫu**; lô gửi thất bại thì các cửa sổ đó thiếu và `measurement_coverage` phản ánh. Cuộc gọi có một endpoint `sdk` và một endpoint `pipeline` thì quy tắc lấy mẫu chỉ áp dụng cho endpoint `sdk`.

Trong cuộc gọi, SDK ghi `call_stats_5s` vào bộ nhớ đệm vòng trên thiết bị: tối đa 360 cửa sổ (30 phút) và 256 KB mỗi cuộc gọi. Tràn thì giữ cửa sổ **mới nhất**, đặt `stats_status = truncated`. Lý do: **quyết định có gửi hay không chỉ biết được khi cuộc gọi kết thúc** (cuộc gọi có tệ không?), mà lúc đó cần dữ liệu từ đầu cuộc gọi. Bộ đệm giữ lại tạm thời để đủ dữ liệu khi cần quyết định.

### 13.3 Quy tắc lấy mẫu dữ liệu diagnostic (khi cuộc gọi kết thúc)

| Tầng | Điều kiện | Kết quả |
|---|---|---|
| **critical** | `end_reason ∈ {ice_failed, dropped_network, dropped_turn}`, hoặc `n_ice_attempts > 1`, hoặc có fallback hoặc restart | Giữ **toàn bộ**, `prob = 1.0`, `stats_status = kept_critical`, `stats_sampling_reason = critical:<lý do>` |
| **normal** | `u64(sha256(utf8(call_id))[0:8], big-endian) mod 1000 < 100` | Giữ, `prob = 0.1`, `kept_sampled`, `hash_sample` |
| **normal, không trúng** | ngược lại | Xóa buffer, `prob = 0.0`, `not_sampled`, `not_selected` |

- **SDK tự xác định tầng critical** từ những gì nó quan sát được (ICE thất bại, rớt, restart, fallback). BE gửi `end_reason` trong tin nhắn kết thúc nếu có. *Vì sao:* quyết định giữ hay xóa buffer phải được đưa ra **ngay trên thiết bị** khi cuộc gọi kết thúc, trước khi `call_outcome` (do BE ghi) kịp tới.
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
| I3 | FAIL | `len(candidates) = min(k, số TURN khả dụng sau lọc)`; rank liên tục 1..len; không trùng `turn_id`; tổng propensity = 1 (sai số 1e-6) | Lỗi code thuật toán; hoặc trả đủ `k` bằng cách nhét lại TURN đã bị lọc (`down`...) |
| I4 | WARN | Chỉ với `decision_mode = live`: TURN thực dùng (`actual_turn_id`, §16.6; thiếu thì `relay_turn_*`) phải nằm trong `candidates` của cùng bên (trừ `static_fallback`). `turn_identity_method = ambiguous` thì bỏ qua | Client tự ý dùng TURN khác, hoặc hostname pool đưa client tới máy khác (khi đó I19 cũng báo). Chạy `shadow` không kiểm vì client không buộc phải dùng danh sách đó |
| I5 | WARN | **Chỉ kiểm tra thứ tự nhân quả** (xem bên dưới) | Đồng hồ điện thoại lệch quá 2 giây, hoặc lỗi gắn event |
| I6 | FAIL | `answered = false` thì `end_reason` chỉ được là `invite_undelivered`, `not_answered`, `rejected`, `cancelled_by_caller`. Và `answered = false ∧ connected = true` chỉ hợp lệ khi `connection_mode = pre_connect` | Lỗi logic ở SDK, hoặc `connection_mode` ghi sai |
| I7 | FAIL | `dropped = true` thì phải `answered` và `connected` | Lỗi gán nhãn |
| I8 | FAIL | `path_type = relay_same` khi và chỉ khi `actual_turn_id_caller = actual_turn_id_callee ≠ null` (thiếu `actual_turn_id` thì dùng `relay_turn_*`; `ambiguous` thì bỏ qua) | Lỗi gán nhãn; hoặc hai bên cùng hostname pool nhưng bị coi là cùng máy |
| I9 | WARN | Trên **cùng một cửa sổ 5s** (`window_5s`), khi mọi chặng của cả hai chiều là `one_way` và `clock_sync_err_ms ≤ 2` (3 chặng mỗi chiều; `relay_same` chỉ 2): \|Σforward + Σreverse − `media_rtcp_rtt_ms`\| ≤ max(0.2 × `media_rtcp_rtt_ms`, 15 ms) | Một trong hai nguồn đo sai, sai đơn vị, hoặc chặng đo không cùng cửa sổ |
| I10 | FAIL | Số liệu hợp lệ: `0 ≤ value_ms ≤ 10000`; `0 ≤ loss_pct ≤ 100`; jitter ≥ 0; `0 ≤ utilization_pct ≤ 150`; **tổng histogram = số cửa sổ assessable tương ứng**; `success = true` ⇔ `error_code = none` | Sai đơn vị (giây/ms), counter âm, lỗi cộng histogram; allocation ghi `success = true` mà vẫn có mã lỗi (hoặc ngược lại) |
| I11 | WARN | `event_id` duy nhất (bản trùng bị loại và đếm) | Gửi lại do mạng chập chờn |
| I12 | FAIL | Decision dùng snapshot S thì `S.published_ts ≤ request_ts` | Selector đọc snapshot chưa được publish |
| I13 | FAIL | Mọi event đóng góp vào snapshot S phải có `event_ts < S.cutoff_ts` **và** `ingest_ts < S.cutoff_ts`. Snapshot đã publish là bất biến | Lỗi pipeline hoặc backtest rò dữ liệu tương lai |
| I14 | FAIL | Selector không được chặn lời mời gọi: **BE gửi lời mời song song với việc gọi Selector**. Selector lỗi/timeout thì `decision_source = static_fallback`; không bao giờ có `end_reason` do Selector | BE (Signaling) chờ Selector rồi mới gửi lời mời |
| I15 | FAIL | Nếu `experiment_id ≠ null` thì `arm ≠ null` và `assignment_ts ≤ request_ts` đầu tiên | Gán nhánh sau khi đã biết kết quả/quyết định |
| I16 | FAIL | KPI chính và guardrail chỉ đọc dữ liệu KPI-grade, kiểm tra ở **cấp dòng**: dòng `call_stats_5s` chỉ được làm đầu vào khi endpoint đó `derivation = pipeline` | Ai đó viết KPI đọc `call_stats_5s` của endpoint `sdk` |
| I17 | FAIL | Với endpoint `derivation = sdk`: `stats_sampling_prob` và `stats_sampling_reason` khớp quy tắc §13.3 khi tính lại từ `call_id` và outcome. Endpoint `pipeline` được kiểm bằng I22 | Cài đặt hash sai ngôn ngữ, quy tắc đổi mà không nâng `sampling_rule_version` |
| I18 (mới ở v0.3.0) | FAIL | Nếu `ice_transport_policy = relay` thì mọi attempt `connected` phải có `path_type ∈ {relay_relay, relay_same}` | Client thực tế đã nối P2P / `relay_direct` dù cấu hình là `relay` (BE gửi sai cấu hình hoặc client bỏ qua nó); `ice_transport_policy` ghi sai; hoặc `path_type` suy sai từ cặp candidate (kiểm tra `selected_*_candidate_type`). Nếu thật sự hay xảy ra thì giả định "chỉ relay" (Q7) đang sai |
| I19 (mới ở v0.4.0) | **WARN** | Nếu có `relayed_ip` hoặc `turn_server_ip`: máy suy ra từ `dim_turn_endpoint` phải trùng `turn_id` mà Selector chọn. Lệch thì ghi `turn_identity_mismatch`. Đây là **phát hiện vận hành**, không phải lỗi dữ liệu | Hostname pool hoặc geo-DNS đưa client tới máy khác dự định; `dim_turn_endpoint` thiếu/cũ (IP mới chưa được khai báo); hoặc các nguồn IP mâu thuẫn nhau |
| I20 (mới ở v0.4.0) | FAIL | Attempt `connected` có `callee_device_id = call_outcome.answered_device_id`. Decision và allocation của thiết bị không bắt máy không được ghép vào attempt đó (`release_reason = other_device_answered`) | Pipeline ghép theo `call_id` + `side` mà bỏ `device_id`; `answered_device_id` ghi sai; hoặc SDK điền nhầm `callee_device_id` |
| I21 (mới ở v0.4.0) | FAIL | KPI chỉ gồm cuộc gọi `call_type = one_to_one` lúc tạo. Với `converted_to_group = true`, mọi cửa sổ sau `converted_ts` không đánh giá được. **Guardrail hạ tầng `turn_utilization_p95` được miễn**: tính trên toàn bộ tải, kể cả cuộc gọi nhóm | Query KPI quên lọc `call_type`; `converted_ts` thiếu nên cửa sổ sau khi chuyển nhóm lọt vào histogram |
| I22 (mới ở v0.4.0) | FAIL | Endpoint `derivation = pipeline` ⇒ `call_stats_5s` của endpoint đó có **mọi** cửa sổ đã gửi (không lấy mẫu), cùng `window_s` và `quality_rule_version`. Cửa sổ thiếu chỉ do gửi thất bại, và được phản ánh trong `measurement_coverage` | SDK vẫn áp ring buffer/lấy mẫu cho endpoint `pipeline`; trộn dữ liệu khác `window_s` hoặc khác phiên bản bucket; lô gửi thất bại mà không tính vào `measurement_coverage` |
| I23 (mới ở v0.4.0) | FAIL | `end_reason = ice_failed` ⇒ `answered ∧ ¬connected`. Và `answered ∧ ¬connected` ⇒ `end_reason ∈ {ice_failed, normal_hangup, app_crash, unknown}` | `ice_failed` gán cho cuộc gọi chưa bắt máy, hoặc cho cuộc gọi đã từng nối (lẽ ra là `dropped_*`); cuộc gọi bắt máy mà chưa nối nhưng ghi `dropped_network`/`rejected`...; `connected` ghi sai |
| I24 (mới ở v0.4.0) | FAIL | `dropped = true` ⇔ `end_reason ∈ {dropped_network, dropped_turn}` | Cờ `dropped` và `end_reason` do hai nơi ghi mà không đồng bộ; gán `dropped` cho `app_crash` |

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

v0.1 so tổng 3 chặng một chiều với RTT/2. Cách đó **chỉ đúng nếu mạng đối xứng**, mà mạng thật thường không (4G upload khác download). Ví dụ minh họa: một đường có forward 140 ms + reverse 160 ms (RTT 300, RTT/2 = 150) và một đường khác forward 150 ms + reverse 10 ms (RTT 160, RTT/2 = 80). RTT/2 báo hai chiều bằng nhau trong khi thực tế một chiều dài hơn hẳn chiều kia. Kiểm tra chéo bằng RTT/2 sẽ báo lỗi oan hoặc bỏ sót lỗi thật. Vì I9 chỉ chạy khi đủ điều kiện, nên mức là WARN: không đủ điều kiện thì bỏ qua chứ không coi là sai. **Cách tính hiện hành (v0.4.0):** I9 chạy trên **từng cửa sổ 5 giây** (`window_5s`) chứ không trên tóm tắt epoch: |Σforward + Σreverse − `media_rtcp_rtt_ms`| ≤ max(0.2 × `media_rtcp_rtt_ms`, 15 ms). Khi `relay_same` thì mỗi chiều chỉ có 2 chặng. *Vì sao theo cửa sổ:* so sánh "cùng thời điểm" mới có nghĩa; so trung bình cả epoch thì mạng đổi giữa chừng sẽ báo lệch oan.

### 14.4 I12 và I13: "thời điểm hệ thống biết"
Có ba mốc thời gian dễ lẫn:
- `event_ts`: sự việc xảy ra lúc nào (đồng hồ của nơi sinh).
- `ingest_ts`: hệ thống **nhận được** lúc nào.
- `published_ts` (của snapshot): snapshot **bắt đầu được dùng** lúc nào.

Quy tắc: Selector tại thời điểm *t* chỉ được dùng snapshot đã publish trước *t* (I12). Và snapshot chỉ chứa event mà hệ thống **đã biết trước cutoff** — tức cả `event_ts` lẫn `ingest_ts` đều < `cutoff_ts` (I13).

**Ví dụ sự kiện đến muộn:** Một cuộc gọi kết thúc lúc 23:58 giờ VN ngày D. Điện thoại mất sóng, tới 00:20 ngày D+1 mới gửi được `call_outcome`. Với snapshot có cutoff 00:00 ngày D+1: `event_ts` = 23:58 < cutoff, nhưng `ingest_ts` = 00:20 > cutoff. Hệ thống *chưa biết* điều này lúc cutoff, nên event **không** được vào snapshot đó mà vào snapshot hôm sau. Nếu bỏ điều kiện `ingest_ts`, thì dựng lại snapshot sau này sẽ khác bản đã publish, và backtest sẽ "biết" những thứ mà hệ thống thật chưa biết, cho kết quả đẹp giả.

**Snapshot bất biến:** đã publish thì không sửa. Sửa logic hay bổ sung dữ liệu muộn thì tạo `v<n+1>` với `snapshot_id` mới (`parent_snapshot_id` trỏ về bản cũ). Quyết định đã ghi `feature_snapshot_id` cũ vẫn truy được chính xác bản cũ đó.

### 14.5 I14, I15, I16, I17: giải thích ngắn
- **I14 (Selector không chặn):** nếu Selector sập mà cuộc gọi cũng chết theo thì thuật toán "gây ra" lỗi, không phải "tối ưu" cuộc gọi. Selector chỉ được là cố vấn; hỏng thì dùng danh sách mặc định. Từ v0.3.0 luật nói rõ cách làm: **BE gửi lời mời song song với việc gọi Selector**, không chờ Selector xong mới gửi. Nhờ vậy độ trễ Selector không cộng vào thời gian đổ chuông, và Selector timeout chỉ dẫn tới `static_fallback` chứ không bao giờ thành `end_reason`.
- **I15 (gán nhánh trước quyết định):** nếu gán nhánh sau khi đã biết cuộc gọi diễn ra thế nào thì có thể (cố ý hoặc vô tình) chọn cuộc gọi dễ cho nhánh mình thích.
- **I16:** xem §3.
- **I17:** xem §13.3.
- **I18 (chỉ relay thì không có P2P, mới ở v0.3.0):** nếu cấu hình ICE là `relay` mà vẫn thấy cuộc gọi nối P2P thì hoặc cấu hình, hoặc dữ liệu, hoặc giả định "chỉ relay" đang sai. Bất biến này biến một giả định chưa xác minh (Q7) thành thứ kiểm tra được hằng ngày; vi phạm là FAIL vì nó làm sai cả cách đọc `path_type` lẫn `p2p_rate`.

### 14.6 I19–I24 (mới ở v0.4.0): giải thích ngắn

- **I19 (WARN, không phải FAIL):** máy thật (tra IP trong `dim_turn_endpoint`) khác máy Selector chọn. Đây **không phải dữ liệu sai**: dữ liệu ghi đúng cái đã xảy ra. Nó là một **phát hiện vận hành** ("DNS đang đưa client tới máy khác dự định"), nên hiện lên trang Data Quality và đi vào chỉ số `turn_identity_mismatch_rate` (§20.5). Nếu đặt FAIL thì pipeline sẽ loại đúng những cuộc gọi cho thấy vấn đề hạ tầng. Ví dụ: Selector chọn `VN-SGN-VTL-01` nhưng `relayed_ip = 203.0.113.30` thuộc `VN-SGN-VTL-03` trong `dim_turn_endpoint` ⇒ ghi `turn_identity_mismatch`; KPI theo TURN gán cho `VN-SGN-VTL-03`.
- **I20 (FAIL):** attempt `connected` phải đi với thiết bị đã bắt máy. Nếu sai, hạng TURN, `propensity` và allocation bị ghép từ **thiết bị khác**, làm hỏng mọi phân tích "TURN được đề xuất có được dùng không". Là FAIL vì đây là lỗi ghép dữ liệu, không phải hiện tượng đáng quan sát.
- **I21 (FAIL):** KPI chỉ tính `one_to_one`, và sau `converted_ts` không có cửa sổ nào được đánh giá. Là FAIL vì cuộc gọi nhóm lọt vào PCR sẽ làm sai chính định nghĩa của metric (§2B.4). **Ngoại lệ:** guardrail hạ tầng `turn_utilization_p95` được miễn và tính trên **toàn bộ** tải, vì TURN bị chiếm chỗ bởi cuộc gọi nhóm vẫn là TURN đầy thật; lọc đi thì tải bị đánh giá thấp.
- **I22 (FAIL):** endpoint `pipeline` phải có đủ mọi cửa sổ đã gửi, cùng `window_s` và `quality_rule_version`. Nếu bị lấy mẫu hay thiếu, histogram do pipeline dựng sẽ lệch **mà không báo**; đúng là thứ KPI-grade cấm. Cửa sổ thiếu chỉ được do gửi thất bại, và phải thể hiện trong `measurement_coverage`.
- **I23 (FAIL):** `ice_failed` nghĩa là **đã bắt máy mà media chưa bao giờ nối**. Ngược lại, cuộc gọi đã bắt máy mà chưa nối thì `end_reason` chỉ có thể là `ice_failed`, `normal_hangup` (người dùng bỏ máy vì im lặng), `app_crash` hoặc `unknown`. Là FAIL vì `setup_fail` (§20.1) dựa trực tiếp vào cặp (`answered`, `connected`, `end_reason`); ghi sai là PCR sai.
- **I24 (FAIL):** `dropped` và `end_reason` phải khớp: `dropped = true` ⇔ `dropped_network` hoặc `dropped_turn`. Nhánh `drop` của poor dựa vào đây.
- **Viết lại (không đổi ý chính):** I3 cho phép trả ít hơn `k` khi sau lọc không đủ TURN; I4 chỉ kiểm khi `live` và dùng `actual_turn_id`; I8 dùng `actual_turn_id`; I16 kiểm ở cấp dòng; I17 kiểm theo endpoint; I6 tách rõ hai vế.

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
SDK chỉ biết `hostname` của candidate relay. Pipeline tra `dim_turn.hostname` để ra `turn_id`, **chỉ khi hostname trỏ tới đúng một máy**. Hostname pool thì `relay_turn_*` là `null` và máy thật được xác định từ IP (§16.6).

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
2. Thiếu thì ghép theo (`call_id`, `decision_id`, `side`, `device_id`, `turn_id`, `transport`, `ice_generation`), với điều kiện allocation còn hiệu lực: `response_ts ≤ mốc < released_ts`, trong đó mốc = `ice_connected_ts` (hoặc `start_ts` nếu attempt thất bại), và `released_ts = null` nghĩa là vẫn còn hiệu lực. **Không bao giờ** ghép allocation của thế hệ cũ vào attempt mới chỉ vì cùng `turn_id`.
3. Xuất ra `used_by_ice` (bool) và `match_method` (`id`, `rule`, `ambiguous`).

### 16.4 `fact_call`
Một dòng mỗi cuộc gọi: các cột KPI (tính từ dữ liệu KPI-grade), `rank_used_*`, `joint_propensity = p_caller × p_callee`, `arm`, `blind_cost_ms` (chỉ sim). Từ v0.4.0 có thêm:
- `poor_category` ∈ {`setup_fail`, `drop`, `quality`, `none`}: cuộc gọi tệ vì lý do nào (ba nhánh của §20.1; `none` = không poor).
- `quality_assessment_status` (enum ở §6): `not_applicable` nếu ¬(answered ∧ connected); `assessed` nếu mọi (bên, metric) đều xác định; `partially_assessed` nếu chỉ một phần xác định; `unclassifiable` nếu không cái nào xác định.
- `actual_turn_id_*` và `turn_identity_method` (§16.6).
- Thông tin client của hai đầu: `platform`, `app_version`, `device_class`.

**`joint_propensity` (cập nhật):** `p_side` = `propensity` của candidate có `rank = chosen_rank` trong decision mà attempt `connected` **đầu tiên** dùng. *Vì sao `chosen_rank`:* "hành động" của policy là việc nó yêu cầu client thử hạng nào (`chosen_rank`); việc client phải fallback sang hạng khác là **một phần kết quả**, không phải hành động của policy. Dùng xác suất của TURN thực dùng sẽ lẫn hai thứ đó, và làm hỏng việc cân lại (OPE).

### 16.5 `dq_results`
`(pipeline_run_id, dt, check_id, table, level, status, n_checked, n_bad, sample_event_ids[])`: kết quả mọi kiểm tra bất biến. (Khóa đổi tên thành `pipeline_run_id` ở v0.4.0: đó là lần chạy **pipeline**, khác với `sim_run_id` là lần chạy simulator.)

**Check `release_regression` (mới ở v0.4.0, WARN):** có check phân phối theo `app_version`. Nếu một metric lệch **đột ngột ngay sau** một bản phát hành app thì WARN `release_regression`. *Vì sao:* để không đổ nhầm cho TURN (câu chuyện Android 3.12.0 ở §2B.1). Khi lệch **nghiêm trọng** (ngưỡng trong `kpi.yaml`, ví dụ trung vị lệch ≥ 10 lần so với các bản khác cùng nền tảng), metric đó của bản app bị **cách ly**: coi như không đánh giá được, cho tới khi có quy tắc sửa được duyệt và có version (`correction_rule_version`). Pipeline **không tự đoán và sửa đơn vị**. *Vì sao:* tự nhân ×1000 theo phỏng đoán có thể che mất một lỗi khác; cách ly thì khoảng PCR [low, high] rộng ra nhưng không bị lệch giả. Chuyển đổi đơn vị theo **đặc tả của nguồn** (W3C trả giây ⇒ × 1000 ở adapter) vẫn làm bình thường. Kịch bản S25 kiểm tra điều này (§19.4).

### 16.6 Danh tính TURN thực: `actual_turn_id` (mới ở v0.4.0, contract §8.6)

Pipeline xuất `actual_turn_id_caller`, `actual_turn_id_callee` (máy TURN **thực tế** của mỗi bên) và `turn_identity_method` ∈ {`ip`, `hostname`, `ambiguous`}.

**Thứ tự ưu tiên tra cứu** trong `dim_turn_endpoint` có hiệu lực tại thời điểm đó:

| Ưu tiên | Nguồn | Vì sao đặt ở vị trí này |
|---|---|---|
| 1 | `relayed_ip_*` của **cặp candidate được chọn** (`ice_attempt`) | Là địa chỉ relay của chính kết nối đã dùng: bằng chứng trực tiếp nhất |
| 2 | `relayed_ip` của **allocation đã dùng** | Cũng là IP relay, nhưng của allocation (phải ghép đúng allocation trước, §16.3) |
| 3 | `turn_server_ip` | IP client gửi tới; đúng máy nếu không có load balancer/anycast ở giữa |
| 4 | Hostname (`dim_turn_endpoint.hostname`), **chỉ khi hostname trỏ tới đúng một máy** | Yếu nhất: hostname pool không phân biệt được máy |
| — | Không có gì dùng được | `actual_turn_id = null` |

Các nguồn mâu thuẫn nhau ⇒ WARN (I19). `turn_identity_method` = `ip` (từ nguồn 1–3), `hostname` (nguồn 4), hoặc `ambiguous` (hostname pool, không có IP).

**Quy tắc dùng:**
- **Mọi KPI theo TURN dùng `actual_turn_id`**, không dùng `turn_id` của Selector và không dùng `relay_turn_*` (riêng I4 và I8 mới lùi về `relay_turn_*` khi thiếu `actual_turn_id`). Khi `ambiguous`, cuộc gọi vào nhóm **"pool"**, không gán bừa cho một máy: gán bừa thì vừa đổ lỗi nhầm vừa che lỗi thật.
- **Tính theo từng đầu:** cuộc gọi `relay_relay` góp vào TURN của **mỗi** bên; `relay_same` góp **một lần**. Một cuộc gọi không được đếm hai lần cho cùng một máy.
- `device_class` được suy ra ở đây (từ `device_model` theo bảng tra có version), cùng với thông tin client.

*Ví dụ minh họa (số tự đặt):* attempt có `relayed_ip_caller = 203.0.113.10`; `dim_turn_endpoint` ghi `203.0.113.10` → `VN-SGN-VTL-03`. `actual_turn_id_caller = VN-SGN-VTL-03`, `turn_identity_method = ip`, dù `turn_url` là hostname pool.

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

Nhóm càng chi tiết càng sát thực tế nhưng càng ít dữ liệu. Feature store cung cấp **mọi cấp**. **Cách Selector chọn cấp là thiết kế của Đoàn** (contract không bắt buộc một cách). Khuyến nghị: cấp chi tiết nhất mà **mọi** candidate đều có `n_eff ≥ 30`, *vì sao:* nếu TURN A được chấm ở cấp 4 còn TURN B ở cấp 1 thì hai điểm số không so sánh được với nhau. Cấp đã dùng phải ghi vào `score_components.backoff_level` của **từng candidate** và vào `fallback_reason` (ví dụ `backoff_L1`). Đây là lời giải cho kịch bản Cold-start.

**Định nghĩa thống kê (v0.4.0; tham số tạm thời nằm trong `kpi.yaml`):**
- **Trọng số mỗi cuộc gọi** `w = 0.5^(tuổi_ngày / 7)`; **`n_eff = Σ w`**. Dữ liệu 7 ngày tuổi có trọng số một nửa, 14 ngày thì một phần tư.
- **Giá trị chặng cấp cuộc gọi** = Σ(`value_ms` × `n_samples`) / Σ `n_samples` qua các epoch của cuộc gọi. Mỗi cuộc gọi đóng góp **một** giá trị.
- **`p50_shrunk = (n_eff · p50 + m · p50_cha) / (n_eff + m)`** với `m = 30`, "cha" = cấp backoff kế tiếp. Nhóm ít mẫu (`n_eff` nhỏ) bị kéo mạnh về mức của cấp cha; nhóm nhiều mẫu gần như giữ nguyên `p50`. Ví dụ minh họa: `n_eff = 10`, `p50 = 20`, `p50_cha = 35` ⇒ (10×20 + 30×35)/(10+30) = 31.25.

### 17.1 `feat_leg_stats`: chặng user ↔ TURN

**Nguồn (v0.4.0):** `path_leg_measurement[epoch_summary]` với `leg_type = user_turn`, `method ∈ {inband, idle_probe}`. Số đo **probe** (`call_id = null`, `network_epoch = null`) là nguồn hợp lệ cho feature, nhưng **không bao giờ cho KPI**.

| Field | Nghĩa | Vì sao cần |
|---|---|---|
| `snapshot_id`, `segment_level`, `segment_key` | Snapshot nào, nhóm user cấp nào | Xem §17.0 |
| `turn_id` | TURN nào | |
| `direction` (đổi giá trị ở v0.4.0) | `user_to_turn` hoặc `turn_to_user`, suy từ `side` + `direction` của §10.3: caller/`forward` và callee/`reverse` là `user_to_turn`, còn lại là `turn_to_user` | Từ góc nhìn của **user** thì chiều "đi lên TURN" và "từ TURN về" mới có nghĩa; `forward/reverse` là theo chiều caller→callee nên lẫn hai bên |
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
Nguồn: `path_leg_measurement[epoch_summary]` với `leg_type = turn_turn`, `method ∈ {inband, mesh_probe}`. Field: `snapshot_id`, `src_turn`, `dst_turn` (gói tin đi từ `src_turn` tới `dst_turn`), `direction`, `metric`, `hour_bucket`, `n_raw`, `n_eff`, `p50`, `p95`, `loss_mean`, `jitter_p95`, `source_mix`, `last_observed_ts`. Cuộc gọi quốc tế (Nhật ↔ Đức) có chặng giữa chiếm phần lớn độ trễ; đề bài yêu cầu tối ưu kết hợp hai đầu.

### 17.3 `feat_turn_health`
`snapshot_id`, `turn_id`, `health_status`, `health_score`, `utilization_p95_24h`, `alloc_success_24h` (+ khoảng tin cậy Wilson `ci_low`, `ci_high`), `incidents_detected_7d`, `stability_cv_24h`. Khoảng tin cậy cho thấy 3/3 thành công khác hẳn 3000/3000 dù cùng 100%.

### 17.4 `feat_path_history`
`snapshot_id`, `caller_segment_key` (cấp 2), `callee_segment_key` (cấp 2), `turn_caller`, `turn_callee`, `n_calls`, `n_eff`, `poor_rate` (+ khoảng tin cậy, theo **đúng định nghĩa §20.1**), `drop_rate`, `setup_fail_rate` (đổi tên từ `ice_fail_rate` ở v0.4.0), `last_observed_ts`. Đây là Historical Connection mà đề bài yêu cầu: có những thứ chỉ thấy ở mức cả đường (một cặp TURN hay rớt do lỗi tương thích). `poor_rate` dùng cùng định nghĩa PCR nên feature và KPI không lệch nhau.

### 17.5 `feat_callee_prior`
`snapshot_id`, `caller_segment_key` (cấp 2), `callee_country`, `callee_vn_region`, `n`, `share`. Ví dụ "người gọi miền Nam thì 62% người nghe ở miền Nam…". Khi gọi mù, thuật toán dùng phân phối này để chọn TURN tốt nhất xét trên trung bình các khả năng. Chỉ chứa số đếm, an toàn về riêng tư.

### 17.6 `feat_turn_alloc_latency`: tách riêng, **không phải độ trễ chặng**
`snapshot_id`, `segment_key`, `turn_id`, `transport`, `n`, `alloc_ms_p50`, `alloc_ms_p95`, `alloc_success_rate` (+ khoảng tin cậy). Đây là chỗ duy nhất `alloc_ms` được thống kê, vì nó là chỉ báo "TURN này phản hồi allocation nhanh/chậm" chứ không phải độ trễ truyền media. Nằm trong bảng riêng để không ai vô tình ghép nó vào độ trễ chặng.

### 17.7 `health_snapshot`: ảnh chụp sức khỏe mỗi phút (mới ở v0.4.0, contract §9.7)

Feature snapshot cập nhật mỗi ngày, quá chậm để né một TURN vừa sập. Vì vậy có thêm **health snapshot mỗi phút**, dựng từ `turn_health_1m`, dùng cho health filtering lúc runtime.

| Field | Nghĩa | Vì sao cần |
|---|---|---|
| `health_snapshot_id` | Mã bản, dạng `hl-YYYYMMDDTHHMM` | `selector_decision.health_snapshot_id` trỏ vào đây |
| `cutoff_ts`, `published_ts` | Cutoff (đầu phút) và lúc publish | I12 và I13 áp dụng như feature snapshot: Selector dùng bản mới nhất có `published_ts ≤ request_ts`, và bản chỉ chứa dữ liệu trước cutoff |
| `turn_id` | TURN nào | |
| `health_status`, `health_score` | Trạng thái và điểm 0–1 (cao = tốt) | Đầu vào lọc TURN `down`/`overloaded` |
| `utilization_pct_5m`, `alloc_fail_rate_5m` | Tải và tỉ lệ allocation lỗi trung bình 5 phút | Phát hiện sớm quá tải/lỗi |

Snapshot này **bất biến** như feature snapshot.

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

Một file JSON cho mỗi lần chạy, commit cùng kết quả. Field: `sim_run_id`, `run_kind`, `benchmark_id`, `replicate_seed`, `simulator_version`, `git_commit`, `config_hash`, `contract_version`, `topology_version`, `network_profile_version`, `scenario_version`, `incident_schedule_version`, `incidents_sha256`, `root_seeds` {traffic, network, incidents, noise, behavior, policy} — seed gốc; việc rút số dùng RNG có khóa, `policy_version`, `exploration_epsilon`, `connection_mode`, `ice_transport_policy`, `be_region`, `initial_snapshot_hash`, `burn_in_days`, `environment_dir`, `started_at`, `completed_at`.

**Vì sao cần?** Dữ liệu giả vô giá trị nếu không biết nó sinh ra thế nào. Manifest cho phép tái lập (cùng manifest → cùng hash dữ liệu, có test), biết phiên bản mọi thành phần, và chứng minh các cam kết trước khi chạy.

### 19.3 `scripted` và `blind_benchmark`

| Loại | Dùng cho | Sự cố |
|---|---|---|
| `scripted` | Test tự động, demo các kịch bản S01–S25 | **Công khai**, có kỳ vọng rõ (ví dụ "TURN X sập lúc 10:00, thuật toán phải né") |
| `blind_benchmark` | So sánh policy, insight report | **Ẩn**. `incidents_sha256` (hash của lịch sự cố) được **commit trước khi phân tích** |
| `dev` | Phát triển | Tùy ý |

**Vì sao `incidents_sha256`?** Lịch sự cố của benchmark mù được giữ kín. Cam kết hash trước chứng minh sau này: "lịch sự cố này đã cố định từ trước khi ta nhìn kết quả", tức không ai chỉnh sự cố cho hợp với kết luận. Khi công bố, ai cũng kiểm tra lại bằng cách băm file sự cố.

### 19.4 Tag cuộc gọi khác với kịch bản hệ thống

- **Tag cuộc gọi** (`scenario_tag`, ghi trong `call_session`): chỉ mô tả *loại cuộc gọi*: `S01_vn_same_region_same_isp`, `S02_vn_cross_region`, `S03_vn_same_region_cross_isp`, `S04_vn_intl_with_turn`, `S05_vn_intl_no_turn`, `S06_intl_same_area`, `S07_intl_cross_area`, `S09_cold_start`, `S10_network_change`, `S00_background`.
- **Kịch bản hệ thống** (chỉ nằm trong manifest của `scripted`, **không bao giờ** là tag cuộc gọi): `S08_turn_failure`, `S11_turn_overload`, `S12_isp_congestion`, `S13_regional_outage`, `S14_asymmetric_path`, `S15_selector_timeout`, `S16_stale_snapshot`, `S17_delayed_telemetry`, `S18_turn_recovery`, `S19_p2p_preferred` (chạy với `ice_transport_policy = all`), `S20_call_burst`, và **năm kịch bản production mới ở v0.4.0** (S21–S25, bên dưới).

**Năm kịch bản production (S21–S25).** Contract ghi **tên** các kịch bản; **kỳ vọng chính thức nằm ở spec §10**. Bảng dưới tóm tắt:

| Kịch bản | Điều production nó mô phỏng (§2B) | Kiểm tra điều gì |
|---|---|---|
| `S21_multi_device_ring` | Điều 3: B có nhiều thiết bị cùng đổ chuông | `answered_device_id`, `n_devices_rung > 1`, allocation `other_device_answered` không bị ghép vào attempt (I20) |
| `S22_group_call_filtered` | Điều 4: có cuộc gọi nhóm | Cuộc gọi `group` bị lọc khỏi KPI (I21); cuộc gọi chuyển nhóm giữa chừng thì cửa sổ sau `converted_ts` không đánh giá được |
| `S23_turn_pool_hostname` | Điều 2: hostname pool trỏ tới nhiều máy | `actual_turn_id` từ IP, `turn_identity_method`, `turn_identity_mismatch` (I19), nhóm "pool" khi `ambiguous` |
| `S24_raw_stats_derivation` | Điều 5: SDK chỉ gửi getStats thô | `derivation = pipeline`, `raw_full`, I22, và kết quả giống hệt `derivation = sdk` (derivation-equivalence) |
| `S25_app_release_regression` | Điều 1: một bản app phát hành bị lỗi (báo jitter bằng giây) | Check DQ `release_regression` (§16.5) cắm cờ và **cách ly** metric jitter của bản đó; PCR theo TURN của lần chạy không lỗi nằm trong khoảng [low, high] của lần chạy có lỗi; KPI cắt theo `app_version` thấy lỗi nằm ở app, không ở TURN |

**Mặc định production-like của simulator:** thông tin client theo phân bố nền tảng; một thiết bị mỗi user; chỉ cuộc gọi 1-1; mỗi máy TURN một IP dùng cho cả hai vai trò (`role = both`). Các trường hợp còn lại (nhiều thiết bị, nhóm, pool, raw stats, release lỗi) chỉ được kiểm tra bằng S21–S25. Vì vậy các tính năng production **không làm đổi kết quả** của các lần chạy benchmark thường.

**Vì sao tách?** Nếu một cuộc gọi mang tag `S08_turn_failure` thì bất kỳ ai đọc `call_session` đều biết "TURN đang sập" mà không cần tự phát hiện. Tag cuộc gọi chỉ được nói loại cuộc gọi (vùng nào, ISP nào), còn sự cố nằm ở `incident_truth` bị giấu. Bộ kịch bản phải có ít nhất một kịch bản Geo thắng, một Historical thắng, một Smart thắng, để chứng tỏ benchmark không thiên vị.

---

## 20. KPI Dictionary (§13 của contract): đo "tốt" như thế nào

Bản máy đọc là `contracts/kpi.yaml`. Mọi KPI ở mục này **chỉ đọc dữ liệu KPI-grade** (I16). Ngưỡng ghi ở đây là *tạm thời* và được đóng băng trong `kpi.yaml` trước `blind_benchmark` đầu tiên; sau đó chỉ đổi bằng version mới.

**Ngữ nghĩa percentile:** `call_*` = trong một cuộc gọi; `population_*` = giữa các cuộc gọi, tính trên giá trị cấp cuộc gọi. **Không bao giờ lấy trung bình các P95.**

### 20.1 Phân loại một cuộc gọi: "tệ" nghĩa là gì?

**Phạm vi (v0.4.0, làm rõ):** **chỉ cuộc gọi `call_type = one_to_one`** (I21). Phần này trước đây chỉ ngầm định trong spec; nay ghi rõ trong định nghĩa. Với simulator kết quả không đổi vì mọi cuộc gọi mô phỏng đều là 1-1. Xem §20.6.

Với cuộc gọi *c*, metric *m* ∈ {RTT, loss, jitter}, **chỉ trên audio**, gộp mọi epoch và tính **riêng từng bên** (caller, callee):

```
PoorFraction_m(c, bên) = Σ cửa sổ tệ_m / Σ cửa sổ đánh giá được_m     (chỉ xác định khi Σ cửa sổ đánh giá được ≥ 4)

Cửa sổ tệ:  RTT     → bucket ≥ 300 ms   (media_rtcp_rtt)
            loss    → bucket ≥ 3 %
            jitter  → bucket ≥ 30 ms    (jitter estimate)

quality_poor(c)    = tồn tại bên nào, metric nào xác định mà PoorFraction ≥ 0.20
quality_ok(c)      = mọi metric của mọi bên đều xác định và đều < 0.20
còn lại            → quality_unknown(c)   (không có gì xác định, hoặc chỉ một phần xác định mà không có cái nào poor)

setup_fail(c)  = answered ∧ ¬connected ∧ end_reason ≠ app_crash
                 (gồm ice_failed và người dùng bỏ máy khi media chưa nối được, I23)
drop(c)        = dropped          (⇔ end_reason ∈ {dropped_network, dropped_turn}, I24)
quality_bad(c) = answered ∧ connected ∧ ¬dropped ∧ quality_poor(c)

poor(c)           = setup_fail(c) ∨ drop(c) ∨ quality_bad(c)        (ba nhánh rời nhau)
unclassifiable(c) = answered ∧ connected ∧ ¬dropped ∧ quality_unknown(c)
```

**`poor` là ba nhánh rời nhau (v0.4.0, đổi nghĩa so với bản nháp trước):**

| Nhánh | Là gì | Người dùng trải nghiệm |
|---|---|---|
| `setup_fail` | Đã bắt máy mà media **không bao giờ nối được** (trừ `app_crash`) | Bấm nghe rồi im lặng |
| `drop` | Đã nối, rồi rớt do mạng/TURN (`dropped_network`, `dropped_turn`) | Đang nói thì đứt |
| `quality_bad` | Đã nối, không rớt, nhưng ≥ 20% cửa sổ tệ ở một bên/metric | Nói được nhưng giật, trễ, mất tiếng |

*Vì sao ba nhánh phải rời nhau:* mỗi cuộc gọi chỉ thuộc đúng một nhánh (hoặc không nhánh nào), nên `pcr_itt_low` = `setup_fail_rate` + `drop_rate` + `quality_poor_rate` **chính xác**, không đếm đôi. `fact_call.poor_category` ghi nhánh đó (`setup_fail`, `drop`, `quality`, `none`).

*Vì sao `unclassifiable` rời với `poor`:* `unclassifiable` chỉ dành cho cuộc gọi đã nối, không rớt, mà thiếu số đo; còn `poor` đã loại các cuộc gọi đó ở cả ba nhánh. Nhờ vậy **`pcr_itt_high − pcr_itt_low = unclassifiable_rate` đúng từng chữ**: khoảng giữa hai cận chính là phần cuộc gọi chưa phân loại được, không hơn không kém.

**Vì sao cuộc gọi đã bắt máy mà không nối được lại tính là poor?** Xem FAQ §23: người dùng đã bấm nghe rồi chẳng nghe được gì. Bản trước chỉ tính `end_reason = ice_failed`, nên một cuộc gọi bắt máy, im lặng, người dùng tự cúp (`normal_hangup`) bị **bỏ sót** và trông như cuộc gọi bình thường. Bản mới tính theo **trải nghiệm** (đã bắt máy ∧ chưa từng nối), không theo nhãn lý do.

Lý do kết thúc ngoài phạm vi TURN (`invite_undelivered`, `not_answered`, `rejected`, `cancelled_by_caller`, `app_crash`) và `normal_hangup` của cuộc gọi đã nối mà chất lượng ok **không** làm cuộc gọi bị tính tệ, nhưng cuộc gọi **vẫn ở trong cohort**. `app_crash` không bị tính là `setup_fail` vì app sập không nói lên gì về TURN.

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
| **Cohort** | Mọi `call_session` **có `call_type = one_to_one`** của experiment đã được gán `arm` (I15, I21), **kể cả** khi sau đó Selector timeout, static fallback, P2P (khi `ice_transport_policy = all`), allocation lỗi, không gửi được lời mời, hoặc không ai bắt máy |
| `pcr_itt_low` | Σ poor / \|cohort\| (cho rằng mọi cuộc gọi unclassifiable đều tốt) = `setup_fail_rate` + `drop_rate` + `quality_poor_rate` |
| `pcr_itt_high` | Σ (poor ∨ unclassifiable) / \|cohort\| (cho rằng mọi unclassifiable đều tệ) = `pcr_itt_low` + `unclassifiable_rate` |
| Đơn vị | %, **càng thấp càng tốt** |

**Vì sao cohort xác định trước quyết định (ITT)?** Nếu chỉ tính cuộc gọi "đã nối được qua TURN", thuật toán có thể "thắng" nhờ để những cuộc gọi khó rơi ra ngoài mẫu (ví dụ cuộc gọi phải static fallback, hay không gửi được lời mời, hay chuyển sang P2P khi `ice_transport_policy = all`, thì không được đếm). ITT đếm *mọi* cuộc gọi được giao cho nhánh đó, nên không thể thắng bằng cách đẩy vấn đề ra ngoài mẫu. Cohort được định nghĩa ở lúc gán nhánh (trước mọi quyết định), tức trước khi biết kết quả.

**Vì sao hai cận (low/high)?** Có những cuộc gọi không đủ số đo để phân loại. Tính chúng là tốt hay là tệ đều là giả định. Thay vì chọn bừa, báo cáo cả hai cực đoan: kết luận chỉ mạnh khi đúng ở cả hai. Nếu `low` và `high` chênh nhau nhiều tức là telemetry thiếu, và bản thân điều đó là thông tin (có guardrail `unclassifiable_rate`).

### 20.3 Tầng 1b: Metric phụ quan trọng (có điều kiện)

| KPI | Định nghĩa |
|---|---|
| `pcr_answered` (low/high) | Như trên nhưng mẫu số = cuộc gọi đã bắt máy trong cohort. Diễn giải là chất lượng **có điều kiện**, với giả định policy không ảnh hưởng việc bắt máy. Giả định này được **kiểm tra và báo cáo** (`answer_rate` theo nhánh), **không bao giờ dùng để đổi metric chính** |
| Thành phần (rời nhau, cùng mẫu số cohort; **có công thức ở v0.4.0**) | `setup_fail_rate` = Σ setup_fail / \|cohort\|, tách tiếp thành `ice_fail_rate` = Σ[`end_reason = ice_failed`] / \|cohort\| và `setup_abandon_rate` = phần còn lại (bắt máy, chưa nối, người dùng bỏ máy). `drop_rate` = Σ drop / \|cohort\|. `quality_poor_rate` = Σ quality_bad / \|cohort\|. `unclassifiable_rate` = Σ unclassifiable / \|cohort\|. `pcr_itt_low` = tổng ba thành phần đầu |
| Phễu (cùng mẫu số cohort; **có công thức ở v0.4.0**) | `invite_delivered_rate` = Σ[`ring_ts` ≠ null]; `answer_rate` = Σ answered; `selector_timeout_rate` = Σ cuộc gọi có ≥ 1 decision không có `response_ts`; `static_fallback_rate` = Σ cuộc gọi có ≥ 1 decision `static_fallback`; `p2p_rate` (= 0 theo định nghĩa khi `ice_transport_policy = relay`, I18); `app_crash_rate` = Σ[`end_reason = app_crash`] — không poor, không unclassifiable vì ngoài phạm vi TURN, nhưng **báo riêng theo nhánh** để nếu policy nào làm app crash nhiều hơn thì vẫn thấy |

*Vì sao đổi tên `ice_fail_rate` thành `setup_fail_rate` làm guardrail:* guardrail cũ chỉ đếm `ice_failed`, bỏ sót cuộc gọi bắt máy-mà-không-nối nhưng người dùng tự cúp. Contract ghi định nghĩa cũ "thiếu tử số". `ice_fail_rate` vẫn tồn tại nhưng chỉ là một **thành phần** của `setup_fail_rate`.

### 20.4 Tầng 2: Guardrail (non-inferiority)

Guardrail là "đừng làm hỏng thứ khác". Smart chỉ được gọi là tốt hơn nếu mọi guardrail không tệ hơn Geo quá biên cho phép δ.

| Guardrail | Hướng | Margin δ |
|---|---|---|
| `setup_fail_rate` (mẫu số cohort ITT; đổi tên từ `ice_fail_rate` ở v0.4.0) | thấp | +0.2 điểm % |
| `drop_rate` (mẫu số cohort ITT) | thấp | +0.2 điểm % |
| `cst_technical_p95` = P95(`ice_connected_ts − checks_start_ts`) trên attempt `connected` **có `attempt_seq` nhỏ nhất** của mỗi cuộc gọi; attempt thiếu `checks_start_ts` bị loại và tỉ lệ thiếu được báo kèm | thấp | +10% |
| `ttfm_post_answer_p95` = P95(max(0, max_bên(`first_media_received_ts`) − `answer_ts`)), **chỉ khi `connection_mode = post_answer`**. `first_media_received_ts` của một bên = **min trên mọi epoch** của thiết bị tham gia kết nối; cuộc gọi thiếu một bên bị loại, tỉ lệ loại được báo kèm | thấp | +10% |
| `selector_api_p95`: nguồn `selector_decision.api_latency_ms`, **mỗi `decision_id` tính một lần**, chỉ `decision_mode = live`, bỏ null (tỉ lệ null báo kèm) | thấp | ≤ 50 ms (tuyệt đối) |
| `selector_availability` = 1 − Σ(decision không có `response_ts`) / Σ decision, **trên cùng tập** với `selector_api_p95` | cao | ≥ 99.9% (tuyệt đối) |
| `static_fallback_rate` (định nghĩa ở Phễu) | thấp | +0.2 điểm % |
| `turn_utilization_p95` (mọi TURN, mọi phút; **miễn I21**: tính trên toàn bộ tải, kể cả cuộc gọi nhóm) | thấp | ≤ 85% (tuyệt đối) |
| `unclassifiable_rate` (độ đầy đủ telemetry) | thấp | +1.0 điểm % |
| `pcr_itt_high` theo từng `pair_group` (hiệu chéo bất lợi: `pcr_itt_high(Smart) − pcr_itt_low(Geo)`) | thấp | +0.5 điểm % |

**Cách tính chung (v0.4.0):** mọi phép tính thời gian dùng `event_ts_corrected` (§16.1); phân vị dùng nội suy tuyến tính (`quantile_cont`); mọi KPI theo TURN dùng `actual_turn_id` (§16.6). *Vì sao các "chỉ khi…, mỗi `decision_id` một lần":* một decision có hai dòng (caller, callee) và có thể nhiều thiết bị; đếm theo dòng thì một request bị tính 2 lần và độ trễ Selector bị trộn với shadow; `shadow` không phải thứ người dùng gặp. `ttfm` lấy **min theo epoch** vì media đầu tiên là cái người dùng nghe, và chỉ áp dụng `post_answer` vì với `pre_connect` mốc `answer_ts` không phải điểm bắt đầu của kết nối.

- "Điểm %" = hiệu số tuyệt đối (từ 1.0% lên 1.2% là +0.2 điểm %). "+10%" là tương đối.
- `max(0, …)` trong `ttfm_post_answer`: với `pre_connect`, media có thể đã tới trước khi người dùng bấm nghe, nên khoảng thời gian âm bị chặn về 0.
- `selector_api_p95`: vì BE gọi Selector song song với việc gửi lời mời và độ trễ nằm trong lúc đổ chuông (§2A.2), guardrail này chủ yếu bảo vệ trước timeout / `static_fallback` và năng lực chịu tải, không phải thời gian thiết lập người dùng cảm nhận.
- Guardrail `unclassifiable_rate` bảo vệ chống "thắng bằng cách làm mất telemetry".
- Guardrail theo `pair_group` bảo vệ chống việc thắng tổng thể bằng cách hy sinh một nhóm.

### 20.5 Tầng 3: Chẩn đoán (không dùng để kết luận thắng/thua)

`pnr` = Σ quality_bad / Σ (answered ∧ connected ∧ ¬dropped ∧ ¬quality_unknown), tức chất lượng có điều kiện trên cuộc gọi đã nối (**đã hạ cấp, không còn là metric chính**) · `population_media_rtcp_rtt_p50/p95` · `population_ice_stun_rtt_p95` · `population_loss` · `population_jitter_estimate_p95` · `mos_est` (E-model) · `max_epoch_p95` · `rank_of_used` · `est_vs_observed_mae` · `confidence_calibration` · `coverage_7d` · `ess` · `hhi_turn` · `alloc_success_rate` · `allocation_not_selected_rate` · `allocation_never_checked_rate` (khi có `ice_candidate_pair`) · `reserve_allocation_seconds` · `allocation_seconds_unanswered` · `blind_cost_ms` · regret · `setup_breakdown_post_answer` · `signaling_overhead_est_ms` · `poor_bottleneck_share` (ba chỉ số này mới ở v0.3.0, giải thích ngay dưới) · `turn_identity_mismatch_rate` (mới ở v0.4.0, §20.6) · mọi KPI chính và guardrail được **cắt theo `platform`, `app_version`, `device_class`** trên dashboard (mới ở v0.4.0, §20.6).

Mấy chỉ số cần giải thích: `mos_est` là điểm chất lượng ước lượng từ công thức E-model; `ess` = effective sample size, số mẫu hiệu dụng sau khi cân trọng số; `hhi_turn` = chỉ số dồn tập trung vào ít TURN (càng cao càng dồn); `coverage_7d` = tỉ lệ phân khúc có đủ dữ liệu trong 7 ngày; `reserve_allocation_seconds` và `allocation_seconds_unanswered` = chi phí giữ chỗ TURN dự phòng và giữ chỗ cho cuộc gọi không ai nghe.

**Ba chỉ số chẩn đoán mới ở v0.3.0.** Công thức chi tiết viết trong `contracts/kpi.yaml` lúc implement; chúng **không ảnh hưởng luật kết luận** (§21.4).

- **`setup_breakdown_post_answer`:** P50/P95 của **từng đoạn** thời gian từ lúc bắt máy tới lúc có tiếng, tính trên `event_ts_corrected`, **chỉ** khi `connection_mode = post_answer`. Bốn đoạn:

  | Đoạn | Là gì |
  |---|---|
  | `answer_ts → checks_start_ts` | signaling qua BE + gathering candidate |
  | `checks_start_ts → ice_connected_ts` | ICE (chính là `cst_technical`) |
  | `ice_connected_ts → dtls_connected_ts` | DTLS (bước mã hóa) |
  | `dtls_connected_ts → first_media_received_ts` | media bắt đầu tới |

  *Vì sao cần:* guardrail `cst_technical_p95` và `ttfm_post_answer_p95` chỉ cho biết chậm hay không. Bảng này cho biết **chậm ở đoạn nào**. Nếu đoạn đầu (có BE) chiếm phần lớn thì lỗi nằm ở signaling, không phải ở việc chọn TURN.
- **`signaling_overhead_est_ms`** = (`caller_signaling_rtt_ms` + `callee_signaling_rtt_ms`) / 2, xấp xỉ **một lượt tin nhắn B → BE → A**. *Vì sao cần:* để trừ phần do BE ra khỏi đoạn đầu ở trên, và để thấy đặt BE ở đâu thì lợi (§2A).
- **`poor_bottleneck_share`:** trong các cuộc gọi **poor**, tỉ lệ cuộc gọi có **chặng tệ nhất là `user_turn`** (chặng cuối từ máy người dùng tới TURN, "last mile") so với `turn_turn` (chặng giữa hai TURN). Tính từ `path_leg_measurement[epoch_summary]`. *Vì sao cần:* cuộc gọi tệ mà chặng tệ nhất là last mile (Wi-Fi yếu, 4G chập chờn) thì **đổi TURN gần như không cứu được**, còn chặng giữa `turn_turn` tệ nhất thì chọn cặp TURN khác **có thể cứu**. Chỉ số này cho biết trong các cuộc gọi tệ, bao nhiêu phần thuật toán chọn TURN có cơ hội cải thiện. Nó trả lời trực tiếp yêu cầu Data Insights của đề bài (chỉ ra nút thắt ở đâu và hành động nào có ích). Vì dùng số đo chặng nên đây chỉ là chẩn đoán, không bao giờ là nhãn PCR.

### 20.6 Phạm vi 1-1, và các cách cắt theo nền tảng (mới ở v0.4.0)

**Phạm vi chỉ cuộc gọi 1-1 (làm rõ, không đổi định nghĩa).**
- Cohort của `pcr_itt` và §20.1 **chỉ gồm `call_type = one_to_one`** (I21). Cuộc gọi `group` và `unknown` không vào KPI; số cuộc gọi bị loại vì `call_type ≠ one_to_one` được **báo cáo theo nhánh** để chắc việc loại không lệch giữa Geo và Smart.
- Cuộc gọi 1-1 **chuyển thành nhóm** (`converted_to_group = true`) vẫn thuộc cohort (lúc tạo nó là 1-1), nhưng mọi cửa sổ **sau `converted_ts`** không đánh giá được, vì nửa sau đi qua SFU.
- Ngoại lệ: `turn_utilization_p95` tính trên **toàn bộ** tải (kể cả cuộc gọi nhóm), vì đây là guardrail hạ tầng.
- **Không đổi kết quả simulator:** trước v0.4.0 điều này chỉ được ngầm hiểu trong spec. Mọi cuộc gọi mô phỏng đều là 1-1 nên cohort, `pcr_itt` và mọi số cũ **giữ nguyên**. Việc ghi rõ chỉ có tác dụng khi dữ liệu production có cuộc gọi nhóm.

**Cắt theo nền tảng.** Mọi KPI chính và guardrail được **cắt theo `platform`, `app_version`, `device_class`** trên dashboard. Đây là **chẩn đoán**, không đổi luật kết luận (§21.4): Smart tốt hơn hay tệ hơn vẫn được phán trên toàn bộ cohort, không phán theo từng lát cắt. *Vì sao:* cắt để trả lời "chỗ tệ là do TURN hay do bản app", kết hợp với check `release_regression` (§16.5). Cắt nhiều lát rồi chọn lát đẹp để kết luận là cách tự lừa mình.

**`turn_identity_mismatch_rate` (chẩn đoán, từ I19).** Tỉ lệ cuộc gọi mà máy TURN thật (`actual_turn_id`) khác máy Selector chọn. *Vì sao cần:* nếu tỉ lệ này cao thì nhiều cuộc gọi không đi theo đề xuất, và không công bằng khi chấm Selector theo kết quả của những cuộc gọi mà client được DNS đưa tới máy khác. Nó là tín hiệu để đội hạ tầng xem lại hostname pool/geo-DNS, không phải tiêu chí thắng thua.

---

## 21. Đánh giá (Evaluation): làm sao biết Smart thật sự tốt hơn Geo

### 21.1 Estimand: ta đang đo cái gì?
`Δ = PCR_itt(Smart) − PCR_itt(Geo)` trên **cùng các yếu tố ngoại sinh**. So sánh với Historical theo cùng cách. Các họ policy (qua `policy_version`): `geo_baseline@*`, `historical@*`, `smart@*`. Hiệu ứng này là hiệu ứng **ITT**: "nếu giao nhánh này cho mọi cuộc gọi thì tỉ lệ cuộc gọi tệ khác nhau bao nhiêu".

### 21.2 Thiết kế trên simulator

1. **Mỗi policy một môi trường cô lập.** Mỗi (policy, seed) là một lần chạy riêng với `environment_dir` riêng, có feature store, health state, tải TURN và cache riêng. Vì sao: nếu hai policy chạy chung một thế giới, Smart dồn người vào TURN X làm X chậm và Geo cũng chịu hậu quả (interference), nên không đo được hiệu ứng riêng của từng policy.
2. **Yếu tố ngoại sinh dùng chung.** Traffic (ai gọi ai, lúc nào, có bắt máy không, thời lượng dự định, thời điểm đổi mạng), lịch sự cố, mạng nền. Mọi policy phải gặp *đúng cùng một thế giới bên ngoài*.
3. **Yếu tố nội sinh được phép khác nhau** (tải TURN, lịch sử, snapshot): đó là hiệu ứng cần đo.
4. **RNG có khóa, không phải luồng tuần tự.** Giá trị ngẫu nhiên là hàm của (seed, thực thể, thời điểm), ví dụ `(seed, call_id, "answer")` cho việc bắt máy, `(seed, call_id, leg, direction, window_idx, "noise")` cho nhiễu, `(seed, turn_id, ts_bucket, "net")` cho mạng nền. **Số event do policy sinh ra không được làm xê dịch bất kỳ luồng ngẫu nhiên nào.**

**Vì sao "mỗi loại một luồng riêng" (traffic, network…) vẫn chưa đủ?** Luồng ngẫu nhiên tuần tự là một dãy số rút lần lượt. Dù đã tách luồng cho `network`, nếu Smart sinh ra 5.000 mẫu nhiễu còn Geo sinh 4.000 mẫu thì mẫu thứ 4.001 trở đi của hai nhánh **lệch nhau**: cùng thời điểm nhưng ra nhiễu khác, và từ đó hai nhánh sống trong "thế giới khác" chỉ vì số lần rút khác nhau. RNG có khóa tính giá trị trực tiếp từ (seed, call_id, ...) nên nhiễu của cuộc gọi X ở thời điểm Y luôn như nhau bất kể có bao nhiêu event khác. (`root_seeds` trong manifest vẫn ghi lại seed gốc của từng nhóm, nhưng việc rút số phải theo khóa.)

5. **Khởi đầu giống nhau.** Mọi policy dùng cùng `initial_snapshot_hash`. **Burn-in 3 ngày** bị loại khỏi đánh giá, vì lúc đầu hệ thống còn đang ấm lên.
6. **Tái lập:** cùng manifest → cùng hash dữ liệu (có test).
7. **BE-invariance** (v0.3.0, siết lại ở v0.4.0): cùng seed và policy, đổi `be_region` thì `pcr_itt` và mọi metric chất lượng phải **giống hệt**; chỉ các chỉ số thời gian thiết lập được đổi. Vì BE làm **dịch thời điểm media bắt đầu**, phép thử này chạy trên **kịch bản scripted có truth không đổi theo thời gian** và health không đổi (nếu truth đổi theo thời gian thì dịch thời điểm sẽ đổi số đo một cách chính đáng). Nhiễu đo khóa theo `window_idx` (tương đối với neo của endpoint) nên không đổi khi neo dịch. Độ trễ BE↔Selector trong sim không phụ thuộc `be_region` (giả định đặt cùng chỗ), nên quyết định của Selector không đổi.
8. **Derivation-equivalence** (v0.4.0): trên cùng dữ liệu, `call_stats_epoch` do SDK tính và do pipeline tính từ `call_stats_5s` phải giống hệt (có test).

### 21.3 Đơn vị độc lập = seed, và power analysis

- **Đơn vị độc lập là seed, không phải cuộc gọi.** Với mỗi seed *r*, tính `d_r` (hiệu PCR giữa hai policy) trên **toàn bộ cuộc gọi gộp chung** có `initiated_ts` sau burn-in (v0.4.0: không lấy trung bình các tỉ lệ theo ngày, vì ngày ít cuộc gọi sẽ có trọng số ngang ngày nhiều cuộc gọi). Mỗi seed là một thế giới độc lập.
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
| **Smart tốt hơn** | `UpperCI95(worst) < 0` **và** mọi guardrail **đạt** (theo đúng loại của nó, bên dưới) |
| **Smart tệ hơn** | `LowerCI95(best) > 0` **hoặc** có ít nhất một guardrail **vi phạm** |
| **INCONCLUSIVE** | Mọi trường hợp còn lại, kể cả khi CI chỉ chạm margin |

**Khoảng tin cậy (v0.4.0):** `UpperCI95` / `LowerCI95` là hai đầu của khoảng tin cậy **hai phía** 95% (98.33% cho guardrail theo `pair_group`), tính bằng **t-interval** trên R giá trị theo seed. *Vì sao t-interval:* R thường nhỏ (vài chục seed), phân phối chuẩn sẽ cho khoảng hẹp quá mức.

**Hai loại guardrail, mỗi loại có điều kiện "đạt" và "vi phạm" riêng:**

| Loại | Kiểm tra trên | Đạt khi | Vi phạm khi |
|---|---|---|---|
| **Tương đối** (δ dạng "+x điểm %" hoặc "+x%") | ΔG_j = G_j(Smart) − G_j(Geo). "+x%" nghĩa là δ_j = x% × **trung bình qua các seed của G_j(Geo)** | `UpperCI95(ΔG_j) < δ_j` | `LowerCI95(ΔG_j) > δ_j` |
| **Tuyệt đối** (δ dạng "≤ x" hoặc "≥ x") | Chính G_j(Smart) | `UpperCI95(G_j) ≤ x` (hoặc `LowerCI95(G_j) ≥ x` nếu guardrail "cao = tốt") | `LowerCI95(G_j) > x` (hoặc `UpperCI95(G_j) < x`) |

Guardrail tính từ hai cận PCR (ví dụ `pcr_itt_high` theo `pair_group`) dùng hiệu chéo bất lợi `pcr_itt_high(Smart) − pcr_itt_low(Geo)`. Nằm giữa "đạt" và "vi phạm" thì không bên nào thỏa, và kết luận rơi vào INCONCLUSIVE.

- **Non-inferiority:** guardrail không đòi Smart *tốt hơn*, chỉ đòi *không tệ hơn quá δ*. `UpperCI95(ΔG_j) < δ_j` nghĩa là ngay cả cận trên của khoảng tin cậy về mức chênh lệch vẫn nằm trong biên cho phép.
- **Vì sao INCONCLUSIVE là kết luận hợp lệ:** thà nói "chưa đủ bằng chứng" còn hơn kết luận sai. Cũng vì vậy chạm margin vẫn là inconclusive.
- Guardrail theo `pair_group` dùng khoảng tin cậy **98.33%** (hiệu chỉnh Bonferroni cho 3 nhóm: 1 − 0.05/3).
- Kết luận chỉ áp dụng cho `data_source = synthetic` với các giả định trong sổ giả định của spec.

### 21.5 Sensitivity bắt buộc
Thử lại với: ngưỡng RTT 200/300/400 · loss 1/3/5 · jitter 10/30/50 · PoorFraction 0.1/0.2/0.3 · **`connection_mode = pre_connect`** · **`ice_transport_policy = all`**.

Với `pre_connect`, **chạy lại toàn bộ** KPI chính, guardrail và tải TURN (không chỉ đổi nhãn): allocation phải sống trong lúc đổ chuông, kể cả cuộc gọi không được bắt máy, và có TTL. Vì `pre_connect` thay đổi lượng allocation, thời gian giữ chỗ và thứ tự sự kiện nên có thể đổi cả thứ hạng policy. 

Với `ice_transport_policy = all` (v0.3.0), bật lại P2P và `relay_direct` rồi cũng **chạy lại toàn bộ**. *Vì sao:* mặc định `relay` là suy ra từ lời mentor và chưa xác minh (Q7). Nếu thật ra hệ thống cho phép P2P thì một phần cuộc gọi không đi qua TURN, và thứ hạng policy có thể đổi.

Thứ hạng đổi chiều ở bất kỳ kịch bản nào ⇒ kết luận ghi "phụ thuộc giả định".

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

## 22. Đi qua một cuộc gọi từ đầu tới cuối (v0.4)

**Kịch bản S02:** A ở **TP.HCM, Viettel, 4G**, dùng **điện thoại Android (app 3.12.0)**, gọi B ở **Hà Nội, VNPT, Wi-Fi**, dùng **iPhone (app 3.12.1)**. Chế độ `post_answer`, `ice_transport_policy = relay`, BE đặt ở **SGN** (`be_region = SGN`). Cuộc gọi thuộc thí nghiệm Geo vs Smart, nhánh Smart. **Mọi con số, mã thiết bị, phiên bản app và địa chỉ IP dưới đây đều là ví dụ minh họa** (bao gồm các số signaling RTT và bảng thời gian thiết lập, tự đặt cho khớp mốc thời gian, không phải số đo thật; IP lấy từ dải RFC 5737 dành cho tài liệu).

Từ v0.3.0 (và giữ nguyên ở v0.4.0), BE đứng giữa phần điều khiển: mọi lời mời, SDP, ICE candidate đi A → BE → B, và BE gọi Selector. Âm thanh thì đi thẳng A → TURN(A) → TURN(B) → B, không qua BE (§2A). Hàng "Selector cho phía B" dưới đây được đặt ở lúc **máy B đổ chuông** (`refined`), đúng như §0.2 của contract.

| Thời điểm (UTC) | Chuyện gì xảy ra | Bảng được ghi | Field đáng chú ý |
|---|---|---|---|
| 12:59:59.990 | Hệ thống gán nhánh | (nằm trong `call_session`) | `assignment_ts` ≤ `request_ts` đầu tiên (I15) |
| 13:00:00.000 | A bấm gọi | `call_session` | `call_id = C1`, `call_type = one_to_one`, `caller_device_id = c41d07e9…`, `connection_mode = post_answer`, `ice_transport_policy = relay`, `be_region = SGN`, `be_instance = be-sgn-03`, `experiment_id = exp-w4-geo-vs-smart`, `arm = smart`, `randomization_unit = run`, `experiment_cluster_id = sim_run_id`, `scenario_tag = S02_vn_cross_region` |
| 13:00:00.020 | Hỏi Selector cho phía A. Chưa biết B ở đâu | `selector_decision` (caller) | `device_id = c41d07e9…`, `phase = initial`, `info_level = caller_only`, `peer_ctx` toàn `unknown`, `policy_version = smart@0.3.1`, `feature_snapshot_id = feat-20261112-v1`; 4 TURN: SGN-VTL-01 (propensity 1.0), SGN-FPT-01, DAD-VTL-01, SG-SIN-01. `api_latency_ms = 18` do BE đo. BE gửi lời mời cho B **song song**, không chờ Selector (I14) |
| 13:00:00.100 | Điện thoại A xin chỗ trên TURN hạng 1 | `turn_allocation` (A) | `allocation_id = AL-A`, `device_id = c41d07e9…`, `turn_id = SGN-VTL-01`, `turn_url = turn:turn-pool-sgn.example:3478` (**hostname pool**), `turn_server_ip = 203.0.113.10`, `relayed_ip = 203.0.113.11`, `ice_generation = 0`, `alloc_ms = 38` (gồm vòng 401 + xử lý), `success = true`, `error_code = none` |
| 13:00:00.900 | Máy B nhận lời mời, đổ chuông | `call_outcome.ring_ts` (ghi khi kết thúc) | `ring_ts = 13:00:00.900` |
| 13:00:00.920 | BE hỏi Selector cho phía B. Giờ đã biết B ở Hà Nội | `selector_decision` (callee) | `device_id = 5ae2b8c0…`, `phase = refined`, `info_level = full`, hạng 1 là HAN-VNP-01. B chỉ có **một** thiết bị đổ chuông nên chỉ có một request `refined` này (`n_devices_rung = 1`). Độ trễ Selector nằm gọn trong lúc đổ chuông, người dùng không thấy |
| 13:00:04.000 | B bấm nghe | `call_outcome.answer_ts` | `answer_ts = 13:00:04.000` |
| 13:00:04.090 | Điện thoại B xin chỗ | `turn_allocation` (B) | `allocation_id = AL-B`, `device_id = 5ae2b8c0…`, `turn_id = HAN-VNP-01`, `turn_url = turn:turn-han-01.vnp.example:3478` (hostname riêng của một máy), `turn_server_ip = 198.51.100.20`, `relayed_ip = 198.51.100.21`, `alloc_ms = 41` |
| 13:00:04.150 | ICE bắt đầu kiểm tra | `ice_attempt` | `checks_start_ts = 04.150` (sau `answer_ts`, thỏa I5e) |
| 13:00:04.412 | ICE nối xong | `ice_attempt` | `ice_connected_ts = 04.412` → **neo cửa sổ**; `cst_technical = 262 ms`; `selected_local_candidate_type = relay`, `selected_remote_candidate_type = relay` → `path_type = relay_relay` (hai `actual_turn_id` khác nhau, bảng ở §6); `caller_device_id = c41d07e9…`, `callee_device_id = 5ae2b8c0…` (khớp `answered_device_id`, I20); `relay_turn_caller = null` (hostname là pool, nên **không** suy được máy từ hostname), `relay_turn_callee = HAN-VNP-01` (hostname trỏ đúng một máy); `relayed_ip_caller = 203.0.113.11`, `relayed_ip_callee = 198.51.100.21` (cả hai candidate là `relay`, nên được ghi IP); `caller_allocation_id = AL-A`, `callee_allocation_id = AL-B`; `rank_caller = 1`, `rank_callee = 1`; `attempt_seq = 1`, `ice_generation = 0` |
| 13:00:04.470 | DTLS xong | `ice_attempt` | `dtls_connected_ts = 04.470` |
| 13:00:04.540 | Gói media đầu tiên được nhận ở A | `call_stats_epoch` | `first_media_received_ts = 04.540` → `ttfm_post_answer = 540 ms` |
| Hết epoch 0 | Số đo chặng tóm tắt (6 dòng) | `path_leg_measurement` (`epoch_summary`, `inband`, `one_way`, `clock_sync_err_ms = 0.8`) | forward: A→SGN 9.1, SGN→HAN 13.8, HAN→B 2.3 (tổng 25.2 ms). reverse: B→HAN 2.5, HAN→SGN 14.2, SGN→A 10.9 (tổng 27.6 ms) |
| Hết epoch 0 | SDK hai bên gửi histogram | `call_stats_epoch` ×2 (audio) | `derivation = sdk` (cả hai bên tự tính histogram trên thiết bị), `window_s = 5`, `device_id` lần lượt `c41d07e9…` (caller) và `5ae2b8c0…` (callee). Xem bên dưới |
| 13:03:08 | Cúp máy | `call_outcome` | `answered`, `answered_device_id = 5ae2b8c0…`, `n_devices_rung = 1`, `converted_to_group = false`, `connected`, `end_reason = normal_hangup`, `dropped = false`, `duration_s = 184`, `pair_group = VN_VN`, `n_ice_attempts = 1`, `stats_status = kept_sampled`, `stats_sampling_prob = 0.1`, `stats_sampling_reason = hash_sample`, `caller_signaling_rtt_ms = 45`, `callee_signaling_rtt_ms = 38` (đo gần lúc gọi, minh họa) |

**Thời gian thiết lập sau khi bắt máy (`setup_breakdown_post_answer`, minh họa):** từ các mốc ở bảng trên, bốn đoạn là:

| Đoạn | Tính | Thời gian |
|---|---|---|
| `answer_ts → checks_start_ts` (signaling qua BE + gathering) | 04.150 − 04.000 | 150 ms |
| `checks_start_ts → ice_connected_ts` (ICE, = `cst_technical`) | 04.412 − 04.150 | 262 ms |
| `ice_connected_ts → dtls_connected_ts` (DTLS) | 04.470 − 04.412 | 58 ms |
| `dtls_connected_ts → first_media_received_ts` (media tới) | 04.540 − 04.470 | 70 ms |
| **Tổng** | = `ttfm_post_answer` | **540 ms** |

`signaling_overhead_est_ms` = (45 + 38) / 2 = **41.5 ms**, xấp xỉ một lượt B → BE → A. Phần này nằm trong đoạn đầu 150 ms; ~108 ms còn lại là xử lý ở BE, gathering candidate và xin chỗ TURN của B (các số này là minh họa, contract không tách nhỏ hơn). Chú ý: đây là chỗ duy nhất mà BE để lại dấu vết trong cuộc gọi.

**Nếu đổi `be_region`** (ví dụ đặt BE ở nơi khác), chỉ các số **thời gian thiết lập** này (hai `*_signaling_rtt_ms`, đoạn đầu của `setup_breakdown_post_answer`, và kéo theo `ttfm_post_answer`) thay đổi. **Phân loại PCR không đổi**, vì BE không nằm trên đường media: RTT/loss/jitter, histogram và `poor(C1)` ở dưới vẫn y nguyên.

**Kiểm tra chéo I9 (WARN; minh họa ở mức trung bình epoch cho dễ tính, còn contract kiểm trên từng cửa sổ 5 giây của `window_5s`, §14.3):** cả 3 chặng forward và 3 chặng reverse đều `one_way`, cùng cửa sổ, sai số đồng hồ 0.8 ≤ 2. Tổng forward + reverse = 25.2 + 27.6 = **52.8 ms**. `media_rtcp_rtt` (P50) của luồng A khoảng 51 ms. Lệch 1.8 ms, nằm trong ≤ 15 ms nên I9 thỏa. Lưu ý chiều reverse (27.6) lớn hơn chiều forward (25.2): đúng là mạng không đối xứng, nếu lấy RTT/2 = 25.5 làm "one-way" thì cả hai chiều đều bị đánh giá sai.

**Danh tính TURN thực của C1 (`actual_turn_id`, §16.6, minh họa).** `dim_turn_endpoint` (giả định) có: `203.0.113.10` (`listen`) và `203.0.113.11` (`relay`) thuộc `SGN-VTL-01`, hostname `turn-pool-sgn.example` trỏ tới **cả ba** máy SGN (pool); `198.51.100.20` / `198.51.100.21` thuộc `HAN-VNP-01`, hostname `turn-han-01.vnp.example` chỉ trỏ tới một máy.

| Bên | Tra theo thứ tự ưu tiên | Kết quả |
|---|---|---|
| Caller (A) | (1) `relayed_ip_caller = 203.0.113.11` có trong `dim_turn_endpoint` → `SGN-VTL-01`. **Dừng ở bước 1.** (Nếu thiếu IP thì hostname pool `turn-pool-sgn.example` trỏ tới 3 máy ⇒ mơ hồ ⇒ `ambiguous`, vào nhóm "pool") | `actual_turn_id_caller = SGN-VTL-01`, `turn_identity_method = ip` |
| Callee (B) | (1) `relayed_ip_callee = 198.51.100.21` → `HAN-VNP-01` | `actual_turn_id_callee = HAN-VNP-01`, `turn_identity_method = ip` |

Máy thực khớp máy Selector chọn (`SGN-VTL-01`, `HAN-VNP-01`) nên **không có `turn_identity_mismatch`** (I19). `path_type`: (relay, relay) và hai `actual_turn_id` khác nhau ⇒ `relay_relay`. Mọi KPI theo TURN của C1 góp vào **cả hai** máy (một lần mỗi máy), vì là `relay_relay`.

**Thông tin client của C1 (minh họa, trong `ctx`, §8):**

| | A (caller) | B (callee) |
|---|---|---|
| `device_id` | `c41d07e9…` | `5ae2b8c0…` |
| `platform` | `android` | `ios` |
| `app_version` | `3.12.0` | `3.12.1` |
| `os_version`, `sdk_version` | `14`, `2.7.1` | `17.5`, `2.7.1` |
| `device_model` → `device_class` (pipeline tính) | `SM-A546E` → `mid` | `iPhone14,5` → `high` |

Hai đầu khác nền tảng và khác bản app. Nếu sau này thấy PCR của các cuộc gọi có Android 3.12.0 tăng đột ngột, dashboard cắt theo `app_version` sẽ cho thấy chuyện đó (§20.6). Các field này vào `fact_call` (§16.4).

**Hai histogram của cuộc gọi.** Mỗi endpoint neo ở lúc **nó** ghi nhận ICE connected lần đầu (A ≈ 04.412 trên đồng hồ A; B có neo riêng trên đồng hồ B). Cuộc gọi kéo dài tới 13:03:08, tức 183.6 giây ≈ 36 cửa sổ 5 giây hoàn chỉnh. Cửa sổ chỉ tính khi nằm trọn trong [`answer_ts`, `end_ts`] (`converted_ts` không có). Key bucket là **key chuẩn** (§10.4).

| Metric | A (caller, 4G) | B (callee, Wi-Fi) |
|---|---|---|
| `media_rtcp_rtt_hist` (cửa sổ) | `{"lt100": 33, "100_200": 3}` (tổng 36; các key còn lại = 0) | `{"lt100": 34}` (tổng 34) |
| `rtt_windows_assessable` | 36 | 34 (2 cửa sổ chưa có RTCP RR với DLSR ≠ 0, nên điều kiện (c) không thỏa) |
| `loss_hist` | `{"lt1": 31, "1_3": 3, "3_5": 2, "ge5": 0}` (tổng 36) | `{"lt1": 36}` |
| `loss_windows_assessable` | 36 | 36 |
| `jitter_estimate_hist` | `{"lt10": 28, "10_30": 7, "30_50": 1, "ge50": 0}` (tổng 36) | `{"lt10": 35, "10_30": 1}` (tổng 36) |
| `jitter_windows_assessable` | 36 | 36 |

Kiểm tra I10: tổng mỗi histogram bằng đúng số cửa sổ assessable tương ứng. (Nếu một epoch không có cửa sổ nào đánh giá được thì histogram là `{}`, không phải `null`.)

**Cách tính PCR cho cuộc gọi này (§20.1):**
1. Cửa sổ tệ: RTT bucket ≥ 300 ms (`300_400`, `ge400`), loss bucket ≥ 3% (`3_5`, `ge5`), jitter bucket ≥ 30 ms (`30_50`, `ge50`).
2. Phía A: RTT tệ = 0 (không có bucket ≥ 300), mẫu số 36 → 0/36 = **0.000**. Loss tệ = 2 + 0 = 2, mẫu số 36 → 2/36 = **0.056**. Jitter tệ = 1 + 0 = 1 → 1/36 = **0.028**.
3. Phía B: RTT 0/34 = **0.000**; loss 0/36 = **0.000**; jitter 0/36 = **0.000**.
4. Điều kiện xác định: mọi mẫu số ≥ 4 → cả 6 PoorFraction đều xác định.
5. Không có PoorFraction nào ≥ 0.20 → `quality_poor = false`. Mọi metric của mọi bên xác định và < 0.20 → `quality_ok = true`, `quality_unknown = false`.
6. Ba nhánh của `poor`: `setup_fail(C1)` = answered ∧ ¬connected ∧ … = **false** (đã connected); `drop(C1)` = dropped = **false** (`end_reason = normal_hangup`); `quality_bad(C1)` = answered ∧ connected ∧ ¬dropped ∧ quality_poor = **false**. Vậy `poor(C1) = false`, và **`poor_category = none`**. `unclassifiable(C1)` = answered ∧ connected ∧ ¬dropped ∧ quality_unknown = **false**.
7. **`quality_assessment_status = assessed`**: cả 6 cặp (bên, metric) đều xác định (mọi mẫu số ≥ 4), nên không phải `partially_assessed` hay `unclassifiable`. (Nếu C1 chưa bao giờ nối thì sẽ là `not_applicable`.)
8. Cuộc gọi là `call_type = one_to_one` nên **ở trong cohort** (mẫu số) của `pcr_itt_low` và `pcr_itt_high`, đóng góp 0 vào tử số của cả hai.

**Một biến thể để thấy nhánh `setup_fail` (minh họa, không phải C1):** nếu B bấm nghe (`answered = true`) nhưng ICE không bao giờ nối được và B tự cúp sau 12 giây, `end_reason = normal_hangup`, `connected = false`. Theo I23 đây là trường hợp hợp lệ. Khi đó `setup_fail = true`, `poor_category = setup_fail`, `quality_assessment_status = not_applicable`, và cuộc gọi **được tính là poor** dù không có `ice_failed` nào (§23).

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
PNR chỉ tính trên cuộc gọi đã connected, nên một policy làm cho nhiều cuộc gọi khó nối bị loại ra khỏi mẫu số thì PNR của nó trông đẹp. PCR (ITT) tính trên mọi cuộc gọi đã gán nhánh, và đếm cả lỗi thiết lập (`setup_fail`), rớt, lẫn chất lượng tệ trong một con số. PNR còn có trong danh sách chẩn đoán nhưng không dùng để phán thắng thua.

**Sao dùng ITT mà không chỉ tính cuộc gọi thực sự đi qua TURN?**
Vì "đi qua TURN" là kết quả sau quyết định, có thể bị chính policy ảnh hưởng. Loại các cuộc gọi sau khi đã biết kết quả (Selector timeout, static fallback, và P2P nếu policy cho phép) tạo ra thiên lệch chọn lọc. ITT giữ nguyên cohort từ lúc gán nhánh, nên so sánh công bằng.

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

**Đi qua BE có làm cuộc gọi chậm không?**
Không làm **chất lượng tiếng** tệ đi: BE chỉ làm signaling, media đi A → TURN(A) → TURN(B) → B mà không qua BE, nên BE không cộng gì vào RTT, loss, jitter và không đổi `pcr_itt`. BE chỉ làm **thời gian thiết lập** dài thêm, vì mọi tin nhắn đi qua nó; với `post_answer` cần ít nhất một lượt B → BE → A sau khi bắt máy, ≈ (RTT(A↔BE) + RTT(B↔BE)) / 2 + thời gian BE xử lý. Ví dụ ước tính (không phải số đo): gọi trong nước với BE ở VN chỉ vài chục ms; gọi Nhật ↔ Đức với BE ở Hà Nội thì ≈ (93 + 189) / 2 ≈ 141 ms (§2A). Phần này được theo dõi bằng `*_signaling_rtt_ms` và `setup_breakdown_post_answer`. Selector cũng không làm chậm: BE gọi nó song song với việc gửi lời mời (I14), độ trễ nằm trong lúc đổ chuông.

**Vì sao mặc định chỉ dùng relay, không P2P?**
Vì mentor mô tả ICE đi qua "TURN top 1 của mỗi bên", nên contract suy ra `ice_transport_policy = relay`. Đây là **suy ra, chưa xác minh** (Q7). Chọn mặc định này vì nếu cuộc gọi nối thẳng thì không đi qua TURN, và việc chọn TURN không còn ảnh hưởng tới nó. Để giả định không bị "tin mù", có I18 (policy `relay` mà thấy P2P thì FAIL) và bài kiểm tra độ nhạy `ice_transport_policy = all` (§21.5), bật lại P2P và `relay_direct` rồi chạy lại toàn bộ. Tài liệu này **không** coi P2P là chuyện phổ biến theo mặc định.

**Nếu sau này media đi qua SFU thì sao?**
Khi đó mỗi bên có PeerConnection riêng tới media server, nên `media_rtcp_rtt`, loss, jitter chỉ phản ánh **nửa đường**, và định nghĩa PCR không còn đúng. Đó là thay đổi **MAJOR**, phải mở version contract mới, không vá bằng cách thêm field (§2A.5; `docs/research/05`, `/06`).

**Sao cuộc gọi đã bắt máy mà không nối được lại tính là poor?**
Vì người dùng đã **bấm nghe** rồi không nghe được gì: đó là trải nghiệm tệ nhất có thể, tệ hơn cả tiếng giật. Bản nháp trước chỉ tính poor khi `end_reason = ice_failed`, nên nếu người dùng chờ vài giây trong im lặng rồi tự cúp (`end_reason = normal_hangup`, `connected = false`) thì cuộc gọi trông như cuộc gọi bình thường và lọt khỏi tử số, làm PCR **đẹp giả**. Định nghĩa hiện hành (§20.1) dựa vào trải nghiệm: `setup_fail` = đã bắt máy ∧ chưa từng nối ∧ `end_reason ≠ app_crash`. I23 bảo đảm các nhãn `end_reason` đi đúng với tình huống này. Hai điểm cần nhớ: (1) cuộc gọi **không** được bắt máy (`not_answered`, `rejected`...) vẫn không poor, vì đó là chuyện của người dùng; (2) `app_crash` không bị tính là `setup_fail`, vì app sập không nói lên gì về TURN. Nó cũng là lý do guardrail đổi từ `ice_fail_rate` sang `setup_fail_rate`.

**Vì sao cần `app_version` / `platform`?**
Để không đổ lỗi nhầm cho TURN. Mỗi bản app/SDK có thể tính jitter, loss hay RTT khác nhau, và mỗi nền tảng (iOS, Android, web) báo getStats theo cách riêng. Một bản app lỗi tính sai jitter sẽ làm PCR của mọi TURN mà người dùng bản đó đi qua trông tệ (§2B.1). Có `platform`, `app_version`, `device_class` thì dashboard cắt được KPI theo từng lát và check `release_regression` cắm cờ khi metric đổi đột ngột ngay sau một bản phát hành. Các cắt này chỉ để **chẩn đoán**, không đổi luật kết luận (§20.6).

**Đã có hostname sao còn lưu IP của TURN? Có trái quy tắc không lưu IP không?**
Hostname không nói được **máy nào**: một hostname pool có thể trỏ tới nhiều máy (DNS round-robin, geo-DNS, anycast), nên Selector chọn `SGN-1` mà client vẫn có thể tới `SGN-3` (§2B.2). Chỉ IP mới xác định được máy (`actual_turn_id`, §16.6). Và **không trái quy tắc**: quy tắc "không lưu IP thô" nhắm vào **IP của người dùng** (candidate `host`/`srflx`/`prflx`, kể cả `relatedAddress`/`relatedPort`), là dữ liệu cá nhân. IP của **máy chủ TURN** là hạ tầng của công ty, không thuộc về ai trong số người dùng, nên được lưu (`turn_server_ip`, `relayed_ip`, `relayed_ip_*`, `dim_turn_endpoint.ip`). `relayed_ip_*` chỉ ghi khi candidate là `relay`, nên không thể vô tình ghi IP người dùng vào đó.

**Người nghe có 2 thiết bị thì tính thế nào?**
Vẫn **một** cuộc gọi, **một** dòng trong cohort. Mỗi thiết bị đang đổ chuông có request `refined` và `decision_id` riêng, và allocation riêng. Thiết bị **bắt máy** được ghi ở `call_outcome.answered_device_id`; chỉ decision, allocation và attempt của thiết bị đó được ghép lại với nhau (I20). Allocation của thiết bị không bắt máy có `release_reason = other_device_answered` và không bao giờ được ghép vào attempt. `n_devices_rung` cho biết có bao nhiêu thiết bị đã đổ chuông. Số đo chất lượng (histogram) là của thiết bị bắt máy. Kịch bản S21 kiểm tra trường hợp này.

**Cuộc gọi nhóm có bị tính vào PCR không?**
Không. Cohort của `pcr_itt` và §20.1 chỉ gồm `call_type = one_to_one` (I21), vì cuộc gọi nhóm qua SFU có số đo "nửa đường" (§2A.5) mà PCR không được định nghĩa cho. Cuộc gọi 1-1 chuyển thành nhóm giữa chừng vẫn nằm trong cohort (lúc tạo nó là 1-1) nhưng mọi cửa sổ sau `converted_ts` không được đánh giá. Số cuộc gọi bị loại được báo cáo theo nhánh. Ngoại lệ duy nhất là guardrail hạ tầng `turn_utilization_p95`, tính trên **toàn bộ** tải kể cả cuộc gọi nhóm. Trên simulator việc này không đổi kết quả vì mọi cuộc gọi mô phỏng đều là 1-1 (S22 kiểm tra riêng phần lọc).

**SDK không tự tính được histogram thì sao?**
Dùng `derivation = pipeline` (§2B.5): SDK gửi `call_stats_5s` (mỗi cửa sổ một dòng, đủ các cột ở §10.5) cho **100%** cuộc gọi của endpoint đó, pipeline tự dựng `call_stats_epoch` theo **đúng cùng quy tắc** cửa sổ/bucket. Không ring buffer, không lấy mẫu cho endpoint này (I22); cửa sổ thiếu chỉ do gửi thất bại và thể hiện ở `measurement_coverage`. Có test derivation-equivalence để chứng minh hai cách cho kết quả giống hệt. Cái giá là tốn băng thông hơn. Đây là câu hỏi mở Q10, nên contract hỗ trợ cả hai.

**Contract nhiều bảng như vậy có quá nặng cho 6 tuần không?**
Simulator sinh tất cả bảng từ cùng một mô hình nên thêm bảng không tốn nhiều công. Mỗi bảng ứng với đúng một hệ thống ngoài đời, nên lúc pilot chỉ cần nối từng nguồn vào đúng bảng của nó.

---

## 24. Bảng tra nhanh: yêu cầu đề bài → lấy từ đâu (v0.4)

| Yêu cầu | Bảng · field |
|---|---|
| TURN VN theo miền / ISP / TURN Server / Network / thời gian | `ctx.vn_region`, `ctx.isp`/`asn`, **`actual_turn_id`** (máy thật, §16.6; không dùng `turn_id` của Selector), `ctx.network_type`, `event_ts` |
| TURN quốc tế theo Country / Region / TURN Location | `ctx.country`, `dim_turn.country`/`city`; TURN gắn theo **`actual_turn_id`** |
| Phân tích theo nền tảng / phiên bản app / lớp máy (v0.4.0) | `ctx.platform`, `ctx.app_version`, `ctx.sdk_version`, `ctx.os_version`, `ctx.device_model` → `device_class` (có trong `fact_call`); check DQ `release_regression` (§16.5) |
| Cuộc gọi nhiều thiết bị, cuộc gọi nhóm (phạm vi KPI, v0.4.0) | `device_id` (decision/allocation/attempt/số đo chặng/stats), `call_outcome.answered_device_id`, `n_devices_rung`, `release_reason = other_device_answered`; `call_session.call_type`, `call_outcome.converted_to_group`, `converted_ts` (I20, I21) |
| Biết client thật sự tới máy TURN nào (v0.4.0) | `turn_allocation.turn_url`/`turn_server_ip`/`relayed_ip`, `ice_attempt.relayed_ip_*`, `dim_turn_endpoint` → `actual_turn_id`, `turn_identity_method`; chẩn đoán `turn_identity_mismatch_rate` (I19) |
| User ở nước có và không có TURN | `ctx.country` so với danh sách `dim_turn.country` |
| VN↔VN, VN↔Quốc tế, Quốc tế↔Quốc tế | `call_outcome.pair_group` |
| Allocation Success | `turn_allocation.success`, `error_code`; `feat_turn_alloc_latency.alloc_success_rate` |
| Độ trễ cấp chặng, P50/P95 | `path_leg_measurement.value_ms` + `measurement_kind` + `granularity = epoch_summary`; `feat_leg_stats.p50`/`p95` |
| Độ trễ allocation | `turn_allocation.alloc_ms`; `feat_turn_alloc_latency.alloc_ms_p50`/`p95` (không phải độ trễ chặng) |
| Failure Rate, Connection Success | `call_outcome.answered`, `connected`, `end_reason`; KPI `setup_fail_rate` (gồm `ice_fail_rate`, `setup_abandon_rate`), `invite_delivered_rate`, `answer_rate`; `fact_call.poor_category` |
| **Chất lượng cuộc gọi tổng thể (metric chính)** | **`pcr_itt_low`/`pcr_itt_high`** từ `call_session` (cohort) + `call_outcome` + `call_stats_epoch` |
| Stability, Health, Usage | `turn_health_1m` (theo `turn_id` của máy), `feat_turn_health.stability_cv_24h`, `health_snapshot` (§17.7) |
| TURN được xếp hạng so với TURN ICE thực dùng | `selector_decision.candidates` so với **`actual_turn_id`** (thiếu thì `ice_attempt.relay_turn_*`), `rank_*`, `*_allocation_id` |
| Kiểu đường (relay / P2P) | `ice_attempt.selected_*_candidate_type` → `path_type`; cấu hình cho phép: `call_session.ice_transport_policy` (I18) |
| Data Insights: nút thắt ở đâu, đổi TURN có giúp được không | `poor_bottleneck_share` (từ `path_leg_measurement[epoch_summary]`, chỉ chẩn đoán) |
| Geo Baseline so với Historical / Smart | `call_session.arm`, `selector_decision.policy_version`; luật kết luận §21.4 |
| Availability, API Latency, Error, Fallback, Freshness | `service_health_1m` |
| CST (thiết lập kỹ thuật) | `ice_attempt.ice_connected_ts − checks_start_ts` (KPI `cst_technical_p95`); chẩn đoán đoạn chậm: `setup_breakdown_post_answer` (+ `signaling_overhead_est_ms` cho phần BE) |
| TTFM | `call_stats_epoch.first_media_received_ts` − `call_outcome.answer_ts` (KPI `ttfm_post_answer_p95`); chẩn đoán đoạn chậm: `setup_breakdown_post_answer` |
| RTT, Packet Loss, Jitter | `call_stats_epoch.media_rtcp_rtt_hist`, `loss_hist`, `jitter_estimate_hist` (KPI-grade); `call_stats_5s` (chi tiết, lấy mẫu) |
| Drop Rate | `call_outcome.dropped` (⇔ `end_reason` drop, I24); KPI `drop_rate` |
| SDK không tính được histogram (v0.4.0) | `call_stats_epoch.derivation = pipeline`, `window_s`, `call_stats_5s` đầy đủ, `stats_sampling_reason = raw_full` (I22) |
| Decision Trace theo Call ID | Mọi bảng sự kiện, nối qua `call_id`; chi tiết từng cửa sổ ở `call_stats_5s` (nếu được lấy mẫu) |
| TURN Failure | `selector_decision.filtered_out`, `turn_health_1m`, `ice_attempt.trigger = fallback`; TURN lỗi xác định bằng **`actual_turn_id`** |
| Cold-start | `feat_*.segment_level`, `n_eff`, `selector_decision.fallback_reason` |
| Network Change | `ice_attempt.network_epoch`, `trigger = restart_network_change`, `ice_generation`; `call_stats_epoch.network_epoch` |
| Phân biệt dữ liệu thật và giả lập | `data_source` |
| Confidence | `selector_decision.confidence` |
| Thí nghiệm / gán nhánh | `call_session.experiment_id`, `arm`, `assignment_ts`, `randomization_unit` |
| Dữ liệu chi tiết có được lưu không | `call_outcome.stats_status`, `stats_sampling_prob`, `stats_sampling_reason` |
| Tái lập một lần chạy sim | `run_manifest` (qua `sim_run_id`) |
| Đánh giá đường chưa đi (sim) | `truth_leg_5m` (chỉ `eval/`), regret §21.6 |
| Chất lượng dữ liệu | `dq_results` (bất biến I1–I24, check `release_regression`) |

---

## 25. Câu hỏi mở mới ở v0.3.0 và v0.4.0 (contract §17; không chặn freeze, đều có mặc định)

Q1–Q5 giữ nguyên như contract §17 (Q4, Q5 đã nhắc ở §10.2 và §23). Q6–Q8 mới ở v0.3.0, Q9–Q12 mới ở v0.4.0 (bảng thứ hai bên dưới).

| # | Câu hỏi | Ai trả lời | Mặc định | Vì sao hỏi |
|---|---|---|---|---|
| Q6 | Có bao nhiêu BE, đặt ở đâu, gán BE cho cuộc gọi thế nào | Mentor | Một cụm BE; vị trí là tham số, mặc định `SGN`. Chỉ ảnh hưởng thời gian thiết lập | Quyết định `be_region` và độ lớn của lượt signaling (§2A). Không đổi PCR nên không chặn |
| Q7 | ICE chỉ dùng relay hay cho phép P2P | Mentor / đội WebRTC | `relay` (suy ra từ mô tả của mentor); `all` là sensitivity | Quyết định `ice_transport_policy` mặc định, I18 và có cần chạy lại sensitivity `all` hay không |
| Q8 | SDK có đo RTT kênh signaling không | Mentor | Field nullable, không chặn | Quyết định có `caller_signaling_rtt_ms`, `callee_signaling_rtt_ms` và `signaling_overhead_est_ms` hay không |

**Bốn câu mới ở v0.4.0** (mặc định đều làm contract chạy được ngay, nên không chặn freeze):

| # | Câu hỏi | Ai trả lời | Mặc định | Vì sao hỏi |
|---|---|---|---|---|
| Q9 | TURN được cấp cho client bằng hostname riêng từng máy, hostname chung của pool, hay IP? | Đội hạ tầng | Hostname riêng; xác định máy bằng IP khi có (§7.4) | Quyết định `relay_turn_*` có suy ra được từ hostname không, và mức độ cần `dim_turn_endpoint`/IP (§2B.2, §16.6). Hostname pool thì chỉ IP mới nói được máy |
| Q10 | SDK tự tính được `call_stats_epoch` hay chỉ gửi được getStats thô? | Đội mobile/web | Hỗ trợ cả hai (`derivation`) | Quyết định mỗi nền tảng dùng `sdk` hay `pipeline`, và băng thông phải gửi `call_stats_5s` 100% (§2B.5) |
| Q11 | Người nghe có nhiều thiết bị cùng đổ chuông không? | Mentor | Có thể; contract đã hỗ trợ | Quyết định `device_id`/`n_devices_rung` có thường khác 1 không; nếu không bao giờ thì I20 và S21 ít gặp (§2B.3) |
| Q12 | Có cuộc gọi nhóm không, đánh dấu thế nào, cuộc gọi 1-1 có chuyển thành nhóm được không? | Mentor | `call_type`; chỉ cuộc gọi 1-1 vào KPI | Quyết định có cần `converted_ts` và có cần bàn lại SFU (thay đổi MAJOR) hay không (§2B.4) |
