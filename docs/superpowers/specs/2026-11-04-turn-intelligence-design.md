# TURN Intelligence — Thiết kế Simulator, Data Pipeline & Dashboard

- **Ngày:** 2026-11-04 · **Owner:** Đặng Quốc Hiệp · **Đối tác:** Đặng Đỉnh Đoàn (thuật toán + API)
- **Trạng thái:** Draft v0.1, chờ Hiệp và Đoàn duyệt
- **Research nền:** `docs/research/01..04-*.md`

> Đọc nhanh: §1 → §3 (flow một cuộc gọi) → §4 (vòng lặp theo ngày) → §7 (pipeline). Các phần còn lại là tra cứu.

---

## 1. Mục tiêu và phạm vi

**Bài toán.** Thuật toán của Đoàn xếp hạng **top-4 TURN cho mỗi bên**. Cuộc gọi đi theo đường `A → TA1 → TB1 → B` (rank 1 của mỗi bên), còn rank 2–4 là dự phòng. Production **chỉ đo được đường đã đi**. Phần của Hiệp là xây hệ thống:

1. **Sinh dữ liệu** giả lập có tính thực tế, vì chưa có log thật.
2. **Xử lý dữ liệu** (pipeline + data quality) bằng code dùng lại được nguyên vẹn khi có log Call thật.
3. **Đo lường và đánh giá độc lập** chất lượng TURN, chất lượng thuật toán và sức khỏe service.
4. **Trình bày** trên dashboard chạy thật, kèm insight có bằng chứng.

**Định nghĩa "xong" (MVP 02/12, Final 15/12):**
- Simulator chạy rolling 30 ngày, có đủ 10 kịch bản bắt buộc (§10).
- Pipeline chạy incremental theo ngày, chạy lại không đổi kết quả, và bắt được dữ liệu bẩn đã tiêm.
- Dashboard đi được từ *quyết định của thuật toán* → *đường thực đi* → *chất lượng cuộc gọi*, có Decision Trace theo Call ID.
- Có ≥3 insight, mỗi insight được kiểm chứng với sự cố ẩn (precision/recall).
- Đánh giá thuật toán **có xử lý selection bias** (§8), và được kiểm chứng bằng Network Truth.

**Ngoài phạm vi:** group call/SFU, alerting (Grafana), đo RIPE Atlas thật, M-Lab BigQuery, mọi khẳng định về cải thiện production.

**Nguyên tắc trung thực.** Mọi kết luận gắn nhãn nguồn `data_source ∈ {synthetic, lab_zenodo, public_reference, production}`. Kết quả trên simulator **không** được dùng để khẳng định production đã tốt hơn.

---

## 2. Thuật ngữ

| Thuật ngữ | Nghĩa |
|---|---|
| **Leg (chặng)** | Một đoạn của đường đi: `A_TA` (A→TURN của A), `TA_TB` (TURN↔TURN), `TB_B` (TURN của B→B) |
| **Path (đường)** | Tổ hợp (TAi, TBj). Độ trễ một chiều của đường = tổng 3 chặng. Nếu TAi = TBj thì chặng `TA_TB` = 0 |
| **Policy** | Thuật toán chọn TURN: `geo_baseline` (Hiệp viết) hoặc `smart_vX` (Đoàn viết) |
| **Exploration (ε)** | Tỉ lệ nhỏ cuộc gọi cố ý đi rank 2–4 để có dữ liệu cho đường chưa đi |
| **Propensity** | Xác suất policy chọn đúng đường đã đi. Bắt buộc phải log thì mới sửa được lệch |
| **Network Truth** | Chất lượng "thật" của mọi chặng, chỉ simulator biết. Dashboard **không đọc**, chỉ dùng để chấm điểm |
| **Oracle** | Đường tốt nhất theo Network Truth, là mốc để tính regret |
| **PNR** | Poor Network Rate: % cuộc gọi vượt ngưỡng xấu (theo Via, SIGCOMM 2016) |
| **Snapshot** | Phiên bản bảng feature/health mà policy dùng khi quyết định. Phục vụ point-in-time và chống leakage |

---

## 3. Flow một cuộc gọi

