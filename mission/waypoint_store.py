"""Lưu và xóa tuyến waypoint trong data/waypoints.json."""

import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
WAYPOINTS_FILE = PROJECT_DIR / "data" / "waypoints.json"
WAYPOINTS_SCHEMA_VERSION = 1


def save_waypoints(
        area_id, area_name, algorithm, spacing_m, uav_position, waypoints):
    """Lưu hoặc cập nhật tuyến mới nhất cho khu vực và thuật toán đó."""
    document = _read_document()
    route = {
        "area_id": area_id,
        "area_name": area_name,
        "algorithm": algorithm,
        "spacing_m": spacing_m,
        "start_position": uav_position,
        "waypoints": waypoints,
    }

    document["routes"] = [
        saved_route
        for saved_route in document["routes"]
        if (saved_route.get("area_id"), saved_route.get("algorithm"))
        != (area_id, algorithm)
    ]
    document["routes"].append(route)

    WAYPOINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WAYPOINTS_FILE.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_waypoints_for_area(area_id):
    """Xóa mọi tuyến đã lưu thuộc khu vực; trả về số tuyến đã xóa."""
    if not WAYPOINTS_FILE.exists():
        return 0

    document = _read_document()
    remaining_routes = [
        route for route in document["routes"]
        if route["area_id"] != area_id
    ]
    deleted_count = len(document["routes"]) - len(remaining_routes)
    if deleted_count == 0:
        return 0

    document["routes"] = remaining_routes
    WAYPOINTS_FILE.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return deleted_count


def _read_document():
    if not WAYPOINTS_FILE.exists():
        return {
            "schema_version": WAYPOINTS_SCHEMA_VERSION,
            "routes": [],
        }

    document = json.loads(WAYPOINTS_FILE.read_text(encoding="utf-8"))
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "routes"}
            or document["schema_version"] != WAYPOINTS_SCHEMA_VERSION
            or not isinstance(document["routes"], list)):
        raise ValueError("File waypoints.json không đúng định dạng hỗ trợ.")

    required_fields = {
        "area_id",
        "area_name",
        "algorithm",
        "spacing_m",
        "start_position",
        "waypoints",
    }
    if any(not isinstance(route, dict)
           or not required_fields.issubset(route)
           for route in document["routes"]):
        raise ValueError("Một tuyến trong waypoints.json bị thiếu trường dữ liệu.")

    return document
