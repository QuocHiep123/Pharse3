# CallDiag MVP: bài toán, phạm vi và luồng chạy

Tài liệu này mô tả MVP CallDiag giải bài toán gì, ranh giới của nó, dữ liệu đi qua hệ thống ra sao và vì sao thiết kế như vậy. Cách cài đặt và chạy xem `README.md`.

## 1. Bài toán

Khi một cuộc gọi WebRTC chất lượng kém hoặc không kết nối được, kỹ sư vận hành phải trả lời:

1. Cuộc gọi hỏng ở **giai đoạn nào** của vòng đời (setup, SDP, ICE, media)?
2. Chất lượng suy giảm **từ lúc nào đến lúc nào**?
3. **Thành phần nào** có khả năng liên quan (mạng, TURN server, client)? Thành phần nào đã được loại trừ, và dựa trên bằng chứng gì?
4. Hệ thống **chưa biết** điều gì, và cần kiểm tra gì tiếp?

Làm tay việc này nghĩa là đọc trace, metric và log từ nhiều nguồn rồi tự ghép. Rủi ro lớn nhất không phải bỏ sót mà là **kết luận bừa**: thấy TURN CPU cao liền đổ lỗi cho TURN dù cuộc gọi không đi qua TURN, thấy metric trống liền coi là "bằng 0, ổn", hoặc trình bày một phỏng đoán như sự thật.

**Mục tiêu của MVP:** tự động hóa quy trình trên cho một cuộc gọi, và xuất **Incident Report** trong đó mọi khẳng định đều truy ngược được về dữ liệu gốc. Report tách rõ điều **quan sát được** (FACT) với điều **suy ra** (INFERENCE), và nói thẳng điều chưa biết.

## 2. Điều MVP phải chứng minh

| # | Tiêu chí | Kịch bản kiểm |
|---|---|---|
| 1 | Khoanh **đúng phase** lỗi; fail sớm thì không phân tích QoS | S3, S5 |
| 2 | Khoanh **đúng khoảng thời gian** bất thường (sai số ±5 s) | S1, S2, S6 |
| 3 | FACT chỉ là dữ kiện có `refs` tới event / metric / log; INFERENCE luôn có `supported_by: [F…]` | tất cả |
| 4 | Dùng TURN ≠ TURN lỗi | S4 |
| 5 | TURN quá tải nhưng không nằm trên media path ≠ nguyên nhân | S2 |
| 6 | Thiếu dữ liệu ≠ bằng 0: hạ confidence, chuyển thành giả thuyết | S6 |
| 7 | Không bịa incident khi cuộc gọi khỏe | S0 |

## 3. Phạm vi

**Trong phạm vi**

- Cuộc gọi **1:1**: alice (caller) ↔ bob (callee). Media đi P2P trực tiếp hoặc qua TURN relay `turn-01`.
- Điểm đo: stats phía **alice** (RTT, jitter, packet loss, inbound bitrate, client CPU) và metric của `turn-01` (CPU). Stats phía bob được ghi rõ là *không thu thập*.
- Dữ liệu **giả lập, tất định** (seed cố định), một synthetic clock UTC chung cho mọi nguồn.
- Phát hiện bất thường bằng **rule thống kê** (không ML); suy luận bằng **rule engine** tất định.
- LLM **tùy chọn**, chỉ viết lại phần tóm tắt.
- Đầu ra: JSON, Markdown, OpenTelemetry-like trace, UI Streamlit, bảng eval.

**Ngoài phạm vi (cố ý)**

SFU / gọi nhóm, WebRTC stack thật, storage thật (Elasticsearch / OpenSearch), multi-agent (LangGraph), ML anomaly detection và SHAP, active learning, auth, database, Docker. Các module được tách rời để có thể thay thế từng phần sau này (mục 9).

## 4. Dữ liệu đầu vào

Mỗi cuộc gọi là một `CallTelemetry` (`calldiag/models.py`), lưu được thành JSON (`data/scenarios/S*.json`):

