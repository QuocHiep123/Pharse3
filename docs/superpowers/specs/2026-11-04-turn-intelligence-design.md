# TURN Intelligence — Thiết kế Simulator, Data Pipeline & Dashboard

- **Ngày:** 2026-11-04 · **Owner:** Đặng Quốc Hiệp · **Đối tác:** Đặng Đỉnh Đoàn (thuật toán + API)
- **Trạng thái:** Draft v0.4, đồng bộ với Data Contract v0.4.0, chờ Hiệp và Đoàn duyệt
- **Research nền:** `docs/research/01..07-*.md`. Riêng 05–07 (media qua BE/SFU) **chỉ áp dụng Pattern 1** (một PeerConnection A → TURN(A) → TURN(B) → B, BE chỉ làm signaling, xác nhận 2026-11-04); các pattern có media server ở giữa là phương án dự phòng, chưa dùng (xem §17)
- **Nguồn sự thật cho schema, bất biến, KPI, luật đánh giá:** `docs/contracts/data-contract.md` (v0.4.0). Spec này **không lặp lại định nghĩa**, chỉ tóm tắt và trỏ tới mục tương ứng của contract. Mâu thuẫn giữa hai tài liệu thì contract thắng.

> Đọc nhanh: §1 → §3 (flow một cuộc gọi) → §4 (vòng lặp theo ngày) → §7 (pipeline). Các phần còn lại là tra cứu.

---

## 1. Mục tiêu và phạm vi

**Bài toán.** Thuật toán của Đoàn xếp hạng **top-4 TURN cho mỗi bên**. Cuộc gọi đi theo đường `A → TA1 → TB1 → B` (rank 1 của mỗi bên), còn rank 2–4 là dự phòng. Production **chỉ đo được đường đã đi**. Phần của Hiệp là xây hệ thống:

1. **Sinh dữ liệu** giả lập có tính thực tế, vì chưa có log thật.
2. **Xử lý dữ liệu** (pipeline + data quality) bằng code dùng lại được nguyên vẹn khi có log Call thật.
3. **Đo lường và đánh giá độc lập** chất lượng TURN, chất lượng thuật toán và sức khỏe service.
4. **Trình bày** trên dashboard chạy thật, kèm insight có bằng chứng.

**Định nghĩa "xong" (MVP 02/12, Final 15/12):**
- Simulator chạy rolling 30 ngày (sau burn-in 3 ngày), có đủ các kịch bản bắt buộc S01–S10 và các kịch bản production S21–S25 (§10).
- Pipeline chạy incremental theo ngày, chạy lại không đổi kết quả, và bắt được dữ liệu bẩn đã tiêm.
- Dashboard đi được từ *quyết định của thuật toán* → *đường thực đi* → *chất lượng cuộc gọi*, có Decision Trace theo Call ID.
- **Metric chính là `pcr_itt`** (Poor Call Rate, intention-to-treat, hai cận low/high; contract §13.3), không phải PNR. Kết luận Smart tốt hơn / tệ hơn / INCONCLUSIVE theo luật chéo hai cận và guardrail non-inferiority (contract §14.4), đơn vị độc lập là seed (contract §14.3). Các ngưỡng/luật được đóng băng trước `blind_benchmark` đầu tiên.
- Có ≥3 insight, mỗi insight được kiểm chứng với sự cố ẩn (precision/recall) và chạy trên `blind_benchmark` (§6.6).
- Đánh giá thuật toán **có xử lý selection bias** (§8), và được kiểm chứng bằng Network Truth.

**Kiến trúc được giả định (contract §0.2):** BE (Spring Boot) chỉ là backend signaling, **không** nằm trên đường media; chính sách ICE mặc định là relay-only.

**Ngoài phạm vi:** KPI cho group call (simulator chỉ sinh cuộc gọi nhóm trong kịch bản S22 để chứng minh chúng bị lọc khỏi KPI, I21), SFU, alerting (Grafana), đo RIPE Atlas thật, M-Lab BigQuery, mọi khẳng định về cải thiện production.

**Nguyên tắc trung thực.** Mọi kết luận gắn nhãn nguồn `data_source ∈ {synthetic, lab_zenodo, public_reference, production}`. Kết quả trên simulator **không** được dùng để khẳng định production đã tốt hơn. Kết luận chỉ áp dụng cho `data_source=synthetic` với các giả định trong sổ giả định (§16).

---

## 2. Thuật ngữ

| Thuật ngữ | Nghĩa |
|---|---|
| **Leg (chặng)** | Một đoạn của đường đi: `user_turn` (user ↔ TURN của họ) và `turn_turn` (TURN ↔ TURN). Mỗi chặng có hướng `forward`/`reverse` |
| **Path (đường)** | Tổ hợp (TAi, TBj). Độ trễ một chiều forward = `user_turn(caller)` + `turn_turn(TA→TB)` + `user_turn(callee)`. Nếu TAi = TBj (`relay_same`) thì không có chặng `turn_turn` (= 0) |
| **Policy** | Thuật toán chọn TURN. Ba họ (contract §14.1): `geo_baseline@*` (Hiệp viết), `historical@*`, `smart@*` (Đoàn viết) |
| **Exploration (ε)** | Tỉ lệ nhỏ cuộc gọi cố ý đi rank 2–4 để có dữ liệu cho đường chưa đi |
| **Propensity** | Xác suất policy chọn đúng đường đã đi. Bắt buộc phải log thì mới sửa được lệch |
| **Network Truth** | Chất lượng "thật" của mọi chặng, chỉ simulator biết. Dashboard **không đọc**, chỉ dùng để chấm điểm (contract §11) |
| **Oracle** | Đường tốt nhất theo Network Truth **trong số đường khả thi theo sự thật**, là mốc để tính regret (contract §14.6) |
| **PCR ITT** (`pcr_itt`) | Poor Call Rate, intention-to-treat: tỉ lệ cuộc gọi "tệ" trên **cả cohort đã được gán nhánh**, báo cáo hai cận `low`/`high`. **Metric chính.** Định nghĩa: contract §13.2–13.3 |
| **PNR** | Poor Network Rate kiểu Via. Chỉ còn là **chẩn đoán** (Tầng 3, trên cuộc gọi đã connected), không dùng để kết luận |
| **KPI-grade** | Dữ liệu gửi 100% cuộc gọi (`call_stats_epoch`, `path_leg_measurement[epoch_summary]`, `call_outcome`...). Chỉ loại này được dùng cho KPI chính và guardrail (I16) |
| **Diagnostic** | Dữ liệu lấy mẫu hoặc tùy telemetry (`call_stats_5s`, `window_5s`, `ice_candidate_pair`). Chỉ để điều tra, Decision Trace, biểu đồ chi tiết |
| **`connection_mode`** | Thời điểm ICE bắt đầu: `post_answer` (sau khi bắt máy, **mặc định, giả định chưa xác minh**) hoặc `pre_connect` (trong lúc đổ chuông) |
| **BE (signaling backend)** | Backend Spring Boot của công ty. **Chỉ** làm signaling: lời mời, đổ chuông, bắt máy, SDP, ICE candidate; gọi Selector; ghi `call_session`/`selector_decision`. Là producer `signaling` trong contract. Media **không** đi qua BE (contract §0.2) |
| **Mặt phẳng điều khiển vs mặt phẳng media** | Điều khiển: `A ⇄ BE ⇄ B` và `BE → Selector`. Media: một PeerConnection `A → TURN(A) → TURN(B) → B`, không qua BE. BE chỉ ảnh hưởng **thời gian thiết lập**, không ảnh hưởng RTT/loss/jitter nên không ảnh hưởng `pcr_itt` |
| **`ice_transport_policy`** | `relay` (mặc định; chỉ dùng relay candidate, suy ra từ mô tả của mentor, chưa xác minh) hoặc `all` (cho phép P2P và `relay_direct`, chỉ dùng làm sensitivity). Bất biến I18: `relay` ⇒ mọi attempt `connected` có `path_type ∈ {relay_relay, relay_same}` |
| **Snapshot** | Phiên bản bảng feature/health mà policy dùng khi quyết định. Có `cutoff_ts`, `published_ts`, `content_hash`, bất biến sau khi publish (contract §9.0) |

---

## 3. Flow một cuộc gọi

```
 MẶT PHẲNG ĐIỀU KHIỂN:  A ⇄ BE ⇄ B  (invite, ring, answer, SDP, ICE candidate)  ·  BE → Selector (initial, refined)
 MẶT PHẲNG MEDIA:       A → TURN(A) → TURN(B) → B   (một PeerConnection, KHÔNG qua BE)

 t0  A bấm gọi: BE tạo call_session (gán experiment_id/arm, ghi ice_transport_policy, be_region TRƯỚC mọi quyết định) ► [call_session]
     BE ── Selector.select(ctx_A, ctx_B?) ──────────────────────────────────────────► [selector_decision]
                                  │  đọc snapshot mới nhất có published_ts ≤ t           phase=initial
                                  │  trả 4 TURN/bên + score + propensity + confidence
                                  │  Selector KHÔNG chặn lời mời; lỗi/timeout ⇒ static_fallback (I14)
 t1  Client A, B allocate (allocation_id do client sinh) ► TURN ─────────────────────► [turn_allocation]
                                  (alloc_ms = allocation latency, gồm vòng 401 + xử lý server; KHÔNG phải số đo chặng)
 t2  ring_ts: máy B đổ chuông · answer_ts: B bấm nghe (cả hai là sự kiện của BE) ────► [call_outcome]  (+ *_signaling_rtt_ms, chẩn đoán)
     máy B đổ chuông → biết ctx_B → BE gọi Selector refine ──────────────────────────► [selector_decision] phase=refined
                                  (mỗi thiết bị của B đổ chuông = một request refined và một decision_id riêng; ICE dùng decision_id của thiết bị bắt máy, I20)
 t3  post_answer: answer → SDP/ICE candidate đi qua BE → ICE checks bắt đầu.
     ICE (post_answer: checks sau answer_ts): start_ts → checks_start_ts →
     ice_connected_ts → dtls_connected_ts; lỗi thì fallback rank kế ─────────────────► [ice_attempt] (+attempt_seq, ice_generation,
                                                                                        allocation_id mỗi bên, loại candidate được chọn → path_type)
 t4  Media chạy. SDK tính trên thiết bị và gửi khi epoch kết thúc (hoặc gửi call_stats_5s 100% để pipeline tính) ► [call_stats_epoch]  100%, cửa sổ 5 s neo theo từng endpoint tại ice_connected_ts đầu tiên trên đồng hồ endpoint đó
                                                                                         [path_leg_measurement] granularity=epoch_summary  100%
     chỉ cuộc gọi được lấy mẫu (critical 100% + SHA-256 10%) ────────────────────────► [call_stats_5s], [path_leg_measurement] window_5s
     đổi Wi-Fi↔4G → network_epoch+1, ICE restart (ice_generation+1) ─────────────────► [ice_attempt] restart
 t5  Kết thúc ────────────────────────────────────────────────────────────────────────► [call_outcome]
 song song: TURN↔TURN mesh probe, TURN health, Selector service health ──────────────► [path_leg_measurement] (probe, call_id=null) [turn_health_1m] [service_health_1m]
 chỉ simulator: chất lượng thật của mọi chặng, sự cố ─────────────────────────────────► [truth_leg_5m] [incident_truth] [dirt_log]  (ẩn)
```

