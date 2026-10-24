# Claude-Video-Journalist

**A Claude Code skill that turns TikToks, Reels, Shorts and other short videos into evidence-backed Markdown your AI agents can actually use.**

Give it a video file, a folder or a URL. You get an index, one claim card per video, a faithful article, and the transcript plus on-screen text as evidence. Every number in a card points to the second it appears in the video and is checked against both what was said and what was shown. Your agent reads the card, not the whole film.

Runs on your machine. ffmpeg, Whisper and OCR do the boring part; **one Claude CLI call per new video** writes the card. No server, no API key in the repo, no uploading videos anywhere.

Polish readers: [README.pl.md](README.pl.md). Last updated: 2026-10-24. Version 0.1.0.

---

## What is a claim card?

A claim card is a short Markdown file (about 600 tokens) that records what a video's author claims, the numbers behind it with timestamps, how the author says it was tested, and what the author did not tell you. It starts life as `status: untested`, because a video is a claim, not a fact. Your agent can test the claim and write the result back.

```
OUTPUT/clips/
  INDEX.md                  id | profile | lang | status | thesis | domain | link
  cards/<id>.md             claim, reported numbers (@s), method as stated, gaps, cautions
  articles/<id>.md          what was said and shown, in order, with a table of slide data
  archive/<id>.tx.md        transcript in [mm:ss] blocks (open only to verify)
  archive/<id>.screen.md    de-duplicated on-screen text with first/last time seen
```

A complete example, made from the invented 48-second sample in this repo, is in [`examples/sample/OUTPUT`](examples/sample/OUTPUT). Yes, the trading strategy in it is fictional. So is the index it trades. We checked.

## Who this is for

- You collect reels, shorts and clips as research and want them in a Claude Project without re-watching anything.
- You run a Claude agent (trading research, product research, course notes, competitive intel) and want it fed claims with sources instead of vibes.
- You want "video to Markdown" that an agent can audit, including when the speaker misquotes their own slide.

## How it is different from "video to transcript" scripts

| | Typical transcript script | Claude-Video-Journalist |
|---|---|---|
| Output | one long text per video | index + card + article + evidence files |
| Numbers | wherever they fall in the text | each with `@s`, checked speech vs screen (`number_check`) |
| On-screen text | ignored or mixed in | OCR'd, de-duplicated, timestamped, used as evidence |
| Things the model made up | you find out later | a validator in code rejects numbers, quotes, names and table labels with no source |
| Claims | presented as summary | presented as the author's hypothesis with a status lifecycle |
| Language | often translated | kept as spoken; quotes stay quotes |
| Re-runs | pay again | cached by SHA-256, rebuild for free after code changes |

**What a card does not do:** it does not make a short clip cheaper to load. Across 82 cards from earlier runs, a card averaged about 630 tokens (characters / 4, an estimate), while the raw transcript archive averaged about 370 and the OCR archive about 390. For one- to two-minute clips the card is bigger than the transcript. What you buy is structure, evidence and loading on demand: an agent reads one `INDEX.md` instead of 80 transcripts and opens the archive only to check a number. The saving on long videos is not measured yet.

## Measured so far (read before trusting it)

- Invented sample, 48 s: one Claude call, **0.0457 USD-equivalent**, 0 coverage problems. The validator made 3 rejections, 2 of them wrong (a table label). That is a 66.7% false-rejection rate on three events, which tells you more about the weakness than about the rate.
- Earlier runs on about 80 real short videos (not in this repo): 0 coverage violations, false-rejection rate 5.4% (target 3%), screen attribution 100%, 30 of 30 numbers in reviewed cards traced to the source, 0.10 to 0.14 USD-equivalent per clip. Quality was judged in 8 independent AI reviews over four rounds; the last averaged 80/100 on a real batch. Those figures come from project notes, so you cannot reproduce them from this repo.
- It reports what a video claims. It does not check whether the claim is true. Whisper can mishear; every archive says `verified_by_ear: false` until a human listens.

## Install and run

