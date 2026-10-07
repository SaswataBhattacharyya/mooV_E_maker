import yt_dlp
import os

"""Downloads YouTube videos from a list of URLs in a text file,
ydl_opts = {
    # Prefer 720p mp4 when available; else bestvideo+bestaudio; else best
    # The first succeeds wins: 
    #  - try 720p mp4 progressive
    #  - try bestvideo up to 720 + bestaudio (will merge)
    #  - fallback to single 'best'
    'format': (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo[height<=720]+bestaudio/"
        "best[height<=720]/best"
    ),

    'outtmpl': os.path.join(output_folder, '%(title)s.%(ext)s'),

    # We DO want ffmpeg merges/remux
    'merge_output_format': 'mp4',   # try to end as mp4 when possible
    'postprocessors': [
        # If final stream isn’t mp4-compatible, yt-dlp may remux to mkv automatically.
        # This remuxer avoids re-encoding when possible.
        {'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'}
    ],

    'noplaylist': True,

    # SABR workaround: use the Android client (often avoids the “web https skipped” message)
    'extractor_args': {'youtube': {'player_client': ['android']}},

    # Optional: be quiet or verbose
    # 'quiet': True,
    # 'verbose': True,
}

def list_formats(url):
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        print(f"\n=== Formats for {info.get('title','?')} ===")
        for f in info['formats']:
            print(f"{f.get('format_id'):>6} | {f.get('ext'):>4} | {f.get('height')}p | "
                  f"vcodec={f.get('vcodec')} acodec={f.get('acodec')} url?={'yes' if f.get('url') else 'no'}")

"""

def download_videos_from_file(link_file_path, output_folder):
    with open(link_file_path, 'r') as f:
        video_links = [line.strip() for line in f if line.strip()]

    os.makedirs(output_folder, exist_ok=True)

    ydl_opts = {
        'format': (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[height<=720]+bestaudio/"
            "best[height<=720]/best"
        ),
        'outtmpl': os.path.join(output_folder, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'postprocessors': [
            {'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'}
        ],
        'noplaylist': True,
        'extractor_args': {'youtube': {'player_client': ['android']}},
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for link in video_links:
            try:
                print(f"Downloading: {link}")
                ydl.download([link])
            except Exception as e:
                print(f"Error downloading {link}: {e}")

if __name__ == "__main__":
    txt_path = input("Enter path to text file with YouTube URLs:\n").strip()
    output_dir = input("Enter output folder path:\n").strip()
    download_videos_from_file(txt_path, output_dir)
