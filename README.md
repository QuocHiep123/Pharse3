# TURN Selector Intelligence

Đề tài sáu tuần: **chọn danh sách TURN cho Caller và Callee**, rồi đánh giá kết quả kết nối. Hiện tại Hiệp làm **simulator + data model trước**; mentor chưa giao log thật hay danh sách field production, nên mọi thông số mô phỏng là *giả định có version*.

![Luồng Week 1: một cuộc gọi synthetic từ cấu hình đến kiểm tra](docs/turn-call-lifecycle.svg)

| | |
|---|---|
| **Trạng thái contract** | [Data Contract v0.5.0](docs/w2-data-contract/DATA_CONTRACT_v0.5.0.md) · `simulator_ready` · nguồn production chờ xác minh |
| **Phân công** | **Hiệp**: simulator, raw synthetic, pipeline, dashboard · **Đoàn**: thuật toán Selector, interface, đề xuất contract |
| **Đọc tiếp** | [Khảo sát nguồn dữ liệu](docs/w2-data-contract/KHAO_SAT_NGUON_DU_LIEU.md) · [Định nghĩa metric](docs/w2-data-contract/metric_config_v0.5.0.yaml) · [W1 của Hiệp](docs/W1_HIEP.md) · [Quyết định cho simulator](docs/w2-data-contract/README.md) · [KPI MVP](docs/w2-data-contract/KPI_MVP_v0.5.0.md) · [Hướng giải quyết của Đoàn](docs/w2-data-contract/Huong_giai_quyet_Smart_TURN_Selector.md) |

---

## 1. Một cuộc gọi đi qua hệ thống như thế nào

Signaling đi qua BE (Spring Boot); **media đi A → TURN(A) → TURN(B) → B**, không qua BE. Selector được gọi **song song** với invite, không chặn signaling.

```mermaid
sequenceDiagram
  autonumber
  participant A as Caller (A)
  participant BE as BE (signaling)
  participant S as Selector / policy
  participant B as Callee (B)
  participant T as TURN (A) → TURN (B)

  A->>BE: gọi B
  BE->>BE: tạo call_session + endpoint_network_context
  par song song, không chặn
    BE->>B: invite
  and
    BE->>S: select (ctx hai bên)
    S-->>BE: hai danh sách ≤ 8 mục + cặp dẫn đầu
    BE->>BE: ghi Decision Log (decision_id)
  end
  BE-->>A: cấu hình iceServers của A
  BE-->>B: cấu hình iceServers của B
  A->>A: client_applied_config
  B->>B: client_applied_config
  A->>T: ICE chọn cặp thực tế theo priority
  B->>T: (cặp thực tế có thể khác cặp dẫn đầu)
  A-->>B: media qua TURN, getStats mỗi đầu
  A->>BE: client_call_report
  B->>BE: client_call_report
  BE->>BE: call_outcome (end_signal)
```

> Điểm khác v0.4.0: không còn "đi rank 1 × rank 1, lỗi thì thử rank kế". Selector chọn **cặp dẫn đầu**, ICE chọn **cặp thực tế**; hai thứ được ghi riêng.

## 2. Dữ liệu chảy qua hai lớp

```mermaid
flowchart LR
  subgraph RAW["Lớp 1 · Contract thu thập"]
    direction TB
    R1["Call logs<br/>call_session · call_outcome<br/>client_call_report"]
    R2["Decision Log<br/>selector_decision_request<br/>selector_decision · _pair"]
    R3["Client<br/>client_applied_config<br/>ice_event · call_stats_*"]
    R4["Network context<br/>endpoint_network_context"]
    R5["TURN<br/>turn_health_1m · turn_allocation<br/>turn_probe (tùy profile)"]
  end
  subgraph POST["Lớp 2 · Sau thu thập"]
    direction TB
    P1["Pipeline làm sạch<br/>outcome_log · ice_attempt*<br/>telemetry_coverage"]
    P2["Feature<br/>feat_leg_stats · feat_turn_turn<br/>health_snapshot"]
    P3["Labeled + KPI<br/>fact_call · fact_call_endpoint"]
  end
  RAW --> P1 --> P2
  P1 --> P3
  R2 --> P3
  P2 -. "chỉ dùng dữ liệu đã đến<br/>trước request_ts" .-> R2
  classDef raw fill:#e8f1ff,stroke:#3b6fd4;
  classDef post fill:#eaf7ee,stroke:#2f8f4e;
  class R1,R2,R3,R4,R5 raw
  class P1,P2,P3 post
```