```
 t0  A bấm gọi ── Signaling ──► Selector.select(ctx_A, ctx_B?)  ───────────────► [selector_decision]
                                  │  đọc feature/health snapshot (ngày d-1)          phase=initial
                                  │  trả 4 TURN/bên + score + propensity + confidence
 t1  Client A, B allocate ──────► TURN (cả 4/bên, §5.1) ──────────────────────────► [turn_allocation] ×8
                                  (RTT allocation = số đo chặng A_TAi lúc setup)     [path_leg_measurement] method=alloc
 t2  B bắt máy → biết ctx_B ──► (tùy chọn) Selector refine ───────────────────────► [selector_decision] phase=refined
 t3  ICE: đi TA1×TB1; lỗi thì fallback rank kế ──────────────────────────────────► [ice_attempt] (+attempt_seq)
 t4  Media chạy, đo liên tục mỗi 5 s, cho từng chặng và từng bên ────────────────► [call_stats_5s], [path_leg_measurement] method=inband
     đổi Wi-Fi↔4G → network_epoch+1, ICE restart ───────────────────────────────► [ice_attempt] restart
 t5  Kết thúc ────────────────────────────────────────────────────────────────────► [call_outcome]
 song song: TURN↔TURN mesh probe, TURN health, Selector service health ──────────► [turn_probe] [turn_health_1m] [service_health_1m]
 chỉ simulator: chất lượng thật của mọi chặng, sự cố ──────────────────────────────► [truth_leg] [incident_truth]  (ẩn)
```

Toàn bộ event nối với nhau qua `call_id` và `decision_id`. Cuộc gọi lỗi **vẫn được giữ lại**, không bao giờ điền 0.

---

## 4. Vòng lặp theo ngày (rolling simulation, vòng kín)

```
for d in day_1 .. day_30:
    snapshot = feature_store.latest(as_of = d-1)      # policy chỉ thấy quá khứ
    sim.run_day(d, policy, snapshot)                  # sinh raw events ngày d
    pipeline.run(d, lookback_days = 3)                # raw → clean → DQ → feature → mart
    feature_store.publish(snapshot_id = d)            # ngày d+1 sẽ dùng
```

- Ngày 1 dùng **prior** (geo + dữ liệu công khai), nên cold-start toàn hệ thống là có thật.
- Có `lookback_days=3` vì simulator cố tình sinh event trễ tới 72 giờ.
- Mỗi lần chạy có `run_id` và `seed`. Cùng seed thì ra cùng kết quả.

---

## 5. Hai ý tưởng thu dữ liệu chặng (đề xuất gửi mentor)

Lý do cần hai cơ chế này: chỉ đo đường đã đi thì dữ liệu bị lệch theo chính thuật toán (§8). Mục tiêu là **có thêm số đo chặng mà không làm đổi đường đi của cuộc gọi**.

### 5.1 Allocate toàn bộ 4 TURN mỗi bên lúc setup (pre-allocation)

- **Cách làm:** client gửi TURN Allocate tới cả 4 server cùng lúc. Server nào xong cũng cho ra RTT của chặng `A→TAi` *lúc setup*. Sau khi ICE connected: **giữ rank 1 và rank 2** (refresh định kỳ) để fallback nhanh, **giải phóng rank 3–4**.
- **Lợi ích:**
  - Có dữ liệu chặng user→TURN cho cả 4 TURN, miễn phí.
  - Fallback không phải chờ allocate lại (thường mất 100–300 ms).
  - Phát hiện sớm TURN lỗi hoặc quá tải.
- **Chi phí:** số allocation tăng khoảng 4 lần trong vài giây đầu. Tốn port và quota trên TURN. Allocation có lifetime ngắn và được giải phóng sớm nên chi phí thực tế nhỏ.
- **Hạn chế:** đây chỉ là số đo lúc setup, không phải trong lúc media chạy, nên gắn `method=alloc`. Số đo này cũng gồm cả thời gian TURN xử lý.

### 5.2 TURN↔TURN mesh probe phía server

- **Cách làm:** mỗi TURN chạy một agent nhẹ, cứ 60 giây gửi gói UDP echo hoặc relay loopback (kiểu `turn-monitor`) tới mọi TURN khác. Với 22 TURN là 462 cặp có hướng, tức khoảng 8 gói/giây trên toàn hệ thống, không đáng kể.
- **Lợi ích:** chặng giữa `TA_TB` **không phụ thuộc user**, nên probe cho **toàn bộ ma trận mà không bị thuật toán làm lệch**. Sau đó chỉ còn 2 chặng phía user bị lệch. Probe còn phát hiện được sự cố backbone giữa các vùng.
- **Một chiều hay RTT:** đo một chiều cần đồng bộ đồng hồ giữa các server (NTP tốt, lệch dưới 1 ms). Không có thì dùng RTT/2 và gắn cờ `one_way_estimated=true`.

