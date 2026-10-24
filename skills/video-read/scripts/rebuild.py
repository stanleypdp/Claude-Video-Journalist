"""`vjournalist rebuild`: see references/output-format.md. Usage: python rebuild.py [arguments of the CLI command]."""

import sys

from _run import run

raise SystemExit(run("rebuild", sys.argv[1:]))
