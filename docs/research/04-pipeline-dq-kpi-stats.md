# 04 - Pipeline, Data Quality, KPI Statistics, Anomaly Detection, Dashboard

> Phạm vi: TURN Selector Intelligence MVP (6 tuần, laptop, Python). Tài liệu dựa trên kiến thức kỹ thuật và tài liệu chính thức; các URL ở mục 7 chưa được mở lại để kiểm tra từng link trong phiên này, cần verify trước khi trích dẫn chính thức.

## 0. Bảng khuyến nghị

| Quyết định | Chọn | Vì sao | Phương án thay thế |
|---|---|---|---|
| Storage | Parquet, hive partition `dt=YYYY-MM-DD` | Columnar, partition pruning, ghi đè nguyên partition = idempotent | Delta/Iceberg (overkill cho 300k calls) |
| Query engine | DuckDB (embedded) | SQL mạnh, `quantile_cont`, `approx_quantile`, đọc Parquet/JSON trực tiếp, 1 file | SQLite (thiếu window/quantile tốt), Postgres (cần server) |
| Transform | Polars (lazy) cho clean/feature; DuckDB SQL cho mart | Polars nhanh, schema chặt; SQL dễ review cho aggregate | Pandas (chậm, dtype lỏng) |
| Orchestration | Script Python + CLI `run --date`, Makefile | Day-by-day đơn giản, không cần DAG engine | Prefect/cron nhẹ; Airflow/Dagster là overkill |
| Transform framework | Không dùng dbt/SQLMesh ở MVP; SQL file + hàm Python | Ít dependency; 4 layer cố định | dbt-duckdb nếu cần lineage/test chuẩn; SQLMesh nếu cần incremental tự quản |
| Dedup | `event_id` PK; `QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY ingest_ts DESC)=1` | Idempotent, an toàn với late/retry | Seen-set/Bloom (không cần) |
| DQ | pandera (schema/range) + check SQL tự viết (orphan, freshness, late rate) ghi vào bảng `dq_results` | Nhẹ, chạy trên Polars/DuckDB, dễ test | Great Expectations (nặng), soda-core (tốt, thêm dependency), dbt tests (cần dbt) |
| CI cho rate | Wilson interval | Ổn với n nhỏ và p gần 0/1 | Clopper-Pearson, Jeffreys |
| Cold start | Empirical Bayes Beta-Binomial + min n | Ranking segment nhỏ ổn định | Hierarchical Bayes (PyMC, overkill) |
| Percentile | Tính từ raw value ở mức call bằng `quantile_cont`; không average P95; sketch khi scale | Percentile không cộng được | t-digest / DDSketch / histogram bucket |
| Anomaly | Robust z (median/MAD) trên baseline hour-of-week + EWMA/CUSUM cho drift chậm | Giải thích được, ít tham số | STL, Prophet, isolation forest (giai đoạn sau) |
| Multiple comparisons | Benjamini-Hochberg FDR | Kiểm soát tỷ lệ phát hiện sai, ít bảo thủ | Bonferroni |
| Dashboard | Streamlit + Plotly/Altair đọc DuckDB | Drill-down + Decision Trace tuỳ biến bằng Python, tái dùng mã thống kê | Grafana (time-series/alert), Superset/Metabase (BI chung, nặng) |
| Service health | RED cho API, USE cho tài nguyên, vài SLI/SLO | Chuẩn công nghiệp, ít chỉ số | Prometheus + Grafana sau MVP |

## 1. Pipeline với DuckDB + Parquet + Polars

### 1.1 Layout

```
data/raw/events/dt=2026-10-01/part-*.jsonl      # bất biến, append-only
data/clean/<event_type>/dt=2026-10-01/*.parquet # dedup, ép kiểu
data/quarantine/<event_type>/dt=.../*.parquet   # bản ghi hỏng + reason
data/feature/call_features/dt=.../*.parquet     # 1 dòng / call_id
data/mart/kpi_segment_hour/dt=.../*.parquet     # aggregate theo segment
data/meta/dq_results.parquet, run_log.parquet
```
`dt` là event date (theo `event_ts` UTC), không phải ingest date; lưu thêm `ingest_ts`, `batch_id`.