### 5.3 (Bổ sung) Idle probe phía client

Khi app mở hoặc rảnh, khoảng 1 lần/ngày, SDK gửi 1 STUN binding tới 2 TURN chọn ngẫu nhiên **ngoài** top của user đó. Mục đích là lấp coverage của chặng user→TURN với chi phí gần bằng 0 và không ảnh hưởng cuộc gọi. Gắn `method=idle_probe`.

**Trong simulator**, cả 3 cơ chế là tham số bật/tắt (`alloc_all`, `mesh_probe`, `idle_probe_rate`). Báo cáo sẽ so sánh coverage và sai số đánh giá khi bật/tắt từng cơ chế, làm bằng chứng để đề xuất với mentor.

---

## 6. Simulator

### 6.1 Module

| Module | Trách nhiệm |
|---|---|
| `world` | Sinh `dim_turn`, `dim_user`, ma trận khoảng cách và độ trễ giữa thành phố |
| `truth` | **Network Truth**: độ trễ, loss, jitter thật của mọi chặng theo thời gian (ẩn) |
| `incidents` | Tiêm sự cố từ file ẩn `incidents.yaml` |
| `traffic` | Ai gọi ai, lúc nào. Phân bố theo giờ trong ngày, cặp VN/quốc tế, cuộc gọi "mù" |
| `policy` | Interface `select(ctx) -> Decision`. Có sẵn `geo_baseline`, plug-in policy của Đoàn, wrapper ε-exploration |
| `call_engine` | Allocation → ICE/fallback → media 5 s → outcome, đọc từ `truth` và cộng nhiễu đo |
| `probes` | Mesh TURN↔TURN, idle probe |
| `health` | `turn_health_1m` (tải được tính từ chính traffic, nên có hiện tượng dồn traffic gây quá tải), `service_health_1m` |
| `dirt` | Tiêm dữ liệu bẩn: 1–3% event thiếu, trùng, trễ, lệch đồng hồ, sai đơn vị |
| `runner` | Vòng rolling (§4), seed, sink |

### 6.2 Thế giới

- **TURN Việt Nam (15):** Bắc (HAN ×4, HPH ×1), Trung (DAD ×3, HUE ×1, NHA ×1), Nam (SGN ×4, CTO ×1). Mỗi miền được host bởi Viettel, VNPT và FPT.
- **TURN quốc tế (7):** SG ×2, JP-Tokyo, HK, DE-Frankfurt, US-West, AU-Sydney.
- **Quốc gia có user nhưng không có TURN:** TW, KR, TH, MY, FR, UK, US-East…
- **User (50k):** 80% VN (Bắc 40%, Trung 15%, Nam 45%; Viettel 45%, VNPT 30%, FPT 20%, khác 5%) và 20% quốc tế. Mạng chính: wifi 55%, 4G 38%, 5G 7%.
- **Cold-start có chủ đích:** 3 quốc gia và 2 ISP nhỏ có dưới 30 cuộc gọi trong cả 30 ngày.
- Đây là giả định của nhóm. Nếu mentor có topology thật thì thay vào file `configs/world.yaml`.

### 6.3 Mô hình Network Truth (độ trễ một chiều của một chặng)

```
ms = base_city(src_city, dst_city) / 2      # từ bảng ping thành phố WonderNetwork (RTT → /2)
   + isp_penalty(src_isp, dst_host_isp)     # cùng ISP 0; khác ISP trong VN 3–15 ms (GIẢ ĐỊNH, có sensitivity)
   + access(network_type)                   # chỉ chặng phía user: wifi ~2–5, 4G ~10–20, 5G ~5–10 (nền từ Ookla)
   + diurnal(hour, region)                  # cao điểm 20–23h tăng 10–30%
   + load_penalty(turn_utilization)         # >80% tải thì tăng mạnh
   + incident(t)                            # theo incidents.yaml
   + noise ~ LogNormal                      # đuôi dài
```

