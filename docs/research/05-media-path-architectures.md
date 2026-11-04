# 05 - Kiến trúc media path: backend nằm giữa các relay của hai phía
> **Áp dụng cho dự án (cập nhật 2026-11-04):** BE chỉ là backend signaling, media **không** đi qua BE ⇒ kiến trúc của công ty là **Pattern 1** (A → TURN(A) → TURN(B) → B, một PeerConnection). Phần Pattern 2 (SFU) và Pattern 3 (backbone) giữ làm tham khảo nếu kiến trúc thay đổi. Xem contract v0.3.0 §0.2.

Ngày nghiên cứu: 2026-11-04. Mục tiêu: hiểu cách các hệ thống gọi thực tế đặt một node backend giữa relay của A và relay của B, để mô hình hóa đường A -> TURN(A) -> BE -> TURN(B) -> B.

Quy ước tag:
- [V] = đã xác minh trong phiên này từ trang đã fetch (kèm URL), hoặc từ kết quả tìm kiếm trích dẫn nguồn đó (ghi rõ "qua search" khi chưa mở được trang gốc).
- [K] = kiến thức nền, chưa xác minh được trong phiên này. Không dùng [K] làm căn cứ thiết kế cuối cùng.

Giới hạn trung thực: nhiều trang tài liệu chính thức (Zoom, Agora, Twilio, Google Meet, WhatsApp, Messenger) không fetch được nội dung chi tiết. Các mục đó chủ yếu là [K]. Paper Switchboard: PDF tải về nhưng không trích được text, chỉ xác minh qua trang kết quả search. Chưa tìm thấy paper Microsoft nào khác về chọn relay/media-server cho Teams mà xác minh được; ngoài Via và Switchboard, có "Saving Private WAN" (Titan / Titan-Next) [V] abstract tại https://arxiv.org/abs/2407.02037.

## 1. Bảng tóm tắt

| Hệ thống | TURN/relay so với media server | Gọi 1:1 | Chọn vị trí server/relay | Cascading / backbone | Telemetry |
|---|---|---|---|---|---|
| Teams / Skype | Transport Relay (TR) tách khỏi Media Processor (MP); client tới MP trực tiếp hoặc qua TR [V] | P2P nếu được; không thì qua TR; MP chỉ khi cần xử lý media (ghi âm, phiên âm...) [V] | Cuộc họp đặt ở vùng của người vào đầu tiên; signaling tới server gần nhất [V] | Via: overlay trên private backbone của nhà cung cấp [V] | Client gửi telemetry lên Microsoft 365 (bước 8) [V] |
| Zoom | Client -> Zone Controller -> MMR [V qua search]; không có TURN chuẩn | [K] có P2P cho 1:1 trong một số trường hợp | Zone, rồi ZC chọn MMR theo vị trí và hiệu năng mạng [V qua search] | MMR liên lạc giữa data center [V qua search, mức chung] | [K] |
| Agora SD-RTN | Edge node + backbone ảo; không phải TURN [K] | [K] qua SD-RTN | "Chọn đường tốt nhất tự động", ML [V] | Chọn đường giữa edge theo path metric/latency (patent) [V qua search] | Giám sát mạng thời gian thực [V] |
| Twilio Video | SFU của Twilio; TURN luôn bật [V qua search] | Room type P2P đã deprecated; chỉ còn group (SFU) [V qua search] | `media_region` chọn tường minh [V qua search]; NTS: server gần nhất theo địa lý [V] | [K] | [K] |
| Cloudflare Realtime | TURN (anycast) tách riêng, thiết kế đi kèm SFU [V] | Qua SFU [V] (Cloudflare quản lý SFU) | TURN: anycast về location gần nhất [V]; SFU: app không chọn region [V] | [K] | [K] |
| LiveKit Cloud | SFU mesh; TURN nhúng (self-host) [V qua search] | Qua SFU | Client vào SFU gần nhất [V] | Mesh giữa SFU, mỗi SFU tự chọn nguồn theo tải và khoảng cách mạng, không có coordinator [V] | Có giám sát sức khỏe, chi tiết không công bố [V] |
| Jitsi | JVB là media server; coturn riêng [K] | [K] có chế độ P2P | Region-based bridge selection của Jicofo [V] | Octo / relay giữa các JVB, ICE + DTLS/SRTP [V] | [K] |
| Discord | Mọi voice qua SFU tự viết, không P2P, không ICE [V] | Qua SFU | Region của người vào đầu tiên (hoặc override); server ít tải nhất trong region [V] | Không thấy [V] | Server báo health/load vào etcd [V] |
| Google Meet / WhatsApp / Messenger | Không có tài liệu công khai xác minh được [V: không tìm thấy] | [K] | [K] | [K] | [K] |

