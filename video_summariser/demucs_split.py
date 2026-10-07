#!/usr/bin/env python3
"""
demucs_split.py

Batch split all MP3s under an input folder using Demucs, preserving folder structure.

Outputs numbered stems:
  {name}_1.mp3, {name}_2.mp3, ...

Demucs native stem sets depend on model:
- 2 stems: vocals + no_vocals  (use --stems 2)
- 4 stems: vocals, drums, bass, other (default for htdemucs)
- 6 stems: if model supports (e.g. htdemucs_6s)

Requires:
- demucs installed
- ffmpeg installed (Demucs uses it for mp3 output)
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from typing import List


AUDIO_EXTS = {".mp3"}


def run(cmd: List[str]) -> None:
    print("→", " ".join(cmd))
    subprocess.run(cmd, check=True)


def pick_model(stems: int, model: str | None) -> str:
    if model:
        return model
    if stems == 2:
        return "htdemucs"
    if stems == 4:
        return "htdemucs"
    if stems >= 6:
        return "htdemucs_6s"
    return "htdemucs"


def list_mp3s(input_root: Path) -> List[Path]:
    return [p for p in sorted(input_root.rglob("*.mp3")) if p.is_file()]


def find_demucs_track_dir(tmp_out: Path, model_name: str, track_stem: str) -> Path:
    """
    Demucs typically writes:
      tmp_out/<model_name>/<track_stem>/*.mp3
    """
    p = tmp_out / model_name / track_stem
    if p.exists():
        return p

    # Fallback: search for a directory that looks like the track folder
    # (handles slight naming differences across versions)
    candidates = list(tmp_out.rglob(track_stem))
    for c in candidates:
        if c.is_dir():
            return c

    raise FileNotFoundError(f"Could not locate Demucs output folder for track: {track_stem}")


def number_and_copy_stems(stem_dir: Path, out_dir: Path, base_name: str) -> int:
    """
    Take whatever mp3 stems Demucs produced, sort them deterministically, and write:
      out_dir/<base_name>_1.mp3, _2.mp3, ...
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    stem_files = sorted([p for p in stem_dir.glob("*.mp3") if p.is_file()])
    if not stem_files:
        raise FileNotFoundError(f"No MP3 stems found in {stem_dir}")

    for i, src in enumerate(stem_files, start=1):
        dst = out_dir / f"{base_name}_{i}.mp3"
        shutil.copy2(src, dst)

    return len(stem_files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_root", required=True, help="Folder containing mp3 files (recursively).")
    ap.add_argument("--output_root", required=True, help="Folder to write split mp3s (preserve structure).")
    ap.add_argument("--stems", type=int, default=4, help="Requested stems (2 / 4 / 6 recommended).")
    ap.add_argument("--model", default=None, help="Demucs model name (optional).")
    ap.add_argument("--mp3_bitrate", default="320", help="MP3 bitrate (e.g. 192/256/320).")
    ap.add_argument("--device", default=None, help="cpu or cuda (optional).")
    ap.add_argument("--tmp_out", default="/tmp/demucs_out", help="Temp output directory inside container.")
    args = ap.parse_args()

    input_root = Path(args.input_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    tmp_out = Path(args.tmp_out)

    if not input_root.exists():
        raise SystemExit(f"Input root does not exist: {input_root}")

    model_name = pick_model(args.stems, args.model)

    mp3s = list_mp3s(input_root)
    if not mp3s:
        raise SystemExit(f"No mp3 files found under: {input_root}")

    # Clear temp output each run
    if tmp_out.exists():
        shutil.rmtree(tmp_out, ignore_errors=True)
    tmp_out.mkdir(parents=True, exist_ok=True)

    for mp3 in mp3s:
        rel = mp3.relative_to(input_root)
        out_dir = output_root / rel.parent
        base_name = mp3.stem

        print(f"\n=== Demucs: {rel} ===")

        cmd = ["demucs", "-n", model_name, "--mp3", "--mp3-bitrate", str(args.mp3_bitrate), "-o", str(tmp_out)]

        if args.stems == 2:
            cmd += ["--two-stems", "vocals"]
        elif args.stems in (4, 6):
            pass
        else:
            # Best-effort fallback
            print(f"[warn] stems={args.stems} not standard. Continuing with model default outputs.")

        if args.device:
            cmd += ["--device", args.device]

        cmd += [str(mp3)]
        run(cmd)

        # Locate demucs output stem folder and copy numbered outputs
        stem_dir = find_demucs_track_dir(tmp_out, model_name, base_name)
        n = number_and_copy_stems(stem_dir, out_dir, base_name)
        print(f"   Wrote {n} stems -> {out_dir}")

        # Clean temp track folder to keep /tmp small
        shutil.rmtree(tmp_out / model_name / base_name, ignore_errors=True)

    print("\nAll done.")


if __name__ == "__main__":
    main()