### 1.2 Idempotent re-run
- `run(date)` tính toàn bộ partition `dt=date`, ghi ra thư mục tạm rồi rename thay thế nguyên partition (overwrite, không append). Cùng input cho cùng output.
- DuckDB: `COPY (...) TO 'path' (FORMAT PARQUET, PARTITION_BY (dt), OVERWRITE_OR_IGNORE)` hoặc ghi từng `dt` vào thư mục riêng; đọc bằng `read_parquet('.../*/*.parquet', hive_partitioning=true)`; filter theo `dt` cho partition pruning.
- Hàm thuần: output chỉ phụ thuộc input + version code; ghi `code_version` và `input_hash` vào `run_log`. Test: chạy 2 lần, so hash output.

### 1.3 Late-arriving events
- Event thuộc `dt` theo `event_ts`. Khi file đến muộn chứa event của ngày D-k, đánh dấu partition D-k dirty và recompute D-k cùng các layer phụ thuộc. Feature theo call dựng theo `call_id`, không theo ngày (call qua nửa đêm).
- Lookback cố định (vd 3 ngày): mỗi ngày chạy lại T-3..T. Event muộn hơn cửa sổ vào bảng `late_beyond_window`, đếm `late_rate`, backfill thủ công.
- Watermark = `max(event_ts)` mỗi nguồn. Call "complete" khi có outcome hoặc quá timeout (vd 2h); nếu không là `incomplete/orphan`.
- Simulator cần chủ động inject: tỷ lệ trễ, trùng, thiếu, clock skew để test pipeline.

### 1.4 Dedup
- Khoá `event_id` (UUID/ULID sinh ở producer, ổn định khi retry). Giữ bản có `ingest_ts` mới nhất (hoặc đầu tiên; chọn một và ghi tài liệu). Cùng `event_id` nhưng payload khác -> quarantine như conflict.
- Dedup xuyên partition: anti-join với clean trong cửa sổ lookback.

### 1.5 Phân vai Polars và DuckDB
- Polars lazy (`scan_ndjson`, `scan_parquet`): parse JSON, ép kiểu, feature theo call.
- DuckDB: join nhiều bảng, window, quantile, mart. Trao đổi qua Arrow (`.pl()`/`.arrow()`).
- Pitfall: schema drift JSON -> định nghĩa schema tường minh, field lạ giữ trong cột `extra` (JSON); timestamp luôn UTC; ID là string.

### 1.6 Công cụ khác và cái gì là overkill
- dbt-duckdb: model SQL + tests + docs + lineage; incremental `delete+insert` theo partition. Có ích nhưng thêm learning curve; không bắt buộc ở MVP.
- SQLMesh: incremental theo time-range, tự quản interval, audits, hỗ trợ DuckDB. Hợp bài toán chạy theo ngày nhưng khái niệm mới (plan/apply, model kinds) -> overkill 6 tuần.
- Overkill: Airflow/Dagster, Spark, Kafka, Delta/Iceberg, feature store, data catalog, Great Expectations full suite, Prometheus stack.
- Giữ SQL trong thư mục `sql/` theo layer để dễ chuyển sang dbt/SQLMesh sau.

## 2. Data Quality

### 2.1 Chọn framework
| Công cụ | Ưu | Nhược | Kết luận |
|---|---|---|---|
| pandera | Schema as code, hỗ trợ Polars/pandas, check range/regex/unique, lazy validation gom lỗi | Chủ yếu row/column, không có freshness/cross-table | Dùng cho schema + range ở clean |
| Great Expectations | Nhiều expectation, Data Docs | Nặng, config phức tạp | Bỏ ở MVP |
| soda-core | SodaCL YAML gồm freshness, row count, cross-table; hỗ trợ DuckDB | Thêm dependency, DSL riêng | Phương án thay thế tốt; mượn ý tưởng |
| dbt tests | unique/not_null/relationships/accepted_values gọn | Cần dbt | Chỉ khi dùng dbt |
| SQL tự viết | Toàn quyền, chạy trong DuckDB | Tự bảo trì | Dùng cho orphan, freshness, late rate, skew |

