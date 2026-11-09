"""Kết nối MAVSDK 4.x trong event loop riêng, không chặn vòng lặp Qt."""

import asyncio
from importlib.metadata import PackageNotFoundError, version
import math
import time

from PyQt5.QtCore import QThread, pyqtSignal


DEFAULT_CONNECTION_URI = "udpin://0.0.0.0:14540"
SYSTEM_DISCOVERY_TIMEOUT_S = 15.0
TELEMETRY_STALE_TIMEOUT_S = 5.0
REQUIRED_MAVSDK_VERSION = "4.0.6"


class DroneClient(QThread):
    """Một client MAVSDK chạy trong QThread và sở hữu asyncio event loop."""

    ready = pyqtSignal()
    connection_changed = pyqtSignal(bool, str)
    telemetry_updated = pyqtSignal(dict)
    log_message = pyqtSignal(str)
    operation_finished = pyqtSignal(str, bool, str)
    mission_progress = pyqtSignal(int, int)
    mission_state_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop = None
        self._mavsdk = None
        self._drone = None
        self._action = None
        self._telemetry = None
        self._mission = None
        self._connected = False
        self._tasks = set()
        self._uploaded_signature = None
        self._prepared_mission_plan = None
        self._prepared_signature = None
        self._mission_running = False
        self._mission_paused = False
        self._last_mission_progress = None
        self._operation_busy = False
        self._latest = {
            "connected": False,
            "armed": False,
            "in_air": False,
        }
        self._last_telemetry_at = None
        self._disconnect_reported = False

    def run(self):
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self.ready.emit()
        loop.run_forever()

        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        loop.close()
        self._loop = None

    def connect_drone(self, connection_uri):
        self._submit(self._connect(connection_uri.strip()))

    def disconnect_drone(self):
        self._submit(self._disconnect())

    def arm(self):
        self._submit(self._arm())

    def disarm(self):
        self._submit(self._disarm())

    def takeoff(self, altitude_m, speed_m_s):
        self._submit(self._takeoff(altitude_m, speed_m_s))

    def hold(self):
        self._submit(self._hold())

    def return_to_launch(self):
        self._submit(self._return_to_launch())

    def land(self):
        self._submit(self._land())

    def upload_mission(self, mission_definition, signature):
        self._submit(self._upload_mission(mission_definition, signature))

    def create_mission_plan(self, mission_definition, signature):
        self._submit(
            self._create_mission_plan(mission_definition, signature)
        )

    def start_mission(self, mission_definition, signature):
        self._submit(self._start_mission(mission_definition, signature))

    def pause_mission(self):
        self._submit(self._pause_mission())

    def resume_mission(self):
        self._submit(self._resume_mission())

    def stop_worker(self):
        if self._loop is not None and self.isRunning():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self.wait(3000)

    def _submit(self, coroutine):
        if self._loop is None or not self.isRunning():
            coroutine.close()
            self.operation_finished.emit(
                "Worker", False, "Dịch vụ MAVSDK chưa khởi động."
            )
            return
        asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    async def _connect(self, connection_uri):
        if self._connected:
            self.connection_changed.emit(
                True, "UAV đã kết nối; hãy ngắt kết nối trước khi đổi URI."
            )
            return
        if not connection_uri:
            self.connection_changed.emit(False, "Connection URI không được để trống.")
            return

        self.connection_changed.emit(False, f"Đang kết nối tới {connection_uri}…")
        try:
            installed_version = version("mavsdk")
        except PackageNotFoundError:
            self.connection_changed.emit(
                False,
                "Chưa cài MAVSDK. Cài phiên bản đã ghim bằng: "
                "python -m pip install -r requirements.txt",
            )
            return
        if installed_version != REQUIRED_MAVSDK_VERSION:
            self.connection_changed.emit(
                False,
                f"MAVSDK {REQUIRED_MAVSDK_VERSION} được yêu cầu, nhưng đang có "
                f"{installed_version}. Hãy cài bằng requirements.txt.",
            )
            return

        try:
            from mavsdk.asyncio import ComponentType, Configuration, Mavsdk
            from mavsdk.asyncio.plugins.action import ActionAsync
            from mavsdk.asyncio.plugins.mission import MissionAsync
            from mavsdk.asyncio.plugins.telemetry import TelemetryAsync
        except ImportError as error:
            self.connection_changed.emit(
                False,
                "Không nạp được MAVSDK 4.x. Cài đúng môi trường bằng: "
                "python -m pip install -r requirements.txt. "
                f"Chi tiết: {error}",
            )
            return

        try:
            configuration = Configuration.create_with_component_type(
                ComponentType.GROUND_STATION
            )
            mavsdk = Mavsdk(configuration)
            await mavsdk.add_any_connection(connection_uri)
            drone = await mavsdk.first_autopilot(SYSTEM_DISCOVERY_TIMEOUT_S)
            if drone is None:
                self.connection_changed.emit(
                    False,
                    f"Không tìm thấy autopilot sau {SYSTEM_DISCOVERY_TIMEOUT_S:g} giây. "
                    "Kiểm tra PX4 SITL và Connection URI.",
                )
                return

            self._mavsdk = mavsdk
            self._drone = drone
            self._action = ActionAsync(drone)
            self._mission = MissionAsync(drone)
            self._telemetry = TelemetryAsync(drone)
            self._connected = True
            self._disconnect_reported = False
            self._uploaded_signature = None
            self._mission_running = False
            self._mission_paused = False
            self._last_mission_progress = None
            self._last_telemetry_at = time.monotonic()
            self._latest = {"connected": True, "armed": False, "in_air": False}

            self.connection_changed.emit(
                True, f"Đã phát hiện autopilot qua {connection_uri}."
            )
            self.log_message.emit("UAV 1: CONNECTED — autopilot đã được phát hiện.")
            self.log_message.emit(
                f"UAV 1: MAVSDK {installed_version} native asyncio API."
            )
            self._start_background_task(self._monitor_telemetry())
            self._start_background_task(self._monitor_connection())
            self._start_background_task(self._monitor_status_text())
            self._start_background_task(self._monitor_mission_progress())
        except Exception as error:
            self.connection_changed.emit(False, f"Kết nối thất bại: {error}")
            self.log_message.emit(f"UAV 1: CONNECTION ERROR — {error}")
            self._connected = False
            self._mavsdk = None
            self._drone = None
            self._action = None
            self._mission = None
            self._telemetry = None

    def _start_background_task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _monitor_telemetry(self):
        telemetry = self._telemetry
        if telemetry is None:
            return

        async def stream_position():
            async for value in telemetry.subscribe_position():
                self._last_telemetry_at = time.monotonic()
                await self._publish_position(value)

        async def stream_velocity():
            async for value in telemetry.subscribe_velocity_ned():
                self._last_telemetry_at = time.monotonic()
                self._latest["ground_speed_m_s"] = math.sqrt(
                    value.north_m_s ** 2
                    + value.east_m_s ** 2
                    + value.down_m_s ** 2
                )
                self._publish_latest()

        async def stream_battery():
            async for value in telemetry.subscribe_battery():
                self._last_telemetry_at = time.monotonic()
                # MAVSDK Telemetry reports this field on a 0..100 scale.
                self._latest["battery_percent"] = value.remaining_percent
                self._publish_latest()

        async def stream_armed():
            async for value in telemetry.subscribe_armed():
                self._last_telemetry_at = time.monotonic()
                was_armed = self._latest.get("armed")
                self._latest["armed"] = bool(value)
                if bool(value) != was_armed:
                    state = "ARMED" if value else "DISARMED"
                    self.log_message.emit(f"UAV 1: {state} — telemetry xác nhận.")
                self._publish_latest()

        async def stream_in_air():
            async for value in telemetry.subscribe_in_air():
                self._last_telemetry_at = time.monotonic()
                was_in_air = self._latest.get("in_air")
                self._latest["in_air"] = bool(value)
                if bool(value) and not was_in_air:
                    self.log_message.emit("UAV 1: TAKEOFF — telemetry xác nhận đang bay.")
                elif not bool(value) and was_in_air:
                    self.log_message.emit("UAV 1: LANDED — telemetry xác nhận đã hạ cánh.")
                self._publish_latest()

        async def stream_flight_mode():
            async for value in telemetry.subscribe_flight_mode():
                self._last_telemetry_at = time.monotonic()
                mode = getattr(value, "name", str(value))
                previous = self._latest.get("flight_mode")
                self._latest["flight_mode"] = mode
                if mode != previous:
                    self.log_message.emit(f"UAV 1: FLIGHT MODE {mode}.")
                    if mode == "MISSION":
                        self.mission_state_changed.emit("Mission đang chạy.")
                        self.log_message.emit(
                            "UAV 1: MISSION MODE CONFIRMED — telemetry báo PX4 MISSION."
                        )
                self._publish_latest()

        async def stream_gps():
            async for value in telemetry.subscribe_gps_info():
                self._last_telemetry_at = time.monotonic()
                self._latest["gps_fix"] = getattr(
                    value.fix_type, "name", str(value.fix_type)
                )
                self._latest["gps_satellites"] = int(value.num_satellites)
                self._publish_latest()

        async def stream_health():
            async for value in telemetry.subscribe_health():
                self._last_telemetry_at = time.monotonic()
                self._latest["health_global_ok"] = bool(
                    value.is_global_position_ok
                )
                self._latest["health_home_ok"] = bool(value.is_home_position_ok)
                self._latest["health_local_ok"] = bool(value.is_local_position_ok)
                self._publish_latest()

        async def stream_heading():
            async for value in telemetry.subscribe_heading():
                self._last_telemetry_at = time.monotonic()
                self._latest["heading_deg"] = value.heading_deg
                self._publish_latest()

        async def stream_home():
            async for value in telemetry.subscribe_home():
                self._last_telemetry_at = time.monotonic()
                self._latest["home_lat"] = value.latitude_deg
                self._latest["home_lon"] = value.longitude_deg
                self._latest["home_absolute_altitude_m"] = value.absolute_altitude_m
                self._publish_latest()

        streams = (
            stream_position,
            stream_velocity,
            stream_battery,
            stream_armed,
            stream_in_air,
            stream_flight_mode,
            stream_gps,
            stream_health,
            stream_heading,
            stream_home,
        )
        tasks = [asyncio.create_task(stream()) for stream in streams]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            raise
        except Exception as error:
            self.log_message.emit(f"UAV 1: TELEMETRY ERROR — {error}")

    async def _publish_position(self, value):
        self._latest.update({
            "lat": value.latitude_deg,
            "lon": value.longitude_deg,
            "relative_altitude_m": value.relative_altitude_m,
            "absolute_altitude_m": value.absolute_altitude_m,
        })
        self._publish_latest()

    def _publish_latest(self):
        snapshot = {}
        for key, value in self._latest.items():
            if isinstance(value, float) and not math.isfinite(value):
                snapshot[key] = None
            else:
                snapshot[key] = value
        snapshot["connected"] = self._connected
        self.telemetry_updated.emit(snapshot)

    async def _monitor_connection(self):
        drone = self._drone
        while drone is not None and self._connected:
            try:
                connected = await self._maybe_await(drone.is_connected())
            except Exception:
                connected = False

            stale = (
                self._last_telemetry_at is not None
                and time.monotonic() - self._last_telemetry_at
                > TELEMETRY_STALE_TIMEOUT_S
            )
            if not connected or stale:
                reason = (
                    "Mất heartbeat MAVLink."
                    if not connected
                    else "Telemetry không cập nhật; trạng thái UAV được xem là chưa rõ."
                )
                await self._mark_disconnected(reason)
                break
            await asyncio.sleep(1.0)

    @staticmethod
    async def _maybe_await(value):
        if hasattr(value, "__await__"):
            return await value
        return value

    async def _monitor_status_text(self):
        try:
            async for value in self._telemetry.subscribe_status_text():
                severity = getattr(value.type, "name", str(value.type))
                line = f"PX4 [{severity}]: {value.text}"
                self.log_message.emit(line)
                self._latest["px4_status_text"] = value.text
                self._latest["px4_status_severity"] = severity
                self._publish_latest()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if self._connected:
                self.log_message.emit(f"UAV 1: Không đọc được PX4 status text: {error}")

    async def _monitor_mission_progress(self):
        while self._connected:
            if self._mission_running:
                try:
                    async for value in self._mission.subscribe_mission_progress():
                        if not self._connected or not self._mission_running:
                            break
                        current = int(value.current)
                        total = int(value.total)
                        self.mission_progress.emit(current, total)
                        progress = (current, total)
                        if progress != self._last_mission_progress:
                            self.log_message.emit(
                                f"UAV 1: MISSION PROGRESS {current}/{total} "
                                "— PX4 telemetry."
                            )
                            self._last_mission_progress = progress
                        if total > 0 and current >= total:
                            await self._complete_mission()
                            break
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    self.log_message.emit(f"UAV 1: MISSION PROGRESS ERROR — {error}")
                    self.mission_state_changed.emit(
                        "Không đọc được tiến độ Mission; trạng thái cần kiểm tra trên PX4."
                    )
                    self._mission_running = False
            await asyncio.sleep(0.25)

    async def _complete_mission(self):
        self._mission_running = False
        self._mission_paused = False
        self.log_message.emit("UAV 1: MISSION COMPLETED — PX4 báo current == total.")
        self.mission_state_changed.emit("Mission hoàn tất.")
        end_action = getattr(self, "_mission_end_action", "rtl")

        try:
            if end_action == "land":
                await self._action.land()
                self.log_message.emit(
                    "UAV 1: LAND command được PX4 chấp nhận sau Mission."
                )
                await self._wait_until_landed()
            elif end_action == "hold":
                await self._action.hold()
                self.log_message.emit(
                    "UAV 1: HOLD command được PX4 chấp nhận sau Mission."
                )
            else:
                # Return-to-launch đã được cấu hình trong MissionPlan trước upload.
                await self._wait_until_landed()
        except Exception as error:
            self.log_message.emit(f"UAV 1: END ACTION ERROR — {error}")
            self.mission_state_changed.emit(f"Hành động kết thúc thất bại: {error}")

    async def _wait_until_landed(self, timeout_s=900.0):
        deadline = time.monotonic() + timeout_s
        while self._connected and time.monotonic() < deadline:
            try:
                in_air = bool(await self._telemetry.in_air())
                armed = bool(await self._telemetry.armed())
            except Exception:
                return
            if not in_air and not armed:
                return
            await asyncio.sleep(1.0)
        if self._connected:
            self.mission_state_changed.emit(
                "Chờ hạ cánh quá thời gian; hãy kiểm tra trạng thái PX4."
            )

    async def _read_safety_state(self):
        if not self._connected or self._telemetry is None:
            raise RuntimeError("UAV chưa kết nối.")
        if not await self._maybe_await(self._drone.is_connected()):
            raise RuntimeError("Mất kết nối heartbeat với autopilot.")

        health = await self._telemetry.health()
        gps_info = await self._telemetry.gps_info()
        home = await self._telemetry.home()
        position = await self._telemetry.position()
        armed = bool(await self._telemetry.armed())
        in_air = bool(await self._telemetry.in_air())

        flight_mode = self._latest.get("flight_mode")
        status_text = str(self._latest.get("px4_status_text", ""))
        status_lower = status_text.lower()
        if ("failsafe activated" in status_lower
                or "failsafe active" in status_lower
                or flight_mode == "TERMINATION"):
            raise RuntimeError(
                "PX4 đang báo Failsafe/Termination. Không tiếp tục lệnh; "
                "kiểm tra PX4 status và nguyên nhân trước."
            )

        fix_type = getattr(gps_info.fix_type, "name", str(gps_info.fix_type))
        gps_ok = fix_type not in {"NO_GPS", "NO_FIX", "UNKNOWN"}
        if not health.is_global_position_ok or not gps_ok:
            raise RuntimeError(
                f"GPS/global position chưa đạt yêu cầu (fix={fix_type}, "
                f"global_ok={health.is_global_position_ok})."
            )
        if not health.is_home_position_ok:
            raise RuntimeError("PX4 chưa xác nhận Home position.")

        return {
            "health": health,
            "gps_fix": fix_type,
            "gps_satellites": int(gps_info.num_satellites),
            "home": {
                "lat": float(home.latitude_deg),
                "lon": float(home.longitude_deg),
                "absolute_altitude_m": float(home.absolute_altitude_m),
            },
            "position": {
                "lat": float(position.latitude_deg),
                "lon": float(position.longitude_deg),
                "relative_altitude_m": float(position.relative_altitude_m),
            },
            "armed": armed,
            "in_air": in_air,
            "flight_mode": flight_mode,
            "px4_status_text": status_text,
            "px4_status_severity": self._latest.get("px4_status_severity"),
        }

    async def _require_mission_multicopter(self):
        vehicle_type_method = getattr(self._drone, "vehicle_type", None)
        if vehicle_type_method is None:
            raise RuntimeError(
                "Không đọc được loại phương tiện từ MAVSDK; không thể xác nhận "
                "cách cất cánh Mission."
            )
        vehicle_type = await self._maybe_await(vehicle_type_method())
        vehicle_name = getattr(vehicle_type, "name", str(vehicle_type)).upper()
        supported_types = {
            "MULTICOPTER",
            "GENERICMULTIROTOR",
            "GENERIC_MULTIROTOR",
            "QUADROTOR",
            "COAXIAL",
            "HEXAROTOR",
            "OCTOROTOR",
            "TRICOPTER",
        }
        if vehicle_name not in supported_types:
            raise RuntimeError(
                f"PX4 báo loại phương tiện {vehicle_name}. Mission start từ mặt đất "
                "chỉ được bật ở đây cho multicopter. Mission VTOL cần MissionRaw; "
                "fixed-wing phải được phóng trước."
            )

    async def _arm(self):
        await self._run_operation("Arm", self._arm_impl)

    async def _arm_impl(self):
        state = await self._read_safety_state()
        if state["in_air"]:
            raise RuntimeError("Không Arm lại khi UAV đang bay.")
        if state["armed"]:
            return "UAV đã Armed theo telemetry."
        if not await self._telemetry.health_all_ok():
            raise RuntimeError(
                "PX4 chưa báo toàn bộ health checks đạt; xem health và PX4 status."
            )
        await self._action.arm()
        await self._wait_for_state("armed", True, 8.0)
        return "UAV đã Armed; telemetry xác nhận."

    async def _disarm(self):
        await self._run_operation("Disarm", self._disarm_impl)

    async def _disarm_impl(self):
        if not self._connected:
            raise RuntimeError("UAV chưa kết nối.")
        if await self._telemetry.in_air():
            raise RuntimeError("Không cho phép Disarm khi UAV đang bay.")
        if not await self._telemetry.armed():
            return "UAV đã Disarmed theo telemetry."
        await self._action.disarm()
        await self._wait_for_state("armed", False, 8.0)
        return "UAV đã Disarmed; telemetry xác nhận đang ở mặt đất."

    async def _takeoff(self, altitude_m, speed_m_s):
        await self._run_operation(
            "Takeoff", lambda: self._takeoff_impl(altitude_m, speed_m_s)
        )

    async def _takeoff_impl(self, altitude_m, speed_m_s):
        state = await self._read_safety_state()
        await self._require_mission_multicopter()
        if state["in_air"]:
            raise RuntimeError("Takeoff không hợp lệ khi UAV đã ở trên không.")
        if not state["armed"]:
            raise RuntimeError("Hãy Arm UAV trước khi yêu cầu Takeoff.")
        if not await self._telemetry.health_all_ok():
            raise RuntimeError("PX4 health checks chưa đạt; Takeoff bị từ chối.")
        if not math.isfinite(altitude_m) or not 1.0 <= altitude_m <= 120.0:
            raise ValueError("Độ cao Takeoff phải nằm trong khoảng 1–120 m.")
        if not math.isfinite(speed_m_s) or not 0.5 <= speed_m_s <= 15.0:
            raise ValueError("Tốc độ đặt tối đa phải nằm trong khoảng 0.5–15 m/s.")

        await self._action.set_takeoff_altitude(float(altitude_m))
        await self._action.set_maximum_speed(float(speed_m_s))
        await self._action.takeoff()
        await self._wait_for_state("in_air", True, 30.0)
        return f"Takeoff telemetry đã xác nhận; độ cao đặt {altitude_m:g} m."

    async def _hold(self):
        await self._run_operation("Hold", self._hold_impl)

    async def _hold_impl(self):
        if not self._connected or not await self._telemetry.in_air():
            raise RuntimeError("Hold thủ công chỉ khả dụng khi UAV đang bay.")
        await self._action.hold()
        return "PX4 đã chấp nhận lệnh Hold; đây không phải Pause Mission."

    async def _return_to_launch(self):
        await self._run_operation("RTL", self._rtl_impl)

    async def _rtl_impl(self):
        await self._read_safety_state()
        if not await self._telemetry.in_air():
            raise RuntimeError("RTL chỉ được gửi khi UAV đang bay.")
        await self._action.return_to_launch()
        return "PX4 đã chấp nhận lệnh Return to Launch."

    async def _land(self):
        await self._run_operation("Land", self._land_impl)

    async def _land_impl(self):
        if not self._connected or not await self._telemetry.in_air():
            raise RuntimeError("Land chỉ được gửi khi UAV đang bay.")
        await self._action.land()
        return "PX4 đã chấp nhận lệnh Land tại vị trí hiện tại."

    async def _upload_mission(self, mission_definition, signature):
        async def upload():
            from mission.mission_service import (
                validate_mission,
            )

            state = await self._read_safety_state()
            await self._require_mission_multicopter()
            if state["in_air"]:
                raise RuntimeError("Chỉ Upload Mission mới khi UAV đang ở mặt đất.")
            if state["armed"]:
                raise RuntimeError("Disarm UAV trước khi Upload Mission mới.")

            validation_state = {
                "connected": True,
                "health_global_ok": bool(
                    state["health"].is_global_position_ok
                ),
                "health_home_ok": bool(state["health"].is_home_position_ok),
                "gps_fix": state["gps_fix"],
                "in_air": state["in_air"],
                "home": state["home"],
                "position": state["position"],
                "flight_mode": state["flight_mode"],
                "px4_status_text": state["px4_status_text"],
                "px4_status_severity": state["px4_status_severity"],
            }
            errors, _warnings = validate_mission(
                mission_definition, validation_state, []
            )
            if errors:
                raise RuntimeError("Mission không hợp lệ: " + " ".join(errors))

            if (self._prepared_mission_plan is None
                    or self._prepared_signature != signature):
                raise RuntimeError(
                    "MissionPlan chưa được tạo cho cấu hình hiện tại."
                )
            return_to_launch = mission_definition["end_action"] == "rtl"
            await self._mission.set_return_to_launch_after_mission(
                return_to_launch
            )
            await self._mission.upload_mission(self._prepared_mission_plan)
            self._uploaded_signature = signature
            self._mission_end_action = mission_definition["end_action"]
            self._mission_running = False
            self._mission_paused = False
            return (
                f"PX4 xác nhận Upload thành công: "
                f"{len(mission_definition['waypoints'])} waypoint. "
                "UAV chưa Armed và chưa cất cánh."
            )

        await self._run_operation("Upload Mission", upload)

    async def _create_mission_plan(self, mission_definition, signature):
        async def create():
            from mission.mission_service import build_mission_plan

            plan = build_mission_plan(mission_definition)
            self._prepared_mission_plan = plan
            self._prepared_signature = signature
            return (
                f"Đã tạo MAVSDK MissionPlan với "
                f"{len(mission_definition['waypoints'])} MissionItem; chưa Upload."
            )

        await self._run_operation("Create MissionPlan", create)

    async def _start_mission(self, mission_definition, signature):
        async def start():
            from mission.mission_service import validate_mission

            if not self._connected:
                raise RuntimeError("UAV chưa kết nối.")
            if not mission_definition.get("waypoints"):
                raise RuntimeError("Mission rỗng.")
            if self._uploaded_signature != signature:
                raise RuntimeError(
                    "Cấu hình Mission chưa được Upload hoặc đã thay đổi sau Upload."
                )
            state = await self._read_safety_state()
            await self._require_mission_multicopter()
            if state["in_air"]:
                raise RuntimeError(
                    "Mission mới chỉ được bắt đầu khi UAV đang ở mặt đất."
                )
            if not await self._telemetry.health_all_ok():
                raise RuntimeError("PX4 health checks chưa đạt.")
            validation_state = {
                "connected": True,
                "health_global_ok": bool(
                    state["health"].is_global_position_ok
                ),
                "health_home_ok": bool(state["health"].is_home_position_ok),
                "gps_fix": state["gps_fix"],
                "in_air": state["in_air"],
                "home": state["home"],
                "position": state["position"],
                "flight_mode": state["flight_mode"],
                "px4_status_text": state["px4_status_text"],
                "px4_status_severity": state["px4_status_severity"],
            }
            errors, _warnings = validate_mission(
                mission_definition, validation_state, []
            )
            if errors:
                raise RuntimeError("Mission không hợp lệ: " + " ".join(errors))

            if not state["armed"]:
                await self._action.arm()
                await self._wait_for_state("armed", True, 8.0)
                self.log_message.emit("UAV 1: ARMED — telemetry xác nhận.")

            await self._mission.start_mission()
            self._mission_running = True
            self._mission_paused = False
            self._mission_end_action = mission_definition["end_action"]
            self._last_mission_progress = None
            self.mission_state_changed.emit("PX4 đã chấp nhận Start Mission.")
            self.log_message.emit(
                "UAV 1: MISSION START REQUEST ACCEPTED — đang chờ tiến độ PX4."
            )
            return (
                "PX4 đã chấp nhận Start Mission. Với multicopter, PX4 thực hiện "
                "cất cánh tự động theo Mission; không gửi Action.takeoff riêng."
            )

        await self._run_operation("Action Mission", start)

    async def _pause_mission(self):
        async def pause():
            if not self._connected or not self._mission_running:
                raise RuntimeError("Không có Mission đang chạy để Pause.")
            await self._mission.pause_mission()
            self._mission_running = False
            self._mission_paused = True
            self.mission_state_changed.emit("Mission đã được Pause qua Mission API.")
            return "Mission API đã chấp nhận Pause Mission. UAV có thể vẫn đang bay/giữ vị trí."

        await self._run_operation("Pause Mission", pause)

    async def _resume_mission(self):
        async def resume():
            if not self._connected or not self._mission_paused:
                raise RuntimeError("Không có Mission đã Pause để tiếp tục.")
            await self._read_safety_state()
            await self._mission.start_mission()
            self._mission_paused = False
            self._mission_running = True
            self.mission_state_changed.emit("Đã gửi yêu cầu Resume Mission.")
            return "PX4 đã chấp nhận tiếp tục Mission."

        await self._run_operation("Resume Mission", resume)

    async def _run_operation(self, name, operation):
        if self._operation_busy:
            message = "Một lệnh MAVSDK khác đang được xử lý; hãy đợi kết quả."
            self.operation_finished.emit(name, False, message)
            return

        self._operation_busy = True
        self.log_message.emit(f"UAV 1: {name.upper()} — đang kiểm tra trạng thái.")
        try:
            result = await operation()
        except Exception as error:
            message = str(error)
            self.log_message.emit(f"UAV 1: {name.upper()} FAILED — {message}")
            self.operation_finished.emit(name, False, message)
        else:
            self.log_message.emit(f"UAV 1: {name.upper()} — {result}")
            self.operation_finished.emit(name, True, result)
        finally:
            self._operation_busy = False

    async def _wait_for_state(self, key, expected, timeout_s):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            actual = await self._telemetry.armed() if key == "armed" else (
                await self._telemetry.in_air()
            )
            if bool(actual) is bool(expected):
                return
            await asyncio.sleep(0.25)
        raise TimeoutError(f"Telemetry chưa xác nhận {key}={expected}.")

    async def _mark_disconnected(self, reason):
        if self._disconnect_reported:
            return
        self._disconnect_reported = True
        self._connected = False
        self._uploaded_signature = None
        self._mission_running = False
        self._mission_paused = False
        self._latest = {"connected": False, "armed": None, "in_air": None}
        self.telemetry_updated.emit(dict(self._latest))
        self.connection_changed.emit(False, reason)
        self.mission_state_changed.emit(
            "Trạng thái Mission chưa rõ do mất kết nối; không tự động tiếp tục."
        )
        self.log_message.emit(f"UAV 1: DISCONNECTED — {reason}")
        current_task = asyncio.current_task()
        for task in tuple(self._tasks):
            if task is not current_task:
                task.cancel()

    async def _disconnect(self):
        if not self._connected:
            self.connection_changed.emit(False, "Đã ngắt kết nối.")
            return
        await self._mark_disconnected("Đã ngắt kết nối theo yêu cầu người dùng.")
        for task in tuple(self._tasks):
            task.cancel()
        self._tasks.clear()
        self._mavsdk = None
        self._drone = None
        self._action = None
        self._telemetry = None
        self._mission = None

