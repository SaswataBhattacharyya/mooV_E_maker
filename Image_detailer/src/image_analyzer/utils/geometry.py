from __future__ import annotations

from math import atan2, degrees

from image_analyzer.models.schemas import BoundingBox, NormalizedBoundingBox


def normalize_bbox(box: BoundingBox, width: int, height: int) -> NormalizedBoundingBox:
    safe_width = max(width, 1)
    safe_height = max(height, 1)
    return NormalizedBoundingBox(
        x1=round(box.x1 / safe_width, 6),
        y1=round(box.y1 / safe_height, 6),
        x2=round(box.x2 / safe_width, 6),
        y2=round(box.y2 / safe_height, 6),
    )


def angle_degrees(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    return round(degrees(atan2(point_b[1] - point_a[1], point_b[0] - point_a[0])), 3)

