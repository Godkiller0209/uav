"""Cửa sổ chính và điều hướng giữa các trang của ứng dụng UAV SAR."""

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .map_page import MapPage
from .uav_page import UavPage


class GPSMap(QWidget):
    """Khung ứng dụng gồm thanh điều hướng và các trang chức năng."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("UAV Search & Rescue")
        self.setMinimumSize(1050, 680)
        self.resize(1280, 820)
        self.setStyleSheet(
            "QWidget { background: #081322; color: #edf4ff; "
            "font-family: 'Segoe UI', Arial; }"
        )

        self._create_pages()
        self._create_layout()
        self._connect_navigation()
        self.show_map_page()

    def _create_pages(self):
        self.map_page = MapPage(self)
        self.map_view = self.map_page.map_view
        self.bridge = self.map_page.bridge
        self.uav_page = UavPage(self)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        self.pages.addWidget(self.map_page)
        self.pages.addWidget(self.uav_page)

    def _create_layout(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QWidget(self)
        header.setFixedHeight(54)
        header.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #0d1a2d, stop:1 #142743); "
            "border-bottom: 1px solid #29415f;"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 0, 20, 0)
        brand = QLabel("🧭  UAV Search & Rescue")
        brand.setStyleSheet("font-size: 18px; font-weight: 700; border: 0;")
        connection_status = QLabel("●  Chưa kết nối UAV")
        connection_status.setStyleSheet(
            "color: #d6e3f5; font-size: 13px; border: 0;"
        )
        header_layout.addWidget(brand)
        header_layout.addStretch(1)
        header_layout.addWidget(connection_status)
        root_layout.addWidget(header)

        body = QWidget(self)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        sidebar = self._create_sidebar(body)
        body_layout.addWidget(sidebar)
        body_layout.addWidget(self.pages, 1)
        root_layout.addWidget(body, 1)

    def _create_sidebar(self, parent):
        sidebar = QWidget(parent)
        sidebar.setFixedWidth(100)
        sidebar.setStyleSheet(
            "background: #0e1d31; border-right: 1px solid #263d5c;"
        )

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 14, 8, 12)
        layout.setSpacing(7)

        logo = QLabel("🚁\nUAV SAR")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            "color: #9db0c9; font-size: 13px; font-weight: 700; "
            "line-height: 1.3; border: 0; padding-bottom: 10px;"
        )
        layout.addWidget(logo)

        self.map_nav_button = self._make_nav_button("📍\nBản đồ", sidebar)
        self.uav_nav_button = self._make_nav_button("🚁\nUAV", sidebar)
        layout.addWidget(self.map_nav_button)
        layout.addWidget(self.uav_nav_button)

        for label in (
            "▤\nKế hoạch",
            "👥\nPhân nhiệm vụ",
            "▥\nGiám sát",
            "▤\nNhật ký",
            "⚙\nCài đặt",
        ):
            future_button = self._make_nav_button(label, sidebar)
            future_button.setEnabled(False)
            future_button.setStyleSheet(
                "QPushButton { color: #71839b; background: transparent; "
                "border: 1px solid transparent; border-radius: 9px; "
                "font-size: 11px; padding: 7px 4px; }"
            )
            layout.addWidget(future_button)

        layout.addStretch(1)
        return sidebar

    @staticmethod
    def _make_nav_button(text, parent):
        button = QPushButton(text, parent)
        button.setCheckable(True)
        button.setMinimumHeight(48)
        button.setStyleSheet(
            "QPushButton { color: #c5d2e4; background: transparent; "
            "border: 1px solid transparent; border-radius: 9px; "
            "font-size: 12px; padding: 7px 4px; }"
            "QPushButton:hover { background: #172a45; }"
            "QPushButton:checked { color: white; border-color: #1769d2; "
            "background: #1769d2; font-weight: 700; }"
        )
        return button

    def _connect_navigation(self):
        self.map_nav_button.clicked.connect(self.show_map_page)
        self.uav_nav_button.clicked.connect(self.show_uav_page)

    def show_map_page(self):
        self.pages.setCurrentWidget(self.map_page)
        self.map_nav_button.setChecked(True)
        self.uav_nav_button.setChecked(False)
        QTimer.singleShot(
            100,
            lambda: self.map_view.page().runJavaScript(
                "if (window.invalidateMapSize) window.invalidateMapSize();"
            ),
        )

    def show_uav_page(self):
        self.pages.setCurrentWidget(self.uav_page)
        self.map_nav_button.setChecked(False)
        self.uav_nav_button.setChecked(True)