- **Loss và jitter** là hàm của access, load và incident. Cuộc gọi trên 4G và trong giờ cao điểm có loss cao hơn.
- **Không dùng công thức theo khoảng cách** vì định tuyến không đơn điệu. Ví dụ HN→Seoul 120 ms nhưng HCM→Seoul 65 ms (`docs/research/01`).
- **MOS** tính theo E-model (ITU-T G.107 rút gọn) từ tổng độ trễ, loss và jitter. Zenodo WebRTC-QoE chỉ dùng để đối chiếu.

### 6.4 Hành vi client và ICE

- Mỗi bên nhận `k=4` TURN (tham số, đặt được tới 8 cho đúng đề bài).
- Đường đi = rank 1 × rank 1. Nếu allocation hoặc ICE trên rank 1 lỗi hoặc quá timeout thì thử rank kế, và ghi `attempt_seq`.
- Một phần cuộc gọi trong nước kết nối **P2P trực tiếp** (host/srflx), khi đó `turn_used=false`.
- Đổi mạng giữa cuộc gọi: 3–5% cuộc gọi, kèm ICE restart, `network_epoch+1`.
- **Cuộc gọi mù:** khoảng 40% cuộc gọi lúc t0 chưa biết context của B (`info_level=caller_only`). Policy dùng `callee_prior`. Khi B bắt máy thì có quyết định `refined`.

### 6.5 Quy mô

| Profile | Ngày | Cuộc gọi | Ghi chú |
|---|---|---|---|
| `dev` | 3 | ~10k | chạy dưới 1 phút, dùng cho test |
| `main` | 30 | ~300k | VN↔VN 70%, VN↔Intl 20%, Intl↔Intl 10% |

Số dòng ước tính cho `main`:
- `turn_allocation`: khoảng 2.4M (300k × 2 bên × 4 TURN)
- `path_leg_measurement`: khoảng 3–5M
- `call_stats_5s`: lưu đầy đủ cho 10% cuộc gọi, khoảng 2–3M

### 6.6 Sự cố ẩn (`incidents.yaml`)

Có 5–8 sự cố, ví dụ:
- TURN SGN-2 sập 2 giờ.
- DAD-1 quá tải giờ cao điểm 3 ngày liên tiếp.
- ISP VNPT miền Trung suy giảm dần trong 1 tuần.
- Tuyến SG↔JP tăng 40 ms.
- Một ISP Đài Loan có loss 8%.

File do **script random theo seed** sinh ra (`make incidents`), ghi vào `data/truth/` (gitignore). Hiệp **không mở file và không xem seed** cho tới khi đã viết xong insight (blind). Chỉ module chấm điểm `eval/incident_scoring` được đọc file này.

---

## 7. Data Pipeline

### 7.1 Các lớp

```
nguồn ──► adapters ──► raw/ ──► clean/ ──► feature/ ──► mart/ ──► dashboard
(sim | zenodo | prod)  (nguyên bản)  (chuẩn hóa + DQ)  (historical)  (KPI theo trang)
```

| Lớp | Lưu ở | Làm gì |
|---|---|---|
| **adapters** | code | Mỗi nguồn một adapter, đổi về canonical schema. `sim` (JSONL), `zenodo` (webrtc-internals JSON), `postgres` (dành cho pilot). **Sau adapter, code dùng chung hoàn toàn** |
| **raw** | `data/raw/<table>/dt=YYYY-MM-DD/*.jsonl` | Giữ nguyên bản, append-only, không sửa |
| **clean** | `data/clean/<table>/dt=…/*.parquet` | Ép kiểu, chuẩn đơn vị (ms, %), dedup theo `event_id`, sửa lệch đồng hồ, xử lý counter âm/reset, gom theo `network_epoch`, cắm cờ (không xóa) bản ghi lỗi |
| **clean / fact** | `fact_call` | Một dòng mỗi cuộc gọi, join decision → allocation → ICE → legs → outcome |
| **feature** | `feature/leg_stats`, `feature/turn_health`, `feature/callee_prior` | Aggregate có decay (half-life 7 ngày) theo (phân khúc × TURN × giờ), kèm n, Wilson CI, shrinkage. Có `snapshot_id`. **Đoàn đọc lớp này** |
| **mart** | `mart/*.parquet` | Bảng KPI đã tính sẵn cho từng trang dashboard |

