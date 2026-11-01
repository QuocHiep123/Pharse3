# Pharse3 — callops PoC

Mô phỏng **full luồng cuộc gọi WebRTC** + **QoS/QoE metrics** + **chẩn đoán AIOps tách bạch FACT vs INFERENCE**,
có log chi tiết từng bước để hiểu hệ thống hoạt động thế nào.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env
docker compose up -d --wait        # Redis + OpenSearch (tùy chọn; không có thì tự fallback in-memory)
# docker compose --profile ui up -d  # thêm OpenSearch Dashboards tại http://localhost:5601
```

## Chạy

```powershell
.venv\Scripts\callops list                      # các kịch bản
.venv\Scripts\callops check-env                 # kiểm tra Redis/OpenSearch
.venv\Scripts\callops run congestion            # 1 kịch bản, log DEBUG đầy đủ
.venv\Scripts\callops --log-level INFO run-all  # tất cả, gọn hơn + bảng tổng kết
.venv\Scripts\callops --backend memory run-all  # không cần Docker
.venv\Scripts\python -m pytest                  # unit + e2e test
```

Đầu ra:
- Console: log từng STEP, chuyển trạng thái, ICE check, metric mỗi giây, rule AIOps khớp/không khớp.
- `logs/run-*.jsonl`: log máy đọc (mỗi dòng 1 JSON) — đây là "log gốc".
- `reports/<call_id>.json`: báo cáo chẩn đoán (FACT + INFERENCE).
- Redis `HGETALL call:<call_id>`: trạng thái live của cuộc gọi.
- OpenSearch index `callops-events`, `callops-qos`: `curl "localhost:9200/callops-events/_search?q=error_code:ICE_FAILED&pretty"`.

## Demo UI (Gradio)

```powershell
.venv\Scripts\pip install -e ".[dev,ui]"
.venv\Scripts\callops ui --port 7860     # mở http://127.0.0.1:7860, không cần Docker/LLM
```

6 tab: Run / Playground (chọn/sửa kịch bản), Call Flow (sơ đồ từng bước có animation), QoS Timeline (chart + ngưỡng + vùng sự cố),
Diagnosis (FACT ↔ INFERENCE, rule khớp/không khớp), Logs / Export, Upload / Re-analyze. Thanh thời gian + Play đặt trên các tab;
bật sẵn chế độ "Giải thích cho người mới".

## WebRTC Lab

Trang web dùng `RTCPeerConnection` thật của trình duyệt (chỉ stdlib, không cần extra) để xem từng bước hai bên gọi nhau và xuất log/metric.

```powershell
.venv\Scripts\callops lab            # http://127.0.0.1:8765  (hai tab: ?role=alice và ?role=bob)
```

- Chế độ "Một trang" (Alice + Bob trong cùng trang) hoặc "Hai tab"; bật "Từng bước" để dừng sau mỗi giai đoạn (INVITE, SDP, ICE, DTLS...).
- Media thật (camera + mic, cần `localhost`/`127.0.0.1`) hoặc giả lập; bị từ chối/không có thiết bị thì tự rơi về giả lập. Âm thanh bên kia mặc định tắt để tránh hú; hình/tiếng không rời trình duyệt, file xuất chỉ chứa metric/log.
- Tạo sự cố thật: Chrome DevTools > Network throttling (chỉ ảnh hưởng một số luồng), **clumsy** trên Windows (lag/drop/throttle), hoặc `sudo tc qdisc add dev lo root netem delay 200ms loss 5%` trên Linux.
- Bấm "Tải events.jsonl" + "Tải qos.csv", rồi `callops ui` > tab **Upload / Re-analyze** > chọn 2 file > "Phân tích lại".

## Luồng hoạt động

```
STEP 1 CALL SETUP        INVITE / JOIN_ROOM qua signaling        state: IDLE -> SETUP
STEP 2 SDP OFFER/ANSWER  createOffer / setRemoteDescription      -> OFFER_SENT -> ANSWER_RECEIVED
STEP 3 ICE GATHERING     host (IP LAN) | srflx (STUN) | relay (TURN)
STEP 4 ICE CHECKS        thử từng cặp candidate theo priority    -> ICE_CHECKING
                          host<->host  : chỉ khi cùng LAN               => P2P_HOST
                          srflx<->srflx: hỏng nếu NAT đối xứng          => P2P_STUN
                          *<->relay    : luôn đi được nếu có TURN       => TURN_RELAY
                          >2 người     : mỗi người nối tới SFU           => SFU
                          không cặp nào được                           => ICE_FAILED -> FAILED
STEP 5 MEDIA             DTLS-SRTP, đo QoS mỗi giây/participant  -> CONNECTED
                          vượt ngưỡng -> log QOS_ALERT, hết -> QOS_RECOVERED