Mẫu kết quả: `(check_id, layer, table, dt, severity, metric_value, threshold, status, run_id)` ghi vào `dq_results`. `error` chặn promote sang layer sau; `warn` chỉ hiển thị. Có trang DQ trên dashboard.

### 2.2 DQ check catalog cho event data
| ID | Nhóm | Check | Ngưỡng gợi ý | Severity |
|---|---|---|---|---|
| S1 | Schema | Cột bắt buộc có mặt, kiểu đúng, `event_type` thuộc enum | 100% | error |
| S2 | Schema | Schema version / field lạ | báo khi xuất hiện | warn |
| N1 | Null | Không null ở `event_id, call_id, event_ts, event_type` | 0 | error |
| N2 | Null | Null rate cột nghiệp vụ (isp, region, turn_id, network_type) | < 1-2% | warn |
| R1 | Range | rtt_ms >= 0 và < 10000; jitter >= 0; packet_loss trong [0,1] (hoặc [0,100]); bitrate >= 0 | 0 vi phạm | quarantine |
| R2 | Range | Duration cuộc gọi >= 0 và < 24h | | warn |
| R3 | Domain | region thuộc tập VN; country ISO-3166; ISP trong danh mục | | warn |
| U1 | Unique | `event_id` duy nhất sau dedup | 0 trùng | error |
| U2 | Duplicates | Tỷ lệ trùng thô trước dedup | báo khi tăng đột biến | warn |
| U3 | Conflict | Cùng event_id khác payload | 0 | error |
| F1 | Referential | Mỗi decision có allocation (và ngược lại) | orphan < 0,5% | warn |
| F2 | Referential | ICE event có `call_id` tồn tại ở decision; outcome có decision | như trên | warn |
| F3 | Referential | `turn_id` ở allocation tồn tại trong dimension TURN | 0 | error |
| F4 | Completeness | Call có đủ chuỗi decision -> allocation -> ice -> outcome; tỷ lệ incomplete sau timeout | < 1% | warn |
| T1 | Ordering | decision <= allocation <= ice <= outcome theo thời gian | vi phạm < 0,5% | warn |
| T2 | Clock skew | `ingest_ts - event_ts` âm (event từ tương lai) hoặc skew > 5 phút | < 1% | warn |
| T3 | Clock skew | Chênh `client_ts` vs `server_ts` theo thiết bị/ISP (median, P99) | theo dõi | warn |
| L1 | Freshness | `now - max(event_ts)` mỗi nguồn | < SLO (vd 15 phút với real log; với simulator: đủ ngày D) | error |
| L2 | Late rate | % event có `ingest_ts - event_ts` > lookback | < 1% | warn |
| V1 | Volume | Số event/ngày so với median 7 ngày cùng weekday | ±30% | warn |
| V2 | Volume | Tỷ lệ event_type theo ngày ổn định | drift | warn |
| D1 | Distribution | PSI/KS cho latency, loss so với baseline | PSI > 0,2 | warn |
| K1 | Reconcile | Tổng allocation = tổng decision cùng ngày; mart sum = clean count | chênh = 0 | error |

Quarantine thay vì drop: bản ghi vi phạm S1/R1 ghi sang `quarantine` kèm `reason`.

## 3. Thống kê cho dashboard KPI theo segment

### 3.1 Wilson interval cho tỷ lệ
Với x thành công trên n, p̂ = x/n, z = 1,96:

```
centre = (p̂ + z²/(2n)) / (1 + z²/n)
half   = z · sqrt( p̂(1-p̂)/n + z²/(4n²) ) / (1 + z²/n)
CI     = [centre - half, centre + half]
```
Dùng cho success rate, fallback rate, ICE failure rate. Không dùng Wald (sai khi n nhỏ hoặc p gần 0/1). Luôn hiện n và CI; làm mờ/ẩn segment n < n_min.

### 3.2 Cỡ mẫu tối thiểu
- n cần cho nửa độ rộng CI = e: n ≈ z²·p(1-p)/e². Với e = 0,05: p = 0,5 cần ~385; p = 0,95 cần ~73.
- Thực dụng: n < 30 hiển thị mờ, n < 100 không xếp hạng/không alert; ghi rõ trên UI.
- 300k calls trải trên region × ISP × TURN × network × hour sẽ rất thưa -> rollup đa mức, alert ở mức đủ mẫu, drill xuống mức mịn.

