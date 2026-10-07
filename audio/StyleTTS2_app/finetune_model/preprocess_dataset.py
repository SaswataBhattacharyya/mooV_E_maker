#!/usr/bin/env python3
"""
Preprocess audio/text pairs for StyleTTS2 fine-tuning.

Outputs:
- work_dir/
    wavs/{speaker}/{utt_id}.wav   (24 kHz mono PCM16)
    filelists/{speaker}_train.txt
    filelists/{speaker}_val.txt
    manifest.csv                  (utt_id,speaker_id,speaker_name,wav_path,text)
    speakers.json                 ({speaker_name: speaker_id})

Filelist format expected by StyleTTS2: "relative/path.wav|transcription|speaker_id"
`relative/path.wav` is relative to root_path you pass in the config (we use work_dir/wavs).
"""

import argparse
import csv
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import torchaudio
from torchaudio.transforms import Resample
from tqdm import tqdm


DEFAULT_SR = 24000  # matches StyleTTS2 configs


@dataclass
class Example:
    speaker_name: str
    stem: str
    text: str
    audio_path: Path
    out_relpath: Path


def normalize_text(text: str) -> str:
    """Strip and collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip())


def find_pairs(audio_dir: Path, text_dir: Path) -> Tuple[List[Tuple[str, Path, Path]], List[str]]:
    """
    Match audio/text by stem.
    Returns list of (stem, audio_path, text_path) and list of missing stems.
    """
    audio_files = {p.stem: p for p in audio_dir.glob("*") if p.is_file()}
    text_files = {p.stem: p for p in text_dir.glob("*") if p.is_file()}

    pairs = []
    missing = []
    for stem, a_path in audio_files.items():
        t_path = text_files.get(stem)
        if t_path:
            pairs.append((stem, a_path, t_path))
        else:
            missing.append(stem)
    return pairs, missing


def assign_speaker_ids(pairs: List[Tuple[str, Path, Path]]) -> Dict[str, int]:
    """Derive speaker names from stem prefix before first '_' and assign numeric IDs."""
    speakers = sorted({stem.split("_")[0] for stem, _, _ in pairs})
    return {name: idx for idx, name in enumerate(speakers)}


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def convert_audio(a_path: Path, out_path: Path, target_sr: int) -> None:
    """Load (supports mp3 via torchaudio) and save as mono PCM16 wav at target_sr."""
    wav, sr = torchaudio.load(a_path)
    if wav.dim() == 2 and wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    if sr != target_sr:
        wav = Resample(sr, target_sr)(wav)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(out_path, wav, target_sr, bits_per_sample=16)


def split_train_val(examples: List[Example], val_ratio: float) -> Tuple[List[Example], List[Example]]:
    per_spk: Dict[str, List[Example]] = defaultdict(list)
    for ex in examples:
        per_spk[ex.speaker_name].append(ex)

    train, val = [], []
    for spk, items in per_spk.items():
        n = len(items)
        val_count = max(1, int(n * val_ratio)) if n > 1 else 0
        val.extend(items[:val_count])
        train.extend(items[val_count:])
    return train, val


def write_manifest(manifest_path: Path, examples: List[Example], spk_map: Dict[str, int]) -> None:
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["utt_id", "speaker_id", "speaker_name", "wav_path", "text"])
        for ex in examples:
            writer.writerow([ex.stem, spk_map[ex.speaker_name], ex.speaker_name, str(ex.out_relpath), ex.text])


def write_filelist(path: Path, examples: List[Example], spk_map: Dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(f"{ex.out_relpath}|{ex.text}|{spk_map[ex.speaker_name]}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Preprocess dataset for StyleTTS2 finetuning",
        epilog="If arguments are omitted, you will be prompted interactively.")
    parser.add_argument("--data_root", type=Path, help="Root with audio/ and text/ subfolders")
    parser.add_argument("--work_dir", type=Path, help="Output directory")
    parser.add_argument("--sr", type=int, default=DEFAULT_SR, help="Target sample rate (default 24000)")
    parser.add_argument("--val_ratio", type=float, default=0.05, help="Validation split ratio per speaker")
    parser.add_argument("--dry_run", action="store_true", help="Only report stats, do not write outputs")
    args = parser.parse_args()

    # Interactive prompts for missing required paths
    if args.data_root is None:
        args.data_root = Path(input("Enter data_root (with audio/ and text/): ").strip())
    if args.work_dir is None:
        args.work_dir = Path(input("Enter work_dir (output directory): ").strip())
    if args.sr is None:
        sr_in = input(f"Target sample rate [default {DEFAULT_SR}]: ").strip()
        args.sr = int(sr_in) if sr_in else DEFAULT_SR
    if args.val_ratio is None:
        vr_in = input("Validation ratio per speaker [default 0.05]: ").strip()
        args.val_ratio = float(vr_in) if vr_in else 0.05

    audio_dir = args.data_root / "audio"
    text_dir = args.data_root / "text"
    assert audio_dir.is_dir(), f"Missing audio dir: {audio_dir}"
    assert text_dir.is_dir(), f"Missing text dir: {text_dir}"

    pairs, missing = find_pairs(audio_dir, text_dir)
    if not pairs:
        raise RuntimeError("No audio/text pairs found.")

    speaker_map = assign_speaker_ids(pairs)

    # Build examples
    examples: List[Example] = []
    for stem, a_path, t_path in pairs:
        speaker_name = stem.split("_")[0]
        text = normalize_text(load_text(t_path))
        out_relpath = Path(speaker_name) / f"{stem}.wav"
        examples.append(Example(speaker_name, stem, text, a_path, out_relpath))

    total = len(examples)
    print(f"Found {total} pairs across {len(speaker_map)} speakers.")
    if missing:
        print(f"Missing text for {len(missing)} audio files (will skip): {missing[:5]}{' ...' if len(missing) > 5 else ''}")

    if args.dry_run:
        per_spk = defaultdict(int)
        for ex in examples:
            per_spk[ex.speaker_name] += 1
        for spk, cnt in per_spk.items():
            print(f"Speaker {spk}: {cnt} items")
        return

    # Convert audio
    wav_root = args.work_dir / "wavs"
    for ex in tqdm(examples, desc="Converting audio"):
        out_path = wav_root / ex.out_relpath
        convert_audio(ex.audio_path, out_path, args.sr)

    # Split train/val
    train, val = split_train_val(examples, args.val_ratio)
    print(f"Train: {len(train)}  Val: {len(val)}")

    # Write manifests and filelists
    manifest_path = args.work_dir / "manifest.csv"
    write_manifest(manifest_path, examples, speaker_map)

    filelist_dir = args.work_dir / "filelists"
    for spk_name, spk_id in speaker_map.items():
        spk_train = [e for e in train if e.speaker_name == spk_name]
        spk_val = [e for e in val if e.speaker_name == spk_name]
        write_filelist(filelist_dir / f"{spk_name}_train.txt", spk_train, speaker_map)
        write_filelist(filelist_dir / f"{spk_name}_val.txt", spk_val, speaker_map)

    # Save speaker map
    (args.work_dir / "speakers.json").write_text(json.dumps(speaker_map, indent=2), encoding="utf-8")
    print(f"Saved speaker map to {args.work_dir / 'speakers.json'}")
    print("Done.")


if __name__ == "__main__":
    main()