| Thành phần | Nội dung | ID |
|---|---|---|
| `meta` | `call_id`, thời gian bắt đầu/kết thúc, caller/callee, TURN server, metric kỳ vọng, nguồn bị thiếu | `call-1001` (trung tính, không chứa tên kịch bản) |
| `events` | Trace event theo phase: `CALL_CREATED`, `OFFER_SENT`, `ICE_PAIR_FAILED`, `ICE_SELECTED_PAIR`, `DTLS_CONNECTED`, `FIRST_RTP_RECEIVED`, `CALL_ENDED`… | `ev-017` |
| `metrics` | Sample 1 giây/lần: `rtt_ms`, `jitter_ms`, `packet_loss_pct`, `bitrate_kbps`, `client_cpu_pct`, `turn_cpu_pct`; giá trị thiếu là `null` | `m-alice-rtt_ms-0080` |
| `logs` | Log có level (DEBUG…ERROR), category (signaling, ice, turn, dtls, media, system), component; có cả log của call khác trên cùng TURN | `log-042` |

Các ID sinh trong pipeline: anomaly `an-03`, incident interval `inc-01`, FACT `F7`, INFERENCE `I1`, HYPOTHESIS `H1`, REJECTED `R1`.

## 5. Luồng chạy

```
CallTelemetry
  │
  ├─[1] Timeline + phase      → 5 PhaseSpan (ok / degraded / failed / skipped / incomplete),
  │                             selected path, trace metrics, OTel-like trace
  ├─[2] Anomaly detection     → MetricAnomaly[], IncidentInterval[], MissingMetric[]   (chỉ khi Media đã thiết lập)
  ├─[3] Correlation           → PathContext + EvidenceBundle (log liên quan, component nào trên path)
  ├─[4] FACT extraction       → FactStore F1…Fn, mỗi FACT có refs
  ├─[5] Reasoning (6 rule)    → INFERENCE / HYPOTHESIS / REJECTED + UNKNOWN + NEXT CHECK
  ├─[6] Report assembly       → IncidentReport (severity, headline, summary template)
  ├─[7] LLM summary (tùy chọn)→ viết lại 2 đoạn summary
  └─[8] Validator             → loại phần vi phạm guardrail, ghi lỗi/cảnh báo
        │
        ├─ CLI: out/reports/<S>.json, <S>.md, out/traces/<S>.otel.json
        ├─ Streamlit UI: waterfall 5 phase, chart, log, report có truy vết
        └─ Eval: so với kết quả mong đợi của từng kịch bản
```

Mỗi bước là hàm thuần trong `calldiag/pipeline/`, nối với nhau ở `pipeline/run.py`. Ngưỡng và hằng số đều ở `calldiag/config.py`.

### [1] Dựng vòng đời cuộc gọi (`timeline.py`, `phases.py`)

Gom event theo 5 phase: **Call Setup → Offer/Answer SDP → ICE Candidate Exchange → Media Established → Call Termination**. Mỗi phase có event bắt đầu, event thành công và event thất bại; ví dụ ICE bắt đầu ở `ICE_GATHERING_START`, thành công ở `ICE_CONNECTED`, thất bại ở `ICE_FAILED`.

- Phase thất bại → các phase sau là **skipped**, không phân tích QoS cho chúng.
- Lấy **selected candidate pair** (ví dụ `relay↔srflx qua turn-01`) để biết TURN có nằm trên media path hay không.
- Tính trace metrics: time-to-accept, time-to-answer, ICE gathering/checking, DTLS, time-to-first-media, thời lượng.

### [2] Phát hiện bất thường (`anomaly.py`)

Chỉ chạy khi phase Media đã được thiết lập.

- **Baseline**: median của 20 s đầu sau khi media thiết lập.
- Một sample bị đánh dấu khi **rolling mean 5 s** vượt **cả** ngưỡng tuyệt đối **và** ngưỡng tương đối so với baseline. Ví dụ RTT ≥ 250 ms và ≥ 2× baseline; loss ≥ 5 % và ≥ 3× baseline; bitrate ≤ 900 kbps và ≤ 0.6× baseline; TURN CPU ≥ 85 % và ≥ 1.5× baseline.
- Các đoạn cách nhau ≤ 3 s được gộp; đoạn ngắn hơn 5 s bị bỏ (tránh nhiễu).
- Anomaly QoS (RTT, jitter, loss, bitrate) gộp thành **QoS incident interval** (cách nhau ≤ 5 s). Anomaly tài nguyên (TURN CPU, client CPU) **tự nó không tạo incident**; nó chỉ được gắn vào incident nếu chồng lấn trong ±10 s.
- Metric thiếu ≥ 50 % sample → ghi **MissingMetric**, không thay bằng 0.
- Phase Media có incident → chuyển từ `ok` sang `degraded`.

