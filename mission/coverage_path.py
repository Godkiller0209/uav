"""Điểm vào chung để chọn thuật toán tạo đường bao phủ khu vực."""

from mission.zigzag import create_zigzag_coverage_path


def create_coverage_path(
        coordinates, spacing_m, uav_position, algorithm="zigzag"):
    """Tạo đường bay bằng thuật toán được yêu cầu.

    Hàm này giữ giao diện gọi chung cho GUI. Khi thêm thuật toán mới, có thể
    thêm nhánh chọn thuật toán tại đây mà không đưa logic hình học vào GUI.
    """
    if algorithm == "zigzag":
        return create_zigzag_coverage_path(
            coordinates,
            spacing_m,
            uav_position,
        )

    raise ValueError(f"Thuật toán tạo đường bay không được hỗ trợ: {algorithm}")
