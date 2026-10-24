# Installation

Needs macOS or Linux, Python 3.11 (uv provides it), ffmpeg, and the Claude Code CLI logged in (`claude auth login`). yt-dlp is only needed for URL input.

```bash
git clone <repository-url> Claude-Video-Journalist && cd Claude-Video-Journalist
./install.sh                      # add --skills to link the skills into ~/.claude/skills; --dry-run to preview
uv run python -m vjournalist preflight
uv run python -m vjournalist read <video file | folder | URL>
```

## What `install.sh` does

| Step | Command it runs (or prints if Homebrew is missing) |
|---|---|
| uv | `brew install uv` |
| ffmpeg | `brew install ffmpeg` |
| yt-dlp (URL input) | `brew install yt-dlp` |
| Python packages | `uv sync` (faster-whisper, rapidocr-onnxruntime, opencv, scenedetect, ...) |
| Skills (`--skills`) | `ln -sfn skills/<name> ~/.claude/skills/<name>` for `video-read` and `claim-cards` |

Without Homebrew install the tools with your package manager; `preflight` tells you what is still missing.

## Installing the skills without the script

- Copy or link `skills/video-read` and `skills/claim-cards` into `~/.claude/skills/` (user level) or `<project>/.claude/skills/` (one project).
- Or package them: `python -m scripts.package_skill skills/video-read` from the skill-creator skill's folder gives a `.skill` file. A `.skill` file carries only the instructions and thin scripts, not the Python package: set `VJOURNALIST_HOME` to the clone so the scripts find it.
- `claim-cards` is plain text and needs nothing but the files it reads.

## First run

The first `read` downloads the Whisper `small` model (about 460 MB) into `data/models`; later runs are offline except for the Claude CLI call. `data/` (cache, work files, models) stays out of git.

## Troubleshooting

- `MISS claude`: install the Claude Code CLI and run `claude auth login`.
- `MISS whisper`: `uv sync` did not finish; rerun `./install.sh`.
- `OPT yt-dlp`: optional; install it to read URLs.
- A video longer than `limits.max_video_seconds` (3600) is refused; change it in `config.yaml`.
