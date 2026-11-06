# 03 - Relay / path selection cho VoIP-video và Off-Policy Evaluation (OPE)

Ngày: 2026-11-04. Phạm vi: nghiên cứu tài liệu cho TURN Selector Intelligence.

Lưu ý độ tin cậy: mục Via được xác nhận qua web search (số liệu khác nhau giữa các phiên bản paper, cần xem lại PDF trước khi trích số). Các mục còn lại (Pytheas, CFA, blog Twilio/Cloudflare/Discord/Zoom, paper OPE) viết từ kiến thức nền; URL chưa được fetch lại trong phiên này. Mục nào "chưa kiểm chứng" đều được ghi rõ.

---

## 1. Relay / path selection cho call

### 1.1 Via (Jiang et al., SIGCOMM 2016) - paper quan trọng nhất
- Bài toán: với mỗi call (caller AS/ISP/geo, callee AS/ISP/geo), chọn đường: direct, hoặc qua 1 relay (bounce), hoặc 2 relay (transit) của overlay managed (backbone DC Microsoft). Dữ liệu: hàng chục đến hàng trăm triệu call Skype.
- Metric: RTT, loss, jitter; gộp thành **PNR (Poor Network Rate)** = tỷ lệ call có ít nhất 1 metric vượt ngưỡng xấu (ví dụ RTT >= 320ms, loss >= 1.2%, jitter >= 12ms; ngưỡng cần kiểm tra lại trong paper). Đánh giá bằng % giảm PNR so với default (direct) và so với oracle.
- Granularity/feature: gom call theo (source AS, dest AS), có thể thêm geo; mỗi nhóm có bảng performance cho từng relay option. Nhận xét: vấn đề mạng kém phân tán theo thời gian/vùng nên không fix được bằng rule tĩnh; hiệu năng đủ ổn định theo ngày để dự đoán.
- Cách làm hai pha:
  1. **Prediction-based pruning**: dùng lịch sử để dự đoán performance từng (nhóm, relay option), loại option chắc chắn kém, giữ top-k nhỏ.
  2. **Exploration-exploitation**: trên top-k còn lại dùng bandit (biến thể epsilon-greedy/UCB) cho từng nhóm; top-k nhỏ nên explore rẻ. Có **relay budget** (chỉ một phần call được relay, ưu tiên call có lợi ích kỳ vọng cao).
- **Sparse data / path chưa quan sát**: nhiều cặp (src,dst) ít mẫu. Via dùng **tomography / decomposition**: path = access leg (src->relay) + backbone + leg (relay->dst); hiệu năng leg học từ mọi call đi qua leg đó, rồi ghép để dự đoán cặp chưa từng quan sát. Đây là lý do ta log per-leg RTT/alloc.
- Đánh giá: trace-driven với **oracle** làm cận trên; so sánh với "luôn direct", "relay gần nhất", "chỉ prediction, không explore", "chỉ explore"; có pilot deployment nhỏ. Hạn chế: số đo chỉ có cho đường đã chọn, nên counterfactual dựa vào các lựa chọn explore.
- **What we take**:
  - Tách score = leg(caller->TURN_A) + leg(TURN_B->callee) (+ inter-TURN) thay vì học trên cặp đầy đủ: giải quyết sparse và dự đoán path chưa quan sát.
  - Pipeline hai pha: prune bằng predictor, explore trong top-k nhỏ. Ta allocate cả k server nên exploration gần như miễn phí về media (ICE chọn pair).
  - Metric chính kiểu PNR (tỷ lệ call xấu), không chỉ mean RTT; báo thêm "gap to oracle".
  - Ablation: no-explore, no-pruning, geo-only.
  - Thừa nhận oracle chỉ đúng trên tập path quan sát được.

### 1.2 Pytheas (Jiang et al., NSDI 2017)
- Frame tối ưu QoE thành exploration-exploitation theo nhóm (group = session có cùng critical features), dùng **Discounted UCB** ở frontend phân tán; backend group hóa near-real-time. Xử lý được độ trễ dữ liệu và thay đổi theo thời gian.
- **What we take**: nhóm call theo critical features (ISP, geo bucket), bandit mỗi nhóm; discounting cho non-stationarity/staleness; kiến trúc quyết định cục bộ, học tập trung.

