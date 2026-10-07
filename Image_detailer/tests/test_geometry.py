import unittest

from image_analyzer.models.schemas import BoundingBox
from image_analyzer.utils.geometry import angle_degrees, normalize_bbox


class GeometryTests(unittest.TestCase):
    def test_normalize_bbox(self) -> None:
        bbox = BoundingBox(x1=10, y1=20, x2=50, y2=80)
        normalized = normalize_bbox(bbox, width=100, height=200)
        self.assertEqual(normalized.x1, 0.1)
        self.assertEqual(normalized.y1, 0.1)
        self.assertEqual(normalized.x2, 0.5)
        self.assertEqual(normalized.y2, 0.4)

    def test_angle_degrees(self) -> None:
        self.assertEqual(angle_degrees((0.0, 0.0), (1.0, 1.0)), 45.0)


if __name__ == "__main__":
    unittest.main()
