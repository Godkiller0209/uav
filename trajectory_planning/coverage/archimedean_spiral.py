"""Sinh đường Archimedean Spiral và cắt nó theo một polygon GPS.

Tọa độ dùng phép chiếu equirectangular cục bộ, phù hợp cho khu vực SAR nhỏ.
Đường cong được lấy mẫu thành các đoạn ngắn, sau đó từng đoạn được cắt theo
polygon. Những phần rời nhau được giữ thành các segment riêng: module này
không tự tạo đường nối có thể đi ra ngoài khu vực.
"""

import math


EARTH_RADIUS_M = 6_371_000.0
_EPSILON_M = 1e-7
_MAX_CURVE_SAMPLES = 1_000_000
_MAX_COVERAGE_CELLS = 200_000


def create_archimedean_spiral(
        coordinates, spacing_m, initial_radius_m=0.0, center=None,
        footprint_width_m=None):
    """Tạo các đoạn quỹ đạo xoắn nằm trong polygon và chỉ số ước lượng.

    ``spacing_m`` là khoảng cách tâm giữa hai vòng liên tiếp. Với
    ``r = a + b*theta``, bán kính tăng ``2*pi*b`` sau một vòng nên
    ``b = spacing_m / (2*pi)``.

    ``footprint_width_m`` được xem là đường kính vùng quan sát tròn trên mặt
    đất, dùng để ước lượng Coverage Ratio. Giá trị này không thay đổi đường
    xoắn; người dùng nên chọn spacing không lớn hơn footprint.
    """
    _validate_positive_number(spacing_m, "Khoảng cách giữa các vòng")
    _validate_nonnegative_number(initial_radius_m, "Bán kính ban đầu")
    if footprint_width_m is not None:
        _validate_positive_number(footprint_width_m, "Footprint cảm biến")

    origin_lat, origin_lon, polygon = _project_polygon(coordinates)
    center_xy = _choose_center(polygon, center, origin_lat, origin_lon)
    radial_growth = spacing_m / (2.0 * math.pi)
    max_radius = max(math.hypot(x - center_xy[0], y - center_xy[1])
                     for x, y in polygon)

    if initial_radius_m > max_radius + spacing_m:
        raise ValueError(
            "Bán kính ban đầu lớn hơn khu vực; đường xoắn không thể đi vào polygon."
        )

    sample_step_m = min(1.0, max(0.1, spacing_m / 10.0))
    local_curve = _sample_spiral(
        center_xy, initial_radius_m, radial_growth, max_radius, sample_step_m
    )
    local_segments = _clip_curve_to_polygon(local_curve, polygon)
    if not local_segments:
        raise ValueError("Đường xoắn không giao với phần bên trong polygon.")

    segments = []
    for segment in local_segments:
        points = []
        for x, y in segment:
            gps = _unproject_point(x, y, origin_lat, origin_lon)
            points.append({
                "x_m": round(x, 8),
                "y_m": round(y, 8),
                "lat": round(gps[0], 7),
                "lon": round(gps[1], 7),
            })
        if len(points) >= 2:
            segments.append(points)

    path_length_m = sum(
        _polyline_length(segment) for segment in local_segments
    )
    turning_behavior = _measure_turning(local_segments)
    coverage_ratio, resolution = _estimate_coverage(
        polygon, local_segments, footprint_width_m
    )
    center_gps = _unproject_point(
        center_xy[0], center_xy[1], origin_lat, origin_lon
    )

    return {
        "algorithm": "archimedean_spiral",
        "local_frame_origin": {
            "lat": origin_lat,
            "lon": origin_lon,
        },
        "center": {"lat": round(center_gps[0], 7),
                   "lon": round(center_gps[1], 7)},
        "spiral_spacing_m": float(spacing_m),
        "initial_radius_m": float(initial_radius_m),
        "radial_growth_m_per_rad": radial_growth,
        "theoretical_turn_spacing_m": 2.0 * math.pi * radial_growth,
        "footprint_width_m": footprint_width_m,
        "coverage_ratio": coverage_ratio,
        "coverage_estimation_resolution_m": resolution,
        "path_length_m": path_length_m,
        "turning_behavior": turning_behavior,
        "boundary_violation_m": 0.0,
        "discontinuity_count": max(0, len(segments) - 1),
        "segments": segments,
        "sample_step_m": sample_step_m,
        "projection": "local_equirectangular",
    }


