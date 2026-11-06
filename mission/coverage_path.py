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


def create_multi_area_coverage_path(
        areas, spacing_m, uav_position, algorithm="zigzag"):
    """Tạo một tuyến liên tục qua các khu vực theo thứ tự danh sách."""
    if not isinstance(areas, list) or not areas:
        raise ValueError("Cần ít nhất một khu vực đã lưu để tạo tuyến.")

    current_position = uav_position
    all_waypoints = []
    area_results = []
    total_lane_count = 0

    for area_index, area in enumerate(areas, start=1):
        if not isinstance(area, dict):
            raise ValueError(f"Dữ liệu khu vực {area_index} không hợp lệ.")

        try:
            area_id = area["id"]
            area_name = area["name"]
            coordinates = area["coordinates"]
        except KeyError as error:
            raise ValueError(
                f"Khu vực {area_index} thiếu trường {error.args[0]}."
            ) from None

        area_path = create_coverage_path(
            coordinates,
            spacing_m,
            current_position,
            algorithm=algorithm,
        )
        waypoint_start = len(all_waypoints) + 1
        all_waypoints.extend(area_path["waypoints"])
        waypoint_end = len(all_waypoints)
        area_results.append({
            "area_id": area_id,
            "area_name": area_name,
            "lane_count": area_path["lane_count"],
            "spacing_m": area_path["spacing_m"],
            "scan_angle_degrees": area_path["scan_angle_degrees"],
            "waypoint_start": waypoint_start,
            "waypoint_end": waypoint_end,
        })

        total_lane_count += area_path["lane_count"]
        current_position = area_path["waypoints"][-1]

    return {
        "algorithm": algorithm,
        "spacing_m": spacing_m,
        "lane_count": total_lane_count,
        "areas": area_results,
        "waypoints": all_waypoints,
    }
