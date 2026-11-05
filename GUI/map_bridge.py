"""Cầu nối QWebChannel giữa bản đồ JavaScript và ứng dụng Python."""

import json
import math
from pathlib import Path
import uuid

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from mission.coverage_path import create_coverage_path
from mission.waypoint_store import delete_waypoints_for_area, save_waypoints


PROJECT_DIR = Path(__file__).resolve().parent.parent
SEARCH_AREAS_FILE = PROJECT_DIR / "data" / "search_areas.json"
LEGACY_SEARCH_AREA_FILE = PROJECT_DIR / "data" / "search_area.json"

SEARCH_AREAS_SCHEMA_VERSION = 1


class MapBridge(QObject):
    """Nhận, kiểm tra và lưu polygon do trang bản đồ gửi lên."""

    status_changed = pyqtSignal(str)
    search_areas_loaded = pyqtSignal(str)
    search_areas_saved = pyqtSignal(str)
    coverage_path_ready = pyqtSignal(str)

    @pyqtSlot()
    def load_search_areas(self):
        try:
            areas_document = self._read_search_areas()
            self._validate_search_areas(areas_document)
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as error:
            self.status_changed.emit(f"Không thể đọc khu vực đã lưu: {error}")
            areas_document = {
                "schema_version": SEARCH_AREAS_SCHEMA_VERSION,
                "areas": [],
            }

        self.search_areas_loaded.emit(
            json.dumps(areas_document, ensure_ascii=False)
        )

    @pyqtSlot(str)
    def save_search_areas(self, areas_json):
        try:
            areas_document = json.loads(areas_json)
            self._validate_search_areas(areas_document)

            SEARCH_AREAS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SEARCH_AREAS_FILE.write_text(
                json.dumps(areas_document, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as error:
            self.status_changed.emit(f"Không thể lưu các khu vực: {error}")
            return

        self.search_areas_saved.emit(
            json.dumps(areas_document, ensure_ascii=False)
        )
        self.status_changed.emit(
            f"Đã lưu {len(areas_document['areas'])} khu vực vào "
            "data/search_areas.json"
        )

    @pyqtSlot(str)
    def delete_waypoints_for_area(self, area_id):
        try:
            deleted_count = delete_waypoints_for_area(area_id)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            self.status_changed.emit(
                f"Không thể xóa waypoint của khu vực: {error}"
            )
            return

        if deleted_count:
            self.status_changed.emit(
                f"Đã xóa {deleted_count} tuyến waypoint của khu vực."
            )
        else:
            self.status_changed.emit(
                "Khu vực đã xóa không có tuyến waypoint đã lưu."
            )

    def _read_search_areas(self):
        if SEARCH_AREAS_FILE.exists():
            return json.loads(SEARCH_AREAS_FILE.read_text(encoding="utf-8"))

        if LEGACY_SEARCH_AREA_FILE.exists():
            legacy_coordinates = json.loads(
                LEGACY_SEARCH_AREA_FILE.read_text(encoding="utf-8")
            )
            self._validate_coordinates(legacy_coordinates)
            return {
                "schema_version": SEARCH_AREAS_SCHEMA_VERSION,
                "areas": [{
                    "id": f"area-{uuid.uuid4().hex[:8]}",
                    "name": "Khu vực 1",
                    "coordinates": legacy_coordinates,
                }],
            }

        return {
            "schema_version": SEARCH_AREAS_SCHEMA_VERSION,
            "areas": [],
        }

    @classmethod
    def _validate_search_areas(cls, document):
        if (not isinstance(document, dict)
                or set(document) != {"schema_version", "areas"}):
            raise ValueError("Dữ liệu cần có schema_version và areas.")
        if document["schema_version"] != SEARCH_AREAS_SCHEMA_VERSION:
            raise ValueError("Phiên bản dữ liệu khu vực không được hỗ trợ.")
        if not isinstance(document["areas"], list):
            raise ValueError("areas phải là một danh sách.")

        area_ids = set()
        for index, area in enumerate(document["areas"], start=1):
            if (not isinstance(area, dict)
                    or set(area) != {"id", "name", "coordinates"}):
                raise ValueError(
                    f"Khu vực {index} phải có id, name và coordinates."
                )
            if (not isinstance(area["id"], str) or not area["id"].strip()
                    or area["id"] in area_ids):
                raise ValueError(f"Mã khu vực {index} không hợp lệ hoặc bị trùng.")
            if not isinstance(area["name"], str) or not area["name"].strip():
                raise ValueError(f"Tên khu vực {index} không được để trống.")

            area_ids.add(area["id"])
            cls._validate_coordinates(area["coordinates"])

    @pyqtSlot(str, str, str, float, str)
    def generate_coverage_path(
            self, area_id, area_name, coordinates_json, spacing_m, uav_json):
        try:
            coordinates = json.loads(coordinates_json)
            uav_position = json.loads(uav_json)
            coverage_path = create_coverage_path(
                coordinates,
                spacing_m,
                uav_position,
                algorithm="zigzag",
            )
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            self.status_changed.emit(f"Không thể tạo đường quét: {error}")
            return

        self.coverage_path_ready.emit(
            json.dumps(coverage_path, ensure_ascii=False)
        )

        try:
            save_waypoints(
                area_id,
                area_name,
                "zigzag",
                coverage_path["spacing_m"],
                uav_position,
                coverage_path["waypoints"],
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            self.status_changed.emit(
                f"Đã tạo đường quét nhưng không lưu được waypoint: {error}"
            )
            return

        self.status_changed.emit(
            f"Đã tạo {coverage_path['lane_count']} làn quét, "
            f"{len(coverage_path['waypoints'])} waypoint, "
            f"khoảng cách {coverage_path['spacing_m']} m. "
            "Đã lưu vào data/waypoints.json."
        )

    @staticmethod
    def _validate_coordinates(coordinates):
        if not isinstance(coordinates, list) or len(coordinates) < 3:
            raise ValueError("Polygon cần có ít nhất 3 điểm.")

        for index, point in enumerate(coordinates, start=1):
            if not isinstance(point, dict) or set(point) != {"lat", "lon"}:
                raise ValueError(f"Điểm {index} phải có lat và lon.")

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
