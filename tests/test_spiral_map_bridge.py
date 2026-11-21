import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from GUI import map_bridge
from GUI.map_bridge import MapBridge


class SpiralMapBridgeTests(unittest.TestCase):
    def test_spiral_is_emitted_and_saved_separately(self):
        area = {
            "id": "sample-area",
            "name": "Test area",
            "coordinates": [
                {"lat": 21.0, "lon": 105.0},
                {"lat": 21.0, "lon": 105.001},
                {"lat": 21.001, "lon": 105.001},
                {"lat": 21.001, "lon": 105.0},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            trajectory_path = Path(temporary_directory) / "trajectories.json"
            bridge = MapBridge()
            emitted = []
            bridge.trajectory_ready.connect(emitted.append)
            bridge_status = []
            bridge.status_changed.connect(bridge_status.append)
            with patch.object(map_bridge, "TRAJECTORY_FILE", trajectory_path):
                bridge.generate_archimedean_spiral(
                    json.dumps(area), 10.0, 0.0, "null", 12.0
                )

            self.assertTrue(trajectory_path.exists())
            stored = json.loads(trajectory_path.read_text(encoding="utf-8"))
            emitted_result = json.loads(emitted[0])
            self.assertEqual(stored["algorithm"], "archimedean_spiral")
            self.assertEqual(emitted_result["area_id"], "sample-area")
            self.assertTrue(emitted_result["segments"])
            self.assertIn("Đã tạo Spiral", bridge_status[-1])


if __name__ == "__main__":
    unittest.main()
