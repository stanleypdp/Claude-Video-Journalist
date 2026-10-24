import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from vjournalist.config import input_folders


def output_roots():
    """OUTPUT/<folder> for every configured input folder (where `read` writes)."""
    from vjournalist.read_batch import default_output

    return [default_output(folder) for folder in input_folders()]


def find_archive(id_, roots=None):
    for root in roots if roots is not None else output_roots():
        path = Path(root) / "archive" / f"{id_}.tx.md"
        if path.exists():
            return path
    return None


def preflight():
    """ffmpeg, whisper (package + local model), claude CLI, optional yt-dlp. No model call."""
    from vjournalist.config import Config

    config = Config.load()
    rows = []
    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        rows.append((tool, bool(found), found or "not in PATH (brew install ffmpeg)", True))
    try:
        import faster_whisper  # noqa: F401

        model = next((config.data / "models").glob(f"models--*faster-whisper-{config.whisper_model}"), None)
        rows.append((
            "whisper", True,
            f"faster-whisper, model {config.whisper_model}: "
            + (str(model) if model else f"not in {config.data / 'models'} (first use downloads it)"),
            True,
        ))  # fmt: skip
    except ImportError:
        rows.append(("whisper", False, "faster-whisper is not installed (see install.md)", True))
    binary = shutil.which(config.claude)
    detail = "Claude CLI not found"
    if binary:
        version = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30)
        detail = f"{binary} {version.stdout.strip()}"
    rows.append(("claude", binary is not None, detail, True))
    ytdlp = shutil.which("yt-dlp")
    rows.append(("yt-dlp", ytdlp is not None, ytdlp or "not installed (only needed for URL input)", False))
    for name, ok, detail, required in rows:
        print(f"{'OK  ' if ok else 'MISS' if required else 'OPT '} {name}: {detail}")
    return 0 if all(ok for _, ok, _, required in rows if required) else 1


def resolve_source(source, options, config):
    """-> (label for the report, files, captions {path: caption file}, output dir)."""
    from vjournalist.pipeline.download import fetch_url, is_url
    from vjournalist.read_batch import default_output

    if is_url(source):
        if options.dry_run:
            print("--dry-run does not download; pass a local file or folder.", file=sys.stderr)
            raise SystemExit(2)
        video, captions, title = fetch_url(source, config.data / "downloads", config.max_bytes)
        target = Path(options.output).expanduser() if options.output else default_output(video, title)
        return video.parent, [video], ({video: captions} if captions else None), target
    path = Path(source).expanduser()
    if path.is_dir():
        files, captions = None, None
    elif path.is_file():
        files = [path.resolve()]
        captions = {files[0]: Path(options.captions).expanduser()} if options.captions else None
    else:
        print(f"Not a file, folder or URL: {source}", file=sys.stderr)
        raise SystemExit(2)
    target = Path(options.output).expanduser() if options.output else default_output(path)
    return (path if path.is_dir() else path.resolve().parent), files, captions, target


