# Giao diện dữ liệu planner và trajectory tracker

Đây là hợp đồng dữ liệu dự kiến, chưa phải bộ điều khiển đã cài đặt. Planner
phải mô tả mục tiêu chuyển động; tracker nhận tham chiếu theo thời gian và so
sánh với trạng thái ước lượng từ telemetry.

Mỗi mẫu tham chiếu nên có dạng:

```python
{
    "time_s": 12.5,
    "position_m": {"x": 42.0, "y": 18.0, "z": 20.0},
    "velocity_m_s": {"x": 3.0, "y": 0.5, "z": 0.0},
    "acceleration_m_s2": {"x": 0.0, "y": -0.2, "z": 0.0},
    "heading_rad": 0.17,
}
```

- `time_s`: thời gian tương đối đơn điệu từ đầu segment/quỹ đạo.
- `position_m`: vị trí tham chiếu trong một local frame có gốc và phép chiếu
  được ghi metadata; `z`/độ cao phải được xác định rõ theo datum trước khi
  gửi bay.
- `velocity_m_s`, `acceleration_m_s2`: đạo hàm tham chiếu theo cùng frame.
- `heading_rad`: tùy chọn, suy ra từ vận tốc ngang khi tốc độ khác 0.

Planner không được phụ thuộc vào tracker. Tracker cần interface chung để có
thể thay Cascaded PID bằng Backstepping. Sau này có thể tách vòng position,
velocity và attitude/rate theo loại setpoint: Python gửi position/velocity/
acceleration ở Offboard; PX4 thường giữ các vòng ổn định attitude/rate và
actuator cấp thấp. Cần kiểm tra cụ thể loại setpoint mà MAVSDK/PX4 hỗ trợ trước
khi triển khai.

Các đoạn Spiral sau khi clip có thể rời nhau. Mỗi segment phải có thời gian
riêng hoặc cần một connector an toàn đã được planner xác minh; không được đặt
hai điểm cuối/đầu rời nhau thành hai mẫu liền kề cùng một timeline mà không
mô tả chuyển tiếp. Phiên bản planner hiện tại chỉ xuất vị trí XY/GPS từng
segment và chưa xuất các tham chiếu vận tốc, gia tốc, độ cao hay thời gian.