def _sample_spiral(center, initial_radius, radial_growth, max_radius, step_m):
    curve = []
    theta = 0.0
    max_theta = max(0.0, (max_radius + step_m - initial_radius) / radial_growth)
    while theta <= max_theta:
        radius = initial_radius + radial_growth * theta
        curve.append((center[0] + radius * math.cos(theta),
                      center[1] + radius * math.sin(theta)))
        if len(curve) > _MAX_CURVE_SAMPLES:
            raise ValueError(
                "Tham số tạo ra quá nhiều điểm mẫu; hãy tăng spiral spacing."
            )
        local_speed = max(radius, radial_growth, step_m)
        theta += min(0.1, step_m / local_speed)
    return curve


def _clip_curve_to_polygon(curve, polygon):
    segments = []
    active = []
    for start, end in zip(curve, curve[1:]):
        cuts = [0.0, 1.0]
        for edge_start, edge_end in _edges(polygon):
            parameter = _segment_intersection_parameter(
                start, end, edge_start, edge_end
            )
            if parameter is not None:
                cuts.append(parameter)
        cuts = _unique_sorted(cuts)
        for lower, upper in zip(cuts, cuts[1:]):
            if upper - lower <= 1e-12:
                continue
            midpoint = _interpolate(start, end, (lower + upper) / 2.0)
            if _point_in_polygon(midpoint, polygon):
                inside_start = _interpolate(start, end, lower)
                inside_end = _interpolate(start, end, upper)
                if not active:
                    active = [inside_start]
                elif _distance(active[-1], inside_start) > _EPSILON_M:
                    segments.append(active)
                    active = [inside_start]
                active.append(inside_end)
            elif active:
                segments.append(active)
                active = []
        if cuts and not _point_in_polygon(end, polygon) and active:
            segments.append(active)
            active = []
    if active:
        segments.append(active)
    return [_remove_consecutive_duplicates(segment) for segment in segments
            if len(segment) >= 2]


def _project_polygon(coordinates):
    if not isinstance(coordinates, list) or len(coordinates) < 3:
        raise ValueError("Polygon cần ít nhất 3 điểm.")
    for index, point in enumerate(coordinates, start=1):
        _validate_gps_point(point, f"Đỉnh {index}")
    origin_lat = sum(point["lat"] for point in coordinates) / len(coordinates)
    origin_lon = sum(point["lon"] for point in coordinates) / len(coordinates)
    latitude_scale = math.cos(math.radians(origin_lat))
    if abs(latitude_scale) < 1e-6:
        raise ValueError("Phép chiếu cục bộ hiện tại không phù hợp gần vùng cực.")
    polygon = [
        (math.radians(point["lon"] - origin_lon) * EARTH_RADIUS_M
         * latitude_scale,
         math.radians(point["lat"] - origin_lat) * EARTH_RADIUS_M)
        for point in coordinates
    ]
    if _distance(polygon[0], polygon[-1]) <= _EPSILON_M:
        polygon.pop()
    if len(polygon) < 3:
        raise ValueError("Polygon cần ít nhất 3 đỉnh khác nhau.")
    for first, second in _edges(polygon):
        if _distance(first, second) <= _EPSILON_M:
            raise ValueError("Polygon có hai đỉnh liên tiếp trùng nhau.")
    _validate_simple_polygon(polygon)
    if abs(_signed_area(polygon)) <= _EPSILON_M:
        raise ValueError("Polygon suy biến hoặc có diện tích bằng 0.")
    return origin_lat, origin_lon, polygon


def _choose_center(polygon, center, origin_lat, origin_lon):
    if center is not None:
        _validate_gps_point(center, "Tâm xoắn ốc")
        lat_scale = math.cos(math.radians(origin_lat))
        point = (math.radians(center["lon"] - origin_lon) * EARTH_RADIUS_M
                 * lat_scale,
                 math.radians(center["lat"] - origin_lat) * EARTH_RADIUS_M)
        if not _point_in_polygon(point, polygon):
            raise ValueError("Tâm xoắn ốc phải nằm bên trong polygon.")
        return point

    area_twice = 2.0 * _signed_area(polygon)
    centroid_x = sum((a[0] + b[0]) * (a[0] * b[1] - b[0] * a[1])
                     for a, b in _edges(polygon)) / (3.0 * area_twice)
    centroid_y = sum((a[1] + b[1]) * (a[0] * b[1] - b[0] * a[1])
                     for a, b in _edges(polygon)) / (3.0 * area_twice)
    if _point_in_polygon((centroid_x, centroid_y), polygon):
        return centroid_x, centroid_y

    # Centroid của polygon lõm có thể nằm ngoài. Chọn điểm lưới bên trong có
    # khoảng cách tới biên lớn nhất, thay vì dùng tâm ngoài khu vực.
    min_x, max_x = min(p[0] for p in polygon), max(p[0] for p in polygon)
    min_y, max_y = min(p[1] for p in polygon), max(p[1] for p in polygon)
    best_point = None
    best_clearance = -1.0
    grid_count = 40
    for row in range(grid_count + 1):
        y = min_y + (max_y - min_y) * row / grid_count
        for column in range(grid_count + 1):
            x = min_x + (max_x - min_x) * column / grid_count
            candidate = (x, y)
            if _point_in_polygon(candidate, polygon):
                clearance = min(_point_segment_distance(candidate, a, b)
                                for a, b in _edges(polygon))
                if clearance > best_clearance:
                    best_point, best_clearance = candidate, clearance
    if best_point is None:
        raise ValueError("Không tìm được điểm bên trong polygon làm tâm xoắn.")
    return best_point


