# 02 - WebRTC stats: format, preprocessing, feature engineering, KPI

Ngày: 2026-11-04. Phạm vi: nguồn dữ liệu (a) simulator, (b) Zenodo WebRTC-QoE (record 15836614), (c) production logs.

Chú thích độ tin cậy: **[V]** = đã xác minh từ trang web trong phiên research này; **[K]** = kiến thức nền (spec/RFC/code đã biết), chưa fetch lại được (w3.org trả 403, README rtcstats không mô tả format) -> cần verify bằng cách đọc source/file mẫu trước khi chốt code.

---

## 0. Phát hiện quan trọng về dataset Zenodo

- [V] Record 15836614 là **WebRTC-QoE** (Univ. Cagliari, CC BY 4.0, DOI 10.21227/mb47-hf44): 20 người x 15 test condition (TC) = **300 file** `webrtc_internals_dump-TCx_y-z-t.txt`, 396 MB giải nén. Cấu trúc thư mục `User1..User20`.
- Tên file mã hóa điều kiện mạng: x = TC, y = delay ms {0,500,1000}, z = jitter ms {0,500}, t = loss % {0,15,30}. Nhãn là ACR 1-5 (`Subjective_results_dataset.csv`, 300 dòng).
- Hệ quả: dữ liệu là **lab/controlled network impairment**, 2 bên, **không có nhãn TURN/relay** (cần kiểm tra thực tế trong dump có candidate `relay` hay không; khả năng cao là host/srflx). Dùng được để calibrate MOS/quality score (so E-model với ACR), KHÔNG dùng để học TURN selection. Phải parse tên file thành cột ground-truth (`impair_delay_ms`, `impair_jitter_ms`, `impair_loss_pct`) và dùng làm label kiểm chứng phép đo.
- Lưu ý: delay 500/1000 ms và loss 15/30% nằm ngoài miền hợp lệ của E-model (G.107 chủ yếu delay < 400 ms) -> chỉ dùng như điểm kiểm tra đơn điệu, không coi là hiệu chuẩn chính xác.

---

## 1. Định dạng dump

### 1.1 Chrome webrtc-internals dump (`chrome://webrtc-internals` -> Create Dump) [K]

JSON object, các khóa cấp 1 chính:

```
{
  "getUserMedia": [...],
  "PeerConnections": {
    "<pid>-<n>": {
      "pid": ..., "url": "...", "rtcConfiguration": "{iceServers:[...], iceTransportPolicy:...}",
      "constraints": "...",
      "updateLog": [ { "time": "<ISO/epoch string>", "type": "iceConnectionStateChange", "value": "connected" }, ... ],
      "stats": {
        "<statsId>-<metricName>": {
          "startTime": "2024-...Z", "endTime": "2024-...Z",
          "statsType": "inbound-rtp",
          "values": "[0.01,0.02,...]"      // CHUỖI JSON của mảng số, 1 phần tử / lần getStats (mỗi ~1 s)
        }, ...
      }
    }
  },
  "UserAgent": "...", "version": ...
}
```

Điểm cần nhớ:
- Stats là **time series theo từng metric**, khóa `"<statsObjectId>-<metricName>"` (vd `RTCIceCandidatePair_xxx-currentRoundTripTime`, `RTCInboundRTPAudioStream_123-jitter`). Phải tách khóa bằng `rsplit('-', 1)`, vì ID có thể chứa dấu `-`.
- `values` là **string** chứa mảng JSON (phải `json.loads` lần 2). Không có timestamp từng điểm: timestamp điểm i phải nội suy `startTime + i * (endTime-startTime)/(n-1)` hoặc dùng khoảng poll 1 s. Các metric của cùng object có thể có `startTime` khác nhau (object xuất hiện muộn).
- Giá trị string (state, candidateType...) cũng nằm trong `values` dạng mảng chuỗi.
- Trong các bản Chrome mới, `stats` còn có dạng metric kiểu `[<id>]`/`[kind]` và nhiều giá trị lặp; luôn code theo kiểu phòng thủ (thiếu khóa -> NaN, không crash).
- Dump gốc **không** nén delta; chỉ lưu dạng "đã bỏ trùng thời gian" theo từng metric.
- `updateLog` là nguồn cho state machine (iceconnectionstatechange, connectionstatechange, icecandidate, setLocalDescription/setRemoteDescription, `onicecandidate`, `icecandidateerror`) -> dùng tính Call Setup Time, ICE time.

### 1.2 rtcstats dump (github.com/rtcstats/rtcstats) [V một phần / K]