- Toàn bộ event nối với nhau qua `call_id`, `decision_id`, `allocation_id`. Cuộc gọi lỗi **vẫn được giữ lại**, không bao giờ điền 0 (thiếu số đo thì `null` kèm lý do).
- **Media không bao giờ đi qua BE.** BE chỉ ảnh hưởng thời gian thiết lập (đoạn `answer_ts → checks_start_ts`, chẩn đoán `setup_breakdown_post_answer`, `signaling_overhead_est_ms`), không bao giờ ảnh hưởng RTT/loss/jitter hay `pcr_itt` (contract §0.2, §13.3).
- Với `ice_transport_policy = relay` (mặc định) mọi attempt `connected` đều là `relay_relay` hoặc `relay_same` (I18); P2P chỉ xuất hiện khi chạy sensitivity `all`.
- Contract chỉ ràng buộc các quan hệ nhân quả (I5); **không** ép thứ tự giữa allocation, signaling và ICE checks ngoài những quan hệ đó.
- `alloc_ms` chỉ là độ trễ của thao tác allocation. Không được coi là RTT hay one-way của chặng (contract §5.3, §8.2).
- Hai tầng dữ liệu (contract §0.1): `call_stats_epoch` và `path_leg_measurement[epoch_summary]` luôn 100%; `call_stats_5s` và `window_5s` chỉ cho cuộc gọi được lấy mẫu (quy tắc ở §6.5).

---

## 4. Vòng lặp theo ngày (rolling simulation, vòng kín)

```
for d in day_1 .. day_30:
    # mỗi cuộc gọi tại thời điểm t dùng snapshot MỚI NHẤT có published_ts <= t   (I12)
    sim.run_day(d, policy, env_dir)            # sinh raw events ngày d, trong môi trường cô lập của policy
    pipeline.run(d, lookback_days = 3)         # raw → clean → DQ → mart
    feature_store.build(cutoff_ts = 00:00 giờ VN ngày d+1)   # chỉ event có event_ts < cutoff VÀ ingest_ts < cutoff (I13)
    feature_store.publish(...)                 # published_ts > cutoff_ts; snapshot bất biến
```

- **Cutoff** của snapshot là 00:00 giờ VN (17:00 UTC hôm trước), mỗi ngày một snapshot. Từ `cutoff_ts` tới `published_ts`, Selector vẫn **dùng snapshot cũ**.
- **Bất biến:** snapshot đã publish không sửa. Event trễ (ingest sau cutoff) không lọt vào snapshot đó; backfill hoặc sửa logic thì tạo `snapshot_id` mới (`feat-YYYYMMDD-v<n+1>`). Dựng lại từ raw và cấu hình đã lưu phải ra cùng `content_hash`. Chi tiết: contract §9.0.
- **Burn-in 3 ngày** đầu bị loại khỏi đánh giá. Mọi policy khởi đầu từ cùng `initial_snapshot_hash`, nên cold-start toàn hệ thống vẫn là thật (ngày 1 dùng prior: geo + dữ liệu công khai).
- Có `lookback_days=3` vì simulator cố tình sinh event trễ tới 72 giờ (lớp clean ghi đè partition). Điều này **không** làm đổi snapshot đã publish.
- Mỗi lần chạy có `run_manifest` (contract §12) gồm `sim_run_id`, `replicate_seed`, `root_seeds`, `environment_dir`... Cùng manifest thì ra cùng hash dữ liệu.

---

## 5. Hai ý tưởng thu dữ liệu chặng (đề xuất gửi mentor)

Lý do cần các cơ chế này: chỉ đo đường đã đi thì dữ liệu bị lệch theo chính thuật toán (§8). Mục tiêu là **có thêm số đo chặng mà không làm đổi đường đi của cuộc gọi**.

### 5.1 Allocate toàn bộ 4 TURN mỗi bên lúc setup (pre-allocation)

- **Cách làm:** client gửi TURN Allocate tới cả 4 server cùng lúc. Sau khi ICE connected: **giữ rank 1 và rank 2** (refresh định kỳ) để fallback nhanh, **giải phóng rank 3–4** (`release_reason`: `not_needed`, `kept_for_failover`...).
- **Lợi ích:**
  - Fallback không phải chờ allocate lại (thường mất 100–300 ms).
  - Phát hiện sớm TURN lỗi hoặc quá tải qua `alloc_success_rate` và lỗi `alloc_error`.
  - Có thống kê **độ trễ allocation** theo (segment, TURN, transport) trong `feat_turn_alloc_latency` (contract §9.6).
- **Chi phí:** số allocation tăng khoảng 4 lần trong vài giây đầu. Tốn port và quota trên TURN; với `pre_connect` còn thêm allocation sống trong lúc đổ chuông (§6.4).
- **Giới hạn quan trọng:** `alloc_ms` là **allocation latency** (gồm vòng 401 và thời gian server xử lý), **không phải số đo chặng**, nên pre-allocation **không** cho dữ liệu chặng user→TURN. `alloc_ms` chỉ được dùng làm predictor của chặng sau khi một **thí nghiệm hiệu chỉnh** (W5) chứng minh được quan hệ trên dữ liệu tách riêng (contract §8.2). Cho tới lúc đó, không có `method=alloc`, không đổi `alloc_ms` sang one-way.

### 5.2 TURN↔TURN mesh probe phía server

- **Cách làm:** mỗi TURN chạy một agent nhẹ, cứ 60 giây gửi gói UDP echo hoặc relay loopback (kiểu `turn-monitor`) tới mọi TURN khác. Với 22 TURN là 462 cặp có hướng, tức khoảng 8 gói/giây trên toàn hệ thống, không đáng kể. Ghi `method=mesh_probe`.
- **Lợi ích:** chặng giữa `turn_turn` **không phụ thuộc user**, nên probe cho **toàn bộ ma trận mà không bị thuật toán làm lệch**. Sau đó chỉ còn các chặng `user_turn` bị lệch. Probe còn phát hiện được sự cố backbone giữa các vùng.
- **Một chiều hay RTT:** đo một chiều (`measurement_kind=one_way`) cần đồng bộ đồng hồ giữa các server và bắt buộc có `clock_sync_err_ms`. Không có thì đo `rtt`; lớp clean tạo `one_way_ms_estimated` có cờ `symmetric_assumption=true`, tách khỏi `one_way_ms_observed` (contract §8.2).

### 5.3 (Bổ sung) Idle probe phía client

Khi app mở hoặc rảnh, khoảng 1 lần/ngày, SDK gửi 1 STUN binding tới 2 TURN chọn ngẫu nhiên **ngoài** top của user đó. Mục đích là lấp coverage của chặng user→TURN với chi phí gần bằng 0 và không ảnh hưởng cuộc gọi. Gắn `method=idle_probe`. Đây (cùng `inband`) là nguồn số đo chặng `user_turn`.

**Trong simulator**, cả 3 cơ chế là tham số bật/tắt (`alloc_all`, `mesh_probe`, `idle_probe_rate`). Báo cáo sẽ so sánh coverage và sai số đánh giá khi bật/tắt từng cơ chế, làm bằng chứng để đề xuất với mentor.

---

## 6. Simulator

### 6.1 Module

| Module | Trách nhiệm |
|---|---|
| `world` | Sinh `dim_turn`, `dim_turn_endpoint`, `dim_user`, `dim_asn`, ma trận khoảng cách và độ trễ giữa thành phố, cùng thông tin client của từng user (§6.3b) |
| `truth` | **Network Truth**: độ trễ, loss, jitter thật của mọi chặng theo thời gian (ẩn), tách thành thành phần ngoại sinh và thành phần do tải (contract §11) |
| `incidents` | Tiêm sự cố từ lịch ẩn `incidents.yaml` (§6.6) |
| `traffic` | Ai gọi ai, lúc nào, có bắt máy không. Phân bố theo giờ trong ngày, cặp VN/quốc tế, cuộc gọi "mù" |
| `policy` | Interface `select(req, rng) -> Decision` (contract §10). Có sẵn `geo_baseline`, plug-in policy của Đoàn, wrapper ε-exploration. `rng` do simulator cấp; policy không tạo RNG toàn cục |
| `be` | Mô hình BE signaling (§6.3a): `be_region`, độ trễ tin nhắn signaling, thời gian xử lý của BE, `*_signaling_rtt_ms`. Chỉ tác động lên mốc thời gian thiết lập, **không** đụng tới `truth` của đường media |
| `call_engine` | Allocation → ICE/fallback → media → `call_stats_epoch` → outcome, đọc từ `truth` và cộng nhiễu đo. Dòng thời gian thiết lập đi qua `be` |
| `probes` | Mesh TURN↔TURN, idle probe |
| `health` | `turn_health_1m` (tải được tính từ chính traffic, nên có hiện tượng dồn traffic gây quá tải), `service_health_1m`, và **`health_snapshot` mỗi phút** (contract §9.7: `health_snapshot_id` = `hl-YYYYMMDDTHHMM`, `health_status`, `health_score`, `utilization_pct_5m`, `alloc_fail_rate_5m`; cutoff = đầu phút, bất biến, I12/I13). Health filtering của policy chỉ đọc snapshot này (bản mới nhất có `published_ts ≤ request_ts`), không đọc trạng thái sống |
| `dirt` | Tiêm dữ liệu bẩn: 1–3% event thiếu, trùng, trễ, lệch đồng hồ, sai đơn vị |
| `runner` | Vòng rolling (§4), RNG có khóa, sink, ghi `run_manifest`, cô lập môi trường theo policy |

**Tái lập và công bằng giữa các policy** (contract §14.2): mỗi (policy, seed) là một lần chạy riêng với `environment_dir` riêng. Yếu tố ngoại sinh (traffic, bắt máy, thời lượng dự định, đổi mạng, lịch sự cố, mạng nền) được sinh trước hoặc rút từ RNG có khóa theo thực thể và thời điểm, nên số event do policy sinh ra không làm xê dịch luồng ngẫu nhiên nào. Tải, lịch sử, snapshot là nội sinh và được phép khác nhau.

### 6.2 Thế giới

- **TURN Việt Nam (15):** Bắc (HAN ×4, HPH ×1), Trung (DAD ×3, HUE ×1, NHA ×1), Nam (SGN ×4, CTO ×1). Mỗi miền được host bởi Viettel, VNPT và FPT.
- **TURN quốc tế (7):** SG ×2, JP-Tokyo, HK, DE-Frankfurt, US-West, AU-Sydney.
- **Quốc gia có user nhưng không có TURN:** TW, KR, TH, MY, FR, UK, US-East…
- **User (50k):** 80% VN (Bắc 40%, Trung 15%, Nam 45%; Viettel 45%, VNPT 30%, FPT 20%, khác 5%) và 20% quốc tế. Mạng chính: wifi 55%, 4G 38%, 5G 7%.
- **Cold-start có chủ đích:** 3 quốc gia và 2 ISP nhỏ có dưới 30 cuộc gọi trong cả 30 ngày.
- Đây là giả định của nhóm. Nếu mentor có topology thật thì thay vào file `configs/world.yaml`.

### 6.3 Mô hình Network Truth (độ trễ một chiều của một chặng)

```
ms = base_city(src_city, dst_city) / 2      # nửa RTT từ bảng ping thành phố WonderNetwork
   + isp_penalty(src_isp, dst_host_isp)     # cùng ISP 0; khác ISP trong VN 3–15 ms (GIẢ ĐỊNH, có sensitivity)
   + access(network_type)                   # chỉ chặng phía user: wifi ~2–5, 4G ~10–20, 5G ~5–10 (nền từ Ookla)
   + diurnal(hour, region)                  # cao điểm 20–23h tăng 10–30%
   + load_penalty(turn_utilization)         # >80% tải thì tăng mạnh   → load_one_way_ms (riêng từng môi trường)
   + incident(t)                            # theo incidents.yaml
   + noise ~ LogNormal                      # đuôi dài
```

