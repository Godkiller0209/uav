# Hướng dẫn phát triển UAV SAR

## Mục tiêu nghiên cứu

Dự án chuyển trọng tâm từ **Waypoint Following** sang **Continuous Trajectory
Planning, Trajectory Tracking Control và Multi-UAV Coordination**. Phát triển
từng giai đoạn, ưu tiên hiện tại là sinh quỹ đạo bao phủ khu vực bất kỳ bằng
Archimedean Spiral. Tái sử dụng GUI, polygon, MAVSDK và Mission hiện có khi
phù hợp; không viết lại dự án.

## Trạng thái và ranh giới module

- `GUI/`, `assets/`: giao diện, bản đồ, tương tác và QWebChannel. Không đặt
  thuật toán hình học hoặc điều khiển phức tạp ở đây.
- `trajectory_planning/`: chuyển tọa độ và sinh/xử lý quỹ đạo; không phụ thuộc
  GUI, PX4 hay MAVSDK.
- `coverage_path_planning/`: Zigzag waypoint cũ, còn được Mission sử dụng.
- `drone/`: MAVSDK client, telemetry và lệnh UAV.
- `mission/`: xác thực waypoint, cấu hình và tạo MAVSDK MissionPlan.
- `tests/`: kiểm tra hình học và nghiệp vụ có thể chạy độc lập với PX4.

Không xóa Zigzag hoặc Mission trước khi kiểm tra toàn bộ import/call sites:
GUI hiện gọi planner Zigzag, MissionService đọc `data/waypoints.json`, UavPage
dùng nó để tạo MissionPlan. Spiral lưu riêng `data/trajectories.json`; không
được xem các segment bị ngắt là một chuỗi waypoint Mission liên tục.

## Kế hoạch kỹ thuật

1. Sinh Archimedean Spiral trong XY cục bộ, clip với polygon và báo rõ đoạn
   đứt. Với `r = a + bθ`, `spiral_spacing = 2πb`.
2. Đánh giá coverage, chiều dài, spacing, vi phạm biên, điểm đứt và hành vi
   quay; nêu phương pháp ước lượng và sai số.
3. Định nghĩa giao diện tham chiếu planner/tracker gồm thời gian, vị trí, vận
   tốc và gia tốc.
4. Sau khi planner được đánh giá, nghiên cứu Cascaded PID và Backstepping.
   Python gửi setpoint phù hợp qua MAVSDK Offboard; PX4 tiếp tục đảm nhiệm các
   vòng điều khiển cấp thấp theo cấu hình. Mission Mode vẫn là phương án
   waypoint cũ và không tương đương continuous tracking.
5. Chỉ ở giai đoạn sau mới làm chia vùng, phân công, giám sát lỗi, tái phân
   phối và tránh xung đột nhiều UAV.

Không triển khai PID, Backstepping, Offboard hoặc Multi-UAV trước phạm vi
planner hiện tại. Không tự chuyển sang ROS2, không sửa PX4/Gazebo khi không
cần, không cài thư viện tùy tiện và không tạo package rỗng. Chỉ thêm dependency
khi có lý do kỹ thuật rõ ràng.

## Nguyên tắc thực hiện

- Đọc code và import graph thực tế trước khi sửa/xóa; nội dung tài liệu không
  thay cho việc xác nhận chức năng chạy được.
- Giữ các chức năng GUI và MAVSDK đang có nếu chưa chứng minh được là dư thừa.
- Dùng đường dẫn dựa trên `__file__`; không phụ thuộc working directory.
- Không đưa API key, credential hay dữ liệu tọa độ riêng vào log/tài liệu.
- Không commit hoặc push nếu chưa được yêu cầu.
- Khi có thay đổi, giải thích file đã sửa, lý do, kiểm tra đã chạy và giới hạn
  còn lại. Không tuyên bố hoàn thành nếu chưa kiểm tra.

## Chạy

Tạo môi trường: `python -m venv .venv`; Linux/macOS bật bằng
`source .venv/bin/activate`, Windows PowerShell bật bằng
`.venv\\Scripts\\Activate.ps1`. Cài gói với `python -m pip install -r
requirements.txt`; chạy ứng dụng bằng `python main.py`. Unit test hình học:
`python -m unittest discover -s tests -v`.