- [V] Gói: `rtcstats-js` (SDK client, stream dump lên server), `rtcstats-server` (nhận, ghi dump lên S3-compatible, metadata + feature vào DB), `rtcstats-features` (trích feature offline), `dump-importer` (đọc cả định dạng rtcstats và webrtc-internals). README không mô tả format dump.
- [K] Dump rtcstats (legacy/fippo): file text, dòng đầu là meta (version/client info); mỗi message là mảng JSON `[method, peerConnectionId, args, timestamp]`, ví dụ `["create","PC_0",{config},ts]`, `["addIceCandidate","PC_0",{...},ts]`, `["oniceconnectionstatechange","PC_0","connected",ts]`, `["getStats","PC_0",{statsId:{timestamp,type,...}},ts]`. Server nén cả file (gzip), client có thể gửi qua WebSocket với permessage-deflate.
- [K] **Delta/dedup**: rtcstats-js chỉ gửi trong `getStats` những **stats report object/field thay đổi** so với lần trước (so sánh từng object theo id; field không đổi bị bỏ; có thể làm tròn timestamp). Importer phải **tái dựng đầy đủ** bằng cách carry-forward (giữ trạng thái cuối của mỗi `statsId`, merge delta mới vào). Quên bước này sẽ làm mất field (RTT, state) ở các mẫu sau.
- Khuyến nghị: viết `ParsedStatsReport` trung gian = bảng long `(call_id, pc_id, ts, stats_id, type, field, value)` cho cả hai định dạng, sau đó mới sang canonical wide. Có thể dùng `dump-importer` để đối chiếu kết quả (oracle test).
- TODO verify: đọc source `rtcstats/rtcstats` (`packages/dump-importer`, `packages/rtcstats-js`) để xác nhận cấu trúc message và logic delta.

---

## 2. Spec W3C webrtc-stats: trường cần dùng

Nguồn gốc: [V] một phần (bảng đơn vị bên dưới đã xác nhận cho các hàng đánh dấu V).

| Raw stat (type.field) | Canonical field | Đơn vị raw | Đơn vị canonical | Ghi chú |
|---|---|---|---|---|
| candidate-pair.currentRoundTripTime [K] | `net_rtt_ms` | giây | ms | RTT STUN gần nhất trên pair; nguồn RTT chính, có kể cả khi không media |
| candidate-pair.totalRoundTripTime + responsesReceived [K] | `net_rtt_avg_ms` | giây, count | ms | mean = total/responses (delta giữa 2 mẫu = RTT trung bình cửa sổ) |
| candidate-pair.availableOutgoingBitrate [K] | `bwe_out_bps` | bit/s | bit/s | ước lượng BWE của sender; có thể vắng |
| candidate-pair.availableIncomingBitrate [K] | `bwe_in_bps` | bit/s | bit/s | thường vắng |
| candidate-pair.bytesSent/bytesReceived [K] | `pair_bytes_tx/rx` | byte (counter) | byte, rate bit/s | cumulative |
| candidate-pair.state / nominated / selected [K] | `pair_state`, `pair_nominated` | enum / bool | - | `state` in frozen, waiting, in-progress, failed, succeeded |
| candidate-pair.requestsSent/responsesReceived/consentRequestsSent [K] | `stun_req`, `stun_resp` | count | count | tỷ lệ mất STUN = 1 - resp/req |
| transport.selectedCandidatePairId [V] | `selected_pair_id` | ID | - | **nguồn chính** xác định pair đang dùng; đổi theo thời gian |
| transport.dtlsState, iceState, iceRole, dtlsCipher [K] | `dtls_state`, `ice_state` | enum | - | |
| (cũ) candidate-pair.selected / googActiveConnection [K] | fallback cho Chrome cũ | bool | - | dùng khi không có `transport` |
| local-candidate.candidateType [V] | `local_cand_type` | enum host/srflx/prflx/relay | - | |
| local-candidate.relayProtocol [V] | `relay_protocol` | enum udp/tcp/tls | - | chỉ có ở **local** relay candidate; = giao thức tới TURN (khác `protocol` là giao thức của candidate) |
| local-candidate.url [V] | `turn_url` | string | - | URL ICE server (`turn:host:port?transport=`) sinh candidate; chỉ local srflx/relay; **không có ở remote** |
| local-candidate.address / ip, port [V] | `local_cand_addr` | string | - | `address` nullable; relay local address = địa chỉ relay trên TURN server (relayed transport address) |
| remote-candidate.candidateType, address, port, protocol [V/K] | `remote_cand_type`, `remote_addr` | - | - | address có thể null/mDNS (`xxx.local`) |
| local/remote-candidate.networkType [K] | `net_type` | enum wifi/cellular/ethernet | - | chỉ local (Chrome) |
| inbound-rtp.jitter [V] | `rx_jitter_ms` | **giây** | ms (x1000) | RFC 3550, tính trong đơn vị clock rate -> giây |
| inbound-rtp.packetsLost [V] | `rx_pkts_lost_cum` | packets (counter, **có thể âm**) | packets | clamp delta >= 0 khi tính rate |
| inbound-rtp.packetsReceived [K] | `rx_pkts_cum` | packets | packets | |
| inbound-rtp.bytesReceived [K] | `rx_bytes_cum` | byte | bit/s sau diff | |
| inbound-rtp.jitterBufferDelay + jitterBufferEmittedCount [V/K] | `rx_jb_delay_ms` | giây, count | ms | mean = Δdelay / Δemitted |
| inbound-rtp.concealedSamples / totalSamplesReceived [K] | `rx_concealed_ratio` | samples | ratio | audio quality proxy |
| inbound-rtp.framesDecoded/framesDropped/framesPerSecond/freezeCount/totalFreezesDuration [K] | `rx_fps`, `freeze_cnt`, `freeze_ms` | - / giây | ms | video |
| inbound-rtp.frameWidth/Height [K] | `rx_res_h` | px | px | |
| remote-inbound-rtp.roundTripTime [V] | `rtp_rtt_ms` | giây | ms | từ RTCP RR; vắng đến khi có RR với DLSR != 0 -> NaN hợp lệ, không phải 0 |
| remote-inbound-rtp.fractionLost [V] | `tx_loss_frac` | fraction 0..1 | ratio (và %) | loss phía sender-view theo RR (interval giữa 2 RR). Chú ý: một số impl dùng thang 0..255 (aiortc/RTCP raw) -> verify |
| remote-inbound-rtp.packetsLost, jitter [K] | `tx_remote_lost_cum`, `tx_remote_jitter_ms` | packets, giây | - | |
| outbound-rtp.bytesSent/packetsSent [K] | `tx_bytes_cum` | byte | bit/s | |
| outbound-rtp.targetBitrate [V] | `tx_target_bps` | bit/s | bit/s | encoder target |
| outbound-rtp.qualityLimitationReason / qualityLimitationDurations [K] | `tx_qlimit` | enum none/cpu/bandwidth/other | - | tách lỗi CPU khỏi lỗi mạng |
| outbound-rtp.retransmittedPacketsSent, nackCount, pliCount [K] | `tx_nack`, `tx_pli` | count | count | |
| media-source.audioLevel [K] | `tx_audio_level` | 0..1 | - | phát hiện im lặng/no-audio |
| stats.timestamp [K] | `ts_ms` | DOMHighResTimeStamp ms | epoch ms | trong Chrome thường là epoch ms; trong webrtc-internals dump bị mất -> dùng startTime/endTime |