- Các thành phần không do tải gộp thành `exo_one_way_ms` (giống nhau giữa các policy), phần do tải là `load_one_way_ms` (contract §11).
- **Loss và jitter** là hàm của access, load và incident. Cuộc gọi trên 4G và trong giờ cao điểm có loss cao hơn.
- **Không dùng công thức theo khoảng cách** vì định tuyến không đơn điệu. Ví dụ HN→Seoul 120 ms nhưng HCM→Seoul 65 ms (`docs/research/01`).
- Telemetry mà SDK "quan sát" (histogram RTT media / loss / jitter theo cửa sổ 5 s trong `call_stats_epoch`) được sinh từ truth + nhiễu đo. Nhãn PCR chỉ đọc telemetry này, **không bao giờ đọc `path_leg_measurement` hay truth** (contract §13).
- **MOS** tính theo E-model (ITU-T G.107 rút gọn) và chỉ là **chẩn đoán** (`mos_est`). Zenodo WebRTC-QoE chỉ dùng để đối chiếu.

### 6.3a BE (signaling) trong simulator

- **Tham số `be_region`:** một cụm BE duy nhất, mặc định `SGN` (contract Q6: số BE và vị trí thật chưa biết). Ghi vào `call_session.be_region`.
- **Độ trễ một tin nhắn signaling** giữa user và BE = `RTT(thành phố user ↔ thành phố BE) / 2` (từ ma trận RTT thành phố, §6.3) + độ trễ một chiều của mạng truy cập (`access(network_type)`). **Thời gian xử lý của BE** nhỏ, phân phối LogNormal.
- **Dòng thời gian thiết lập sau khi bắt máy (`post_answer`):** `answer_ts` → tin nhắn SDP/ICE đi qua BE → `checks_start_ts` → `ice_connected_ts` → `dtls_connected_ts` → `first_media_received_ts`. Đoạn đầu phụ thuộc BE; các đoạn sau chỉ phụ thuộc đường media. Đây là cơ sở của chẩn đoán `setup_breakdown_post_answer` (contract §13.3).
- **`caller_signaling_rtt_ms`, `callee_signaling_rtt_ms`:** sinh = RTT thật app ↔ BE + nhiễu đo (có thể null, contract Q8). `signaling_overhead_est_ms` được tính ở pipeline từ hai số này.
- **BE không đổi đường media:** `be_region` không được tham gia vào `truth` của chặng, tải TURN, loss, jitter hay xác suất ICE thành công. Đây là điều kiện của test BE-invariance (§14).
- **Hai điều kiện để BE-invariance đúng được** (contract §14.2): (1) BE làm dịch thời điểm media bắt đầu, nên phép thử chạy trên **kịch bản scripted có truth không đổi theo thời gian và health không đổi**; (2) nhiễu đo được khóa theo `window_idx` (tương đối với neo của endpoint), không theo thời gian tuyệt đối, nên không đổi khi neo dịch. Độ trễ BE ↔ Selector trong sim **không phụ thuộc `be_region`** (giả định đặt cùng chỗ, A18), nên quyết định của Selector không đổi.
- Các con số overhead signaling chỉ là **ước lượng** từ snapshot WonderNetwork (`docs/research/01`), không phải số đo (A14).

### 6.3b Thông tin client, thiết bị và danh tính TURN trong simulator (contract v0.4.0)

Mục đích: để pipeline và dashboard được thử trên dữ liệu có cùng độ "lộn xộn" như production (nhiều nền tảng, nhiều phiên bản app, hostname chung, nhiều thiết bị), thay vì chỉ trên dữ liệu đồng nhất.

**Sinh thông tin client** (contract §4: `device_id`, `platform`, `os_version`, `app_version`, `sdk_version`, `device_model`, `browser_*`). Mỗi user được gán một lần lúc dựng `dim_user`, theo RNG có khóa (không phụ thuộc policy):

| Thành phần | Cách sinh | Ghi chú |
|---|---|---|
| `platform` theo quốc gia | Bảng tỉ lệ theo `home_country`. Ví dụ VN: android ≈ 65%, ios ≈ 32%, web ≈ 3% | **Số bịa, nhãn giả định (A15)**, không phải số đo. Đặt trong `configs/world.yaml` để thay khi có số thật |
| `app_version` / `sdk_version` | 2–3 phiên bản đang chạy cùng lúc, có **staged rollout**: bản mới tăng dần tỉ lệ user theo ngày (ví dụ 0% → 10% → 50% → 100% trong vài ngày) | Cần để DQ `release_regression` có "trước/sau phát hành" (S25) |
| `device_model` → `device_class` | Mỗi platform có danh sách model giả; bảng tra có version ánh xạ model → `low`/`mid`/`high`/`unknown` | `device_class` là cột phái sinh của pipeline (contract §8.6), sim không ghi |
| `device_id` | HMAC-SHA256 của một id cài đặt giả, cùng cách với `user_hash` | Không lưu id thô |

**Mặc định production-like (contract §14.2):** mỗi user một thiết bị; chỉ cuộc gọi 1-1 (`call_type = one_to_one`); mỗi máy TURN có **một IP `listen` và một IP `relay`** trong `dim_turn_endpoint` (§3.4; `role = both` nếu hai vai dùng chung một IP), hostname riêng từng máy. Các trường hợp khác chỉ xuất hiện trong kịch bản scripted S21–S25 (§10). Cột thuộc khóa không bao giờ null: `device_id` không biết thì `'unknown'`, không áp dụng (ví dụ `turn_turn`) thì `'-'`; `call_type` không biết thì `'unknown'`.

**Quy tắc cửa sổ mà simulator và pipeline phải cài đặt giống hệt (contract §5.7):**
- Neo `anchor_ts` **theo từng endpoint**, trên đồng hồ endpoint đó, tại lần `ice_connected` đầu tiên; cửa sổ *i* = [anchor + i·w, anchor + (i+1)·w), `w = window_s` (5 s). Không đặt lại sau restart.
- Cửa sổ thuộc epoch chứa **điểm giữa** của nó (epoch là [bắt đầu, kết thúc)).
- **Đánh giá được** khi: (a) nằm trọn trong [`answer_ts`, min(`end_ts`, `converted_ts`)]; (b) không giao với khoảng gián đoạn restart [`end_ts` attempt cũ, `ice_connected_ts` attempt mới); (c) metric hợp lệ: RTT cần RTCP RR với DLSR ≠ 0 (`rtt_sample_valid`), loss cần Δexpected > 0 và Δlost ≥ 0, jitter cần giá trị không null (`jitter_sample_valid`).
- Bucket đóng trái mở phải; key chuẩn: RTT `lt100|100_200|200_300|300_400|ge400`, loss `lt1|1_3|3_5|ge5`, jitter `lt10|10_30|30_50|ge50`. Histogram là `{}` (không null) khi không có cửa sổ đánh giá được.
- `call_stats_5s` do sim sinh phải đủ cột của contract §5.8 (`window_start_ts`, `*_sample_valid`, `packets_expected`/`packets_lost` là **Δ trong cửa sổ**, `audio_active_s`, `restart_gap`, `conn_state`...) để pipeline tính lại đúng `call_stats_epoch`.

**Quy tắc thu thập diagnostic theo endpoint:** ring buffer và lấy mẫu (§6.5) chỉ áp dụng cho endpoint `derivation = sdk`; endpoint `derivation = pipeline` gửi liên tục 100% (lô gửi thất bại thì thiếu cửa sổ và `measurement_coverage` phản ánh). SDK tự xác định tầng critical từ những gì nó quan sát (ICE thất bại, rớt, restart, fallback).

**`dim_turn_endpoint` trong simulator.** Ví dụ (chỉ dùng dải tài liệu RFC 5737, không bao giờ IP thật):

| turn_id | role | ip | hostname |
|---|---|---|---|
| `VN-SGN-viettel-01` | listen | 203.0.113.10 | turn-sgn-01.example.com |
| `VN-SGN-viettel-01` | relay | 203.0.113.11 | |
| `VN-HAN-vnpt-01` | listen | 198.51.100.10 | turn-han-01.example.com |
| `VN-HAN-vnpt-01` | relay | 198.51.100.11 | |

**Quy tắc ghi IP (privacy, contract §0.3):** chỉ ghi IP của **máy chủ TURN**: `turn_server_ip` (IP `listen`) và `relayed_ip` / `relayed_ip_*` (IP `relay`). IP của user (candidate `host`/`srflx`/`prflx`) **không bao giờ** được sinh ra hay lưu; candidate không phải `relay` thì `relayed_ip_*` = null. **Không bao giờ lưu `relatedAddress`/`relatedPort`** (chứa IP người dùng). `be_instance` là một **tên** máy BE, không phải IP. Mọi IP được ghi phải có trong `dim_turn_endpoint`.

### 6.4 Hành vi client và ICE

- **`ice_transport_policy` (mặc định `relay`, ghi vào `call_session.ice_transport_policy`):** `relay` = chỉ relay candidate, **không có P2P** và không có `relay_direct`; mọi attempt `connected` có `path_type ∈ {relay_relay, relay_same}` (I18). `all` = sensitivity bắt buộc (contract §14.5), bật lại `p2p_host`, `p2p_srflx`, `relay_direct`.
- Mỗi bên nhận `k=4` TURN (tham số, đặt được tới 8 cho đúng đề bài). Số candidate thực là `min(k, số TURN khả dụng sau lọc)` (I3); thiếu thì `fallback_reason = insufficient_candidates`.
- Đường đi = rank 1 × rank 1. Nếu allocation hoặc ICE trên rank 1 lỗi hoặc quá timeout thì thử rank kế, và ghi `attempt_seq`, `ice_generation`.
- **`path_type` suy từ cặp candidate được chọn** (`selected_local/remote_candidate_type`), không giả định luôn là `relay_relay`. Với `relay` (mặc định) chỉ ra `relay_relay` hoặc `relay_same` (hai bên dùng chung một TURN). **P2P chỉ xuất hiện trong sensitivity `ice_transport_policy = all`** (`p2p_host`, `p2p_srflx`, khi đó `turn_used=false`); cuộc gọi P2P vẫn nằm trong cohort ITT. Không có tỉ lệ P2P mặc định nào.
- Đổi mạng giữa cuộc gọi: 3–5% cuộc gọi, kèm ICE restart, `network_epoch+1`.
- **Cuộc gọi mù:** khoảng 40% cuộc gọi lúc t0 chưa biết context của B (`info_level=caller_only`). Policy dùng `callee_prior`. Khi B bắt máy thì có quyết định `refined`.
- **`connection_mode`:**
  - **`post_answer` (mặc định)**: ICE checks chỉ bắt đầu sau `answer_ts`. Đây là **giả định chưa xác minh** (A9, contract Q5); ghi trong `run_manifest.connection_mode`.
  - **`pre_connect`** (sensitivity bắt buộc, contract §14.5): ICE chạy trong lúc đổ chuông, nên `connected` có thể true dù `answered=false` (I6 chỉ cho phép trường hợp này với `pre_connect`). Chế độ này phải **chạy lại toàn bộ** KPI chính, guardrail và tải TURN, mô phỏng **allocation sống trong lúc đổ chuông kể cả cuộc gọi không được bắt máy**, có TTL và `release_reason=unanswered`. Tải TURN tăng sẽ phản hồi vào `load_one_way_ms`. Chẩn đoán: `allocation_seconds_unanswered`, `reserve_allocation_seconds`.
  - **`ice_transport_policy = all`** (sensitivity bắt buộc, contract §14.5): bật lại P2P và `relay_direct`, **chạy lại toàn bộ** KPI chính, guardrail và tải TURN.
- Thứ hạng Geo/Smart đổi chiều khi chuyển `connection_mode` hoặc `ice_transport_policy` ⇒ kết luận ghi "phụ thuộc giả định".

### 6.5 Quy mô

| Profile | Ngày | Cuộc gọi | Ghi chú |
|---|---|---|---|
| `dev` | 3 | ~10k | chạy dưới 1 phút, dùng cho test |
| `main` | 30 (+3 burn-in) | ~300k | VN↔VN 70%, VN↔Intl 20%, Intl↔Intl 10% |

