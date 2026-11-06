"""Trang bản đồ web và cầu nối giữa Leaflet với Python."""

from pathlib import Path

from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView

from .map_bridge import MapBridge


PROJECT_DIR = Path(__file__).resolve().parent.parent


class MapPage(QWidget):
    """Nạp giao diện HTML và thiết lập QWebChannel cho bản đồ."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.map_view = QWebEngineView(self)
        self.bridge = MapBridge()
        self.channel = QWebChannel(self.map_view.page())
        self.channel.registerObject("mapBridge", self.bridge)
        self.map_view.page().setWebChannel(self.channel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.map_view)

        html_path = PROJECT_DIR / "assets" / "map.html"
        self.map_view.load(QUrl.fromLocalFile(str(html_path)))