### 2.1 Khác biệt aiortc/simulator [K, cần verify trên version đang dùng]

- aiortc `getStats()` trả `RTCInboundRtpStreamStats` với `jitter` **tính theo đơn vị clock RTP (samples/ticks)**, không phải giây như spec -> với audio 48 kHz, `jitter_s = jitter / clock_rate` (ở một số bản đã chia sẵn; phải kiểm tra bằng cách so với jitter đã biết). `packetsLost` ok; `roundTripTime` có trong remote-inbound-rtp. aiortc thiếu nhiều field (candidate-pair stats, transport.selectedCandidatePairId, jitterBufferDelay, totalRoundTripTime...).
- Quy ước: mỗi nguồn có `source_profile` (chrome_webrtc_internals | rtcstats_chrome | aiortc | simulator | prod_sdk) với bảng `unit_scale` riêng; chuẩn hóa ở tầng **clean**, tầng feature chỉ thấy đơn vị canonical (ms, bit/s, ratio 0..1).
- Simulator nên phát cùng schema canonical để tránh phân kỳ; nhưng cũng nên có một chế độ "emit raw W3C" để test adapter.

---

## 3. Preprocessing checklist

| # | Bước | Pitfall | Quy tắc đề xuất |
|---|---|---|---|
| 1 | Dedupe file/dump | Cùng call bị upload 2 lần; dump webrtc-internals export lặp; cùng PC nhiều file | Key = hash(nội dung chuẩn hóa) + (user, startTime, pc_id); giữ bản dài hơn/đầy đủ hơn, log số bản loại |
| 2 | Parse an toàn | `values` là chuỗi JSON lồng; file hỏng/cắt ngang; encoding BOM | try/except từng PC; ghi `parse_status`, `n_pc_ok`; không bỏ cả file vì 1 PC lỗi |
| 3 | Dựng timeline | webrtc-internals không có ts từng điểm; rtcstats delta cần carry-forward | Nội suy ts từ start/end và số mẫu; rtcstats: merge delta theo statsId; lưu `ts_source` (native/interpolated) |
| 4 | Clock skew | Client clock sai; getStats timestamp vs server receive time; múi giờ | Dùng thời gian tương đối từ `t0` của call cho feature; epoch chỉ để join; nếu có server ts, ước lượng offset = median(server - client); cờ `clock_suspect` nếu offset > 5 s hoặc ts đi lùi |
| 5 | Sắp xếp & trùng ts | ts không đơn điệu, 2 mẫu cùng ts | sort theo ts; loại mẫu trùng (giữ mẫu cuối); khoảng cách mẫu `dt` <= 0 -> bỏ |
| 6 | Chuẩn hóa đơn vị | jitter giây vs ms vs ticks; RTT giây; fractionLost 0..1 vs 0..255 | Bảng `unit_scale` theo source_profile; assert range sau chuẩn hóa (RTT 0..10 000 ms, jitter 0..5 000 ms, loss 0..1) |
| 7 | Counter -> rate | Cumulative bytes/packets: dùng giá trị thô sẽ sai | `rate = (c_t - c_{t-1}) / (ts_t - ts_{t-1})`; bit/s = 8*Δbytes/Δt; loss_ratio_window = Δlost / (Δlost + Δrecv) (chia 0 -> NaN) |
| 8 | Counter reset / wrap | Counter về 0 sau ICE restart, track replace, SSRC đổi; packetsLost âm | Nếu Δ < 0 -> coi là reset: bỏ mẫu rate đó (hoặc dùng giá trị mới làm Δ khởi đầu), `reset_flag=1`; clamp packetsLost âm Δ về 0; không cộng dồn qua reset |
| 9 | Stat ID đổi | Sau ICE restart/renegotiation, candidate-pair/transport/ssrc có ID mới; tên Chrome `RTCIceCandidatePair_xxx` đổi | Không dùng ID làm khóa lâu dài. Khóa logic: `(pc_id, type, kind, ssrc)` cho rtp; cho pair dùng `(local_cand_key, remote_cand_key)` với `cand_key=(type,address,port,protocol)`. Tạo `leg_id` tăng mỗi lần transport/selected pair đổi |
| 10 | Selected pair switch | Pair được chọn đổi giữa chừng (relay A -> relay B, host -> relay); chọn pair bằng `state=succeeded` sai vì nhiều pair succeeded | Mỗi mẫu: `sel = transport.selectedCandidatePairId` (fallback: pair `nominated && state==succeeded` có bytesSent lớn nhất/`googActiveConnection`). Tạo `segment_id` mỗi lần `sel` đổi; tính feature cả per-call và per-segment; đếm `n_pair_switch` |
| 11 | Xác định TURN server thực dùng | `url` chỉ có ở local candidate; remote relay không có url; relay address có thể là IP khác hostname | Từ selected pair: `local_cand = candidates[pair.localCandidateId]`. Nếu `local.type=='relay'` -> TURN phía local = `local.url` (host:port, transport) + `local.address:port` (relayed address) + `relayProtocol`. Nếu `remote.type=='relay'` -> TURN phía remote (chỉ có address). Join `url`/IP với bảng `turn_server_registry` (hostname, IP, region). Nếu pair không relay -> `turn_used=false` (đường P2P, rất quan trọng cho nhãn). Nếu có nhiều relay candidate (nhiều url) mà chưa chọn -> ghi cả danh sách `gathered_relays` để so sánh với "chọn". Chú ý Chrome có thể ẩn `url` trên candidate đã gather qua mDNS/redacted |
| 12 | Thiếu mẫu / gap | getStats bị throttling (tab nền), mạng tắc, mẫu thưa >1 s | Với gap > 3x median dt: không nội suy qua gap; đánh `gap_flag`, cắt segment; rate chỉ tính khi dt trong [0.5, 5] s (hoặc 3x poll interval) |
| 13 | Thiếu field (NaN) | RTT vắng, remote-inbound-rtp chưa có, candidate-pair thiếu ở aiortc | Phân biệt "missing" vs 0: giữ NaN + cột `*_valid`; không fillna 0; imputation chỉ ở tầng model, không ở clean |
| 14 | Call không có media | Chỉ data channel; chỉ ICE rồi hủy; track muted; bytes = 0 | `has_audio_rx`, `has_video_rx`, `media_seconds`. Đặt `is_scoreable = media_seconds >= 10` (ngưỡng cấu hình); call không media vẫn giữ cho KPI setup/ICE nhưng loại khỏi MOS |
| 15 | Nhiều PC / nhiều stream trong 1 file | Chrome dump gồm nhiều PC (kể cả PC thăm dò, thiết bị, screen share) | `call` = nhóm PC theo thời gian + url; mỗi PC=1 leg; chọn PC chính (media_seconds lớn nhất) cho điểm chất lượng; cờ `n_pc` |
| 16 | Outlier | RTT 0 hoặc quá lớn, jitter khổng lồ lúc bắt đầu, bitrate spike do ts gần nhau | winsorize 0.1-99.9% khi dựng feature (không ở clean); giữ giá trị gốc ở clean; loại `dt < 0.2 s` |
| 17 | Bỏ khởi động/kết thúc | 2-3 mẫu đầu nhiễu (BWE chưa hội tụ), mẫu cuối khi đóng | Tùy chọn `warmup_s=5`, `cooldown_s=2` tham số hóa; feature "steady-state" tính sau warmup, feature "startup" tính riêng |
| 18 | Hướng (tx vs rx) | Nhầm RTT hai chiều, loss send-side vs recv-side | Đặt tên rõ: `rx_*` từ inbound-rtp (chất lượng nhận của chính client), `tx_*_remote` từ remote-inbound-rtp (chất lượng bên kia thấy) |
| 19 | Anonymization/PII | IP, user agent trong dump | Hash IP (HMAC có muối), chỉ giữ ASN/prefix/country; giữ IP TURN server (không phải PII) |
| 20 | Split train/test | Rò rỉ khi cùng call/cùng user nằm ở nhiều fold | Split theo `call_id`/`user_id` (group k-fold); với WebRTC-QoE split theo `User` (và theo TC) |
| 21 | Lineage & idempotent | Chạy lại pipeline tạo bản sao | raw bất biến, clean có `source_file_hash`, `parser_version`; ghi quality report mỗi lô (số file/PC, % NaN, % reset, %gap) |

