# TURN Intelligence — Thiết kế Simulator, Data Pipeline & Dashboard

- **Ngày:** 2026-11-04 · **Owner:** Đặng Quốc Hiệp · **Đối tác:** Đặng Đỉnh Đoàn (thuật toán + API)
- **Trạng thái:** Draft v0.2, đồng bộ với Data Contract v0.2.0, chờ Hiệp và Đoàn duyệt
- **Research nền:** `docs/research/01..04-*.md`
- **Nguồn sự thật cho schema, bất biến, KPI, luật đánh giá:** `docs/contracts/data-contract.md` (v0.2.0). Spec này **không lặp lại định nghĩa**, chỉ tóm tắt và trỏ tới mục tương ứng của contract. Mâu thuẫn giữa hai tài liệu thì contract thắng.

> Đọc nhanh: §1 → §3 (flow một cuộc gọi) → §4 (vòng lặp theo ngày) → §7 (pipeline). Các phần còn lại là tra cứu.

---

## 1. Mục tiêu và phạm vi

**Bài toán.** Thuật toán của Đoàn xếp hạng **top-4 TURN cho mỗi bên**. Cuộc gọi đi theo đường `A → TA1 → TB1 → B` (rank 1 của mỗi bên), còn rank 2–4 là dự phòng. Production **chỉ đo được đường đã đi**. Phần của Hiệp là xây hệ thống:

1. **Sinh dữ liệu** giả lập có tính thực tế, vì chưa có log thật.
2. **Xử lý dữ liệu** (pipeline + data quality) bằng code dùng lại được nguyên vẹn khi có log Call thật.
3. **Đo lường và đánh giá độc lập** chất lượng TURN, chất lượng thuật toán và sức khỏe service.
4. **Trình bày** trên dashboard chạy thật, kèm insight có bằng chứng.

**Định nghĩa "xong" (MVP 02/12, Final 15/12):**
- Simulator chạy rolling 30 ngày (sau burn-in 3 ngày), có đủ các kịch bản bắt buộc S01–S10 (§10).
- Pipeline chạy incremental theo ngày, chạy lại không đổi kết quả, và bắt được dữ liệu bẩn đã tiêm.
- Dashboard đi được từ *quyết định của thuật toán* → *đường thực đi* → *chất lượng cuộc gọi*, có Decision Trace theo Call ID.
- **Metric chính là `pcr_itt`** (Poor Call Rate, intention-to-treat, hai cận low/high; contract §13.3), không phải PNR. Kết luận Smart tốt hơn / tệ hơn / INCONCLUSIVE theo luật chéo hai cận và guardrail non-inferiority (contract §14.4), đơn vị độc lập là seed (contract §14.3). Các ngưỡng/luật được đóng băng trước `blind_benchmark` đầu tiên.
- Có ≥3 insight, mỗi insight được kiểm chứng với sự cố ẩn (precision/recall) và chạy trên `blind_benchmark` (§6.6).
- Đánh giá thuật toán **có xử lý selection bias** (§8), và được kiểm chứng bằng Network Truth.

**Ngoài phạm vi:** group call/SFU, alerting (Grafana), đo RIPE Atlas thật, M-Lab BigQuery, mọi khẳng định về cải thiện production.

**Nguyên tắc trung thực.** Mọi kết luận gắn nhãn nguồn `data_source ∈ {synthetic, lab_zenodo, public_reference, production}`. Kết quả trên simulator **không** được dùng để khẳng định production đã tốt hơn. Kết luận chỉ áp dụng cho `data_source=synthetic` với các giả định trong sổ giả định (§16).

---

## 2. Thuật ngữ

