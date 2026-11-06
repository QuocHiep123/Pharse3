# Lab kiểm chứng ICE trên Chromium thật

Lab gồm hai PeerConnection trong một trang Chromium `about:blank`, 8 tiến trình coturn và các proxy tạo độ trễ, mất gói hoặc ngắt hẳn từng TURN. Trang chỉ kết nối tới các dịch vụ cục bộ.

Kết quả và cách đọc nằm ở [KET_QUA.md](KET_QUA.md).

## Cài đặt

```bash
cd docs/w2-data-contract/lab_ice
```

```bash
npm init -y && npm i playwright-core
```

```bash
PLAYWRIGHT_BROWSERS_PATH=./browsers npx playwright-core install chromium-headless-shell
```

```bash
sudo apt-get install -y coturn libnss3 libnspr4 libasound2t64
```

Không có quyền root thì dùng `apt-get download` rồi `dpkg -x` vào một thư mục, sau đó trỏ `COTURN_BIN`, `COTURN_LIB` và `LD_LIBRARY_PATH` tới thư mục đó.

## Chạy

Script dùng `--no-sandbox` để chạy được trong WSL. Chỉ dùng cấu hình này cho lab cục bộ. Script cũng cần interface tên `eth0`.

```bash
CHROME_BIN=$(find ./browsers -type f -name chrome-headless-shell | head -1) OUT=ket_qua.json node lab_ice.js 2>&1 | tee ket_qua.log
```

Toàn bộ mất khoảng 45 phút. Thêm `ONLY=R1,R4` để chọn kịch bản, `REPS=1` để chạy thử nhanh.

## Các kịch bản

| Kịch bản | Câu hỏi |
|---|---|
| R1 | Vị trí đầu chậm hơn thì cặp nào thắng, tùy theo độ trễ tín hiệu và thời gian đổ chuông? |
| R2 | Bao nhiêu cặp được ping và có RTT? Các cặp khác sống bao lâu? |
| R3 | TCP có ghép với UDP không? Thứ tự danh sách có thắng giao thức không? |
| R4 | TURN chết ở các thời điểm khác nhau thì ICE có tự phục hồi không? ICE restart mất bao lâu? |
| R5 | Thời gian thiết lập theo độ dài danh sách, khi TURN chết từ trước. Thời gian thu đủ candidate |
| R6 | TURN đang dùng xấu đi thì ICE có rời đi không? |
| R7 | Thời điểm nhận candidate có phản ánh độ trễ tới từng TURN không? |
| R8 | Kế hoạch đặt chéo và dùng chung có cho đúng cặp không? |
| R9 | TURN của Caller chết sau khi đã cấp phát thì danh sách dài tốn thêm bao nhiêu? |
| R10 | Tuổi cuộc gọi nào là giới hạn để ICE còn tự chuyển đường? |
| R11 | TURN của Callee chậm hơn bao nhiêu thì bị loại khỏi cuộc đua? |

Cần lặp lại trên Firefox và Safari, vì Firefox không dùng mã ICE của libwebrtc.
