# Pharse3
## VIN TURN Selector — Vòng đời một cuộc gọi

Dòng thời gian của một cuộc gọi A → B, và mọi thành phần chạm vào nó. Trục ngang là thời gian của cuộc gọi. Phần trên chạy trong lúc gọi, phần dưới chạy sau khi gọi xong. Mũi tên xanh lá là vòng kín: cuộc gọi này dạy cho cuộc gọi sau.

🔗 **Bản tương tác (có dark mode):** https://claude.ai/artifact/FL225f5tBa1u1aFfppYE9L

**Ví dụ đang theo dõi:** A: `HAN · ASN 7552 · 4G` · B: `SGN · ASN 18403 · wifi` · Chọn: `DAD-1 → DAD-1` · Chi phí: `119,6 ms` · Confidence: `0,57 (medium)` · Bị loại: `SGN-1 (quá tải)`

![Sơ đồ swimlane vòng đời cuộc gọi TURN Selector](docs/turn-call-lifecycle.svg)

### Bảy bước, mỗi bước làm gì

| # | Bước | Làm gì |
|---|---|---|
| ① | **Request** | Signaling hỏi Selector. Selector tra **feature** đã tính sẵn, **ranking** lọc SGN-1 rồi chấm điểm các cặp bằng ms, rút thăm theo phân phối, gắn **confidence**. Ghi ngay `DECISION` kèm propensity. |
| ② | **Allocate** | Client xin chỗ trên **từng** server trong danh sách và đo thời gian. `ALLOCATION REPORT` cho RTT của cả k server, kể cả server không được dùng. |
| ③ | **ICE + media** | ICE mới là bên chọn đường cuối cùng. Selector chỉ gợi ý. Media đi A → DAD-1 → B, getStats đo RTT, loss, jitter. |
| ④ | **Kết thúc** | `CALL OUTCOME` ghi relay **thực sự** được dùng, thời gian thiết lập, chất lượng và lý do kết thúc. |
| ⑤ | **Label data** | Join ba event theo `decision_id` thành một dòng có nhãn. Nhãn gắn với relay thực dùng. Cuộc gọi lỗi vẫn giữ lại, không điền 0. |
| ⑥ | **Learning** | Mỗi 5 phút cập nhật thống kê có decay, tính lại chi phí, kiểm tra rồi xuất bản bảng mới. Cuộc gọi sau tra bảng này ở bước ①. |
| ⑦ | **Evaluation** | Gộp hàng nghìn dòng, so với baseline geo + health bằng OPE hoặc A/B. Chỉ khi qua cổng thì bản mới mới được tăng traffic. |

### Hai điều hay nhầm

- **Observability khác evaluation.** Observability hỏi hệ thống có đang chạy không: latency, lỗi, server sập. Evaluation hỏi quyết định có tốt hơn baseline không, và cần so sánh nhân quả trên nhiều dữ liệu.
- **Label data nằm ở giữa.** Cả learning lẫn evaluation đều đọc từ cùng một bảng nhãn. Nhãn sai thì cả hai sai theo cùng một hướng, nên rất khó phát hiện.

> Số liệu ví dụ lấy từ lần chạy `POST /v1/turn/select` của prototype (dữ liệu synthetic). Chi tiết ở `02`, `09`, `10`, `14`, `15` và `21-production-pipeline.md`.
