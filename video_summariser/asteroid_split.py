#!/usr/bin/env python3
"""
asteroid_split.py

Batch split all MP3s under an input folder using Asteroid (speech separation models).
Outputs two MP3 files per input: source_1.mp3 and source_2.mp3

Important:
- Asteroid is primarily a *speech separation* toolkit (separating overlapping speakers),
  not a music stem separator. If you feed a song, the two outputs may not correspond
  cleanly to "vocals" and "instrumental".
- For vocals vs accompaniment, Demucs is usually the right tool.
- Still, this script does what you asked: takes MP3s and outputs 2 MP3s per file via Asteroid.

Requirements:
- pip install asteroid torch torchaudio soundfile
- ffmpeg available in PATH (for MP3 encoding)
"""

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import List

import torch
import torchaudio
import soundfile as sf
from asteroid.models import BaseModel


def has_bin(name: str) -> bool:
    return shutil.which(name) is not None


def load_audio_mono(path: Path, target_sr: int = 8000) -> tuple[torch.Tensor, int]:
    """
    Load audio, convert to mono, resample to target_sr for the speech-sep model (often 8kHz).
    """
    wav, sr = torchaudio.load(str(path))
    if wav.ndim == 2 and wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    if sr != target_sr:
        wav = torchaudio.functional.resample(wav, sr, target_sr)
        sr = target_sr
    return wav, sr


def save_mp3(wav: torch.Tensor, sr: int, out_mp3: Path, bitrate: str = "320k") -> None:
    """
    Save via temporary WAV + ffmpeg mp3 encode (more reliable than direct mp3 writers).
    """
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    tmp_wav = out_mp3.with_suffix(".tmp.wav")
    # soundfile expects shape (samples, channels) or (samples,) for mono.
    audio_np = wav.squeeze(0).detach().cpu().numpy()
    sf.write(str(tmp_wav), audio_np, sr, subtype="PCM_16")

    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-y",
        "-i", str(tmp_wav),
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,
        str(out_mp3),
    ]
    subprocess.run(cmd, check=True)
    tmp_wav.unlink(missing_ok=True)


AUDIO_EXTS = {".mp3"}


def list_mp3s(input_root: Path) -> List[Path]:
    return [p for p in sorted(input_root.rglob("*.mp3")) if p.is_file()]