```bash
git clone <repository-url> Claude-Video-Journalist && cd Claude-Video-Journalist
./install.sh                                   # uv, ffmpeg, yt-dlp, Python packages (details: install.md)
uv run python -m vjournalist preflight         # checks ffmpeg, whisper, claude, yt-dlp
uv run python -m vjournalist read https://example.com/some-video   # or a file, or a folder
```

Needs the Claude Code CLI logged in (`claude auth login`). First run downloads the Whisper `small` model (about 460 MB). Commands: `read`, `rebuild`, `index`, `check`, `tx`, `preflight`. `read --dry-run` lists what would be analysed before anything is spent.

URLs go through yt-dlp. If the uploader supplied captions in the video's own language, they replace Whisper (`asr: platform_captions` in the archive header). Automatic captions are not used.

## The two skills

| Skill | For | Needs |
|---|---|---|
| [`video-read`](skills/video-read/SKILL.md) | producing the files above from a file, folder or URL | this repository's Python package |
| [`claim-cards`](skills/claim-cards/SKILL.md) | an agent that consumes the files: index first, plan a test from a card, verify a number with `tx`, record results | nothing, plain text |

Install into Claude Code with `./install.sh --skills` (links both into `~/.claude/skills/`), copy the two folders yourself, or build a `.skill` package with the skill-creator tooling. A `.skill` file holds only instructions and thin scripts, so set `VJOURNALIST_HOME` to your clone. Details in [install.md](install.md).

## How to use the output in a Claude Project

1. Upload `INDEX.md` and the `cards/` folder. That is the working set.
2. Upload `articles/` only for the topics you care about.
3. Leave `archive/` on disk. The `claim-cards` skill tells the agent to open a transcript block only when it needs to verify one number.
4. When the agent tests a claim, it moves the card from `untested` to `in_test` and then to `confirmed` or `rejected`, and writes what it found in `agent_notes`. `rebuild` will not overwrite a card an agent has touched.

## Frequently asked questions

**Does it work with YouTube, TikTok, Instagram Reels and local files?**
Yes. URLs are fetched with yt-dlp; local files and whole folders work without network.

**Does it translate?**
No. An English video gives English files, a Polish one gives Polish files. Translation was tried and removed: it cost tokens and turned quotes into paraphrases.

**How much does one video cost?**
One Claude CLI call per new video, 0.05 to 0.14 USD-equivalent in our runs, counted against your Claude subscription. Re-running the same file costs nothing.

**Can I use this for a trading or research agent?**
That was the first use. The `analysis` profile records reported figures, stated method and the gaps you must fill before you can reproduce a test. Treat every card as the author's claim; the status field exists so your agent keeps it honest.

**Is the video uploaded anywhere?**
No. Text and a few frames go to the Claude CLI; the video file stays on your machine.

**Does it analyse editing, music or style?**
No. This tool records content. Style analysis is a separate project.

## Tests and evals

`uv run pytest -q` and `uv run ruff check .` run without Whisper, network or a Claude login (ASR and OCR are mocked). `skills/*/evals/` holds four graded cases: an uncovered number is rejected; a planted 55.2 to 55.7 change becomes a `conflict`; the source language is kept; a test plan is built from the card alone. `tests/test_skill_evals.py` runs the deterministic half offline; graded runs need a model (`claude plugin eval skills/video-read`). `scripts/prepush_scan.sh` checks the repo for secrets, personal paths, e-mails, account names, video files and stray Polish before a push.

## Known limits

False rejections of correct table labels; the Whisper `small` model on noisy audio; the internal ids of the gap checks are Polish and mapped to English labels; chapter validation for videos over about 5 minutes is not calibrated; developed and used on macOS, while CI runs only the unit tests on Linux. Planned work: [ROADMAP.md](ROADMAP.md). History: [CHANGELOG.md](CHANGELOG.md).

## License

MIT, see [LICENSE](LICENSE). Only process videos you have the right to process. The tool downloads locally and sends text and a few frames to the Claude CLI, never the video file.

---

*Keywords for the humans and robots who search: Claude Code skill, Claude skills, video to Markdown, TikTok transcript, Instagram Reels transcript, YouTube Shorts notes, knowledge base for AI agents, claim cards, evidence-backed summaries, local Whisper, OCR on-screen text.*
