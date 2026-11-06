"""Trang UAV, hiện để trống cho đến khi triển khai kết nối và điều khiển."""

from PyQt5.QtWidgets import QWidget


class UavPage(QWidget):
    """Vùng nội dung dành cho các chức năng UAV trong tương lai."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("uavPage")
        self.setStyleSheet("QWidget#uavPage { background: #0d1b2e; }")
