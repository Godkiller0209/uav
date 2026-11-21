import math
import unittest

from trajectory_planning.coverage.archimedean_spiral import (
    _point_in_polygon,
    _project_polygon,
    create_archimedean_spiral,
)


def gps_polygon(points_m):
    """Chuyển tọa độ mẫu quanh Hà Nội từ mét sang GPS để tạo fixture."""
    origin_lat, origin_lon = 21.0, 105.0
    radius = 6_371_000.0
    latitude_scale = math.cos(math.radians(origin_lat))
    return [
        {
            "lat": origin_lat + math.degrees(y / radius),
            "lon": origin_lon + math.degrees(x / (radius * latitude_scale)),
        }
        for x, y in points_m
    ]


SAMPLES = {
    "square": [(0, 0), (80, 0), (80, 80), (0, 80)],
    "rectangle": [(0, 0), (140, 0), (140, 60), (0, 60)],
    "triangle": [(0, 0), (100, 0), (45, 80)],
    "irregular_convex": [(0, 0), (100, 5), (90, 70), (25, 95), (-10, 45)],
    "concave": [(0, 0), (100, 0), (100, 35), (55, 35),
                (55, 85), (0, 85)],
    "small": [(0, 0), (3, 0), (3, 3), (0, 3)],
    "complex_near_edge": [(0, 0), (100, 0), (100, 100), (70, 100),
                           (70, 30), (30, 30), (30, 100), (0, 100)],
}


class ArchimedeanSpiralTests(unittest.TestCase):
    def test_required_polygon_shapes_produce_interior_segments(self):
        for shape_name, points in SAMPLES.items():
            with self.subTest(shape=shape_name):
                gps = gps_polygon(points)
                result = create_archimedean_spiral(
                    gps, spacing_m=12.0, footprint_width_m=15.0
                )
                _, _, polygon_xy = _project_polygon(gps)
                self.assertTrue(result["segments"])
                self.assertGreater(result["path_length_m"], 0)
                self.assertIsNotNone(result["coverage_ratio"])
                self.assertGreaterEqual(result["coverage_ratio"], 0.0)
                self.assertLessEqual(result["coverage_ratio"], 1.0)
                for segment in result["segments"]:
                    self.assertGreaterEqual(len(segment), 2)
                    for point in segment:
                        self.assertTrue(_point_in_polygon(
                            (point["x_m"], point["y_m"]), polygon_xy
                        ))

    def test_spacing_maps_to_archimedean_growth(self):
        result = create_archimedean_spiral(
            gps_polygon(SAMPLES["square"]), spacing_m=10.0
        )
        self.assertAlmostEqual(
            result["radial_growth_m_per_rad"], 10.0 / (2.0 * math.pi)
        )
        self.assertAlmostEqual(result["theoretical_turn_spacing_m"], 10.0)

    def test_concave_polygon_reports_separate_segments(self):
        result = create_archimedean_spiral(
            gps_polygon(SAMPLES["concave"]), spacing_m=8.0
        )
        self.assertEqual(
            result["discontinuity_count"], len(result["segments"]) - 1
        )

    def test_selected_center_outside_polygon_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "bên trong polygon"):
            create_archimedean_spiral(
                gps_polygon(SAMPLES["square"]), 10.0,
                center={"lat": 21.01, "lon": 105.01},
            )

    def test_self_intersection_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "tự giao nhau"):
            create_archimedean_spiral(
                gps_polygon([(0, 0), (20, 20), (0, 20), (20, 0)]), 5.0
            )

    def test_invalid_spacing_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "lớn hơn 0"):
            create_archimedean_spiral(gps_polygon(SAMPLES["square"]), 0.0)


if __name__ == "__main__":
    unittest.main()