def process_single_file(in_mp3: Path, out_dir: Path, model: BaseModel, device: str, bitrate: str = "320k", chunk_length: int = None) -> None:
    """
    Process a single MP3 file and save two separated sources.
    
    Args:
        chunk_length: If provided, process audio in chunks of this many seconds to save memory.
                     If None, process entire file at once.
    """
    print(f"Processing: {in_mp3.name}")
    
    wav, sr = load_audio_mono(in_mp3, target_sr=8000)
    
    # Calculate duration
    duration_sec = wav.shape[1] / sr
    print(f"   Duration: {duration_sec:.1f}s, Samples: {wav.shape[1]}")
    
    # If chunk_length is specified and file is long, process in chunks
    if chunk_length and duration_sec > chunk_length:
        print(f"   Processing in chunks of {chunk_length}s to save memory...")
        chunk_samples = int(chunk_length * sr)
        total_samples = wav.shape[1]
        
        # Pre-allocate output tensors on CPU
        src1_parts = []
        src2_parts = []
        
        for start_idx in range(0, total_samples, chunk_samples):
            end_idx = min(start_idx + chunk_samples, total_samples)
            chunk = wav[:, start_idx:end_idx].to(device)
            
            with torch.no_grad():
                est = model.separate(chunk)
            
            # Normalize shapes
            if est.ndim == 2:
                est = est.unsqueeze(1)
            elif est.ndim == 3:
                if est.shape[0] == 1:
                    est = est.squeeze(0).unsqueeze(1)
                else:
                    est = est[0].unsqueeze(1)
            
            if est.shape[0] < 2:
                raise RuntimeError(f"Expected 2 sources, got shape {tuple(est.shape)}")
            
            # Move to CPU immediately
            src1_parts.append(est[0].cpu())
            src2_parts.append(est[1].cpu())
            
            # Clear GPU memory
            del chunk, est
            if device == "cuda":
                torch.cuda.empty_cache()
            
            print(f"   Processed chunk: {start_idx/sr:.1f}s - {end_idx/sr:.1f}s")
        
        # Concatenate all chunks
        src1 = torch.cat(src1_parts, dim=1)
        src2 = torch.cat(src2_parts, dim=1)
        del src1_parts, src2_parts
    else:
        # Process entire file at once
        wav = wav.to(device)
        
        with torch.no_grad():
            est = model.separate(wav)
        
        # Normalize shapes to: (2, 1, T)
        if est.ndim == 2:
            est = est.unsqueeze(1)
        elif est.ndim == 3:
            if est.shape[0] == 1:
                est = est.squeeze(0).unsqueeze(1)
            else:
                est = est[0].unsqueeze(1)
        
        if est.shape[0] < 2:
            raise RuntimeError(f"Expected 2 sources, got shape {tuple(est.shape)}")
        
        src1 = est[0].cpu()  # (1, T) - move to CPU immediately
        src2 = est[1].cpu()
        
        # Clear GPU memory
        del wav, est
        if device == "cuda":
            torch.cuda.empty_cache()
    
    out1 = out_dir / f"{in_mp3.stem}_source1.mp3"
    out2 = out_dir / f"{in_mp3.stem}_source2.mp3"
    
    save_mp3(src1, sr, out1, bitrate=bitrate)
    save_mp3(src2, sr, out2, bitrate=bitrate)
    
    # Clear CPU tensors too
    del src1, src2
    
    print(f"   Saved: {out1.name}, {out2.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_root", required=True, help="Folder containing mp3 files (recursively).")
    ap.add_argument("--output_root", required=True, help="Folder to write split mp3s (preserve structure).")
    ap.add_argument("--model_id", default="JorisCos/ConvTasNet_Libri2Mix_sepclean_8k",
                    help="Asteroid pretrained model id from Hugging Face.")
    ap.add_argument("--mp3_bitrate", default="320k", help="MP3 bitrate (e.g. 192k/256k/320k).")
    ap.add_argument("--device", default=None, help="cpu or cuda (optional, auto-detects if not provided).")
    ap.add_argument("--chunk_length", type=int, default=None,
                    help="Process long files in chunks of N seconds to save GPU memory (e.g. 60 for 60-second chunks).")
    args = ap.parse_args()

    if not has_bin("ffmpeg"):
        raise SystemExit("ffmpeg not found. Install ffmpeg to write MP3 outputs.")

    input_root = Path(args.input_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()

    if not input_root.exists():
        raise SystemExit(f"Input root does not exist: {input_root}")

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Loading model {args.model_id} on {device} ...")
    model = BaseModel.from_pretrained(args.model_id)
    model.to(device)
    model.eval()

    mp3s = list_mp3s(input_root)
    if not mp3s:
        raise SystemExit(f"No mp3 files found under: {input_root}")

    print(f"Found {len(mp3s)} MP3 file(s) to process\n")

    for mp3 in mp3s:
        rel = mp3.relative_to(input_root)
        out_dir = output_root / rel.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n=== Asteroid: {rel} ===")
        try:
            process_single_file(mp3, out_dir, model, device, bitrate=args.mp3_bitrate, chunk_length=args.chunk_length)
            # Clear GPU cache after each file to prevent memory buildup
            if device == "cuda":
                torch.cuda.empty_cache()
        except Exception as e:
            print(f"   ERROR processing {mp3.name}: {e}")
            # Clear cache even on error
            if device == "cuda":
                torch.cuda.empty_cache()
            continue

    print("\nAll done.")


if __name__ == "__main__":
    main()
