# append_latest_firstpost.py
from pathlib import Path
import yt_dlp

CHANNEL_URL = "https://www.youtube.com/@Firstpost/videos"

def normalize_url(s: str) -> str:
    return s.strip()

def get_latest_video_url(channel_url: str) -> str:
    """
    Use yt-dlp to extract the newest upload from a channel page without downloading.
    """
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,   # don't resolve every video fully
        "playlistend": 1,       # only need the latest
        "noplaylist": False,    # channel pages are treated like playlists
        # Keep consistent with your existing setup style (optional):
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    entries = info.get("entries") or []
    if not entries:
        raise RuntimeError("No videos found (entries list is empty).")

    latest = entries[0]

    # Prefer direct webpage_url if present
    url = latest.get("webpage_url")
    if url:
        return url

    # Otherwise build from id
    vid = latest.get("id")
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"

    raise RuntimeError("Could not extract latest video URL (missing webpage_url and id).")

def main():
    txt_path_str = input("Enter path to text file (it will be created if missing):\n").strip()
    if not txt_path_str:
        print("No path provided.")
        return

    txt_path = Path(txt_path_str)
    txt_path.parent.mkdir(parents=True, exist_ok=True)

    existing = set()
    if txt_path.exists():
        for line in txt_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            u = normalize_url(line)
            if u:
                existing.add(u)

    try:
        latest_url = normalize_url(get_latest_video_url(CHANNEL_URL))
    except Exception as e:
        print(f"Failed to fetch latest video: {e}")
        return

    if latest_url in existing:
        print("No update: latest video link already present.")
        return

    # Append neatly
    with txt_path.open("a", encoding="utf-8") as f:
        if txt_path.exists() and txt_path.stat().st_size > 0:
            f.write("\n")
        f.write(latest_url)

    print("Updated. Appended:")
    print(latest_url)

if __name__ == "__main__":
    main()