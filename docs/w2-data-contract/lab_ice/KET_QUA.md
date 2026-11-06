# Kết quả lab ICE

**Môi trường:** Chromium 156.0.8078.4 headless, coturn 4.6.1 không sửa, 8 TURN trên một máy. Dữ liệu gốc: `ket_qua.json` (R1 đến R8), `ket_qua_bo_sung.json` (R9 đến R11).

**Cách đọc:** đây là bằng chứng về **cơ chế** trên Chromium. Mỗi cấu hình chỉ có 2 đến 12 lần chạy. Không dùng các con số này để kết luận về chất lượng production.

## Tham số đo được

| Tham số | Giá trị đo | Kịch bản |
|---|---|---|
| Thời gian thêm do danh sách 8 so với 4, TURN khỏe | Khoảng 7 đến 11 ms | R5, R9 |
| Thời gian thêm khi TURN đã chết từ trước lúc cấp phát | Không đo được khác biệt | R5 |
| Thời gian thêm khi TURN chết sau khi đã cấp phát | Khoảng **63 ms × (k − 1)²**, với k là vị trí TURN sống đầu tiên ở phía đó | R9 |
| Trường hợp xấu nhất ở trên | **777 ms** với danh sách 4, **3.282 ms** với danh sách 8 | R9 |
| Cửa sổ ICE còn tự chuyển đường | TURN chết khi cuộc gọi dưới **7 giây**: có. Từ **8 giây**: không | R10 |
| Thời gian tự chuyển đường trong cửa sổ đó | 3,7 đến 4,0 giây | R10 |
| Từ lúc TURN chết đến khi ICE báo `disconnected` | 6,4 đến 7,7 giây | R4 |
| Từ `disconnected` đến `connectionState = failed` | Khoảng 10 giây | R4 |
| ICE restart sau đó | 162 đến 193 ms (tín hiệu 50 ms, mạng nội bộ), giống nhau với 4 và 8 TURN | R4 |
| Số cặp còn sống theo tuổi cuộc gọi | Đủ đến khoảng 10 giây, còn 1 đến 3 cặp lúc 15 giây, còn 1 cặp lúc 40 giây | R2, R4 |
| Số cặp có RTT trong danh sách 8 | **1 trên 32 cặp** suốt 90 giây | R2 |
| Lưu lượng tới TURN không dùng | Chỉ vài gói mỗi đợt, về 0 từ khoảng 60 giây | R2 |
| Thời điểm nhận candidate theo độ trễ một chiều | 65 + 4,01 × độ trễ (ms), R² = 0,99997, sai lệch tối đa 1,8 ms | R7 |
| TURN của Callee bị loại khi cấp phát chậm hơn TURN nhanh nhất | Tín hiệu 50 ms: giữ đến 60 ms, mất từ 100 ms. Tín hiệu 300 ms: giữ đến 220 ms, mất từ 300 ms | R11 |
| Thời gian thu đủ candidate khi có một TURN chết | **39,9 giây**, so với 0,12 giây khi tất cả khỏe | R5 |

## Các hành vi đã xác nhận

| Hành vi | Kết quả |
|---|---|
| Số cặp với danh sách 6 UDP và 2 TCP | 64 cặp, mọi candidate đều là UDP |
| Danh sách 3 UDP và 1 TCP | 16 cặp |
| Caller chỉ có TCP | Vẫn ghép được với TURN UDP của Callee |
| TCP đứng trước UDP trong danh sách | UDP vẫn được chọn |
| Đặt chéo hai TURN | Đúng cặp đầu, 4 trên 4 lần |
| Đặt chéo, TURN đầu của Caller chết | Chuyển sang một relay qua TURN còn lại, 4 trên 4 lần |
| Dùng chung một TURN | Đúng, 4 trên 4 lần. Hairpin chạy được **trên một máy**, chưa nói lên điều gì về NAT 1:1 trên cloud |

## Khác với dự đoán từ mã nguồn

1. **Không phải lúc nào cũng ghim ở vị trí đầu.** Khi có một kết nối đủ tốt đầu tiên, libwebrtc dừng thu candidate (`stop_gather_on_strongly_connected`, mặc định bật). TURN nào cấp phát chậm hơn sẽ bị loại hẳn.
   - Caller có thời gian đổ chuông nên giữ đủ danh sách. Khi đó ICE ghim thật: RTT 64 ms (vị trí đầu chậm 15 ms) và 132 ms (chậm 60 ms), trong khi đường tốt nhất chỉ 23 ms.
   - Callee thường mất TURN chậm, nên có thể không dùng đúng vị trí đầu do Selector xếp.
   - Không có đổ chuông, cả hai bên đều có thể mất TURN chậm.
2. **Cửa sổ tự chuyển đường là khoảng 7 giây, không phải 30 giây.** Cặp đã prune mà chưa từng nhận gì bị hủy sau 10 giây, và ICE cần khoảng 2,5 giây để nhận ra kết nối yếu.
3. **TURN chết từ trước không làm chậm kết nối khi dùng trickle ICE,** vì nó không tạo ra candidate. Chi phí chỉ xuất hiện khi TURN chết sau khi đã cấp phát.
4. **Các vị trí sau vẫn có ích sau cửa sổ 7 giây:** ICE restart thu lại candidate từ cả danh sách, nên có thể phục hồi mà không cần gọi lại Selector.
5. **Khi chất lượng xấu đi:** RTT tăng 300 ms thì ICE không rời TURN trong 45 giây. Mất 30% gói thì sau 45 giây vẫn ở TURN cũ, chỉ đổi thoáng qua một lần. Mất 60% và 90% thì có chuyển, nhưng thử nghiệm này bắt đầu từ giây thứ 6, tức còn trong cửa sổ. Sau cửa sổ chưa được đo.

## Giới hạn

- Chặng giữa hai TURN không có độ trễ thêm.
- Mọi TURN dùng chung một relay IP. Permission tính theo IP nên ở đây dễ hơn thực tế; TURN khác IP có thể làm kiểm tra và cuộc đua chậm hơn.
- Hai bên chạy chung một trình duyệt, cùng máy, cùng interface. Chưa có mạng di động, Wi-Fi hay NAT thật.
- Mới đo Chromium. Firefox và Safari chưa đo.
- Luật 63 ms × (k − 1)² khớp 5 điểm đo, với một phía có TURN chết. Chưa thử cả hai phía cùng có TURN chết.
- Trong R10 có một lần chuyển đường sau 207 ms, khác hẳn các lần còn lại. Lúc đó chỉ còn 12 cặp, nên nhiều khả năng cặp đang dùng đã không đi qua TURN bị tắt.

## Các lần chạy không dùng được

Dữ liệu của hai lần chạy này đã được xóa; chỉ giữ lại lý do.

| Lần chạy | Lý do |
|---|---|
| `lan_chay_1_co_loi/` | `node-turn` trả phản hồi ChannelBind thiếu `MESSAGE-INTEGRITY`, khiến mọi cuộc gọi chết ở giây thứ 40 |
| `lan_chay_2_node_turn_loi_channeldata/` | Sau khi vá lỗi trên, cặp được chọn đổi liên tục và data channel mở rất chậm. Vì thế lab chuyển sang coturn |
