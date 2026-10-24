#!/usr/bin/env bash
# Install the dependencies of Claude-Video-Journalist. Run from the repository root.
#   ./install.sh                 python environment (uv sync) + check ffmpeg, yt-dlp, claude
#   ./install.sh --skills        also link the two skills into ~/.claude/skills
#   ./install.sh --dry-run       print what would be done
# Nothing here uses sudo. Missing system tools are installed with Homebrew when it is present, otherwise
# the script prints the command to run yourself.
set -eu

DRY=0; SKILLS=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --skills) SKILLS=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
run() { echo "+ $*"; if [ "$DRY" -eq 0 ]; then "$@"; fi; }
have() { command -v "$1" >/dev/null 2>&1; }

need_brew() { # tool, brew formula
  if have "$1"; then echo "ok: $1"; return; fi
  if have brew; then run brew install "$2"; else echo "missing: $1 (install it, e.g. your package manager's '$2')"; fi
}

if ! have uv; then
  if have brew; then run brew install uv; else echo "missing: uv (https://docs.astral.sh/uv/)"; fi
else echo "ok: uv"; fi
need_brew ffmpeg ffmpeg
need_brew yt-dlp yt-dlp   # only used for URL input
have claude && echo "ok: claude CLI" || echo "missing: Claude Code CLI (https://claude.com/claude-code), log in with: claude auth login"

if have uv; then run uv sync --project "$HERE"; fi

if [ "$SKILLS" -eq 1 ]; then
  run mkdir -p "$HOME/.claude/skills"
  for skill in video-read claim-cards; do
    run ln -sfn "$HERE/skills/$skill" "$HOME/.claude/skills/$skill"
  done
  echo "Skills linked. video-read finds the project through VJOURNALIST_HOME or its own location:"
  echo "  export VJOURNALIST_HOME=\"$HERE\""
fi

echo
echo "Next: uv run python -m vjournalist preflight"
echo "The first read downloads the Whisper 'small' model (about 460 MB) into data/models."