- **Engine:** DuckDB + Polars. Mỗi ngày chạy lại thì **ghi đè cả partition**, nên idempotent.
- **DQ:** pandera cho schema và range, cộng các check SQL. Kết quả ghi vào `dq_results(run_id, dt, check, table, status, n_bad, sample_ids)`.

### 7.2 Danh mục data quality check (rút gọn, đầy đủ ở research/04)

| Nhóm | Check |
|---|---|
| Schema | Đủ cột, đúng kiểu, `contract_version` hợp lệ |
| Range | `ms` từ 0 đến 5000, loss từ 0 đến 100, jitter ≥ 0, rank từ 1 đến k |
| Unique | Trùng `event_id` → dedup và đếm |
| Toàn vẹn | Allocation, ICE hay outcome không có decision tương ứng (orphan); decision không có outcome |
| Thứ tự | `t_decision ≤ t_alloc ≤ t_ice ≤ t_end` |
| Thời gian | Lệch `client_ts − server_ts` quá ngưỡng; tỉ lệ event trễ; freshness |
| Nhất quán | TURN ICE dùng phải nằm trong list của decision; tổng 3 chặng xấp xỉ RTT đầu-cuối |
| Phân phối | Số lượng hoặc trung vị lệch quá 3 MAD so với baseline cùng giờ trong tuần |

**Tự kiểm chứng:** mọi lỗi do `dirt` tiêm vào đều có ID. Pipeline phải bắt được **≥95%**, và đây là một test bắt buộc.

---

## 8. Xử lý selection bias khi đánh giá

**Vấn đề:** chỉ đường rank 1 × rank 1 được đo. Nếu policy hoàn toàn deterministic thì **không thể** ước lượng đúng kết quả của đường chưa đi (điều kiện overlap). Giải bằng 5 lớp:

| # | Cơ chế | Loại | Ghi chú |
|---|---|---|---|
| 1 | **Gộp chặng giữa các cuộc gọi**, dựng mô hình `ms_chặng ~ f(phân khúc, TURN, giờ, network)` (Direct Method) | Thuật toán | Không lấp được chặng chưa từng được đo |
| 2 | **Mesh probe** cho chặng giữa (§5.2), cộng **pre-allocation và idle probe** cho chặng user (§5.1, §5.3) | Thiết lập dữ liệu | Gần như không lệch |
| 3 | **ε-exploration có propensity:** mỗi bên, xác suất 1−ε đi rank 1, ε chia đều cho các rank 2–4 đã qua health filter. Không explore khi có sự cố hoặc user mạng yếu. `p = p_A(i) × p_B(j)` | Thiết lập dữ liệu | ε mặc định 0 (giống production); thí nghiệm với 2% và 5% |
| 4 | **IPS / SNIPS / Doubly Robust** để đánh giá policy mới trên log cũ (thư viện `obp`) | Thuật toán | Propensity được clip để giảm phương sai |
| 5 | **Fallback tự nhiên** (rank 1 lỗi nên đi rank 2) | Dữ liệu | Bị lệch vì xảy ra lúc mạng tệ; chỉ dùng kèm biến điều chỉnh |

**Thí nghiệm then chốt** (chỉ simulator làm được): với ε ∈ {0, 2%, 5%}, so sai số của ước lượng naive / DM / IPS / DR với **regret thật** tính từ Network Truth. Báo cáo cả chi phí exploration (PNR tăng bao nhiêu).

---

## 9. KPI Dictionary (định nghĩa dùng chung)

