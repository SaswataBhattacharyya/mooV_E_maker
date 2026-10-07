import os
import shutil
import subprocess
from pathlib import Path

# Defaults (change if you want)
DEFAULT_AUDIO_DIR = "/path/input_audio"
DEFAULT_OUT_DIR = "/path/compressed_audio"

AUDIO_EXTS = {".wav", ".mp3"}

# Compression settings
TARGET_MP3_BITRATE = "96k"   # 64k, 96k, 128k
WAV_CODEC = "adpcm_ima_wav"  # compressed WAV (optional)

def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def compress_audio(audio_path: Path, out_dir: Path, to_mp3: bool = True):
    """
    Compress an audio file.
    - MP3 → lower bitrate MP3
    - WAV → MP3 (default) or compressed WAV
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    if to_mp3:
        out_file = out_dir / (audio_path.stem + ".mp3")
        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-y",
            "-i", str(audio_path),
            "-map_metadata", "0",
            "-vn",
            "-acodec", "libmp3lame",
            "-ab", TARGET_MP3_BITRATE,
            str(out_file)
        ]
    else:
        out_file = out_dir / (audio_path.stem + ".wav")
        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-y",
            "-i", str(audio_path),
            "-vn",
            "-acodec", WAV_CODEC,
            str(out_file)
        ]

    subprocess.run(cmd, check=True)

def main():
    audio_dir = input(f"Audio folder [{DEFAULT_AUDIO_DIR}]: ").strip() or DEFAULT_AUDIO_DIR
    out_dir = input(f"Save compressed audio to [{DEFAULT_OUT_DIR}]: ").strip() or DEFAULT_OUT_DIR

    audio_dir = Path(audio_dir)
    out_dir = Path(out_dir)

    if not has_ffmpeg():
        print("ffmpeg not found. Please install ffmpeg and retry.")
        return

    audios = [
        p for p in sorted(audio_dir.glob("*"))
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    ]

    if not audios:
        print(f"No audio files found in {audio_dir}")
        return

    for audio in audios:
        print(f"→ Compressing: {audio.name}")
        try:
            # WAV → MP3, MP3 → MP3 (lower bitrate)
            compress_audio(audio, out_dir, to_mp3=True)
            print("   Saved.")
        except subprocess.CalledProcessError as e:
            print(f"   Failed: {e}")

if __name__ == "__main__":
    main()
