"""`vjournalist preflight`: see references/output-format.md. Usage: python preflight.py [arguments of the CLI command]."""

import sys

from _run import run

raise SystemExit(run("preflight", sys.argv[1:]))
