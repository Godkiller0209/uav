"""Chuyển polygon GPS sang XY và tạo các làn quét song song."""

import math


EARTH_RADIUS_M = 6_371_000
COORDINATE_EPSILON = 1e-8


def create_coverage_path(coordinates, spacing_m):
    """Tạo các đoạn quét nằm trong polygon; trả về dữ liệu vẽ dạng GPS."""
    _validate_spacing(spacing_m)
    polygon = _validate_and_project_polygon(coordinates)

    minimum_y = min(point[1] for point in polygon)
    maximum_y = max(point[1] for point in polygon)
    area_height = maximum_y - minimum_y
    if area_height <= COORDINATE_EPSILON:
        raise ValueError("Khu vực quá hẹp để tạo đường quét.")

    lane_count = max(1, math.ceil(area_height / spacing_m))
    lane_spacing = area_height / lane_count
    origin_lat, origin_lon = _get_origin(coordinates)
    latitude_scale = math.cos(math.radians(origin_lat))

    segments = []
    for lane_index in range(lane_count):
        scan_y = minimum_y + lane_spacing * (lane_index + 0.5)
        intervals = _get_scan_intervals(polygon, scan_y)

        if lane_index % 2 == 1:
            intervals.reverse()

        for start_x, end_x in intervals:
            if lane_index % 2 == 1:
                start_x, end_x = end_x, start_x

            segment = [
                _xy_to_gps(start_x, scan_y, origin_lat, origin_lon, latitude_scale),
                _xy_to_gps(end_x, scan_y, origin_lat, origin_lon, latitude_scale),
            ]
            segments.append(segment)

    if not segments:
        raise ValueError("Không tạo được làn quét bên trong polygon.")

    return {
        "spacing_m": round(lane_spacing, 2),
        "lane_count": lane_count,
        "segments": segments,
    }


def _validate_spacing(spacing_m):
    if isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)):
        raise ValueError("Khoảng cách quét phải là một số tính bằng mét.")
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("Khoảng cách quét phải lớn hơn 0 mét.")


def _validate_and_project_polygon(coordinates):
    if not isinstance(coordinates, list) or len(coordinates) < 3:
        raise ValueError("Cần ít nhất 3 điểm để tạo polygon.")

    origin_lat, origin_lon = _get_origin(coordinates)
    latitude_scale = math.cos(math.radians(origin_lat))
    if abs(latitude_scale) < 1e-6:
        raise ValueError("Phép chiếu hiện tại không phù hợp gần vùng cực.")

    polygon = []
    for index, point in enumerate(coordinates, start=1):
        if not isinstance(point, dict) or set(point) != {"lat", "lon"}:
            raise ValueError(f"Điểm {index} phải có đúng hai trường lat và lon.")

        latitude = point["lat"]
        longitude = point["lon"]
        if (isinstance(latitude, bool) or isinstance(longitude, bool)
                or not isinstance(latitude, (int, float))
                or not isinstance(longitude, (int, float))):
            raise ValueError(f"Tọa độ điểm {index} phải là số.")
        if (not math.isfinite(latitude) or not math.isfinite(longitude)
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180):
            raise ValueError(f"Tọa độ điểm {index} nằm ngoài giới hạn GPS.")

        x = (math.radians(longitude - origin_lon)
             * EARTH_RADIUS_M * latitude_scale)
        y = math.radians(latitude - origin_lat) * EARTH_RADIUS_M
        polygon.append((x, y))

    if _distance_squared(polygon[0], polygon[-1]) <= COORDINATE_EPSILON ** 2:
        polygon.pop()
    if len(polygon) < 3:
        raise ValueError("Polygon cần ít nhất 3 đỉnh khác nhau.")

    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        if _distance_squared(point, next_point) <= COORDINATE_EPSILON ** 2:
            raise ValueError("Polygon không được có hai đỉnh liên tiếp trùng nhau.")

    if abs(_signed_area(polygon)) <= COORDINATE_EPSILON:
        raise ValueError("Các điểm tạo thành polygon có diện tích bằng 0.")

    _validate_no_self_intersections(polygon)
    return polygon


