# UAV Search and Rescue

Ứng dụng Python/PyQt5 hiển thị bản đồ, quản lý các polygon tìm kiếm và tạo
waypoint bao phủ khu vực.

## Tổ chức phần tạo đường bay

- `mission/coverage_path.py`: điểm vào chung để chọn thuật toán tạo đường bay.
- `mission/zigzag.py`: đổi polygon GPS sang XY cục bộ, tạo các làn
  quét zigzag, sắp thứ tự waypoint bắt đầu từ vị trí UAV giả lập.
- `mission/waypoint_store.py`: lưu tuyến waypoint đã tạo vào JSON.
- `data/waypoints.json`: kết quả mới nhất cho từng polygon và thuật toán; file
  này được Git bỏ qua vì có thể chứa tọa độ khu vực thực tế.

Khi bấm **Tạo đường quét**, GUI gửi polygon đang chọn, khoảng cách quét và vị
trí UAV giả lập qua QWebChannel. Python gọi thuật toán Zigzag, trả kết quả để
bản đồ hiển thị và lưu danh sách waypoint vào `data/waypoints.json`.
Khi xóa một polygon, các tuyến waypoint gắn với polygon đó cũng bị xóa; tuyến
của những polygon khác vẫn được giữ lại.

Thuật toán hiện tại là phiên bản đầu: làn quét theo một hướng cố định; chưa
kiểm tra các đoạn nối có nằm hoàn toàn trong polygon hay chưa. Chưa kết nối
PX4/Gazebo và chưa điều khiển UAV thật.
