import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path


def slug(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")[:72] or "untitled"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def atomic_text(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as out:
            out.write(value)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def read_json(path):
    return json.loads(Path(path).read_text())


def run(args, timeout=300):
    proc = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode:
        # Do not include command arguments: they can contain source URLs or cookie paths.
        raise RuntimeError(f"{Path(str(args[0])).name}: command failed (exit code {proc.returncode}).")
    return proc.stdout


@contextlib.contextmanager
def pipeline_lock(data):
    data.mkdir(parents=True, exist_ok=True)
    with (data / "vjournalist.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Another video is being processed. Try again when the current job finishes."
            ) from None
        yield


def check_quota(config):
    total = sum(p.stat().st_size for p in config.data.rglob("*") if p.is_file() and not p.is_symlink())
    if total >= config.max_bytes:
        raise RuntimeError("Data limit exceeded. Remove unneeded files before the next analysis.")
    return config.max_bytes - total


def cleanup_work(config):
    """Keep permanent cache and Markdown; expire only old content-addressed work dirs."""
    cutoff = time.time() - 14 * 86400
    root = config.data / "work"
    if not root.exists():
        return
    for directory in root.iterdir():
        if (
            directory.is_symlink()
            or not directory.is_dir()
            or not re.fullmatch(r"[a-f0-9]{64}", directory.name)
        ):
            continue
        latest = max(
            [directory.stat().st_mtime]
            + [p.stat().st_mtime for p in directory.rglob("*") if p.is_file() and not p.is_symlink()]
        )
        if latest < cutoff:
            shutil.rmtree(directory)


class Jobs:
    def __init__(self, data):
        data.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(data / "vjournalist.db")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY, sha256 TEXT, name TEXT NOT NULL, mode TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued', step TEXT, error TEXT,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                elapsed_s REAL, usage TEXT, outputs TEXT, cached INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS job_logs (
                id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, step TEXT, message TEXT
            );
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}
        for name, kind in (("role", "TEXT"), ("schema_version", "INTEGER")):
            if name not in columns:
                self.db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")
        self.db.commit()

    def create(self, name, role, schema_version=3):
        cursor = self.db.execute(
            "INSERT INTO jobs(name,mode,role,schema_version) VALUES (?,?,?,?)",
            (name, role, role, schema_version),
        )
        self.db.commit()
        return cursor.lastrowid

    def update(self, job, **values):
        allowed = {"sha256", "status", "step", "error", "elapsed_s", "usage", "outputs", "cached"}
        if not values.keys() <= allowed:
            raise ValueError("Invalid job fields")
        assignments = ", ".join(f"{key}=?" for key in values)
        self.db.execute(
            f"UPDATE jobs SET {assignments}, updated=CURRENT_TIMESTAMP WHERE id=?", [*values.values(), job]
        )
        self.db.commit()

    def log(self, job, step, message):
        self.update(job, status="running", step=step)
        self.db.execute("INSERT INTO job_logs(job_id, step, message) VALUES (?, ?, ?)", (job, step, message))
        self.db.commit()
        print(f"[{step}] {message}", flush=True)

    def close(self):
        self.db.close()
