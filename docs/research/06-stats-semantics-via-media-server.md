# 06 - Ngữ nghĩa getStats khi media đi qua media server (SFU)
> **Áp dụng cho dự án (cập nhật 2026-11-04):** BE chỉ là backend signaling, media **không** đi qua BE ⇒ kiến trúc của công ty là **Pattern 1** (A → TURN(A) → TURN(B) → B, một PeerConnection). Phần Pattern 2 (SFU) và Pattern 3 (backbone) giữ làm tham khảo nếu kiến trúc thay đổi. Xem contract v0.3.0 §0.2. Cột áp dụng trong bảng §1 là **P2P relay-relay (1 PC A↔B)**.

Ngày: 2026-11-04. Phạm vi: đường media có thể là A → TURN(A) → BE → TURN(B) → B (BE có thể là SFU), thay vì 1 PeerConnection A↔B.

Quy ước tag: **[V]** = đã đọc nguồn trong phiên này (kèm URL ở mục Trích dẫn, ví dụ [V-R7667]); **[K]** = kiến thức chưa kiểm chứng trong phiên này (cần xác nhận). Lưu ý: công cụ fetch trả về bản tóm tắt, một số trang bị cắt (RFC 3550, 8445, 8656, webrtc-stats chỉ đọc một phần); các mục liên quan được ghi rõ.

---

## 1. Topology RTP có middlebox (RFC 7667)

| Khái niệm | Nội dung | Tag |
|---|---|---|
| RTP Translator (3.5, 3.2.1) | Giữ nguyên SSRC qua translator; khi dịch media phải *viết lại* RTCP RR của endpoint B trước khi chuyển cho A (để A thấy loss/seq nhất quán với stream thực nhận); seq number được dịch tương ứng. Relay kiểu "multicast over unicast" chuyển tiếp RTP/RTCP tới mọi endpoint. | [V-R7667] |
| Mixer / RTCP-terminating MCU (3.6, 3.9) | Mỗi endpoint chạy một phiên RTP point-to-point với MCU; MCU tự sinh SR/RR ("must not forward RTCP unaltered between the two domains"); SSRC đầu ra thường khác (SSRC của mixer, nguồn nằm trong CSRC; nhiều MCU để CC=0). | [V-R7667] |
| Selective Forwarding Middlebox (3.7) | Mỗi endpoint có RTP session độc lập; SFM "chiếu" SSRC nguồn vào từng session; **seq number được đánh lại liên tục theo gói thực sự gửi trong từng session**; mỗi endpoint có thể có view SSRC khác nhau; xử lý FIR, gộp TMMBR về nguồn. | [V-R7667] |
| NACK/RTX/FEC trong RFC 7667 | RFC 7667 mục 3.5-3.9 (phần đọc được) **không** mô tả chi tiết NACK/RTX/FEC per leg. | [V-R7667] (không có nội dung) |
| NACK/RTX/FEC thực tế ở SFU | Mediasoup: RTX nhận (producer) và RTX gửi (consumer) xử lý độc lập; consumer có SSRC/RTX SSRC riêng sinh mới; dùng RTT giới hạn tần suất gửi lại; có code đánh lại seq/SSRC (PipeConsumer). Thông thường SFU là "hop" riêng cho NACK: nhận NACK từ downstream và phục vụ từ buffer của chính nó, và tự NACK upstream. | mediasoup: [V-MS-DISC][V-MS-RTP]; khái quát "mọi SFU" = [K] |
| SFU có kết thúc RTCP per leg không | Theo mô hình SFM (session độc lập) và mediasoup (SSRC consumer mới, RTCP per transport) thì có: SR/RR là per leg. LiveKit dùng RR từ client downstream để lấy loss/RTT/jitter downstream (xem 4). | [V-R7667][V-MS-RTP][V-LK-PR] |

