# mp3_to_text.py
import os
import whisper
from pathlib import Path

# Defaults (change if you want)
DEFAULT_AUDIO_DIR = "/path/saved_mp3"
DEFAULT_OUT_DIR = "/path/transcripts"
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mkv", ".webm"}

# Whisper model to use — options: tiny, base, small, medium, large
# 'small' is recommended for 4GB VRAM
DEFAULT_MODEL = "small"


def transcribe_audio(audio_path: Path, out_dir: Path, model):
    """Transcribe audio file and save as .txt in output folder."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / (audio_path.stem + ".txt")

    print(f"   Detecting language and transcribing...")
    result = model.transcribe(
        str(audio_path),
        task="transcribe",       # 'transcribe' keeps original language
                                 # change to 'translate' to force output in English
        verbose=False
    )

    detected_lang = result.get("language", "unknown")
    print(f"   Detected language: {detected_lang}")

    # Write transcript to text file
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"Audio File : {audio_path.name}\n")
        f.write(f"Language   : {detected_lang}\n")
        f.write(f"Model Used : {DEFAULT_MODEL}\n")
        f.write("-" * 60 + "\n\n")
        f.write(result["text"].strip())
        f.write("\n")

    print(f"   Saved → {out_file.name}")


def main():
    audio_dir = input(f"Audio folder [{DEFAULT_AUDIO_DIR}]: ").strip() or DEFAULT_AUDIO_DIR
    out_dir   = input(f"Save transcripts to [{DEFAULT_OUT_DIR}]: ").strip() or DEFAULT_OUT_DIR

    audio_dir = Path(audio_dir)
    out_dir   = Path(out_dir)

    if not audio_dir.exists():
        print(f"Folder not found: {audio_dir}")
        return

    audio_files = [p for p in sorted(audio_dir.glob("*"))
                   if p.is_file() and p.suffix.lower() in AUDIO_EXTS]

    if not audio_files:
        print(f"No audio files found in {audio_dir}")
        return

    print(f"\nLoading Whisper model '{DEFAULT_MODEL}'... (downloads on first run)")
    model = whisper.load_model(DEFAULT_MODEL)
    print(f"Model loaded. Found {len(audio_files)} file(s) to transcribe.\n")

    for audio in audio_files:
        print(f"→ Processing: {audio.name}")
        try:
            transcribe_audio(audio, out_dir, model)
        except Exception as e:
            print(f"   Failed: {e}")

    print("\nDone! All transcripts saved.")


if __name__ == "__main__":
    main()