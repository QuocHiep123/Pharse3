# 01 - Nguồn dữ liệu mạng công khai để calibrate network model

Ngày nghiên cứu: 2026-11-04. Mục tiêu: calibrate synthetic network model (latency/loss/jitter giữa thành phố/quốc gia/ISP, mobile vs fixed, theo giờ) cho TURN Selector.

Quy ước độ tin cậy: **[V]** = đã đọc trực tiếp từ nguồn trong phiên nghiên cứu này; **[K]** = kiến thức nền, CHƯA verify trong phiên này (cần kiểm tra lại trước khi dựa vào); **[N]** = không tìm thấy.

## 1. Bảng tóm tắt

| Nguồn | Nội dung chính | Phủ VN / quốc gia | Truy cập | License | Chi phí | Giá trị calibrate |
|---|---|---|---|---|---|---|
| RIPE Atlas | ping/traceroute từ probe thật, theo ASN/country | VN: 41 probe đang connected, 2 anchor [V] | REST API, bulk dump, tạo measurement bằng credits | Dữ liệu mở (RIPE NCC terms) [K] | Miễn phí, tạo measurement tốn credits (credits kiếm bằng cách host probe) | Cao nhất cho RTT/loss/jitter per-ASN, nhưng mẫu VN nhỏ |
| WonderNetwork pings | RTT trung bình giữa ~250 thành phố, có min/max/stddev | Hanoi và HCMC đều có [V] | Web (scrape), không có API chính thức [K] | Chưa rõ, cần hỏi | Miễn phí | Ma trận city-to-city quốc tế rất tiện, nhưng là server datacenter, không phải end-user |
| M-Lab NDT | speed test: MinRTT, loss/retrans, throughput, kèm ASN + geo client | Toàn cầu, VN có [K] | BigQuery `measurement-lab.ndt.*`, GCS | CC0 1.0 [V] | BigQuery: free tier 1 TB/tháng, vượt thì trả theo query [K] | Cao: phân phối RTT/loss theo ASN, giờ, thành phố; client thật |
| Ookla Open Data | tile ~610 m: avg_d_kbps, avg_u_kbps, avg_lat_ms, tests, devices; tách fixed/mobile | Toàn cầu gồm VN [V] | S3 `s3://ookla-open-data` (no-sign-request), Parquet/Shapefile | CC BY-NC-SA 4.0 [V] | Miễn phí | Cao cho mobile vs fixed latency theo vị trí (không có ISP, không có loss/jitter) |
| Cloudflare Radar | IQI: bandwidth, latency idle/loaded, jitter, cấp country và ASN | Có VN và ASN [V] | Radar API (free), web | CC BY-NC 4.0 [V] | Miễn phí (cần API token [K]) | Trung bình-cao: median theo ASN/country theo thời gian, có jitter |
| CAIDA (Ark, ITDK, AS rank) | traceroute topology, AS relationship | Toàn cầu [K] | Download, cần đăng ký AUA | Chặt hơn, phi thương mại [K] | Miễn phí | Thấp-trung bình: dùng để dựng topology/path peering, không phải số latency |
| VNIX / nghiên cứu peering VN | mô tả IX, thành viên | VN [V] | Slide VNNIC | n/a | n/a | Chỉ định tính, không có số RTT [N] |
| WebRTC-QoE (Zenodo 15836614) | webrtc-internals + MOS dưới impairment cố định | Lab, không địa lý [V] | Download | Xem record Zenodo | Miễn phí | Ánh xạ loss/jitter/delay sang MOS (dùng ở tầng scoring, không phải network model) |
| Packet trace 13 app (Zoom/Teams/Meet) | pcap + domain/port | Lab [V] | Từ paper (arts.units.it) | Chưa rõ | Miễn phí | Thấp: hành vi bitrate/giao thức, không có QoS đo được |
| Microsoft/Zoom/Webex call-quality | -- | -- | -- | -- | -- | [N] Không có dataset công khai; chỉ có ngưỡng khuyến nghị của vendor |

## 2. Chi tiết từng nguồn

