"""`vjournalist tx`: see references/output-format.md. Usage: python tx.py [arguments of the CLI command]."""

import sys

from _run import run

raise SystemExit(run("tx", sys.argv[1:]))