| Thuật ngữ | Nghĩa |
|---|---|
| **Leg (chặng)** | Một đoạn của đường đi: `user_turn` (user ↔ TURN của họ) và `turn_turn` (TURN ↔ TURN). Mỗi chặng có hướng `forward`/`reverse` |
| **Path (đường)** | Tổ hợp (TAi, TBj). Độ trễ một chiều forward = `user_turn(caller)` + `turn_turn(TA→TB)` + `user_turn(callee)`. Nếu TAi = TBj (`relay_same`) thì không có chặng `turn_turn` (= 0) |
| **Policy** | Thuật toán chọn TURN: `geo_baseline` (Hiệp viết) hoặc `smart_vX` (Đoàn viết) |
| **Exploration (ε)** | Tỉ lệ nhỏ cuộc gọi cố ý đi rank 2–4 để có dữ liệu cho đường chưa đi |
| **Propensity** | Xác suất policy chọn đúng đường đã đi. Bắt buộc phải log thì mới sửa được lệch |
| **Network Truth** | Chất lượng "thật" của mọi chặng, chỉ simulator biết. Dashboard **không đọc**, chỉ dùng để chấm điểm (contract §11) |
| **Oracle** | Đường tốt nhất theo Network Truth **trong số đường khả thi theo sự thật**, là mốc để tính regret (contract §14.6) |
| **PCR ITT** (`pcr_itt`) | Poor Call Rate, intention-to-treat: tỉ lệ cuộc gọi "tệ" trên **cả cohort đã được gán nhánh**, báo cáo hai cận `low`/`high`. **Metric chính.** Định nghĩa: contract §13.2–13.3 |
| **PNR** | Poor Network Rate kiểu Via. Chỉ còn là **chẩn đoán** (Tầng 3, trên cuộc gọi đã connected), không dùng để kết luận |
| **KPI-grade** | Dữ liệu gửi 100% cuộc gọi (`call_stats_epoch`, `path_leg_measurement[epoch_summary]`, `call_outcome`...). Chỉ loại này được dùng cho KPI chính và guardrail (I16) |
| **Diagnostic** | Dữ liệu lấy mẫu hoặc tùy telemetry (`call_stats_5s`, `window_5s`, `ice_candidate_pair`). Chỉ để điều tra, Decision Trace, biểu đồ chi tiết |
| **`connection_mode`** | Thời điểm ICE bắt đầu: `post_answer` (sau khi bắt máy, **mặc định, giả định chưa xác minh**) hoặc `pre_connect` (trong lúc đổ chuông) |
| **Snapshot** | Phiên bản bảng feature/health mà policy dùng khi quyết định. Có `cutoff_ts`, `published_ts`, `content_hash`, bất biến sau khi publish (contract §9.0) |

---

## 3. Flow một cuộc gọi

```
 t0  A bấm gọi: Signaling tạo call_session (gán experiment_id/arm TRƯỚC mọi quyết định) ► [call_session]
     Signaling ── Selector.select(ctx_A, ctx_B?) ────────────────────────────────────► [selector_decision]
                                  │  đọc snapshot mới nhất có published_ts ≤ t           phase=initial
                                  │  trả 4 TURN/bên + score + propensity + confidence
                                  │  Selector KHÔNG chặn lời mời; lỗi/timeout ⇒ static_fallback (I14)
 t1  Client A, B allocate (allocation_id do client sinh) ► TURN ─────────────────────► [turn_allocation]
                                  (alloc_ms = allocation latency, gồm vòng 401 + xử lý server; KHÔNG phải số đo chặng)
 t2  ring_ts: máy B đổ chuông · answer_ts: B bấm nghe ───────────────────────────────► [call_outcome]
     B bắt máy → biết ctx_B → (tùy chọn) Selector refine ───────────────────────────► [selector_decision] phase=refined
 t3  ICE (post_answer: checks sau answer_ts): start_ts → checks_start_ts →
     ice_connected_ts → dtls_connected_ts; lỗi thì fallback rank kế ─────────────────► [ice_attempt] (+attempt_seq, ice_generation,
                                                                                        allocation_id mỗi bên, loại candidate được chọn → path_type)
 t4  Media chạy. SDK tính trên thiết bị và gửi khi epoch kết thúc ────────────────────► [call_stats_epoch]  100%, cửa sổ 5 s neo tại ice_connected_ts đầu tiên
                                                                                         [path_leg_measurement] granularity=epoch_summary  100%
     chỉ cuộc gọi được lấy mẫu (critical 100% + SHA-256 10%) ────────────────────────► [call_stats_5s], [path_leg_measurement] window_5s
     đổi Wi-Fi↔4G → network_epoch+1, ICE restart (ice_generation+1) ─────────────────► [ice_attempt] restart
 t5  Kết thúc ────────────────────────────────────────────────────────────────────────► [call_outcome]
 song song: TURN↔TURN mesh probe, TURN health, Selector service health ──────────────► [path_leg_measurement] (probe, call_id=null) [turn_health_1m] [service_health_1m]
 chỉ simulator: chất lượng thật của mọi chặng, sự cố ─────────────────────────────────► [truth_leg_5m] [incident_truth] [dirt_log]  (ẩn)
```

