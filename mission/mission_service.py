"""Đọc tuyến đã lưu, xác thực và tạo MissionPlan MAVSDK 4.x."""

import json
from importlib.metadata import PackageNotFoundError, version
import math
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
WAYPOINTS_FILE = PROJECT_DIR / "data" / "waypoints.json"
SEARCH_AREAS_FILE = PROJECT_DIR / "data" / "search_areas.json"
SUPPORTED_SCHEMA_VERSION = 2
DEFAULT_ALTITUDE_M = 20.0
DEFAULT_SPEED_M_S = 5.0
MAX_RELATIVE_ALTITUDE_M = 120.0
MAX_WAYPOINT_SPEED_M_S = 15.0
EARTH_RADIUS_M = 6_371_000.0


def load_latest_route(path=WAYPOINTS_FILE):
    """Nạp tuyến cuối cùng theo đúng schema v2, không ghi vào file nguồn."""
    source_path = Path(path)
    if not source_path.exists():
        raise ValueError(f"Không tìm thấy file waypoint: {source_path}")

    try:
        document = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Không đọc được waypoints.json: {error}") from error

    if (not isinstance(document, dict)
            or document.get("schema_version") != SUPPORTED_SCHEMA_VERSION):
        raise ValueError("Chỉ hỗ trợ waypoints.json có schema_version = 2.")
    routes = document.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("waypoints.json chưa có tuyến nào được lưu.")

    route = routes[-1]
    required_route_fields = {
        "area_ids", "areas", "algorithm", "spacing_m",
        "start_position", "waypoints",
    }
    if not isinstance(route, dict) or not required_route_fields.issubset(route):
        raise ValueError("Tuyến mới nhất thiếu trường theo schema v2.")
    if (not isinstance(route["area_ids"], list)
            or not isinstance(route["areas"], list)
            or not isinstance(route["start_position"], dict)):
        raise ValueError("Metadata khu vực hoặc vị trí bắt đầu không hợp lệ.")
    _validate_gps_point(route["start_position"], "Vị trí bắt đầu trong tuyến")
    if not isinstance(route["waypoints"], list) or not route["waypoints"]:
        raise ValueError("Tuyến mới nhất không có waypoint.")
    if not isinstance(route["areas"], list) or not route["areas"]:
        raise ValueError("Tuyến mới nhất không có thông tin khu vực.")

    waypoints = []
    for index, point in enumerate(route["waypoints"], start=1):
        _validate_gps_point(point, f"Waypoint {index}")
        # Đưa vào bản sao mới; không sửa route hoặc tài liệu JSON gốc.
        waypoints.append({"lat": float(point["lat"]), "lon": float(point["lon"])})

    expected_start = 1
    metadata_area_ids = []
    for area_index, area in enumerate(route["areas"], start=1):
        if not isinstance(area, dict):
            raise ValueError(f"Metadata khu vực {area_index} không hợp lệ.")
        if not {"area_id", "area_name"}.issubset(area):
            raise ValueError(f"Metadata khu vực {area_index} thiếu id hoặc tên.")
        metadata_area_ids.append(area["area_id"])
        try:
            waypoint_start = int(area["waypoint_start"])
            waypoint_end = int(area["waypoint_end"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"Metadata khu vực {area_index} thiếu khoảng waypoint."
            ) from None
        if waypoint_start != expected_start or waypoint_end < waypoint_start:
            raise ValueError(
                f"Khoảng waypoint của khu vực {area_index} không liên tục."
            )
        if waypoint_end > len(waypoints):
            raise ValueError(
                f"Khu vực {area_index} trỏ đến waypoint không tồn tại."
            )
        expected_start = waypoint_end + 1
    if expected_start - 1 != len(waypoints):
        raise ValueError("Metadata khu vực không khớp số waypoint trong tuyến.")
    if route["area_ids"] != metadata_area_ids:
        raise ValueError("area_ids không khớp metadata khu vực của tuyến.")

    return {
        "source_route": json.loads(json.dumps(route)),
        "waypoints": waypoints,
        "waypoint_count": len(waypoints),
        "source_path": str(source_path),
    }


def apply_default_settings(route_data, altitude_m=DEFAULT_ALTITUDE_M,
                           speed_m_s=DEFAULT_SPEED_M_S):
    """Tạo cấu hình Mission làm việc từ tuyến GPS chỉ có lat/lon."""
    if not math.isfinite(float(altitude_m)) or not (
            1.0 <= float(altitude_m) <= MAX_RELATIVE_ALTITUDE_M):
        raise ValueError(
            f"Độ cao tương đối phải từ 1 đến {MAX_RELATIVE_ALTITUDE_M:g} m."
        )
    if not math.isfinite(float(speed_m_s)) or not (
            0.5 <= float(speed_m_s) <= MAX_WAYPOINT_SPEED_M_S):
        raise ValueError(
            f"Tốc độ waypoint phải từ 0.5 đến {MAX_WAYPOINT_SPEED_M_S:g} m/s."
        )

    return {
        "source_route": route_data["source_route"],
        "source_path": route_data["source_path"],
        "end_action": "rtl",
        "max_start_distance_m": 500.0,
        "waypoints": [
            {
                **point,
                "relative_altitude_m": float(altitude_m),
                "speed_m_s": float(speed_m_s),
                "is_fly_through": True,
                "yaw_deg": None,
            }
            for point in route_data["waypoints"]
        ],
    }


def load_search_areas(path=SEARCH_AREAS_FILE):
    """Đọc polygon hiện có để chỉ cảnh báo đoạn nối đi ra ngoài khu vực."""
    source_path = Path(path)
    if not source_path.exists():
        return []
    try:
        document = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Không đọc được search_areas.json: {error}") from error
    if (not isinstance(document, dict)
            or document.get("schema_version") != 1
            or not isinstance(document.get("areas"), list)):
        raise ValueError("search_areas.json không đúng schema hiện tại.")
    for area_index, area in enumerate(document["areas"], start=1):
        if (not isinstance(area, dict)
                or not isinstance(area.get("id"), str)
                or not isinstance(area.get("coordinates"), list)):
            raise ValueError(f"Khu vực {area_index} trong search_areas.json lỗi.")
        for point_index, point in enumerate(area["coordinates"], start=1):
            _validate_gps_point(point, f"Khu vực {area_index}, điểm {point_index}")
    return document["areas"]


def validate_mission(mission_definition, telemetry=None, search_areas=None):
    """Trả về (errors, warnings); kiểm tra trạng thái, GPS, Mission và tuyến."""
    errors = []
    warnings = []
    if not isinstance(mission_definition, dict):
        return ["Cấu hình Mission chưa được tạo."], warnings

    waypoints = mission_definition.get("waypoints")
    if not isinstance(waypoints, list) or not waypoints:
        errors.append("Mission rỗng; cần ít nhất một waypoint.")
        return errors, warnings

    for index, point in enumerate(waypoints, start=1):
        try:
            _validate_gps_point(point, f"Waypoint {index}")
        except ValueError as error:
            errors.append(str(error))
            continue

        altitude = point.get("relative_altitude_m")
        speed = point.get("speed_m_s")
        if (isinstance(altitude, bool) or not isinstance(altitude, (int, float))
                or not math.isfinite(altitude)
                or not 1.0 <= altitude <= MAX_RELATIVE_ALTITUDE_M):
            errors.append(
                f"Waypoint {index}: độ cao tương đối phải từ 1 đến "
                f"{MAX_RELATIVE_ALTITUDE_M:g} m."
            )
        if (isinstance(speed, bool) or not isinstance(speed, (int, float))
                or not math.isfinite(speed)
                or not 0.5 <= speed <= MAX_WAYPOINT_SPEED_M_S):
            errors.append(
                f"Waypoint {index}: tốc độ phải từ 0.5 đến "
                f"{MAX_WAYPOINT_SPEED_M_S:g} m/s."
            )
        yaw = point.get("yaw_deg")
        if yaw is not None and (
                isinstance(yaw, bool) or not isinstance(yaw, (int, float))
                or not math.isfinite(yaw) or not -180.0 <= yaw <= 180.0):
            errors.append(f"Waypoint {index}: yaw phải từ -180 đến 180 độ.")

    if mission_definition.get("end_action") not in {"rtl", "land", "hold"}:
        errors.append("Hành động kết thúc Mission không hợp lệ.")

    if telemetry is not None:
        status_text = str(telemetry.get("px4_status_text", "")).lower()
        flight_mode = str(telemetry.get("flight_mode", "")).upper()
        if ("failsafe activated" in status_text
                or "failsafe active" in status_text
                or flight_mode == "TERMINATION"):
            errors.append(
                "PX4 đang báo Failsafe/Termination; không được Upload hoặc chạy Mission."
            )

    if telemetry is None:
        errors.append("Chưa có Telemetry từ UAV để kiểm tra pre-flight.")
    else:
        if not telemetry.get("connected"):
            errors.append("UAV chưa kết nối.")
        if not telemetry.get("health_global_ok"):
            errors.append("PX4 chưa xác nhận vị trí toàn cầu/GPS khỏe.")
        if not telemetry.get("health_home_ok"):
            errors.append("PX4 chưa xác nhận Home position.")
        gps_fix = telemetry.get("gps_fix")
        if gps_fix in {None, "NO_GPS", "NO_FIX", "UNKNOWN"}:
            errors.append("Chưa có GPS fix hợp lệ từ PX4.")
        if telemetry.get("in_air"):
            errors.append("Mission mới chỉ được kiểm tra/upload khi UAV ở mặt đất.")

        home = telemetry.get("home") or telemetry
        try:
            _validate_gps_point(home, "Home position")
            home_is_valid = True
        except ValueError as error:
            errors.append(str(error))
            home_is_valid = False

        if not home_is_valid:
            errors.append("Không đọc được Home position từ Telemetry.")
        elif waypoints and _point_is_valid(waypoints[0]):
            position = telemetry.get("position")
            if (not isinstance(position, dict)
                    or position.get("lat") is None
                    or position.get("lon") is None):
                position = telemetry if telemetry.get("lat") is not None else home
            try:
                _validate_gps_point(position, "Vị trí UAV hiện tại")
            except ValueError as error:
                errors.append(str(error))
            else:
                distance = _distance_m(position, waypoints[0])
                try:
                    threshold = float(
                        mission_definition.get("max_start_distance_m", 500.0)
                    )
                except (TypeError, ValueError):
                    threshold = float("nan")
                if not math.isfinite(threshold) or threshold <= 0:
                    errors.append("Ngưỡng khoảng cách waypoint đầu phải lớn hơn 0 m.")
                elif distance > threshold:
                    warnings.append(
                        f"Waypoint đầu cách vị trí UAV hiện tại {distance:.0f} m "
                        f"(ngưỡng cảnh báo {threshold:.0f} m). Kiểm tra khu vực "
                        "mô phỏng và tuyến trước khi Upload."
                    )

    warnings.extend(_check_transit_segments(
        mission_definition, search_areas or []
    ))
    return errors, warnings


def build_mission_plan(mission_definition):
    """Tạo MissionPlan của MAVSDK 4.x; không gửi dữ liệu lên UAV."""
    try:
        installed_version = version("mavsdk")
    except PackageNotFoundError as error:
        raise RuntimeError(
            "Chưa cài MAVSDK 4.0.6; cài bằng requirements.txt trước."
        ) from error
    if installed_version != "4.0.6":
        raise RuntimeError(
            f"MissionPlan cần MAVSDK 4.0.6, nhưng đang có {installed_version}."
        )

    try:
        from mavsdk.asyncio.plugins.mission import MissionItem, MissionPlan
    except ImportError as error:
        raise RuntimeError(
            "Cần MAVSDK 4.0.6 trong môi trường Python đang chạy. "
            "Cài bằng: python -m pip install -r requirements.txt"
        ) from error

    waypoints = mission_definition.get("waypoints", [])
    if not waypoints:
        raise ValueError("Không thể tạo MissionPlan rỗng.")

    for index, point in enumerate(waypoints, start=1):
        _validate_gps_point(point, f"Waypoint {index}")
        altitude = point.get("relative_altitude_m")
        speed = point.get("speed_m_s")
        if (isinstance(altitude, bool) or not isinstance(altitude, (int, float))
                or not math.isfinite(altitude)
                or not 1.0 <= altitude <= MAX_RELATIVE_ALTITUDE_M):
            raise ValueError(f"Waypoint {index}: độ cao tương đối không hợp lệ.")
        if (isinstance(speed, bool) or not isinstance(speed, (int, float))
                or not math.isfinite(speed)
                or not 0.5 <= speed <= MAX_WAYPOINT_SPEED_M_S):
            raise ValueError(f"Waypoint {index}: tốc độ không hợp lệ.")
        yaw = point.get("yaw_deg")
        if yaw is not None and (
                isinstance(yaw, bool) or not isinstance(yaw, (int, float))
                or not math.isfinite(yaw) or not -180 <= yaw <= 180):
            raise ValueError(f"Waypoint {index}: yaw không hợp lệ.")

    items = []
    for point in waypoints:
        item = MissionItem()
        item.latitude_deg = float(point["lat"])
        item.longitude_deg = float(point["lon"])
        item.relative_altitude_m = float(point["relative_altitude_m"])
        item.speed_m_s = float(point["speed_m_s"])
        item.is_fly_through = bool(point["is_fly_through"])
        item.yaw_deg = (
            float(point["yaw_deg"])
            if point.get("yaw_deg") is not None
            else float("nan")
        )
        item.acceptance_radius_m = 2.0
        item.gimbal_pitch_deg = float("nan")
        item.gimbal_yaw_deg = float("nan")
        item.loiter_time_s = 0.0
        item.camera_photo_interval_s = 1.0
        item.camera_photo_distance_m = 0.0
        item.camera_action = MissionItem.CameraAction.NONE
        item.vehicle_action = MissionItem.VehicleAction.NONE
        items.append(item)

    return MissionPlan(items)


def mission_signature(mission_definition):
    """Dấu nhận diện để từ chối khởi chạy nếu cấu hình đổi sau Upload."""
    return json.dumps(
        mission_definition,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_gps_point(point, label):
    if not isinstance(point, dict) or not {"lat", "lon"}.issubset(point):
        raise ValueError(f"{label} phải có lat và lon.")
    latitude = point["lat"]
    longitude = point["lon"]
    if (isinstance(latitude, bool) or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float))
            or not isinstance(longitude, (int, float))):
        raise ValueError(f"{label}: lat/lon phải là số.")
    if (not math.isfinite(latitude) or not math.isfinite(longitude)
            or not -90.0 <= latitude <= 90.0
            or not -180.0 <= longitude <= 180.0):
        raise ValueError(f"{label}: tọa độ nằm ngoài giới hạn GPS.")


