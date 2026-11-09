"""Trang quản lý một UAV, Telemetry thật và Mission MAVSDK."""

from copy import deepcopy
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from drone.drone_client import DEFAULT_CONNECTION_URI, DroneClient
from mission.mission_service import (
    DEFAULT_ALTITUDE_M,
    DEFAULT_SPEED_M_S,
    MAX_RELATIVE_ALTITUDE_M,
    MAX_WAYPOINT_SPEED_M_S,
    apply_default_settings,
    load_latest_route,
    load_search_areas,
    mission_signature,
    validate_mission,
)


class UavPage(QWidget):
    """Giao diện UAV 1; MAVSDK chạy nền qua DroneClient."""

    connection_state_changed = pyqtSignal(bool, str)
    telemetry_updated = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("uavPage")
        self.setStyleSheet(
            "QWidget#uavPage { background: #0d1b2e; }"
            "QGroupBox { border: 1px solid #29415f; border-radius: 8px; "
            "margin-top: 10px; padding: 10px; font-weight: 700; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 5px; }"
            "QLineEdit, QDoubleSpinBox, QComboBox { background: #0d1a2c; "
            "border: 1px solid #304969; border-radius: 5px; padding: 6px; }"
            "QListWidget, QPlainTextEdit { background: #0b1728; "
            "border: 1px solid #263d5c; border-radius: 6px; }"
            "QPushButton { background: #1a2d48; border: 1px solid #385474; "
            "border-radius: 6px; padding: 7px 10px; }"
            "QPushButton:hover:enabled { background: #233b5d; }"
            "QPushButton:disabled { color: #71839b; background: #142238; }"
        )

        self._connected = False
        self._connecting = False
        self._telemetry_snapshot = {"connected": False}
        self._route_data = None
        self._mission_definition = None
        self._search_areas = []
        self._action_list_built = False
        self._mission_plan_ready = False
        self._mission_validated = False
        self._mission_uploaded = False
        self._uploaded_signature = None
        self._pending_plan_signature = None
        self._current_card = None

        self._create_ui()
        self._connect_signals()

        self.drone_client = DroneClient(self)
        self._connect_drone_signals()
        self.drone_client.start()
        self._refresh_controls()

    def _create_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        root.addWidget(self.scroll_area)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 8)
        content_layout.setSpacing(10)
        self.scroll_area.setWidget(content)

        title = QLabel("UAV 1 · PX4 SITL")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        content_layout.addWidget(title)

        content_layout.addWidget(self._create_connection_group())
        content_layout.addWidget(self._create_telemetry_group())
        content_layout.addWidget(self._create_manual_controls_group())
        content_layout.addWidget(self._create_mission_group(), 1)
        content_layout.addWidget(self._create_log_group())

    def _create_connection_group(self):
        group = QGroupBox("Kết nối UAV")
        layout = QVBoxLayout(group)

        row = QHBoxLayout()
        row.addWidget(QLabel("Connection URI"))
        self.connection_uri_input = QLineEdit(DEFAULT_CONNECTION_URI)
        self.connection_uri_input.setToolTip(
            "URI mặc định cho PX4 SITL. Có thể thay bằng URI MAVLink khác."
        )
        row.addWidget(self.connection_uri_input, 1)
        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        layout.addLayout(row)

        self.connection_status_label = QLabel("Disconnected · chưa có telemetry")
        self.connection_status_label.setWordWrap(True)
        self.connection_status_label.setStyleSheet("color: #ffcc80;")
        layout.addWidget(self.connection_status_label)
        return group

    def _create_telemetry_group(self):
        group = QGroupBox("Telemetry từ PX4 qua MAVSDK")
        grid = QGridLayout(group)
        self.telemetry_labels = {}
        fields = (
            ("Vị trí", "—"),
            ("Độ cao tương đối", "—"),
            ("Độ cao tuyệt đối", "—"),
            ("Ground speed", "—"),
            ("Pin", "—"),
            ("Trạng thái", "—"),
            ("Flight mode", "—"),
            ("GPS", "—"),
            ("Heading", "—"),
            ("PX4 status gần nhất", "—"),
        )
        for index, (name, initial_value) in enumerate(fields):
            row = index // 2
            column = (index % 2) * 2
            title = QLabel(f"{name}:")
            title.setStyleSheet("color: #9db0c9;")
            value = QLabel(initial_value)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            self.telemetry_labels[name] = value
            grid.addWidget(title, row, column)
            grid.addWidget(value, row, column + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        return group

    def _create_manual_controls_group(self):
        group = QGroupBox("Điều khiển thủ công · chỉ thử trên SITL")
        layout = QVBoxLayout(group)

        settings = QHBoxLayout()
        self.takeoff_altitude = self._make_spin_box(1, 120, DEFAULT_ALTITUDE_M, 1)
        self.takeoff_speed = self._make_spin_box(
            0.5, MAX_WAYPOINT_SPEED_M_S, DEFAULT_SPEED_M_S, 0.5
        )
        settings.addWidget(QLabel("Độ cao Takeoff (m)"))
        settings.addWidget(self.takeoff_altitude)
        settings.addWidget(QLabel("Tốc độ tối đa (m/s)"))
        settings.addWidget(self.takeoff_speed)
        settings.addStretch(1)
        layout.addLayout(settings)

        row = QHBoxLayout()
        self.arm_button = QPushButton("Arm")
        self.disarm_button = QPushButton("Disarm")
        self.takeoff_button = QPushButton("Takeoff")
        self.hold_button = QPushButton("Hold")
        self.rtl_button = QPushButton("RTL")
        self.land_button = QPushButton("Land")
        for button in (
                self.arm_button, self.disarm_button, self.takeoff_button,
                self.hold_button, self.rtl_button, self.land_button):
            row.addWidget(button)
        layout.addLayout(row)

        explanation = QLabel(
            "Hold yêu cầu PX4 chuyển sang giữ vị trí. Pause Mission dùng Mission API "
            "để tạm dừng tiến độ. RTL quay về Home; Land hạ cánh tại vị trí hiện tại."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet("color: #9db0c9; font-size: 11px;")
        layout.addWidget(explanation)
        return group

    def _create_mission_group(self):
        group = QGroupBox("Mission từ data/waypoints.json")
        layout = QVBoxLayout(group)

        buttons = QHBoxLayout()
        self.load_mission_button = QPushButton("1 · Load Mission")
        self.build_actions_button = QPushButton("2 · Build actions")
        self.create_plan_button = QPushButton("3 · Create MissionPlan")
        self.validate_mission_button = QPushButton("4 · Validate")
        self.upload_mission_button = QPushButton("5 · Upload")
        self.execute_mission_button = QPushButton("6 · Action / Execute")
        self.execute_mission_button.setStyleSheet(
            "QPushButton { background: #a83232; border-color: #d45b5b; "
            "font-weight: 700; }"
        )
        for button in (
                self.load_mission_button, self.build_actions_button,
                self.create_plan_button, self.validate_mission_button,
                self.upload_mission_button, self.execute_mission_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        settings_group = QGroupBox("Cấu hình Mission đang làm việc")
        settings = QGridLayout(settings_group)
        self.default_altitude = self._make_spin_box(
            1, MAX_RELATIVE_ALTITUDE_M, DEFAULT_ALTITUDE_M, 1
        )
        self.default_speed = self._make_spin_box(
            0.5, MAX_WAYPOINT_SPEED_M_S, DEFAULT_SPEED_M_S, 0.5
        )
        self.max_start_distance = self._make_spin_box(10, 5000, 500, 50)
        self.end_action = QComboBox()
        self.end_action.addItem("RTL về Home và hạ cánh theo PX4", "rtl")
        self.end_action.addItem("Land tại vị trí hiện tại sau Mission", "land")
        self.end_action.addItem("Hold tại điểm kết thúc", "hold")
        self.apply_defaults_button = QPushButton("Áp dụng độ cao/tốc độ mặc định cho tất cả")

        settings.addWidget(QLabel("Độ cao mặc định (m)"), 0, 0)
        settings.addWidget(self.default_altitude, 0, 1)
        settings.addWidget(QLabel("Tốc độ mặc định (m/s)"), 0, 2)
        settings.addWidget(self.default_speed, 0, 3)
        settings.addWidget(QLabel("Cảnh báo khoảng cách WP đầu (m)"), 1, 0)
        settings.addWidget(self.max_start_distance, 1, 1)
        settings.addWidget(QLabel("Kết thúc Mission"), 1, 2)
        settings.addWidget(self.end_action, 1, 3)
        settings.addWidget(self.apply_defaults_button, 2, 0, 1, 4)
        layout.addWidget(settings_group)

        self.mission_source_label = QLabel("Chưa nạp tuyến waypoint.")
        self.mission_source_label.setWordWrap(True)
        self.mission_status_label = QLabel("Mission chưa được tạo.")
        self.mission_status_label.setWordWrap(True)
        self.mission_progress_label = QLabel("Tiến độ: —")
        self.mission_progress_bar = QProgressBar()
        self.mission_progress_bar.setRange(0, 100)
        self.mission_progress_bar.setValue(0)
        self.mission_upload_status_label = QLabel("Upload: chưa gửi lên PX4")
        layout.addWidget(self.mission_source_label)
        layout.addWidget(self.mission_status_label)
        layout.addWidget(self.mission_progress_label)
        layout.addWidget(self.mission_progress_bar)
        layout.addWidget(self.mission_upload_status_label)

        splitter = QSplitter(Qt.Horizontal)
        self.action_cards = QListWidget()
        self.action_cards.setMinimumHeight(245)
        self.action_cards.setMinimumWidth(280)
        self.action_cards.setToolTip(
            "Thứ tự hành động. Mission waypoint giữ đúng thứ tự trong JSON."
        )
        splitter.addWidget(self.action_cards)

        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(4, 0, 0, 0)
        self.card_title = QLabel("Chọn một card để xem cấu hình")
        self.card_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        detail_layout.addWidget(self.card_title)
        self.card_description = QLabel(
            "Waypoint chỉ có lat/lon trong JSON; độ cao, tốc độ và tuỳ chọn bay "
            "được lưu trong cấu hình Mission hiện tại."
        )
        self.card_description.setWordWrap(True)
        self.card_description.setStyleSheet("color: #9db0c9;")
        detail_layout.addWidget(self.card_description)
        self.waypoint_form = QWidget()
        self.waypoint_form_layout = QFormLayout(self.waypoint_form)
        self.card_lat = self._make_spin_box(-90, 90, 0, 0.0000001)
        self.card_lat.setDecimals(7)
        self.card_lon = self._make_spin_box(-180, 180, 0, 0.0000001)
        self.card_lon.setDecimals(7)
        self.card_altitude = self._make_spin_box(
            1, MAX_RELATIVE_ALTITUDE_M, DEFAULT_ALTITUDE_M, 1
        )
        self.card_speed = self._make_spin_box(
            0.5, MAX_WAYPOINT_SPEED_M_S, DEFAULT_SPEED_M_S, 0.5
        )
        self.card_fly_through = QCheckBox("Bay xuyên qua, không dừng tại waypoint")
        self.card_yaw_enabled = QCheckBox("Đặt yaw (độ)")
        self.card_yaw = self._make_spin_box(-180, 180, 0, 5)
        self.save_waypoint_button = QPushButton("Lưu cấu hình waypoint vào Mission đang làm việc")
        self.waypoint_form_layout.addRow("Latitude", self.card_lat)
        self.waypoint_form_layout.addRow("Longitude", self.card_lon)
        self.waypoint_form_layout.addRow("Relative altitude (m)", self.card_altitude)
        self.waypoint_form_layout.addRow("Speed sau waypoint (m/s)", self.card_speed)
        self.waypoint_form_layout.addRow("", self.card_fly_through)
        self.waypoint_form_layout.addRow("", self.card_yaw_enabled)
        self.waypoint_form_layout.addRow("Yaw (độ)", self.card_yaw)
        self.waypoint_form_layout.addRow("", self.save_waypoint_button)
        self.waypoint_form.setVisible(False)
        detail_layout.addWidget(self.waypoint_form)
        detail_layout.addStretch(1)
        splitter.addWidget(details)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        end_controls = QHBoxLayout()
        self.pause_mission_button = QPushButton("Pause Mission")
        self.resume_mission_button = QPushButton("Resume Mission")
        end_controls.addWidget(self.pause_mission_button)
        end_controls.addWidget(self.resume_mission_button)
        end_controls.addStretch(1)
        layout.addLayout(end_controls)

        self.validation_output = QPlainTextEdit()
        self.validation_output.setReadOnly(True)
        self.validation_output.setMaximumBlockCount(100)
        self.validation_output.setPlaceholderText(
            "Kết quả kiểm tra, cảnh báo waypoint và đoạn chuyển tiếp sẽ hiện ở đây."
        )
        self.validation_output.setMaximumHeight(120)
        layout.addWidget(self.validation_output)
        return group

    def _create_log_group(self):
        group = QGroupBox("Log sự kiện UAV / PX4")
        layout = QVBoxLayout(group)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(1000)
        self.log_output.setMaximumHeight(150)
        layout.addWidget(self.log_output)
        return group

    @staticmethod
    def _make_spin_box(minimum, maximum, value, step):
        spin_box = QDoubleSpinBox()
        spin_box.setRange(float(minimum), float(maximum))
        spin_box.setValue(float(value))
        spin_box.setSingleStep(float(step))
        spin_box.setDecimals(1 if step >= 0.1 else 7)
        return spin_box

    def _connect_signals(self):
        self.connect_button.clicked.connect(self._connect_uav)
        self.disconnect_button.clicked.connect(self.drone_disconnect)
        self.arm_button.clicked.connect(
            lambda: self._confirm_and_call(
                "Arm UAV 1? Chỉ tiếp tục khi PX4 SITL/Gazebo đã sẵn sàng.",
                self.drone_client.arm if hasattr(self, "drone_client") else None,
            )
        )
        self.disarm_button.clicked.connect(self._confirm_disarm)
        self.takeoff_button.clicked.connect(self._confirm_takeoff)
        self.hold_button.clicked.connect(self._call_connected(self._hold))
        self.rtl_button.clicked.connect(self._confirm_rtl)
        self.land_button.clicked.connect(self._confirm_land)

        self.load_mission_button.clicked.connect(self._load_mission)
        self.build_actions_button.clicked.connect(self._build_actions)
        self.create_plan_button.clicked.connect(self._create_mission_plan)
        self.validate_mission_button.clicked.connect(self._validate_current_mission)
        self.upload_mission_button.clicked.connect(self._upload_mission)
        self.execute_mission_button.clicked.connect(self._confirm_execute_mission)
        self.apply_defaults_button.clicked.connect(self._apply_defaults_to_all)
        self.action_cards.currentItemChanged.connect(self._show_selected_card)
        self.save_waypoint_button.clicked.connect(self._save_selected_waypoint)
        self.card_yaw_enabled.toggled.connect(self.card_yaw.setEnabled)
        self.end_action.currentIndexChanged.connect(self._end_action_changed)

    def _connect_drone_signals(self):
        self.drone_client.connection_changed.connect(self._on_connection_changed)
        self.drone_client.telemetry_updated.connect(self._on_telemetry_updated)
        self.drone_client.log_message.connect(self._append_log)
        self.drone_client.operation_finished.connect(self._on_operation_finished)
        self.drone_client.mission_progress.connect(self._on_mission_progress)
        self.drone_client.mission_state_changed.connect(self._on_mission_state)

    def _connect_uav(self):
        if self._connecting or self._connected:
            return
        self._connecting = True
        self.connection_status_label.setText("Đang kết nối MAVSDK tới PX4 SITL…")
        self._refresh_controls()
        self.drone_client.connect_drone(self.connection_uri_input.text())

    def drone_disconnect(self):
        self.drone_client.disconnect_drone()

    def _confirm_and_call(self, message, callback):
        if callback is None:
            return
        answer = QMessageBox.question(
            self,
            "Xác nhận điều khiển UAV",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            callback()

    def _confirm_disarm(self):
        self._confirm_and_call(
            "Yêu cầu Disarm. Ứng dụng sẽ từ chối nếu Telemetry báo UAV đang bay.",
            self.drone_client.disarm,
        )

    def _confirm_takeoff(self):
        answer = QMessageBox.warning(
            self,
            "Xác nhận cất cánh SITL",
            "Takeoff sẽ điều khiển PX4 SITL cất cánh ngay. Hãy xác nhận môi trường "
            "đang là PX4 SITL + Gazebo, không phải UAV thật.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.drone_client.takeoff(
                self.takeoff_altitude.value(), self.takeoff_speed.value()
            )

    def _hold(self):
        self.drone_client.hold()

    def _confirm_rtl(self):
        self._confirm_and_call(
            "Gửi RTL: UAV sẽ quay về Home theo chế độ và tham số PX4.",
            self.drone_client.return_to_launch,
        )

    def _confirm_land(self):
        self._confirm_and_call(
            "Gửi Land: UAV sẽ hạ cánh tại vị trí hiện tại.",
            self.drone_client.land,
        )

    def _call_connected(self, callback):
        return lambda: callback() if self._connected else None

    def _on_connection_changed(self, connected, message):
        self._connected = bool(connected)
        self._connecting = bool(not connected and message.startswith("Đang kết nối"))
        self.connection_status_label.setText(
            f"{'Connected' if connected else 'Disconnected'} · {message}"
        )
        self.connection_status_label.setStyleSheet(
            "color: #81c784;" if connected else "color: #ffcc80;"
        )
        self.connection_state_changed.emit(bool(connected), message)
        if not connected:
            self._telemetry_snapshot = {"connected": False}
            self._mission_uploaded = False
            self._uploaded_signature = None
            self.mission_upload_status_label.setText(
                "Upload: trạng thái không còn xác định sau khi ngắt kết nối"
            )
            self.telemetry_updated.emit(dict(self._telemetry_snapshot))
        else:
            self._telemetry_snapshot["connected"] = True
            self.telemetry_updated.emit(dict(self._telemetry_snapshot))
        self._refresh_controls()

    def _on_telemetry_updated(self, snapshot):
        self._telemetry_snapshot = dict(snapshot)
        self.telemetry_updated.emit(dict(snapshot))

        if snapshot.get("lat") is not None and snapshot.get("lon") is not None:
            position = f"{snapshot['lat']:.7f}, {snapshot['lon']:.7f}"
        else:
            position = "—"
        self.telemetry_labels["Vị trí"].setText(position)
        self.telemetry_labels["Độ cao tương đối"].setText(
            self._format_number(snapshot.get("relative_altitude_m"), "m")
        )
        self.telemetry_labels["Độ cao tuyệt đối"].setText(
            self._format_number(snapshot.get("absolute_altitude_m"), "m")
        )
        self.telemetry_labels["Ground speed"].setText(
            self._format_number(snapshot.get("ground_speed_m_s"), "m/s")
        )
        self.telemetry_labels["Pin"].setText(
            self._format_number(snapshot.get("battery_percent"), "%")
        )

        armed = snapshot.get("armed")
        in_air = snapshot.get("in_air")
        if armed is None or in_air is None:
            flight_state = "Chưa xác định"
        else:
            flight_state = f"{'Armed' if armed else 'Disarmed'} · "
            flight_state += "In Air" if in_air else "Landed"
        self.telemetry_labels["Trạng thái"].setText(flight_state)
        self.telemetry_labels["Flight mode"].setText(
            snapshot.get("flight_mode", "—")
        )
        gps_fix = snapshot.get("gps_fix")
        satellites = snapshot.get("gps_satellites")
        global_health = snapshot.get("health_global_ok")
        home_health = snapshot.get("health_home_ok")
        global_text = self._format_health_flag(global_health)
        home_text = self._format_health_flag(home_health)
        health_text = (
            f"global {global_text} · Home {home_text}"
        )
        self.telemetry_labels["GPS"].setText(
            f"{gps_fix or '—'} · {satellites if satellites is not None else '—'} "
            f"vệ tinh · {health_text}"
        )
        self.telemetry_labels["Heading"].setText(
            self._format_number(snapshot.get("heading_deg"), "°")
        )
        severity = snapshot.get("px4_status_severity")
        text = snapshot.get("px4_status_text")
        status_text = f"{severity}: {text}" if text else "—"
        self.telemetry_labels["PX4 status gần nhất"].setText(status_text)
        if severity in {"CRITICAL", "ALERT", "EMERGENCY"} and text:
            self.connection_status_label.setText(f"PX4 {severity}: {text}")
            self.connection_status_label.setStyleSheet("color: #ff8a80;")
        self._refresh_controls()

    @staticmethod
    def _format_number(value, unit):
        if value is None:
            return "—"
        try:
            return f"{float(value):.1f} {unit}"
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def _format_health_flag(value):
        if value is True:
            return "OK"
        if value is False:
            return "chưa đạt"
        return "—"

    def _append_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")

    def _on_operation_finished(self, name, success, message):
        if name == "Worker":
            self._connecting = False
            self.connection_status_label.setText(message)
            self._refresh_controls()
            return
        if name == "Create MissionPlan":
            signature_is_current = (
                success
                and self._pending_plan_signature == self._current_mission_signature()
            )
            self._mission_plan_ready = signature_is_current
            self._mission_validated = False
            self._mission_uploaded = False
            self._uploaded_signature = None
            self.mission_upload_status_label.setText(
                "MissionPlan đã tạo trong worker · chưa Upload"
                if signature_is_current
                else "MissionPlan chưa sẵn sàng cho cấu hình hiện tại"
            )
        if name == "Upload Mission":
            if success:
                current_signature = self._current_mission_signature()
                if current_signature == self._pending_upload_signature:
                    self._mission_uploaded = True
                    self._uploaded_signature = self._pending_upload_signature
                    self.mission_upload_status_label.setText(
                        f"Upload: thành công · "
                        f"{len(self._mission_definition['waypoints'])} "
                        "waypoint · UAV chưa cất cánh"
                    )
                else:
                    self._mission_uploaded = False
                    self._uploaded_signature = None
                    self.mission_upload_status_label.setText(
                        "PX4 đã nhận Mission cũ; cấu hình hiện tại đã đổi, cần Upload lại."
                    )
            else:
                self._mission_uploaded = False
                self._uploaded_signature = None
                self.mission_upload_status_label.setText(
                    f"Upload thất bại: {message}"
                )
        if name == "Action Mission" and not success:
            self.mission_status_label.setText(f"Không chạy Mission: {message}")
        if name == "Action Mission" and success:
            self.mission_status_label.setText(message)
        if not success:
            QMessageBox.warning(self, f"{name} thất bại", message)
        else:
            self.mission_status_label.setText(message)
        self._refresh_controls()

    def _on_mission_progress(self, current, total):
        if total <= 0:
            self.mission_progress_label.setText("Tiến độ: không có waypoint")
            self.mission_progress_bar.setValue(0)
            return
        progress = max(0, min(100, int(current * 100 / total)))
        self.mission_progress_bar.setValue(progress)
        if current >= total:
            self.mission_progress_label.setText(
                f"Mission hoàn tất · {total}/{total} waypoint"
            )
        else:
            current_waypoint = min(current + 1, total)
            self.mission_progress_label.setText(
                f"Đang hướng tới Waypoint {current_waypoint}/{total} "
                f"· PX4 progress {current}/{total}"
            )

    def _on_mission_state(self, message):
        self.mission_status_label.setText(message)

    def _load_mission(self):
        try:
            route_data = load_latest_route()
            mission_definition = apply_default_settings(
                route_data,
                self.default_altitude.value(),
                self.default_speed.value(),
            )
            mission_definition["max_start_distance_m"] = (
                self.max_start_distance.value()
            )
            self._search_areas = load_search_areas()
        except (OSError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Không thể Load Mission", str(error))
            self._append_log(f"LOAD MISSION FAILED — {error}")
            return

        self._route_data = route_data
        self._mission_definition = mission_definition
        self._action_list_built = False
        self._mission_plan_ready = False
        self._mission_validated = False
        self._mission_uploaded = False
        self._uploaded_signature = None
        self.mission_source_label.setText(
            f"Đã nạp tuyến mới nhất: {route_data['waypoint_count']} waypoint · "
            f"thuật toán {route_data['source_route'].get('algorithm', 'không rõ')} · "
            f"nguồn {route_data['source_path']} · không sửa file gốc."
        )
        self.mission_upload_status_label.setText("Upload: chưa gửi lên PX4")
        self.mission_status_label.setText(
            "Đã đọc tuyến GPS theo thứ tự JSON. Chưa tạo MissionPlan, chưa Upload."
        )
        self._populate_waypoint_cards(waypoints_only=True)
        self._send_mission_route_to_map()
        self.validation_output.clear()
        self._append_log(
            f"LOADED {route_data['waypoint_count']} waypoint từ tuyến mới nhất; "
            "tọa độ nguồn giữ nguyên."
        )
        self._refresh_controls()

    def _populate_waypoint_cards(self, waypoints_only=False):
        self.action_cards.clear()
        if not self._mission_definition:
            return

        if not waypoints_only:
            self._add_card("Pre-flight Check", {"kind": "preflight"})
            self._add_card("Arm", {"kind": "arm"})
            self._add_card(
                "Start Mission / PX4 multicopter takeoff",
                {"kind": "mission_start"},
            )

        for index, point in enumerate(self._mission_definition["waypoints"]):
            self._add_card(
                f"Waypoint {index + 1} · {point['lat']:.7f}, {point['lon']:.7f}",
                {"kind": "waypoint", "index": index},
            )

        if not waypoints_only:
            self._add_card(
                f"End action · {self._end_action_label()}",
                {"kind": "end_action"},
            )

    def _add_card(self, title, payload):
        item = QListWidgetItem(title)
        item.setData(Qt.UserRole, payload)
        self.action_cards.addItem(item)

    def _build_actions(self):
        if not self._mission_definition:
            QMessageBox.information(self, "Mission", "Hãy Load Mission trước.")
            return
        self._mission_definition["end_action"] = self.end_action.currentData()
        self._mission_definition["max_start_distance_m"] = (
            self.max_start_distance.value()
        )
        self._populate_waypoint_cards(waypoints_only=False)
        self._action_list_built = True
        self._invalidate_mission_plan("Danh sách actions vừa được tạo.")
        self.action_cards.setCurrentRow(0)
        self.mission_status_label.setText(
            "Đã tạo thứ tự actions. Chưa tạo MAVSDK MissionPlan và chưa gửi lên PX4."
        )
        self._append_log(
            "BUILT action cards; Mission controls, MissionItems và end action được phân biệt."
        )
        self._refresh_controls()

    def _show_selected_card(self, current, previous):
        del previous
        if current is None:
            self._current_card = None
            self.card_title.setText("Chọn một card để xem cấu hình")
            self.card_description.setText("")
            self.waypoint_form.setVisible(False)
            return

        payload = current.data(Qt.UserRole) or {}
        self._current_card = payload
        kind = payload.get("kind")
        self.waypoint_form.setVisible(kind == "waypoint")

        if kind == "waypoint":
            index = payload["index"]
            point = self._mission_definition["waypoints"][index]
            self.card_title.setText(f"Waypoint {index + 1}")
            self.card_description.setText(
                "Card này cấu hình MissionItem. Thay đổi chỉ thuộc Mission đang làm việc; "
                "waypoints.json không bị ghi lại."
            )
            self.card_lat.setValue(point["lat"])
            self.card_lon.setValue(point["lon"])
            self.card_altitude.setValue(point["relative_altitude_m"])
            self.card_speed.setValue(point["speed_m_s"])
            self.card_fly_through.setChecked(point["is_fly_through"])
            yaw = point.get("yaw_deg")
            self.card_yaw_enabled.setChecked(yaw is not None)
            self.card_yaw.setEnabled(yaw is not None)
            if yaw is not None:
                self.card_yaw.setValue(yaw)
            return

        descriptions = {
            "preflight": (
                "Kiểm tra kết nối, GPS/global position, Home, trạng thái mặt đất, "
                "tọa độ, độ cao, khoảng cách và các cảnh báo tuyến."
            ),
            "arm": "Action API: Arm được gọi khi người dùng xác nhận chạy Mission.",
            "mission_start": (
                "Mission API: sau Arm, Start Mission. Với PX4 multicopter, PX4 tự "
                "thực hiện climb/takeoff theo Mission; độ cao của Waypoint 1 là "
                "độ cao mục tiêu ban đầu. Không tạo Takeoff MissionItem và không "
                "gửi Action.takeoff riêng."
            ),
            "end_action": (
                "RTL là thiết lập Mission/PX4 để quay về Home sau waypoint cuối; "
                "Land gọi Action.land tại điểm kết thúc; Hold gọi Action.hold. "
                "Chỉ chọn một cách kết thúc."
            ),
        }
        titles = {
            "preflight": "Pre-flight Check",
            "arm": "Arm · Action API",
            "mission_start": "Start Mission / PX4 multicopter takeoff",
            "end_action": f"End action · {self._end_action_label()}",
        }
        self.card_title.setText(titles.get(kind, "Mission action"))
        self.card_description.setText(descriptions.get(kind, ""))

    def _save_selected_waypoint(self):
        if (not self._mission_definition or not self._current_card
                or self._current_card.get("kind") != "waypoint"):
            return
        index = self._current_card["index"]
        point = self._mission_definition["waypoints"][index]
        point.update({
            "lat": self.card_lat.value(),
            "lon": self.card_lon.value(),
            "relative_altitude_m": self.card_altitude.value(),
            "speed_m_s": self.card_speed.value(),
            "is_fly_through": self.card_fly_through.isChecked(),
            "yaw_deg": self.card_yaw.value() if self.card_yaw_enabled.isChecked() else None,
        })
        item = self.action_cards.currentItem()
        item.setText(
            f"Waypoint {index + 1} · {point['lat']:.7f}, {point['lon']:.7f}"
        )
        self.card_yaw.setEnabled(self.card_yaw_enabled.isChecked())
        self._invalidate_mission_plan(
            f"Đã cập nhật cấu hình Waypoint {index + 1} trong Mission đang làm việc."
        )
        self._send_mission_route_to_map()
        self._append_log(
            f"EDITED Waypoint {index + 1} in working Mission; source JSON unchanged."
        )

    def _apply_defaults_to_all(self):
        if not self._mission_definition:
            QMessageBox.information(self, "Mission", "Hãy Load Mission trước.")
            return
        for point in self._mission_definition["waypoints"]:
            point["relative_altitude_m"] = self.default_altitude.value()
            point["speed_m_s"] = self.default_speed.value()
        self._invalidate_mission_plan("Đã áp dụng defaults cho toàn bộ waypoint.")
        self._send_mission_route_to_map()
        if self._action_list_built:
            self._populate_waypoint_cards(waypoints_only=False)
        self._append_log("APPLIED default altitude and speed to working Mission only.")

    def _end_action_changed(self, index):
        del index
        if self._mission_definition is None:
            return
        self._mission_definition["end_action"] = self.end_action.currentData()
        if self._action_list_built:
            self._populate_waypoint_cards(waypoints_only=False)
        self._invalidate_mission_plan("Hành động kết thúc Mission đã thay đổi.")

    def _create_mission_plan(self):
        if not self._mission_definition or not self._action_list_built:
            QMessageBox.information(
                self, "Create MissionPlan", "Hãy Load Mission và Build actions trước."
            )
            return
        self._sync_mission_settings()
        self._pending_plan_signature = self._current_mission_signature()
        self._mission_plan_ready = False
        self._mission_validated = False
        self._mission_uploaded = False
        self._uploaded_signature = None
        self.mission_upload_status_label.setText(
            "Đang tạo MAVSDK MissionPlan trong event loop nền…"
        )
        self.mission_status_label.setText(
            "Đang tạo MissionPlan trên máy này; thao tác này chưa gửi dữ liệu lên PX4."
        )
        self.drone_client.create_mission_plan(
            deepcopy(self._mission_definition), self._pending_plan_signature
        )
        self._refresh_controls()

    def _validate_current_mission(self):
        if not self._mission_definition or not self._action_list_built:
            QMessageBox.information(self, "Validate", "Hãy Load Mission và Build actions trước.")
            return
        self._sync_mission_settings()
        telemetry = self._telemetry_for_validation()
        errors, warnings = validate_mission(
            self._mission_definition, telemetry, self._search_areas
        )
        lines = [
            f"Waypoint count: {len(self._mission_definition['waypoints'])}",
            f"End action: {self._end_action_label()}",
            f"Connection: {'Connected' if self._connected else 'Disconnected'}",
        ]
        lines.extend(f"ERROR · {item}" for item in errors)
        lines.extend(f"WARNING · {item}" for item in warnings)
        if not errors:
            lines.append("OK · Không phát hiện lỗi chặn theo các kiểm tra hiện có.")
        self.validation_output.setPlainText("\n".join(lines))
        self._mission_validated = not errors
        self._mission_uploaded = False
        self._uploaded_signature = None
        self.mission_upload_status_label.setText(
            "Upload: chưa gửi lên PX4 sau lần Validate mới nhất"
        )
        self.mission_status_label.setText(
            "Mission hợp lệ theo các kiểm tra hiện có. Cảnh báo cần xem trước Upload."
            if not errors else "Mission chưa hợp lệ; sửa lỗi trước khi Upload."
        )
        self._append_log(
            f"VALIDATED mission: {len(errors)} lỗi, {len(warnings)} cảnh báo."
        )
        self._refresh_controls()

    def _telemetry_for_validation(self):
        snapshot = dict(self._telemetry_snapshot)
        snapshot["connected"] = self._connected and bool(snapshot.get("connected"))
        snapshot["home"] = {
            "lat": snapshot.get("home_lat"),
            "lon": snapshot.get("home_lon"),
        }
        snapshot["position"] = {
            "lat": snapshot.get("lat"),
            "lon": snapshot.get("lon"),
        }
        return snapshot

    def _upload_mission(self):
        if not self._mission_plan_ready or not self._mission_validated:
            QMessageBox.information(
                self, "Upload Mission", "Tạo MissionPlan và Validate thành công trước."
            )
            return
        if not self._source_route_is_current():
            self._invalidate_mission_plan(
                "data/waypoints.json đã đổi sau khi Load; hãy Load Mission mới."
            )
            QMessageBox.warning(
                self,
                "Tuyến nguồn đã đổi",
                "Tệp waypoint đã thay đổi sau khi nạp Mission. Hãy Load lại và kiểm tra "
                "tuyến mới trước khi Upload.",
            )
            return
        errors, warnings = validate_mission(
            self._mission_definition,
            self._telemetry_for_validation(),
            self._search_areas,
        )
        if errors:
            self.validation_output.setPlainText(
                "\n".join(f"ERROR · {item}" for item in errors)
            )
            QMessageBox.warning(
                self, "Không thể Upload", "Trạng thái UAV/Mission đã thay đổi; Validate lại."
            )
            self._mission_validated = False
            self._refresh_controls()
            return
        if warnings:
            answer = QMessageBox.warning(
                self,
                "Cảnh báo tuyến Mission",
                "\n\n".join(warnings)
                + "\n\nUpload Mission lên PX4? UAV sẽ không tự Arm hoặc cất cánh.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        self._pending_upload_signature = self._current_mission_signature()
        self._mission_uploaded = False
        self.mission_upload_status_label.setText("Upload: đang gửi MissionPlan lên PX4…")
        self.drone_client.upload_mission(
            deepcopy(self._mission_definition), self._pending_upload_signature
        )
        self._refresh_controls()

    def _confirm_execute_mission(self):
        if not self._mission_uploaded:
            QMessageBox.warning(
                self, "Mission chưa Upload", "Không thể chạy Mission trước khi Upload thành công."
            )
            return
        if not self._source_route_is_current():
            self._mission_uploaded = False
            self._uploaded_signature = None
            self._refresh_controls()
            QMessageBox.warning(
                self,
                "Tuyến nguồn đã đổi",
                "data/waypoints.json đã thay đổi từ sau khi Mission được Load/Upload. "
                "Không chạy bản Mission cũ; hãy Load, kiểm tra và Upload lại.",
            )
            return
        answer = QMessageBox.warning(
            self,
            "Xác nhận Action Mission",
            f"Bắt đầu Mission {len(self._mission_definition['waypoints'])} waypoint?\n\n"
            "Ứng dụng sẽ kiểm tra kết nối, GPS, Home, health và trạng thái mặt đất; "
            "sau đó Arm và gọi Mission.start_mission(). PX4 multicopter tự cất cánh "
            "theo Mission. Chỉ thực hiện trong PX4 SITL + Gazebo.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.drone_client.start_mission(
                deepcopy(self._mission_definition),
                self._current_mission_signature(),
            )

    def _sync_mission_settings(self):
        self._mission_definition["end_action"] = self.end_action.currentData()
        self._mission_definition["max_start_distance_m"] = (
            self.max_start_distance.value()
        )

    def _current_mission_signature(self):
        if self._mission_definition is None:
            return None
        self._sync_mission_settings()
        return mission_signature(self._mission_definition)

    def _source_route_is_current(self):
        if not self._route_data:
            return False
        try:
            latest = load_latest_route()
        except (OSError, TypeError, ValueError):
            return False
        return mission_signature(latest["source_route"]) == mission_signature(
            self._route_data["source_route"]
        )

    def _invalidate_mission_plan(self, message):
        self._mission_plan_ready = False
        self._mission_validated = False
        self._mission_uploaded = False
        self._uploaded_signature = None
        self.mission_upload_status_label.setText(
            "Mission thay đổi · cần Create MissionPlan, Validate và Upload lại"
        )
        if message:
            self.mission_status_label.setText(message)
        self._refresh_controls()

    def _send_mission_route_to_map(self):
        if not self._mission_definition:
            return
        parent_window = self.window()
        bridge = getattr(parent_window, "bridge", None)
        if bridge is not None:
            try:
                bridge.set_mission_route(self._mission_definition["waypoints"])
            except (TypeError, ValueError) as error:
                self._append_log(f"MAP MISSION ROUTE ERROR — {error}")

    def _end_action_label(self):
        labels = {
            "rtl": "RTL về Home",
            "land": "Land tại điểm kết thúc",
            "hold": "Hold tại điểm kết thúc",
        }
        if self._mission_definition:
            key = self._mission_definition.get(
                "end_action", self.end_action.currentData()
            )
        else:
            key = self.end_action.currentData()
        return labels.get(key, "chưa chọn")

    def _refresh_controls(self):
        connected = self._connected
        self.connect_button.setEnabled(not connected and not self._connecting)
        self.disconnect_button.setEnabled(connected)
        for button in (
                self.arm_button, self.disarm_button, self.takeoff_button,
                self.hold_button, self.rtl_button, self.land_button,
                self.pause_mission_button, self.resume_mission_button):
            button.setEnabled(connected)

        loaded = self._mission_definition is not None
        self.build_actions_button.setEnabled(loaded)
        actions_built = loaded and self._action_list_built
        self.create_plan_button.setEnabled(actions_built)
        self.validate_mission_button.setEnabled(actions_built and connected)
        self.upload_mission_button.setEnabled(
            self._mission_plan_ready and self._mission_validated and connected
        )
        self.execute_mission_button.setEnabled(
            self._mission_uploaded and connected
        )
        self.apply_defaults_button.setEnabled(loaded)
        self.save_waypoint_button.setEnabled(
            bool(self._current_card)
            and self._current_card.get("kind") == "waypoint"
        )

    def closeEvent(self, event):
        if self.drone_client.isRunning():
            if self._connected and self._telemetry_snapshot.get("in_air"):
                answer = QMessageBox.warning(
                    self,
                    "UAV đang bay",
                    "Đóng ứng dụng sẽ ngắt kênh telemetry; PX4 sẽ tự xử lý theo failsafe "
                    "đã cấu hình. Bạn có chắc muốn đóng không?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    event.ignore()
                    return
            self.drone_client.stop_worker()
        event.accept()
