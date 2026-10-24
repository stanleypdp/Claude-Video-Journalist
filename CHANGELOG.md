# Changelog

## 0.1.1 - 2026-10-24

- Last-frame extraction no longer depends on the ffmpeg build: some builds (Ubuntu CI) exit 0 and write no file when the seek lands past the last video frame, which skipped the step-back retry. A missing or empty file now counts as a miss and the scan steps back in 0.04 s increments for up to about 0.5 s. Regression test added.
- All error and log messages are in English (`Brak klatki...` was the last Polish one). Polish stays only in the language lexicon and in test fixtures. `scripts/prepush_scan.sh` has a new category, "Polish in error / log messages", that also covers files marked as Polish.
- `install.sh`: exit code 0 after a successful Homebrew install even when `brew` itself returns non-zero (judged by the tool being on PATH); exit code 1 only if a tool is still missing after `brew install`. Prints a note at the start that Homebrew may ask for confirmation.

## 0.1.0 - 2026-10-24

First public version.

- `video-read` skill and `vjournalist` package: video file, folder or URL -> `INDEX.md`, claim cards, articles, transcript and OCR archives. One Claude CLI call per new video, cache by SHA-256.
- URL input through the yt-dlp command line tool; uploader captions (`.vtt`/`.srt`) replace Whisper when their language matches the video's declared language (`asr: platform_captions` in the archive header).
- Coverage validator in code: every number needs a source in the transcript or OCR; on-screen quotes, table labels and proper names are checked against the source; `number_check` compares speech with screen.
- `claim-cards` skill: how an agent reads an index, plans a test from a card, verifies a number, and records results.
- Commands: `preflight`, `read`, `rebuild` (keeps cards whose status or notes were changed by an agent), `index`, `check`, `tx`.
- Source language is kept (English and Polish sources are tested); no translation.
- Evals for both skills in `skills/*/evals/`, trigger query sets, a synthetic example in `examples/sample/`.