Kết luận: với SFU điển hình, A và B mỗi bên có PeerConnection riêng tới BE; RTCP, SSRC, seq number là **per leg**, không có gì đi xuyên suốt A↔B ngoài payload (E2E encryption nếu dùng insertable streams là [K]).

---

## 2. Bảng: field → đo đoạn nào

Ký hiệu đoạn (khi P2P relay-relay: A → TURN(A) → TURN(B) → B, một PC; khi via SFU: PC_A = A↔BE, PC_B = B↔BE).

| Field (getStats) | P2P relay-relay (1 PC A↔B) | Via SFU (A có PC_A, B có PC_B) | Tag |
|---|---|---|---|
| `remote-inbound-rtp.roundTripTime` (media_rtcp_rtt) | RTT A↔B xuyên suốt: A gửi SR (NTP), B trả RR, RTT = A − LSR − DLSR (RFC 3550 6.4.1); đi qua cả 2 TURN. Tính xấp xỉ, giả định đối xứng. | Chỉ RTT **A↔BE** (hoặc đúng hơn: A tới điểm sinh RR là BE). Nếu SFU kết thúc RTCP thì RR do SFU sinh, DLSR của SFU. **Không** bao gồm BE↔B. | Công thức: [V-R3550], [V-W3C]; "chỉ tới BE" suy ra từ RTCP-termination [V-R7667]; chi tiết SFU forward RR hay không = [K] |
| `candidate-pair.currentRoundTripTime` (ice_stun_rtt) | RTT STUN giữa A và peer ICE (ở đây: A↔TURN(A)↔…↔B nếu pair relay-relay: STUN check đi end-to-end qua relay, tức xấp xỉ RTT A↔B qua cả 2 TURN). Gồm cả consent-check (RFC 7675). | RTT STUN từ A tới **ICE agent của BE** (qua TURN(A) nếu pair dùng relay candidate của A): xấp xỉ A→TURN(A)→BE→ về. Nếu BE là ICE-lite thì BE chỉ trả lời STUN (không tự sinh check) nhưng A vẫn đo được RTT check của A. **Không bao gồm** TURN(B), B. | W3C định nghĩa: [V-W3C]; ICE-lite chỉ trả lời check: [V-R8445]; suy luận đoạn đường: [K] |
| `inbound-rtp.packetsLost` | Mất gói của stream A→B qua toàn đường (tính theo seq number gốc, RFC 3550). | Chỉ mất gói trên stream mà **SFU gửi cho B** tính theo seq number SFU đã đánh lại (RFC 7667 3.7 seq đánh lại theo gói thực gửi). Mất upstream (A→BE) **không hiện** nếu SFU đánh lại seq liên tục hoặc nếu gói bị mất được che bằng NACK/RTX từ SFU. Xem biến thể bên dưới. | [V-R7667] (seq rewrite); biến thể = [K] |
| `inbound-rtp.jitter` | Interarrival jitter (RFC 3550 A.8) của stream A→B, gồm biến động toàn đường. | Jitter của chuỗi gói **SFU→B** (pacing/forward của SFU tự nó thêm biến động; biến động upstream chỉ đi qua trong chừng mực SFU forward ngay, không buffer). Không là tổng jitter 2 đoạn. | Định nghĩa: [V-R3550]; hành vi theo SFU = [K] |
| `remote-inbound-rtp.fractionLost/packetsLost` (phía A) | Loss A→B do B báo. | Loss **A→BE** do BE báo (hoặc SFU viết lại RR). | [K] (dựa trên RTCP termination [V-R7667]) |
| `remote-inbound-rtp.jitter` | Jitter B thấy. | Jitter BE thấy. | [K] |
| `inbound-rtp.jitterBufferDelay / EmittedCount` | Độ trễ trong jitter buffer của B (cục bộ); không đổi bản chất. | Như cũ: chỉ phần buffer của B (cục bộ). SFU thường không có jitter buffer nên không có phần BE. | Định nghĩa: [V-W3C]; "SFU không buffer" = [K] |
| `inbound-rtp.totalProcessingDelay` | Từ gói RTP đầu của frame tới khi decode xong (cục bộ). | Như cũ (cục bộ). | [V-W3C] |
| `inbound-rtp.estimatedPlayoutTimestamp` | Thời điểm NTP phát ra ước từ ánh xạ RTP↔NTP của SR. | NTP theo SR của **SFU** (nếu SFU tự sinh SR với clock của nó), nên không phải thời điểm capture ở A. | Định nghĩa: [V-W3C]; "theo SR của SFU" = [K] |
| `remote-outbound-rtp` (SR phía gửi, `remoteTimestamp`) | SR của A tới B. | SR của **BE** tới B (BE là sender trong PC_B). | Sự có mặt trong appendix: [V-W3C]; ngữ nghĩa SFU = [K] |
| `outbound-rtp` / `media-source` ở A | Gửi vào 1 PC. | Gửi vào PC_A, BE có thể nhân bản đi nhiều người nhận. | [K] |

