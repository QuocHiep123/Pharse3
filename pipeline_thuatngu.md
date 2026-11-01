# Pipeline và thuật ngữ: OJT AI20K (bản dễ hiểu)

> **Lưu ý:** sơ đồ dưới đây là mô hình dựng từ checklist OJT và những gì đã học, chưa phải kiến trúc thật của repo. Khi đọc code, việc của bạn là **đối chiếu**: chỗ nào khớp, chỗ nào khác.

## 1. Pipeline trong một hình

```
 Người dùng A  ⇄ ⇄ ⇄ (RTP/SRTP) ⇄ ⇄ ⇄  Người dùng B / SFU      ① MEDIA plane
      │ SDP, ICE candidate                                       (tiếng, hình)
      ▼
 Signaling server (Java/Spring)                                  ② CONTROL plane
      │ sinh ra: sự kiện + log + metric (getStats: RTT, jitter, loss)  (điều phối cuộc gọi)
      ▼
 Kafka  [call-events] [call-metrics]                             ③ TELEMETRY plane
      ├──► ClickHouse   metric chuỗi thời gian (nhanh khi tổng hợp)    (đo đạc, chẩn đoán)
      ├──► OpenSearch   log, tìm kiếm văn bản
      └──► PostgreSQL   dữ liệu nghiệp vụ (rooms, calls)
                │
                ▼
 Phân tích bất thường (Đoàn) ──► Agent điều phối (Hiệp, LangGraph)
                                   ├─ Metric Agent  → đọc ClickHouse
                                   └─ Log Agent     → đọc OpenSearch
                                         ▼
                      Báo cáo: FACT [log_line_id] + INFERENCE có luận cứ
```

**Một câu:** cuộc gọi diễn ra → hệ thống ghi lại dấu vết → đẩy vào ống Kafka → cất vào kho phù hợp → AI đọc dấu vết để giải thích vì sao cuộc gọi tệ.

**Ba plane là ba việc khác nhau:** media plane chở tiếng/hình, control plane điều phối ai nối với ai, telemetry plane chỉ quan sát. Plane cuối **không được làm chậm** hai plane đầu.

## 2. Thuật ngữ, mỗi cái một dòng

### Cuộc gọi (WebRTC)

- **Signaling:** kênh trao đổi "tôi là ai, tôi nói được gì". Nằm ngoài WebRTC, bạn tự chọn WebSocket hay HTTP.
- **SDP (offer/answer):** bản khai "tôi hỗ trợ codec nào, khoá nào, địa chỉ nào". Một bên gửi offer, bên kia đáp answer.
- **ICE candidate:** một địa chỉ mạng có thể dùng để nối tới tôi. ICE thử các cặp địa chỉ rồi chọn cặp tốt nhất.
- **STUN:** hỏi "bên ngoài NAT nhìn tôi là địa chỉ nào?".
- **TURN:** máy chủ **chuyển tiếp** media khi hai bên không nối trực tiếp được.
- **NAT:** thiết bị đổi địa chỉ riêng thành địa chỉ công cộng, khiến máy ngoài không gọi vào thẳng được.
- **P2P / SFU / MCU:** P2P gửi thẳng. SFU nhận một luồng rồi **chuyển** cho mọi người. MCU **trộn** thành một luồng.
- **RTP / RTCP:** RTP chở media, RTCP chở báo cáo chất lượng về luồng đó.
- **SRTP / DTLS:** mã hoá media. DTLS bắt tay trao khoá, SRTP dùng khoá đó mã hoá gói.

### Chất lượng

- **QoS vs QoE:** QoS là số đo của mạng (RTT, jitter, loss). QoE là cảm nhận của người dùng. QoS xấu thường kéo QoE xấu nhưng không phải lúc nào cũng vậy.
- **RTT:** thời gian khứ hồi.
- **Jitter:** độ dao động của độ trễ.
- **Packet loss:** tỉ lệ gói mất.
- **MOS (1 đến 5):** điểm chất lượng thoại, tính từ E-model (R → MOS).
- **Jitter buffer:** bộ đệm làm mượt jitter, đổi thêm độ trễ lấy độ mượt.
- **Concealment / freeze:** hệ thống che chỗ mất tiếng, hoặc hình bị đứng.
- **GCC / REMB:** thuật toán ước lượng băng thông để tự giảm hay tăng bitrate.

### Hạ tầng dữ liệu

- **Kafka:** ống truyền sự kiện.
  - **Topic** chia thành **partition**.
  - Cùng **key** thì vào cùng partition nên giữ được thứ tự.
  - **Consumer group** chia việc đọc.
  - **Lag** là độ chậm so với dữ liệu mới nhất.
