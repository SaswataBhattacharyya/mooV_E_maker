import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from image_analyzer.cli.batch import resolve_batch_inputs


class BatchInputTests(unittest.TestCase):
    def test_resolve_batch_inputs_from_directory(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            image_path = tmp_path / "sample.png"
            Image.new("RGB", (5, 5), (0, 0, 0)).save(image_path)
            resolved = resolve_batch_inputs(tmp_path)
            self.assertEqual(resolved, [image_path])

    def test_resolve_batch_inputs_from_manifest(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            image_path = tmp_path / "sample.png"
            manifest_path = tmp_path / "inputs.txt"
            Image.new("RGB", (5, 5), (0, 0, 0)).save(image_path)
            manifest_path.write_text(f"{image_path}\n", encoding="utf-8")
            resolved = resolve_batch_inputs(manifest_path)
            self.assertEqual(resolved, [image_path.resolve()])


if __name__ == "__main__":
    unittest.main()