### 1.3 CFA (Jiang et al., NSDI 2016)
- Critical Feature Analysis: học online feature nào quyết định chất lượng (ASN, CDN, city) rồi dự đoán theo nhóm khớp critical features. Hạn chế (Pytheas nêu): dự đoán thuần túy gây feedback loop, thiếu explore, herding.
- **What we take**: chọn granularity đủ dữ liệu với fallback phân cấp (ISP+city -> ISP+country -> country -> global); cảnh báo vòng phản hồi.

### 1.4 Thực tiễn công nghiệp (chủ yếu blog; chưa kiểm chứng chi tiết)
- **Twilio Network Traversal Service**: TURN global, trả danh sách ICE server theo vùng latency thấp (kiểu geo/latency routing) - tương đương Geo baseline.
- **Cloudflare Realtime TURN**: anycast, client tới PoP gần nhất theo BGP, không chọn tường minh. Khác ta: anycast đẩy quyết định cho routing; ta chọn tường minh nên phải log.
- **Zoom / Discord / Teams**: chọn theo proximity/geo + tải (Zoom), voice region auto theo ping/geo (Discord), Transport Relay anycast (Teams). Chi tiết nội bộ không công khai; kết luận an toàn: geo/proximity là chuẩn công nghiệp, hợp lý khi dùng Geo làm baseline. Cần tìm URL cụ thể trước khi trích dẫn chính thức.

### Bảng so sánh nhanh

| Hệ thống | Đơn vị quyết định | Explore | Dự đoán path chưa thấy | Metric |
|---|---|---|---|---|
| Via | (src AS, dst AS) x relay option | bandit trong top-k đã prune + budget | tomography theo leg | PNR, % giảm vs oracle |
| Pytheas | group theo critical feature | Discounted UCB | không (theo group) | QoE |
| CFA | critical-feature group | gần như không | không | độ chính xác dự đoán QoE |
| Ta | (caller ctx, callee ctx?) x top-k TURN | cần thiết kế (mục 3) | per-leg | xem mục 4, 7 |

---

## 2. Off-Policy Evaluation (OPE) trên logged bandit data

Setting: context x (caller/callee ctx), action a (TURN hoặc ranked list), reward r (chất lượng call), logging policy pi_0 sinh log, target policy pi (thuật toán mới) cần đánh giá.

| Estimator | Ý tưởng | Ưu | Nhược |
|---|---|---|---|
| Direct Method (DM) | V = mean(sum_a pi(a/x) * r_hat(x,a)) | Variance thấp | Bias nếu r_hat sai, đặc biệt vùng không có dữ liệu (đúng vấn đề closed-loop) |
| IPS/IPW | mean(w * r), w = pi(a/x) / pi_0(a/x) | Không bias nếu có support + propensity đúng | Variance cao; cần pi_0 > 0 |
| SNIPS | sum(w*r) / sum(w) (Swaminathan & Joachims 2015) | Giảm variance, bounded | Hơi bias; vẫn cần support |
| Doubly Robust (DR) | DM + IPS hiệu chỉnh phần dư (Dudik et al. 2011) | Không bias nếu một trong (r_hat, propensity) đúng | Vẫn cần support; w lớn + r_hat tệ gây nhiễu |
| Biến thể | Switch-DR, DRos (shrinkage), MRDR, clipping, DML | Điều khiển bias-variance | Phải chọn tham số |

### Yêu cầu logging cho OPE
- **Propensity thật** của hành động tại thời điểm quyết định (không xấp xỉ sau này).
- **Policy version** + config, để tái tạo pi_0 và biết khi nào policy đổi.
- **Support**: pi_0(a/x) > 0 với mọi a mà target pi có thể chọn. Policy **deterministic** (top-k cố định) cho propensity 0/1, nên IPS/DR không đánh giá được action chưa từng chọn. Phải có randomization.
- **Ranking/slate**: action space là tổ hợp, weight theo cả list làm variance bùng nổ. Dùng slot-wise / pseudo-inverse estimator (Swaminathan et al. 2017), cascade/position models (Li et al. 2018; McInerney et al. 2020). Với ta, giả định hợp lý là reward phân rã cộng theo leg/slot; phải nêu rõ đây là giả định.
- **Hai lớp quyết định**: (a) policy của ta chọn list (có propensity); (b) ICE chọn pair (ta không kiểm soát nhưng có thể mô hình P(pair used / list, RTT) từ log). Phải log cả hai.