---

## 4. Feature engineering - tham chiếu thực hành

### 4.1 rtcstats-features / Jitsi rtcstats [V một phần]
- [V] Server trích "feature set" (số lượng PC, thời gian WebSocket connect...), đẩy vào DB; dump nằm ở S3. `features-client.js` (fork cũ) chia 3 loại feature: chỉ cần client, cần client + connection, và theo track. Ví dụ `websocketConnectionTime`, `numberOfPeerConnections`, `userfeedback`.
- [K] Các feature kết nối điển hình trong rtcstats-features: thời gian từ `create` tới `connected` (`connectionTime`/`iceConnectionTime`), số lần ICE restart, `iceConnectionState` cuối, loại candidate được chọn (`selectedLocal/RemoteCandidateType`), `relayType`/`turn`, throughput trung bình/max, RTT/jitter/loss trung bình theo stream, số candidate theo type, thời gian gather.
- Mẫu thiết kế nên bắt chước: feature = hàm (client | connection | track) -> giá trị, đăng ký theo registry; chạy offline từ dump.

### 4.2 noise-lab/vcaml [V]
- [V] Features theo **cửa sổ**: **LSTATS** (thống kê độ dài gói: mean, std, min, max, Q1/Q2/Q3, count, total bytes, unique sizes), **TSTATS** (thống kê inter-arrival time: mean, std, min, max, Q1/Q2/Q3, burst count), **SIZE/IAT** (vector thô cố định chiều, pad/truncate), và RTP-specific (`rtp-ml`: buffer time, unique RTP timestamps, out-of-order count, RTP lag).
- [V] Nhãn từ webrtc-internals: `framesReceivedPerSecond`, `bitrate` inbound video, `frame_jitter` (std của inter-frame delay, ms), `frameHeight`. Đánh giá bằng MAE và accuracy trong ±2 fps; `frameHeight` bằng accuracy phân loại.
- [V] `FileProcessor` ghép CSV network trace với WebRTC JSON; **FileValidator** lọc trace bất thường trước khi train; **KfoldCVOverFiles** (k=5) chia fold theo file (tránh rò rỉ giữa các cửa sổ cùng file). Tiêu chí lọc và độ dài cửa sổ không được nêu trên README -> đọc code `config.yaml`/validator.
- Bài học cho ta: (1) cửa sổ cố định (vd 1 s) căn theo `getStats` poll; (2) đánh giá group-k-fold theo file/call; (3) có bước validator tách riêng (tương ứng bước 12-14 checklist).

