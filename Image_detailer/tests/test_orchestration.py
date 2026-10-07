import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from image_analyzer.config.settings import load_settings
from image_analyzer.pipeline import analyze_image


class OrchestrationTests(unittest.TestCase):
    def test_orchestration_events_cover_expected_stages(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            image_path = tmp_path / "sample.png"
            Image.new("RGB", (12, 12), (150, 160, 170)).save(image_path)

            result = analyze_image(image_path, load_settings(project_root), output_root=tmp_path / "artifacts", save_debug=False)

            stages = [event.stage for event in result.orchestration_events]
            self.assertIn("load_image", stages)
            self.assertIn("decide_people_modules", stages)
            self.assertIn("synthesize_layers", stages)
            self.assertIn("write_outputs", stages)

    def test_description_layers_are_numbered_from_image_stem(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            image_path = tmp_path / "sample.png"
            Image.new("RGB", (12, 12), (10, 20, 30)).save(image_path)

            result = analyze_image(image_path, load_settings(project_root), output_root=tmp_path / "artifacts", save_debug=False)

            file_names = [layer.file_name for layer in result.description_layers]
            self.assertEqual(file_names[0], "sample_desc_1.txt")
            self.assertEqual(file_names[-1], "sample_desc_6.txt")
            self.assertEqual(len(result.description_layers), 6)


if __name__ == "__main__":
    unittest.main()
