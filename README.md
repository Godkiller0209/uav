# UAV Search and Rescue

Ứng dụng Python/PyQt5 hiển thị bản đồ, quản lý các polygon tìm kiếm và tạo
waypoint bao phủ khu vực.

## Tổ chức phần tạo đường bay

- `mission/zigzag.py`: đổi một polygon GPS sang XY cục bộ, tạo làn Zigzag và
  sắp thứ tự waypoint bắt đầu từ vị trí hiện tại của UAV.
- `mission/coverage_path.py`: điều phối Zigzag qua toàn bộ polygon theo thứ tự
  danh sách, dùng waypoint cuối khu vực trước để chọn đầu vào khu vực kế tiếp.
- `mission/waypoint_store.py`: lưu tuyến waypoint đã tạo vào JSON.
- `data/waypoints.json`: tuyến Zigzag mới nhất đi qua toàn bộ polygon; file này
  được Git bỏ qua vì có thể chứa tọa độ khu vực thực tế.

Khi bấm **Tạo tuyến tất cả khu vực**, GUI gửi toàn bộ polygon đã lưu, khoảng
cách quét và vị trí UAV giả lập qua QWebChannel. Python tạo một danh sách
waypoint liên tục theo thứ tự các polygon, trả kết quả để bản đồ hiển thị và
lưu tuyến tổng hợp vào `data/waypoints.json`. Thay đổi danh sách khu vực hoặc
vị trí UAV sẽ xóa tuyến cũ để tránh dùng nhầm lộ trình đã lỗi thời.

Thuật toán hiện tại là phiên bản đầu: làn quét theo một hướng cố định; chưa
kiểm tra các đoạn nối có nằm hoàn toàn trong polygon hay chưa. Chưa kết nối
PX4/Gazebo và chưa điều khiển UAV thật.