### Tooling
- **Open Bandit Pipeline (obp)**: Saito et al., arXiv 2008.07146; docs https://zr-obp.readthedocs.io/en/latest/. Có IPW, SNIPW, DM, DR, Switch, DRos, MRDR, DML và estimator cho slate/ranking (nhóm `Slate*IPS`; xác nhận tên class theo version đang dùng). Schema `BanditFeedback` (action, reward, pscore, context, position) nên được dùng làm format chuẩn cho log của ta.
- **Vowpal Wabbit**: `--cb_explore_adf`, `--cb_type ips|dr|mtr`, `--explore_eval`; hỗ trợ log action probabilities (DSJSON). Dùng nếu muốn pipeline contextual-bandit dựng sẵn (cú pháp cần kiểm lại theo version).
- Decision Service (Agarwal et al.): kiến trúc logging + join dữ liệu exploration.

### Pitfalls
1. Logging deterministic: không support, estimate vô nghĩa cho action chưa chọn.
2. Variance bùng nổ khi w lớn: clip, SNIPS, bootstrap CI, báo effective sample size ESS = (sum w)^2 / sum w^2.
3. Propensity sai hoặc ghi sau khi lọc (ví dụ sau khi loại server down).
4. Non-stationarity: dùng time-split, không shuffle ngẫu nhiên.
5. Reward missing-not-at-random: chỉ đường được dùng mới có media metric.
6. Interference/herding: tải TURN phụ thuộc chính quyết định của policy; OPE bandit giả định no interference nên không bắt được. Cần simulator hoặc canary A/B.

---

## 3. Exploration an toàn cho production networking

| Chiến lược | Propensity log | Ghi chú cho TURN |
|---|---|---|
| Epsilon-greedy có ràng buộc | (1-eps) + eps/n hoặc eps/n | Chỉ explore trong top-m đã qua health + ngưỡng RTT/geo; không explore server unhealthy/quá xa |
| Softmax/Boltzmann trên score | p ~ exp(score/T) | Propensity đóng, liên tục, hợp IPS; chỉnh T để kiểm soát regret |
| Thompson sampling | Không đóng; ước lượng Monte Carlo rồi log | Tự thích nghi uncertainty; cần log posterior hoặc propensity MC |
| UCB / Discounted UCB (Pytheas) | Deterministic với cùng state | Muốn OPE phải thêm randomization |
| Randomized slot swap | Xác suất swap, ứng viên thay thế | Hợp ranking: swap slot thấp (3..k) nên ICE vẫn có đường tốt |

- **Lượng traffic**: kinh nghiệm chung là khoảng 1-5% traffic cho exploration (không phải con số cố định từ paper; chưa kiểm chứng nguồn cụ thể). Nên tính theo ESS cần đạt: đủ mẫu mỗi (context bucket, server) để CI đủ hẹp.
- **Guardrails**: không explore call ưu tiên cao hoặc khi có sự cố; kill switch; explore chỉ ở slot thấp để slot 1 an toàn; cap tải per-server.
- Vì ta allocate cả k, đổi một slot gần như zero-cost cho media, nhưng chỉ cho dữ liệu level 2 (alloc/RTT), không phải full media.

---

## 4. Metric đánh giá ranking

| Metric | Định nghĩa | Lưu ý |
|---|---|---|
| Rank-of-used | Vị trí trong list của TURN mà ICE dùng | Bị ảnh hưởng bởi ICE |
| Hit@k vs best path | Best path (theo oracle trên tập quan sát được) có trong top-k | Chỉ tính được trên call có đủ level-2 data |
| NDCG@k | Graded relevance = tier chất lượng từng path | Cần label nhiều path/call, chỉ tập con |
| Regret | quality(best observed) - quality(chosen); mean, p90, p95 | Oracle observed-only làm regret bị đánh giá thấp |
| PNR / poor-call rate | % call vượt ngưỡng RTT/loss/jitter | Metric kinh doanh, theo Via |
| Coverage | % (bucket, server) có >= N mẫu trong T ngày | Tách theo observation level |
| Staleness | Tuổi trung vị của quan sát gần nhất mỗi (bucket, server) | Liên hệ discounting |
| Traffic concentration | Gini / HHI (sum s_i^2) của phân phối allocation | So với Geo baseline |
| Overload / herding | Max utilization, tỷ lệ alloc fail, tương quan tải-RTT | OPE không thấy; cần simulator hoặc A/B |