### Biến thể hành vi SFU ảnh hưởng packetsLost/jitter (B)
1. **SFU đánh lại seq liên tục + NACK/RTX riêng mỗi leg** (SFM chuẩn 7667 mục 3.7, mediasoup): B chỉ thấy loss của SFU→B; loss upstream A→BE bị "che" (hoặc xuất hiện như khoảng trống mà SFU không báo). [V-R7667][V-MS-DISC]; mức độ che cụ thể = [K]
2. **SFU forward seq gốc (pass-through, ít gặp)**: loss upstream xuất hiện lẫn trong loss của B. [K]
3. **SFU tự sinh gói/padding, drop layer simulcast cố ý**: B có thể thấy "mất" hoặc nhảy seq do chủ ý, không phải mất mạng. [K]

Hệ quả cho KPI: `packetsLost` của B ≠ chất lượng đường A→B, mà là chất lượng một nửa đường.

---

## 3. Delay đầu-cuối qua SFU

| Cơ chế | Nội dung | Tag |
|---|---|---|
| RTCP SR NTP timestamp | Ánh xạ RTP timestamp ↔ NTP của **bên phát SR**. Với SFU tự sinh SR (RTCP termination), NTP là đồng hồ SFU, không phải đồng hồ A. Vì vậy chỉ cho biết đồng bộ A/V, không cho delay xuyên A→B. | RTCP-termination [V-R7667]; hệ quả = suy luận [K] |
| abs-capture-time (webrtc.org) | Header extension 1 byte-header, dạng ngắn 8 byte (timestamp UQ32.32) hoặc dài 16 byte (thêm estimated capture clock offset, signed). Quan hệ: Capture NTP Clock = Sender NTP Clock + Capture Clock Offset. Mixer có thể chỉnh timestamp hoặc viết lại hoàn toàn bằng NTP clock của nó (khi đó coi như nó là capture system); phải gửi lại với gói đầu sau khi đổi capture system. Tài liệu **không nói** mixer nên đặt offset thế nào khi viết lại, và không định nghĩa công thức delay; muốn tính delay cần đồng hồ receiver đồng bộ NTP với đồng hồ capture. Trạng thái: experimental. | [V-ACT] |
| Expose ra JS | `captureTimestamp`/`senderCaptureTimeOffset` nằm ở `RTCRtpSynchronizationSource/ContributingSource` (qua `getSynchronizationSources()`), chỉ có khi extension được đàm phán; theo comment trên GitHub Chrome cài từ M95, có thể chỉ cho audio; Firefox 91 có field này. Chưa thấy trên `inbound-rtp` trong spec phần đã đọc. | [V-WEBRTC-EXT] một phần; "chỉ audio" là báo cáo gián tiếp, cần kiểm lại bằng chrome thực |
| `estimatedPlayoutTimestamp` | Định nghĩa trong W3C (NTP của mẫu cuối cùng phát được, ngoại suy); hiệu audio−video cho A/V sync. | [V-W3C]; Chrome có cài? [K] |
| `jitterBufferDelay`, `totalProcessingDelay` | Có trong W3C, đo trễ cục bộ phía nhận (buffer, decode). | [V-W3C]; Chrome có cài (thực tế có) = [K] |
| One-way / E2E latency A→B | Từ stats thuần client: **không đo trực tiếp được**. Cần (a) abs-capture-time + SFU giữ/cập nhật offset đúng + đồng hồ A,B đồng bộ chặt (NTP: cỡ ms-chục ms; PTP: sub-µs trong LAN) hoặc (b) cộng các đoạn đo riêng (RTT/2 mỗi đoạn, giả định đối xứng). | Phân tích dựa [V-ACT]; độ chính xác NTP/PTP = [K] |