## 2. Từng hệ thống

### 2.1 Microsoft Teams / Skype

Nguồn chính: https://learn.microsoft.com/en-us/microsoftteams/microsoft-teams-online-call-flows (fetch đầy đủ).

- Vị trí relay: Microsoft 365 gồm "Transport Relay, conferencing server, and Media Processor" phân tán toàn cầu, có edge gần mạng khách hàng [V]. Conferencing server có IP public nên không cần relay; client kết nối thẳng hoặc qua TR khi firewall hạn chế [V].
- 1:1: dùng ICE. Caller và callee mỗi bên lấy tập candidate (local, reflexive, relay), trao đổi qua signaling, STUN check chọn cặp tốt nhất [V]. Cả hai nội bộ -> direct; một bên nằm sau firewall -> dùng relay candidate của một trong hai bên [V]. Điểm quan trọng: "Media endpoint trong cloud được dùng theo nhu cầu xử lý media, không theo loại cuộc gọi"; cuộc gọi 1:1 có thể dùng media endpoint để phiên âm/ghi âm, trong khi họp 2 người có thể không dùng [V]. Tức là BE (MP) chen vào giữa vì lý do tính năng, không vì mạng.
- Chọn vị trí: "Hội nghị Teams được host tại vùng nơi người tham gia đầu tiên vào"; media P2P đi đường trực tiếp nhất; signaling luôn đến server gần nhất [V].
- Backbone: bài Via (SIGCOMM 2016) mô tả "overlay được quản lý, xây trên các private backbone nối data center của nhà cung cấp", chọn relay bằng lọc dự đoán + khám phá/khai thác (exploration-exploitation); phân tích 88 triệu cuộc gọi, 1.900 AS, 126 quốc gia; giảm tỷ lệ cuộc gọi tệ tới 66% [V] https://www.microsoft.com/en-us/research/publication/via-improving-internet-telephony-call-quality-using-predictive-relay-selection/. Lưu ý Via là nghiên cứu trên dữ liệu một nhà cung cấp VoIP lớn (Skype), không khẳng định là kiến trúc Teams hiện nay [V: abstract không nêu tên sản phẩm].
- Switchboard (SIGCOMM 2023, Bothra et al.): quản lý tài nguyên cho conferencing; mỗi cuộc gọi được host trên một media processing server ở một trong nhiều DC; giảm tới 51% chi phí provisioning, chịu 1.4x tải; so sánh với chính sách chọn DC khác (round-robin, locality) [V qua search] https://www.microsoft.com/en-us/research/uploads/prod/2023/08/sigcomm23-final936.pdf ; https://arxiv.org/pdf/2508.00426. Thuật toán chi tiết chưa đọc được.
- Titan / Titan-Next: gán chung "conferencing server và routing option (Internet hay WAN)" cho từng cuộc gọi; giảm tổng peak WAN tới 61% [V] https://arxiv.org/abs/2407.02037. Đây là ví dụ rõ nhất về "chọn chung" server và đường.
- Telemetry: client gửi telemetry lên Microsoft 365 sau khi chọn đường (bước 8) [V]; CQD tổng hợp telemetry tổ chức [V] https://learn.microsoft.com/en-us/microsoftteams/prepare-network.
- Ràng buộc: media của Teams chỉ đi qua relay native của Teams, không hỗ trợ relay bên thứ ba [V].

