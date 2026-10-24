# Changelog

## 0.1.0 - 2026-10-24

First public version.

- `video-read` skill and `vjournalist` package: video file, folder or URL -> `INDEX.md`, claim cards, articles, transcript and OCR archives. One Claude CLI call per new video, cache by SHA-256.
- URL input through the yt-dlp command line tool; uploader captions (`.vtt`/`.srt`) replace Whisper when their language matches the video's declared language (`asr: platform_captions` in the archive header).
- Coverage validator in code: every number needs a source in the transcript or OCR; on-screen quotes, table labels and proper names are checked against the source; `number_check` compares speech with screen.
- `claim-cards` skill: how an agent reads an index, plans a test from a card, verifies a number, and records results.
- Commands: `preflight`, `read`, `rebuild` (keeps cards whose status or notes were changed by an agent), `index`, `check`, `tx`.
- Source language is kept (English and Polish sources are tested); no translation.
- Evals for both skills in `skills/*/evals/`, trigger query sets, a synthetic example in `examples/sample/`.
