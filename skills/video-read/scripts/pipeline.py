"""The whole Read sequence for one source, stopping at the first problem.

    python pipeline.py <video file | folder | URL> [--output DIR] [--recursive] [--captions FILE]

preflight -> read --dry-run (files and URLs skip the dry run) -> read -> check (coverage validator).
The only paid step is `read`, one Claude call per new video; cached videos cost nothing.
"""

import sys
from pathlib import Path

from _run import run
from read_helpers import is_url, output_dir_from_args


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    source = argv[0]
    if (code := run("preflight", [])) != 0:
        return code
    if Path(source).expanduser().is_dir() and (code := run("read", [source, "--dry-run", *argv[1:]])) not in (0,):
        return code
    if (code := run("read", argv)) != 0:
        return code
    output = output_dir_from_args(argv)
    if output and not is_url(source):
        return run("check", [str(output)])
    print("Done. Run `check` on the OUTPUT folder printed above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