### 2.2 Zoom

Nguồn: kết quả search (whitepaper Zoom Client Connection Process, không fetch được do lỗi kết nối) và ThousandEyes https://docs.thousandeyes.com/product-documentation/best-practices/monitoring-zoom.
- Client chọn zone, hỏi Zone Controller để lấy MMR tốt nhất theo vị trí, hiệu năng mạng và giao thức [V qua search]. MMR host cuộc họp và lo liên lạc backend giữa các data center [V qua search].
- Có thể giới hạn region data center theo tài khoản trả phí [V qua search].
- P2P cho cuộc 1:1, cascading cụ thể giữa MMR, telemetry: [K], chưa xác minh.

### 2.3 Agora SD-RTN

Nguồn: https://www.agora.io/en/network-white-paper (trang marketing), search patent https://uspto.report/patent/app/20200067828.
- SD-RTN giám sát mạng thời gian thực và tự chọn đường hiệu quả nhất, dùng ML [V]. Patent mô tả SDN chọn đường tối ưu giữa các edge node theo path metric và độ trễ thấp nhất [V qua search; chưa chắc là cài đặt của Agora].
- Khách hàng chọn được network region để kiểm soát luồng dữ liệu [V].
- Phân biệt edge / last mile / backbone, cách chọn access point: [K]. Trang chính thức không nêu cấu trúc này (đã fetch, không có).

### 2.4 Twilio

- Network Traversal Service (TURN) "độc lập với Twilio Regions, định tuyến tới server gần nhất theo địa lý"; endpoint global.turn.twilio.com [V] https://www.twilio.com/docs/stun-turn.
- Video: client publish một lần lên SFU, SFU chuyển tiếp [V] https://www.twilio.com/docs/video/tutorials/understanding-video-rooms. Chỉ còn room type group; P2P/go/group-small deprecated; `media_region` chọn tường minh; TURN luôn bật [V qua search] https://www.twilio.com/docs/video/api/rooms-resource.
- Cascading, telemetry: [K].

### 2.5 Cloudflare Realtime

- TURN là relay managed nằm giữa client và SFU; client kết nối turn.cloudflare.com và tới location gần nhất qua anycast; miễn phí khi dùng với SFU [V] https://developers.cloudflare.com/realtime/turn/.
- SFU do Cloudflare vận hành, ứng dụng "không deploy SFU và không chọn region"; mỗi session một PeerConnection [V] https://developers.cloudflare.com/realtime/sfu/calls-vs-sfus/. Cách cascading nội bộ: [K].

### 2.6 LiveKit

- Cloud chạy nhiều SFU trong mesh, "multi-home": participant không cần cùng một server; kết nối tới SFU gần nhất, mục tiêu media server trong 100 ms từ bất cứ đâu [V] https://livekit.com/blog/scaling-webrtc-with-distributed-mesh.
- Mỗi SFU xác định track cần theo subscription cục bộ, hỏi các server khác, nhận phản hồi kèm tải và thông tin định tuyến, tự chọn nguồn theo tải và khoảng cách mạng; không coordinator trung tâm; relay dùng giao thức FlatBuffers mang RTP; hình dạng mesh đổi theo track [V] cùng URL.
- Self-host: Redis cho multi-node, TURN nhúng [V qua search; nguồn thứ ba] https://docs.livekit.io/cloud/architecture (trang docs fetch không có chi tiết).

### 2.7 Jitsi