| KPI | Định nghĩa | Mẫu số / ghi chú |
|---|---|---|
| Allocation Success | allocation thành công / số lần allocate | Theo TURN, ISP, vùng |
| Leg / Path latency P50, P95 | Quantile trên **dữ liệu gốc**, không lấy trung bình của các P95 | Một chiều, ms |
| Failure Rate | Cuộc gọi không kết nối được / cuộc gọi đã bắt máy | **Loại `not_answered`** |
| Connection Success | 1 − Failure Rate | |
| CST | Từ lúc B bắt máy tới ICE `connected` | |
| TTFM | Từ lúc `connected` tới gói media đầu tiên | |
| RTT / Loss / Jitter | Từ `call_stats_5s`, tính theo epoch | |
| Drop Rate | Kết thúc bất thường **sau khi** đã connected / số cuộc gọi connected | |
| MOS | E-model | Ước lượng, không phải điểm chủ quan |
| PNR | % cuộc gọi có (one-way > 150 ms) hoặc (loss > 3%) hoặc (MOS < 3.5) | Ngưỡng là tham số |
| Stability | Độ lệch chuẩn hoặc CV của latency theo giờ; số lần đổi health status | Theo TURN |
| Rank-of-used | Rank của TURN mà cuộc gọi thực sự dùng | Phân phối |
| Regret | ms(đường đã đi) − ms(oracle) | Thật chỉ có trên sim; ước lượng bằng DR |
| Coverage | % ô (phân khúc × TURN) có số đo trong 7 ngày | |
| Traffic concentration | HHI theo TURN | Phát hiện dồn traffic |
| Service Availability / API latency / Error / Fallback / Freshness | Theo RED; freshness = now − snapshot mới nhất | `service_health_1m` |

**Quy tắc thống kê:**
- Segment có n < 30 thì ẩn. n < 100 thì không xếp hạng.
- Tỉ lệ đi kèm Wilson CI. Segment cold-start dùng shrinkage Beta-Binomial.
- Khi quét nhiều segment thì hiệu chỉnh Benjamini-Hochberg.
- So sánh giữa các nhóm có pha trộn mạng khác nhau thì chuẩn hóa theo network type (chống nghịch lý Simpson).

---

## 10. Mười kịch bản bắt buộc: dữ liệu và kiểm chứng

| # | Kịch bản | Simulator tạo bằng | Dashboard hoặc test phải cho thấy |
|---|---|---|---|
| 1 | HCM Viettel ↔ HCM Viettel | Traffic nội vùng | TURN SGN-Viettel đứng top, CST thấp |
| 2 | HCM Viettel ↔ HN VNPT | Khác miền | So đường SGN×HAN với DAD×DAD; chặng giữa từ mesh |
| 3 | HCM Viettel ↔ HCM FPT | `isp_penalty` | Chi phí khác ISP, chọn TURN host ISP nào |
| 4 | HCM Viettel ↔ SG Singtel | Quốc tế có TURN | SGN×SG, chất lượng theo giờ |
| 5 | HCM VNPT ↔ Đài Loan 4G | TW không có TURN | TW đi qua HK hay JP hay SG; so với nước có TURN |
| 6 | SG ↔ JP | Intl cùng khu vực | Joint ranking cho cả hai đầu |
| 7 | JP ↔ DE | Intl khác khu vực | Đường dài, chặng giữa chiếm phần lớn |
| 8 | TURN failure | `incidents.yaml` | Health filter, tỉ lệ fallback, thời gian phát hiện |
| 9 | Cold-start | Quốc gia/ISP ít mẫu | CI rộng, shrinkage, confidence thấp, coverage |
| 10 | Network change | Đổi epoch giữa cuộc gọi | KPI theo epoch, ICE restart, drop |

Mỗi kịch bản có một `scenario_tag` trong `call_outcome` và một test end-to-end trên profile `dev`.

---

## 11. Dashboard (Streamlit)

| Trang | Nội dung chính | Bộ lọc |
|---|---|---|
| Overview | KPI chính, xu hướng 30 ngày, nhãn nguồn dữ liệu | ngày, nguồn |
| TURN Việt Nam | Heatmap miền-user × miền-TURN, ISP-user × ISP-host; P50/P95; theo giờ | miền, ISP, TURN, network, giờ |
| TURN Quốc tế | Bản đồ quốc gia → TURN location; nước có và không có TURN | country, region |
| Caller ↔ Callee | Ba nhóm VN-VN / VN-Intl / Intl-Intl; ma trận cặp | nhóm, cặp |
| Call Quality | CST, TTFM, RTT, Loss, Jitter, Drop, MOS, PNR | |
| Service Health | Availability, API P95, error, fallback, freshness | |
| Algorithm Quality | Rank-of-used, PNR theo policy, regret (DR và thật), coverage, HHI, ESS, so sánh Geo và Smart | policy, ε |
| Data Quality | `dq_results`, orphan, event trễ, lệch đồng hồ | run, bảng |
| Decision Trace | Nhập `call_id` → timeline: context → 4 TURN/bên + score → allocation → đường đi → stats theo chặng → outcome | |
| Insights | Bất thường tự phát hiện (robust z, EWMA/CUSUM) kèm bằng chứng | |