- Toàn bộ event nối với nhau qua `call_id`, `decision_id`, `allocation_id`. Cuộc gọi lỗi **vẫn được giữ lại**, không bao giờ điền 0 (thiếu số đo thì `null` kèm lý do).
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
| `world` | Sinh `dim_turn`, `dim_user`, `dim_asn`, ma trận khoảng cách và độ trễ giữa thành phố |
| `truth` | **Network Truth**: độ trễ, loss, jitter thật của mọi chặng theo thời gian (ẩn), tách thành thành phần ngoại sinh và thành phần do tải (contract §11) |
| `incidents` | Tiêm sự cố từ lịch ẩn `incidents.yaml` (§6.6) |
| `traffic` | Ai gọi ai, lúc nào, có bắt máy không. Phân bố theo giờ trong ngày, cặp VN/quốc tế, cuộc gọi "mù" |
| `policy` | Interface `select(req, rng) -> Decision` (contract §10). Có sẵn `geo_baseline`, plug-in policy của Đoàn, wrapper ε-exploration. `rng` do simulator cấp; policy không tạo RNG toàn cục |
| `call_engine` | Allocation → ICE/fallback → media → `call_stats_epoch` → outcome, đọc từ `truth` và cộng nhiễu đo |
| `probes` | Mesh TURN↔TURN, idle probe |
| `health` | `turn_health_1m` (tải được tính từ chính traffic, nên có hiện tượng dồn traffic gây quá tải), `service_health_1m` |
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

### 6.4 Hành vi client và ICE

- Mỗi bên nhận `k=4` TURN (tham số, đặt được tới 8 cho đúng đề bài).
- Đường đi = rank 1 × rank 1. Nếu allocation hoặc ICE trên rank 1 lỗi hoặc quá timeout thì thử rank kế, và ghi `attempt_seq`, `ice_generation`.
- **`path_type` suy từ cặp candidate được chọn** (`selected_local/remote_candidate_type`), không giả định luôn là `relay_relay`. Một phần cuộc gọi trong nước kết nối **P2P** (`p2p_host`, `p2p_srflx`), khi đó `turn_used=false`; cuộc gọi P2P vẫn nằm trong cohort ITT.
- Đổi mạng giữa cuộc gọi: 3–5% cuộc gọi, kèm ICE restart, `network_epoch+1`.
- **Cuộc gọi mù:** khoảng 40% cuộc gọi lúc t0 chưa biết context của B (`info_level=caller_only`). Policy dùng `callee_prior`. Khi B bắt máy thì có quyết định `refined`.
- **`connection_mode`:**
  - **`post_answer` (mặc định)**: ICE checks chỉ bắt đầu sau `answer_ts`. Đây là **giả định chưa xác minh** (A9, contract Q5); ghi trong `run_manifest.connection_mode`.
  - **`pre_connect`** (sensitivity bắt buộc, contract §14.5): ICE chạy trong lúc đổ chuông, nên `connected` có thể true dù `answered=false` (I6 chỉ cho phép trường hợp này với `pre_connect`). Chế độ này phải **chạy lại toàn bộ** KPI chính, guardrail và tải TURN, mô phỏng **allocation sống trong lúc đổ chuông kể cả cuộc gọi không được bắt máy**, có TTL và `release_reason=unanswered`. Tải TURN tăng sẽ phản hồi vào `load_one_way_ms`. Chẩn đoán: `allocation_seconds_unanswered`, `reserve_allocation_seconds`.
- Thứ hạng Geo/Smart đổi chiều khi chuyển `connection_mode` ⇒ kết luận ghi "phụ thuộc giả định".

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

**Quy tắc lấy mẫu dữ liệu diagnostic** (contract §6.3): ring buffer trên thiết bị (≤ 360 cửa sổ, ≤ 256 KB/cuộc gọi). Khi kết thúc: cuộc gọi **critical** (`ice_failed`, `dropped_network`, `dropped_turn`, `n_ice_attempts > 1`, có fallback/restart) giữ **100%**; cuộc gọi thường giữ nếu `u64(sha256(utf8(call_id))[0:8], big-endian) mod 1000 < 100` (**10%**). Kết quả ghi vào `stats_status`, `stats_sampling_prob`, `stats_sampling_reason`. Aggregate chẩn đoán dùng trọng số Horvitz-Thompson `1/prob` ở cấp cuộc gọi. Dữ liệu KPI-grade không phụ thuộc quy tắc này.

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
| `scripted` | Công khai, có kỳ vọng rõ (kịch bản hệ thống S08, S11–S20) | Test tự động, demo |
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
| **clean** | `data/clean/<table>/dt=…/*.parquet` | Pipeline **cam kết xuất ra** các cột/bảng ở **contract §8**: hiệu chỉnh đồng hồ lưu **tách riêng** (`event_ts_corrected`, `clock_skew_ms`, `clock_correction_version`, `clock_quality_flag`); `one_way_ms_observed` / `one_way_ms_estimated` (có cờ `symmetric_assumption`); ghép allocation↔ICE (`used_by_ice`, `match_method`); `fact_call`; `dq_results`. Cũng ép kiểu, chuẩn đơn vị, dedup `event_id`, xử lý counter âm/reset, cắm cờ (không xóa) bản ghi lỗi |
| **feature** | `feature/*` | Các bảng `feat_*` ở contract §9, gắn `snapshot_id`, bất biến, có `content_hash`. **Đoàn đọc lớp này** |
| **mart** | `mart/*.parquet` | Bảng KPI đã tính sẵn cho từng trang dashboard (định nghĩa KPI: contract §13) |