Số dòng ước tính cho `main` (một policy, một seed):
- `turn_allocation`: khoảng 2.4M (300k × 2 bên × 4 TURN, khi bật `alloc_all`)
- `path_leg_measurement[epoch_summary]` (**100% cuộc gọi**): khoảng 2M (≈ 300k × ~6 dòng/epoch: 2 hướng × 3 chặng, cộng epoch phát sinh do đổi mạng)
- `path_leg_measurement[window_5s]` và `call_stats_5s` (**lấy mẫu**): đo lại khi có call_engine ở W2 vì phụ thuộc tỉ lệ cuộc gọi critical
- `call_stats_epoch`: 100%, một dòng mỗi (call × endpoint_side × media_kind × epoch)

**Quy tắc lấy mẫu dữ liệu diagnostic** (contract §6.3): ring buffer trên thiết bị (≤ 360 cửa sổ, ≤ 256 KB/cuộc gọi). Khi kết thúc: cuộc gọi **critical** (`ice_failed`, `dropped_network`, `dropped_turn`, `n_ice_attempts > 1`, có fallback/restart) giữ **100%**; cuộc gọi thường giữ nếu `u64(sha256(utf8(call_id))[0:8], big-endian) mod 1000 < 100` (**10%**). Kết quả ghi vào `stats_status`, `stats_sampling_prob`, `stats_sampling_reason`. Aggregate chẩn đoán dùng trọng số Horvitz-Thompson `1/prob` ở cấp cuộc gọi. Dữ liệu KPI-grade không phụ thuộc quy tắc này. Quy tắc này chỉ áp dụng cho endpoint `derivation = sdk`; endpoint `derivation = pipeline` luôn gửi 100% (`raw_full`, I22).

### 6.6 Sự cố ẩn (`incidents.yaml`) và loại lần chạy

Có 5–8 sự cố, ví dụ:
- TURN SGN-2 sập 2 giờ.
- DAD-1 quá tải giờ cao điểm 3 ngày liên tiếp.
- ISP VNPT miền Trung suy giảm dần trong 1 tuần.
- Tuyến SG↔JP tăng 40 ms.
- Một ISP Đài Loan có loss 8%.

Hai loại lần chạy (`run_kind`, contract §12):

| Loại | Sự cố | Dùng cho |
|---|---|---|
| `scripted` | Công khai, có kỳ vọng rõ (kịch bản hệ thống S08, S11–S25) | Test tự động, demo |
| `blind_benchmark` | Ẩn, sinh theo seed bằng script (`make incidents`) vào `data/truth/` (gitignore) | So sánh policy, insight report |

Với `blind_benchmark`: `incidents_sha256` của lịch sự cố được **commit vào `run_manifest` trước khi phân tích**. Hiệp **không mở file và không xem seed** cho tới khi đã viết xong insight. Chỉ module chấm điểm `eval/incident_scoring` được đọc file này. Ngưỡng và luật kết luận phải đóng băng trước `blind_benchmark` đầu tiên.

---

## 7. Data Pipeline

### 7.1 Các lớp

```
nguồn ──► adapters ──► raw/ ──► clean/ ──► feature/ ──► mart/ ──► dashboard
(sim | zenodo | prod)  (nguyên bản)  (chuẩn hóa + DQ)  (snapshot bất biến)  (KPI theo trang)
```

| Lớp | Lưu ở | Làm gì |
|---|---|---|
| **adapters** | code | Mỗi nguồn một adapter, đổi về canonical schema. `sim` (JSONL), `zenodo` (webrtc-internals JSON), `postgres` (dành cho pilot). **Sau adapter, code dùng chung hoàn toàn** |
| **raw** | `data/raw/<table>/dt=YYYY-MM-DD/*.jsonl` | Giữ nguyên bản, append-only, không sửa. `event_ts` gốc bất biến |
| **clean** | `data/clean/<table>/dt=…/*.parquet` | Pipeline **cam kết xuất ra** các cột/bảng ở **contract §8**: hiệu chỉnh đồng hồ lưu **tách riêng** (`event_ts_corrected`, `clock_skew_ms`, `clock_correction_version`, `clock_quality_flag`); `one_way_ms_observed` / `one_way_ms_estimated` (có cờ `symmetric_assumption`); ghép allocation↔ICE (`used_by_ice`, `match_method`; quy tắc ghép gồm cả `device_id`, contract §8.3); danh tính TURN thực (`actual_turn_id_*`, `turn_identity_method`, §7.3); `call_stats_epoch` do pipeline tính khi `derivation = pipeline` (§7.3); `fact_call`; `dq_results`. Cũng ép kiểu, chuẩn đơn vị, dedup `event_id`, xử lý counter âm/reset, cắm cờ (không xóa) bản ghi lỗi |
| **feature** | `feature/*` | Các bảng `feat_*` ở contract §9, gắn `snapshot_id`, bất biến, có `content_hash`. **Đoàn đọc lớp này** |
| **mart** | `mart/*.parquet` | Bảng KPI đã tính sẵn cho từng trang dashboard (định nghĩa KPI: contract §13) |

- **Engine:** DuckDB + Polars. Mỗi ngày chạy lại thì **ghi đè cả partition** ở raw→clean→mart, nên idempotent. Riêng snapshot feature đã publish thì không ghi đè (§4).
- **DQ:** pandera cho schema và range, cộng các check SQL. Kết quả ghi vào `dq_results` (cột: contract §8.5).

### 7.2 Data quality: bất biến và mức độ

Bộ kiểm tra chính là **24 bất biến I1–I24 của contract §7**, chia hai mức:
- **FAIL**: dữ liệu sai, phải sửa (ví dụ I1, I3, I6–I8, I10, I12–I18, I20–I24). Mới: **I23** (`ice_failed` ⇔ `answered ∧ ¬connected`; và `answered ∧ ¬connected` chỉ có `end_reason ∈ {ice_failed, normal_hangup, app_crash, unknown}`) và **I24** (`dropped = true` ⇔ `end_reason ∈ {dropped_network, dropped_turn}`).
- **WARN**: đáng ngờ, hiện lên trang Data Quality (ví dụ I2, I4, I5, I9, I11, I19). Riêng **I19** là **phát hiện vận hành** (`turn_identity_mismatch`), không phải lỗi dữ liệu.

Ngoài bất biến, thêm các check thống kê/vận hành: schema và `contract_version`; tỉ lệ event trễ và freshness; lệch đồng hồ client–Signaling; phân phối (số lượng hoặc trung vị lệch quá 3 MAD so với baseline cùng giờ trong tuần); `unclassifiable_rate` và phân bố `stats_status` (§11); và check phân phối theo `app_version` (`release_regression`, §7.3). `dq_results` dùng `pipeline_run_id` (lần chạy pipeline), khác `sim_run_id`.

**Tự kiểm chứng:** mọi lỗi do `dirt` tiêm vào đều có ID trong `dirt_log`. Pipeline phải bắt được **≥95%**, và đây là một test bắt buộc.

### 7.3 Danh tính TURN thực, derivation, phân loại PCR và release_regression (contract v0.4.0)

1. **Danh tính TURN thực (contract §8.6).** Với mỗi bên, `actual_turn_id_caller/callee` tra trong `dim_turn_endpoint` có hiệu lực tại thời điểm đó, theo thứ tự ưu tiên: (1) `relayed_ip_*` của cặp candidate được chọn; (2) `relayed_ip` của allocation đã dùng; (3) `turn_server_ip`; (4) hostname, **chỉ khi** hostname trỏ tới đúng một máy. Còn lại là null. Các nguồn mâu thuẫn nhau ⇒ WARN I19. Xuất `turn_identity_method` ∈ {`ip`, `hostname`, `ambiguous`}; `ambiguous` gắn vào nhóm "pool", không gán bừa cho một máy. **Mọi KPI theo TURN dùng `actual_turn_id` và tính theo từng đầu**: cuộc gọi `relay_relay` góp vào TURN của mỗi bên, `relay_same` góp một lần. I19 so `actual_turn_id` với `turn_id` Selector chọn; lệch ⇒ `turn_identity_mismatch` (dashboard §11). `path_type` suy theo bảng contract §2: (relay, relay) → `relay_same` nếu `actual_turn_id` hai đầu trùng, ngược lại `relay_relay`; I4 và I8 cũng dùng `actual_turn_id` (thiếu thì `relay_turn_*`, `ambiguous` thì bỏ qua).
2. **Đường dẫn derivation (contract §5.7, §5.8, §6.3 mục 6, I22).** Với endpoint `derivation = pipeline`, SDK gửi `call_stats_5s` 100% và pipeline tính `call_stats_epoch` theo **đúng các quy tắc cửa sổ ở §6.3b** (neo theo endpoint trên đồng hồ endpoint; epoch theo điểm giữa; điều kiện đánh giá được (a)(b)(c); key bucket chuẩn; histogram `{}` khi trống). Mốc `answer_ts`/`end_ts`/`converted_ts` dùng `event_ts_corrected` (§8.1); test tương đương chạy với độ lệch đồng hồ bằng 0. Dòng do pipeline tính có `producer = client_sdk` (kế thừa), `event_ts = epoch_end_ts`, `ingest_ts` = max `ingest_ts` các dòng 5s đầu vào, `event_id` = UUIDv5 tất định từ (`call_id`, `endpoint_side`, `device_id`, `media_kind`, `network_epoch`, `derivation`). I16 kiểm ở **cấp dòng**: `call_stats_5s` chỉ vào KPI khi endpoint đó `derivation = pipeline`. Hai đường phải cho kết quả giống hệt (test ở §14).
3. **Lọc cuộc gọi cho KPI (I21).** Chỉ `call_type = one_to_one` vào KPI (số cuộc gọi bị loại được báo cáo theo nhánh); với `converted_to_group = true` thì mọi cửa sổ sau `converted_ts` không đánh giá được. `turn_utilization_p95` được miễn: tính trên toàn bộ tải kể cả cuộc gọi nhóm.
4. **Nhiều thiết bị (I20).** Attempt `connected` chỉ ghép với decision/allocation của thiết bị có `device_id = call_outcome.answered_device_id`. Quy tắc ghép allocation↔ICE gồm `device_id`; allocation còn hiệu lực khi `response_ts ≤ mốc < released_ts`, mốc = `ice_connected_ts` (hoặc `start_ts` nếu attempt thất bại), `released_ts` null = còn hiệu lực.
5. **Phân loại PCR (contract §13.2), tính từ KPI-grade, đọc `event_ts_corrected`.** `poor` gồm **ba nhánh rời nhau**: `setup_fail` (= `answered ∧ ¬connected ∧ end_reason ≠ app_crash`, gồm `ice_failed` và người dùng bỏ máy khi media chưa nối được), `drop` (= `dropped`), `quality_bad` (= `answered ∧ connected ∧ ¬dropped ∧ quality_poor`). `unclassifiable = answered ∧ connected ∧ ¬dropped ∧ quality_unknown` **rời với poor**, nên `pcr_itt_high − pcr_itt_low = unclassifiable_rate`. `fact_call` thêm `poor_category` ∈ {`setup_fail`, `drop`, `quality`, `none`} và `quality_assessment_status`. Phân vị dùng `quantile_cont`.
6. **Probe và health.** Probe (`call_id = null`) lưu ở `path_leg_measurement` với `granularity = epoch_summary`, `network_epoch = null`, khoảng [`window_start_ts`, `window_end_ts`] (ví dụ 5 phút); probe cấp **feature** (`feat_leg_stats` nguồn `inband`/`idle_probe`, `feat_turn_turn` nguồn `inband`/`mesh_probe`), **không** vào KPI. `feat_leg_stats.direction` ∈ {`user_to_turn`, `turn_to_user`}, suy từ `side` + `direction` (caller/forward và callee/reverse là `user_to_turn`). Thống kê: `w = 0.5^(tuổi_ngày/7)`, `n_eff = Σw`, `p50_shrunk = (n_eff·p50 + m·p50_cha)/(n_eff + m)` với `m = 30`. Feature store cung cấp **mọi cấp** backoff; cấp dùng do **Đoàn** chọn và ghi vào `score_components.backoff_level` của từng candidate. Pipeline cũng dựng `health_snapshot` mỗi phút từ `turn_health_1m` (contract §9.7, I12/I13).
7. **DQ `release_regression` (contract §8.5).** Check phân phối theo `app_version`: metric lệch đột ngột ngay sau một bản phát hành ⇒ WARN `release_regression`, để không đổ lỗi nhầm cho TURN. Lệch nghiêm trọng ⇒ **cách ly** metric đó của bản app (không đánh giá được) cho tới khi có quy tắc sửa được duyệt; pipeline **không tự đoán và sửa đơn vị**. Cắt theo `platform` và `app_version` để lỗi của một phiên bản không lẫn vào chất lượng TURN.