def run_read(options, parser):
    from vjournalist.config import Config
    from vjournalist.read_batch import format_report, read_folder
    from vjournalist.service import analyze_video

    sources = [options.source] if options.source else [str(f) for f in input_folders()]
    if not sources:
        parser.error("Pass a folder, file or URL, or set input_folders in config.yaml")
    code = 0
    for source in sources:
        config = Config.load()
        label, files, captions, output = resolve_source(source, options, config)
        os.environ["BRIDGE_DIR"] = str(output)
        report = read_folder(
            label,
            Config.load(),
            analyze=analyze_video,
            recursive=options.recursive,
            dry_run=options.dry_run,
            wait=not options.no_wait,
            poll_s=options.poll_minutes * 60,
            max_wait_s=options.max_wait_hours * 3600,
            files=files,
            captions=captions,
        )
        print(format_report(report))
        print(f"Results (INDEX.md, articles/, cards/, archive/): {output.resolve()}")
        summary = report["summary"]
        code = max(code, 75 if summary["pending"] and not options.dry_run else 1 if summary["errors"] else 0)
    return code


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(
        prog="vjournalist", description="Turn short videos into evidence-backed Markdown for Claude agents (local)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight", help="Check ffmpeg, whisper, Claude CLI and yt-dlp (no model call)")
    read = commands.add_parser("read", help="Read a video file, a folder of videos or a URL (SHA-256 cache, resumable)")
    read.add_argument("source", nargs="?", help="File, folder or URL; omitted: input_folders from config.yaml")
    read.add_argument("--recursive", action="store_true", help="Include subfolders (folder input)")
    read.add_argument("--dry-run", action="store_true", help="List only: cached vs to analyze; no LLM call")
    read.add_argument("--no-wait", action="store_true", help="On a Claude CLI limit exit with code 75 instead of waiting")
    read.add_argument("--poll-minutes", type=float, default=15, help="Pause when the limit has no known reset")
    read.add_argument("--max-wait-hours", type=float, default=6)
    read.add_argument("--captions", help="Caption file (.vtt/.srt) to use instead of ASR (single file input)")
    read.add_argument("--output", "--bridge-dir", dest="output", help="Output directory (default: <parent>/OUTPUT/<name>)")
    rebuild = commands.add_parser("rebuild", help="Rebuild cards and articles from the cache; zero LLM calls")
    rebuild.add_argument("output", help="OUTPUT/X directory to rebuild")
    rebuild.add_argument("--only", help="Only this id")
    rebuild.add_argument("--overwrite", action="store_true", help="Also overwrite cards with a changed status or agent_notes")
    index = commands.add_parser("index", help="Regenerate INDEX.md from the card headers (no rebuild, no LLM)")
    index.add_argument("output", help="OUTPUT/X directory")
    check = commands.add_parser("check", help="Run the coverage validator over an OUTPUT/X directory")
    check.add_argument("output", help="OUTPUT/X directory")
    check.add_argument("--id", action="append", help="Only this id (repeatable)")
    tx = commands.add_parser("tx", help="Fragment of a transcript archive")
    tx.add_argument("id")
    tx.add_argument("--at", type=float, required=True)
    tx.add_argument("--window", type=float, default=20)
    tx.add_argument("--output", help="OUTPUT/X directory (default: search the folders in config.yaml)")
    options = parser.parse_args(argv)
    if options.command == "preflight":
        return preflight()
    if options.command == "tx":
        from vjournalist.bridge.transcript import fragment

        if not re.fullmatch(r"[a-zA-Z0-9_-]+", options.id) or options.at < 0 or options.window <= 0:
            parser.error("Invalid id, time or window")
        path = find_archive(options.id, [options.output] if options.output else None)
        if path is None:
            print(f"No archive for {options.id}", file=sys.stderr)
            return 1
        print(fragment(path.read_text(encoding="utf-8"), options.at, options.window))
        return 0
    if options.command == "rebuild":
        from vjournalist.rebuild import format_rebuild, rebuild

        output = Path(options.output).expanduser()
        if not output.is_dir():
            parser.error("Output directory does not exist")
        report = rebuild(output, only=options.only, overwrite=options.overwrite)
        print(format_rebuild(report))
        return 1 if report["failures"] else 0
    if options.command == "index":
        from vjournalist.bridge.cards import build_index

        output = Path(options.output).expanduser()
        if not (output / "cards").is_dir():
            parser.error("Output directory has no cards/")
        build_index(output)
        print(f"INDEX.md regenerated: {output / 'INDEX.md'}")
        return 0
    if options.command == "check":
        from vjournalist.bridge.coverage import check_bridge

        output = Path(options.output).expanduser()
        if not output.is_dir():
            parser.error("Output directory does not exist")
        ids = options.id or [p.stem for p in sorted((output / "cards").glob("*.md"))]
        problems = check_bridge(output, ids)
        print("\n".join(problems) if problems else f"OK: {len(ids)} card(s), 0 coverage problems")
        return 1 if problems else 0
    try:
        return run_read(options, parser)
    except KeyboardInterrupt:
        print("Interrupted. Checkpoints kept; an uncertain LLM call is not retried.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