Dashboard **chỉ đọc `mart/`** (và `clean/` cho Decision Trace), không bao giờ đọc `truth`. Riêng trang "Sim Validation" là ngoại lệ, được đánh dấu rõ.

---

## 12. Data Contract v0.1 (tóm tắt — bản đầy đủ và chuẩn: `docs/contracts/data-contract-v0.1.md`)

Viết dưới 3 dạng sinh từ một nguồn: **JSON Schema** (trung lập ngôn ngữ, Java Spring Boot đọc được), **Pydantic** (Python), **Postgres DDL** (dành cho pilot).

Mọi bảng có các cột chung: `event_id, contract_version, data_source, sim_run_id, client_ts, server_ts`.

| Bảng | Khóa | Field chính |
|---|---|---|
| `dim_turn` | turn_id | country, vn_region, city, lat, lon, host_isp, host_asn, capacity, transports[], status |
| `dim_user` | user_id (hash) | country, vn_region, city, isp, asn, primary_network, cohort |
| `selector_decision` | decision_id | call_id, side, phase{initial, refined, restart}, ts, policy_version, decision_mode{live, shadow}, decision_source{api, static_fallback}, info_level{full, caller_only, country_only, none}, ctx{country, region, city, isp, asn, network, geo_mismatch}, candidates[k]{rank, turn_id, score, reason, propensity}, chosen_rank, is_exploration, confidence, feature_snapshot_id, health_snapshot_id, api_latency_ms, error |
| `turn_allocation` | event_id | call_id, side, turn_id, rank, transport{udp, tcp, tls}, success, alloc_ms, error_code, released_at |
| `ice_attempt` | event_id | call_id, attempt_seq, network_epoch, turn_used, relay_turn_a, relay_turn_b, rank_a, rank_b, local_type, remote_type, state, cst_ms, ttfm_ms |
| `path_leg_measurement` | event_id | call_id (null nếu là probe), leg{A_TA, TA_TB, TB_B}, src_id, dst_id, method{alloc, inband, mesh_probe, idle_probe}, one_way_ms, one_way_estimated, loss_pct, jitter_ms, t_offset_s, network_epoch |
| `call_stats_5s` | (call_id, side, t_offset) | network_epoch, network_type, rtt_ms, jitter_ms, loss_pct, bitrate_kbps, state |
| `call_outcome` | call_id | answered, connected, duration_s, end_reason, dropped, caller/callee ctx đầy đủ (join muộn), pair_group, scenario_tag, mos_est, aggregate p50/p95 |
| `turn_health_1m` | (turn_id, minute) | active_alloc, utilization, cpu, health_status, health_snapshot_id |
| `service_health_1m` | minute | req_count, p50_ms, p95_ms, error_rate, fallback_rate, freshness_s |
| `callee_prior` | (caller_segment, callee_segment) | n, share — chỉ số đếm, không lưu ai gọi ai |
| **ẩn:** `truth_leg`, `incident_truth`, `dirt_log` | | Chỉ dùng cho việc chấm điểm |

**Privacy:** user_id được hash, geo chỉ tới cấp thành phố, không lưu IP thô (chỉ ASN).

---

## 13. Công nghệ và cấu trúc repo

- **Python 3.12**, `.venv`, DuckDB, Polars, Pydantic, pandera, numpy/scipy, Streamlit, plotly, obp, pytest.
- Raw sink mặc định là JSONL. **Postgres (Docker, đã có) là sink thứ hai**, chạy từ W2, để pipeline đọc qua `postgres_scanner` giống lúc pilot.
- **Chung một repo với Đoàn.** `contracts/` là nguồn chung. Mọi PR đụng tới `contracts/` cần cả hai duyệt.
- **Data Contract chi tiết:** `docs/contracts/data-contract-v0.1.md`.

```
contracts/           # JSON Schema, Pydantic, Postgres DDL (nguồn chung với Đoàn)
configs/             # world.yaml, sim_dev.yaml, sim_main.yaml, incidents.yaml (ẩn)
src/turnintel/
  sim/               # world, truth, incidents, traffic, policy, call_engine, probes, health, dirt, runner
  pipeline/          # adapters/, clean, dq, fact, features, marts, orchestrator
  eval/              # ope, regret, anomaly, incident_scoring
dashboard/           # app.py + pages/
data/                # raw, clean, feature, mart, truth, external  (gitignore)
tests/               # unit + 10 scenario e2e (profile dev)
docs/                # research/, specs/, kpi-dictionary, reports/
```

