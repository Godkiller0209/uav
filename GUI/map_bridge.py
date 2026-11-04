"""Cầu nối QWebChannel giữa bản đồ JavaScript và ứng dụng Python."""

import json
import math
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from mission.coverage_path import create_coverage_path


PROJECT_DIR = Path(__file__).resolve().parent.parent
SEARCH_AREA_FILE = PROJECT_DIR / "data" / "search_area.json"


class MapBridge(QObject):
    """Nhận, kiểm tra và lưu polygon do trang bản đồ gửi lên."""

    status_changed = pyqtSignal(str)
    coverage_path_ready = pyqtSignal(str)

    @pyqtSlot(str, float)
    def generate_coverage_path(self, coordinates_json, spacing_m):
        try:
            coordinates = json.loads(coordinates_json)
            coverage_path = create_coverage_path(coordinates, spacing_m)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            self.status_changed.emit(f"Không thể tạo đường quét: {error}")
            return

        self.coverage_path_ready.emit(
            json.dumps(coverage_path, ensure_ascii=False)
        )
        self.status_changed.emit(
            f"Đã tạo {coverage_path['lane_count']} làn quét, "
            f"khoảng cách {coverage_path['spacing_m']} m."
        )

    @pyqtSlot(str)
    def save_search_area(self, coordinates_json):
        try:
            coordinates = json.loads(coordinates_json)
            self._validate_coordinates(coordinates)

            SEARCH_AREA_FILE.parent.mkdir(parents=True, exist_ok=True)
            SEARCH_AREA_FILE.write_text(
                json.dumps(coordinates, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except (json.JSONDecodeError, TypeError, ValueError, OSError) as error:
            self.status_changed.emit(f"Không thể lưu khu vực: {error}")
            return

        self.status_changed.emit(
            f"Đã lưu {len(coordinates)} điểm vào data/search_area.json"
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