def _point_is_valid(point):
    try:
        _validate_gps_point(point, "Waypoint")
        return True
    except ValueError:
        return False


def _distance_m(first, second):
    lat1 = math.radians(float(first["lat"]))
    lat2 = math.radians(float(second["lat"]))
    delta_lat = lat2 - lat1
    delta_lon = math.radians(float(second["lon"]) - float(first["lon"]))
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(haversine)))


def _check_transit_segments(mission_definition, search_areas):
    route = mission_definition.get("source_route", {})
    route_areas = route.get("areas", [])
    waypoints = mission_definition.get("waypoints", [])
    if any(not _point_is_valid(point) for point in waypoints):
        return [
            "Không thể kiểm tra đoạn chuyển tiếp vì có waypoint GPS không hợp lệ."
        ]
    if not route_areas or not search_areas:
        return [
            "Không tìm thấy polygon gốc để kiểm tra các đoạn chuyển tiếp; "
            "đã giữ nguyên waypoint và cần kiểm tra tuyến trực quan."
        ]

    polygon_by_id = {
        area.get("id"): area.get("coordinates", [])
        for area in search_areas
        if isinstance(area, dict) and isinstance(area.get("coordinates"), list)
    }
    waypoint_area = {}
    warnings = []
    for area in route_areas:
        area_id = area.get("area_id")
        try:
            first_index = int(area["waypoint_start"]) - 1
            last_index = int(area["waypoint_end"]) - 1
        except (KeyError, TypeError, ValueError):
            warnings.append("Metadata waypoint của một khu vực không đọc được.")
            continue
        if area_id not in polygon_by_id:
            warnings.append(
                f"Không còn polygon '{area.get('area_name', area_id)}' để "
                "kiểm tra các đoạn chuyển tiếp."
            )
            continue
        for index in range(first_index, min(last_index, len(waypoints) - 1) + 1):
            waypoint_area[index] = area_id

    for index in range(len(waypoints) - 1):
        first = waypoints[index]
        second = waypoints[index + 1]
        first_area_id = waypoint_area.get(index)
        second_area_id = waypoint_area.get(index + 1)
        if not first_area_id or not second_area_id:
            continue

        if first_area_id == second_area_id:
            polygons = [polygon_by_id.get(first_area_id, [])]
            area_name = next((
                area.get("area_name", first_area_id)
                for area in route_areas if area.get("area_id") == first_area_id
            ), first_area_id)
        else:
            polygons = [
                polygon_by_id.get(first_area_id, []),
                polygon_by_id.get(second_area_id, []),
            ]
            area_name = "các khu vực liền kề"

        distance = _distance_m(first, second)
        sample_count = max(2, int(math.ceil(distance / 5.0)))
        exits_polygon = False
        for sample_index in range(1, sample_count):
            fraction = sample_index / sample_count
            sample = {
                "lat": first["lat"] + (second["lat"] - first["lat"]) * fraction,
                "lon": first["lon"] + (second["lon"] - first["lon"]) * fraction,
            }
            if not any(_point_in_polygon(sample, polygon) for polygon in polygons):
                exits_polygon = True
                break
        if exits_polygon:
            warnings.append(
                f"Đoạn nối Waypoint {index + 1} → Waypoint {index + 2} có thể "
                f"đi ngoài polygon {area_name}; thuật toán Zigzag không bị thay đổi."
            )
    return warnings


def _point_in_polygon(point, polygon):
    if not isinstance(polygon, list) or len(polygon) < 3:
        return False
    x = float(point["lon"])
    y = float(point["lat"])
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = float(previous["lon"]), float(previous["lat"])
        x2, y2 = float(current["lon"]), float(current["lat"])
        crosses = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / (y2 - y1) + x1
        )
        if crosses:
            inside = not inside
        previous = current
    return inside