---

## 14. Kiểm chứng (testing)

1. **Unit:** adapter, chuẩn hóa đơn vị, dedup, sửa lệch đồng hồ, các hàm KPI (P95 đúng, Wilson CI), propensity.
2. **Contract:** mọi event do sim sinh ra đều qua JSON Schema. Fixture Zenodo đi qua adapter `zenodo`.
3. **Idempotent:** chạy pipeline 2 lần trên cùng một ngày thì mart giống hệt nhau.
4. **DQ recall ≥ 95%** trên lỗi tiêm từ `dirt_log`.
5. **Tính nhất quán:** TURN ICE dùng phải nằm trong decision; tổng chặng xấp xỉ đầu-cuối.
6. **Kịch bản:** 10 test e2e (§10).
7. **Đánh giá các bộ đánh giá:** sai số của DR so với regret thật phải nhỏ hơn naive; precision/recall và độ trễ phát hiện trên `incident_truth`.

---

## 15. Lịch theo tuần (phần của Hiệp)

| Tuần | Giao |
|---|---|
| W1 (04–10/11) | Spec này, Data Contract v0.1 chốt với Đoàn, KPI Dictionary, world.yaml, khung simulator (world, truth, traffic, geo_baseline) |
| W2 (11–17/11) | Call engine, raw → clean → fact, DQ cơ bản, profile dev và main, **Dashboard V1** (TURN VN/Intl theo vùng, country, ISP, network) → **Sprint 1 18/11** |
| W3 (18–24/11) | Rolling loop, feature store, probes, health, trang TURN Performance và Service Health |
| W4 (25/11–01/12) | Cắm policy của Đoàn, exploration và propensity, trang Algorithm Quality và Decision Trace, filter và drill-down → **MVP 02/12** |
| W5 (02–08/12) | So Geo với Smart, OPE và thí nghiệm ε, anomaly detection, mở incidents → ≥3 insight |
| W6 (09–15/12) | Adapter Postgres cho pilot, hoàn thiện tài liệu và báo cáo, đề xuất cải tiến → **Final 15/12** |

---

## 16. Sổ giả định (cập nhật khi có thông tin)

| # | Giả định | Nguồn hoặc lý do | Ảnh hưởng nếu sai |
|---|---|---|---|
| A1 | k=4 mỗi bên, đi rank 1 × rank 1, fallback theo rank | Mentor (qua Hiệp) | Đề bài ghi 8 → để tham số |
| A2 | Đo một chiều, liên tục, có loss/jitter/outcome | Hiệp | Nếu chỉ có RTT thì dùng RTT/2 và gắn cờ |
| A3 | Pre-allocation 4 TURN, mesh probe, idle probe | Đề xuất của nhóm (§5) | Mặc định **tắt** trong profile "giống production" |
| A4 | Topology 22 TURN | Nhóm tự thiết kế | Thay `world.yaml` |
| A5 | Phạt khác ISP trong VN 3–15 ms | Không có dữ liệu công khai | Có sensitivity analysis |
| A6 | Schema DB công ty chưa có | Mentor | Adapter `postgres` viết ở W6 |
| A7 | Policy production hiện tại deterministic (ε=0) | Suy ra | Có ε thì OPE dễ hơn |
| A8 | Đoàn cần feature theo segment có backoff nhiều cấp (§12 contract) | Thiết kế của Hiệp | Đoàn duyệt ở W1 |

## 17. Rủi ro

- **Simulator "quá đẹp"**, khiến thuật toán học đúng giả định của chính simulator. Giảm thiểu bằng nhiễu đuôi dài, sự cố ẩn, sensitivity analysis trên A5, và chỉ báo cáo kết quả có nhãn synthetic.
- **Contract lệch giữa Hiệp và Đoàn.** Giảm thiểu bằng một nguồn `contracts/`, test contract trong CI, đổi version khi có thay đổi.
- **Khối lượng 6 tuần.** Thứ tự ưu tiên: pipeline + DQ + Dashboard V1 trước, sau đó mới tới OPE và exploration.