Luôn kèm CI (bootstrap theo ngày/user để giữ tương quan), ESS, và phân tầng theo observation level (1/2/3) và blind vs known callee.

---

## 5. Callee location chưa biết (blind decision)

- **Prior over callee context**: P(callee bucket / caller, lịch sử user/tenant/room, giờ, tỷ lệ cùng quốc gia). Prior phân cấp: user history -> tenant -> caller region -> global.
- **Expected-cost selection**: chọn list L tối thiểu E_{c ~ P(callee)}[cost_caller_leg(a) + cost_callee_leg(b, c)]. Vì poor call là metric đuôi, cân nhắc risk-aware (CVaR, p90).
- **Two-phase decision**: phase 1 (t=0) chọn server phía caller (leg chỉ phụ thuộc caller) cộng tập đa dạng phía callee, đa dạng theo các cụm callee khả dĩ (tối đa hóa xác suất có ít nhất 1 server tốt, kiểu submodular coverage). Phase 2: khi callee lộ location (ví dụ candidates/join), cập nhật hoặc bổ sung TURN phía callee (re-rank, thêm allocation, hoặc ICE restart nếu cần).
- **Logging**: log quyết định lúc blind, phân phối prior đã dùng (để tái tạo propensity), và callee context thật hậu nghiệm (để tính regret). Đánh giá riêng giá trị thông tin: VoI = cost(blind) - cost(known).
- Cách Via xử lý phía callee chưa biết: chưa kiểm chứng, cần đọc lại paper.

---

## 6. Bảng yêu cầu logging

| Field | Vì sao cần |
|---|---|
| call_id, ts_decision, ts_end | Join, time-split, tránh leakage |
| policy_id + policy_version + config hash (k, T, eps, thresholds) | Tái tạo pi_0, tách ảnh hưởng thay đổi policy |
| role (caller/callee), list theo từng side | Quyết định theo từng bên |
| context: caller ISP/ASN, geo bucket, network type, giờ; callee ctx hoặc callee_unknown=true + prior đã dùng | Context x; tách blind |
| candidate set đủ điều kiện (sau lọc health/geo) kèm score | Biết support thực; tính pi(a/x) cho policy mới |
| ranked list k trả về (có thứ tự) | Action đã thực thi |
| propensity của list/từng slot + cách tính (eps, T, số mẫu MC) | IPS/DR bắt buộc |
| exploration flag + slot bị swap | Tách mẫu explore/exploit, kiểm tra support |
| shadow policy scores (Geo, policy mới) cùng call | Đánh giá đối chứng, tính w |
| per-leg alloc success/latency, RTT cho mọi TURN trong list | Level 2: phân rã leg, dự đoán path chưa quan sát |
| used pair (ICE selected pair, relay ids) + thời điểm | Action ICE thực dùng; mô hình P(used / list) |
| full media metrics (RTT, loss, jitter, MOS/score, duration, drop) cho path dùng | Level 1 reward |
| outcome flags (failure, reconnect, ICE restart) | Reward xấu, censoring |
| server health/load snapshot lúc quyết định | Context cho herding, non-stationarity |
| observation_level mỗi (call, server): 1/2/3 | Mô hình missingness, tách báo cáo |
| callee context hậu nghiệm + độ trễ lúc biết | Regret, VoI, two-phase |
| client version, tỷ lệ log drop/dedupe | Chất lượng log, selection bias do mất log |

---

## 7. Phương pháp đánh giá đề xuất (so với Geo baseline, trung thực)

1. **Điều kiện cần: randomization.** Nếu log hiện tại deterministic, OPE không có hiệu lực cho server chưa từng chọn. Bật exploration có propensity (softmax hoặc swap slot thấp, eps ~1-5% tùy ESS), ghi version. Kết quả trước đó chỉ gọi là "replay observed-only", không gọi là OPE.
2. **Hai lớp đánh giá**:
   - (A) Quan sát thật: chỉ trên call mà path của policy mới nằm trong tập level 1/2; báo "evaluation coverage" = % call có đủ dữ liệu. Không ngoại suy phần còn lại; thay vào đó báo cận (best-case/worst-case) bằng cách gán reward lạc quan/bi quan cho unobserved (kiểu bounds của Manski).
   - (B) Mô hình leg: học r_hat(x, leg) kiểu Via (additive, fallback phân cấp) làm DM; cross-fit.