### [3] Tương quan log (`correlate.py`)

Với mỗi incident (hoặc phase thất bại), lấy log trong khoảng **[bắt đầu − 10 s, kết thúc + 10 s]**. Mỗi log được chấm điểm: điểm theo level, cộng nếu component **nằm trên media path**, cộng nếu category khớp loại sự cố, trừ nếu log thuộc **call khác**. Kết quả là `EvidenceBundle`: khoảng thời gian trọng tâm, log liên quan, và evidence còn thiếu (ví dụ không có log TURN).

### [4] Trích FACT (`facts.py`)

Đây là nơi duy nhất tạo FACT. Mỗi FACT có `kind`, câu mô tả tiếng Việt và `refs` tới dữ liệu gốc. Ví dụ từ S1:

| ID | Kind | Statement | Refs |
|---|---|---|---|
| F6 | selected_path | Selected candidate pair: relay↔srflx qua TURN turn-01 | `ev-021` |
| F8 | metric_change | TURN CPU (turn-01) tăng từ 42% lên 95% (đỉnh 98%) trong 10:21:15–10:21:44 | `an-01`, `m-turn-01-turn_cpu_pct-0075`, … |
| F12 | metric_change | RTT (alice) tăng từ 80 ms lên 311 ms trong 10:21:21–10:21:42 | `an-05`, … |
| F13 | metric_level | Client CPU (alice) median 29%, max 35%; không ghi nhận anomaly theo rule | `m-alice-client_cpu_pct-0079`, … |
| F18 | log_event | turn-01 ERROR: "relay send queue overflow: dropped 132 packets" | `log-029` |

FACT **không chứa từ nhân quả** ("gây ra", "do", "because", "likely"…). Nó ghi điều code chứng minh được: "không ghi nhận anomaly theo rule" thay vì "không vượt ngưỡng".

### [5] Suy luận (`rules.py`, `reasoning.py`)

Mỗi rule có **precondition**, **điều kiện bắt buộc**, **booster**, **counter-evidence** và **missing penalty**. Mỗi điều kiện chỉ đọc FACT và trả `TRUE` / `FALSE` / `UNKNOWN`.

```
precondition không thỏa      → bỏ qua rule
điều kiện bắt buộc FALSE      → REJECTED  (kèm FACT phản chứng)
điều kiện bắt buộc UNKNOWN    → HYPOTHESIS (kèm evidence còn thiếu + cách kiểm chứng)
tất cả TRUE                   → INFERENCE, confidence bắt đầu High rồi trừ bậc:
                                 −1 nếu có booster nhưng không booster nào được xác minh
                                 −1 cho mỗi counter-evidence đúng
                                 −1 cho mỗi dữ liệu quan trọng bị thiếu
```

| Rule | Bắt buộc | Booster / counter / penalty |
|---|---|---|
| `SIGNALING_FAILURE` | Offer/Answer failed, quan sát được ANSWER timeout | + log signaling WARN/ERROR |
| `ICE_CONNECTIVITY_FAILURE` | ICE failed, mọi candidate pair đã thử đều thất bại | + relay pair cũng đã thử và thất bại |
| `TURN_OVERLOAD_DEGRADATION` | QoS incident, path qua TURN, TURN CPU **của server trên path** cao trong incident | + TURN CPU tăng trước QoS, + log TURN trên path; − client CPU cao |
| `NETWORK_PATH_DEGRADATION` | QoS incident có RTT hoặc loss bất thường | + nhiều metric QoS cùng suy giảm; − client CPU cao; − thiếu TURN CPU trên path relay |
| `RELAY_NOT_A_FAULT` | Đi qua TURN, không QoS anomaly, đủ 5 phase | |
| `HEALTHY_CALL` | Media thiết lập, không QoS anomaly, đủ 5 phase | |

