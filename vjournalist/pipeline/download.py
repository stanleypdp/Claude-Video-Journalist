"""URL input: download with the yt-dlp command line tool, plus the uploader's own captions if there are any.

Only captions written by the uploader are used (not the platform's automatic ones), and only when their
language matches the video's declared language, so a translated track is never mistaken for the speech.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

VIDEO_SUFFIXES = (".mp4", ".webm", ".mkv", ".mov", ".m4v")
CAPTION_SUFFIXES = (".vtt", ".srt")


def is_url(value):
    return urlparse(str(value)).scheme.lower() in ("http", "https")


def pick_captions(directory, info):
    """The one caption file that is safe to treat as the spoken transcript, else None."""
    from vjournalist.pipeline.captions import caption_language

    files = sorted(p for p in Path(directory).iterdir() if p.suffix in CAPTION_SUFFIXES)
    declared = (info.get("language") or "").split("-")[0].lower()
    if declared:
        for path in files:
            if (caption_language(path) or "").split("-")[0].lower() == declared:
                return path
        return None
    return files[0] if len(files) == 1 else None


def fetch_url(url, dest, max_bytes, run=subprocess.run, which=shutil.which):
    """Download `url` into `dest`. Returns (video_path, captions_path or None, title)."""
    binary = which("yt-dlp")
    if binary is None:
        raise RuntimeError("yt-dlp not found. Install it (see install.md) or download the video yourself.")
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=dest, prefix="download-"))
    command = [
        binary, "--no-playlist", "--no-progress", "--quiet", "--no-warnings",
        "-f", "bv*[height<=1920]+ba/b[height<=1920]", "--merge-output-format", "mp4",
        "--write-subs", "--sub-langs", "all,-live_chat", "--sub-format", "vtt/srt/best",
        "--write-info-json", "--max-filesize", str(max_bytes), "--socket-timeout", "30", "--retries", "1",
        "-o", str(work / "video.%(ext)s"), url,
    ]  # fmt: skip
    proc = run(command, capture_output=True, text=True, timeout=900)
    if proc.returncode:
        # The URL is left out of the message: it may carry tokens.
        raise RuntimeError(f"yt-dlp failed (exit code {proc.returncode}). Download the video yourself and pass the file.")
    videos = [p for p in work.iterdir() if p.suffix in VIDEO_SUFFIXES]
    if len(videos) != 1:
        raise ValueError("Download produced no single video file.")
    info_path = work / "video.info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    return videos[0], pick_captions(work, info), info.get("title") or "video"
