import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from image_analyzer.providers.color import DominantColorProvider


class ColorProviderTests(unittest.TestCase):
    def test_color_provider_reports_rgb(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "red.png"
            Image.new("RGB", (10, 10), (220, 10, 10)).save(image_path)
            artifact = DominantColorProvider().analyze(image_path, {})
            dominant = artifact.data["dominant_colors"][0]
            self.assertEqual(dominant["name"], "red-dominant")
            self.assertGreater(dominant["rgb"][0], dominant["rgb"][1])


if __name__ == "__main__":
    unittest.main()
