---
name: video-read
description: Turn a short video (local file, folder of videos, or a TikTok / Instagram / YouTube / Loom / direct URL) into evidence-backed Markdown that Claude agents can use as knowledge - an INDEX, one claim card per video, a faithful article, and a timestamped transcript and on-screen-text archive. Use this skill whenever the user wants to extract knowledge, claims, steps or numbers from a video or reel, make notes from a video for an agent, check what a creator actually says versus shows on screen, or says things like "read this reel", "pull the knowledge out of this clip", "what does this video claim", or "turn these videos into something my agent can use" - even if they never say "skill". Not for editing videos, subtitling, summarizing without evidence, or analysing visual style.
---

# video-read

Produces the files a `claim-cards` consumer reads. Everything runs on the user's machine (ffmpeg, faster-whisper, rapidocr); the only paid step is **one Claude CLI call per new video**, and a video already seen (same SHA-256) costs nothing.

## What you get

For a source `X` the output goes to `OUTPUT/X/` (details in `references/output-format.md`):

```
INDEX.md                 one row per video: id, profile, lang, status, thesis, domain, link to the card
cards/<id>.md            claim card (~600 tokens): thesis, reported numbers with `@s` locators, method, gaps
articles/<id>.md         faithful narration of speech and screen + a table of data shown on slides
archive/<id>.tx.md       transcript in [mm:ss] blocks (the evidence; open only to verify)
archive/<id>.screen.md   de-duplicated on-screen text (OCR) with first/last time seen
archive/<id>.rejections.md   what the code removed and why (diagnostics, not a source of facts)
```

## Run it

Check the environment once, then read. From this skill's `scripts/` folder:

```bash
python scripts/preflight.py                       # ffmpeg, whisper, claude (yt-dlp only for URLs)
python scripts/pipeline.py <file|folder|URL>      # preflight -> dry run -> read -> coverage check
```

The same steps individually: `read.py <file|folder|URL> [--dry-run] [--recursive] [--output DIR] [--captions FILE] [--no-wait]`, `check.py <OUTPUT/X>`, `rebuild.py <OUTPUT/X>`, `python -m vjournalist index <OUTPUT/X>`, `tx.py <id> --at 53 --window 20`. Equivalent: `python -m vjournalist <command>` inside the repo.

If `preflight` reports MISS, read `install.md` in the repository (it lists the one-line installs) instead of guessing. If the scripts say `vjournalist is not installed`, set `VJOURNALIST_HOME` to the clone.

Before a run on a folder, do the dry run and tell the user how many videos are new: each is one paid call (about 0.05-0.15 USD-equivalent on the user's subscription limits for a short clip; see `references/cost-and-cache.md`). Do not start a large batch the user did not ask for.

## Reading the report

`read` prints files, analyzed, from cache, duplicates, errors, pending, and cost. Report these numbers to the user as they are. Then run `check`: `OK ... 0 coverage problems` means every number in cards and articles exists in the transcript or OCR. Any listed problem is a defect to report, not to fix by hand.

Exit code 75 means the Claude CLI limit stopped the run with videos pending; running the same command again continues from the cache.

Quality metrics printed after a run: `false_rejection_rate` (rejections whose content was actually in the source), `screen_attribution_ok`, `not_in_ocr_per_card`. Quote them; do not interpret a small sample as a benchmark.

## Rules

- **Source language is kept.** An English video gives English files, a Polish video Polish files. Never translate cards or articles, and never ask for a translation as part of this skill.
- **No paid repairs.** If a card fails validation, the fix is code or `rebuild` (cache, zero calls), not another Claude call. Never call `claude -p` yourself; only `read` does.
- **Never upload other people's videos** to any service. URLs are downloaded locally with yt-dlp; only text and a few frames go to the Claude CLI.
- **Do not edit `reported`, `number_check` or archive files.** Consumers rely on them as the evidence.
- `rebuild` skips cards whose `status` or `agent_notes` a consumer has changed (it says how many it kept); `--overwrite` forces it and loses those results.
- Do not summarize or paraphrase the cards back to the user unless asked; point to `INDEX.md` and the card paths.
- Uploader captions (`.vtt`/`.srt`) replace Whisper only when they exist and match the video's language; the archive header then says `asr: platform_captions`.

## References

- `references/output-format.md` - every output file, header fields, how ids are built.
- `references/cost-and-cache.md` - what costs money, what is cached, how to redo a video, limits.