- **ClickHouse:** kho lưu theo cột, rất nhanh khi tính trung bình/tổng trên hàng triệu dòng metric.
- **OpenSearch:** tìm kiếm văn bản bằng chỉ mục ngược. Nhớ `text` (bị tách từ) khác `keyword` (khớp nguyên văn).
- **PostgreSQL:** CSDL quan hệ, đảm bảo ACID, dùng cho dữ liệu nghiệp vụ.
- **Redis:** bộ nhớ đệm trong RAM, dùng cho trạng thái tạm.
- **Java/Spring:** Spring dựng sẵn nhiều thứ.
  - **DI** là "đưa đồ vào cho tôi", **Bean** là đối tượng Spring quản lý.
  - Code thường tách Controller → Service → Repository.
- **REST / gRPC:** hai cách gọi API. REST dùng HTTP + JSON dễ đọc. gRPC dùng HTTP/2 + Protobuf nhị phân, nhỏ và nhanh.

### Docker

- **Image:** gói đóng sẵn, chỉ đọc (ví dụ `postgres:16`). **Container:** thể hiện đang chạy của image.
- **Volume:** chỗ giữ dữ liệu bên ngoài container. Dữ liệu ghi bên trong container sẽ mất khi container bị xoá.
- **Port publish `-p máy_bạn:container`:** mở cổng từ máy bạn vào container.
- **Compose:** một file mô tả cả nhóm container. Tên service là tên DNS trong mạng nội bộ (`kafka:29092`).

### AIOps / Agent

- **FACT:** trích trực tiếp từ log/metric, có timestamp hay mã dòng chứng minh.
- **INFERENCE:** kết luận suy ra từ FACT, **bắt buộc** có luận cứ. Luôn nêu giả thuyết cạnh tranh và một quan sát có thể phân biệt chúng.
- **Grounded generation:** mọi khẳng định kèm `[log_line_id]` hoặc `[metric_timestamp]`.
- **LangGraph:** thư viện dựng agent dạng đồ thị gồm State, Node, Edge, Conditional Edge.
- **Supervisor pattern:** một agent điều phối chia việc cho các sub-agent (Metric Agent, Log Agent).
- **Anomaly detection:** tìm điểm lệch bất thường trong chuỗi thời gian (Z-score trượt, EWMA).

## 3. Cách đọc code hiệu quả với Claude CLI

Mục tiêu là **hiểu và đọc**, không phải gõ lại, nên dùng CLI như người dẫn đường:

1. **Bắt đầu từ cụm chạy được.** Chạy `docker compose up -d` trước. Hệ thống đang chạy giúp so sánh code với hành vi thật.
2. **Hỏi bản đồ trước, chi tiết sau.** Prompt gợi ý: *"Chỉ đọc, đừng sửa gì. Liệt kê các module chính và vai trò mỗi cái."*
3. **Bám theo một sự kiện từ đầu đến cuối.** Ví dụ: *"Theo dõi một message vào topic `call-events` đi qua những class nào, từ lúc sinh ra đến lúc nằm trong kho."*
4. **Mang theo 5 câu hỏi khi đọc bất kỳ hệ thống nào:**
   - Dữ liệu đi vào từ đâu? Đi ra đâu?
   - Trạng thái được lưu ở đâu?
   - Cái gì chạy bất đồng bộ, cái gì đồng bộ?
   - Khi một bước hỏng thì chuyện gì xảy ra (retry, mất dữ liệu, trùng)?
   - Thứ tự và tính idempotent được đảm bảo thế nào?
5. **Tự dự đoán trước khi hỏi CLI.** Trước khi mở một file, đoán nó làm gì rồi mới kiểm tra.
6. **Đừng tin CLI mù quáng.** Yêu cầu nó chỉ ra **file và dòng** làm bằng chứng. Đây chính là kỷ luật FACT vs INFERENCE.

## 4. Tự kiểm tra

1. ★ Bạn thấy một service ghi vào Kafka rồi **không** thấy gì ghi vào ClickHouse. Nêu **hai giả thuyết** khác nhau giải thích điều này. Mỗi giả thuyết cần quan sát gì để xác nhận?
2. ★ Nếu Kafka chết, cuộc gọi đang diễn ra có bị rớt không? Giải thích bằng khái niệm ba plane.
3. Vì sao metric đưa vào ClickHouse còn log đưa vào OpenSearch, mà không dồn hết vào Postgres?
4. Vì sao `kafka-init` dùng `kafka:29092` còn app chạy trên máy bạn dùng `localhost:9092`?