INFERENCE được xếp theo **độ cụ thể** của rule (lỗi phase > TURN > mạng chung), rồi theo confidence; `I1` là kết luận chính. Rule nào cũng mang theo **alternatives**, **unknowns** và **next checks** cụ thể (ví dụ "so sánh TURN CPU với số allocation trong 10:21:19–10:21:44").

### [6] Lắp report (`report.py`, `render.py`)

- **Severity** tách khỏi confidence: `critical` nếu một phase (trừ Termination) thất bại; `none` nếu không có incident; `major` nếu incident ≥ 20 s hoặc loss đỉnh ≥ 10 %; còn lại `minor`.
- **Headline** theo rule chính, ví dụ "Chất lượng suy giảm 10:21:19–10:21:44, có khả năng liên quan tới quá tải TURN server".
- Report Markdown gồm: vòng đời 5 phase, trace metrics, timeline, FACTS, log liên quan, INFERENCES, HYPOTHESES, REJECTED, UNKNOWN, NEXT CHECK, evidence bundle, engineering summary (có trích `[F…]`), executive summary (cho người không chuyên), validation.

### [7] LLM summary (tùy chọn, `calldiag/llm/`)

LLM chỉ nhận phần report đã kiểm chứng (FACT, INFERENCE, HYPOTHESIS, REJECTED, UNKNOWN), **không** thấy tên kịch bản hay call ID, và chỉ viết lại hai đoạn summary. Nó không tạo hay sửa FACT, kết luận, confidence, severity. Hiện dùng OpenAI qua Protocol `LLMClient`; response được cache để chạy lại cho cùng kết quả.

### [8] Validator (`validator.py`)

Validator dựng lại anomaly từ telemetry gốc rồi kiểm:

- FACT: có refs, refs tồn tại, không chứa từ cấm.
- INFERENCE / HYPOTHESIS / REJECTED: chỉ trỏ tới FACT có thật; confidence hợp lệ; primary khớp.
- Summary: không trích ID lạ. Riêng summary do LLM viết còn phải: không thêm con số không có trong đầu vào, executive ≤ 80 từ và không có trích dẫn, engineering có trích dẫn.

Phần vi phạm bị loại; summary LLM vi phạm thì quay về bản template; mọi lỗi và cảnh báo được ghi lại trong report. `--strict` trả exit 1 nếu report có lỗi.

## 6. Kịch bản kiểm thử

| ID | Tình huống | Hệ thống phải kết luận | Hành vi được kiểm |
|---|---|---|---|
| S0 | P2P, mạng ổn | `HEALTHY_CALL`, severity none | Không bịa incident |
| S1 | Qua TURN; TURN CPU 40→95 % trước, rồi RTT 80→310 ms, loss 12 % | `TURN_OVERLOAD_DEGRADATION`, High, major | Tương quan TURN trên path + thứ tự thời gian |
| S2 | P2P suy giảm; `turn-01` quá tải vì call khác | `NETWORK_PATH_DEGRADATION`, High; TURN **REJECTED** | Không đổ lỗi thành phần ngoài path |
| S3 | Mọi candidate pair timeout | `ICE_CONNECTIVITY_FAILURE`, High, critical; Media skipped | Khoanh phase, không phân tích QoS |
| S4 | Qua TURN, chất lượng tốt | `RELAY_NOT_A_FAULT` | Dùng TURN ≠ lỗi |
| S5 | Không nhận được ANSWER | `SIGNALING_FAILURE`, High, critical; ICE + Media skipped | Fail sớm nhất |
| S6 | Giống S1 nhưng collector không gửi TURN CPU | `NETWORK_PATH_DEGRADATION`, **Medium**; TURN là **HYPOTHESIS** | Thiếu dữ liệu ≠ 0 |

## 7. Đánh giá

`python -m calldiag eval` chạy cả 7 kịch bản và so với kết quả mong đợi (`calldiag/scenarios/expected.py`):