### 2.1 RIPE Atlas
- Nội dung: ping, traceroute, DNS, HTTP từ probe; field `rtt`, `sent`, `rcvd`, `dst`, `prb_id`; metadata probe: `country_code`, `asn_v4`, `is_anchor`, toạ độ.
- Verify (API `https://atlas.ripe.net/api/v2/probes/?country_code=VN&status=1`, 2026-11-04) [V]: 41 probe đang connected ở VN. Phân bố ASN: **AS18403 (FPT) 9, AS45899 (VNPT) 6, AS7552 (Viettel) 5**, còn lại 21 probe rải ở ~15 ASN nhỏ (131429, 135932, 63734, 149107, 45903, 150818...). Có 2 anchor: probe 7400 (VinaHost, HCMC, AS7552) và 7810 (AS131429).
- Hạn chế: 41 probe, hầu hết đặt ở fixed/home hoặc datacenter; gần như không có probe mobile 4G/5G; phân bố Bắc/Trung/Nam không rõ (cần lọc theo toạ độ). Probe nhà FPT khá nhiều, hữu ích cho đại diện FPT fixed.
- Cách dùng: (a) lấy built-in measurement (ping tới k-root / anchor mesh) của các probe VN qua `/measurements/{id}/results/` mà không tốn credits; (b) tạo user-defined ping từ probe VN tới anchor ở SG, JP, HK, DE, US, AU, TW, KR, TH, FR (tốn credits, probe VN 41 x 10 đích x 24h chấp nhận được); (c) anchor mesh có sẵn dữ liệu anchor-to-anchor giữa các nước để lấy RTT quốc tế.
- Cho ra: median/p95 RTT, loss, stddev (jitter proxy) theo cặp (ASN VN, nước đích) và theo giờ trong ngày.
- Docs: https://atlas.ripe.net/docs/apis/ ; https://atlas.ripe.net/api/v2/probes/ ; bối cảnh VN: https://blog.apnic.net/2017/06/21/vietnam-myanmar-join-asia-pacific-ripe-atlas-anchor-network/

### 2.2 WonderNetwork Global Ping
- Nội dung: bảng RTT trung bình/min/max/stddev giữa các thành phố (server của họ), cập nhật liên tục ("Last Checked" 2026-11-04). Có Hanoi và Ho Chi Minh City [V].
- Số liệu snapshot 2026-11-04 [V], xem mục 3.
- Cảnh báo: server datacenter (đường đi tốt hơn end-user); số liệu Hanoi-Singapore (55 ms) cao hơn HCMC-Singapore (28 ms) hợp lý về địa lý, nhưng Hanoi-Seoul 120 vs HCMC-Seoul 65 và Hanoi-Bangkok 70 vs HCMC-Bangkok 90 cho thấy routing không đơn điệu theo khoảng cách: nên lưu lại điều này vào model (routing-dependent, không chỉ distance-dependent).
- Truy cập: trang web; scrape cần xem ToS. Không thấy API chính thức [K]. Dùng làm ma trận RTT cơ sở / sanity check, không dùng làm nguồn duy nhất.
- URL: https://wondernetwork.com/pings/Hanoi ; https://wondernetwork.com/pings/Ho%20Chi%20Minh%20City

### 2.3 M-Lab NDT
- Nội dung [V một phần]: download/upload speed, RTT, packet loss; CC0 1.0, từ 2009 đến nay, lưu trên GCS và (theo trang) queryable qua BigQuery; ví dụ table `measurement-lab.ndt.download`. Nguồn: https://www.measurementlab.net/data/
- [K, cần verify schema, vì trang docs BQ trả 404 lúc kiểm tra]: view hợp nhất `measurement-lab.ndt.unified_downloads` / `unified_uploads` có `a.MinRTT`, `a.LossRate`, `a.MeanThroughputMbps`, `client.Geo.CountryCode`, `client.Geo.City`, `client.Network.ASNumber`, `client.Network.ASName`, `date`, `a.TestTime`. Server M-Lab đặt ở các metro (có SG, HK, TYO...), nên MinRTT đo là RTT client->metro gần nhất.
- Cho ra: phân phối MinRTT và LossRate theo ASN (7552/45899/18403), theo giờ (TestTime), theo thành phố. Không phân biệt mobile/fixed trực tiếp; suy luận qua ASN mobile (Viettel Mobile/Vinaphone/MobiFone dùng AS riêng hoặc chung, cần kiểm tra) hoặc không suy luận được cho ASN dùng chung.
- Hạn chế: RTT là tới server M-Lab gần nhất, không phải cặp tuỳ ý; số mẫu VN không rõ, nên COUNT trước khi chạy. Dùng `WHERE date BETWEEN` để giảm chi phí.

