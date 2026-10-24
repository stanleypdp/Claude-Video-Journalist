"""Small helpers for pipeline.py (no heavy imports, so the launcher stays fast)."""

from pathlib import Path
from urllib.parse import urlparse


def is_url(value):
    return urlparse(str(value)).scheme.lower() in ("http", "https")


def output_dir_from_args(argv):
    """The OUTPUT directory `read` will use: --output/--bridge-dir, else the default for a folder or file."""
    for flag in ("--output", "--bridge-dir"):
        if flag in argv and argv.index(flag) + 1 < len(argv):
            return Path(argv[argv.index(flag) + 1]).expanduser()
    source = Path(argv[0]).expanduser()
    if is_url(argv[0]):
        return None
    if source.is_dir():
        return source.resolve().parent / "OUTPUT" / source.resolve().name
    return Path.cwd() / "OUTPUT" / "".join(c if c.isalnum() else "-" for c in source.stem.lower()).strip("-")
