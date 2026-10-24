"""Shared launcher: runs `python -m vjournalist <command> ...` with the project's own environment.

The project folder is found, in order, from $VJOURNALIST_HOME, from the location of this script (when the skill
lives inside a clone of the repo), or from an already importable `vjournalist` package.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_home():
    env = os.environ.get("VJOURNALIST_HOME")
    candidates = [Path(env).expanduser()] if env else []
    candidates += list(Path(__file__).resolve().parents)
    for path in candidates:
        if (path / "vjournalist" / "__init__.py").exists() and (path / "pyproject.toml").exists():
            return path
    return None


def run(command, args):
    home = find_home()
    if home is None and importlib.util.find_spec("vjournalist") is None:
        print(
            "vjournalist is not installed. Clone the repository and run ./install.sh, then set\n"
            "VJOURNALIST_HOME to the clone (or install the skill from inside the clone). See install.md.",
            file=sys.stderr,
        )
        return 127
    # The package is importable through PYTHONPATH; the working directory stays the caller's, so relative paths work.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(home or ""), os.environ.get("PYTHONPATH", "")]))}
    if home and shutil.which("uv"):
        return subprocess.call(["uv", "run", "--project", str(home), "python", "-m", "vjournalist", command, *args], env=env)
    return subprocess.call([sys.executable, "-m", "vjournalist", command, *args], env=env)
