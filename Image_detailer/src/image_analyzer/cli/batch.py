from __future__ import annotations

from pathlib import Path


SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def resolve_batch_inputs(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() in SUPPORTED_IMAGE_EXTS)

    if path.is_file():
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        return [Path(line).resolve() for line in lines if line and not line.startswith("#")]

    raise FileNotFoundError(f"Batch input not found: {path}")
