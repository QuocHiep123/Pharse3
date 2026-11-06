# Đề xuất sửa Data Contract v0.4.0 thành v0.5.0

**Từ:** Đoàn. **Gửi:** Hiệp.

**Đối chiếu với:** `docs/contracts/data-contract.md` (v0.4.0), `docs/superpowers/specs/2026-11-04-turn-intelligence-design.md` và `docs/contracts/erd-and-flow.html`, nhánh `docs/w1-design-and-data-contract`, commit `e4d84f8`.

**File kèm:**

- [`data_contract_v0.5.0_de_xuat.schema.yaml`](data_contract_v0.5.0_de_xuat.schema.yaml): contract thu thập, viết bằng JSON Schema 2020-12.
- [`dac_ta_sau_thu_thap_v0.5.0_de_xuat.schema.yaml`](dac_ta_sau_thu_thap_v0.5.0_de_xuat.schema.yaml): các lớp sau thu thập. Đây là bản chuyển tiếp để không mất nội dung; đặc tả đầy đủ của từng lớp viết sau.
- `KET_QUA.md`: kết quả lab ICE mà mục 1.3 trích dẫn.

> Contract trong đề xuất này là bản thiết kế dữ liệu raw có thể thu thập: nghĩa dữ liệu, schema, nguồn và khả năng thu thập, khóa liên kết, đơn vị và thời gian, nullability. Feature, dự đoán của mô hình, KPI và giả lập được giữ ở file đi kèm. Tài liệu không chốt thuật toán, cách triển khai simulator, detector, ngưỡng vận hành, thiết kế thí nghiệm hay lịch triển khai.

Trong tài liệu này, "§" là mục của contract v0.4.0, "spec §" là mục của spec. Tên field là gợi ý để trao đổi.

## Mục lục