- Cascading địa lý: ra mắt 2018, tắt 2020 vì tải, bật lại 2022 [V qua search] https://jitsi.org/blog/bridge-cascading-is-back/ (đã fetch). Người dùng kết nối bridge gần, các bridge chuyển tiếp cho nhau. RTT bước kế giảm 29% (223 -> 158 ms) giữa các châu lục [V]. Nhóm vùng gần nhau (Frankfurt+London) để tránh cascading làm tăng RTT [V].
- Relay (secure Octo): ICE + DTLS/SRTP giữa từng cặp bridge; Jicofo dùng RegionBasedBridgeSelectionStrategy; client biết region qua `config.deploymentInfo.userRegion` [V] https://github.com/jitsi/jitsi-videobridge/blob/master/doc/relay.md.
- coturn và chế độ P2P cho 1:1: [K].

### 2.8 Discord

- Mọi voice/video đi qua SFU C++ tự viết, không P2P; không dùng ICE vì client luôn kết nối relay server của Discord; 850+ voice server ở 13 region [V] https://discord.com/blog/how-discord-handles-two-and-half-million-concurrent-voice-users-using-webrtc.
- Guilds service gán voice server ít tải nhất trong region; mỗi voice server báo health/load vào etcd [V] cùng URL.
- Region mặc định "Automatic" dựa trên người đầu tiên vào kênh trống, có Region Override [V qua search] https://support.discord.com/hc/en-us/articles/1500007645701-Voice-Regions-on-Discord.

### 2.9 Google Meet, WhatsApp, Messenger

Không tìm được tài liệu chính thức xác minh được trong phiên này (search chỉ ra blog bên thứ ba). Tất cả là [K]: Meet dùng media server của Google; WhatsApp và Messenger dùng relay của hãng, có P2P cho 1:1 khi khả thi. Không dùng cho thiết kế.

## 3. Tổng hợp 3 pattern

### Pattern 1: P2P relay-relay (một PeerConnection, mô hình hiện tại)

```
A --UDP--> TURN(A) ==inter-relay== TURN(B) <--UDP-- B
```
(ICE chọn cặp candidate; relay-relay chỉ khi direct/srflx không thông. Teams 1:1 [V].)

- Legs: L1 A->TURN(A) (last mile); L2 TURN(A)->TURN(B) (đường giữa hai relay, Internet công cộng); L3 TURN(B)->B.
- Ai đo: L1/L3 do client SDK (RTT, jitter, loss từ getStats) và TURN server (allocation, byte count) ; L2 chỉ do probe agent đặt cạnh TURN hoặc suy ra (tổng end-to-end trừ L1, L3). Media server không có.
- Ghép: TURN(A) và TURN(B) do mỗi bên chọn độc lập theo ICE candidate; "coupled" duy nhất ở bước ICE chọn cặp. Không có thứ gì phải chọn chung ngoài cặp candidate cuối.

### Pattern 2: client -> TURN edge -> media server (SFU) -> TURN edge -> client

```
A -> TURN(A) -> [ SFU/MP ] -> TURN(B) -> B
        (leg-A: A..SFU)   (leg-B: SFU..B)  
```
Mỗi client có PeerConnection riêng tới SFU (Twilio, Cloudflare, Discord, LiveKit, Teams MP/conferencing server [V]).

- Legs: A->TURN(A); TURN(A)->SFU; SFU->TURN(B); TURN(B)->B. Hai "nửa" độc lập, SFU kết thúc DTLS/SRTP mỗi nửa (Twilio: SFU giải mã và mã hóa lại [V]).
- Ai đo: client SDK đo từng nửa riêng (RTT tới SFU qua getStats); TURN server đo cạnh A/B; media server đo cả hai nửa (RTCP, jitter buffer) và là nơi duy nhất thấy cả hai phía; probe agent cho leg TURN->SFU.
- Ghép: lựa chọn TURN(A) và TURN(B) về cơ bản tách rời (mỗi bên chọn edge gần mình, thường anycast/geo-DNS), NHƯNG vị trí media server phải chọn chung cho cả hai phía (Teams: vùng người vào đầu tiên [V]; Discord: region người đầu tiên [V]; Twilio: `media_region` tường minh [V]; Titan-Next: chọn chung server và routing option [V]). Phải chọn chung: vị trí SFU; rồi RTT tổng = RTT_A + RTT_B nên chọn SFU phải tối thiểu hóa tổng hoặc max, không phải mỗi bên riêng.

