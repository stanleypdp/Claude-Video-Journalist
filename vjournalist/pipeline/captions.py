"""Platform captions (WebVTT / SRT) as a transcript, used instead of ASR when the uploader supplied them."""

import html
import re
from pathlib import Path

TIME = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
)
TAGS = re.compile(r"<[^>]+>|\{[^}]*\}")


def _seconds(hours, minutes, seconds, millis):
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis.ljust(3, "0")) / 1000


def parse_captions(text):
    """WebVTT or SRT text -> [{start, end, text}]. Consecutive duplicate cues (rolling captions) are merged."""
    segments = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").lstrip("﻿")):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines or lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        index = next((i for i, line in enumerate(lines) if TIME.search(line)), None)
        if index is None:
            continue
        match = TIME.search(lines[index])
        start = _seconds(*match.group(1, 2, 3, 4))
        end = _seconds(*match.group(5, 6, 7, 8))
        words = re.sub(r"\s+", " ", html.unescape(TAGS.sub("", " ".join(lines[index + 1 :])))).strip()
        if not words or end <= start:
            continue
        if segments and segments[-1]["text"] == words and start - segments[-1]["end"] < 0.5:
            segments[-1]["end"] = end
            continue
        segments.append({"start": round(start, 3), "end": round(end, 3), "text": words})
    return segments


def caption_language(path):
    """`video.en.vtt` -> `en`; `video.pt-BR.srt` -> `pt-BR`; None when the name carries no code."""
    parts = Path(path).name.split(".")
    return parts[-2] if len(parts) >= 3 else None


def transcript_from_captions(path, language=None):
    """Transcript dict shaped like the ASR result; engine `platform_captions` marks the archive header."""
    path = Path(path)
    segments = parse_captions(path.read_text(encoding="utf-8", errors="replace"))
    if not segments:
        raise ValueError("The caption file has no usable cues.")
    code = language or caption_language(path) or "unknown"
    return {
        "engine": "platform_captions",
        "model": "",
        "language": code.split("-")[0].lower() if code != "unknown" else "unknown",
        "language_probability": 1.0,
        "segments": segments,
        "audio_kind": "unknown",
        "bpm": "unknown",
    }
