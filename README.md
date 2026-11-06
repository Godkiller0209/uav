# UAV Search and Rescue

Ứng dụng Python/PyQt5 hiển thị bản đồ, quản lý các polygon tìm kiếm và tạo
waypoint bao phủ khu vực.

## Tổ chức phần tạo đường bay

- `mission/zigzag.py`: đổi một polygon GPS sang XY cục bộ, tìm cạnh dài nhất,
  xoay hệ quét theo cạnh đó rồi tạo và sắp thứ tự waypoint Zigzag.
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

Mỗi polygon tự chọn hướng quét song song với cạnh dài nhất của nó. Đây là một
heuristic theo từng polygon, chưa tối ưu tổng quãng đường của cả nhiệm vụ; các
đoạn nối vẫn có thể ra ngoài polygon. Chưa kết nối PX4/Gazebo hay UAV thật.