1. [Tóm tắt và việc cần Hiệp phản hồi](#1-tóm-tắt-và-việc-cần-hiệp-phản-hồi)
2. [Ranh giới theo vòng đời dữ liệu](#2-ranh-giới-theo-vòng-đời-dữ-liệu)
3. [Nguồn thu và khả năng thu thập](#3-nguồn-thu-và-khả-năng-thu-thập)
4. [Call logs](#4-call-logs)
5. [getStats và sự kiện ICE](#5-getstats-và-sự-kiện-ice)
6. [TURN metrics](#6-turn-metrics)
7. [Probe giữa các TURN](#7-probe-giữa-các-turn)
8. [Danh mục TURN và danh tính](#8-danh-mục-turn-và-danh-tính)
9. [Decision Log](#9-decision-log)
10. [Đầu vào của Outcome Log và khóa nối](#10-đầu-vào-của-outcome-log-và-khóa-nối)
11. [Các lớp sau thu thập](#11-các-lớp-sau-thu-thập)
12. [Phần hoãn và phần bỏ](#12-phần-hoãn-và-phần-bỏ)
13. [Bất biến và ví dụ dữ liệu](#13-bất-biến-và-ví-dụ-dữ-liệu)
14. [Xác nhận nguồn thu](#14-xác-nhận-nguồn-thu)
15. [Version, ánh xạ khái niệm và schema](#15-version-ánh-xạ-khái-niệm-và-schema)
16. [Ngoài phạm vi](#16-ngoài-phạm-vi)
17. [Mức độ kiểm chứng](#17-mức-độ-kiểm-chứng)

---

## 1. Tóm tắt và việc cần Hiệp phản hồi

**Mình chưa thể duyệt v0.4.0 theo §16, và đề nghị hai bên ra v0.5.0 theo đề xuất này.** Pipeline, KPI và cách đánh giá của v0.4.0 là nền tốt, mình muốn giữ. Phần cần sửa là nghĩa của một số dữ liệu, ranh giới giữa các lớp, và những dữ liệu chưa ai xác nhận thu được.

### 1.1. Ba vấn đề chính

- **Contract đang gộp nhiều lớp.** Dữ liệu thu từ nguồn, cột do pipeline tính, feature, KPI và truth của giả lập nằm chung, nên khó trả lời câu hỏi cơ bản: BE và WebRTC core thật sự phải thu gì, và có thu được không. Đề xuất tách thành contract thu thập và đặc tả các lớp sau.
- **Sai đơn vị quyết định.** Contract theo "đi rank 1 × rank 1, lỗi thì thử rank kế" và ghi quyết định theo từng bên. Hướng thuật toán của mình là: Selector chọn cặp trong top-k theo khoảng tin cậy, đặt cặp dẫn đầu lên đầu hai danh sách, còn ICE chọn cặp thực tế theo priority.
- **Chưa rõ nguồn thu.** Nhiều field được coi là luôn có, dù chưa ai xác nhận thu được, nhất là `path_leg_measurement`: §0.1 xếp vào KPI-grade 100%, trong khi §15 và giả định A2 ghi phương pháp chưa xác minh.

### 1.2. Giữ nền tảng

Giữ snapshot bất biến (I12, I13), cách ly truth, `pcr_itt` hai cận, `dim_turn_endpoint`, `actual_turn_id`. Các phần này chuyển sang file đi kèm hoặc có sửa nghĩa ở các mục dưới, nhưng ý tưởng không đổi. Nhánh chưa có `contracts/`, nên hiện chỉ cần sửa tài liệu.

### 1.3. Bằng chứng chính

| Nguồn | Kết quả | Ảnh hưởng đến contract |
|---|---|---|
| Lab | ICE đi theo priority, không tìm đường tốt nhất: cặp đầu ghim ở RTT 64 đến 132 ms khi đường tốt nhất là 23 ms | `chosen_rank` không còn nghĩa; cần ghi cặp dẫn đầu |
| Lab | TURN cấp phát chậm hơn có thể bị bỏ. Với Callee, tín hiệu 50 ms giữ đến 60 ms và mất từ 100 ms; tín hiệu 300 ms giữ đến 220 ms và mất từ 300 ms | Không thấy candidate không phải lỗi TURN; độ trễ signaling có thể đổi đường thực tế và `pcr_itt` |
| Lab | TURN hỏng khi cuộc gọi dưới 7 giây thì ICE tự chuyển; từ 8 giây thì không. Phát hiện `disconnected` sau 6,4 đến 7,7 giây; ICE restart 162 đến 193 ms | `trigger = fallback` không phản ánh thực tế; cần dòng thời gian ICE để đo phục hồi |
| Lab | Danh sách 8 chỉ 1 trên 32 cặp có RTT | `ice_candidate_pair` không phải công cụ đo các TURN khác |
| [W3C webrtc-stats](https://www.w3.org/TR/webrtc-stats/) | `url`, `relayProtocol` không được có trên remote candidate | §15 đang ánh xạ sai |
| [RFC 8656 §7.4](https://www.rfc-editor.org/rfc/rfc8656.html) | 486 là quota theo username, 508 là thiếu capacity | Không gộp cả hai thành quá tải |
| `prom_server.c` của coturn, bản 4.6.1 và `master` | Không có bộ đếm lỗi allocation; `turn_traffic_*`, `turn_total_traffic_*` chỉ tính session đã kết thúc | `alloc_failures`, `bandwidth_mbps` chưa có nguồn gần thời gian thực từ exporter |
| [VIA, SIGCOMM 2016](https://cs.cmu.edu/~junchenj/via.pdf), mục 3.2 và 4.4 | Dùng kết quả đầu cuối của đường đã dùng và tomography tuyến tính; dùng số đo giữa các relay do Skype cung cấp cho đường transit | Raw cần số trung bình cấp cuộc gọi, danh tính TURN và probe giữa các TURN |
| MSR-TR-2016-57 (Rødbro, Chou, Dogan), 7 triệu cuộc gọi Skype | Chuyển trọng tâm từ tách được từng thành phần sang dự đoán được đường; mọi quan sát đều cần biết đường đi | Chặng là số ước lượng; danh tính TURN là yêu cầu chính với raw |

**Giới hạn của lab:** Chromium 156 và coturn 4.6.1 trên một máy, chặng giữa không có độ trễ thêm, mọi TURN dùng chung một relay IP, dùng data channel, chưa đo Firefox, Safari và mobile. Các số trên là bằng chứng về cơ chế, không phải tham số production hay luật chung.

### 1.4. Phạm vi phía thuật toán

Đây là câu trả lời phía mình, và đề xuất dựa trên các câu này. Spec có chỗ ghi khác, xem việc số 3 ở mục 1.5.

| Chủ đề | Cách làm | Ảnh hưởng đến contract |
|---|---|---|
| Độ dài danh sách | Tối đa 8 mục mỗi bên, tính riêng UDP, TCP, TLS. Hai baseline trả đúng 8; thuật toán cải tiến trả theo top-k, được ít hơn 8 | `requested_max_list_size`, `returned_list_size`, `client_turn_transport` trên từng mục |
| Thời điểm quyết định | Selector biết Callee ngay từ đầu, một request trả hai danh sách | Bỏ `refined`, hoãn `locked_*`; giữ `info_level` cho trường hợp BE chưa có ngữ cảnh Callee |
| Đổ chuông và tín hiệu | Chưa mô hình hóa | Hoãn các cột cần phép đo thêm; vẫn giữ mốc rẻ cho TTFM |
| Client | ICE chuẩn của WebRTC, trên web và mobile, không sửa SDK | Mọi trường client phải lấy được từ API chuẩn. Bỏ các cột cần hook thấp tầng |
| Loại đường | Cuộc gọi thật có đủ P2P, STUN, TURN, nhưng chỉ xét dữ liệu relay, gồm cả dùng chung một TURN | Xem mục 3.4. Dùng chung một TURN là cặp hai TURN trùng nhau, không cần cột riêng |
| Selector hiện tại | Chưa có, Geo Baseline là baseline | `decision_source = static_config`, `policy_version = static@1` |
| Dữ liệu | Tự giả lập, so với baseline; có ý nghĩa rồi mới đưa contract cho BE và WebRTC core thu thập | Giả lập phải sinh đúng raw của contract; phần xác nhận nguồn thu (mục 14) diễn ra sau, nhưng thiết kế phải khả thi ngay từ bây giờ |
| Thử nghiệm | Tạm thời chưa chạy bóng hay thử trên traffic thật | Hoãn cột thí nghiệm và `decision_mode` |
| Phương pháp | Bám VIA, không đi quá phạm vi đề bài | Số liệu chi tiết hơn số cấp cuộc gọi phải có lý do riêng |
| Danh mục TURN | Tự xây trong giả lập | Giữ cấu trúc `dim_turn`, `dim_turn_endpoint` để sau này hạ tầng điền |

### 1.5. Việc cần Hiệp phản hồi

1. **Việc tách contract:** contract của Hiệp hiện là nguồn duy nhất cho cả feature, KPI và đánh giá. Hiệp có đồng ý tách thành contract thu thập và đặc tả các lớp sau không? Mọi nội dung vẫn được giữ ở file đi kèm (mục 2).
2. **Hướng sửa:** có đồng ý với các mục 3 đến 11 không? Mục nào làm sai dữ liệu hoặc khó cài trong pipeline thì nêu giúp mình tình huống cụ thể.
3. **Giả định A1 và A2:** spec ghi A1 (`k = 4`, rank × rank) có nguồn "Mentor (qua Hiệp)", trong khi mình đang theo 8 mục. A2 có nguồn "Hiệp". Hiệp cho mình biết mentor đã nói cụ thể thế nào, và có gì về cách công ty đo từng chặng không.
4. **Chi tiết schema:** mục 15.3 có các chi tiết mình chọn khi viết YAML. Ba chỗ cần ý kiến nhất là S13 (probe), S15 (bộ đếm) và S16 (tách `call_outcome`).
5. **Version:** thống nhất cách ghi thay đổi phá vỡ tương thích ở mục 15.1.

---

## 2. Ranh giới theo vòng đời dữ liệu

Vòng đời dưới đây là bản tạm thời, chưa chốt:

```text
Call logs + getStats + TURN metrics + probe giữa các TURN
        ↓
Feature tables (leg, backbone, health, load)
        ↓
Ranking Engine → Selector API → client / ICE
                      ↓              ↓
               Decision Log  ←join→  Outcome Log
                      ↓
        Dashboard + Evaluation + cập nhật feature
```

**Cách phân loại một cột:**

| Lớp | Tiêu chí | Nơi đặc tả |
|---|---|---|
| Data Contract thu thập | Một nguồn ghi trực tiếp; trả lời được nguồn nào ghi, qua API hoặc log nào, đơn vị gì, thiếu thì thế nào. Phép trừ giữa hai snapshot do chính nguồn làm vẫn là raw | File contract |
| Decision Log | Hành động và dự đoán của mô hình. Phải ghi lúc quyết định, vì sau này không tính lại chắc chắn được | File contract |
| Pipeline làm sạch | Tính từ raw theo một quy tắc, dù chỉ trên một dòng hoặc một cuộc gọi. Vòng đời chưa vẽ bước này; mình coi nó là phần nối giữa raw và các bước sau | File đi kèm |
| Feature Engineering | Cần cửa sổ thời gian, trọng số, gộp theo nhóm mạng hoặc suy ra từ nhiều cuộc gọi | File đi kèm |
| Labeled Data | Nối Decision Log với Outcome Log rồi gắn nhãn; không tạo thêm dự đoán | File đi kèm |
| Evaluation | KPI và so sánh | File đi kèm |

**Các bảng của v0.4.0 và các bảng đề xuất đi đâu:**

| Lớp | Bảng |
|---|---|
| Contract, tham chiếu | `dim_turn`, `dim_turn_endpoint`, `dim_asn`, `dim_country_area` (mới, mục 8) |
| Contract, Call logs | `call_session`, `client_applied_config` (mới) |
| Contract, getStats và ICE | `ice_event` (mới), `call_stats_epoch`, `call_stats_5s` |
| Contract, TURN metrics | `turn_health_1m`, `turn_allocation` |
| Contract, probe | `turn_probe` (mới, tách từ `path_leg_measurement`) |
| Contract, Decision Log | `selector_decision`, `selector_decision_pair` (mới) |
| Contract, đầu vào Outcome Log | `call_outcome`, `client_call_report` (mới) |
| Contract, hoãn | `candidate_observation` (mới), `ice_candidate_pair` |
| Pipeline làm sạch | `outcome_log` (mới), `ice_attempt`, `ice_attempt_endpoint` (mới), `telemetry_coverage` (mới), `dq_results`, các bảng cột `clean_*` |
| Feature Engineering | `feature_snapshot`, `feat_leg_stats`, `feat_turn_turn`, `feat_turn_health`, `feat_path_history`, `health_snapshot`, `dim_user`. Hoãn: `feat_callee_prior`, `feat_turn_alloc_latency`, `feat_estimated_user_turn_rtt` (mới) |
| Labeled Data, Evaluation | `fact_call`, `metric_config` (mới) |
| Giả lập | `truth_leg_5m`, `incident_truth`, `dirt_log`, `run_manifest`, `benchmark_manifest`, `sim_call_tag` (mới) |
| API và vận hành Selector | `select_request`, `select_response`, `service_health_1m` |

---

## 3. Nguồn thu và khả năng thu thập

### 3.1. Mỗi field phải có nguồn thu

| Mức | Nghĩa | Ví dụ |
|---|---|---|
| A | Service hoặc app tự tạo được sau khi tích hợp | Request và response Selector, lifecycle BE quan sát được |
| B | Thu được có điều kiện | `getStats`, ICE state, exporter |
| C | Cần phép đo hoặc hệ thống mới | Probe giữa các TURN, log TURN có khóa nối |

Mức nguồn không quyết định field là bắt buộc hay nullable. Mỗi field chốt required, nullable hoặc conditional theo từng trạng thái event; ví dụ `response_ts` của Selector không có khi timeout, dù nguồn thuộc mức A.

Một field chỉ được nâng từ "dự kiến" lên "thu được" khi có đủ: owner của nguồn, API hoặc log cụ thể, ví dụ event, đơn vị và đồng hồ, khóa join, hành vi khi thiếu, phạm vi nền tảng và phiên bản.

### 3.2. Tóm tắt khả thi

| Nguồn | Nơi sinh dữ liệu | Có cần sửa SDK không | Đã kiểm chứng đến đâu | Điều chưa chắc |
|---|---|---|---|---|
| Call logs | BE | Không | Mới đọc ánh xạ §15, chưa thấy log thật | Ngữ cảnh Callee, `network_type` trên web |
| getStats về kết nối | Client | Không, app đọc API chuẩn rồi gửi | Lab đọc được trên Chromium 156: `selectedCandidatePairId`, `selectedCandidatePairChanges`, `relayProtocol`, `protocol`, `priority`, `currentRoundTripTime` | Mobile, Firefox, Safari. `address`, `url`, `iceRole` mới theo đặc tả |
| getStats về media | Client | Không | Mới theo đặc tả. Lab dùng data channel nên chưa đo RTP | Chi phí gửi; RTT chỉ có sau RTCP |
| TURN metrics | Hạ tầng TURN | Không liên quan | Đã đọc `prom_server.c` của coturn, chưa có bản công ty dùng | Lỗi allocation chỉ có trong log; nguồn giám sát máy chủ |
| Probe giữa các TURN | Hạ tầng mạng | Không liên quan, nhưng cần hệ thống mới | Chưa có gì | Vị trí đặt, giao thức, chu kỳ |
| Decision Log | BE, từ Selector hoặc cấu hình tĩnh | Không | Hệ thống tự tạo | Trước khi có Selector chỉ có danh sách, không có dự đoán |

### 3.3. Profile quan sát

`observation_profile` mô tả cấu hình nguồn dữ liệu, tách khỏi `policy_version`. Trường này nằm ở `run_manifest`.

| Profile | Dữ liệu |
|---|---|
| `obs_base` | Call logs, getStats và TURN metrics theo capability, Decision Log. Không có probe; health phải khai báo có hay không |
| `obs_active` | `obs_base` thêm probe giữa các TURN. Đây là dạng của vòng đời dữ liệu |
| `obs_infra` | Thêm log của TURN khi có nguồn |

Giữ `obs_base` không có probe để giả lập so được có và không có probe.

**Metadata và trạng thái:**

- **Metadata tĩnh ở cấp profile hoặc nguồn:** `observation_method`, mức hỗ trợ `supported`, `unsupported`, `not_configured`.
- **Trạng thái cụ thể ở bản ghi hoặc coverage record liên kết được:** chưa đo, `stale`, `lost`, `ambiguous`, không áp dụng.
- **Không có dòng dữ liệu thì phần thiếu vẫn phải biểu diễn được:** dùng `telemetry_coverage` theo nguồn, phạm vi và nền tảng.
- **"Không lấy mẫu" không có nghĩa là dữ liệu về đủ.** Coverage thực tế được báo theo nền tảng và policy. Bản ghi có `sequence_no`; cuộc gọi dài có checkpoint.

### 3.4. Phạm vi relay

Trước cuộc gọi không biết sẽ đi relay hay P2P, nên không lọc được từ đầu. Lọc theo "đường được chọn là relay" cũng không được, vì cuộc gọi thất bại không có đường được chọn.

| Phạm vi | Bảng | Quy tắc |
|---|---|---|
| Mọi cuộc gọi | `call_session`, `selector_decision`, `ice_event`, `call_outcome`, `client_call_report` | `ice_event` là căn cứ để lọc |
| Relay hoặc thất bại | `call_stats_epoch`, `call_stats_5s` | Chỉ giữ khi cuộc gọi có lúc đi qua relay, hoặc khi cuộc gọi thất bại |
| Không gắn cuộc gọi | `turn_health_1m`, `turn_allocation`, `turn_probe` | |

"Thất bại" nghĩa là đã bắt máy mà ICE hoặc media không đạt hoặc chưa rõ; cuộc gọi không bắt máy không tính. Trong giả lập, mọi cuộc gọi chạy `ice_transport_policy = relay`.

---

## 4. Call logs

**`call_session`:** giữ khóa, thông tin cuộc gọi, `connection_mode`, `ice_transport_policy`, `be_region`, `be_instance`. Hoãn sáu cột thí nghiệm. `scenario_tag` chuyển sang `sim_call_tag`, `observation_profile` chuyển sang `run_manifest`. Cuộc gọi thật chạy `ice_transport_policy = all`, giả lập chạy `relay`.

**Ngữ cảnh `ctx`:** giữ `user_hash`, `country`, `vn_region`, `city`, `isp`, `asn`, `network_type`, `geo_source`, `geo_mismatch`, `device_id` và các trường về client. `segment_key` chuyển sang Feature Engineering, vì đây là cách gộp nhóm chứ không phải quan sát.

- Vị trí và ISP do BE suy từ IP qua GeoIP.
- `network_type` phải do client báo, và trên web có thể thường xuyên là `unknown`. Mức hỗ trợ theo trình duyệt chưa được kiểm tra.
- Selector biết Callee, nhưng nếu Callee đang offline và chỉ được đánh thức bằng thông báo thì BE có thể chưa có IP hiện tại. Trường hợp này ghi qua `info_level`, và cần hỏi BE khi xác nhận nguồn thu.

**`client_applied_config`:** bằng chứng client đã thực sự dùng cấu hình nào. Danh sách BE đã cấp nằm ở `selector_decision.entries`, nên không lưu lại ở đây. Chỉ khi client dùng cấu hình không tra được qua `applied_decision_id` mới ghi `applied_entries`, và không lưu credential. Bảng này do app ghi, nên ở mức có điều kiện.

Spec đang mâu thuẫn về `refined`: xảy ra lúc đổ chuông (spec §3) hay lúc bắt máy (spec §6.4). Nếu một request trả được hai danh sách thì không cần `refined`, và lý do chính của bảng này chỉ còn là xác nhận cấu hình đã dùng và các lần restart.

---

## 5. getStats và sự kiện ICE

Với một PeerConnection, RTT và loss đều là đầu cuối qua cả hai TURN (§0.2). **getStats không có số đo từng chặng,** nên raw chỉ cần số đầu cuối đúng và biết đúng đường đi.

### 5.1. Dòng thời gian ICE

| Nội dung | Đề xuất |
|---|---|
| Dữ liệu thô | `ice_event` theo từng endpoint: `call_id`, `attempt_seq`, `pc_id`, `ice_generation`, `side`, `device_id`, `event_type`, `event_mono_ms`, `ice_state`, `dtls_state`, loại candidate, `local_turn_url`, `relayed_ip_local`, `relayed_ip_remote`, `client_turn_transport`, `candidate_protocol`, `selected_pair_changes`, `ice_role`, `trigger`, `reason`, `source`, `poll_interval_ms`. Các ID phải có từ producer |
| Danh tính | `local_turn_url` lấy từ `url` của local candidate, nên biết thẳng mục trong danh sách mà không chỉ dựa vào tra IP. `local_turn_id`, `remote_turn_id` do pipeline tra |
| Hai đầu | `url`, `relayProtocol` không có trên remote candidate, và `address` của remote candidate có thể null. Biết đủ hai bên thì cần telemetry của cả hai đầu |
| Lý do restart | Thêm `restart_disconnected`, `restart_quality` vào `ice_trigger`. Không bắt buộc biết nguyên nhân nội bộ của ICE |
| Đổi cặp | `selectedCandidatePairChanges` giúp phát hiện lần đổi bị lỡ giữa hai lần poll. Bộ đếm cũng tăng khi đi từ không có cặp sang có cặp hoặc ngược lại, nên không phải lần tăng nào cũng là đổi đường. Sửa câu "không quan sát được" ở spec §18 mục 11 |

### 5.2. Số trung bình cấp cuộc gọi

VIA dùng số trung bình theo cuộc gọi, trong khi `call_stats_epoch` chỉ có phân vị và histogram. Ngưỡng của VIA (320 ms, 1,2%, 12 ms) cũng không tính được từ histogram hiện có, vì bucket vắt qua các ngưỡng này. Đề xuất thêm bộ đếm tích lũy:

| Cột | Nguồn W3C | Cho biết |
|---|---|---|
| `media_rtcp_rtt_total_s`, `media_rtcp_rtt_measurements` | `remote-inbound-rtp.totalRoundTripTime`, `roundTripTimeMeasurements` | RTT trung bình |
| `ice_stun_rtt_total_s`, `ice_stun_responses` | `candidate-pair.totalRoundTripTime`, `responsesReceived` của cặp đang chọn | RTT trung bình của STUN check |
| `packets_received_total`, `packets_lost_total` | `inbound-rtp.packetsReceived`, `packetsLost` | Tỷ lệ loss |
| `jitter_estimate_sum_ms`, `jitter_estimate_samples` | Cộng dồn các lần đọc `inbound-rtp.jitter` | Jitter trung bình. W3C chỉ có giá trị hiện tại, nên phải lấy mẫu |
| `stats_stream_ref` | Định danh stream của bộ đếm | Phát hiện đổi stream hoặc reset bộ đếm |

**Đọc tại mỗi lần đổi cặp.** Đọc chỉ ở cuối epoch sẽ trộn nhiều đường nếu đổi cặp hoặc restart trong epoch, nên không gắn được cho một cặp TURN. Vì vậy dòng `selected_pair_change` của `ice_event` ghi kèm bộ đếm của cặp vừa rời và của stream audio, và pipeline lấy hiệu giữa hai lần đọc. RTT của `candidate-pair` tính riêng theo cặp và không phụ thuộc media, nên hợp làm đầu vào ghép chặng. Đây là suy luận từ đặc tả, chưa đo.

### 5.3. `call_stats_epoch` và `call_stats_5s`

| Bảng | Nhóm | Xử lý |
|---|---|---|
| `call_stats_epoch` | Khóa, mốc, `first_media_*`, `audio_active_duration_s`, bộ đếm tích lũy | Giữ. `sequence_no` thành bắt buộc và vào khóa, vì checkpoint tạo nhiều dòng cùng epoch |
| `call_stats_epoch` | Histogram, phân vị, số cửa sổ đánh giá được, `derivation`, `quality_rule_version` | Tổng hợp ở client, phục vụ `PoorFraction` ở §13.2. Chỉ giữ nếu WebRTC core xác nhận chi phí trên web và mobile, nên đang nullable |
| `call_stats_5s` | Số đo theo cửa sổ, `packets_received`, `packets_lost`, `rtt_measurements_delta` | Giữ theo mẫu. `packets_received` thay cho `packets_expected` |
| `call_stats_5s` | `packets_expected`, `loss_pct`, `rtt_sample_valid`, `jitter_sample_valid`, `quality_rule_version`, `path_attribution_status`, `restart_gap` | Chuyển sang `clean_stats_columns` |

Quy tắc §6.3 chỉ giữ `call_stats_5s` khoảng 10% với cuộc gọi bình thường, nên số cấp cuộc gọi phải đến từ client. Đọc bộ đếm ở cuối epoch rẻ hơn tự tổng hợp theo cửa sổ. Việc này là code ở tầng app, không sửa WebRTC core, nhưng cần được xác nhận.

**Mẫu RTT:** cửa sổ RTT chỉ có mẫu mới khi `roundTripTimeMeasurements` tăng; không lặp RTT cũ. Reset counter hoặc đổi stream phải được biểu diễn, không suy diễn.

### 5.4. `network_epoch`

`network_epoch` là khóa bắt buộc và cần cho việc gắn nhóm mạng, nhưng chưa rõ web phát hiện đổi mạng bằng gì. Đề xuất: tăng khi client phát hiện đổi mạng; nền tảng không phát hiện được thì giữ 0 và báo ở `telemetry_coverage`, không được hiểu là không đổi mạng.

### 5.5. Thời gian

- Duration chỉ hợp lệ khi trừ trên cùng một đồng hồ đã biết; ưu tiên monotonic trên cùng endpoint và process. App khởi động lại có thể reset đồng hồ, nên `device_id` chưa đủ. Bản này chưa cần `clock_domain` theo từng dòng, nhưng lớp đồng hồ phải biết được qua metadata.
- §8.1 trộn lệch đồng hồ với độ trễ signaling; không dùng để khẳng định duration ngắn.
- Không có hook thấp tầng thì không có `checks_start_ts`. Mốc thay thế là dòng `ice_event` với `ice_state = checking`, có tên và KPI proxy riêng.

---

## 6. TURN metrics

### 6.1. `turn_health_1m`

| Xử lý | Cột |
|---|---|
| Giữ | `turn_id`, `minute_ts`, `active_allocations`, `cpu_pct`, `bandwidth_mbps`, `alloc_attempts`, `alloc_failures`, `alloc_failures_by_code`, `last_observed_ts`, `sample_count`, `source`, `ingest_delay_ms`, `observation_state` |
| Thêm | `liveness_ok`, `liveness_method`: exporter có trả lời không, hoặc health checker thử Allocate có được không |
| Chuyển sang feature health và load | `health_status`, `health_score`, `health_rule_version`, `assigned_by`, `utilization_pct` |

- `health_status` đang là cột duy nhất nói TURN còn sống hay không. Tách đi thì raw cần một tín hiệu sống quan sát trực tiếp, nên mới thêm `liveness_ok`.
- `alloc_attempts`, `alloc_failures`, `bandwidth_mbps` được null và có `source`. Không lấy `turn_traffic_*`, `turn_total_traffic_*` làm bandwidth tức thời, cũng không lấy delta của gauge allocation làm `alloc_attempts`. Bản coturn công ty đang chạy cần đối chiếu riêng.
- `bandwidth_mbps` là tín hiệu tải, không phải chi phí.

### 6.2. `turn_allocation`

Không sửa SDK thì chỉ còn nguồn log của TURN.

| Xử lý | Cột |
|---|---|
| Giữ | `turn_id`, `transport`, `turn_server_ip`, `relayed_ip`, `response_ts`, `allocation_result`, `error_code`, `source`, `released_ts`, `release_reason` |
| Thêm | `server_session_id`, vì `allocation_id` do app tạo không có trong log; `credential_ref`, định danh theo cuộc gọi trích từ username, không phải secret |
| Chuyển sang pipeline | `allocation_id`, `call_id`, `decision_id`, `side`, `device_id`, `match_method` |
| Bỏ | `request_ts`, `alloc_ms`, `attempt_seq`, `is_preallocation`, `turn_url`, `rank`, `ice_generation` |

- `allocation_result` gồm `success`, `failure`, `unknown`. Quan sát chưa biết kết quả không bị ép thành thành công hay thất bại. Sửa I10 theo mục 13.
- 401 rồi thành công là một allocation thành công. 300 là `redirect_300`. 486 là quota theo username, không nói lên sức khỏe server; 508 là thiếu capacity.
- `release_reason` chỉ ghi điều log của TURN cho biết. Máy chủ không biết `call_end` hay `other_device_answered`.
- Nối log với cuộc gọi cần credential theo cuộc gọi. Nhiều cuộc gọi dùng chung username thì bảng chỉ dùng được cho thống kê theo TURN. Không nối chắc chắn được thì `match_method = ambiguous`.

---

## 7. Probe giữa các TURN

Probe là đầu vào của feature backbone. VIA cũng dùng số đo giữa các relay để ước lượng đường transit (mục 3.2 của VIA), chỉ khác là Skype đã có số đo này trên mạng riêng, còn ở đây phải tự xây. Vì vậy đây là nguồn có rủi ro khả thi lớn nhất, và ở mức có điều kiện.

`path_leg_measurement` của v0.4.0 đang gộp ba thứ khác nhau:

| Phần trong bảng | Xử lý | Lý do |
|---|---|---|
| `leg_type = turn_turn`, `method = mesh_probe` | Giữ, đổi thành `turn_probe` | Đúng là probe trong vòng đời |
| `leg_type = user_turn`, `method = derived`, `value_kind = estimated` | Chuyển sang Feature Engineering | Số suy ra, không phải quan sát. Không chia đều loss, jitter đầu cuối cho từng chặng |
| `method = inband`, `idle_probe` | Hoãn | Giả định A2 chưa xác minh được, và không có API chuẩn nào đo được |

**Cột của `turn_probe`:** `src_turn_id`, `dst_turn_id`, `src_ip`, `dst_ip`, `window_start_ts`, `window_end_ts`, `method_version`, `protocol`, `target_port`, `measurement_kind`, `measurement_point`, `value_ms`, `value_ms_p95`, `loss_pct`, `jitter_ms`, `n_samples`, `clock_sync_err_ms`, `observation_state`, `missing_reason`.

Khóa hiện tại của `path_leg_measurement` chứa `call_id`, `attempt_seq`, `network_epoch`, `side` ở dạng nullable, là các cột vô nghĩa với probe. Tách ra thì hết vấn đề này.

**Khả thi cần xác nhận:**

- Đo RTT thay vì một chiều, vì một chiều cần đồng bộ đồng hồ.
- Probe nên đi đúng IP relay và cùng giao thức với media, nếu không có thể khác đường thật.
- Số cặp tăng theo bình phương số TURN, nên chu kỳ đo phụ thuộc kích thước danh mục.
- Coturn không tự đo việc này, nên cần một tác tử đo riêng, chạy trên hoặc cạnh máy TURN.
- Không probe từ một TURN đến chính nó (I30).

---

## 8. Danh mục TURN và danh tính

**`dim_turn`:** giữ định danh, vị trí, `lat`, `lon`, `host_isp`, `host_asn`, `capacity_alloc`, `transports`, `status`, hiệu lực, `failure_domain`. `failure_domain` nhiều chiều có nguồn hạ tầng, tuyến cáp để null nếu chưa có chứng cứ. Hoãn `hairpin_*`, `turn_pool_id`, `turn_instance_id`. Geo Baseline cần tọa độ phía người dùng; raw đã đủ với `city`, còn bảng tra thành phố sang tọa độ thuộc Feature Engineering.

**`dim_turn_endpoint`:** bỏ ràng buộc "một IP chỉ thuộc một `turn_id`" ở §3.4, và sửa câu về anycast ở §0.3 theo hướng "có thể phát hiện và biểu diễn danh tính chưa xác định".

1. **Khóa bản ghi:** có `mapping_id`; IP không còn là khóa duy nhất. Vẫn chặn bản ghi trùng và khoảng hiệu lực chồng lấn không có chủ đích của cùng một quan hệ.
2. **Lookup:** tra theo thời điểm quan sát và vai trò `listen`, `relay`, `both` phù hợp, lấy tập `turn_id` phân biệt. Nhiều dòng của cùng một máy vẫn là một máy. Phần này do pipeline làm (mục 11.1).

**`dim_country_area`:** bảng tra mới cho cấp khu vực; `S06_intl_same_area` đang dùng "area" chưa định nghĩa.

---

## 9. Decision Log

Decision Log được đặc tả trọn ở một chỗ, gồm cả dự đoán. Phần dự đoán không có vấn đề khả thi khi thu thập, nhưng phải được ghi lúc quyết định.

Tách ba đối tượng. Không gộp chúng thành một `chosen_rank`, vì hai danh sách tạo tổ hợp chéo và cặp thực tế có thể nằm ngoài top-k.

| Đối tượng | Nơi ghi | Field |
|---|---|---|
| **Cặp được cân nhắc** | `selector_decision_pair` | `decision_id`, TURN và transport mỗi bên, `metric`, `unit`, `est_value`, `interval_low`, `interval_high`, `interval_kind`, `interval_level`, `in_topk`, `is_lead`, `estimate_source`, `estimator_version`, `input_snapshot_id`, `gate_*` |
| **Hành động, cấp quyết định** | `selector_decision` | `parent_decision_id`, `policy_version`, `decision_source`, `selection_method`, `requested_max_list_size`, `returned_list_size`, `topk_pair_count`, `topk_capped`, `action_propensity`, `propensity_method`, `eligible_action_set`, `confidence*` |
| **Hành động, từng mục danh sách** | `selector_decision.entries` | `entry_id`, `rank`, `turn_id`, `config_ref`, `normalized_config_key`, `client_turn_transport`, `roles[]`, `score`, `score_components`, `reason_codes` |
| **Cấu hình client đã áp dụng** | `client_applied_config` | Xem mục 4 |

**Các quy tắc đi kèm:**

- **Khi chưa có Selector:** BE vẫn ghi `selector_decision` với `decision_source = static_config`, `policy_version = static@1`, `selection_method = static`, `propensity_method = not_estimated`, và không có dòng `selector_decision_pair`. `decision_id` luôn có. `static_fallback` giữ nghĩa là có Selector nhưng lỗi hoặc timeout.
- **Cột snapshot:** `feature_snapshot_id` được null, vì Geo Baseline không dùng feature. `health_snapshot_id` được null khi `static_config`, `static_fallback` hoặc `fallback_type = health_missing`.
- **Dòng cặp:** ghi các cặp trong top-k và hành động đã chọn, kể cả `in_topk = false`. Chưa biết Callee thì được phép trống. Cặp thực tế khác các cặp đã ghi thì Labeled Data ghi là không có dự đoán, không suy ra. `transport_*` nằm trong khóa nên bắt buộc.
- **Tập hành động đủ điều kiện:** lưu thành object hoặc snapshot bất biến, định vị được. Hash chỉ để kiểm tra nội dung, không tự dựng lại được hành động.
- **Độ dài danh sách:** thay `len = min(k, …)` của I3 bằng `returned_list_size ≤ requested_max_list_size`, rank liên tục từ 1. Trả bao nhiêu mục là quy tắc của policy. Thiếu lựa chọn hợp lệ thì báo `insufficient_candidates`, không nhân bản server. `k` đếm mục còn top-k đếm cặp, nên không dùng chung tên.
- **Khóa danh sách:** khóa bản ghi theo decision, endpoint phía gọi và `entry_id`. Duplicate được định nghĩa theo cấu hình chuẩn hóa. Quy tắc policy cấm lặp server tách khỏi khóa dữ liệu, vì hai URL khác port trên cùng máy và transport vẫn có thể hợp lệ.
- **Propensity theo hành động:**
  - Không nhân `p_caller × p_callee` (§8.4) khi hai bên được chọn chung.
  - Xác suất cặp ICE thực dùng không phải xác suất hành động.
  - Nếu danh sách suy ra hoàn toàn tất định từ cặp dẫn đầu thì xác suất cặp đại diện được; nếu backup, padding, transport hay thứ tự còn ngẫu nhiên thì phải ghi xác suất chung.
  - Ước lượng Monte Carlo phải ghi số mẫu và phương pháp. Chưa ước lượng được thì để null, không điền `1/k`.
- **Cấu hình đang dùng:** decision mới không tự đổi cấu hình client đang dùng. `ice_attempt` trỏ `caller_decision_id`, `callee_decision_id` theo cấu hình đã áp dụng. I4 so với danh sách đã áp dụng.

---

## 10. Đầu vào của Outcome Log và khóa nối

### 10.1. Tách theo nguồn

Outcome Log là view sau pipeline (`outcome_log`, mục 11.1). Contract chỉ bảo đảm đầu vào của view này.

| Nguồn | Bảng | Cột |
|---|---|---|
| BE | `call_outcome`, một dòng mỗi cuộc gọi | `ring_ts`, `answer_received_at_be`, `answered`, `answered_device_id`, `end_ts`, `end_signal`, `end_signal_side`, `caller_ctx_final`, `callee_ctx_final`, `converted_to_group`, `converted_ts` |
| Client | `client_call_report`, một dòng mỗi đầu | `answer_clicked_at_client`, `answer_observed_at_peer`, `client_end_reason`, `stats_status`, `stats_sampling_prob`, `stats_sampling_reason`, `sampling_rule_version` |

- **`end_reason` chưa phải raw.** `dropped_turn` và `dropped_network` là suy luận, BE không quan sát trực tiếp. BE chỉ ghi tín hiệu kết thúc (`end_signal`), client báo lý do nếu có (`client_end_reason`), pipeline phân loại sau.
- **Bảng riêng cho client,** vì hai nguồn không ghi chung một dòng, và `stats_status` là của từng đầu.
- **Hai mốc ở client cho TTFM.** `first_media_received_ts` theo đồng hồ client, còn `answer_received_at_be` theo đồng hồ BE. Với `answer_clicked_at_client` và `answer_observed_at_peer`, TTFM mỗi bên trừ được trên cùng một đồng hồ. Không lấy max timestamp hai máy trừ timestamp BE mà không đánh giá sai số.

### 10.2. Khóa nối contract phải bảo đảm

Labeled Data và feature chỉ dựng được khi raw có đủ các khóa này.

| Khóa | Dùng để nối | Khả thi |
|---|---|---|
| `call_id` | Mọi bảng | BE sinh, client phải gắn vào telemetry |
| `decision_id` | Decision Log với cấu hình đã cấp và lần thử ICE | BE sinh, kể cả khi chưa có Selector |
| `side`, `device_id` | Hai đầu của cuộc gọi | Có |
| `pc_id`, `ice_generation` | Cấu hình, sự kiện ICE, số liệu theo lần restart | Client phải gửi; app làm được |
| `local_turn_url` | Cặp thực tế với mục trong danh sách | Theo đặc tả có; lab chưa đọc |
| `relayed_ip_*` và thời điểm | Cặp thực tế với TURN, qua `dim_turn_endpoint` | Theo đặc tả có; lab chưa đọc trực tiếp |
| `server_session_id`, `credential_ref` | Log TURN với cuộc gọi | Chưa xác nhận; cần credential theo cuộc gọi |

---

## 11. Các lớp sau thu thập

Phần này nằm ở file đi kèm. Mình giữ nguyên nghĩa của các đề xuất, chỉ chuyển chỗ và sửa chỗ buộc phải đổi theo ranh giới mới.

### 11.1. Pipeline làm sạch

**`outcome_log`:** nối `call_outcome`, `client_call_report`, `ice_attempt` và `call_stats_epoch`.

- `ice_connected`, `dtls_connected`, `media_connected` có ba trạng thái `true`, `false`, `unknown`. `answered`, `dropped` được phép null. Hiện §5.9 và I23 không nhất quán: ICE nối được mà media không tới thì không có nhánh đúng.
- `media_connected = false` nghĩa là **đã xác nhận không đạt tiêu chí media trong khoảng đánh giá**, không phải "chưa nhận telemetry media". `media_connected_rule_version` chỉ rõ một hay cả hai endpoint, chiều và loại media cần thiết, mốc đánh giá. Bản này chưa chọn timeout.
- `first_media_received_ts` là timestamp nullable, kèm tình trạng quan sát và định nghĩa rõ: gói RTP đầu, frame giải mã đầu hay âm thanh phát ra.
- Thêm `media_setup_failed` vào `end_reason`, để phân biệt với `ice_failed`.
- Phân tích bắt đầu từ `call_session` rồi left join outcome. Không có dòng outcome thì cuộc gọi vẫn ở trong cohort. `outcome_status` gồm `complete`, `partial`, `missing`, và không trực tiếp quyết định nhãn poor.
- Pipeline có thể tạo placeholder sau thời hạn chờ, với điều kiện: không tự điền `false`; có quy tắc cutoff, dữ liệu đến muộn, version; dòng cuối là duy nhất trong view hiện hành; có nguồn gốc cho placeholder và event thật.
- Các chỗ đang dùng `connected` phải cập nhật đồng bộ: I6, I7, I23, §13.2, `pnr`, `pcr_answered`, `quality_assessment_status` ở §8.4, và các phần tương ứng trong spec.

**Tra danh tính TURN:**

1. **Kết quả:** `turn_identity_status` gồm `identified`, `ambiguous`, `unmapped`, `unknown`. Không có kết quả không mang cùng nghĩa với nhiều kết quả. `actual_turn_id` chỉ có giá trị khi `identified`.
2. **Nguồn phân giải:** không dùng TURN do Selector yêu cầu để phá hòa, vì đó là ý định, không phải chứng cứ máy thực. Nguồn server hoặc endpoint độc lập có thể phân giải nếu ghi rõ nguồn gốc.
3. **Thiếu danh tính:** cuộc gọi vẫn trong KPI tổng; thống kê theo máy không được gán bừa.
4. **I19:** có ba kết quả `match`, `mismatch`, `not_evaluable`. Chưa xác định được máy thì không kết luận `match` hay `mismatch`.

**`path_type`:** mỗi đầu xác định loại candidate bằng **local candidate của chính đầu đó**. Remote candidate chỉ là bằng chứng phụ, và remote `prflx` không tự nói lên loại thật: theo [RFC 8445 §7.3.1.3](https://www.rfc-editor.org/rfc/rfc8445.html#section-7.3.1.3), kiểm tra tới từ địa chỉ chưa biết tạo ra remote `prflx`, và đó có thể chính là relay của đầu kia. Phần này suy từ đặc tả, chưa đo.

| Bằng chứng selected pair | `path_type` |
|---|---|
| Hai candidate là relay, hai máy TURN được xác định và trùng nhau | `relay_same` |
| Hai candidate là relay, hai máy TURN được xác định và khác nhau | `relay_relay` |
| Hai candidate là relay, chưa đủ biết cùng hay khác máy | `relay_unresolved` (mới) |
| Thiếu loại candidate để xác định đường | `unknown` |

- Sửa §2: bỏ nhánh "ngược lại `relay_relay`", vì ID null đang rơi vào nhánh này và I8 bỏ qua kiểm tra.
- Không suy `relay_unresolved` chỉ từ cấu hình `ice_transport_policy = relay`.
- `null` dành cho không áp dụng hoặc chưa có selected path, không đồng nghĩa `unknown`.

**I18:** chỉ còn áp dụng cho giả lập, vì cuộc gọi thật chạy `all`. Kiểm tra theo `applied_ice_transport_policy` của đúng attempt và generation:

| Bằng chứng | Kết quả |
|---|---|
| Local candidate quan sát được không phải relay; hoặc remote candidate đã signal là `host`, `srflx` khi đầu kia cũng áp dụng relay-only | **FAIL**, kể cả khi thiếu phía còn lại khiến `path_type = unknown` |
| Đủ bằng chứng hai candidate là relay | Đạt điều kiện loại candidate; danh tính chưa rõ được phép là `relay_unresolved` |
| Chưa đủ bằng chứng, chưa thấy mâu thuẫn; gồm remote `prflx` khi chưa có telemetry đầu kia | `not_evaluable`, ghi vào coverage; không ghi là đã đạt |

**Gán chất lượng theo đường:** `path_attribution_status` (`single_path`, `mixed`, `unknown`) do pipeline tính.

1. SDK không hỗ trợ thì `unknown`, không mặc định `single_path`.
2. Bộ đếm tăng mà không có timeline thì biết có đổi, không biết đường trung gian; không tạo path epoch giả.
3. Epoch `mixed` hoặc `unknown` vẫn vào KPI toàn cuộc gọi, nhưng không gán chất lượng cho TURN đầu hay cuối.
4. Feature theo đường chỉ dùng phần `single_path`, và báo coverage bị loại. Không dùng cờ này để loại cuộc gọi xấu khỏi cohort.
5. Không dùng cùng quy tắc để xóa số liệu tải và allocation đo được ở hạ tầng.

### 11.2. Feature Engineering

Feature không thuộc contract thu thập, nhưng raw phải đủ để tính được.

| Feature | Bảng | Đầu vào raw | Loại số |
|---|---|---|---|
| Backbone | `feat_turn_turn` | `turn_probe` | `measured`. Thiếu probe thì chỉ `estimated` được khi có mẫu dùng chung TURN; không có mẫu đó thì không tách được khỏi chặng |
| Chặng | `feat_leg_stats` | Kết quả đầu cuối của cặp đã dùng, danh tính hai TURN, nhóm mạng hai bên, và backbone | Luôn `estimated`. Đây là tham số của mô hình để dự đoán đường, không phải số đo |
| Health, load | `health_snapshot`, `feat_turn_health` | `turn_health_1m`, `turn_allocation` | Do quy tắc có version gán |

**Cách suy ra chặng,** theo mục 4.4 của VIA: một đường gồm đoạn từ nhóm mạng đến TURN của mỗi bên, cộng chặng giữa khi hai TURN khác nhau. Đường chưa dùng có thể dự đoán bằng cộng trừ các đường đã thấy, như Hình 11 của VIA, không cần biết riêng từng chặng.

**Mình thử trên dữ liệu tổng hợp** (cộng tính theo cấu trúc, nên chỉ để kiểm tra logic, không nói lên lợi ích thật):

- Thước đo chính nên là độ phủ đường chưa dùng, sai số và mức chênh so với cặp tốt nhất. Có trường hợp tách được 0 trên 64 chặng mà vẫn dự đoán được mọi đường hai relay chưa dùng.
- Probe giúp rõ khi dữ liệu thưa, hoặc chưa có mẫu dùng chung TURN. Khi đã đủ mẫu, probe thêm rất ít, và probe lệch khoảng 20% theo từng cặp còn tệ hơn không có probe. Vì vậy nên coi probe là số đo có sai số, không trừ thẳng khỏi đầu cuối.
- Probe không thay được khám phá: chỉ chọn TURN gần nhất thì có probe vẫn không dự đoán được đường chưa dùng. Điều này có hệ quả với cách thu dữ liệu (mục 14).

**Các việc của đặc tả Feature Engineering:**

- Đổi đầu vào của `feat_leg_stats` sang kết quả đầu cuối và backbone, thêm `value_kind`.
- RTT làm trước. `log(1 − loss)` cộng được khi các chặng độc lập, jitter cộng xấp xỉ. MSR-TR-2016-57 cho thấy mô hình giúp loss khá ít, nên loss và jitter ưu tiên lịch sử trực tiếp.
- Đường nhiều mẫu dùng lịch sử trực tiếp, đường ít mẫu mới ghép chặng.
- `n_eff = Σw` (§9.0): ghi rõ đây là khối lượng mẫu đã decay, không phải cỡ mẫu độc lập.
- Tỷ lệ kết nối theo segment × TURN là thống kê có điều kiện của cuộc gọi có TURN đó, không phải nhãn chặng. CST đầu cuối không gán hết cho từng TURN.
- Nếu cho thuật toán đọc `clean/`, dữ liệu phải as-of theo cả event time và ingest time.
- Câu còn mở của `feat_path_history`: cặp là cặp thực tế hay cặp dẫn đầu; `rtt_p50` và thống kê log thuộc đại lượng RTT nào; có cần tách theo transport không.

**Health:**

- `health_status` thêm `unknown`, đúng với quy ước enum ở §1. Có `last_observed_ts`, `source`, `health_rule_version`, và lý do `health_stale` trong `filtered_out`. Snapshot mới không làm số đo cũ trở thành mới. Thiếu hoặc cũ thì không tự điền `healthy`.
- `health_status` phải ghi được nơi gán và phiên bản luật; không để hai nơi tính khác nhau dưới cùng một field.
- `health_status` mô tả sức khỏe server. Khả năng tới TURN theo mạng và transport, cùng chất lượng đường qua TURN, là các khái niệm khác; `degraded` chỉ được gán khi có nguồn.

**Số ước lượng:** không ghi đè dữ liệu thô, và không gộp phân phối với số đo trực tiếp. Giá trị bị gate loại có thể vẫn được lưu để truy vết, nhưng không được hiểu là đã chấp nhận để sử dụng.

### 11.3. Labeled Data

Labeled Data chỉ nối Decision Log với Outcome Log rồi gắn nhãn, không tạo thêm dự đoán. Để tính KPI ITT trong simulator, chốt `fact_call` có một dòng trên mỗi `call_id` thuộc cohort. File đi kèm vẫn chưa định nghĩa đủ cột; đánh giá dự đoán theo cặp cần bảng hoặc view riêng, vì còn hai câu:

1. Cuộc gọi thiết lập thất bại không có cặp thực tế, vậy nhãn gắn vào cặp dẫn đầu thế nào?
2. Dự đoán và kết quả có cùng đại lượng không? Ví dụ RTT dự đoán là `media_rtcp_rtt` hay `ice_stun_rtt`.

Các cột từ `fact_call` như `pcr_group`, `poor_category`, `action_propensity`, `propensity_decision_id`, `rank_used_*`, `lead_pair_matched` sẽ chuyển sang đặc tả này. Hai bên khác decision thì `action_propensity` để null. Các cột KPI theo §8.4 cũng cần được liệt kê khi viết đặc tả.

### 11.4. KPI

**Cohort:** `pcr_itt` đang định nghĩa cohort theo `arm` và contract bắt buộc `arm` trên sim, nên phải viết lại: trong giả lập, policy lấy từ `run_manifest.policy_version`. Phạm vi dữ liệu theo mục 3.4.

**Hai cận:** hiện outcome bị mất không rơi vào cận nào, nên được tính như không poor ở cả `pcr_itt_low` và `pcr_itt_high`. Đề xuất trên cohort đã chốt:

```text
K: đã có đủ bằng chứng để kết luận poor.
G: đã có đủ bằng chứng để kết luận không poor.
U: còn lại, chưa kết luận được poor hay không poor.

U_quality: phần của U đã xác định điều kiện outcome cần thiết,
           nhưng thiếu bằng chứng chất lượng để phân loại.
U_outcome: U \ U_quality.

N = |K| + |G| + |U|; các tập rời nhau.

pcr_itt_low          = |K| / N
pcr_itt_high         = (|K| + |U|) / N
unclassifiable_rate  = |U_quality| / N
outcome_unknown_rate = |U_outcome| / N
undetermined_rate    = |U| / N = unclassifiable_rate + outcome_unknown_rate
```

| Bước | Điều kiện | Nhóm |
|---|---|---|
| 1 | Có đủ bằng chứng cho `setup_fail`, `drop` hoặc `quality_poor` trên cuộc gọi đã có media | `K` |
| 2 | Đủ bằng chứng không poor: `answered = false`; hoặc `app_crash` khi media chưa nối và không có sự kiện lỗi thiết lập đã quan sát; hoặc media đã nối, không rớt, `quality_ok` | `G` |
| 3 | `answered = true`, `media_connected = true`, `dropped = false`, `quality_unknown` | `U_quality` |
| 4 | Còn lại | `U_outcome` |

- Cuộc gọi đã biết poor không trở thành unknown chỉ vì thiếu trường khác.
- Thiếu cả outcome lẫn quality thuộc `U_outcome`, không đếm hai lần.
- Mọi tỷ lệ dùng cùng cohort, cutoff và đơn vị. `N = 0` thì metric không xác định, không điền 0.
- Công thức `pcr_itt_high − pcr_itt_low = unclassifiable_rate` ở §13.2 đổi thành `= undetermined_rate`, kéo theo test số 17 ở spec §14. Tên `unclassifiable_rate` giữ lại nhưng điều kiện chuyển từ `connected` sang `media_connected`, nên đây là thay đổi nghĩa.
- `setup_fail` đúng khi `answered = true`, `media_connected = false`, và có một trong hai bằng chứng: `setup_failure_observed = true`, hoặc `end_reason` đã biết và khác `app_crash`. `end_reason = unknown` không phải bằng chứng "không crash".

**TTFM:** `ttfm_post_answer_p95` lấy `max` hai bên so với `answer_ts`. Đề xuất viết lại theo từng bên, trên đồng hồ của chính bên đó: Callee dùng `answer_clicked_at_client`, Caller dùng `answer_observed_at_peer`.

**Phục hồi:** tạm đo ở mức ICE từ `ice_event`, nên `detected_to_media_recovery_ms` đổi thành `detected_to_ice_recovery_ms`. Chỉ báo `fault_to_recovery_ms` khi biết mốc fault. `network_epoch`, `ice_generation`, `path_epoch_id` là ba khái niệm riêng.

**BE và outcome:** §0.2 và spec A12 suy từ "BE không chở media" thành "BE không ảnh hưởng `pcr_itt`". Đúng là BE không cộng vào RTT, loss, jitter của một đường cố định, nhưng signaling có thể ảnh hưởng thiết lập và cuộc đua candidate. Đề nghị sửa câu này.

**Ngưỡng:** ngưỡng mạng kém của VIA (320 ms, 1,2%, 12 ms) khác ngưỡng ở §13.2 (300 ms, 3%, 30 ms), nên báo cáo phải nêu rõ đang dùng ngưỡng nào.

**Metadata của metric:** `metric_definition_version`, `detector_version` nếu có kết quả detector, nguồn dữ liệu và phạm vi nền tảng, đơn vị, mẫu số, coverage, `active` hoặc `reporting_only`. Trạng thái cấu hình này khác với trạng thái đo được của từng lần tính (`assessed`, `unknown`, `not_applicable`). `active` không biến dữ liệu thiếu thành đủ, và metric unknown không được coi là đạt.

### 11.5. Giả lập

- Giả lập phải sinh đúng raw của contract. Truth không được xuất thành số đo quan sát khi không có capability.
- `turn_probe` có công tắc bật tắt theo profile, và nên có cả sai số lẫn độ lệch so với đường media.
- `scenario_tag` chuyển sang `sim_call_tag`, vì đây không phải dữ liệu thu được từ cuộc gọi thật.
- `run_manifest` thêm `observation_profile`, `ice_model_version`.
- Spec §6.4 đang mô tả rank × rank, nên sẽ không còn khớp với contract mới.

### 11.6. API Selector

- **SelectRequest:** thay `k` bằng `requested_max_list_size_caller`, `requested_max_list_size_callee`. Thêm `parent_decision_id`, `requested_policy_version`, `idempotency_key`, lý do cho `exclude_turns`. `exploration_epsilon` được null, vì không phải policy nào cũng có ε. Hoãn `locked_side`, `locked_list_hash`.
- **SelectResponse:** thêm `pairs`, `lead_pair`, `topk_pair_count`, `topk_capped`, `selection_method`, `action_propensity`, `propensity_method`, `propensity_n_samples`, `eligible_action_set`, `confidence_evidence`, `fallback_type`, `expires_at`. BE ghi Decision Log từ response, nên response phải chở đủ các trường này.

---

## 12. Phần hoãn và phần bỏ

**Hoãn, có thể mở lại:**

| Phần | Lý do | Mở lại khi |
|---|---|---|
| `candidate_observation` | Chưa dùng thời điểm nhận candidate và không sửa SDK. Trong lab, thời điểm nhận candidate tương quan rất cao với độ trễ, nhưng chưa đo trên mạng thật | Feature chặng ước lượng không đủ tốt; đây là nguồn trực tiếp duy nhất theo từng TURN |
| `ice_candidate_pair` | `current_rtt_ms` gần như luôn trống với cặp không được chọn; danh sách 8 mục tạo đến 64 dòng mỗi attempt | Cần chẩn đoán sâu |
| Chuỗi trạng thái RTP theo cửa sổ | Nhu cầu đến từ việc phát hiện gián đoạn, không có trong đề bài hay VIA. Giới hạn: gián đoạn tự phục hồi không thấy được trong dữ liệu | Có yêu cầu về gián đoạn; nội dung giữ ở `x-deferred-rules` của file đi kèm |
| Cột thí nghiệm, `decision_mode`, `shadow_req_count`, `arm`, I15 | Tạm thời chưa thử nghiệm trên traffic thật | Có thử nghiệm |
| `caller_signaling_rtt_ms`, `callee_signaling_rtt_ms`, `n_devices_rung` | Chưa mô hình hóa đổ chuông và tín hiệu | Mở lại cuộc đua candidate |
| `locked_side`, `locked_list_hash` | Selector biết Callee ngay từ đầu | Cần giữ TURN bên kia khi đổi mạng |
| `hairpin_*`, `turn_pool_id`, `turn_instance_id`, `endpoint_id` | Chưa cần khi danh mục tự xây | Có hạ tầng thật |
| `feat_callee_prior`, `feat_turn_alloc_latency`, `feat_estimated_user_turn_rtt` | Không còn đầu vào hoặc không còn nhu cầu | Mở lại phần tương ứng |
| Mốc media trở lại sau restart | Tạm đo phục hồi ở mức ICE | Cần đo phục hồi media |

**Bỏ vì không còn đúng:**

| Phần dư | Vì sao | Xử lý |
|---|---|---|
| `chosen_rank` | Selector đặt cặp dẫn đầu lên đầu, nên luôn bằng 1 | Thay bằng `is_lead` |
| `propensity` trên Candidate, `joint_propensity` | Sai đơn vị | Chuyển sang `action_propensity` |
| `ice_trigger = fallback`, fallback theo rank | ICE tự đổi cặp trong cùng attempt, sau đó là restart | Bỏ; chỉ thêm lại nếu có client tuần tự, với version riêng |
| `k` mặc định 4 | Baseline cần 8, thuật toán cải tiến có số mục thay đổi | Thay bằng các field ở mục 9 |
| `est_path_ms`, `est_leg_ms` trên Candidate | Không biết ghép với TURN nào của bên kia | Chuyển sang bảng cặp |
| `confidence` dạng số, bắt buộc | Mình ưu tiên căn cứ và phân mức | Cho null; giữ `confidence_level`, thêm số mẫu làm căn cứ |
| Giữ rank 1 và 2, giải phóng rank 3 và 4 (spec §5.1), `kept_for_failover` | libwebrtc tự cắt rồi hủy cặp thừa; client web không điều khiển được từng allocation | Bỏ, trừ khi SDK thực tế làm được |
| `refined` | Một request trả được hai danh sách | Bỏ |
| `blind_cost_ms` | Không còn gọi mù | Bỏ |
| Các cột client cần hook thấp tầng, như `checks_start_ts`, `alloc_ms` | Không sửa SDK | Bỏ |

---

## 13. Bất biến và ví dụ dữ liệu

### 13.1. Bất biến

Danh sách đầy đủ nằm ở `x-invariants` trong hai file YAML.

| Nơi kiểm tra | Bất biến |
|---|---|
| Raw | I1, I2, I6 (theo `end_signal`), I10 (phần raw), I11, I17, I22, I29, I30 (mới) |
| Decision Log | I3, I4, I14, I25, I26, I31 (mới) |
| Pipeline làm sạch | I5, I6, I7, I23, I24 (trên `outcome_log`), I8, I19, I20 |
| Feature Engineering | I12, I13 |
| Labeled Data và Evaluation | I16, I21, I28 |
| Chỉ áp dụng cho giả lập | I18 |
| Hoãn | I9, I15, I27 |

**Các bất biến đổi nghĩa so với v0.4.0:**

| ID | v0.4.0 | Đề xuất |
|---|---|---|
| I3 | `len(candidates) = min(k, …)`; không trùng `turn_id`; Σ propensity = 1 | `returned_list_size ≤ requested_max_list_size`; rank liên tục từ 1; không trùng theo cấu hình chuẩn hóa |
| I4 | So với `candidates` | So với danh sách đã áp dụng cùng bên |
| I6 | `answered = false ∧ connected = true` chỉ khi `pre_connect` | Trên raw theo `end_signal`; trên `outcome_log` dùng `ice_connected = true` |
| I7 | `dropped = true ⇒ answered ∧ connected` | `dropped = true ⇒ answered = true ∧ ice_connected ≠ false ∧ media_connected ≠ false` |
| I8 | `relay_same ⇔` hai `actual_turn_id` trùng | Chỉ khi hai máy `identified`; danh tính chưa rõ là `relay_unresolved` |
| I10 | `success = true ⇔ error_code = none` | `allocation_result = success ⇔ error_code = none`; `unknown` thì `error_code` null |
| I16 | KPI-grade gồm `turn_allocation`, `path_leg_measurement[epoch_summary]` | Hai bảng này không còn thuộc danh sách; `outcome_log` thay `call_outcome` |
| I18 | Chỉ dựa trên `path_type` | Theo bằng chứng và policy đã áp dụng, có `not_evaluable`; chỉ áp dụng cho giả lập |
| I19 | Lệch thì báo mismatch | `match`, `mismatch`, `not_evaluable` |
| I23 | `ice_failed ⇒ answered ∧ ¬connected` | `ice_failed ⇒ answered = true ∧ ice_connected = false`; `media_setup_failed ⇒ answered = true ∧ ice_connected = true ∧ media_connected = false`; `answered = true ∧ media_connected = false ⇒ end_reason ∈ {ice_failed, media_setup_failed, normal_hangup, app_crash, unknown}` |
| I24 | `dropped = true ⇔ end_reason ∈ {dropped_*}` | Áp dụng khi `end_reason` đã biết; `end_reason = unknown` thì `dropped` được null |

### 13.2. Ví dụ dữ liệu

| Tình huống | Bản ghi đúng |
|---|---|
| Chưa có Selector | `selector_decision` với `decision_source = static_config`, `policy_version = static@1`; không có dòng `selector_decision_pair` |
| Có Selector, thiếu Health | `decision_source = api`, `fallback_type = health_missing`, `health_snapshot_id = null` |
| Không có probe | Không có dòng `turn_probe`; phần thiếu nằm ở coverage; `feat_turn_turn` không có nhãn `measured` |
| Cuộc gọi đi P2P | Có `call_session`, `selector_decision`, `ice_event`, `call_outcome`; không giữ `call_stats_epoch` |
| Đã bắt máy, ICE thất bại, chưa từng có relay được chọn | Vẫn giữ `call_stats_epoch`, vì thuộc nhóm thất bại |
| Allocate nhận 401 rồi thành công | Một allocation `success` |
| Caller TCP, Callee UDP | Mỗi bên có `client_turn_transport` riêng; không lấy candidate protocol làm transport tới TURN |
| Lookup IP ra nhiều máy | `ambiguous`, `actual_turn_id = null`, `path_type = relay_unresolved`, I19 `not_evaluable` |
| Lookup IP không ra kết quả | `unmapped`, không ghi `ambiguous` |
| Đổi cặp không restart | `ice_generation` giữ nguyên; dòng `selected_pair_change` có bộ đếm; `path_attribution_status = mixed`, hoặc tính được theo từng đoạn |
| Web không phát hiện được đổi mạng | `network_epoch = 0`; coverage báo không hỗ trợ; không hiểu là không đổi mạng |
| BE thấy mất tín hiệu, không rõ lý do | `end_signal = signaling_lost`; `outcome_log.end_reason = unknown` nếu không có thêm bằng chứng |
| App crash hoặc mất upload | Cuộc gọi vẫn trong cohort; không có `client_call_report`; phần thiếu nằm ở coverage và `U` |
| Đã bắt máy, đã xác nhận không có media, `end_reason = unknown` | `U_outcome`, không phải `setup_fail` |
| RTT không có mẫu mới | Không lặp RTT cũ qua cửa sổ tiếp theo |
| Hành động chọn cặp khác cặp ICE thực tế | Propensity vẫn theo hành động |
| Health trễ | Selector chỉ thấy dữ liệu đã đến và đã publish; thiếu thì `unknown` hoặc `stale` |

---

## 14. Xác nhận nguồn thu

Việc xác nhận diễn ra trước khi đưa contract cho BE và WebRTC core thu thật. Chưa có câu trả lời thì field để nullable hoặc `unknown`, hoặc giới hạn capability.

| Thứ tự | Nguồn trả lời | Cần hiện vật hoặc câu trả lời | Nếu chưa có |
|---|---|---|---|
| 1 | Mentor | Khi thu thật, danh sách có được biến thiên không? Chỉ thu từ danh sách tĩnh hoặc Geo Baseline không khám phá thì không dự đoán được đường chưa dùng, dù có probe. Schema không phụ thuộc vào câu trả lời này, nhưng giá trị của dữ liệu thì có | Giả lập đúng cách thu dự kiến và báo giới hạn |
| 2 | Mentor | **Q4 và một mẫu log thật (spec §18.2):** công ty đo từng chặng thế nào; là đo trực tiếp, RTT probe, giá trị suy ra hay số đầu cuối đổi tên | Không có số đo chặng trực tiếp |
| 3 | BE | Một trace invite đến kết thúc; thời điểm gọi Selector; timeout, fallback; lấy ngữ cảnh Callee từ đâu khi Callee offline hoặc có nhiều thiết bị; BE quan sát được tín hiệu kết thúc nào; credential có theo cuộc gọi không | Chỉ ghi mốc BE thật sự quan sát; nối log TURN để thiếu |
| 4 | WebRTC core, web, mobile | Mẫu `getStats` của cuộc gọi thành công, thất bại, có restart. Chi phí đọc bộ đếm, tổng hợp histogram và gửi trên từng nền tảng. Web phát hiện đổi mạng bằng gì. `url`, `address`, `iceRole`, các bộ đếm RTP có đọc được không | Field nullable; capability là giả định |
| 5 | Hạ tầng TURN | Phiên bản, `/metrics`, log mẫu, sơ đồ IP, DNS, VIP, anycast, capacity, quota; nguồn CPU và băng thông | Dùng `unknown`; health thiếu thì `stale` hoặc `unknown` |
| 6 | Hạ tầng mạng | Đặt probe ở đâu, đo IP, port, protocol nào, chu kỳ bao nhiêu | Không có `turn_probe`; backbone chỉ là số ước lượng |

---

## 15. Version, ánh xạ khái niệm và schema

### 15.1. Version

Đề xuất v0.5.0 có ghi rõ thay đổi phá vỡ tương thích. Theo §16, đổi nghĩa thuộc loại MAJOR; changelog v0.4.0 có tiền lệ giữ số phụ khi chưa có dữ liệu production, nhưng không nên gọi các thay đổi này là "chỉ thêm nullable". Cập nhật đồng thời contract, các phần liên quan của spec, ERD và sổ giả định, theo quy trình §16.

### 15.2. Ánh xạ khái niệm

Đây không phải phép chuyển cơ học; không suy được thì để thiếu.

| v0.4.0 | v0.5.0 |
|---|---|
| `chosen_rank` | `is_lead` trong `selector_decision_pair` |
| `candidates` | `entries` |
| `candidates[].propensity`, `joint_propensity` | `action_propensity`, `propensity_method` |
| `k` | `requested_max_list_size`, `returned_list_size`, `topk_pair_count` |
| `connected` | `outcome_log`: `ice_connected`, `media_connected`, `outcome_status` |
| `end_reason` trên `call_outcome` | `end_signal`, `client_end_reason`; `outcome_log.end_reason` |
| `success` | `allocation_result` |
| `ice_attempt.transport` | `client_turn_transport_caller`, `client_turn_transport_callee` |
| `checks_start_ts` khi không có hook | `ice_event` với `ice_state = checking` |
| `answer_ts` | `answer_received_at_be` |
| `ice_trigger = fallback` | Bỏ |
| `path_leg_measurement` với `mesh_probe` | `turn_probe` |
| `turn_health_1m.health_status` | `liveness_ok`; `health_snapshot.health_status` |
| `stats_status` trên `call_outcome` | `client_call_report.stats_status` |

**Hai ví dụ không chuyển được cơ học:**

- `connected = true` cũ chỉ chứng minh ICE theo định nghĩa cũ, không tự chứng minh `media_connected = true`.
- Propensity từng bên không tự chuyển thành xác suất của hành động nếu không biết cơ chế chọn; dữ liệu cũ có thể phải để `action_propensity = null`.

### 15.3. Schema kèm theo và các chi tiết cần góp ý

File contract có 18 bảng, trong đó 2 bảng hoãn. File đi kèm có 31 bảng, trong đó 3 bảng hoãn và `fact_call` chưa đủ cột. Mỗi bảng nằm trong `$defs`, có grain, khóa, mức nguồn thu; `x-change` cho biết phần thay đổi. Cột không có trong `required` có thể vắng mặt; chỉ nhận `null` khi type/schema cho phép. `x-deferred-columns`, `x-moved-columns`, `x-removed-columns` ghi rõ cột đi đâu. Để kiểm tra một bản ghi, validate với `{"$ref": "#/$defs/<tên bảng>"}`.

Các chi tiết dưới đây mang nhãn `x-review` và đang mở để Hiệp góp ý.

| Mã | Chi tiết | Lý do hoặc phương án khác |
|---|---|---|
| **S13** | Bảng `turn_probe` và các cột của nó | Phương án khác là giữ trong `path_leg_measurement`, nhưng khóa bảng đó vô nghĩa với probe |
| **S15** | Bộ đếm tích lũy trên `call_stats_epoch` và trên dòng `selected_pair_change` của `ice_event` | Phương án khác là bảng snapshot riêng |
| **S16** | `end_signal`, `client_end_reason`, bảng `client_call_report` tách từ `call_outcome` | Ảnh hưởng trực tiếp đến phần BE ghi |
| S1 | `ice_attempt_endpoint` và `ice_connected_any_ts` (file đi kèm) | Giữ mốc từng bên |
| S2 | Tên và cột của `client_applied_config`: `config_source`, `is_fallback_config`, `applied_entries` | |
| S3 | Giữ `selector_decision` theo từng bên, lặp field cấp quyết định, thêm I25 | Phương án khác là tách bảng theo quyết định, gọn hơn nhưng đổi nhiều hơn |
| S4 | `normalized_config_key`, `eligible_action_set`, `confidence_evidence` | |
| S6 | `ice_event` thêm `dtls_state_change`, `restart_requested`, `event_mono_ms`, `clock_session_id` | Để pipeline dựng được `ice_attempt` |
| S7 | `call_stats_5s` thêm `packets_received`, `rtt_measurements_delta` | Pipeline tính lại được `call_stats_epoch` theo I22 |
| S8 | `outcome_log` có `outcome_version`, `outcome_provenance`, `finalized_ts`; nhiều cột được null cho placeholder; `first_media_definition` (file đi kèm) | |
| S9 | `fact_call` có `pcr_group`, `poor_unattributed`, `action_propensity`, `propensity_decision_id` (file đi kèm) | |
| S11 | Enum `observation_state` và cột cùng tên trên `turn_health_1m`, `turn_probe` | |
| S12 | `decision_source = static_config` và `policy_version = static@1` khi chưa có Selector | Tên chỉ là gợi ý |
| S14 | `liveness_ok`, `liveness_method` thay cho `health_status` trên raw | |
| S17 | `local_turn_url` trên `ice_event` | |
| S18 | `server_session_id`, `credential_ref` trên `turn_allocation` | |
| S19 | Bỏ giá trị `refined` của `decision_phase` | Phụ thuộc việc spec có còn gọi lần hai không |
| S20 | `sequence_no` bắt buộc và nằm trong khóa của `call_stats_epoch` | Checkpoint tạo nhiều dòng cùng epoch |

### 15.4. Lỗi nhỏ cần sửa cùng lúc

- Đầu contract còn trỏ tới `data-contract-explained.md`, file đã bị bỏ khỏi repo.
- ERD ghi `selector_decision.decision_id` là PK, trong khi một `decision_id` có nhiều dòng.
- Sơ đồ luồng dữ liệu vẽ `selector` ghi `selector_decision`, trong khi §10 quy định Selector không tự ghi.
- Sơ đồ luồng đang vẽ `allocate (rank 1)` và nhánh `ice_attempt` mới theo rank kế; nên sửa để không ngụ ý client chỉ cấp phát rank 1.
- Spec viết "4 TURN/bên" ở nhiều chỗ.
- §15 ánh xạ `url` trên remote candidate là sai.

---

## 16. Ngoài phạm vi

Đề xuất này không chốt các nội dung sau. Mình có ghi chú và script thử nghiệm cho một số phần, gửi riêng khi Hiệp cần.

- **Mô hình ICE trong simulator:** nhiễu, tham số lab, regression.
- **Mô hình ghép chặng:** cách fit, gate, ngưỡng.
- **Hiệu chỉnh** candidate latency sang RTT.
- **Detector stall:** tiêu chí xác nhận, chu kỳ đo, guardrail gián đoạn.
- **Đánh giá:** test BE-invariance ở §14.2, sensitivity, margin, power, benchmark, luật kết luận.
- **Các phần chưa rà soát sâu của v0.4.0:** nhiều thiết bị (S21), cuộc gọi nhóm (S22), `derivation` (S24), `release_regression` (S25), OPE, pilot switchback (§14.7), `blind_benchmark`. Riêng `device_id` đã khai báo hỗ trợ thì khóa và join phải đúng.
- **Phân công và tiến độ.**

---

## 17. Mức độ kiểm chứng

| Nội dung | Mức |
|---|---|
| Vị trí trong contract, spec, ERD | Đã đọc trực tiếp ở commit `e4d84f8` |
| W3C webrtc-stats, W3C WebRTC | Đã đọc đặc tả; chưa thử trên từng trình duyệt |
| RFC 8656, RFC 8445 | Đã đọc các mục được trích |
| Exporter coturn | Đã đọc `prom_server.c` bản 4.6.1 và `master`; chưa có bản công ty đang chạy |
| Số liệu lab | Trích từ `KET_QUA.md`; xem giới hạn ở mục 1.3 |
| Trường getStats về kết nối | `lab_ice.js` đọc được trên Chromium 156, dùng data channel |
| Trường getStats về media, `url`, `address`, `iceRole`, bộ đếm tích lũy, bộ đếm theo cặp | Mới theo đặc tả, chưa đo |
| Mobile, Firefox, Safari | Chưa kiểm tra |
| Probe, credential theo cuộc gọi, GeoIP, nguồn giám sát máy chủ | Chưa có bằng chứng, là giả định về khả năng thu |
| VIA | Đã đọc lại mục 3.1, 3.2 và 4.4 |
| MSR-TR-2016-57 | Đã đọc toàn văn. Có bằng chứng về tính cộng trên dữ liệu thật của Skype, nhưng chưa phải cho chặng TURN với TURN hay mạng Việt Nam |
| Thử nghiệm ghép chặng và probe | Trên thế giới cộng tính giả lập, nên chỉ kiểm tra logic |
| Hai file YAML | Hợp lệ theo JSON Schema 2020-12; khóa và tham chiếu đã kiểm tra; các tình huống đúng, sai theo từng dòng cho kết quả như mong đợi. Chưa thử với dữ liệu thật. Bất biến nhiều bảng chưa chạy được bằng schema |
