# 07 - Bài toán chọn TURN khi có media server (BE) ở giữa
> **Áp dụng cho dự án (cập nhật 2026-11-04):** BE chỉ là backend signaling, media **không** đi qua BE ⇒ kiến trúc của công ty là **Pattern 1** (A → TURN(A) → TURN(B) → B, một PeerConnection). Phần Pattern 2 (SFU) và Pattern 3 (backbone) giữ làm tham khảo nếu kiến trúc thay đổi. Xem contract v0.3.0 §0.2. Trường hợp áp dụng là **§3.1 Trường hợp 1 (không có BE), biến thể (b) mỗi phía một TURN**, cùng trường hợp dùng chung một TURN (biến thể a).

Ngày: 2026-11-04. Trạng thái: research notes, chưa phải spec.

Chú thích tag: **[V]** = đã mở/đọc nguồn trong phiên này (kèm URL); **[K]** = kiến thức nền, chưa kiểm chứng trong phiên.
Lưu ý độ tin cậy: tag [V] ghi rõ mức đã đọc, "toàn văn" = đã trích text từ PDF/HTML, "abstract/tóm tắt" = chỉ đọc trang tóm tắt hoặc kết quả tìm kiếm. Switchboard chỉ đọc abstract (không mở được PDF), nên mọi chi tiết formulation của Switchboard đều là [K] hoặc gián tiếp qua bài khác.

Ghi chú: thông tin "BE" (A -> TURN(A) -> BE -> TURN(B) -> B) vẫn **chưa được xác nhận** từ công ty. Tài liệu này chuẩn bị sẵn khung cho cả 3 trường hợp để không phải làm lại khi có xác nhận.

---

## 0. Kết luận nhanh (TL;DR)

1. Nếu BE cố định theo cuộc gọi, hai lựa chọn TURN(A) và TURN(B) **tách rời** (đúng như giả thuyết), vì mọi metric đường đi cộng được theo đoạn: `cost = f(A,TURN(A),BE) + g(BE,TURN(B),B)`. Khi đó "joint" nằm ở **chọn BE** (và chọn ghép cặp BE khi cascade), không nằm ở TURN. Các hệ thống thực tế đều xử lý "joint" ở tầng chọn data center/media server, không phải tầng relay đầu cuối: Teams chọn MP data center theo quốc gia người join đầu tiên [V, Saving Private WAN]; VIA chọn "relaying option" = (không relay | 1 relay | cặp relay) [V, VIA PDF].
2. Có một ngoại lệ quan trọng làm TURN(A) và TURN(B) **không** tách hoàn toàn: (a) ràng buộc ngân sách/capacity dùng chung (budget relay trong VIA, capacity BE), (b) metric không cộng (max của hai phía, MOS phi tuyến), (c) BE được chọn *sau* TURN hoặc phụ thuộc TURN (ví dụ BE = điểm gặp của hai TURN trên backbone). Với metric "worst-side" (max), vẫn tách được theo từng BE nhưng **không** tách khi tối ưu BE chung.
3. Khuyến nghị phạm vi: Đoàn giữ thuật toán **per-side top-k có điều kiện theo BE** (`rank(TURN | side, BE)`), làm BE là tham số đầu vào (hoặc một tầng chọn riêng), và simulator/evaluation mở rộng oracle sang bộ ba (TURN(A), BE, TURN(B)).
4. Cảnh báo từ Jitsi (đo trên production): chọn "server gần nhất cho mỗi participant" có thể phản tác dụng; thêm một node trung gian thường làm RTT tăng, chỉ có lợi trong tình huống hẹp [V, Grozev 2018].

---

## 1. Tóm tắt nguồn và "what we take"

### 1.1 Microsoft Switchboard (SIGCOMM 2023)