STEP 6 TERMINATION       BYE                                     -> TERMINATED
STEP 7 AIOps             đọc lại log + metric từ store -> FACT -> rule -> INFERENCE -> report
```

Mọi bước đều đi qua `CallSimulator._emit()`: ghi log (console + JSONL), index vào OpenSearch, cập nhật Redis.
AIOps **không** đọc biến trong bộ nhớ của simulator mà truy vấn lại store — giống hệ thống thật.

## QoS metrics & ngưỡng (`src/callops/qos.py`)

| Metric | Warning | Critical | Ý nghĩa |
|---|---|---|---|
| RTT | ≥300ms | ≥500ms | độ trễ khứ hồi (G.114: one-way <150ms) |
| Jitter | ≥30ms | ≥50ms | biến thiên trễ giữa các gói |
| Packet loss | ≥1% | ≥5% | tỉ lệ mất gói |
| MOS | ≤3.6 | ≤3.1 | điểm thoại 1.0–4.5 (E-model) |
| Concealment | ≥5% | ≥10% | % audio bị PLC "bịa" lại |

MOS tính theo **ITU-T G.107 E-model rút gọn**: `R = 93.2 − Id(delay) − Ie_eff(loss)`, rồi `MOS = 1 + 0.035R + 7e-6·R(R−60)(100−R)`.

## FACT vs INFERENCE (`src/callops/diagnosis.py`)

- **FACT** = thứ có thật trong dữ liệu: có `ts`, `evidence` (dòng log JSON gốc hoặc sample metric gốc), `error_code`.
  3 loại: sự kiện log quan trọng, đoạn metric vượt ngưỡng (gộp các mẫu liên tiếp), số liệu tổng hợp/participant.
- **INFERENCE** = giả thuyết do rule suy ra; **bắt buộc** `derived_from` ≥1 FACT id + `reasoning` + `confidence`.
  `DiagnosisReport` có validator từ chối INFERENCE trích FACT không tồn tại.

| Rule | Điều kiện trên FACT | Kết luận |
|---|---|---|
| ice_failure_root_cause | ICE_FAILED + participant không có relay (+ STUN_TIMEOUT / NAT đối xứng) | thiếu TURN |
| turn_fallback_explained | TURN_FALLBACK + NAT SYMMETRIC/UDP_BLOCKED | relay là đúng thiết kế |
| congestion_vs_random_loss | loss trùng thời gian với jitter/RTT ↑ → nghẽn; loss đơn lẻ → mất gói vô tuyến | |
| latency_only | RTT ↑ nhưng không loss | đường đi/relay xa |
| qoe_impact | MOS/concealment vượt ngưỡng | người dùng cảm nhận được |
| sfu_isolated_participant | gọi SFU, chỉ 1 phần người critical | lỗi last-mile, không phải SFU |
| healthy_call | không có vi phạm, không lỗi | cuộc gọi khỏe |

## Kịch bản (`src/callops/scenarios.py`)

| Tên | Mô tả | Kỳ vọng |
|---|---|---|
| p2p_good | NAT cone, mạng tốt | P2P_STUN, OK |
| same_lan | cùng LAN | P2P_HOST, OK |
| symmetric_nat_turn | caller sau NAT đối xứng | TURN_RELAY, OK |
| ice_failed_no_turn | firewall chặn UDP + không có TURN | FAILED, CRITICAL |
| congestion | bob nghẽn uplink t=10–20s | CRITICAL, nghẽn mạng |
| wifi_loss | mất gói ~3% không kèm jitter | WARNING, mất gói vô tuyến |
| group_sfu | 4 người qua SFU, dave mạng kém | CRITICAL, lỗi last-mile của dave |

Thêm kịch bản mới: thêm 1 `Scenario(...)` vào `SCENARIOS` (đổi NAT, network, `impairments`, `turn_available`).

## Cấu trúc

```
src/callops/
  models.py        Pydantic models: CallState, IceCandidate, QoSSample, Fact, Inference, DiagnosisReport
  scenarios.py     các kịch bản test
  simulator.py     state machine cuộc gọi: setup -> SDP -> ICE -> media -> BYE
  qos.py           ngưỡng, E-model MOS, sinh metric
  storage.py       Redis + OpenSearch / in-memory fallback
  diagnosis.py     FactExtractor + InferenceEngine + DiagnosisService
  logging_setup.py console log dễ đọc + JSONL
  cli.py           entrypoint `callops`
tests/             pytest
```

> Đây là mô phỏng (không có media thật/WebRTC stack thật); hành vi NAT và metric được đơn giản hóa để minh họa.