---

## 8. Bài toán chọn và xử lý selection bias khi đánh giá

### 8.0 Hình thức hóa bài toán chọn (research/07 §3.1)

Với Pattern 1 (mỗi phía một TURN riêng, BE không nằm trên đường media), chi phí của một cặp (r_A, r_B):

```
J = L(A, r_A) + L(r_A, r_B) + L(r_B, B)
```

- Hai phía **chỉ ghép với nhau qua số hạng giữa** `L(r_A, r_B)`, cộng thêm trường hợp dùng chung một TURN (`relay_same`, r_A = r_B, số hạng giữa = 0, khi đó J = L(A, r) + L(r, B) và bài toán là joint hoàn toàn). Khi đoạn giữa không đáng kể thì J tách rời và chọn gần nhất từng bên là xấp xỉ tốt.
- **Nội địa** (đoạn giữa nhỏ): nearest-per-side là xấp xỉ tốt. **Xuyên lục địa** (đoạn giữa lớn, phụ thuộc cặp): joint ranking mới có giá trị. Đây là chỗ bảo vệ bài toán joint caller+callee của đề tài. Kết luận này là suy luận (research/07 gắn nhãn [K]), kiểm chứng trên simulator bằng `joint_path_regret` (contract §14.6) so với tổng regret từng bên.
- **Phát hiện của Via (SIGCOMM 2016):** relay giúp ít khi nghẽn nằm ở last-mile của một phía; khi đó chọn TURN gần hơn có tác dụng lớn hơn, còn đổi relay/đoạn giữa giúp ít. Vì vậy cần chỉ số chẩn đoán **`poor_bottleneck_share`** (contract §13.3): trong các cuộc gọi poor, tỉ lệ có chặng tệ nhất là `user_turn` (last mile, đổi TURN ít giúp được) so với `turn_turn` (đổi TURN có thể giúp). Chỉ số này cho biết trần cải thiện của mọi policy chọn TURN, và được dùng để diễn giải kết quả (không dùng để kết luận thắng/thua).

### 8.1 Selection bias

**Vấn đề:** chỉ đường rank 1 × rank 1 được đo. Nếu policy hoàn toàn deterministic thì **không thể** ước lượng đúng kết quả của đường chưa đi (điều kiện overlap). Giải bằng 5 lớp:

| # | Cơ chế | Loại | Ghi chú |
|---|---|---|---|
| 1 | **Gộp chặng giữa các cuộc gọi**, dựng mô hình `ms_chặng ~ f(phân khúc, TURN, giờ, network)` (Direct Method) từ `path_leg_measurement[epoch_summary]` | Thuật toán | Không lấp được chặng chưa từng được đo |
| 2 | **Mesh probe** cho chặng giữa (§5.2) và **idle probe** cho chặng user (§5.3) | Thiết lập dữ liệu | Gần như không lệch. Pre-allocation (§5.1) **không** thuộc lớp này vì không cho số đo chặng |
| 3 | **ε-exploration có propensity:** mỗi bên, xác suất 1−ε đi rank 1, ε chia đều cho các rank 2–4 đã qua health filter. Không explore khi có sự cố hoặc user mạng yếu. Propensity ghi trong `candidates[].propensity` (tổng = 1, I3); `joint_propensity = p_caller × p_callee` | Thiết lập dữ liệu | ε mặc định 0 (giống production); thí nghiệm với 2% và 5% |
| 4 | **IPS / SNIPS / Doubly Robust** để đánh giá policy mới trên log cũ (thư viện `obp`) | Thuật toán | Propensity được clip để giảm phương sai |
| 5 | **Fallback tự nhiên** (rank 1 lỗi nên đi rank 2) | Dữ liệu | Bị lệch vì xảy ra lúc mạng tệ; chỉ dùng kèm biến điều chỉnh |

**Thí nghiệm then chốt** (chỉ simulator làm được): với ε ∈ {0, 2%, 5%}, so sai số của ước lượng naive / DM / IPS / DR với **regret thật** (3 loại regret, tính khả thi theo truth: contract §14.6). Báo cáo cả chi phí exploration (`pcr_itt` tăng bao nhiêu).

**So sánh policy trên simulator** theo contract §14: môi trường cô lập theo policy, seed là đơn vị độc lập, power analysis, luật kết luận chéo hai cận. OPE trên log của một policy là công cụ bổ sung, không thay cho so sánh này.

---

## 9. KPI Dictionary

**Định nghĩa duy nhất nằm ở `docs/contracts/data-contract.md` §13** (bản máy đọc: `contracts/kpi.yaml`). Spec này không lặp lại công thức. Tóm tắt các tầng:

- **Tầng 1, metric chính:** `pcr_itt` (hai cận low/high), cohort = mọi `call_session` `one_to_one` đã được gán nhánh (I21). `poor` là ba nhánh rời nhau (`setup_fail`, `drop`, `quality_bad`); `unclassifiable` rời với poor nên `pcr_itt_high − pcr_itt_low = unclassifiable_rate`. Tầng 1b: `pcr_answered` (có điều kiện); thành phần rời nhau cùng mẫu số cohort: `setup_fail_rate` (tách tiếp thành `ice_fail_rate` = `end_reason = ice_failed` và `setup_abandon_rate` = phần còn lại), `drop_rate`, `quality_poor_rate`, `unclassifiable_rate`; phễu có công thức trong contract §13.3 (`invite_delivered_rate`, `answer_rate`, `selector_timeout_rate`, `static_fallback_rate`, `p2p_rate`, `app_crash_rate` — crash ngoài phạm vi TURN nên không tính poor, nhưng báo riêng theo nhánh).
- **Tầng 2, guardrail** (non-inferiority, margin δ và ngưỡng tuyệt đối trong contract §13.3, luật kết luận §14.4): `setup_fail_rate` (tên cũ `ice_fail_rate`, nay là thành phần con), `drop_rate`, CST kỹ thuật, TTFM sau bắt máy, API Selector P95 và availability (tính từ `selector_decision`, mỗi `decision_id` một lần, `decision_mode = live`), static fallback, TURN utilization, `unclassifiable_rate`, `pcr_itt_high` theo `pair_group`. Mốc thời gian dùng `event_ts_corrected`; mọi KPI theo TURN dùng `actual_turn_id`.
- **Tầng 3, chẩn đoán** (không dùng để kết luận thắng/thua): PNR, MOS, population RTT/loss/jitter, rank-of-used, calibration, coverage, ESS, HHI, regret, `setup_breakdown_post_answer`, `signaling_overhead_est_ms`, `poor_bottleneck_share`...

Ngữ nghĩa percentile: `call_*` = trong một cuộc gọi, `population_*` = giữa các cuộc gọi trên giá trị cấp cuộc gọi; không bao giờ lấy trung bình các P95. Phân vị dùng nội suy tuyến tính (`quantile_cont`).

**Luật kết luận (contract §14.4):** `UpperCI95`/`LowerCI95` là hai đầu của khoảng tin cậy hai phía 95% (98.33% cho `pair_group`) bằng t-interval trên R giá trị theo seed. Guardrail tương đối: "+x%" nghĩa là δ = x% × trung bình qua seed của G(Geo); **đạt** ⇔ `UpperCI95(ΔG) < δ`, **vi phạm** ⇔ `LowerCI95(ΔG) > δ`. Guardrail tuyệt đối: đạt ⇔ `UpperCI95(G) ≤ x` (hoặc `LowerCI95(G) ≥ x` nếu cao = tốt), vi phạm ⇔ `LowerCI95(G) > x` (hoặc `UpperCI95(G) < x`). `d_r` tính trên **toàn bộ cuộc gọi gộp chung** có `initiated_ts` sau burn-in (không lấy trung bình tỉ lệ theo ngày).

**Quy tắc thống kê dùng chung:**
- Segment có n < 30 thì ẩn. n < 100 thì không xếp hạng.
- Tỉ lệ đi kèm Wilson CI. Segment cold-start dùng shrinkage Beta-Binomial.
- Khi quét nhiều segment thì hiệu chỉnh Benjamini-Hochberg.
- So sánh giữa các nhóm có pha trộn mạng khác nhau thì chuẩn hóa theo network type (chống nghịch lý Simpson).
- Ngưỡng PoorWindow/PoorFraction là **SLO nội bộ tạm thời** (A10), có sensitivity bắt buộc (contract §14.5), cùng `connection_mode = pre_connect` và `ice_transport_policy = all`.

---

## 10. Kịch bản bắt buộc: dữ liệu và kiểm chứng

Có hai loại kịch bản (contract §12), không được lẫn nhau:
- **Kịch bản cuộc gọi** (`scenario_tag` trong `call_session`): chỉ mô tả *loại cuộc gọi*, không bao giờ mã hóa sự cố ẩn.
- **Kịch bản hệ thống** (chỉ nằm trong manifest của lần chạy `scripted`, không bao giờ là tag cuộc gọi).

**Kịch bản cuộc gọi**

| ID | Kịch bản | Simulator tạo bằng | Dashboard hoặc test phải cho thấy |
|---|---|---|---|
| S01 | HCM Viettel ↔ HCM Viettel | Traffic nội vùng | TURN SGN-Viettel đứng top, CST thấp |
| S02 | HCM Viettel ↔ HN VNPT | Khác miền | So đường SGN×HAN với DAD×DAD; chặng giữa từ mesh |
| S03 | HCM Viettel ↔ HCM FPT | `isp_penalty` | Chi phí khác ISP, chọn TURN host ISP nào |
| S04 | HCM Viettel ↔ SG Singtel | Quốc tế có TURN | SGN×SG, chất lượng theo giờ |
| S05 | HCM VNPT ↔ Đài Loan 4G | TW không có TURN | TW đi qua HK hay JP hay SG; so với nước có TURN |
| S06 | SG ↔ JP | Intl cùng khu vực | Joint ranking cho cả hai đầu |
| S07 | JP ↔ DE | Intl khác khu vực | Đường dài, chặng giữa chiếm phần lớn |
| S09 | Cold-start | Quốc gia/ISP ít mẫu | CI rộng, shrinkage, confidence thấp, coverage |
| S10 | Network change | Đổi epoch giữa cuộc gọi | KPI theo epoch, ICE restart, drop |
| S00 | Background | Phần còn lại của traffic | Nền để tính KPI chung |

**Kịch bản hệ thống** (chạy `scripted`, mỗi kịch bản có kỳ vọng công khai; S21–S25 là kịch bản production của contract v0.4.0, §6.3b)