### Pattern 3: overlay/backbone giữa các edge

```
A -> Edge(A) ==== backbone (private/overlay, có thể nhiều hop) ==== Edge(B) -> B
        (TURN/relay nằm ở edge)      
```
Gồm Via (overlay trên private backbone) [V], Agora SD-RTN (edge + route selection) [V mức chung], LiveKit mesh và Jitsi Octo (bridge cascading) [V].

- Legs: A->Edge(A) (last mile); Edge(A)->Edge(B) qua backbone, có thể gồm nhiều đoạn con (đoạn qua Edge trung gian); Edge(B)->B.
- Ai đo: client SDK cho last mile; node backbone/edge tự đo (probe giữa các node) để xây bảng chi phí đường (SD-RTN, Via dùng đo đạc để dự đoán [V]); media server/bridge đo từng link relay (LiveKit chọn nguồn theo khoảng cách mạng [V]).
- Ghép: chọn Edge(A) và Edge(B) tách rời (gần mỗi client, LiveKit/Jitsi [V]) nhưng đường giữa chúng là quyết định thứ ba (routing) phụ thuộc cả hai edge; cần chọn chung cặp (Edge(A), Edge(B), đường backbone). Via: chọn relay/đường qua bandit với ngân sách relay [V]; Jitsi: nhóm vùng gần nhau để cascading không làm xấu đi [V].

### Ánh xạ với 3 giả thuyết về "BE"

- (a) BE = media server/SFU mà client kết nối riêng: Pattern 2. 
- (b) BE = backbone/overlay giữa các TURN: Pattern 3 (BE có thể là một hoặc nhiều hop).
- (c) BE chỉ là signaling: quay lại Pattern 1 (media không qua BE); Teams cũng tách rõ signaling và media [V].
- Lưu ý: ba pattern khác nhau ở chỗ "BE có nằm trong đường media không" và "BE có kết thúc SRTP không". Câu hỏi này có thể xác nhận bằng một câu hỏi với công ty: media của A và B có cùng một 5-tuple/PeerConnection không? Hoặc: trên đường đi, có SRTP bị giải mã tại BE không?

## 4. Hệ quả cho dự án

Không đổi data contract v0.2.0 (frozen) một cách im lặng; đề xuất dưới đây cần quyết định của Hiệp và Đoàn.

### Nếu Pattern 1 (c)
- Giữ nguyên mô hình. Không đổi gì.

### Nếu Pattern 2 (a)
- Data contract: thêm thực thể `media_server` (id, region, ISP/AS, toạ độ) và hai cặp leg mỗi cuộc gọi: `leg_A = {A->TURN(A), TURN(A)->MS}`, `leg_B = {MS->TURN(B), TURN(B)->B}`. Thêm trường `ms_selected_by` (first-joiner, caller region, explicit) và `ms_region`. Đổi tên/độ rộng leg: từ 3 leg thành 4 leg.
- Hồ sơ đo trong pilot: "chỉ đo rank-1 x rank-1 cho mỗi bên" nay phải thêm chiều "vị trí MS", vì rank-1 của A và rank-1 của B có thể dẫn tới MS khác nhau. Số cặp cần đo tăng theo số vị trí MS.
- Simulator: thêm bước chọn MS (chiến lược: first-joiner, min tổng RTT, min max RTT); độ trễ end-to-end = RTT(A..MS) + RTT(MS..B) + thời gian xử lý MS; không còn cặp relay-relay trực tiếp. Mô hình hoá "coupling": reward của lựa chọn TURN(A) phụ thuộc MS, do đó thuật toán chọn TURN không thể bỏ qua MS (xem Titan-Next: chọn chung [V]).
- Dashboard: thêm tab theo MS; tách "nửa A" và "nửa B" để phân bổ lỗi.

