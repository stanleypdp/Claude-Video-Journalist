"""`vjournalist check`: see references/output-format.md. Usage: python check.py [arguments of the CLI command]."""

import sys

from _run import run

raise SystemExit(run("check", sys.argv[1:]))
