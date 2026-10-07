import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from image_analyzer.config.settings import load_settings
from image_analyzer.pipeline import analyze_image


class PipelineSmokeTests(unittest.TestCase):
    def test_analyze_image_writes_bundle(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            image_path = tmp_path / "sample.png"
            output_root = tmp_path / "outputs"
            Image.new("RGB", (20, 10), (200, 200, 200)).save(image_path)

            result = analyze_image(image_path, load_settings(project_root), output_root=output_root, save_debug=True)

            self.assertEqual(result.image.width, 20)
            self.assertTrue((output_root / "sample" / "details.json").exists())
            self.assertTrue((output_root / "sample" / "description.txt").exists())
            self.assertTrue((output_root / "sample" / "events.json").exists())
            self.assertTrue((output_root / "sample" / "layers.json").exists())
            self.assertTrue((output_root / "sample" / "sample_desc_1.txt").exists())
            self.assertTrue((output_root / "sample" / "module_outputs.json").exists())


if __name__ == "__main__":
    unittest.main()