### 3.3 Empirical Bayes (Beta-Binomial shrinkage)
Giả sử p_i ~ Beta(α, β), x_i | p_i ~ Binomial(n_i, p_i). Ước lượng α, β từ toàn bộ segment (method of moments hoặc MLE marginal Beta-Binomial). Posterior mean:

```
p̃_i = (x_i + α) / (n_i + α + β)
```
Segment nhỏ bị kéo về trung bình toàn cục (hoặc trung bình của cha trong hierarchy, vd ISP trong region). Dùng p̃ hoặc quantile 5% của posterior để xếp hạng "tệ nhất"; vẫn hiện p̂ thô và n. Cũng là prior cho cold start của TURN/ISP mới.

### 3.4 Percentile đúng cách
- Không average P95 của các nhóm: P95 của hỗn hợp khác trung bình P95 các nhóm (kể cả có trọng số n), vì percentile không tuyến tính. Ví dụ nhóm A 10 mẫu, nhóm B 1000 mẫu có phân phối khác nhau.
- Lựa chọn: (a) giữ raw value mức call và tính `quantile_cont(rtt, 0.95)` trên tập con khi truy vấn - 300k dòng, DuckDB trả lời trong mili giây; đây là lựa chọn MVP. (b) histogram bucket cố định (đếm cộng được) rồi nội suy. (c) sketch mergeable: t-digest (chính xác ở đuôi), DDSketch (đảm bảo sai số tương đối α) - cần khi dữ liệu lớn/streaming. DuckDB có `approx_quantile` (t-digest) và `quantile_cont` chính xác.
- Mart không lưu P95 nếu cần re-aggregate; lưu histogram/sketch hoặc đọc từ feature layer. CI cho percentile ở segment nhỏ: bootstrap hoặc CI dựa trên order statistics (rank theo binomial).

### 3.5 Simpson's paradox, stratification, standardization
- So sánh TURN A và B: A tốt hơn ở mọi network type/ISP nhưng tệ hơn tổng thể nếu A được chọn nhiều cho ISP/mạng khó. Selector không random nên confounding mạnh.
- Xử lý: (1) so sánh trong stratum (cùng region × ISP × network × hour-bucket); (2) direct standardization: rate_std(TURN) = Σ_s w_s · p_{TURN,s} với w_s là phân phối mix chuẩn (vd mix toàn cục); (3) hiển thị decomposition mix vs rate; (4) dashboard cho chọn "chuẩn hoá theo..." và cảnh báo khi mix lệch lớn.
- Đánh giá nhân quả của policy cần exploration/randomization hoặc off-policy evaluation (IPS/DR); simulator có ground truth nên dùng được ở giai đoạn sau.

### 3.6 Multiple comparisons
- Quét hàng nghìn segment ở α = 0,05 sinh hàng chục false alarm. Quy trình BH: tính p-value mỗi segment (kiểm định hai tỷ lệ hoặc binomial exact so với baseline), sắp p_(1) <= ... <= p_(m), lấy k lớn nhất thoả p_(k) <= (k/m)·q (q = 0,05-0,1), cờ mọi i <= k. Kiểm soát FDR, ít bảo thủ hơn Bonferroni (α/m).
- Kết hợp shrinkage (3.3), ngưỡng effect size tối thiểu (vd >= 3 điểm %) và n_min để alert có ý nghĩa vận hành. Quét phân cấp: mức thô trước, drill xuống khi có tín hiệu.

## 4. Anomaly / degradation detection

### 4.1 Dữ liệu
Mỗi entity (TURN, ISP, Region, hoặc tổ hợp) có chuỗi KPI theo giờ/ngày: success_rate, fallback_rate, P95 RTT, packet loss. Bucket thưa -> dùng tỷ lệ kèm n và shrinkage; bỏ bucket n < n_min.

