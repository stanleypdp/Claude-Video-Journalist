"""Platform captions replace ASR; URL input is exercised with a fake yt-dlp (no network in tests)."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from vjournalist.bridge.transcript import render_archive
from vjournalist.pipeline import media
from vjournalist.pipeline.captions import caption_language, parse_captions, transcript_from_captions
from vjournalist.pipeline.download import fetch_url, is_url, pick_captions

VTT = """WEBVTT

NOTE made by the uploader

00:00:01.000 --> 00:00:03.500
We replayed <c>1096</c> orders.

00:00:03.500 --> 00:00:06.000
We replayed 1096 orders.

00:00:06.000 --> 00:00:08.000 align:start
The edge was 2.6 &amp; small.
"""

SRT = """1
00:00:00,500 --> 00:00:02,000
First line

2
00:01:02,250 --> 00:01:04,000
Second
line
"""


def test_vtt_tags_entities_and_rolling_duplicates():
    segments = parse_captions(VTT)
    assert segments == [
        {"start": 1.0, "end": 6.0, "text": "We replayed 1096 orders."},
        {"start": 6.0, "end": 8.0, "text": "The edge was 2.6 & small."},
    ]


def test_srt_multiline_cue_and_minutes():
    assert parse_captions(SRT) == [
        {"start": 0.5, "end": 2.0, "text": "First line"},
        {"start": 62.25, "end": 64.0, "text": "Second line"},
    ]


def test_caption_language_from_file_name(tmp_path):
    assert caption_language("video.en.vtt") == "en" and caption_language("video.pt-BR.srt") == "pt-BR"
    assert caption_language("video.vtt") is None
    path = tmp_path / "video.pl.vtt"
    path.write_text(VTT)
    transcript = transcript_from_captions(path)
    assert transcript["engine"] == "platform_captions" and transcript["language"] == "pl"
    with pytest.raises(ValueError):
        (tmp_path / "empty.en.vtt").write_text("WEBVTT\n")
        transcript_from_captions(tmp_path / "empty.en.vtt")


def test_captions_skip_whisper_and_word_timestamp_pass(tmp_path, config, monkeypatch):
    path = tmp_path / "video.en.vtt"
    path.write_text(VTT)
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", None)  # whisper must not be imported
    metadata = {"has_audio": True}
    transcript = media.transcribe("unused.mp4", tmp_path, metadata, config, captions=path)
    assert transcript["segments"][0]["text"] == "We replayed 1096 orders."
    assert "words" not in transcript["segments"][0]


def test_archive_header_says_platform_captions():
    text = render_archive("x", {"language": "en"}, [], 8, "platform_captions", {})
    assert "asr: platform_captions" in text


def test_pick_captions_needs_a_matching_declared_language(tmp_path):
    (tmp_path / "video.en.vtt").write_text(VTT)
    (tmp_path / "video.de.vtt").write_text(VTT)
    assert pick_captions(tmp_path, {"language": "en"}).name == "video.en.vtt"
    assert pick_captions(tmp_path, {"language": "fr"}) is None  # a translated track is never trusted
    assert pick_captions(tmp_path, {}) is None  # two tracks and no declared language
    (tmp_path / "video.de.vtt").unlink()
    assert pick_captions(tmp_path, {}).name == "video.en.vtt"


def test_is_url():
    assert is_url("https://example.com/v/1") and not is_url("/tmp/clip.mp4") and not is_url("clip.mp4")


def fake_run(files, info, code=0):
    def run(command, **_):
        out = command[command.index("-o") + 1].replace("video.%(ext)s", "")
        directory = __import__("pathlib").Path(out)
        for name, content in files.items():
            (directory / name).write_text(content)
        if info is not None:
            (directory / "video.info.json").write_text(json.dumps(info))
        return SimpleNamespace(returncode=code, stdout="", stderr="")

    return run


def test_fetch_url_returns_video_captions_and_title(tmp_path):
    run = fake_run({"video.mp4": "x", "video.en.vtt": VTT}, {"title": "Fictional clip", "language": "en"})
    video, captions, title = fetch_url("https://example.com/v/1", tmp_path, 10**9, run=run, which=lambda _: "/bin/yt-dlp")
    assert video.name == "video.mp4" and captions.name == "video.en.vtt" and title == "Fictional clip"


def test_fetch_url_failure_hides_the_url(tmp_path):
    leaky = "https://example.com/v/1?q=LEAKME"
    with pytest.raises(RuntimeError) as error:
        fetch_url(leaky, tmp_path, 10**9, run=fake_run({}, None, code=1), which=lambda _: "/bin/yt-dlp")
    assert "LEAKME" not in str(error.value)
    with pytest.raises(RuntimeError, match="yt-dlp not found"):
        fetch_url(leaky, tmp_path, 10**9, run=subprocess.run, which=lambda _: None)


def test_cli_read_single_file_uses_cwd_output(tmp_path, monkeypatch, capsys):
    from vjournalist import cli, read_batch

    clip = tmp_path / "My Clip.mp4"
    clip.write_bytes(b"x")
    seen = {}

    def fake_read_folder(label, config, **kwargs):
        seen.update(label=label, files=kwargs["files"], bridge=config.bridge, captions=kwargs["captions"])
        summary = dict.fromkeys(("files", "analyzed", "cache", "duplicates", "errors", "pending"), 0)
        return {"summary": {**summary, "cost_usd": 0, "historical_cost_usd_cache": 0}, "rows": [], "paused_s": 0, "folder": str(label)}

    monkeypatch.setattr(read_batch, "read_folder", fake_read_folder)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BRIDGE_DIR", raising=False)
    assert cli.main(["read", str(clip), "--captions", str(tmp_path / "c.en.vtt")]) == 0
    assert seen["files"] == [clip.resolve()] and seen["bridge"] == (tmp_path / "OUTPUT" / "my-clip").resolve()
    assert seen["captions"] == {clip.resolve(): tmp_path / "c.en.vtt"}
    capsys.readouterr()


def test_prepare_with_local_video_and_captions_writes_platform_captions_header(video, config, tmp_path):
    from vjournalist.bridge.transcript import write_archives

    captions = tmp_path / "clip.en.vtt"
    captions.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nThe edge was 2.6 points.\n")
    work = tmp_path / "work"
    work.mkdir()
    common = media.prepare(video, work, config, lambda *_: None, captions=captions)
    assert common["transcript"]["engine"] == "platform_captions"
    write_archives("clip-1", common, tmp_path / "OUTPUT")
    archive = (tmp_path / "OUTPUT" / "archive" / "clip-1.tx.md").read_text()
    assert "asr: platform_captions" in archive and "lang: en" in archive and "The edge was 2.6 points." in archive