### 2.4 Ookla Open Data
- Nội dung [V]: tile zoom 16 (~610 m), `avg_d_kbps`, `avg_u_kbps`, `avg_lat_ms`, `tests`, `devices`, `quadkey`; hai layer `performance_fixed_tiles` (wifi/ethernet) và `performance_mobile_tiles` (4G/5G); quý từ Q1 2019 đến Q1 2026; bản April 2026 có xoá một số vùng. Loaded-latency chỉ có ở Parquet, thưa.
- Truy cập: `aws s3 cp --no-sign-request s3://ookla-open-data/parquet/performance/type=mobile/year=2026/quarter=1/...`; https://github.com/teamookla/ookla-open-data
- License: CC BY-NC-SA 4.0 (phi thương mại, ShareAlike). Đồ án OJT/học tập thì ổn, nhưng ghi attribution.
- Cho ra: avg_lat_ms mobile vs fixed theo toạ độ -> gán cho Hà Nội / Đà Nẵng / HCMC; trung bình có trọng số `tests`. Không có ISP, không có loss/jitter; latency là tới server speedtest nội địa gần nhất (vì vậy là access latency, không phải RTT tới nước ngoài). Đây chính là "access-network delay" cộng vào đường backbone.

### 2.5 Cloudflare Radar
- Nội dung [V qua search/blog]: Internet Quality page với bandwidth, latency (idle và loaded), jitter, cấp country và ASN, theo thời gian; có Connection Quality và IQI là hai nguồn khác nhau. Dữ liệu qua Radar API; license CC BY-NC 4.0 [V].
- Latency/jitter đo tới edge Cloudflare (gần), tức tương tự Ookla: đo access, không đo liên lục địa. Giá trị là có **ASN-level + time series (theo giờ)**, tốt cho hình dạng biến thiên theo giờ.
- Endpoint cụ thể (`/radar/quality/iqi/summary`, `/timeseries_groups`) [K, chưa verify]; xem https://developers.cloudflare.com/radar/ và https://blog.cloudflare.com/introducing-radar-internet-quality-page/

### 2.6 CAIDA
- Ark (traceroute từ monitor toàn cầu), ITDK (router-level topology), AS Relationships/AS Rank. Cần đăng ký và chấp nhận AUA [K]. Dùng để biết VN đi qua AS trung gian nào (ví dụ transit qua HK/SG), hỗ trợ xây path/hop model. Ít giá trị trực tiếp cho số latency. https://www.caida.org/catalog/datasets/ [K]