| ID | Kịch bản | Kiểm tra |
|---|---|---|
| S08 | TURN failure | Health filter, tỉ lệ fallback, thời gian phát hiện |
| S11 | TURN overload | Feedback loop dồn traffic, `turn_utilization_p95` |
| S12 | ISP congestion | Suy giảm theo ISP |
| S13 | Regional outage | Sự cố cả miền |
| S14 | Asymmetric path | Hai hướng forward/reverse khác nhau |
| S15 | Selector timeout | `static_fallback`, I14, `selector_availability` |
| S16 | Stale snapshot | Snapshot cũ, `feature_snapshot_age_s` |
| S17 | Delayed telemetry | Event trễ, I13 |
| S18 | TURN recovery | Phục hồi sau sự cố |
| S19 | P2P preferred | Chạy với `ice_transport_policy = all` (mặc định `relay` không có P2P, I18): `p2p_rate`, cohort ITT vẫn gồm cuộc gọi P2P |
| S20 | Call burst | Tải đột biến |
| S21 | Multi-device ring (`S21_multi_device_ring`) | Người nghe có 2–3 thiết bị cùng đổ chuông, chỉ một thiết bị bắt máy. **Mỗi thiết bị có một request `refined` và một `decision_id` riêng**; ICE attempt trỏ `decision_id` của thiết bị bắt máy; `answered_device_id`, `n_devices_rung`; allocation của thiết bị khác có `release_reason = other_device_answered`; I20 pass và không có decision/allocation của thiết bị không bắt máy bị ghép vào attempt `connected` |
| S22 | Group call filtered (`S22_group_call_filtered`) | Có cuộc gọi `call_type = group` và cuộc gọi 1-1 `converted_to_group = true` (kèm `converted_ts`). Cả hai **không vào KPI** (I21): cohort `pcr_itt` và mọi guardrail giống hệt khi bỏ các cuộc gọi này đi; cửa sổ sau `converted_ts` không đánh giá được |
| S23 | TURN pool hostname (`S23_turn_pool_hostname`) | Một hostname chung (ví dụ `turn-pool.example.com`) trỏ tới nhiều máy trong `dim_turn_endpoint` (ví dụ 198.51.100.20 → `VN-SGN-viettel-01`, 198.51.100.21 → `VN-SGN-viettel-02`). Client rơi vào máy khác máy Selector chọn: I19 bắn, `turn_identity_mismatch_rate` > 0, `actual_turn_id` đúng khi có IP, `turn_identity_method = ambiguous` khi chỉ có hostname |
| S24 | Raw-stats derivation (`S24_raw_stats_derivation`) | Cùng một dữ liệu chạy hai lần: `derivation = sdk` và `derivation = pipeline` (SDK gửi `call_stats_5s` 100%, I22). `call_stats_epoch` phải **giống hệt** nhau (derivation-equivalence). Ngoài test này, mỗi endpoint chỉ có **một** `derivation` vào KPI (contract §5.7) |
| S25 | App release regression (`S25_app_release_regression`) | Một `app_version` mới (đang staged rollout) báo jitter bằng **giây** thay vì ms. DQ `release_regression` phải cắm cờ phiên bản đó và **cách ly** metric jitter của nó (contract §8.5, không tự sửa đơn vị). PCR theo TURN (`actual_turn_id`) của lần chạy cùng seed không có lỗi phải nằm trong khoảng [`pcr_itt_low`, `pcr_itt_high`] của lần chạy có lỗi |

Phải có kịch bản **Geo thắng**, kịch bản **Historical thắng** và kịch bản **Smart thắng**. Mỗi kịch bản có một test end-to-end trên profile `dev`.

---

## 11. Dashboard (Streamlit)

| Trang | Nội dung chính | Bộ lọc |
|---|---|---|
| Overview | KPI chính (`pcr_itt` hai cận), xu hướng 30 ngày, nhãn nguồn dữ liệu | ngày, nguồn, `platform`, `app_version`, `device_class` |
| TURN Việt Nam | Heatmap miền-user × miền-TURN, ISP-user × ISP-host; P50/P95; theo giờ. **TURN được xác định bằng `actual_turn_id`** (§7.3), tính theo từng đầu; nhóm "pool" (`ambiguous`) hiển thị riêng | miền, ISP, TURN (`actual_turn_id`), network, giờ, `platform`, `app_version`, `device_class` |
| TURN Quốc tế | Bản đồ quốc gia → TURN location; nước có và không có TURN (theo `actual_turn_id`) | country, region, `platform`, `app_version`, `device_class` |
| Caller ↔ Callee | Ba nhóm VN-VN / VN-Intl / Intl-Intl; ma trận cặp | nhóm, cặp |
| Call Quality | CST, TTFM, RTT media, Loss, Jitter, thành phần rời nhau của `pcr_itt` (`setup_fail_rate` tách `ice_fail_rate` / `setup_abandon_rate`, `drop_rate`, `quality_poor_rate`, `unclassifiable_rate`) và phân bố `poor_category`; MOS và PNR hiển thị là chẩn đoán. **Biểu đồ setup-breakdown** (`setup_breakdown_post_answer`: P50/P95 từng đoạn, chỉ `post_answer`) | `be_region`, `platform`, `app_version`, `device_class` |
| Service Health | Availability, API P95 (từ `selector_decision`, mỗi `decision_id` một lần), error, fallback, freshness. **Panel `turn_identity_mismatch_rate`** (I19): tỉ lệ cuộc gọi mà `actual_turn_id` khác `turn_id` Selector chọn, theo hostname/pool, TURN, ngày; số cuộc gọi `ambiguous`. Đây là chẩn đoán vận hành, không phải lỗi dữ liệu | TURN, ngày |
| Algorithm Quality | `pcr_itt` low/high và cận chéo theo policy (kèm CI theo seed), **guardrail** (non-inferiority so với margin), **regret** (in-list, feasible-global, joint-path), rank-of-used, coverage, HHI, ESS, kết luận Smart tốt hơn / tệ hơn / INCONCLUSIVE (CI là t-interval hai phía trên seed) | policy (`geo_baseline` / `historical` / `smart`), ε, seed, `platform`, `app_version`, `device_class` |
| Data Quality | `dq_results` (FAIL/WARN, I1–I24), **WARN `release_regression` theo `app_version`**, orphan, event trễ, lệch đồng hồ, **`unclassifiable_rate`**, **phân bố `stats_status`** (`kept_critical`, `kept_sampled`, `not_sampled`, `truncated`, `lost`) | run, bảng |
| Decision Trace | Nhập `call_id` → timeline: context → 4 TURN/bên + score → allocation → đường đi → stats theo chặng (dữ liệu diagnostic nếu cuộc gọi được lấy mẫu, nếu không thì hiện `stats_status`) → outcome | |
| Insights | Bất thường tự phát hiện (robust z, EWMA/CUSUM) kèm bằng chứng; **`poor_bottleneck_share`** (cuộc gọi poor tệ ở last mile hay chặng giữa, §8.0) | |

Dashboard **chỉ đọc `mart/`** (và `clean/` cho Decision Trace), không bao giờ đọc `truth`. Riêng trang "Sim Validation" là ngoại lệ, được đánh dấu rõ. Số liệu diagnostic không được dùng làm KPI trên các trang kết luận (I16).

---

## 12. Data Contract v0.4.0 (tóm tắt — bản đầy đủ và chuẩn: `docs/contracts/data-contract.md`)

Viết dưới 3 dạng sinh từ một nguồn (`contracts/models.py` Pydantic v2): **JSON Schema** (trung lập ngôn ngữ, Java Spring Boot đọc được), **Postgres DDL** (dành cho pilot), cộng `contracts/kpi.yaml` (KPI Dictionary máy đọc).

| Nhóm | Bảng | Mục contract |
|---|---|---|
| Dimension | `dim_turn` (SCD2), `dim_asn`, `dim_user` | §3 |
| Luồng cuộc gọi, **KPI-grade** | `call_session`, `selector_decision`, `turn_allocation`, `ice_attempt`, `call_outcome`, `call_stats_epoch`, `path_leg_measurement[epoch_summary]` | §5 |
| Luồng cuộc gọi, **diagnostic** | `call_stats_5s`, `path_leg_measurement[window_5s]`, `ice_candidate_pair` (tùy chọn) | §5, §6.3 |
| Hạ tầng | `turn_health_1m`, `service_health_1m` | §6 |
| Clean-layer / fact | `fact_call`, `dq_results` và các cột phái sinh | §8 |
| Feature store | `feat_leg_stats`, `feat_turn_turn`, `feat_turn_health`, `feat_path_history`, `feat_callee_prior`, `feat_turn_alloc_latency` | §9 |
| Hồ sơ lần chạy | `run_manifest` | §12 |
| **Ẩn** | `truth_leg_5m`, `incident_truth`, `dirt_log` | §11 |

- Quy ước chung (UTC, đơn vị, `unknown` vs `null`, hash tất định SHA-256), cột chung của mọi event (`event_id`, `contract_version`, `data_source`, `producer`, `event_ts`, `ingest_ts`, `sim_run_id`, `dt`) và enum: contract §1–§2.
- v0.3.0 chỉ **bổ sung** (MINOR): kiến trúc hai mặt phẳng §0.2, enum `ice_transport_policy`, `call_session.{ice_transport_policy, be_region, be_instance}`, `call_outcome.{caller,callee}_signaling_rtt_ms`, I18, KPI chẩn đoán `setup_breakdown_post_answer` / `signaling_overhead_est_ms` / `poor_bottleneck_share`.
- v0.4.0 (sẵn sàng cho production, contract §0.3) thêm: `dim_turn_endpoint`; thông tin client trong `ctx`; `device_id` trên mọi bảng phía client; `call_type`, `converted_*`, `answered_device_id`; `turn_url`, `turn_server_ip`, `relayed_ip*`; `derivation`, `window_s` của `call_stats_epoch` và bảng `call_stats_5s` đầy đủ; `health_snapshot` mỗi phút (§9.7); I19–I24; kịch bản S21–S25; câu hỏi Q9–Q12. v0.4.0 cũng gồm **sửa theo audit độc lập** (cùng số version): `poor` thành ba nhánh rời nhau, guardrail `ice_fail_rate` → `setup_fail_rate`, quy tắc cửa sổ chặt hơn, luật kết luận §14.4 có định nghĩa CI.
- API Selector (`POST /v1/turn/select`) và interface nội bộ `select(req, rng)`: contract §10.
- **Privacy:** `user_hash` là HMAC-SHA256 có salt, geo chỉ tới cấp thành phố, không lưu IP thô.
- Quy trình đổi version: contract §16 (PR sửa tài liệu **và** `contracts/`, Hiệp và Đoàn cùng approve).

---

## 13. Công nghệ và cấu trúc repo

- **Python 3.12**, `.venv`, DuckDB, Polars, Pydantic v2, pandera, numpy/scipy, Streamlit, plotly, obp, pytest.
- Raw sink mặc định là JSONL. **Postgres (Docker, đã có) là sink thứ hai**, chạy từ W2, để pipeline đọc qua `postgres_scanner` giống lúc pilot.
- **Chung một repo với Đoàn.** `contracts/` là nguồn chung. Mọi PR đụng tới `contracts/` cần cả hai duyệt.
- **Data Contract chi tiết:** `docs/contracts/data-contract.md`.
- **Chính sách lần chạy:** mỗi lần chạy sim ghi một `run_manifest` JSON (contract §12) cạnh kết quả và được commit cùng kết quả. Mỗi (policy, seed) có `environment_dir` riêng (feature store, health state, tải TURN, cache), không dùng chung giữa các policy.