### 4.2 Phương pháp (theo thứ tự ưu tiên cho MVP)
1. Seasonal baseline hour-of-week + robust z-score. baseline_t = median của cùng slot (weekday, hour) K tuần trước. Với 30 ngày dữ liệu mỗi slot chỉ có ~4 điểm, nên gộp thành hour-of-day × (weekday/weekend). Phân tán dùng MAD:
   ```
   z_robust = (x_t - median) / (1,4826 · MAD)      # tương đương 0,6745·(x - median)/MAD
   ```
   Cờ khi |z| > 3,5 (Iglewicz-Hoaglin). Với tỷ lệ, chuẩn hoá thêm sai số nhị thức sqrt(p(1-p)/n) để tránh false alarm khi n nhỏ.
2. EWMA: `S_t = λ·x_t + (1-λ)·S_{t-1}`, λ ≈ 0,2-0,3; cảnh báo khi |S_t - μ0| > L·σ·sqrt(λ/(2-λ)), L ≈ 3. Bắt suy giảm nhỏ kéo dài.
3. CUSUM một phía cho suy giảm: `C_t = max(0, C_{t-1} + (μ0 - x_t)/σ - k)`, cảnh báo khi C_t > h; k ≈ 0,5, h ≈ 4-5 (chọn theo ARL mong muốn). Bắt change-point/drift chậm; reset sau khi xử lý.
4. STL decomposition (`statsmodels.tsa.seasonal.STL`, robust=True): tách trend/seasonal(24h)/residual, áp robust z lên residual. 30 ngày chỉ đủ seasonal 24h, không đủ weekly -> bước nâng cấp.
5. Sau MVP: Prophet, isolation forest, BOCPD.

Kiến trúc: tín hiệu nhanh (robust z theo giờ) + tín hiệu chậm (CUSUM/EWMA theo ngày); gộp alert theo entity, dedup trong cửa sổ, áp BH khi quét nhiều entity; mỗi alert lưu `evidence` (baseline, giá trị, n, CI) để giải thích trên dashboard.

### 4.3 Đánh giá bằng incident inject
Simulator tiêm incident ground-truth: (entity, start, end, loại: step drop / ramp dần / spike ngắn, độ lớn, vd +40ms RTT hoặc -5 điểm success). Lưu `incident_id` ở bảng truth riêng, không lẫn vào dữ liệu pipeline.
- Khớp alert-incident: alert đúng nếu cùng entity và thời điểm trong [start, end + grace].
- Metric: Precision = TP/(TP+FP) (theo episode alert), Recall = TP/(TP+FN) (theo incident), F1, detection delay = t_first_alert - t_start (median, P90), false alarms/entity-week, detection curve theo độ lớn, recall theo kích thước segment.
- Thiết kế: nhiều seed, quét ngưỡng (PR curve cho z, h), incident đa dạng độ lớn/độ dài/segment size; tách tập tuning và test; có chuỗi sạch để đo false positive rate; báo cáo kèm bootstrap CI qua seeds; so với baseline static threshold để chứng minh giá trị.

## 5. Dashboard

### 5.1 So sánh
| Tiêu chí | Streamlit | Grafana | Superset | Metabase |
|---|---|---|---|---|
| Drill-down tuỳ biến theo segment | Tốt (widget, session state) | Trung bình (variables, data links) | Tốt (drill-by, cross-filter) | Trung bình |
| Per-call Decision Trace (view tuỳ biến) | Rất tốt (tự dựng) | Khó | Khó | Khó |
| CI, n, ẩn n nhỏ, shrinkage | Tự do | Hạn chế | Hạn chế | Hạn chế |
| Time-series ops + alerting | Yếu | Rất tốt | Trung bình | Yếu |
| Cài đặt laptop | pip | server + datasource | nặng (Docker) | Java/Docker |
| Đọc DuckDB/Parquet | Trực tiếp | Cần plugin | Có connector | Driver cộng đồng |

Chọn Streamlit: cùng ngôn ngữ, tái dùng mã thống kê, trace view tuỳ biến. Mẹo: `st.cache_data` khoá theo `dt`, DuckDB read-only, mart đã aggregate, `st.dialog`/`st.fragment` cho drill-down, phân trang trace. Grafana là bổ sung sau MVP cho service health/alert.