### 4.3 Nhà cung cấp [K, từ tài liệu công khai; chưa fetch lại, cần verify]
- **callstats.io** (nay thuộc Spearline/đóng): chuẩn hóa theo "conference/user/PC"; metric: E2E RTT, jitter, loss, bitrate, fps, resolution; **MOS audio/video** ước lượng, "ICE connectivity", "setup time", "ICE disruption/restart". 
- **Jitsi** (jitsi-meet `ConnectionQuality`): điểm 0-100 từ bitrate, loss, fps, resolution; Jibri/rtcstats lưu `rtcstats` cho phân tích hậu kiểm.
- **Twilio Voice Insights**: per-call `mos` (1-5), `jitter`, `packet_loss`, `rtt`, tag cảnh báo (high-latency, high-jitter, high-packet-loss, low-mos, ice-connectivity-lost, constant-audio-input...). Tính MOS dựa E-model đơn giản hóa từ latency, jitter, loss.
- **Daily**: network quality `good/low/very-low` theo ngưỡng packet loss + bitrate (ước lượng), `getNetworkStats` có `threshold`, `quality` (0-100), `networkState`.
- **LiveKit**: `ConnectionQuality` {excellent, good, poor, lost} dựa MOS-like score tính ở server từ loss, RTT, jitter và (cho video) bitrate/fps/resolution so với kỳ vọng; có MOS 1-4.5 trong analytics (`quality` + `score`).
- Pattern chung: (a) metric thô p50/p95 theo call, (b) điểm tổng hợp MOS/quality score, (c) cờ sự kiện (ICE fail, disconnect), (d) phân loại theo người dùng/ISP/region/relay.

