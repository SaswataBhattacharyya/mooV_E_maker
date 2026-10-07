from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from image_analyzer.providers.base import OptionalProvider, ProviderArtifact


class DominantColorProvider(OptionalProvider):
    name = "color"

    def analyze(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        with Image.open(image_path).convert("RGB") as image:
            pixels = np.asarray(image.resize((64, 64))).reshape(-1, 3)
        mean_rgb = tuple(int(channel) for channel in pixels.mean(axis=0))
        return ProviderArtifact(
            provider=self.name,
            data={
                "dominant_colors": [
                    {
                        "name": rgb_to_name(mean_rgb),
                        "rgb": mean_rgb,
                        "provenance": self.name,
                        "confidence": 0.55,
                    }
                ]
            },
        )


def rgb_to_name(rgb: tuple[int, int, int]) -> str:
    red, green, blue = rgb
    if red > 180 and green > 180 and blue > 180:
        return "light neutral"
    if red < 80 and green < 80 and blue < 80:
        return "dark neutral"
    if red >= green and red >= blue:
        return "red-dominant"
    if green >= red and green >= blue:
        return "green-dominant"
    return "blue-dominant"

