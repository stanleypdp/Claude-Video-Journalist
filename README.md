# Claude-Video-Journalist

**Turn short videos into evidence-backed knowledge for Claude agents.**

A video (file, folder or URL) goes in. Out come plain Markdown files an agent can load cheaply and check: an index, one claim card per video, a faithful article, and the transcript and on-screen text as evidence. Every number in a card is traced to a second in the video, and checked against both what is said and what is shown.

It runs on your machine: ffmpeg, faster-whisper and OCR do the mechanical work; **one Claude CLI call per new video** writes the card. No server, no API key in the repo. Polski: [README.pl.md](README.pl.md).

```
OUTPUT/clips/
  INDEX.md                      id | profile | lang | status | thesis | domain | link
  cards/<id>.md                 the claim card: thesis, reported numbers (with @s), method, gaps
  articles/<id>.md              what was said and shown, in order, with a table of slide data
  archive/<id>.tx.md            transcript in [mm:ss] blocks (open only to verify)
  archive/<id>.screen.md        de-duplicated on-screen text with first/last time seen
```

A real output, made from the invented sample in this repo, is in [`examples/sample/OUTPUT`](examples/sample/OUTPUT).

## What is different from "video to transcript/summary" scripts

1. **Output shaped for an agent, not for a reader.** The agent reads `INDEX.md`, opens only the cards it needs, and opens the archive only to verify a number. Across 82 cards from earlier runs, a card averaged about 630 tokens (characters / 4, an estimate); the matching transcript archive averaged about 370 and the OCR archive about 390. So for clips of one to two minutes a card is *not* smaller than the raw transcript. What it buys is structure (claim, numbers, method, gaps) and loading on demand. The saving for long videos is not measured here.
2. **Evidence on every number.** Each reported number carries `@s`, the second it appears. `number_check` records whether it was found in speech, on screen or both, and flags `conflict(OCR:x)` when they disagree. A validator in code (not the model) rejects any number that exists in neither the transcript nor the OCR, removes on-screen quotes that are not on screen, and checks proper names and table labels against the source. Nothing from outside the material is added.
3. **Claims are hypotheses with a lifecycle.** Every card starts as `status: untested`, `source_reliability: unverified_claim` ("according to the author"). A consuming agent moves it through `untested -> in_test -> confirmed | rejected` and records results in `agent_notes`; `rebuild` will not overwrite a card an agent has touched.
4. **Content, not style.** It records what the video says and shows. No editing, music or camera analysis.
5. **Source language is kept.** English video gives English files, Polish gives Polish. No translation; quotes stay quotes. (Tested for English and Polish.)
6. **Local, one paid call per video, cached by SHA-256.** The same file is never analysed twice. Rebuilding cards after a code change reads the cache and costs nothing.

## Measured so far (read this before trusting it)

- On the invented sample (`examples/sample`, 48 s): one Claude call, **0.0457 USD-equivalent**, 0 coverage problems from `check`. In the same run the validator made 3 rejections, 2 of which removed correct content (a table label), i.e. `false_rejection_rate` was 66.7% on 3 rejections - a sample too small to mean much, but a real weakness.
- Earlier runs on about 80 real short videos (not included in the repo): 0 coverage violations, `false_rejection_rate` 5.4% (target 3%), `screen_attribution_ok` 100%, 30 of 30 numbers in the reviewed cards covered by the source, 0.10-0.14 USD-equivalent per clip. Quality was judged in 8 independent AI reviews over four rounds (the last scored 80 points on average on a real batch). Those figures come from the project's own notes; the clips are not published, so you cannot reproduce them from this repo.
- It reports what a video claims. It does not check whether the claim is true, and ASR can mishear (`verified_by_ear: false` in every archive).

## Install and run

```bash
git clone <repository-url> Claude-Video-Journalist && cd Claude-Video-Journalist
./install.sh                                     # uv, ffmpeg, yt-dlp, Python packages (details: install.md)
uv run python -m vjournalist preflight           # ffmpeg, whisper, claude, yt-dlp
uv run python -m vjournalist read https://example.com/some-video   # or a file, or a folder
```

Needs the Claude Code CLI logged in (`claude auth login`). The first run downloads the Whisper `small` model (about 460 MB). Commands: `read`, `rebuild`, `index`, `check`, `tx`, `preflight`. `read --dry-run` lists what would be analysed before anything is spent.

URLs use the yt-dlp command line tool. If the uploader supplied captions in the video's own language they replace Whisper (`asr: platform_captions` in the archive header); automatic captions are not used.

## The two skills

| Skill | For | Needs |
|---|---|---|
| [`video-read`](skills/video-read/SKILL.md) | producing the files above from a file, folder or URL | this repository's Python package |
| [`claim-cards`](skills/claim-cards/SKILL.md) | an agent that consumes the files: index first, plan a test from a card, verify a number with `tx`, record results | nothing (plain text) |

Install into Claude Code with `./install.sh --skills` (links them into `~/.claude/skills/`), copy the two folders yourself, or build a `.skill` package with the skill-creator tooling. A `.skill` file holds only instructions and thin scripts, so set `VJOURNALIST_HOME` to the clone. Details in [install.md](install.md).

## Tests and evals

`uv run pytest -q` and `uv run ruff check .` run without Whisper, network or a Claude login (ASR and OCR are mocked). `skills/*/evals/` holds four graded cases (uncovered number is rejected; a planted 55.2 -> 55.7 becomes a conflict; the source language is kept; a plan is built from the card only) plus 20 trigger queries per skill. `tests/test_skill_evals.py` runs the deterministic half of every case offline; the graded runs need a model (`claude plugin eval skills/video-read`). `scripts/prepush_scan.sh` checks the repo for secrets, personal paths, e-mails, account names, video files and Polish text before a push.

## Known limits

Main ones: false rejections of correct table labels; the Whisper `small` model on noisy audio; the internal ids of the gap checks are Polish and mapped to English labels; chapter validation for videos over about 5 minutes is not calibrated; developed and used on macOS, while CI runs only the unit tests on Linux. What is planned: [ROADMAP.md](ROADMAP.md). Version history: [CHANGELOG.md](CHANGELOG.md).

## License

MIT, see [LICENSE](LICENSE). Only process videos you have the right to process; the tool downloads locally and sends text and a few frames to the Claude CLI, never the video file.