def _estimate_coverage(polygon, segments, footprint_width):
    if footprint_width is None:
        return None, None
    min_x, max_x = min(p[0] for p in polygon), max(p[0] for p in polygon)
    min_y, max_y = min(p[1] for p in polygon), max(p[1] for p in polygon)
    area_box = max(0.0, (max_x - min_x) * (max_y - min_y))
    if area_box <= 0:
        return 0.0, None
    resolution = min(1.0, footprint_width / 4.0)
    cells = max(1, math.ceil((max_x - min_x) / resolution)) * max(
        1, math.ceil((max_y - min_y) / resolution)
    )
    if cells > _MAX_COVERAGE_CELLS:
        resolution *= math.sqrt(cells / _MAX_COVERAGE_CELLS)
    columns = max(1, math.ceil((max_x - min_x) / resolution))
    rows = max(1, math.ceil((max_y - min_y) / resolution))
    # Chia các đoạn vào ô không gian để mỗi điểm kiểm tra chỉ xét các đoạn
    # ở gần nó, thay vì so với toàn bộ mẫu quỹ đạo.
    bucket_size = max(footprint_width, resolution * 4.0)
    segment_buckets = {}
    for segment in segments:
        for start, end in zip(segment, segment[1:]):
            first_column = math.floor((min(start[0], end[0]) - min_x)
                                      / bucket_size)
            last_column = math.floor((max(start[0], end[0]) - min_x)
                                     / bucket_size)
            first_row = math.floor((min(start[1], end[1]) - min_y)
                                   / bucket_size)
            last_row = math.floor((max(start[1], end[1]) - min_y)
                                  / bucket_size)
            for bucket_row in range(first_row, last_row + 1):
                for bucket_column in range(first_column, last_column + 1):
                    segment_buckets.setdefault(
                        (bucket_column, bucket_row), []
                    ).append((start, end))
    inside_count = covered_count = 0
    radius_squared = (footprint_width / 2.0) ** 2
    for row in range(rows):
        y = min_y + (row + 0.5) * (max_y - min_y) / rows
        for column in range(columns):
            x = min_x + (column + 0.5) * (max_x - min_x) / columns
            point = (x, y)
            if not _point_in_polygon(point, polygon):
                continue
            inside_count += 1
            bucket_column = math.floor((x - min_x) / bucket_size)
            bucket_row = math.floor((y - min_y) / bucket_size)
            nearby_segments = (
                edge
                for row_offset in (-1, 0, 1)
                for column_offset in (-1, 0, 1)
                for edge in segment_buckets.get(
                    (bucket_column + column_offset, bucket_row + row_offset), []
                )
            )
            if any(_point_segment_distance_squared(point, start, end)
                   <= radius_squared for start, end in nearby_segments):
                covered_count += 1
    return (covered_count / inside_count if inside_count else 0.0), resolution


def _validate_simple_polygon(polygon):
    edges = list(_edges(polygon))
    count = len(edges)
    for first_index, (a, b) in enumerate(edges):
        for second_index in range(first_index + 1, count):
            if second_index in (first_index, first_index + 1):
                continue
            if first_index == 0 and second_index == count - 1:
                continue
            c, d = edges[second_index]
            if _segments_intersect(a, b, c, d):
                raise ValueError("Polygon tự giao nhau, không thể tạo quỹ đạo.")


def _segments_intersect(a, b, c, d):
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    return ((o1 * o2 < 0 and o3 * o4 < 0)
            or abs(o1) <= _EPSILON_M and _on_segment(a, b, c)
            or abs(o2) <= _EPSILON_M and _on_segment(a, b, d)
            or abs(o3) <= _EPSILON_M and _on_segment(c, d, a)
            or abs(o4) <= _EPSILON_M and _on_segment(c, d, b))


