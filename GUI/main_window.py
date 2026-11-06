"""Cửa sổ chính của ứng dụng UAV SAR."""

from pathlib import Path

from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView

from .map_bridge import MapBridge


PROJECT_DIR = Path(__file__).resolve().parent.parent


class GPSMap(QWidget):
    """Hiển thị bản đồ tìm kiếm và trạng thái lưu khu vực."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("UAV Map GUI")
        self.resize(1280, 820)

        self.map_view = QWebEngineView()
        self.bridge = MapBridge()
        self.channel = QWebChannel(self.map_view.page())
        self.channel.registerObject("mapBridge", self.bridge)
        self.map_view.page().setWebChannel(self.channel)

        self.status_label = QLabel("Click trên bản đồ để thêm các điểm khu vực.")
        self.bridge.status_changed.connect(self.status_label.setText)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("UAV SEARCH AREA MAP"))
        layout.addWidget(self.map_view, 1)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        html_path = PROJECT_DIR / "assets" / "map.html"
        self.map_view.load(QUrl.fromLocalFile(str(html_path)))