### 5.2 Observability cho service health
- RED (request-driven, cho API selector): Rate, Errors (error rate, fallback rate), Duration (P50/P95/P99 từ histogram).
- USE (tài nguyên): Utilization, Saturation, Errors, vd allocation đang dùng so với capacity TURN.
- Four golden signals (Google SRE): latency, traffic, errors, saturation.
- SLI/SLO gợi ý:
  - Availability = request hợp lệ thành công / tổng; SLO 99,5% / 30 ngày.
  - Latency SLI = tỷ lệ request < 200 ms; SLO 99% (ngưỡng đặt theo yêu cầu call setup).
  - Fallback rate (chọn TURN mặc định thay vì theo model) < 2%.
  - Data freshness: `now - max(event_ts)` < 15 phút (real log); với simulator: pipeline ngày D xong trước cut-off.
  - Error budget = 1 - SLO; theo dõi burn rate.
- Tách trang service health (selector có sống/nhanh không) khỏi trang network quality KPI (TURN/ISP có tốt không). Log event `api_request` từ API vào cùng pipeline để tái dùng stack.

## 6. Kế hoạch gợi ý (6 tuần)
- Tuần 1: layout Parquet, `run(date)`, dedup, clean + quarantine, test idempotency.
- Tuần 2: DQ catalog (pandera + SQL), `dq_results`, inject lỗi trong simulator (dup, late, skew, orphan).
- Tuần 3: feature + mart, Wilson/EB, min-n, percentile từ raw.
- Tuần 4: dashboard drill-down + Decision Trace.
- Tuần 5: detector (robust z, CUSUM), incident inject, evaluation.
- Tuần 6: BH/FDR, standardization, health page, hardening, tài liệu.

## 7. Tài liệu tham khảo (cần verify link trước khi trích chính thức)
- DuckDB Hive partitioning: https://duckdb.org/docs/data/partitioning/hive_partitioning
- DuckDB Parquet: https://duckdb.org/docs/data/parquet/overview
- DuckDB aggregate functions (quantile_cont, approx_quantile): https://duckdb.org/docs/sql/functions/aggregates
- Polars lazy API: https://docs.pola.rs/user-guide/lazy/
- dbt-duckdb: https://github.com/duckdb/dbt-duckdb
- dbt incremental models: https://docs.getdbt.com/docs/build/incremental-models
- SQLMesh: https://sqlmesh.readthedocs.io/
- pandera: https://pandera.readthedocs.io/
- Great Expectations: https://docs.greatexpectations.io/
- Soda Core / SodaCL: https://docs.soda.io/
- Wilson (1927), JASA 22(158): https://doi.org/10.1080/01621459.1927.10502953
- Brown, Cai, DasGupta (2001), Interval Estimation for a Binomial Proportion: https://doi.org/10.1214/ss/1009213286
- Robinson, Introduction to Empirical Bayes: http://varianceexplained.org/r/empirical_bayes_baseball/
- Dunning and Ertl, t-digest: https://arxiv.org/abs/1902.04023
- Masson, Rim, Lee, DDSketch (VLDB 2019): https://www.vldb.org/pvldb/vol12/p2195-masson.pdf
- Simpson's paradox (SEP): https://plato.stanford.edu/entries/paradox-simpson/
- Benjamini and Hochberg (1995), JRSS B: https://doi.org/10.1111/j.2517-6161.1995.tb02031.x
- Iglewicz and Hoaglin (1993), How to Detect and Handle Outliers, ASQC Quality Press (modified z-score 3,5)
- Cleveland et al. (1990), STL, J. Official Statistics: https://www.wessa.net/download/stl.pdf
- statsmodels STL: https://www.statsmodels.org/stable/generated/statsmodels.tsa.seasonal.STL.html
- NIST e-Handbook, EWMA/CUSUM: https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm
- Page (1954), Continuous Inspection Schemes, Biometrika (CUSUM)
- Streamlit: https://docs.streamlit.io/
- Grafana: https://grafana.com/docs/
- Superset: https://superset.apache.org/docs/intro
- Metabase: https://www.metabase.com/docs/latest/
- Wilkie, The RED Method: https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/
- Gregg, The USE Method: https://www.brendangregg.com/usemethod.html
- Google SRE Book, Monitoring Distributed Systems: https://sre.google/sre-book/monitoring-distributed-systems/
- Google SRE Workbook, Implementing SLOs: https://sre.google/workbook/implementing-slos/
