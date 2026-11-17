"""Shared launcher: runs `python -m vjournalist <command> ...` with the project's own environment.

The project folder is found, in order, from $VJOURNALIST_HOME, from the location of this script (when the skill
lives inside a clone of the repo or an installed plugin), or from an already importable `vjournalist` package.

An installed copy (a plugin: the project files without `.git`) is replaced on every update, so its cache, work
files and Whisper model go to ~/.vjournalist/data instead of the project folder. $DATA_DIR always wins.
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


def data_dir_for(home, environ):
    """Value to export as DATA_DIR, or None to keep the project's own default (a git clone, or DATA_DIR is set)."""
    if environ.get("DATA_DIR") or home is None or (home / ".git").exists():
        return None
    return str(Path.home() / ".vjournalist" / "data")


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
    data_dir = data_dir_for(home, os.environ)
    if data_dir:
        env["DATA_DIR"] = data_dir
    if home and not shutil.which("uv"):
        print("uv is not on PATH; it provides the Python environment. Install it: https://docs.astral.sh/uv/", file=sys.stderr)
    if home and shutil.which("uv"):
        return subprocess.call(["uv", "run", "--project", str(home), "python", "-m", "vjournalist", command, *args], env=env)
    return subprocess.call([sys.executable, "-m", "vjournalist", command, *args], env=env)