### 2.7 VNIX / peering Việt Nam
- Không tìm thấy nghiên cứu công khai đo RTT liên-ISP Viettel/VNPT/FPT [N]. Chỉ có định tính: VNIX giảm latency vì traffic nội địa không đi vòng quốc tế (https://vnnic.vn/node/827 ; https://conference.apnic.net/19/docs/sigs/ix/ix-pres-kien-vnix-intro.pdf); ước tính <5% traffic nội địa qua VNIX, phần lớn là peering trực tiếp trả phí giữa ISP lớn, tier-2/3 dùng VNIX ~70% (slide không rõ ngày: https://www.slideshare.net/bienledang/vietnamdigitalinfrastructurelandscapedangtungsoncmctelecompdf). Thành viên VNIX-HN/HCM: https://bgp.tools/ixp/VNIX-HN .
- Cách bù: dùng RIPE Atlas, ping giữa probe FPT <-> VNPT <-> Viettel (cross-ISP) và Hanoi <-> HCMC để đo trực tiếp; đây là khoảng trống nên tự đo.

### 2.8 WebRTC call-quality datasets
- WebRTC-QoE (Zenodo 15836614, đã có): webrtc-internals + subjective score dưới impairment cố định (jitter 0 hoặc 500 ms, loss 0/15/30%) [V]. Dùng cho mapping network->MOS, không cho phân phối mạng thực.
- Packet traces 13 app (Zoom/Teams/Meet/Skype) công khai: http://arts.units.it/bitstream/11368/3025214/3/09327919-Post_print.pdf [V]; không có loss/jitter đo sẵn.
- Microsoft/Zoom/Webex: không có dataset công khai [N]; chỉ có ngưỡng khuyến nghị (Zoom jitter 40 ms, Teams 30 ms theo https://dnsrobot.net/jitter-test; Microsoft Teams guidance thường nêu latency <100 ms một chiều, loss <1%, jitter <30 ms [K]).

## 3. Bảng số calibration

| Đại lượng | Giá trị | Loại / nguồn | Ghi chú |
|---|---|---|---|
| Hanoi <-> HCMC RTT | ~22 ms (21.93 / 22.11) | WonderNetwork 2026-11-04 [V], datacenter | End-user thường cao hơn; đo lại bằng RIPE Atlas |
| Hanoi -> Singapore | 55.2 ms | WonderNetwork [V] | |
| HCMC -> Singapore | 28.5 ms | WonderNetwork [V] | |
| Hanoi -> Hong Kong | 50.8 ms | WonderNetwork [V] | HCMC -> HK: 62.9 ms |
| Hanoi -> Tokyo | 92.6 ms | WonderNetwork [V] | HCMC -> Tokyo: 87.5 ms |
| Hanoi -> Seoul | 120.2 ms | WonderNetwork [V] | HCMC -> Seoul: 64.8 ms (bất thường, routing khác) |
| Hanoi -> Taipei | 47.6 ms | WonderNetwork [V] | HCMC -> Taipei: 79.8 ms |
| Hanoi -> Bangkok | 70.2 ms | WonderNetwork [V] | HCMC -> Bangkok: 89.7 ms |
| Hanoi -> Sydney | 139.0 ms | WonderNetwork [V] | HCMC -> Sydney: 240.4 ms |
| Hanoi -> Frankfurt | 188.7 ms | WonderNetwork [V] | HCMC -> Frankfurt: 226.7 ms |
| Hanoi -> Paris | 193.7 ms | WonderNetwork [V] | HCMC -> Paris: 237.2 ms |
| Hanoi -> New York | 258.3 ms | WonderNetwork [V] | HCMC -> New York: 262.1 ms; Hanoi -> Washington 267.6 ms |
| Singapore <-> Tokyo (backbone) | ~64 ms (NTT) / 68.9 ms (Hats) | NTT Com slide 2017; hatsnet.io 2026-08 [V] | sàn dưới cho đường dài |
| Hong Kong <-> Singapore (backbone) | 31.5 ms | hatsnet.io [V] | |
| Hong Kong <-> Tokyo (backbone) | 44.9-46.1 ms | hatsnet.io [V] | |
| Hanoi mobile latency median | 19 ms | Ookla (qua báo VietnamNet/The Star, 2026-10) [V, gián tiếp] | Access latency tới server nội địa |
| Hanoi fixed latency median | 4 ms | Ookla (qua báo VN) [V, gián tiếp] | Viettel fixed Q4/2023 cũng 4 ms |
| Mobile latency theo nhà mạng | Vinaphone 19, MobiFone 22, Viettel 26 ms | VietnamNet (ngày không rõ, nguồn Ookla) [V, gián tiếp] | Cần cross-check với Ookla Open Data |
| FPT fixed latency | 46 ms | speedgeo.net [V, nguồn/ngày không rõ] | Độ tin cậy thấp |
| Vietnam median latency | 78 ms | SpeedOf.Me (không phải Ookla) [V] | Đo tới nhiều server, không dùng làm chuẩn |
| Ngưỡng chất lượng call | jitter <30-40 ms | vendor guidance [V gián tiếp] | Dùng cho scoring |

Chú ý: số WonderNetwork là một snapshot, trung bình, từ datacenter. Sự lệch (ví dụ Hanoi-Seoul 120 vs HCMC-Seoul 65) cho thấy cần coi RTT là bảng tra theo cặp thay vì công thức khoảng cách. Số access-latency (Ookla/Cloudflare) phải CỘNG vào backbone RTT, không thay thế.

## 4. Top 3 khuyến nghị

1. **RIPE Atlas** (nguồn chính cho RTT/loss/jitter per-ASN và theo giờ). Là nguồn duy nhất cho phép đo trực tiếp cặp VN-ISP -> nước đích và cross-ISP nội địa (khoảng trống VNIX); verified có probe ở cả ba ASN (FPT 9, VNPT 6, Viettel 5). Hạn chế: mẫu nhỏ, thiếu mobile.
2. **Ookla Open Data** (mobile vs fixed latency theo vị trí). Cho tách mobile/fixed theo tile, ánh xạ Bắc/Trung/Nam, tải về miễn phí không cần credential. Dùng làm thành phần access-delay; chú ý license NC-SA.
3. **M-Lab NDT trên BigQuery** (phân phối loss và RTT theo ASN + giờ, client thật, CC0). Bù hai điểm RIPE Atlas thiếu: loss thật của người dùng cuối và time-of-day với lượng mẫu lớn. Phải verify schema và COUNT mẫu VN trước.

Bổ trợ: WonderNetwork làm ma trận city-to-city và sanity check (rẻ, nhanh); Cloudflare Radar làm hình dạng biến thiên theo giờ theo ASN/country (nếu M-Lab thưa); WebRTC-QoE cho tầng MOS. CAIDA để sau, chỉ khi cần topology.

## 5. Khoảng trống và việc tiếp theo
- Chưa có số mobile 4G/5G cho loss/jitter ở VN từ nguồn công khai đã verify; cần M-Lab theo ASN mobile hoặc tự đo.
- Chưa verify: schema BigQuery NDT, endpoint Radar API, license RIPE Atlas/WonderNetwork/CAIDA. Chưa tìm được dataset Bắc/Trung/Nam chia theo tỉnh ngoài tile Ookla.
- Số báo chí về Ookla (4/19/26 ms) là gián tiếp; nên tính lại từ Ookla Open Data tile bằng `tests`-weighted mean.
