#!/usr/bin/env python3
"""Install this repository's canonical media skills into Hermes home."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SOURCE = Path(__file__).resolve().parent / "skills"
DEFAULT_TARGET = Path.home() / ".hermes" / "skills" / "media"
OWNED_SKILLS = ("comfyui-media-operator", "image-generation-routing", "minimax-h3-video-prompting")


def install(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in OWNED_SKILLS:
        source = SOURCE / name
        destination = target / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        print(f"installed {name} -> {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    install(args.target.expanduser().resolve())


if __name__ == "__main__":
    main()