- **Tóm tắt.** Controller quản lý tài nguyên cho dịch vụ hội nghị (Teams): cấp phát media processor (MP) ở data center, nhận biết "peak" vì chi phí phụ thuộc đỉnh sử dụng và đỉnh lệch múi giờ; cung cấp tài nguyên mạng+compute cùng lúc. Kết quả: giảm tới 51% chi phí provisioning với latency tương đương hoặc tốt hơn, trên hơn 1 năm record Teams [V, abstract: https://www.microsoft.com/en-us/research/publication/switchboard-efficient-resource-management-for-conferencing-services/].
- Bài sau mô tả Switchboard tập trung vào chọn data center cho cuộc gọi (pha chọn DC), còn chọn MP cụ thể trong DC dựa vào load balancer có sẵn [V: https://arxiv.org/html/2508.00426v1]. Mô tả "Switchboard dùng locality + cấu hình cuộc gọi (quốc gia người tham gia, số người, loại media) và giải một linear program" là từ bài Saving Private WAN [V: https://arxiv.org/html/2407.02037v1], không phải từ bản gốc.
- **Chưa đọc được toàn văn** (PDF sigcomm23 không mở). Biến quyết định, constraint chi tiết: [K].
- **What we take:** (i) cấp "MP/BE" được chọn theo **cấu hình cuộc gọi (country của các phía)**, không chỉ theo phía gọi; (ii) objective có thành phần **chi phí + capacity**, không chỉ latency; (iii) latency là ràng buộc/điều kiện chứ không phải duy nhất objective.

### 1.2 Saving Private WAN / Titan-Next (arXiv 2407.02037, Teams)

- **Tóm tắt.** Mỗi cuộc gọi Teams có một MP trong cloud DC; DC chọn theo năng lực compute, vị trí participant, call experience; gán **khi participant đầu tiên join, theo quốc gia của người đó**. Mỗi participant đi qua private WAN (mặc định) hoặc đường Internet rẻ hơn (tiết kiệm tới 53%). Titan (production) chuyển dần 1-3% traffic mỗi cặp country-DC sang Internet, trần ~20%, theo dõi loss/latency/jitter/MOS, rút về WAN nếu xấu ("ưu tiên safety hơn tối ưu"). Titan-Next (prototype) **quyết định chung MP DC và routing option**, objective = tổng peak bandwidth WAN trong 24h, constraint: gán hết cuộc gọi, capacity MP theo DC-timeslot, capacity đường Internet, trung bình max end-to-end latency dưới ngưỡng (~75-80ms). Giải lại LP mỗi 30 phút; di chuyển user khỏi đường Internet xấu (loss >= 1%). Đánh giá: oracle (ground truth, loại bỏ lỗi dự đoán) và prediction-based (Holt-Winters), baseline WRR, Locality First, Titan; trace sản xuất và ~3.5 triệu probe/ngày. MOS gần như phẳng tới ~75ms end-to-end rồi giảm tuyến tính. Đường Internet có loss/spike nhiều hơn WAN [V: https://arxiv.org/html/2407.02037v1, đã đọc 100k ký tự đầu].
- **What we take:** mẫu "last mile = Internet, giữa các MP = WAN riêng"; metric cho giữa-DC là **max end-to-end latency theo cặp participant** chứ không trung bình; mẫu đánh giá **oracle vs prediction** tách lỗi policy khỏi lỗi dự đoán; cơ chế **fallback có kiểm soát (A/B, rollback)**.

### 1.3 VIA (SIGCOMM 2016, Skype)

- **Tóm tắt.** Dữ liệu 430 triệu cuộc gọi Skype, 7 tháng, 126 nước. Mỗi cuộc gọi chọn một *relaying option*: đường mặc định, **bouncing** (một relay), hoặc **transit** (cặp relay đi qua backbone riêng giữa hai relay). Goal: gán mỗi call c một option r tối thiểu hoá `Q(c,r)` (RTT/loss/jitter kỳ vọng), giả định các call độc lập, có **budget B** (vd 30%) về tỷ lệ cuộc gọi được relay (relay chỉ khi lợi ích nằm trong top B percentile). Thuật toán "prediction-guided exploration": predictor theo lịch sử + **network tomography** (ghép các đoạn client-relay, relay-relay từ end-to-end, ví dụ RTT_AS3-AS4 = RTT_AS1-AS4 + RTT_AS2-AS3 - RTT_AS1-AS2) để phủ các "lỗ" dữ liệu; chọn **top-k** động theo khoảng tin cậy 95% (top-k là tập nhỏ nhất sao cho cận dưới của option ngoài top-k cao hơn cận trên của option trong top-k); explore bằng UCB1 sửa đổi (chuẩn hoá reward theo trung bình upper bound của top-k, dành một phần eps gọi cho khám phá ngẫu nhiên ngoài top-k). Đánh giá: **trace-driven replay** theo thứ tự thời gian, giả định hiệu năng một option = mẫu ngẫu nhiên từ cuộc gọi cùng AS-pair, cùng option, cùng cửa sổ 24h; so với oracle (chọn option tốt nhất theo ngày, bỏ qua load) và hai strawman. Kết quả: giảm PNR (poor network rate) 45% so với oracle 53% (từng metric), 23% vs 30% (ít nhất 1 metric xấu); dùng cả transit và bouncing tốt hơn chỉ bouncing (PNR thấp hơn 50% trên các AS pair dùng cả hai); VIA gửi ~54% call qua bouncing, 38% qua transit, 8% đường mặc định. Quan trọng: **lợi ích relay bị giới hạn khi nút cổ chai là last-mile ISP/last-hop**; cuộc gọi quốc tế được cải thiện nhiều hơn nội địa chút ít [V toàn văn: https://cs.cmu.edu/~junchenj/via.pdf, đã trích text].
- Ghi chú: MSR abstract ghi số liệu khác (88 triệu call, tới 66%) so với bản PDF (430 triệu, 45%) [V: https://www.microsoft.com/en-us/research/publication/via-improving-internet-telephony-call-quality-using-predictive-relay-selection/]. Ta dùng số của PDF.
- **What we take:** (i) **đơn vị quyết định là "option" gồm 0, 1 hoặc 2 relay**, rất khớp với (TURN(A), BE, TURN(B)); (ii) **tomography ghép đoạn** cho phép ước lượng bộ ba chưa quan sát từ per-leg stat, đúng bài toán thiếu dữ liệu cho ta; (iii) **top-k theo khoảng tin cậy** thay vì k cố định; (iv) **budget/capacity** là ràng buộc chung cho mọi call; (v) oracle không tính load -> báo cáo oracle như trần lý thuyết.

### 1.4 Hajiesmaili et al., IEEE TMM 2017 (cloud multi-party conferencing)

- **Tóm tắt.** Bài toán chung: gán user->agent + chọn agent transcoding. Objective `min sum_s (a1 F(d_s) + a2 G(x_s) + a3 H(y_s))`: delay (F, ví dụ trung bình của max-delay mỗi user), chi phí bandwidth giữa các agent (G), chi phí transcoding (H). Constraint: capacity bandwidth/CPU của agent và ngưỡng end-to-end Dmax = 400ms (ITU G.114). NP-hard (node assignment), giải bằng **Markov approximation** phân tán. Baseline: **nearest assignment** (mỗi user tới agent gần nhất, như Airlift, vSkyConf); lý do nearest không tối ưu: "oblivious to whereabouts of the other users in a session". Đánh giá: prototype EC2 + trace PlanetLab; giảm 77% chi phí vận hành mà delay thấp hơn [V toàn văn trích text: https://people.cs.umass.edu/~hajiesmaili/files/tmm2017.pdf]. Cũng ghi nhận: không tính chi phí user<->agent vì cố định sau khi gán.
- **What we take:** một công thức mẫu có **đủ ba nhóm: delay (max theo cặp), chi phí inter-agent, capacity**; baseline nearest-assignment là baseline bắt buộc cho evaluation.

### 1.5 Zhang, Niu, Hu, Liu - NOSSDAV 2014 (server selection & topology control)

- **Tóm tắt.** Topology: mỗi client chỉ nối một server, các server full-mesh. Bài toán: cho vị trí client và số server m, chọn **vị trí server (placement)** và **server nào cho client (assignment)** để tối thiểu **trung bình end-to-end delay** giữa mọi cặp client; "hard combinatorial problem" vì placement và assignment tương tác. Giải bằng D-Grouping (phân cụm client theo ping giữa client, không cần toạ độ) + tối ưu lồi để tinh chỉnh vị trí server + ánh xạ vào server thật. Ví dụ đồ chơi trong bài: 1 server 5.39, 2 server 4.83, 4 server 4.13 (đơn vị minh hoạ). Đánh giá: mô phỏng trên ping trace 518 node PlanetLab trong 20 ngày + prototype C++ 7000 dòng trên PlanetLab [V toàn văn: https://sites.ualberta.ca/~dniu/Homepage/Publications_files/szhang-nossdav14.pdf].
- **What we take:** tách placement/assignment, đo bằng **ping/RTT giữa phía client** để nhóm; số server là biến thiết kế (đánh đổi chi phí-delay).

### 1.6 Grozev et al., IEEE CCWC 2018 (Jitsi, geo-location)

- **Tóm tắt.** Mô tả Jitsi Meet: conference được cấp vào **vùng của người join đầu tiên**, giữ nguyên tới khi kết thúc. Đề xuất mô hình phân tán conference trên nhiều media server (Octo): các server nối với nhau, mỗi client nối đúng một server. Đo trên production AWS 4 vùng: 56.383 conference trong 6 tuần, **72% conference không bao giờ vượt 2 người** (và 1:1 dùng P2P), 40.214 session đo RTT. Kết quả quan trọng: "trong hầu hết trường hợp, RTT trung bình từ user tới server sẽ tăng nếu chen thêm server trung gian"; ví dụ user châu Âu -> eu-west-1 104ms, -> us-east-1 141ms, giữa hai server 75ms, nên đi qua eu-west thì dự kiến 179ms > 141ms trực tiếp; chỉ ~33% conference nhiều người có tình huống (hai người cùng vùng, server ở vùng khác) có thể được lợi. Kết luận: "kết nối mỗi participant tới server gần nhất, trái với hiểu biết thông thường, không những tốn kém mà còn phản tác dụng"; cần thêm nghiên cứu về thuật toán chọn server cho conference phân tán [V toàn văn trích text: https://jitsi.org/wp-content/uploads/2018/11/ccwc2018-geo.pdf]. Bài cũng trích Elmokashfi et al. (CoNEXT 2013): đưa traffic vào mạng riêng càng gần nguồn càng tốt, mang nó trong mạng đến gần đích rồi mới thả ra Internet, dùng TURN relay/B2BUA/MCU làm điểm gom.
- **What we take:** bằng chứng thực nghiệm rằng **thêm hop làm tăng RTT** nếu backbone không nhanh hơn Internet trực tiếp -> **luôn có phương án "không dùng BE" / direct hoặc 1 relay** trong tập lựa chọn; 1:1 là phần lớn thời gian cuộc gọi (72%) nên pilot 1:1 là đúng trọng tâm.

### 1.7 Jitsi Octo / Jicofo bridge selection (tài liệu cấu hình)

- Chiến lược mặc định `SingleBridgeSelectionStrategy` (bridge ít tải nhất, không tách conference); `RegionBasedBridgeSelectionStrategy` chọn bridge cùng vùng với client, cần bật Octo; "region groups" nới điều kiện để tránh dùng nhiều JVB trong cùng nhóm vùng; liên kết cascade dùng secure-octo (Colibri2) giữa từng cặp JVB [V qua tìm kiếm, chưa mở trang gốc: https://jitsi.org/blog/bridge-cascading-is-back/ , https://github.com/jitsi/jicofo/blob/master/jicofo-selector/src/main/resources/reference.conf]. Chi tiết mặc định giữa các phiên bản không thống nhất.
- **What we take:** thực tế sản xuất dùng **luật heuristic đơn giản (region match, ít tải) + nhóm vùng** để tránh cascade vô ích, chứ không giải tối ưu toàn cục.

### 1.8 Cloudflare Calls

- Mỗi client kết nối tới data center gần nhất qua **anycast/BGP**; mỗi server chịu trách nhiệm PeerConnection của client gần nó; media đi qua backbone Cloudflare giữa DC (cây phân phối theo từng track, có thể qua DC trung gian); nêu rõ hệ thống chọn vị trí SFU sau khi người đầu tiên vào là "makes routing inefficient when the rest of the participants are clustered elsewhere"; ~95% dân số Internet trong 50ms tới một DC Cloudflare; TURN cũng chạy anycast, nhiều cổng để vượt tường lửa. **Bài không nói về xử lý lỗi/di chuyển phiên** [V: https://blog.cloudflare.com/cloudflare-calls-anycast-webrtc].
- **What we take:** quan điểm "đẩy ISP/last-mile càng ngắn càng tốt, phần dài chạy trên backbone riêng", và phê phán "chọn theo người đầu tiên" (cũng là điều Teams và Jitsi làm).

### 1.9 Zoom

- Dùng geolocation chọn data center gần nhất; MMR nằm trong Meeting Zone; client test các Zone ứng viên rồi hỏi Zone Controller chọn MMR tốt nhất; mỗi data center nối nhiều DC khác bằng link riêng để dự phòng; nếu DC gần nhất hết capacity, traffic tràn sang DC khác [V ở mức kết quả tìm kiếm của các trang tổng hợp/bên thứ ba, chưa mở được tài liệu gốc của Zoom (zoomgov PDF 404, whitepaper không truy cập được): xem https://www.cometchat.com/blog/zoom-video-technology-architecture ; https://docs.thousandeyes.com/product-documentation/best-practices/monitoring-zoom]. Cách một meeting được tách ra nhiều DC: không tìm thấy mô tả. Coi là độ tin cậy thấp.
- **What we take:** mẫu **client-side probing** (đo thật rồi chọn) + **overflow khi capacity cạn**.

### 1.10 Agora SD-RTN

- Vendor mô tả "software-defined real-time network", dùng ML để định tuyến, tuyên bố độ trễ ~400ms hoặc thấp hơn; không có tài liệu nào (trong các trang đã mở) nói chi tiết về edge access node, chọn node vào hay backbone riêng [V ở mức marketing: https://www.agora.io/en/network-white-paper , https://www.agora.io/en/network]. Các tuyên bố số liệu là marketing, không kiểm chứng.
- **What we take:** gần như không có chi tiết dùng được; chỉ dùng như bằng chứng về xu hướng ngành. Không trích số liệu từ Agora vào đánh giá.

### 1.11 Microsoft Teams call flows (tài liệu chính thức)

- 1:1: caller và callee **cùng thu thập candidate** (host/reflexive/relay) qua Transport Relay, dùng ICE (STUN connectivity check) để chọn cặp tốt nhất; ưu tiên đường trực tiếp; nếu không thông thì một hoặc nhiều Transport Relay. Teams chỉ cho phép đi qua relay của Teams/Skype for Business. Teams meeting thì media endpoint (conferencing server) được **host ở vùng người đầu tiên join**; media endpoint dùng theo nhu cầu xử lý (ghi âm, transcription) chứ không theo kiểu cuộc gọi. Signaling luôn tới server gần nhất [V: https://learn.microsoft.com/en-us/microsoftteams/microsoft-teams-online-call-flows].
- **What we take:** trong stack WebRTC chuẩn, mỗi phía **tự chọn TURN riêng** (độc lập), và cặp tốt nhất được ICE chọn; điều này khớp với hình dung "per-side list". Nó cũng hàm ý BE (nếu có) nằm ngoài ICE, là lớp ứng dụng.

### 1.12 Tetris (arXiv 2508.00426) - về capacity/herding

- Gán call->MP gồm 2 pha: P1 chọn DC, P2 chọn MP trong DC. Với P2, **least-loaded gây "herding"**: call mới dồn vào cùng MP vì tải ban đầu thấp; LLR chọn ngẫu nhiên trong K=5 MP ít tải nhất để giảm herding; Tetris dùng peak CPU kỳ vọng + MIP migration mỗi 2 phút. Ngưỡng hot MP = 75% CPU. Đánh giá bằng simulator replay trace 24h trên 10 triệu call [V: https://arxiv.org/html/2508.00426v1].
- **What we take:** nếu nhiều call cùng chọn "BE tốt nhất" thì dồn tải; dùng **randomization trong top-k** và **admission bằng dự đoán peak** (xem §5).

### 1.13 Khác

- Elmokashfi et al., CoNEXT 2013, "Geography matters": mạng IP toàn cầu tự xây cho video conferencing, overlay có provision tốt + định tuyến BGP kiểu **cold-potato theo địa lý**, loss thấp hơn đáng kể so với transit toàn cầu [V ở mức abstract qua tìm kiếm: https://www.simulamet.no/research/geography-matters-building-efficient-transport-network-better-video-conferencing (trang 404 khi fetch; metadata từ kết quả tìm kiếm); DOI 10.1145/2537148 qua https://api.crossref.org/works/10.1145%2F2537148].
- Các patent mô tả quy trình: caller và callee mỗi bên đo latency tới ứng viên relay, **chọn relay có tổng latency thấp nhất** (US10129412); hoặc relay gần caller nhất không đủ, cần thăm dò đường đi (US9794164) [V ở mức kết quả tìm kiếm: https://uspto.report/patent/grant/10129412 , https://patents.google.com/patent/US9794164]. Độ tin cậy thấp, chỉ dùng như ví dụ ý tưởng.

---

## 2. Vị trí đặt BE trong cuộc gọi 1:1 và đánh đổi last-mile / backbone

Không có nguồn nào trong những nguồn đã đọc đưa ra **quy tắc đặt BE tối ưu cho 1:1** (gần caller / gần callee / điểm giữa). Ghi chung: phần này gom bằng chứng gián tiếp.

| Chiến lược | Bằng chứng/lập luận | Tag |
|---|---|---|
| Gần người đầu tiên (first joiner) | Teams (MP DC theo quốc gia người đầu tiên), Jitsi (vùng người đầu tiên). Đơn giản; đã bị Jitsi và Cloudflare chỉ ra là kém khi người còn lại ở nơi khác. | [V] Saving Private WAN, Grozev, Cloudflare |
| Gần mỗi phía rồi nối bằng backbone (hai BE cascade) | Cloudflare, Zoom, Elmokashfi: vào mạng riêng gần nguồn, ra gần đích. Nhưng Jitsi đo: chen server trung gian thường tăng RTT nếu đường Internet trực tiếp đã tốt (ví dụ 179 vs 141ms). | [V] |
| Điểm giữa / min tổng | Zhang 2014 và các bài placement: tối thiểu trung bình end-to-end delay. Với 1:1 chỉ có hai client nên "gần nhất mỗi phía" và "điểm giữa" là hai điểm khác nhau của cùng một đường cong; không có kết quả riêng cho 1:1. | [V] Zhang 2014 (tổng quát) / suy luận cho 1:1 [K] |
| Min của max hai phía (worst side) | Titan-Next dùng "max end-to-end latency" làm ràng buộc; Hajiesmaili dùng max theo cặp (d_u = max_v d_vu). Dùng khi QoE bị chi phối bởi phía tệ nhất. | [V] |
| Tối đa phần đường trên backbone riêng | VIA transit relay; Titan: WAN là mặc định, Internet là tối ưu chi phí; lợi ích backbone bị giới hạn khi nghẽn nằm ở last-mile. | [V] |

Đánh đổi last-mile (Internet công cộng) vs backbone (riêng):
- Backbone riêng: loss/jitter thấp và ổn định hơn; Internet: đôi khi RTT tốt hơn hoặc ngang nhau (Titan: Châu Âu - Bắc Mỹ), nhưng loss/spike nhiều hơn, jitter nhỉnh hơn [V, Saving Private WAN]. Elmokashfi: cold-potato theo địa lý giảm loss đáng kể so với transit [V ở mức abstract].
- VIA: relay ít giúp khi nghẽn là last-mile ISP của một phía [V]. Hệ quả: **với phía có last-mile xấu, chọn TURN gần hơn có tác dụng lớn hơn chọn BE**; ngược lại phần xuyên lục địa mới là chỗ BE/backbone có giá trị.
- Zoom/Cloudflare/Agora đều quảng bá "vào mạng riêng càng sớm càng tốt" nhưng không cung cấp số liệu độc lập (Agora: marketing; Zoom: chưa mở được gốc) [V ở mức đã nêu].

Kết luận cho dự án: **chưa có cơ sở để cố định luật đặt BE**. Nên coi vị trí BE là biến cần chọn dựa trên số đo per-leg, và trong simulator thử cả bốn luật (first-joiner, gần caller, gần callee, min-max) như baseline policy để xem khoảng chênh [K, đề xuất].

---

## 3. Công thức hoá bài toán chọn

Ký hiệu: người gọi A, người nhận B; tập TURN ứng viên T_A, T_B (thường cùng một catalog T); tập BE ứng viên E; metric cho đoạn l là vector m_l = (rtt, loss, jitter) ở thời điểm t; hàm tổng hợp cộng/độ trễ cộng, loss kết hợp `1 - prod(1 - loss_l)`, jitter xấp xỉ theo căn của tổng bình phương hoặc tổng [K]. Chất lượng đường đi `Q(path)` ví dụ MOS/E-model từ (delay một chiều, loss) [K]. Tổng quát các nguồn: Q thường chỉ có thể mô hình hoá qua một hàm chi phí `J` (delay có phạt loss).

### 3.1 Trường hợp 1: không có BE (A -> TURN(A) ... TURN(B) -> B hoặc direct qua một relay)

Có hai biến thể. (a) **Một relay chung** (cả hai phía dùng cùng TURN r): `path = A -> r -> B`; chọn `r* = argmin_{r in T} J(L_{A,r} + L_{r,B})`. Đây là trường hợp trong patent US10129412 (relay có tổng latency thấp nhất) [V qua tìm kiếm]. (b) **Mỗi phía một TURN riêng** (WebRTC thực tế, hai allocation riêng, ICE chọn cặp): chọn (r_A, r_B) với đường giữa r_A và r_B là Internet/WAN không điều khiển được: `J = L_{A,rA} + L_{rA,rB} + L_{rB,B}`. Ở đây r_A và r_B **chỉ ghép qua số hạng giữa** L_{rA,rB}.

- Biến quyết định: r (a) hoặc (r_A, r_B) (b); ràng buộc: capacity TURN, chính sách (băng thông, TCP/UDP fallback).
- Tính joint: (a) joint hoàn toàn (một biến, tổng hai phía); (b) joint chỉ qua `L_{rA,rB}` - nếu ta không đo/ước lượng đoạn giữa thì tách rời được và nearest-per-side là phép xấp xỉ; nếu đoạn giữa đáng kể (xuyên lục địa) thì joint thật sự cần.
- Tương ứng với bài toán gốc của đề tài ("joint caller+callee cho cuộc gọi quốc tế"), và là chỗ ta có nhiều lý do bảo vệ nhất vì **đoạn giữa phụ thuộc cặp (r_A, r_B)**. [K, suy luận]

### 3.2 Trường hợp 2: một BE cố định theo cuộc gọi

`path = A -> r_A -> e -> r_B -> B`, e do hệ thống cấp (cố định, không phải biến). Cả metric cộng: 
`J(r_A, r_B | e) = J_A(r_A | e) + J_B(r_B | e)` với `J_A(r_A|e) = L_{A,rA} + L_{rA,e}`, `J_B(r_B|e) = L_{e,rB} + L_{rB,B}`.
- Hai bài toán độc lập: `r_A* = argmin_r J_A(r|e)`, `r_B* = argmin_r J_B(r|e)`. **Đúng như giả thuyết của đội: tách rời** (decoupled). Điều kiện: (i) hàm mục tiêu cộng được; (ii) không có ràng buộc chung giữa hai phía (capacity TURN dùng chung là ràng buộc chung nhưng chỉ khi r_A = r_B hoặc cùng pool); (iii) nếu metric là **max** (worst side): `min_{rA,rB} max(J_A, J_B)` vẫn tách: min mỗi phía rồi lấy max, tối ưu vì hai hàm độc lập [K, chứng minh tầm thường].
- Điều kiện **không tách**: QoE phi tuyến theo tổng (MOS theo delay tổng): vẫn tách nếu J tăng đơn điệu trong từng phần và ta chỉ cần tối thiểu delay tổng, nhưng **loss cộng dồn kiểu nhân** vẫn đơn điệu nên tách được; nếu có ràng buộc tổng như "tổng delay <= D_max" (Hajiesmaili/Titan-Next) thì feasibility phụ thuộc cặp nhưng với mục tiêu min tổng nghiệm tối ưu vẫn là tổng hai phần tối ưu [K].
- Kết quả thiết kế: ranking **per-side có điều kiện e** là đủ; "joint" chỉ còn một điểm chạm là ràng buộc ngân sách/capacity (VIA budget B, capacity TURN).

### 3.3 Trường hợp 3: nhiều BE (chọn BE, hoặc cascade hai BE)

(a) Chọn một BE `e in E`: 
`min_{e, rA, rB} J_A(rA|e) + J_B(rB|e) + lambda * c(e) + penalty(load(e))`.
Với e cố định, rA, rB tách rời như §3.2; do đó `V_A(e) = min_rA J_A(rA|e)`, `V_B(e) = min_rB J_B(rB|e)`, và `e* = argmin_e V_A(e) + V_B(e) + ...`. **Joint thực sự nằm ở e.** Bài toán là tổ hợp |E| lựa chọn, giải bằng liệt kê (E nhỏ).
(b) Cascade hai BE: `A -> rA -> e_A ==backbone==> e_B -> rB -> B`; thêm biến (e_A, e_B) với đoạn `L_{eA,eB}` (backbone riêng, ổn định); `J = J_A(rA|eA) + L_{eA,eB} + J_B(rB|eB)`. Với (eA, eB) cố định lại tách rời; toàn bài toán là chọn cặp (eA, eB) giống VIA transit relay (cặp relay đi qua backbone) [V, VIA]. Zhang 2014 là trường hợp placement khi số BE là biến chọn (m server) [V].
(c) Có thêm lựa chọn "bỏ BE" (đi thẳng hoặc 1 relay): phải nằm trong tập lựa chọn vì Jitsi cho thấy chen trung gian có thể làm xấu đi [V].
- Ràng buộc: capacity BE (tải CPU/băng thông), chi phí egress giữa BE (Hajiesmaili G(x), Titan-Next peak WAN bandwidth), ngưỡng trễ (Dmax 400ms một chiều theo ITU G.114 trong Hajiesmaili; Titan-Next ~75-80ms).
- Phụ thuộc thời gian/online: VIA coi là bandit (exploration-exploitation) vì chất lượng thay đổi theo thời gian [V].

Tóm tắt phụ thuộc: 

| Trường hợp | Biến | Tách A/B? | "Joint" nằm ở |
|---|---|---|---|
| Không BE (a) một relay chung | r | Không | r |
| Không BE (b) hai TURN riêng | (rA, rB) | Chỉ khi bỏ đoạn giữa | số hạng L(rA,rB) |
| BE cố định | (rA, rB) | **Có** | chỉ ràng buộc chung (budget/capacity) |
| Nhiều BE | (e, rA, rB) hoặc (eA, eB, rA, rB) | Có, **sau khi cố định BE** | chọn BE |

---

## 4. Khuyến nghị

### 4.1 Phạm vi thuật toán của Đoàn

1. **Giữ mục tiêu "top-k TURN per side" nhưng định nghĩa lại có điều kiện:** `rank_k(side, ctx)` với ctx = {BE hoặc "none"}. Khi chưa có BE (hiện tại): ctx="none", đầu ra như cũ. Khi có BE cố định: đổi hàm điểm thành `J_side(r | e)`, không cần đổi kiến trúc. [K, đề xuất]
2. **Không tuyên bố "joint optimization" ở tầng TURN nếu BE cố định.** Nếu BE cố định, nói thẳng trong báo cáo: TURN(A)/TURN(B) tách rời, joint = chọn BE. Nếu đề bài vẫn đòi joint, hai cách trung thực: (i) joint = chọn **(rA, rB)** khi có số hạng đoạn giữa (trường hợp 3.1b), hoặc (ii) joint = chọn BE + TURN hai phía (3.3). Cần hỏi công ty để chốt (xem §6).
3. **Thuật toán nên đơn giản trước, cho điểm theo từng đoạn:** cộng metric theo đoạn (delay cộng, loss nhân) từ thống kê per-leg, tương tự tomography của VIA [V]; chọn top-k theo khoảng tin cậy (VIA) thay vì k cố định [V]; có exploration nhỏ (eps) để cập nhật số đo.
4. **Fallback:** top-k mỗi phía phải gồm ít nhất một ứng viên **khác vùng/AS/nhà cung cấp** (diversity) để khi TURN/đường hỏng (hoặc BE đổi) có phương án tức thì; Titan có cơ chế rollback tự động khi loss tăng [V]. Khi BE hỏng: (a) giữ nguyên top-k per-side nếu BE thay thế gần như cùng vị trí; (b) tính lại `J(r|e')` từ số đo per-leg đã lưu (không cần đo lại toàn bộ) [K]. Điều cần nhóm để ý: danh sách TURN tối ưu theo BE này có thể khác hẳn theo BE khác, nên **đa dạng top-k xuyên BE** (top-k cho từng e trong tập BE khả dĩ) phải được tính trước hoặc tính lười, không có nguồn nào cho thấy chuẩn nào [K].
5. **Không làm** trong phạm vi Đoàn: tối ưu vị trí BE (placement) và provisioning (Switchboard-like); các vấn đề này thuộc phía vận hành công ty [K].

### 4.2 Simulator và evaluation (Hiệp)

1. **Oracle bộ ba:** oracle_t = `argmin_{(rA,e,rB) in feasible} J_true(A, rA, e, rB, B, t)`, trong đó J_true là hiệu năng thực quan sát/ước lượng của bộ ba tại thời điểm t. Với e cố định rút gọn thành hai oracle per-side, nên **tập evaluation chia theo case** (no-BE, fixed-BE, multi-BE).
2. **Regret chung theo đường đi:** `regret = J(selected triple) - J(oracle triple)` (tuyệt đối và tương đối), báo cáo **phân phối (p50/p90/p99)** và tỷ lệ "poor-quality" kiểu PNR của VIA [V]. Với per-side top-k: `regret@k` = min trong top-k bộ ba tạo từ top-k mỗi phía so với oracle. Khi tách rời, regret chung = tổng hai regret per-side (kiểm tra bất biến này trong test của simulator) [K].
3. **Baseline bắt buộc:** nearest-per-user (Hajiesmaili Nrst) [V], first-joiner/locality-first (Teams, Jitsi) [V], random/weighted round robin (Titan-Next) [V], và direct/no-BE (Jitsi cảnh báo thêm hop có thể tệ) [V].
4. **Cách replay:** trace-driven theo thứ tự thời gian, hiệu năng của một option = mẫu từ cuộc gọi cùng cặp, cùng option, cùng cửa sổ (VIA 24h) [V]; ta thiếu số đo cho bộ ba chưa từng chạy, nên cần **tomography/ghép đoạn** từ per-leg (A<->TURN, TURN<->BE, BE<->TURN, TURN<->B) và khai báo rõ giả định cộng đoạn [V ý tưởng, K chi tiết].
5. **Features cần có (per-leg):** `rtt, loss, jitter` (+ số mẫu, khoảng tin cậy, timestamp) cho 4 loại đoạn: user<->TURN (mỗi phía), TURN<->BE, BE<->BE (nếu cascade); metadata: vùng/AS/ISP/loại mạng (WiFi/4G), TURN capacity/load, BE load; ngữ cảnh: cặp quốc gia. Các số liệu BE<->TURN và giữa BE nên có từ probing của hệ thống (VIA lấy RTT giữa relay từ Skype) [V]. Lưu ý rằng hiện tại pilot chỉ đo per-leg trên rank-1 x rank-1 (top-4 mỗi phía) theo memory dự án, nên **dữ liệu off-policy cho bộ ba ngoài top là thiếu**: cần off-policy evaluation/ước lượng hoặc exploration có chủ đích (xem 03-relay-selection-and-ope.md) [K].
6. **Capacity/herding trên BE:** mô phỏng tải (số call đồng thời/CPU/băng thông) cho mỗi BE; thêm ngưỡng 75% hot như Tetris [V]; thử hai chính sách: chọn BE tốt nhất cho mọi call (dễ herding) vs random trong top-K (LLR, K=5 trong Tetris) [V]; đo **tỷ lệ call bị từ chối/trượt BE** và regret theo tải. Oracle không tính load (VIA) nên báo cáo thêm "oracle có capacity" [V ý, K cách làm].
7. **Metric:** regret (ms hoặc MOS), tỷ lệ chọn đúng oracle@1/@k, p90/p99 của delay đường đi, PNR (ngưỡng từ VIA: RTT/loss/jitter tệ) [V cho khái niệm; ngưỡng cụ thể K], số lần đổi BE/migration (Titan-Next đếm migration) [V], chi phí egress giữa BE nếu có.
8. **Ngưỡng QoE gợi ý:** MOS gần phẳng đến ~75ms end-to-end rồi giảm tuyến tính (Teams); ITU G.114 400ms một chiều (Hajiesmaili, Jitsi trích) [V].

---

## 5. Lưu ý về chất lượng bằng chứng (những gì chưa kiểm chứng)

- Switchboard: chưa đọc toàn văn; mọi chi tiết objective ngoài abstract là [K] hoặc gián tiếp.
- Zoom, Agora: chỉ có tài liệu thứ cấp/marketing; không dùng số liệu của họ làm bằng chứng định lượng.
- Chưa tìm thấy bài báo học thuật nào định nghĩa chính xác "TURN(A) -> BE -> TURN(B)" kèm danh sách top-k per-side; công thức §3 là **suy luận của chúng tôi** dựa trên VIA (option = cặp relay), Hajiesmaili (delay cộng theo đoạn) và Zhang (placement/assignment).
- Chưa tìm được luật tối ưu đặt BE cho 1:1; xem §2.
- Elmokashfi 2013 chỉ đọc ở mức abstract qua kết quả tìm kiếm.
- Jitsi: kết luận "thêm server làm tăng RTT" dựa trên bốn vùng AWS và RTT trung bình theo vùng, **không nhất thiết đúng** với backbone riêng nhanh hơn Internet công cộng.

## 6. Câu hỏi cần hỏi công ty để chốt phạm vi

1. BE có thật sự tồn tại trên đường media? Là media server (SFU/MCU, có xử lý) hay chỉ là backbone relay? (ảnh hưởng: có thể cần xử lý/transcoding -> thêm chi phí và capacity.)
2. BE cố định theo cuộc gọi hay có thể cascade/đổi giữa cuộc gọi? Ai chọn BE và bằng tiêu chí nào (first-joiner, locality)?
3. Có thể đo từng đoạn TURN<->BE không, hay chỉ end-to-end? Số liệu BE<->BE đã có chưa?
4. Cuộc gọi 1:1 có luôn qua BE hay chỉ khi P2P/ICE thất bại (như Teams: ưu tiên đường trực tiếp)? [V, Teams call flows]
5. Đề bài "joint caller+callee" kỳ vọng ở mức TURN(A,B), mức BE, hay cả hai?

---

## 7. Danh mục nguồn (URL)

1. Switchboard, SIGCOMM 2023 (abstract): https://www.microsoft.com/en-us/research/publication/switchboard-efficient-resource-management-for-conferencing-services/
2. Saving Private WAN (Titan, Titan-Next, mô tả Teams MP): https://arxiv.org/html/2407.02037v1 ; PDF: https://arxiv.org/pdf/2407.02037
3. VIA, SIGCOMM 2016 (toàn văn): https://cs.cmu.edu/~junchenj/via.pdf ; trang MSR: https://www.microsoft.com/en-us/research/publication/via-improving-internet-telephony-call-quality-using-predictive-relay-selection/
4. Hajiesmaili et al., IEEE TMM 2017: https://people.cs.umass.edu/~hajiesmaili/files/tmm2017.pdf
5. Zhang, Niu, Hu, Liu, NOSSDAV 2014: https://sites.ualberta.ca/~dniu/Homepage/Publications_files/szhang-nossdav14.pdf
6. Grozev et al., CCWC 2018 (Jitsi geo-location): https://jitsi.org/wp-content/uploads/2018/11/ccwc2018-geo.pdf
7. Jitsi bridge cascading (blog + cấu hình Jicofo): https://jitsi.org/blog/bridge-cascading-is-back/ ; https://github.com/jitsi/jicofo/blob/master/jicofo-selector/src/main/resources/reference.conf ; https://github.com/jitsi/jitsi-videobridge/blob/master/doc/relay.md
8. Cloudflare Calls: https://blog.cloudflare.com/cloudflare-calls-anycast-webrtc
9. Agora SD-RTN: https://www.agora.io/en/network-white-paper ; https://www.agora.io/en/network
10. Zoom (thứ cấp): https://www.cometchat.com/blog/zoom-video-technology-architecture ; https://docs.thousandeyes.com/product-documentation/best-practices/monitoring-zoom
11. Microsoft Teams call flows: https://learn.microsoft.com/en-us/microsoftteams/microsoft-teams-online-call-flows
12. Tetris (call-to-MP, herding): https://arxiv.org/html/2508.00426v1
13. Elmokashfi et al., CoNEXT 2013: https://www.simulamet.no/research/geography-matters-building-efficient-transport-network-better-video-conferencing (metadata) ; https://api.crossref.org/works/10.1145%2F2537148
14. Patent relay selection (thứ cấp): https://uspto.report/patent/grant/10129412 ; https://patents.google.com/patent/US9794164