---

## 5. Feature catalog

Quy ước: cửa sổ cơ sở `W = 1 s` (theo poll), cửa sổ tổng hợp `T = 5 s / 10 s` trượt; thống kê `{mean, p50, p95, max, std}`; hậu tố `_w` = trong window, `_c` = per call.

### 5.1 Per-call (một dòng / call; mart `fct_call`)
| Nhóm | Feature |
|---|---|
| Định danh | `call_id`, `source_profile`, `client_os/browser`, `network_type`, `duration_s`, `media_seconds`, `n_pc`, `ts_source`, `clock_suspect` |
| Setup | `call_setup_time_ms`, `time_to_first_media_ms`, `ice_gather_ms`, `ice_connect_ms`, `dtls_ms`, `n_ice_restart`, `ice_final_state`, `n_ice_fail`, `end_reason` |
| Path | `turn_used`, `selected_local_type`, `selected_remote_type`, `relay_protocol`, `turn_server_id/region`, `n_relay_candidates_gathered`, `n_pair_switch`, `time_on_relay_ratio` |
| Network | RTT: `net_rtt_ms_{mean,p50,p95,max}`; jitter `rx_jitter_ms_*`; `loss_ratio_c = ΣΔlost/(ΣΔlost+ΣΔrecv)`; `loss_burst_max` (số mẫu liên tiếp loss > 5%); `bwe_out_bps_{mean,p10}` |
| Media | audio: `rx_audio_bps_mean`, `concealed_ratio`, `jb_delay_ms_mean`; video: `rx_fps_{mean,p10}`, `rx_res_h_mode`, `freeze_cnt`, `freeze_ratio`, `qlimit_bandwidth_ratio`, `qlimit_cpu_ratio`, `nack_rate`, `pli_cnt` |
| Quality | `mos_e_model_{mean,p10,min}`, `r_factor_*`, `pct_time_mos_lt_3`, `pct_time_degraded` |
| Chất lượng dữ liệu | `pct_missing_rtt`, `pct_gap`, `n_reset`, `is_scoreable` |
| Label (QoE dataset) | `acr_score`, `impair_delay_ms`, `impair_jitter_ms`, `impair_loss_pct` |

### 5.2 Per-leg (một dòng / PC hoặc / segment selected-pair; `fct_leg`)
`leg_id`, `segment_id`, `t_start/t_end`, `pair_local_type/remote_type`, `relay_protocol`, `turn_url`, `turn_ip`, `net_rtt_ms_*`, `stun_loss = 1 - Δresp/Δreq`, `consent_fail`, `bytes_tx/rx`, `switch_reason` (inferred: ice_restart | better_pair | failure), `dir` (tx vs rx).

### 5.3 Per-TURN-window (`fct_turn_window`: khóa `turn_server_id x window_start`; window 1 phút / 5 phút)
Phục vụ TURN selector:
- Tải & mức dùng: `n_active_calls`, `n_new_allocations`, `bytes_relayed`, `bitrate_relayed_bps`.
- Chất lượng: `rtt_p50/p95`, `jitter_p95`, `loss_ratio`, `mos_p10`, `pct_calls_mos_lt_3`.
- Độ tin cậy: `ice_success_rate` (cho cặp client-region x TURN), `setup_time_p50/p95`, `drop_rate`, `n_switch_away`.
- Phân tầng: theo `client_region/ASN`, `relay_protocol` (udp/tcp/tls), `turn_region`.
- Chống bias: chỉ ghi nhận stats của TURN được chọn (selection bias) -> lưu `gathered_relays` và `chosen` để dùng IPS/bandit sau này; thêm cột `n_calls` để áp ngưỡng tối thiểu (vd >= 30) trước khi dùng p95.