```
contracts/           # models.py, schemas/*.json, ddl/*.sql, kpi.yaml (nguồn chung với Đoàn)
configs/             # world.yaml, sim_dev.yaml, sim_main.yaml, incidents.yaml (ẩn)
src/turnintel/
  sim/               # world, truth, incidents, traffic, policy, call_engine, probes, health, dirt, runner (+ run_manifest, RNG có khóa)
  pipeline/          # adapters/, clean, dq, fact, features, marts, orchestrator
  eval/              # ope, regret, anomaly, incident_scoring
dashboard/           # app.py + pages/
data/                # raw, clean, feature, mart, truth, external, runs/<environment_dir>  (gitignore, trừ run_manifest)
tests/               # unit + e2e kịch bản (profile dev)
docs/                # research/, specs/, contracts/, reports/
```

---

## 14. Kiểm chứng (testing)

1. **Unit:** adapter, chuẩn hóa đơn vị, dedup, hiệu chỉnh đồng hồ, các hàm KPI (P95 đúng, Wilson CI, PoorFraction/`pcr_itt`), propensity.
2. **Contract:** mọi event do sim sinh ra đều qua JSON Schema. Fixture Zenodo đi qua adapter `zenodo`.
3. **Schema↔kpi.yaml (I16):** KPI chính và guardrail trong `contracts/kpi.yaml` chỉ tham chiếu bảng KPI-grade; test tự động đọc `kpi.yaml` đối chiếu schema.
4. **Idempotent:** chạy pipeline 2 lần trên cùng một ngày thì mart giống hệt nhau.
5. **Late-event snapshot (I13):** event có `ingest_ts ≥ cutoff_ts` không bao giờ lọt vào snapshot đó dù `event_ts < cutoff_ts`; event trễ chỉ xuất hiện ở snapshot sau.
6. **Snapshot `content_hash`:** dựng lại snapshot từ raw và cấu hình đã lưu cho ra cùng `content_hash`; snapshot đã publish không bị sửa (backfill tạo `v<n+1>`); I12 (`published_ts ≤ request_ts`).
7. **RNG có khóa tất định:** cùng `run_manifest` ⇒ cùng hash dữ liệu; đổi policy không làm đổi các luồng ngoại sinh (traffic, bắt máy, nhiễu mạng) của cùng seed.
8. **Sampling (I17):** `stats_sampling_prob` khớp quy tắc critical 100% + SHA-256 10% khi tính lại từ `call_id` và outcome; hash dùng SHA-256 UTF-8, 8 byte big-endian (không dùng `hash()` của ngôn ngữ).
9. **DQ recall ≥ 95%** trên lỗi tiêm từ `dirt_log`.
10. **Bất biến I1–I24:** pass trên dữ liệu sạch; từng bất biến FAIL/WARN bị bắt trên dữ liệu có lỗi chủ đích. Riêng **I18**: với `ice_transport_policy = relay`, mọi attempt `connected` có `path_type ∈ {relay_relay, relay_same}`; dữ liệu chủ đích chèn một attempt `p2p_host` vào cuộc gọi `relay` phải bị bắt (FAIL), còn lần chạy `all` thì không bị I18 bắt.
11. **Cấm đọc truth:** test tự động cấm `selector`, `pipeline`, `features`, `dashboard` import hoặc mở `data/truth/` (contract §11). Policy không tạo RNG toàn cục.
12. **Kịch bản:** e2e cho kịch bản cuộc gọi và kịch bản hệ thống (§10).
13. **BE-invariance** (chạy trên kịch bản scripted có truth không đổi theo thời gian và health không đổi; nhiễu khóa theo `window_idx` tương đối với neo endpoint; độ trễ BE ↔ Selector không phụ thuộc `be_region`, A18): cùng seed và cùng policy, chạy với hai `be_region` khác nhau (ví dụ `SGN` và `HAN`) phải cho **KPI media giống hệt nhau** (`pcr_itt` low/high và mọi chỉ số chất lượng: RTT/loss/jitter, `poor`, `unclassifiable`, guardrail về media), và **chỉ** các chẩn đoán thời gian thiết lập thay đổi (`setup_breakdown_post_answer` đoạn `answer_ts → checks_start_ts`, `signaling_overhead_est_ms`, `*_signaling_rtt_ms`). Bảo đảm BE không rò vào đường media (§6.3a).
14. **Đánh giá các bộ đánh giá:** sai số của DR so với regret thật phải nhỏ hơn naive; precision/recall và độ trễ phát hiện trên `incident_truth`; luật kết luận §14.4 (t-interval hai phía, điều kiện đạt/vi phạm tường minh) trả đúng Smart tốt hơn / tệ hơn / INCONCLUSIVE trên dữ liệu có đáp án.
15. **Bất biến production (contract v0.4.0), mỗi bất biến một test FAIL/WARN có chủ đích:**
    - **I19:** chèn một cuộc gọi có `relayed_ip` thuộc máy khác máy Selector chọn ⇒ WARN `turn_identity_mismatch`; cuộc gọi đúng máy thì không.
    - **I20:** attempt `connected` có `callee_device_id` khác `answered_device_id` ⇒ FAIL; decision/allocation của thiết bị không bắt máy không được ghép vào attempt.
    - **I21:** cuộc gọi `group` và `converted_to_group` không vào KPI; cửa sổ sau `converted_ts` không đánh giá được; `turn_utilization_p95` vẫn tính trên toàn bộ tải.
    - **I22:** endpoint `derivation = pipeline` thiếu cửa sổ do bị lấy mẫu (không phải do gửi thất bại) hoặc khác `window_s`/`quality_rule_version` ⇒ FAIL.
    - **I23:** `end_reason = ice_failed` mà `connected = true`, hoặc `answered ∧ ¬connected` với `end_reason` ngoài {`ice_failed`, `normal_hangup`, `app_crash`, `unknown`} ⇒ FAIL.
    - **I24:** `dropped = true` mà `end_reason` không phải `dropped_network`/`dropped_turn` (và ngược lại; `app_crash` không phải drop) ⇒ FAIL.
16. **Derivation-equivalence:** trên cùng dữ liệu (độ lệch đồng hồ = 0), `call_stats_epoch` do SDK tính và do pipeline tính từ `call_stats_5s` (đủ cột contract §5.8) giống hệt từng byte, gồm neo theo endpoint, epoch theo điểm giữa, key bucket chuẩn và `event_id` UUIDv5 tất định (S24).
17. **Phân loại PCR:** `setup_fail`, `drop`, `quality_bad` rời nhau từng cặp; `unclassifiable` rời với `poor`; `pcr_itt_high − pcr_itt_low = unclassifiable_rate` trên mọi lần chạy; `poor_category` khớp; cuộc gọi `answered ∧ ¬connected ∧ end_reason = app_crash` không phải `setup_fail`.
18. **Một test cho mỗi kịch bản S21–S25** (e2e profile `dev`): S21 multi-device ring (mỗi thiết bị một `decision_id`, I20 pass), S22 group call (bị lọc khỏi KPI), S23 pool hostname (I19 bắn, `turn_identity_mismatch_rate` > 0, `ambiguous` khi chỉ có hostname), S24 raw-stats derivation (như mục 16), S25 app release regression (DQ `release_regression` cắm cờ đúng `app_version`, metric bị cách ly, và PCR theo `actual_turn_id` của lần chạy không lỗi nằm trong khoảng [low, high] của lần chạy có lỗi).
19. **Privacy:** (a) không bao giờ lưu IP của candidate không phải `relay` (`host`/`srflx`/`prflx`), không lưu `relatedAddress`/`relatedPort`; (b) **mọi IP được lưu** (`turn_server_ip`, `relayed_ip`, `relayed_ip_*`) đều có trong `dim_turn_endpoint`; (c) `be_instance` là tên, không phải IP. Quét toàn bộ raw/clean bằng regex IP và đối chiếu với `dim_turn_endpoint`.
20. **Danh tính TURN:** `actual_turn_id` theo đúng thứ tự ưu tiên (relayed_ip của cặp được chọn → allocation `relayed_ip` → `turn_server_ip` → hostname duy nhất); nguồn mâu thuẫn ⇒ I19; KPI theo TURN góp theo từng đầu (`relay_same` một lần); `path_type` khớp bảng ánh xạ contract §2.

---

## 15. Lịch theo tuần (phần của Hiệp)

| Tuần | Giao |
|---|---|
| W1 (04–10/11) | Spec này, Data Contract v0.4.0 chốt với Đoàn (đủ `kpi.yaml`), world.yaml, khung simulator (world, truth, traffic, geo_baseline) |
| W2 (11–17/11) | Call engine, raw → clean → fact, DQ cơ bản, profile dev và main, **Dashboard V1** (TURN VN/Intl theo vùng, country, ISP, network) → **Sprint 1 18/11** |
| W3 (18–24/11) | Rolling loop (snapshot cutoff/published, burn-in), feature store, probes, health, trang TURN Performance và Service Health |
| W4 (25/11–01/12) | Cắm policy của Đoàn, exploration và propensity, trang Algorithm Quality và Decision Trace, filter và drill-down → **MVP 02/12** |
| W5 (02–08/12) | **Power analysis (3 seed thử nghiệm ước lượng phương sai, chốt R trong manifest) và seed replication**; so Geo với Smart theo contract §14, OPE và thí nghiệm ε, sensitivity (gồm `pre_connect`), thí nghiệm hiệu chỉnh `alloc_ms`, anomaly detection, mở incidents → ≥3 insight |
| W6 (09–15/12) | Adapter Postgres cho pilot, hoàn thiện tài liệu và báo cáo, đề xuất cải tiến (thiết kế pilot switchback: contract §14.7) → **Final 15/12** |

---

## 16. Sổ giả định (cập nhật khi có thông tin)