def _get_origin(coordinates):
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("Không có tọa độ để tính gốc bản đồ.")

    try:
        latitudes = [point["lat"] for point in coordinates]
        longitudes = [point["lon"] for point in coordinates]
    except (TypeError, KeyError):
        raise ValueError("Mỗi điểm cần có trường lat và lon.") from None

    return sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes)


def _get_scan_intervals(polygon, scan_y):
    intersections = []
    for index, first in enumerate(polygon):
        second = polygon[(index + 1) % len(polygon)]
        x1, y1 = first
        x2, y2 = second

        # Nửa kín theo trục Y giúp không đếm đỉnh polygon hai lần.
        crosses_scanline = (y1 <= scan_y < y2) or (y2 <= scan_y < y1)
        if crosses_scanline:
            fraction = (scan_y - y1) / (y2 - y1)
            intersections.append(x1 + fraction * (x2 - x1))

    intersections.sort()
    intervals = []
    for index in range(0, len(intersections) - 1, 2):
        start_x = intersections[index]
        end_x = intersections[index + 1]
        if end_x - start_x > COORDINATE_EPSILON:
            intervals.append((start_x, end_x))

    return intervals


def _xy_to_gps(x, y, origin_lat, origin_lon, latitude_scale):
    latitude = origin_lat + math.degrees(y / EARTH_RADIUS_M)
    longitude = origin_lon + math.degrees(
        x / (EARTH_RADIUS_M * latitude_scale)
    )
    return {"lat": round(latitude, 7), "lon": round(longitude, 7)}


def _signed_area(polygon):
    area = 0.0
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        area += x1 * y2 - x2 * y1
    return area / 2


def _validate_no_self_intersections(polygon):
    edge_count = len(polygon)
    for first_index in range(edge_count):
        first_start = polygon[first_index]
        first_end = polygon[(first_index + 1) % edge_count]

        for second_index in range(first_index + 1, edge_count):
            # Hai cạnh kề nhau được phép gặp nhau tại đỉnh chung.
            if (second_index == first_index + 1
                    or (first_index == 0 and second_index == edge_count - 1)):
                continue

            second_start = polygon[second_index]
            second_end = polygon[(second_index + 1) % edge_count]
            if _segments_intersect(
                    first_start, first_end, second_start, second_end):
                raise ValueError("Polygon tự giao cắt; hãy chọn lại các điểm.")


def _segments_intersect(first_start, first_end, second_start, second_end):
    orientation_1 = _orientation(first_start, first_end, second_start)
    orientation_2 = _orientation(first_start, first_end, second_end)
    orientation_3 = _orientation(second_start, second_end, first_start)
    orientation_4 = _orientation(second_start, second_end, first_end)

    if (orientation_1 * orientation_2 < 0
            and orientation_3 * orientation_4 < 0):
        return True

    return (
        (orientation_1 == 0 and _point_on_segment(
            second_start, first_start, first_end))
        or (orientation_2 == 0 and _point_on_segment(
            second_end, first_start, first_end))
        or (orientation_3 == 0 and _point_on_segment(
            first_start, second_start, second_end))
        or (orientation_4 == 0 and _point_on_segment(
            first_end, second_start, second_end))
    )


def _orientation(first, second, third):
    value = ((second[0] - first[0]) * (third[1] - first[1])
             - (second[1] - first[1]) * (third[0] - first[0]))
    if abs(value) <= COORDINATE_EPSILON:
        return 0
    return 1 if value > 0 else -1


def _point_on_segment(point, start, end):
    return (
        min(start[0], end[0]) - COORDINATE_EPSILON
        <= point[0]
        <= max(start[0], end[0]) + COORDINATE_EPSILON
        and min(start[1], end[1]) - COORDINATE_EPSILON
        <= point[1]
        <= max(start[1], end[1]) + COORDINATE_EPSILON
    )


def _distance_squared(first, second):
    return (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2
