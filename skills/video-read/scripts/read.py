"""`vjournalist read`: see references/output-format.md. Usage: python read.py [arguments of the CLI command]."""

import sys

from _run import run

raise SystemExit(run("read", sys.argv[1:]))