### Nếu Pattern 3 (b)
- Data contract: thêm `backbone_path` (danh sách node có thứ tự, hoặc id đường), `leg` thành đoạn tuỳ biến theo số hop; node edge có thể là TURN. Thêm `route_selector` (ai quyết định đường: BE hay client).
- Simulator: thêm ma trận chi phí giữa các edge (đo bởi probe, nên là dữ liệu đầu vào, không phải mô phỏng thuần), mô phỏng chọn đường (min delay, hoặc bandit như Via [V]); khi cross-region VN <-> quốc tế, backbone thay vì Internet công cộng cho L2.
- Telemetry: cần lấy từ node backbone (nếu công ty có), không chỉ client.

### Cho mọi pattern
- Thêm field `path_type` trong dữ liệu cuộc gọi: `p2p | relay_relay | via_ms | via_backbone`, và `bridge_in_path: bool`. Dữ liệu cũ mặc định `relay_relay`.
- Vì Teams cho thấy media endpoint có thể xuất hiện vì lý do tính năng (ghi âm, phiên âm) chứ không phải mạng [V], hỏi công ty BE có lý do tính năng không (vd. ghi âm, kiểm duyệt) để tránh mô hình hoá nhầm thành tối ưu mạng.
- Câu hỏi mở cần xác nhận với công ty (ưu tiên): (1) BE có kết thúc SRTP không; (2) có bao nhiêu BE, đặt ở đâu; (3) BE chọn theo người gọi, người nhận, hay first-joiner; (4) công ty đo được leg nào (client/TURN/BE).

## 5. Nguồn

- Teams call flows: https://learn.microsoft.com/en-us/microsoftteams/microsoft-teams-online-call-flows
- Teams network prep (CQD): https://learn.microsoft.com/en-us/microsoftteams/prepare-network
- Via (SIGCOMM 2016): https://www.microsoft.com/en-us/research/publication/via-improving-internet-telephony-call-quality-using-predictive-relay-selection/
- Switchboard (SIGCOMM 2023): https://www.microsoft.com/en-us/research/uploads/prod/2023/08/sigcomm23-final936.pdf
- Tetris (nhắc Switchboard): https://arxiv.org/pdf/2508.00426
- Saving Private WAN (Titan): https://arxiv.org/abs/2407.02037
- Zoom connection whitepaper (copy bên thứ ba, chỉ qua search): https://dcmpx.remotevs.com/us/zoom/SL/docs/doc/Zoom_Client_Connection%20Process_Whitepaper.pdf
- Agora network page: https://www.agora.io/en/network-white-paper ; patent: https://uspto.report/patent/app/20200067828
- Twilio STUN/TURN: https://www.twilio.com/docs/stun-turn ; Video rooms: https://www.twilio.com/docs/video/tutorials/understanding-video-rooms ; Rooms API: https://www.twilio.com/docs/video/api/rooms-resource
- Cloudflare TURN: https://developers.cloudflare.com/realtime/turn/ ; SFU: https://developers.cloudflare.com/realtime/sfu/calls-vs-sfus/
- LiveKit mesh: https://livekit.com/blog/scaling-webrtc-with-distributed-mesh
- Jitsi cascading: https://jitsi.org/blog/bridge-cascading-is-back/ ; relay doc: https://github.com/jitsi/jitsi-videobridge/blob/master/doc/relay.md
- Discord: https://discord.com/blog/how-discord-handles-two-and-half-million-concurrent-voice-users-using-webrtc ; https://support.discord.com/hc/en-us/articles/1500007645701-Voice-Regions-on-Discord
