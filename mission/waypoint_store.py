"""Lưu tuyến waypoint nhiều khu vực trong data/waypoints.json."""

import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
WAYPOINTS_FILE = PROJECT_DIR / "data" / "waypoints.json"
WAYPOINTS_SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1


def save_waypoints(
        areas, algorithm, spacing_m, start_position, waypoints):
    """Lưu tuyến tổng hợp mới nhất qua danh sách khu vực đã nhận."""
    document = _read_document()
    route = {
        "area_ids": [area["area_id"] for area in areas],
        "areas": areas,
        "algorithm": algorithm,
        "spacing_m": spacing_m,
        "start_position": start_position,
        "waypoints": waypoints,
    }

    document["schema_version"] = WAYPOINTS_SCHEMA_VERSION
    document["routes"] = [route]
    _write_document(document)


def remove_waypoint_routes_not_matching_areas(areas):
    """Xóa tuyến cũ nếu danh sách khu vực đã thay đổi."""
    if not WAYPOINTS_FILE.exists():
        return 0

    document = _read_document()
    current_area_keys = [
        (area["id"], area["name"])
        for area in areas
    ]
    remaining_routes = [
        route for route in document["routes"]
        if _get_route_area_keys(route) == current_area_keys
    ]
    removed_count = len(document["routes"]) - len(remaining_routes)

    if removed_count:
        document["routes"] = remaining_routes
        _write_document(document)

    return removed_count


def clear_saved_waypoints():
    """Xóa tuyến đã lưu, ví dụ khi vị trí bắt đầu UAV bị thay đổi."""
    if not WAYPOINTS_FILE.exists():
        return 0

    document = _read_document()
    removed_count = len(document["routes"])
    if removed_count:
        document["routes"] = []
        _write_document(document)
    return removed_count


def _get_route_area_keys(route):
    return [
        (area["area_id"], area["area_name"])
        for area in route["areas"]
    ]


def _read_document():
    if not WAYPOINTS_FILE.exists():
        return {
            "schema_version": WAYPOINTS_SCHEMA_VERSION,
            "routes": [],
        }

    document = json.loads(WAYPOINTS_FILE.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {
            "schema_version", "routes"}:
        raise ValueError("File waypoints.json không đúng định dạng hỗ trợ.")
    if not isinstance(document["routes"], list):
        raise ValueError("routes trong waypoints.json phải là một danh sách.")

    if document["schema_version"] == LEGACY_SCHEMA_VERSION:
        # Tuyến phiên bản cũ chỉ gắn với từng polygon riêng lẻ, không phải
        # một lộ trình liên tục qua toàn bộ các khu vực.
        migrated_document = {
            "schema_version": WAYPOINTS_SCHEMA_VERSION,
            "routes": [],
        }
        _write_document(migrated_document)
        return migrated_document
    if document["schema_version"] != WAYPOINTS_SCHEMA_VERSION:
        raise ValueError("Phiên bản waypoints.json không được hỗ trợ.")

    required_fields = {
        "area_ids",
        "areas",
        "algorithm",
        "spacing_m",
        "start_position",
        "waypoints",
    }
    for route in document["routes"]:
        if (not isinstance(route, dict)
                or not required_fields.issubset(route)
                or not isinstance(route["area_ids"], list)
                or not isinstance(route["areas"], list)
                or not isinstance(route["waypoints"], list)):
            raise ValueError("Một tuyến trong waypoints.json bị thiếu dữ liệu.")
        if any(not isinstance(area, dict)
               or not {"area_id", "area_name"}.issubset(area)
               for area in route["areas"]):
            raise ValueError("Thông tin khu vực trong waypoint không hợp lệ.")

    return document


def _write_document(document):
    WAYPOINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WAYPOINTS_FILE.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