### 5.4 Cửa sổ ML (kiểu VCAML)
Với mỗi `(call_id, window)`: LSTATS/TSTATS (nếu có packet trace), cộng RTT/jitter/loss/bitrate lag 1..k; nhãn: MOS/`acr_score`, hoặc `degraded_next_10s`. Chia fold theo `call_id`/`user`.

---

## 6. E-model (ITU-T G.107) - công thức đơn giản hóa

Dạng đầy đủ: `R = Ro - Is - Id - Ie_eff + A`. Với call VoIP có default G.107: `Ro - Is ≈ 93.2` (công thức Cole & Rosenbluth đã giản lược: `R = 93.2 - Id - Ie_eff`).

**Delay (Id)**, một chiều `d` (ms) = `d_net + d_jitterbuffer + d_codec(+ d_processing)`; xấp xỉ one-way = RTT/2 + jb_delay + codec_delay (~20-40 ms audio packetization/lookahead; cấu hình):
```
Id = 0.024*d + 0.11*(d - 177.3)*H(d - 177.3)        # H = Heaviside (1 nếu d>177.3 else 0)
```
(Cole & Rosenbluth 2001). [K]

**Loss (Ie_eff)** theo G.107:
```
Ie_eff = Ie + (95 - Ie) * Ppl / (Ppl/BurstR + Bpl)
```
với `Ppl` = tỷ lệ mất gói (%), `Bpl` = packet-loss robustness (Opus/G.711 w/ PLC: G.711 Bpl≈25.1, G.729 ≈19; Opus chưa được liệt kê chuẩn trong G.107 -> dùng Ie≈0, Bpl≈10-20 làm giá trị cấu hình và hiệu chỉnh bằng dữ liệu), `BurstR` = 1 nếu mất ngẫu nhiên, >1 khi mất cụm (ước lượng từ `loss_burst`). [V xác nhận công thức Ie_eff, và R->MOS ở dưới]

Quy đổi Jitter: dùng jitter buffer, cộng vào d: `d_jb ≈ jitterBufferDelay_mean` nếu có, nếu không `≈ 2*jitter`. Loss hiệu dụng = `loss_net + late_loss` (ước lượng `Δconcealed/Δsamples` cho audio nếu có).

**R -> MOS** (G.107): [V]
```
R < 0            : MOS = 1
0 <= R <= 100    : MOS = 1 + 0.035*R + R*(R - 60)*(100 - R)*7e-6
R > 100          : MOS = 4.5
```
Triển khai: clamp MOS ∈ [1, 4.5]; tính theo từng mẫu `W=1 s`, rồi mean/p10/min per call.

Caveat:
- E-model thiết kế cho **audio hội thoại**; video không có công thức G.107 tương đương -> dùng điểm riêng (G.1070 hoặc heuristic fps/res/freeze) và nhãn riêng.
- Miền hợp lệ one-way delay <= ~400 ms, loss <= ~20%; ngoài miền chỉ dùng như chỉ số tương đối (nhớ với WebRTC-QoE TC có delay 500/1000 ms, loss 15/30%).
- Ghi rõ tham số (`Ie`, `Bpl`, `codec_delay`) trong config và version hóa `mos_formula_version`.
- Hiệu chuẩn: hồi quy/monotonic mapping (isotonic) từ `mos_e_model` sang `acr_score` trên WebRTC-QoE để kiểm tra độ lệch.

---

## 7. Định nghĩa KPI

Không có chuẩn thống nhất; dưới đây là định nghĩa **đề xuất của dự án** (dựa trên các mốc sự kiện trong W3C/Chrome `updateLog`, rtcstats). [K] cho cách nhà cung cấp dùng thuật ngữ.