- **Engine:** DuckDB + Polars. Mỗi ngày chạy lại thì **ghi đè cả partition** ở raw→clean→mart, nên idempotent. Riêng snapshot feature đã publish thì không ghi đè (§4).
- **DQ:** pandera cho schema và range, cộng các check SQL. Kết quả ghi vào `dq_results` (cột: contract §8.5).

### 7.2 Data quality: bất biến và mức độ

Bộ kiểm tra chính là **17 bất biến I1–I17 của contract §7**, chia hai mức:
- **FAIL**: dữ liệu sai, phải sửa (ví dụ I1, I3, I6–I8, I10, I12–I17).
- **WARN**: đáng ngờ, hiện lên trang Data Quality (ví dụ I2, I4, I5, I9, I11).

Ngoài bất biến, thêm các check thống kê/vận hành: schema và `contract_version`; tỉ lệ event trễ và freshness; lệch đồng hồ client–Signaling; phân phối (số lượng hoặc trung vị lệch quá 3 MAD so với baseline cùng giờ trong tuần); `unclassifiable_rate` và phân bố `stats_status` (§11).

**Tự kiểm chứng:** mọi lỗi do `dirt` tiêm vào đều có ID trong `dirt_log`. Pipeline phải bắt được **≥95%**, và đây là một test bắt buộc.

---

## 8. Xử lý selection bias khi đánh giá

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

- **Tầng 1, metric chính:** `pcr_itt` (hai cận low/high), cohort = mọi `call_session` đã được gán nhánh. Tầng 1b: `pcr_answered` (có điều kiện), thành phần (`ice_fail_rate`, `drop_rate`, `quality_poor_rate`, `unclassifiable_rate`) và phễu (`answer_rate`, `p2p_rate`...).
- **Tầng 2, guardrail** (non-inferiority, margin δ và ngưỡng tuyệt đối trong contract §13.3, luật kết luận §14.4): ICE fail, drop, CST kỹ thuật, TTFM sau bắt máy, API Selector P95, availability, static fallback, TURN utilization, `unclassifiable_rate`, `pcr_itt_high` theo `pair_group`.
- **Tầng 3, chẩn đoán** (không dùng để kết luận thắng/thua): PNR, MOS, population RTT/loss/jitter, rank-of-used, calibration, coverage, ESS, HHI, regret...

Ngữ nghĩa percentile: `call_*` = trong một cuộc gọi, `population_*` = giữa các cuộc gọi trên giá trị cấp cuộc gọi; không bao giờ lấy trung bình các P95.

**Quy tắc thống kê dùng chung:**
- Segment có n < 30 thì ẩn. n < 100 thì không xếp hạng.
- Tỉ lệ đi kèm Wilson CI. Segment cold-start dùng shrinkage Beta-Binomial.
- Khi quét nhiều segment thì hiệu chỉnh Benjamini-Hochberg.
- So sánh giữa các nhóm có pha trộn mạng khác nhau thì chuẩn hóa theo network type (chống nghịch lý Simpson).
- Ngưỡng PoorWindow/PoorFraction là **SLO nội bộ tạm thời** (A10), có sensitivity bắt buộc (contract §14.5).

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

**Kịch bản hệ thống** (chạy `scripted`, mỗi kịch bản có kỳ vọng công khai)

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
| S19 | P2P preferred | `p2p_rate`, cohort ITT vẫn gồm cuộc gọi P2P |
| S20 | Call burst | Tải đột biến |

Phải có kịch bản **Geo thắng**, kịch bản **Historical thắng** và kịch bản **Smart thắng**. Mỗi kịch bản có một test end-to-end trên profile `dev`.

