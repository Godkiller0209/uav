# UAV Search and Rescue

Dự án Python/PyQt5 nghiên cứu hệ UAV SAR theo hướng **continuous trajectory
planning, trajectory tracking control và multi-UAV coordination**. Trọng tâm
hiện tại là tạo và xem quỹ đạo bao phủ liên tục; GUI bản đồ, kết nối MAVSDK và
luồng Mission cũ được giữ lại để tiếp tục dùng.

## Trạng thái hiện tại

- GUI PyQt5 có trang bản đồ Leaflet, vẽ/chọn/lưu nhiều polygon qua
  `QWebChannel` và trang thao tác UAV.
- Zigzag cũ vẫn tạo tuyến waypoint, lưu `data/waypoints.json` và được trang UAV
  dùng để dựng MAVSDK `MissionPlan`. Đây là **Mission waypoint**, chưa phải
  continuous trajectory tracking.
- Có planner Archimedean Spiral trong `trajectory_planning/`. Nó chuyển GPS
  sang XY cục bộ, kiểm tra polygon đơn giản, xác định tâm tự động hoặc nhận tâm
  người dùng, lấy mẫu đường xoắn, clip theo polygon và ước lượng các chỉ số.
- Bản đồ có lựa chọn Zigzag/Spiral; Spiral áp dụng cho polygon đang chọn và
  được lưu riêng ở `data/trajectories.json`. Tạo/hiển thị quỹ đạo chưa gửi nó
  đến PX4.
- Kết quả Spiral gồm GPS và XY theo local frame (có ghi gốc frame), spacing,
  bán kính ban đầu, hệ số tăng bán kính, chiều dài, Coverage Ratio ước lượng,
  vi phạm biên theo phép clip, số discontinuity và chỉ số đổi hướng/độ cong.
- `DroneClient` và `MissionService` MAVSDK 4.0.6 được giữ nguyên. Chưa đánh giá
  lại việc kết nối PX4/SITL trong phiên rà soát này.
- Chưa triển khai Cascaded PID, Backstepping, Offboard setpoint liên tục hay
  điều phối nhiều UAV.

## Phương pháp Archimedean Spiral

Đường chuẩn trong mặt phẳng XY là `r(θ) = a + bθ`,
`x = xc + r cos θ`, `y = yc + r sin θ`. Vì sau một vòng `θ` tăng `2π`, khoảng
cách bán kính giữa hai vòng là `2πb`; do đó `b = spiral_spacing / (2π)`.
Spacing nên được chọn dựa trên footprint cảm biến. GUI cho nhập đường kính
footprint; nếu spacing lớn hơn footprint, giao diện phát cảnh báo và coverage
ước lượng có thể thấp.

Đường cong được lấy mẫu thành các đoạn ngắn rồi cắt theo polygon. Những phần
liên tục bên trong được vẽ thành các segment riêng. Các đoạn rời nhau **không
được nối tự động**, vì đường thẳng nối có thể cắt qua vùng ngoài khu vực hoặc
vùng cấm. `Coverage Ratio` là ước lượng theo lưới điểm và footprint tròn; đây
không phải chứng minh bao phủ hoàn toàn. `Boundary Violation` của đường đã clip
được báo 0 theo mô hình hình học, nhưng sai số lấy mẫu và phép chiếu vẫn tồn
tại.

Polygon lõm có thể làm một Spiral chuẩn bị cắt thành nhiều đoạn; Spiral đơn
cũng không bảo đảm bao phủ tốt các góc, nhánh hẹp hoặc vùng xa tâm. Bước nghiên
cứu tiếp theo có thể là đường offset thích nghi biên kết hợp các connector an
toàn bên trong polygon. Phương pháp đó sẽ khác Archimedean Spiral chuẩn và cần
được ghi nhãn riêng.

Phép chiếu hiện tại là equirectangular cục bộ, phù hợp các khu vực nhỏ, không
phù hợp vùng cực hoặc polygon rất rộng/cắt kinh tuyến 180°. Hình học được xử lý
bằng Python thuần, không thêm thư viện ngoài.

## Cấu trúc chính

```text
GUI/                         PyQt5 pages, QWebChannel bridge
assets/                      Leaflet HTML/JavaScript
coverage_path_planning/      Zigzag waypoint tương thích Mission cũ
trajectory_planning/         Thuật toán quỹ đạo, tách khỏi GUI/PX4
drone/                       DroneClient, MAVSDK và telemetry
mission/                     Xác thực và tạo MAVSDK MissionPlan
tests/                       Unit test hình học Spiral
data/                        Polygon, waypoint và trajectory cục bộ
```

Không xóa Zigzag hay Mission cũ: `GUI/map_bridge.py` gọi planner Zigzag,
`mission/mission_service.py` nạp waypoint JSON, và `GUI/uav_page.py` tạo/
upload MissionPlan. Spiral dùng định dạng trajectory riêng, không làm thay đổi
schema waypoint Mission.

## Cài đặt và chạy

Linux/macOS, từ thư mục dự án:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Tắt môi trường ảo bằng `deactivate`. Trên Windows PowerShell, bật bằng
`.venv\Scripts\Activate.ps1`.

## Dùng Spiral trên bản đồ

1. Chọn **Vẽ đa giác mới**, tạo polygon rồi **Hoàn thành và lưu**.
2. Chọn polygon trong danh sách.
3. Chọn **Archimedean Spiral · khu vực đang chọn**.
4. Nhập spacing và footprint cảm biến. Quan hệ gợi ý: spacing không vượt quá
   footprint (độ chồng lấn cụ thể còn phụ thuộc cảm biến và nhiệm vụ).
5. Có thể chọn tâm bằng nút **Chọn tâm Spiral trên bản đồ** và click bên trong
   polygon; hoặc dùng **Dùng tâm Spiral tự động**.
6. Đặt bán kính ban đầu nếu cần, sau đó nhấn **Generate Trajectory**.

Bản đồ phân biệt polygon, tâm Spiral và từng segment quỹ đạo. Khu vực lõm có
thể tạo nhiều segment; không có đường nối ngoài vùng. Xóa/tạo lại bằng cách
đổi tham số và nhấn Generate Trajectory. Zigzag cũ vẫn chọn được riêng.

## Kiểm tra

Chạy unit test hình học (không cần PX4/Gazebo):

```bash
python -m unittest discover -s tests -v
```

Test bao gồm hình vuông, chữ nhật, tam giác, lồi không đều, lõm, polygon nhỏ,
hình phức tạp gần biên, spacing, tâm ngoài polygon và polygon tự giao.

## Hướng nghiên cứu sau

- Đánh giá planner trên polygon thực và cải tiến bao phủ vùng biên/góc.
- Chọn chiến lược connector an toàn hoặc trajectory kiểu offset thích nghi.
- Định nghĩa điểm tham chiếu `(position, velocity, acceleration, time)` dùng
  chung giữa planner và tracker; xem
  [`docs/trajectory_tracking_interface.md`](docs/trajectory_tracking_interface.md).
- So sánh Cascaded PID và Backstepping trong module control riêng.
- Nghiên cứu Offboard để gửi setpoint liên tục; Mission API chỉ giữ làm luồng
  waypoint dự phòng/đối chứng.
- Sau đó mới triển khai phân vùng, phối hợp, phát hiện lỗi và phân phối lại
  nhiệm vụ cho nhiều UAV.

Không khẳng định GUI, PX4 hoặc điều khiển bay đã được kiểm chứng chỉ từ việc
code tồn tại. Bản đồ Leaflet/MapTiler cần Internet; không đưa API key vào log
hoặc tài liệu công khai.