def _segment_intersection_parameter(p, p2, q, q2):
    rx, ry = p2[0] - p[0], p2[1] - p[1]
    sx, sy = q2[0] - q[0], q2[1] - q[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) <= 1e-12:
        return None
    qpx, qpy = q[0] - p[0], q[1] - p[1]
    t = (qpx * sy - qpy * sx) / denominator
    u = (qpx * ry - qpy * rx) / denominator
    if -1e-12 <= t <= 1.0 + 1e-12 and -1e-12 <= u <= 1.0 + 1e-12:
        return min(1.0, max(0.0, t))
    return None


def _point_in_polygon(point, polygon):
    inside = False
    x, y = point
    for start, end in _edges(polygon):
        if _point_segment_distance(point, start, end) <= _EPSILON_M:
            return True
        x1, y1 = start
        x2, y2 = end
        if (y1 > y) != (y2 > y):
            crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing_x:
                inside = not inside
    return inside


def _point_segment_distance_squared(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-20:
        return _distance_squared(point, start)
    parameter = max(0.0, min(1.0, ((point[0] - start[0]) * dx
                                   + (point[1] - start[1]) * dy)
                                  / length_squared))
    projection = (start[0] + parameter * dx, start[1] + parameter * dy)
    return _distance_squared(point, projection)


def _point_segment_distance(point, start, end):
    return math.sqrt(_point_segment_distance_squared(point, start, end))


def _orientation(a, b, c):
    return ((b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0]))


def _on_segment(a, b, point):
    return (min(a[0], b[0]) - _EPSILON_M <= point[0]
            <= max(a[0], b[0]) + _EPSILON_M
            and min(a[1], b[1]) - _EPSILON_M <= point[1]
            <= max(a[1], b[1]) + _EPSILON_M)


def _validate_gps_point(point, label):
    if not isinstance(point, dict) or not {"lat", "lon"}.issubset(point):
        raise ValueError(f"{label} cần có lat và lon.")
    lat, lon = point["lat"], point["lon"]
    if (isinstance(lat, bool) or isinstance(lon, bool)
            or not isinstance(lat, (int, float))
            or not isinstance(lon, (int, float))
            or not math.isfinite(lat) or not math.isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        raise ValueError(f"Tọa độ GPS của {label} không hợp lệ.")


def _validate_positive_number(value, label):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ValueError(f"{label} phải là số lớn hơn 0.")


def _validate_nonnegative_number(value, label):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError(f"{label} phải là số không âm.")


def _unproject_point(x, y, origin_lat, origin_lon):
    latitude = origin_lat + math.degrees(y / EARTH_RADIUS_M)
    longitude = origin_lon + math.degrees(
        x / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat)))
    )
    return latitude, longitude


def _polyline_length(points):
    return sum(_distance(a, b) for a, b in zip(points, points[1:]))


def _measure_turning(segments):
    total_heading_change = 0.0
    maximum_curvature = 0.0
    for segment in segments:
        for previous, current, following in zip(
                segment, segment[1:], segment[2:]):
            incoming = (current[0] - previous[0], current[1] - previous[1])
            outgoing = (following[0] - current[0], following[1] - current[1])
            incoming_length = math.hypot(*incoming)
            outgoing_length = math.hypot(*outgoing)
            if incoming_length <= _EPSILON_M or outgoing_length <= _EPSILON_M:
                continue
            incoming_heading = math.atan2(incoming[1], incoming[0])
            outgoing_heading = math.atan2(outgoing[1], outgoing[0])
            change = abs((outgoing_heading - incoming_heading + math.pi)
                         % (2.0 * math.pi) - math.pi)
            total_heading_change += change
            average_step = (incoming_length + outgoing_length) / 2.0
            maximum_curvature = max(maximum_curvature, change / average_step)
    return {
        "absolute_heading_change_rad": total_heading_change,
        "maximum_curvature_per_m": maximum_curvature,
    }


def _signed_area(polygon):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in _edges(polygon)) / 2.0


def _edges(points):
    return ((points[index], points[(index + 1) % len(points)])
            for index in range(len(points)))


def _unique_sorted(values):
    result = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > 1e-10:
            result.append(value)
    return result


def _interpolate(start, end, fraction):
    return (start[0] + (end[0] - start[0]) * fraction,
            start[1] + (end[1] - start[1]) * fraction)


def _distance_squared(first, second):
    return (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2


def _distance(first, second):
    return math.sqrt(_distance_squared(first, second))


def _remove_consecutive_duplicates(points):
    result = []
    for point in points:
        if not result or _distance(result[-1], point) > _EPSILON_M:
            result.append(point)
    return result