| KPI | Định nghĩa đề xuất | Mốc sự kiện |
|---|---|---|
| **Call Setup Time (CST)** | `t(connectionState==connected hoặc iceConnectionState in {connected,completed}) - t(setLocalDescription offer đầu tiên / create PC)`. Biến thể `signaling_to_connected` khi có timestamp signaling | `updateLog` / rtcstats events. Báo cáo p50/p95; loại call fail khỏi CST nhưng tính vào success |
| **Time To First Media (TTFM)** | `t(first sample với inbound-rtp.packetsReceived>0 hoặc framesDecoded>0) - t(call start)`; còn chia audio/video. Dùng `t(first bytesReceived>0)` nếu chưa decode | Từ stats time series; độ phân giải ~ poll 1 s -> ghi `ttfm_resolution_ms` |
| **ICE gathering time** | `t(iceGatheringState=complete hoặc candidate relay đầu) - t(setLocal)` | |
| **ICE connection success** | `calls có ice state đạt connected/completed / calls cố gắng kết nối`; mẫu số loại call bị hủy trước khi có remote answer (cờ `abandoned`). Chia theo candidate type (host/srflx/relay) và `relay_protocol` | `ice_final_state`, `n_ice_fail` |
| **ICE restart rate** | `calls có >=1 ICE restart / calls` | |
| **Drop rate** (call drop) | `calls kết thúc bất thường / calls đã connected`: bất thường = `iceConnectionState` vào `failed`/`disconnected` > N giây rồi call kết thúc, hoặc không có media > X giây trước khi hangup, hoặc end_reason lỗi. Cần định rõ ngưỡng `disconnect_grace_s` (vd 10 s) và loại hangup bình thường | |
| **Media drop / freeze rate** | `thời gian freeze / media_seconds` | `freezeCount`, `totalFreezesDuration` |
| **Poor call rate** | `calls có MOS_p10 < 3 hoặc pct_time_mos_lt_3 > 20%` | |
| **TURN usage rate** | `calls với selected pair có relay / calls connected`; thường dùng để tính chi phí TURN | |

Ghi chú: các bên (Twilio, callstats...) có định nghĩa riêng; cần ghi KPI definition + version cạnh mỗi báo cáo để so sánh.

---

## 8. Việc cần verify tiếp (open items)

1. Đọc source `rtcstats/rtcstats` (`dump-importer`, `rtcstats-js`, `rtcstats-features`) xác nhận format message và logic delta/feature (README không mô tả).
2. Mở 3-5 file mẫu WebRTC-QoE: kiểm tra có `candidate-pair`/`transport`/`local-candidate` không, loại candidate (khả năng là host/srflx), version Chrome, độ dài `values`, field nào thiếu.
3. Kiểm tra aiortc version đang dùng: đơn vị `jitter`, có `candidate-pair`, `remote-inbound-rtp.fractionLost` thang nào.
4. Đọc phần còn lại của W3C spec (candidate-pair, ~12.5k ký tự cuối chưa đọc trong lần fetch) để xác nhận `currentRoundTripTime`, `availableOutgoingBitrate` (đơn vị giây / bit/s).
5. Lấy lại tài liệu callstats/Twilio/Daily/LiveKit để chốt các ngưỡng cảnh báo.

---

## 9. Nguồn

- W3C WebRTC Statistics API: https://www.w3.org/TR/webrtc-stats/ (nội dung đọc qua https://w3c.github.io/webrtc-stats/)
- W3C WebRTC 1.0: https://www.w3.org/TR/webrtc/
- RFC 3550 (RTP, jitter, fraction lost, RTT từ RR): https://www.rfc-editor.org/rfc/rfc3550
- rtcstats monorepo: https://github.com/rtcstats/rtcstats
- rtcstats.js (legacy): https://github.com/rtcstats/rtcstats-js
- webrtc-dump-importer: https://github.com/fippo/webrtc-dump-importer
- rtcstats-server fork (features-client.js): https://github.com/thepatrick/rtcstats-server/blob/master/features-client.js
- Jitsi rtcstats client: https://npmjs.com/package/%40jitsi%2Frtcstats
- noise-lab/vcaml: https://github.com/noise-lab/vcaml
- WebRTC-QoE dataset (Zenodo 15836614, DOI 10.21227/mb47-hf44): https://zenodo.org/records/15836614
- ITU-T G.107 E-model: https://www.itu.int/dms_pubrec/itu-t/rec/g/T-REC-G.107-200503-S!!TOC-HTM-E.htm ; tutorial: https://www.itu.int/ITU-T/2005-2008/com12/emodelv1/tut.htm
- Cole & Rosenbluth, "Voice over IP performance monitoring", ACM SIGCOMM CCR 31(2), 2001: https://typeset.io/papers/voice-over-ip-performance-monitoring-4pf9ftlj0g
- fippo / bloggeek series "Everything you wanted to know about webrtc-internals and getStats": https://bloggeek.me
- Twilio Voice Insights: https://www.twilio.com/docs/voice/voice-insights
- LiveKit connection quality: https://docs.livekit.io/
- Daily network stats: https://docs.daily.co/
- callstats.io (legacy docs): https://www.callstats.io