| # | Giả định | Nguồn hoặc lý do | Ảnh hưởng nếu sai |
|---|---|---|---|
| A1 | k=4 mỗi bên, đi rank 1 × rank 1, fallback theo rank | Mentor (qua Hiệp) | Đề bài ghi 8 → để tham số |
| A2 | Production có số đo chặng liên tục kèm loss/jitter/outcome, mỗi dòng ghi `measurement_kind` và `clock_sync_err_ms` (contract Q4, phương pháp đo **chưa xác minh**) | Hiệp | Chỉ có RTT thì chặng ước lượng là `one_way_ms_estimated` (cờ `symmetric_assumption`), chỉ dùng cho phân rã/feature, **không bao giờ làm nhãn PCR** |
| A3 | Pre-allocation 4 TURN, mesh probe, idle probe | Đề xuất của nhóm (§5) | Mặc định **tắt** trong profile "giống production". Pre-allocation cho thống kê allocation latency, không cho số đo chặng |
| A4 | Topology 22 TURN | Nhóm tự thiết kế | Thay `world.yaml` |
| A5 | Phạt khác ISP trong VN 3–15 ms | Không có dữ liệu công khai | Có sensitivity analysis |
| A6 | Schema DB công ty chưa có | Mentor | Adapter `postgres` viết ở W6 |
| A7 | Policy production hiện tại deterministic (ε=0) | Suy ra | Có ε thì OPE dễ hơn |
| A8 | Đoàn cần feature theo segment có backoff nhiều cấp (contract §9) | Thiết kế của Hiệp | Đoàn duyệt ở W1 |
| A9 | `connection_mode = post_answer` (ICE bắt đầu sau khi bắt máy) | Mặc định chưa xác minh (contract Q5) | Nếu thực tế là `pre_connect`: tải TURN tăng do allocation lúc đổ chuông, KPI thay đổi. Chạy sensitivity `pre_connect`; thứ hạng đổi ⇒ kết luận "phụ thuộc giả định" |
| A10 | Ngưỡng PoorWindow (RTT ≥ 300 ms, loss ≥ 3%, jitter ≥ 30 ms) và PoorFraction ≥ 0.20 là **SLO nội bộ tạm thời**, không suy ra từ G.114 | Nhóm; đóng băng trong `kpi.yaml` trước `blind_benchmark` đầu tiên | Sensitivity 200/300/400, 1/3/5, 10/30/50, 0.1/0.2/0.3; đổi chiều ⇒ ghi "phụ thuộc giả định" |
| A11 | Selector không chặn lời mời gọi: lỗi/timeout ⇒ `static_fallback` (I14); gán nhánh trước quyết định (I15) | **Yêu cầu kiến trúc** với Signaling (Spring Boot) và Selector, không phải giả định về dữ liệu | Vi phạm thì `pcr_itt` và guardrail availability không còn diễn giải được; cần Signaling thay đổi |
| A12 | BE chỉ là backend signaling, media không đi qua BE (**xác nhận 2026-11-04**). Số lượng và vị trí BE chưa biết ⇒ tham số một cụm `be_region`, mặc định `SGN` (contract Q6) | Xác nhận của người dùng; vị trí BE là giả định | BE chỉ ảnh hưởng thời gian thiết lập, không ảnh hưởng `pcr_itt`. Sai vị trí BE chỉ làm lệch chẩn đoán setup; test BE-invariance bảo đảm điều đó. Nếu thực tế có nhiều BE thì thêm cách gán BE cho cuộc gọi (không đổi contract) |
| A13 | `ice_transport_policy = relay` là mặc định (contract Q7) | **Suy ra** từ mô tả của mentor "ICE đi TURN top 1 của mỗi bên", chưa xác minh | Nếu thực tế cho phép P2P: chạy sensitivity `all` (chạy lại toàn bộ); thứ hạng đổi ⇒ kết luận "phụ thuộc giả định" |
| A14 | Các số overhead signaling (độ trễ BE, `*_signaling_rtt_ms`) là **ước lượng** từ snapshot WonderNetwork (`docs/research/01`) cộng mô hình access, không phải số đo | Nhóm | Chỉ ảnh hưởng chẩn đoán thời gian thiết lập; không ảnh hưởng KPI media |
| A15 | Tỉ lệ nền tảng theo quốc gia (ví dụ VN: android ≈ 65%, ios ≈ 32%, web ≈ 3%), 2–3 phiên bản app với staged rollout, bảng `device_model → device_class` | **Số bịa**, nhãn giả định; không có số đo | Chỉ ảnh hưởng cách cắt KPI theo `platform`/`app_version`/`device_class` và kịch bản S25, không ảnh hưởng KPI tổng. Thay bằng số thật trong `configs/world.yaml` khi có |
| A16 | TURN được cấp cho client bằng **hostname riêng từng máy** (contract Q9); xác định máy bằng IP khi có | Mặc định của contract, chờ đội hạ tầng | Nếu thực tế dùng hostname chung của pool hoặc geo-DNS: nhiều cuộc gọi `ambiguous`, I19 bắn nhiều; KPI theo TURN dựa vào IP (`dim_turn_endpoint`) nên cần đội hạ tầng cấp danh sách IP |
| A17 | Phương án **gửi getStats thô** (`derivation = pipeline`, `call_stats_5s` 100%) chấp nhận được về băng thông (contract Q10) | Chưa xác minh với đội mobile/web | Nếu quá tốn băng thông/pin: ép dùng `derivation = sdk` (SDK tính epoch) hoặc giảm tần suất gửi lô; chưa có số đo chi phí |
| A18 | Trong simulator, độ trễ BE ↔ Selector không phụ thuộc `be_region` (BE và Selector đặt cùng chỗ) | Giả định của nhóm (contract §14.2) | Nếu khác: `be_region` có thể đổi thời điểm quyết định của Selector, test BE-invariance cần điều chỉnh |

## 17. Rủi ro

- **Simulator "quá đẹp"**, khiến thuật toán học đúng giả định của chính simulator. Giảm thiểu bằng nhiễu đuôi dài, sự cố ẩn, sensitivity analysis trên A5/A10, và chỉ báo cáo kết quả có nhãn synthetic.
- **Contract lệch giữa Hiệp và Đoàn.** Giảm thiểu bằng một nguồn `contracts/`, test contract và `kpi.yaml` trong CI, đổi version khi có thay đổi.
- **Chi phí chạy** tăng theo R seed × số policy (mỗi cặp là một môi trường cô lập). Giảm thiểu bằng power analysis để chọn R vừa đủ, profile `dev` cho test, báo cáo MDE thực tế nếu không đủ ngân sách (contract §14.3).
- **Công ty thực tế định tuyến media qua media server (SFU) thay vì A → TURN(A) → TURN(B) → B.** Khi đó mỗi bên có PeerConnection riêng tới server, `media_rtcp_rtt`, `packetsLost`, `jitter` chỉ phản ánh **nửa đường**, và định nghĩa PCR/KPI phải đổi, nên cần **MAJOR** contract (contract §0.2, §16). Đã chuẩn bị phân tích ở `docs/research/05` (kiến trúc media path), `06` (ngữ nghĩa stats qua media server), `07` (bài toán chọn khi có media server). Hiện kiến trúc đã được xác nhận là signaling-only nên rủi ro này thấp, nhưng chưa loại trừ cho tương lai.
- **Khối lượng 6 tuần.** Thứ tự ưu tiên: pipeline + DQ + Dashboard V1 trước, sau đó mới tới OPE và exploration.
- **Dữ liệu production khác simulator** (nền tảng, phiên bản app, hostname chung, nhiều thiết bị, cuộc gọi nhóm). Giảm thiểu bằng contract v0.4.0, kịch bản S21–S25 và checklist ở §18.

---

## 18. Production readiness checklist

Simulator chạy được không có nghĩa là sẵn sàng cho pilot. Phần này liệt kê những thứ **còn thiếu** để chuyển từ dữ liệu giả lập sang dữ liệu production. Không có hạng mục nào trong bảng dưới đây đã làm.

### 18.1 Hạng mục

| # | Hạng mục | Vì sao | Khi nào | Ai | Trạng thái |
|---|---|---|---|---|---|
| **P1** | | | | | |
| 1 | Bảng `ops_event`: bảo trì, sự cố, deploy của Selector/TURN/app, đứt cáp quang biển | Production không có `incident_truth`. Cần để chú thích dashboard, loại các khoảng thời gian khỏi phân tích và quy nguyên nhân cho bất thường | W6 | Hiệp + đội hạ tầng | TODO |
| 2 | `experiment_registry` production: `experiment_id`, thiết kế, các nhánh (arms), `randomization_unit`, các block switchback, washout, `kpi_yaml_hash`, thời điểm bắt đầu/kết thúc | `run_manifest` chỉ dùng cho sim. Pilot cần hồ sơ thí nghiệm có thể kiểm toán | Trước pilot | Hiệp + Đoàn | TODO |
| 3 | `call_feedback`: điểm 1–5 sau cuộc gọi và tag vấn đề | Kiểm chứng các ngưỡng PCR tạm thời (A10) với chất lượng người dùng cảm nhận | Pilot | Mentor / product | TODO |
| 4 | Đồng ý telemetry, thời hạn lưu giữ, phân loại dữ liệu cá nhân | Vị trí + thiết bị + phiên bản app + thành phố là dữ liệu cá nhân hoặc dữ liệu có thể định danh gián tiếp theo Nghị định 13/2023/NĐ-CP. Người dùng từ chối (opt-out) tạo lệch mẫu (sampling bias) | Trước pilot | Đội pháp chế công ty | TODO |
| 5 | Tín hiệu mute / hold / DTX từ SDK | Để cửa sổ bị mute được coi là "không áp dụng" thay vì "không đánh giá được" (không làm tăng `unclassifiable_rate`) | Pilot | Đội SDK | TODO |
| 6 | Chi tiết mạng: loại di động LTE/NR/3G, IPv4 hay IPv6 của candidate, SIM carrier (MCC-MNC) so với ASN của IP | Cắt KPI chính xác hơn và phát hiện lệch giữa carrier SIM với ASN mạng đang dùng | Pilot | Hiệp + đội SDK | TODO |
| 7 | Nguồn TURN health | coturn Prometheus có số allocation và bộ đếm rate-limit nhưng **không có RTT hay health** (`docs/research/06`), nên cần một health checker riêng, ánh xạ vào `turn_health_1m` | W6 | Hiệp + đội hạ tầng | TODO |
| 8 | Số byte theo allocation, từ log session của TURN server | Cho Usage và chi phí băng thông TURN quốc tế | Pilot | Đội hạ tầng | TODO |
| **P2** | | | | | |
| 9 | Version của cơ sở dữ liệu GeoIP/ASN | Tái lập phân đoạn (segment) địa lý khi DB đổi | Sau pilot | Hiệp | TODO |
| 10 | Giờ địa phương của user quốc tế | Pipeline tự suy từ quốc gia, **không cần đổi contract** | Sau pilot | Hiệp | TODO |
| 11 | Đổi cặp candidate được chọn mà không có ICE restart | Hiện không quan sát được, có thể làm sai `path_type` và epoch | Sau pilot | Đội WebRTC | TODO |
| 12 | KPI chất lượng video (freeze, độ phân giải, fps) | KPI hiện chỉ tính audio | Sau pilot | Hiệp + đội SDK | TODO |

### 18.2 Việc cần làm sớm

Xin mentor một **mẫu log thật nhỏ** (vài trăm cuộc gọi đã ẩn danh) và chạy adapter `postgres` trên đó ngay, không chờ tới W6. Mục đích: phát hiện sớm sai lệch giữa contract và telemetry thật (field thiếu, đơn vị, hostname/IP, nền tảng không hỗ trợ field), khi còn sửa được rẻ.

### 18.3 Câu hỏi mở của contract (§17)

| Q | Câu hỏi | Ai trả lời | Mặc định hiện tại | Trạng thái |
|---|---|---|---|---|
| Q1 | Đoàn cần thêm feature nào ngoài §9? | Đoàn | Như §9 | chờ |
| Q2 | Thang `score` và cách tính `confidence` | Đoàn | 0–1, cao = tốt | chờ |
| Q3 | k = 4 hay 8 | Mentor / Đoàn | 4 | chờ |
| Q4 | Production đo ms từng chặng bằng cách nào | Mentor | `measurement_kind` + `clock_sync_err_ms` bắt buộc | chờ |
| Q5 | ICE bắt đầu lúc đổ chuông hay sau khi bắt máy | Mentor / đội WebRTC | `post_answer` (giả định chưa xác minh) | chờ |
| Q6 | Số BE, vị trí, cách gán BE cho cuộc gọi | Mentor | Một cụm BE, mặc định `SGN` | chờ |
| Q7 | ICE chỉ dùng relay hay cho phép P2P | Mentor / đội WebRTC | `relay` (suy ra từ mô tả của mentor) | chờ |
| Q8 | SDK có đo RTT kênh signaling không | Mentor | Field nullable, không chặn | chờ |
| Q9 | TURN cấp cho client bằng hostname riêng, hostname chung của pool, hay IP | Đội hạ tầng | Hostname riêng; xác định máy bằng IP khi có | chờ |
| Q10 | SDK tự tính được `call_stats_epoch` hay chỉ gửi getStats thô | Đội mobile/web | Hỗ trợ cả hai (`derivation`) | chờ |
| Q11 | Người nghe có nhiều thiết bị cùng đổ chuông không | Mentor | Có thể; contract đã hỗ trợ | chờ |
| Q12 | Có cuộc gọi nhóm không, đánh dấu thế nào, 1-1 có chuyển thành nhóm được không | Mentor | `call_type`; chỉ cuộc gọi 1-1 vào KPI | chờ |

### 18.4 Định nghĩa "sẵn sàng pilot"

- Adapter parse được mẫu log thật với **≥ 95%** event qua schema validation.
- I1–I24 hoặc pass, hoặc mọi lỗi đều được giải thích.
- Q1–Q12 đã có câu trả lời, hoặc mentor chấp nhận các mặc định.
- Đã có sign-off về privacy.
- Đã có `ops_event` và `experiment_registry`.
