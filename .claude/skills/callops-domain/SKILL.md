---
name: callops-domain
description: WebRTC call platform domain knowledge for the callops project - call flow (setup, SDP offer/answer, ICE, media, termination), P2P/STUN/TURN/SFU selection, QoS/QoE metrics (RTT, jitter, packet loss, MOS E-model, freeze, concealment) and their alert thresholds. Use whenever code, tests, scenarios, prompts or explanations touch call states, media paths, ICE candidates or QoS thresholds.
---

# callops domain: WebRTC call flow + QoS

Source of truth trong code — đọc trước khi viết, không chép lại số liệu:
- `src/callops/models.py`: `CallState`, `NatType`, `CandidateType`, `MediaPath`, `CallEvent`, `QoSSample`.
- `src/callops/qos.py`: `THRESHOLDS`, `compute_mos()`, `PATH_EXTRA_RTT_MS`.
- `src/callops/simulator.py`, `scenarios.py`: luồng 7 bước và các kịch bản lỗi.

## Call flow

```
CALL SETUP (INVITE/JOIN_ROOM) -> SDP OFFER/ANSWER -> ICE GATHERING -> ICE CHECKS
  -> MEDIA ESTABLISHED (DTLS-SRTP, getStats mỗi giây) -> TERMINATION (BYE)
```

| Media path | Khi nào | Hệ quả |
|---|---|---|
| `P2P_HOST` | Hai bên cùng LAN | RTT thấp nhất |
| `P2P_STUN` | NAT cone, srflx<->srflx đi được | Bình thường |
| `TURN_RELAY` | NAT đối xứng / firewall chặn UDP → fallback relay | +RTT, phụ thuộc tải TURN server (CPU/RAM/bandwidth) |
| `SFU` | > 2 người: mỗi người nối tới SFU | Lỗi có thể chỉ ở 1 participant (uplink riêng) |
| `ICE_FAILED` | Không cặp candidate nào thành công (vd. symmetric NAT + không có TURN) | Call FAILED, không có media |

## Ngưỡng QoS (theo `THRESHOLDS`)

| Metric | Warning | Critical | Ghi chú |
|---|---|---|---|
| `rtt_ms` | ≥ 300 | ≥ 500 | ITU-T G.114: one-way < 150ms |
| `jitter_ms` | ≥ 30 | ≥ 50 | Jitter buffer giãn → trễ/méo |
| `packet_loss_pct` | ≥ 1 | ≥ 5 | PLC che được một phần |
| `mos` | ≤ 3.6 | ≤ 3.1 | E-model rút gọn, thang 1.0–4.5 |
| `concealment_pct` | ≥ 5 | ≥ 10 | % audio do PLC "bịa" ra |

MOS là **hệ quả** của RTT/jitter/loss (xem `compute_mos`) — khi chẩn đoán, MOS thấp là triệu chứng QoE, nguyên nhân phải tìm ở metric mạng hoặc log.

## Quy tắc khi làm việc

- Thêm kịch bản lỗi mới → thêm vào `scenarios.py` + test e2e trong `tests/test_flow.py`, giữ seed để tái lập.
- Đổi ngưỡng → chỉ sửa `THRESHOLDS`, ghi nguồn tham chiếu trong comment, báo người cùng nhóm (ảnh hưởng cả anomaly lẫn agent).
- Không hard-code số ngưỡng ở module khác; import `THRESHOLDS`.
- Tài liệu tham khảo: *WebRTC for the Curious* (chương Signaling, Connecting/STUN/TURN, Media Communication).