Một cột là **raw** khi có đúng một nguồn ghi trực tiếp. Cột tính từ nhiều dòng, nhiều nguồn hay theo cửa sổ thuộc lớp 2. Simulator giữ **network truth** ở bảng riêng và không chép thành số đo quan sát.

## 3. Quyết định → áp dụng → thực tế → kết quả

Ba đối tượng khác nhau, nối bằng `decision_id`, `decision_device_id`, `pc_id`, `ice_generation`:

```mermaid
flowchart LR
  D["Cặp được cân nhắc<br/>selector_decision_pair<br/><i>is_lead</i>"]
  L["Danh sách đã cấp<br/>selector_decision.entries<br/><i>tối đa 8 mục/bên</i>"]
  C["Cấu hình client đã áp dụng<br/>client_applied_config"]
  I["Cặp ICE thực tế<br/>ice_event"]
  O["Kết quả<br/>call_outcome + client_call_report<br/>→ outcome_log"]
  D --> L --> C --> I --> O
  I -. "có thể ≠ cặp dẫn đầu" .-> D
```

## 4. KPI không biến "thiếu dữ liệu" thành "tốt"

Mọi call thuộc cohort, kể cả khi thiếu outcome hay stats. Tỷ lệ báo cả hai cận: `pcr_itt_low = K/N` và `pcr_itt_high = (K+U)/N`.

```mermaid
flowchart TD
  S["call_session (N)"] --> O{"có outcome_log?"}
  O -- không --> UO["U_outcome"]
  O -- có --> A{"answered?"}
  A -- false --> G1["G · không poor"]
  A -- true --> M{"media_connected"}
  M -- "false + bằng chứng lỗi" --> K1["K · setup_fail"]
  M -- unknown --> UO
  M -- true --> D{"dropped?"}
  D -- true --> K2["K · drop"]
  D -- false --> Q{"chất lượng"}
  Q -- poor --> K3["K · quality_poor"]
  Q -- ok --> G2["G · không poor"]
  Q -- unknown --> UQ["U_quality"]
  classDef k fill:#fde8e8,stroke:#c0392b;
  classDef g fill:#eaf7ee,stroke:#2f8f4e;
  classDef u fill:#fff6dd,stroke:#c79200;
  class K1,K2,K3 k
  class G1,G2 g
  class UO,UQ u
```

RTT, packet loss, jitter luôn đi kèm `sample_count`, `eligible_count`, `measurement_coverage`. `call_stats_*` chỉ giữ cuộc gọi relay hoặc thất bại, nên không suy rộng chất lượng sang cuộc gọi P2P.

## 5. User không có TURN tại quốc gia của mình

```mermaid
flowchart LR
  U["ctx.country của endpoint"] --> L{"dim_turn có TURN<br/>trong country/area?"}
  L -- có --> H{"turn_health_1m<br/>healthy?"}
  H -- có --> A["local_turn_available"]
  H -- không --> B["no_healthy_turn"]
  L -- không --> C{"inventory_scope<br/>đầy đủ?"}
  C -- không --> D["no_turn_observed / unknown<br/>→ fallback theo dim_country_area"]
  C -- có --> E["fallback + ghi used_fallback_turn"]
```

`no_turn_observed` **không** có nghĩa là `not_deployed`.

## 6. Bản đồ thư mục

| Đường dẫn | Nội dung |
|---|---|
| [`docs/w2-data-contract/DATA_CONTRACT_v0.5.0.md`](docs/w2-data-contract/DATA_CONTRACT_v0.5.0.md) | **Bản chốt**: quyết định, assumption, danh sách bảng, KPI |
| [`docs/w2-data-contract/`](docs/w2-data-contract/) | Đề xuất và hai schema YAML của Đoàn; KPI; lab ICE |
| [`docs/research/`](docs/research/) | Ghi chú nghiên cứu (dataset, getStats, VIA/OPE, kiến trúc media) |