---

## 11. Dashboard (Streamlit)

| Trang | Nội dung chính | Bộ lọc |
|---|---|---|
| Overview | KPI chính (`pcr_itt` hai cận), xu hướng 30 ngày, nhãn nguồn dữ liệu | ngày, nguồn |
| TURN Việt Nam | Heatmap miền-user × miền-TURN, ISP-user × ISP-host; P50/P95; theo giờ | miền, ISP, TURN, network, giờ |
| TURN Quốc tế | Bản đồ quốc gia → TURN location; nước có và không có TURN | country, region |
| Caller ↔ Callee | Ba nhóm VN-VN / VN-Intl / Intl-Intl; ma trận cặp | nhóm, cặp |
| Call Quality | CST, TTFM, RTT media, Loss, Jitter, Drop, thành phần của `pcr_itt`; MOS và PNR hiển thị là chẩn đoán | |
| Service Health | Availability, API P95, error, fallback, freshness | |
| Algorithm Quality | `pcr_itt` low/high và cận chéo theo policy (kèm CI theo seed), **guardrail** (non-inferiority so với margin), **regret** (in-list, feasible-global, joint-path), rank-of-used, coverage, HHI, ESS, kết luận Smart tốt hơn / tệ hơn / INCONCLUSIVE | policy, ε, seed |
| Data Quality | `dq_results` (FAIL/WARN), orphan, event trễ, lệch đồng hồ, **`unclassifiable_rate`**, **phân bố `stats_status`** (`kept_critical`, `kept_sampled`, `not_sampled`, `truncated`, `lost`) | run, bảng |
| Decision Trace | Nhập `call_id` → timeline: context → 4 TURN/bên + score → allocation → đường đi → stats theo chặng (dữ liệu diagnostic nếu cuộc gọi được lấy mẫu, nếu không thì hiện `stats_status`) → outcome | |
| Insights | Bất thường tự phát hiện (robust z, EWMA/CUSUM) kèm bằng chứng | |

Dashboard **chỉ đọc `mart/`** (và `clean/` cho Decision Trace), không bao giờ đọc `truth`. Riêng trang "Sim Validation" là ngoại lệ, được đánh dấu rõ. Số liệu diagnostic không được dùng làm KPI trên các trang kết luận (I16).

---

## 12. Data Contract v0.2.0 (tóm tắt — bản đầy đủ và chuẩn: `docs/contracts/data-contract.md`)

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
10. **Bất biến I1–I17:** pass trên dữ liệu sạch; từng bất biến FAIL/WARN bị bắt trên dữ liệu có lỗi chủ đích.
11. **Cấm đọc truth:** test tự động cấm `selector`, `pipeline`, `features`, `dashboard` import hoặc mở `data/truth/` (contract §11). Policy không tạo RNG toàn cục.
12. **Kịch bản:** e2e cho kịch bản cuộc gọi và kịch bản hệ thống (§10).
13. **Đánh giá các bộ đánh giá:** sai số của DR so với regret thật phải nhỏ hơn naive; precision/recall và độ trễ phát hiện trên `incident_truth`; luật kết luận §14.4 trả đúng Smart tốt hơn / tệ hơn / INCONCLUSIVE trên dữ liệu có đáp án.

---

## 15. Lịch theo tuần (phần của Hiệp)

| Tuần | Giao |
|---|---|
| W1 (04–10/11) | Spec này, Data Contract v0.2.0 chốt với Đoàn (đủ `kpi.yaml`), world.yaml, khung simulator (world, truth, traffic, geo_baseline) |
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

## 17. Rủi ro

- **Simulator "quá đẹp"**, khiến thuật toán học đúng giả định của chính simulator. Giảm thiểu bằng nhiễu đuôi dài, sự cố ẩn, sensitivity analysis trên A5/A10, và chỉ báo cáo kết quả có nhãn synthetic.
- **Contract lệch giữa Hiệp và Đoàn.** Giảm thiểu bằng một nguồn `contracts/`, test contract và `kpi.yaml` trong CI, đổi version khi có thay đổi.
- **Chi phí chạy** tăng theo R seed × số policy (mỗi cặp là một môi trường cô lập). Giảm thiểu bằng power analysis để chọn R vừa đủ, profile `dev` cho test, báo cáo MDE thực tế nếu không đủ ngân sách (contract §14.3).
- **Khối lượng 6 tuần.** Thứ tự ưu tiên: pipeline + DQ + Dashboard V1 trước, sau đó mới tới OPE và exploration.