- trạng thái 5 phase; có incident hay không; khoảng incident (±5 s);
- rule chính, confidence, severity;
- rule bắt buộc phải có (INFERENCE / HYPOTHESIS / REJECTED) và rule bị cấm;
- metric phải được báo thiếu;
- validator pass và mọi ID truy vết được.

Kết quả hiện tại: **7/7 PASS**. Bộ test (`pytest -q`, khoảng 480 test) có cả các ca cố tình làm sai kỳ vọng để chứng minh từng check thật sự bắt được lỗi, và smoke test UI.

**Definition of Done:** `pytest -q` xanh; `eval` 7/7 PASS; UI hiển thị waterfall 5 phase, chart có vùng incident, log được tô sáng, và chọn một FACT/INFERENCE thì chart và log tương ứng được highlight.

## 8. Nguyên tắc thiết kế

| Nguyên tắc | Lý do |
|---|---|
| FACT chỉ do code tất định sinh, luôn có refs | Người đọc kiểm được mọi dữ kiện; LLM không thể "bịa" dữ kiện |
| INFERENCE luôn trích FACT; confidence High/Medium/Low kèm lý do | Kết luận có căn cứ; tránh con số phần trăm tạo cảm giác chính xác giả |
| Pipeline không đọc `scenario_id`, `title`, không rẽ nhánh theo `call_id` | Kết luận chỉ đến từ dữ liệu; eval không bị "học thuộc đáp án" |
| Missing là `None`, sinh FACT `missing_data`, điều kiện thành `UNKNOWN` | Thiếu dữ liệu không được biến thành "khỏe" |
| TURN chỉ bị quy trách nhiệm khi nằm trên selected path | Tránh đổ lỗi theo tương quan bề mặt (S2) |
| Resource anomaly không tự tạo incident | Incident được định nghĩa từ trải nghiệm cuộc gọi (QoS), tài nguyên là evidence |
| Severity và confidence là hai trục riêng | "Nghiêm trọng" khác "chắc chắn" |
| Ngưỡng ở `config.py`, dữ liệu kịch bản ở `scenarios/` | Chỉnh ngưỡng một chỗ; pipeline không thấy dữ liệu theo kịch bản |
| Hàm thuần trong `pipeline/`, I/O chỉ ở CLI / UI / `io.py` | Dễ test, dễ thay nguồn dữ liệu |
| Tất định (seed, synthetic clock, cache LLM) | Demo và eval lặp lại được |

## 9. Hướng mở rộng

| Hướng | Thay ở đâu |
|---|---|
| Đọc telemetry thật từ OpenSearch / Elasticsearch | Thêm loader tạo `CallTelemetry` trong `io.py`; pipeline giữ nguyên |
| Stats hai phía, gọi nhóm qua SFU | Mở rộng `CallMeta` và `PathContext`; thêm rule cho SFU |
| ML anomaly detection, SHAP | Thay hoặc bổ sung `detect_anomalies`, vẫn xuất `MetricAnomaly` để FACT/rule không đổi |
| Multi-agent (LangGraph) | Agent dùng FACT làm đầu vào và phải qua cùng validator; rule engine hiện tại là baseline để so |
| Thêm kịch bản / benchmark | Thêm module trong `scenarios/` + kết quả mong đợi; không sửa pipeline |

## 10. Thuật ngữ

| Thuật ngữ | Nghĩa |
|---|---|
| FACT | Dữ kiện quan sát trực tiếp hoặc phép tính truy ngược được về dữ liệu gốc |
| INFERENCE | Kết luận mà mọi điều kiện bắt buộc của rule đều được FACT xác nhận |
| HYPOTHESIS | Giải thích khả dĩ nhưng thiếu evidence, kèm cách kiểm chứng |
| REJECTED | Giả thuyết bị loại vì có FACT mâu thuẫn |
| UNKNOWN | Điều evidence hiện có không phân biệt được |
| NEXT CHECK | Hành động cụ thể giúp giảm bất định |
| QoS incident | Khoảng thời gian có anomaly trên RTT, jitter, packet loss hoặc bitrate |
| Resource anomaly | Anomaly trên TURN CPU hoặc client CPU; tự nó không tạo incident |
| Selected path | Candidate pair được ICE chọn; xác định TURN có nằm trên media path không |
