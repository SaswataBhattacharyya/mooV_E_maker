#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
from pathlib import Path

ANIME2SKETCH_DIR = "/home/saswata/web_dev/video maker/video/ai_sketch/Anime2Sketch"

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

def run(cmd, cwd=None):
    subprocess.run(cmd, check=True, cwd=cwd)

def main():
    frames_root = Path(input("Enter frames root folder:\n").strip())
    out_root = Path(input("Enter output sketch folder:\n").strip())
    out_root.mkdir(parents=True, exist_ok=True)

    a2s = Path(ANIME2SKETCH_DIR)
    test_py = a2s / "test.py"
    if not test_py.exists():
        raise RuntimeError("test.py not found in Anime2Sketch repo")

    # Find folders that contain images
    image_dirs = set(p.parent for p in frames_root.rglob("*") if p.suffix.lower() in IMG_EXTS)

    print(f"Found {len(image_dirs)} image folders.")

    for img_dir in sorted(image_dirs):
        rel = img_dir.relative_to(frames_root)
        out_dir = out_root / rel
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n→ Processing folder: {rel}")

        cmd = [
            "python", "test.py",
            "--dataroot", str(img_dir),
            "--output_dir", str(out_dir),
            "--gpu_ids", "0",          # change if needed
        ]

        try:
            run(cmd, cwd=str(a2s))
            print("✓ Done")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed: {e}")

if __name__ == "__main__":
    main()