3. **Estimators**: báo song song DM, SNIPS (có clip), DR (cross-fit), kèm bootstrap CI theo ngày và ESS. Tin DR khi DM và SNIPS cùng hướng; bất đồng lớn là cờ đỏ về support hoặc mô hình.
4. **Slate**: dùng slot-wise/pseudo-inverse (obp Slate estimators) với giả định additive; kiểm tra giả định bằng so với IPS trực tiếp trên subset nhỏ.
5. **Tách ICE**: báo policy value ở hai mức: list-level (hit@k, best-in-list; ta kiểm soát) và used-path-level (phụ thuộc ICE).
6. **Blind**: báo riêng blind vs known; so cost kỳ vọng dưới prior với cost thực hậu nghiệm; báo VoI và calibration của prior.
7. **Time-split** (train quá khứ, eval tương lai), phân tầng theo ISP/geo. Chỉ số: PNR, regret p50/p90, hit@k, rank-of-used, coverage, staleness, Gini/HHI, max load.
8. **Herding**: OPE không đo; thêm replay-simulator có mô hình tải (capacity, RTT tăng theo load) hoặc canary A/B tỷ lệ nhỏ với cap per-server; theo dõi HHI so với Geo.
9. **Trung thực**: ghi rõ phần nào là counterfactual thật và phần nào do mô hình; dùng bootstrap theo ngày/user vì call tương quan; báo cả kết quả âm; Geo baseline tính cùng cohort và filter.
10. **Lộ trình**: (a) chốt schema log theo mục 6, map sang obp `BanditFeedback`; (b) bật exploration có propensity 2-4 tuần; (c) chạy OPE và đối chiếu với A/B nhỏ để hiệu chuẩn (kiểm OPE bằng ground truth A/B).

---

## 8. Tài liệu tham khảo

- Jiang et al., VIA, SIGCOMM 2016. https://www.microsoft.com/en-us/research/publication/via-improving-internet-telephony-call-quality-using-predictive-relay-selection/ ; PDF https://cs.cmu.edu/~junchenj/via.pdf (đã xác nhận qua search)
- Jiang et al., Pytheas, NSDI 2017. https://www.usenix.org/conference/nsdi17/technical-sessions/presentation/jiang (chưa fetch lại)
- Jiang et al., CFA, NSDI 2016. https://www.usenix.org/conference/nsdi16/technical-sessions/presentation/jiang (chưa fetch lại)
- Saito et al., Open Bandit Dataset and Pipeline. https://arxiv.org/abs/2008.07146 ; https://zr-obp.readthedocs.io/en/latest/ ; https://pypi.org/project/obp (đã xác nhận qua search)
- Dudik, Langford, Li, Doubly Robust Policy Evaluation and Learning, ICML 2011. https://arxiv.org/abs/1103.4601
- Swaminathan & Joachims, The Self-Normalized Estimator for Counterfactual Learning, NeurIPS 2015 (tìm theo tiêu đề trên papers.nips.cc)
- Swaminathan et al., Off-policy Evaluation for Slate Recommendation, NeurIPS 2017. https://arxiv.org/abs/1605.04812
- Li et al., Offline Evaluation of Ranking Policies with Click Models, KDD 2018. https://arxiv.org/abs/1804.10488
- McInerney et al., Counterfactual Evaluation of Slate Recommendations with Sequential Reward Interactions, KDD 2020. https://arxiv.org/abs/2007.12986
- Agarwal et al., Making Contextual Decisions with Low Technical Debt. https://arxiv.org/abs/1606.03966
- Vowpal Wabbit docs. https://vowpalwabbit.org/ (chưa kiểm chứng trang cụ thể)
- Andersen et al., Resilient Overlay Networks, SOSP 2001.
- Twilio: https://www.twilio.com/docs/stun-turn ; Cloudflare: https://developers.cloudflare.com/realtime/turn/ (chưa kiểm chứng nội dung)