---

## 4. Telemetry phía server

### SFU (per participant)
| SFU | Có thể báo | Tag |
|---|---|---|
| LiveKit | Dùng receiver report của client để lấy loss/RTT/jitter downstream (PR #1781: góc nhìn chỉ SFU không biết loss phía client downstream, không có RTT/jitter); có hook `SetRTT`, `OnMediaLossFeedback` | [V-LK-PR] |
| Jitsi Videobridge | Có `rtt_aggregate`: RTT đo qua RTCP, trung bình trên các endpoint local có số đo hợp lệ (mức bridge, không per endpoint trong tài liệu); stats qua `/colibri/stats`, `/metrics` (Prometheus), MUC; tài liệu liệt kê (không đầy đủ) không có metric loss/jitter chung | [V-JVB] |
| mediasoup | Stats per Producer/Consumer qua API (RTT cho consumer đến từ RTCP, không cần XR) | [V-MS-DISC]; chi tiết API `getStats` = [K] |
| Janus, Pion | Chưa đọc tài liệu trong phiên này; Pion có interceptor stats, Janus có event handler/RTCP stats | [K] |

Chung: loss mỗi chiều (uplink = SFU nhận từ client; downlink = RR từ client), RTT từ SR/RR, jitter từ RR/receiver tự tính. [K]

### TURN (coturn)
| Mục | Nội dung | Tag |
|---|---|---|
| Prometheus | `--prometheus`, cổng mặc định 9641: `turn_total_allocations{type,protocol,family}`, các counter 401 và ratelimit. Tài liệu trang đọc **không** có metric RTT, bytes/packets per allocation. | [V-COTURN-PROM] |
| Per-allocation bytes/packets, lifetime | coturn có session/traffic stat trong log (`usage` log: rb, rp, sb, sp) và DB (redis `status`), không trong Prometheus doc đọc. | [K] |
| Allocation lifetime | Mặc định 600 s; Refresh gia hạn; gửi data không gia hạn; Refresh lifetime=0 xóa. | [V-R8656] |
| Đo RTT tới client/peer | RFC 8656 phần đọc không có cơ chế đo RTT; TURN server relay payload không hiểu RTP. coturn không công bố RTT. Có thể RTT tới client suy từ TCP (nếu TURN/TCP) hoặc probe ngoài. | RFC [V-R8656]; coturn [V-COTURN-PROM] (không thấy RTT) |

### ICE-lite trên SFU
ICE-lite: chỉ dùng host candidate, **không sinh connectivity check**, chỉ trả lời (STUN server), luôn controlled; full agent (client) làm controlling. Hệ quả: RTT STUN do **client** đo được; BE không tự đo STUN RTT tới client (chỉ có thể suy từ thời điểm nhận check). [V-R8445]

---

## 5. Đo từng đoạn

| Đoạn | Ai đo | Cách | Loại | Ghi chú | Tag |
|---|---|---|---|---|---|
| A → TURN(A) | Client A | STUN Binding/Allocate request tới TURN(A) (RTT, không phải one-way); hoặc ICE check pair host↔relay | RTT | Đây là phần "client↔TURN"; không có one-way nếu không đồng bộ clock client | [K] |
| TURN(A) → BE | Hạ tầng công ty | Probe server-to-server giữa TURN(A) và BE (ICMP/UDP echo, TWAMP) | RTT hoặc one-way | One-way cần đồng hồ đồng bộ | [K] |
| BE → TURN(B) | Hạ tầng công ty | Như trên | RTT/one-way | | [K] |
| TURN(B) → B | Client B | STUN tới TURN(B) | RTT | | [K] |
| Khi xuyên TURN toàn đoạn A↔BE | Client A | `candidate-pair.currentRoundTripTime` (pair relay→BE) và `remote-inbound-rtp.roundTripTime` | RTT | Gộp hai đoạn A→TURN(A) và TURN(A)→BE; muốn tách phải trừ số đo từng đoạn | suy luận [K] |

Đồng bộ đồng hồ: one-way cần NTP (thường ms đến chục ms qua Internet, đủ cho tham chiếu thô) hoặc PTP (sub-µs/µs, LAN/DC có hỗ trợ phần cứng); OWAMP/TWAMP (RFC 4656/5357) đo one-way/two-way active, TWAMP-light đo RTT không cần đồng bộ. [K] (chưa đọc RFC trong phiên này).

---

## 6. Quy tắc ghép KPI từ hai nửa đường (A↔BE, B↔BE)

| KPI | Quy tắc | Điều kiện/giới hạn | Tag |
|---|---|---|---|
| RTT | RTT_e2e ≈ RTT(A↔BE) + RTT(B↔BE) + xử lý trong BE (forwarding/queue của SFU) | Cộng được; hai số đo phải cùng thời điểm; RTT RTCP chỉ xấp xỉ vì giả định đối xứng (RFC 3550 6.4.1 nêu điều này) | cộng: toán học; hạn chế đối xứng [V-R3550] |
| Delay một chiều A→B | ≈ d(A→BE) + d(BE→B) + trễ nội bộ BE + jitter buffer B | Cần one-way, đồng hồ đồng bộ, hoặc xấp xỉ RTT/2 | [K] |
| Loss | l_e2e ≈ 1 − (1−l_AB)·(1−l_BB') nếu độc lập | Giả định độc lập; nếu SFU NACK/RTX thì loss "thấy được" thấp hơn loss mạng thô, cần phân biệt loss trước/sau recovery; loss tương quan (cùng hạ tầng) làm công thức sai | [K] |
| Jitter | **Không cộng được**. Jitter là deviation làm mịn (hàm 1/16, RFC 3550) trên mỗi leg, không có tính cộng đơn giản; xấp xỉ thô: phương sai cộng nếu độc lập (σ² = σ₁²+σ₂²) nhưng jitter RFC là kỳ vọng |D| làm mịn nên chỉ tham khảo | định nghĩa [V-R3550]; xấp xỉ = [K] |
| Cái người nghe thật sự nghe | Ưu tiên số đo tại **B (receiver)**: `inbound-rtp` jitterBufferDelay, concealed samples, `packetsLost` chỉ SFU→B + loss tại A→BE từ nguồn khác; hiểu rằng B chỉ thấy nửa SFU→B | [K] |

---

## 7. Nguồn KPI-grade đề xuất

1. **RTT mỗi leg**: `candidate-pair.currentRoundTripTime` (STUN, mẫu dày, mọi pair) + `remote-inbound-rtp.roundTripTime` (RTCP, đến BE). Ghi rõ mỗi số là đoạn nào. Giữ ice_stun_rtt cho "client↔BE qua relay", media_rtcp_rtt cho "client↔điểm kết thúc RTCP".
2. **Loss/jitter**: lấy từ cả hai phía (RR về client, server-side của SFU cho uplink), ghi nhãn `leg ∈ {A_up, B_down}`; không gán cho "đường A→B".
3. **Từng đoạn TURN↔BE**: server-to-server probe (TWAMP-light/UDP echo) định kỳ; coi là nguồn độc lập, không phụ thuộc client.
4. **E2E (nếu cần)**: abs-capture-time nếu SFU hỗ trợ và clock đồng bộ; nếu không, dùng tổng RTT hai nửa + bù xử lý BE.
5. Thêm trường `topology` ∈ {p2p_relay, sfu} và `leg` vào data contract; đổi tên ngữ nghĩa `media_rtcp_rtt` thành "RTT tới điểm kết thúc RTCP".

---

## 8. Câu hỏi mở cho công ty

1. BE có thật là SFU hay MCU (mixing)? Sản phẩm nào (mediasoup/Janus/JVB/LiveKit/Pion/tự viết)?
2. BE kết thúc RTCP (tự sinh SR/RR) hay forward/viết lại RR? Có đổi SSRC và seq?
3. BE làm NACK/RTX/FEC per leg hay chỉ forward? Có jitter buffer không?
4. BE là ICE-lite hay full ICE? Client tới BE đi qua TURN relay candidate hay trực tiếp? "Rank-1×rank-1" của pilot là chọn TURN(A) và TURN(B) tới BE hay tới nhau?
5. TURN(A) và TURN(B) có thể tới BE theo đường nội bộ nào (cùng DC, backbone)? Có đo được TURN↔BE không?
6. BE có API/metrics per participant (RTT, loss, jitter) và lưu lịch sử không? Cho truy cập không?
7. Có abs-capture-time đàm phán không? Đồng hồ server đồng bộ bằng NTP hay PTP, độ chính xác?
8. coturn có bật log/Redis statistics per allocation (bytes/packets) không? Có đo RTT TURN→client?
9. Có E2E encryption (insertable streams) ảnh hưởng RTP header extension không?
10. Cuộc gọi 1:1 có luôn đi qua BE hay có P2P fallback?

---

## Trích dẫn

- [V-R7667] RFC 7667 RTP Topologies: https://www.rfc-editor.org/rfc/rfc7667.html
- [V-R3550] RFC 3550 RTP (6.4.1 RTT, loss, jitter): https://www.rfc-editor.org/rfc/rfc3550.html
- [V-R8656] RFC 8656 TURN: https://www.rfc-editor.org/rfc/rfc8656.html
- [V-R8445] RFC 8445 ICE (2.5 lite): https://www.rfc-editor.org/rfc/rfc8445.html
- [V-W3C] W3C webrtc-stats: https://www.w3.org/TR/webrtc-stats/
- [V-ACT] abs-capture-time: https://chromium.googlesource.com/external/webrtc.git/+/HEAD/docs/native-code/rtp-hdrext/abs-capture-time/README.md
- [V-WEBRTC-EXT] sender capture time (kết quả search): https://github.com/w3c/webrtc-extensions/issues/109 , https://w3c.github.io/webrtc-extensions/explainer , https://bugzilla.mozilla.org/show_bug.cgi?id=1713134
- [V-MS-RTP] mediasoup RTP parameters: https://mediasoup.org/documentation/v3/mediasoup/rtp-parameters-and-capabilities/
- [V-MS-DISC] mediasoup discourse (kết quả search, chưa mở): https://mediasoup.discourse.group/t/nack-generator-logic/5481
- [V-LK-PR] LiveKit PR #1781: https://github.com/livekit/livekit/pull/1781 (chỉ thấy qua search snippet)
- [V-JVB] Jitsi Videobridge statistics: https://github.com/jitsi/jitsi-videobridge/blob/master/doc/statistics.md
- [V-COTURN-PROM] coturn Prometheus: https://github.com/coturn/coturn/blob/master/docs/Prometheus.md

Giới hạn: không đọc được trang tài liệu chính của Janus và Pion; chưa kiểm chứng trực tiếp trên Chrome thật việc `captureTimestamp` và `estimatedPlayoutTimestamp`; một số trang RFC chỉ đọc qua tóm tắt công cụ nên nên đối chiếu lại trước khi trích nguyên văn.
