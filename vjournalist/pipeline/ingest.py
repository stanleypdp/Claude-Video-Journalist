import shutil
from pathlib import Path

from vjournalist.storage import check_quota, sha256


def ingest(source, config):
    """Copy a local video into the content-addressed store. Returns (path, sha256, url, name).

    URLs are downloaded before this point (see `vjournalist.pipeline.download`); `url` stays "unknown".
    """
    uploads = config.data / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ValueError("The file does not exist or is not a regular file.")
    digest = sha256(path)
    # One content-addressed file, independent of supplied filename and extension.
    target = uploads / f"{digest}.video"
    if not target.exists():
        if path.stat().st_size > check_quota(config):
            raise ValueError("The file exceeds the available data limit.")
        incoming = uploads / f".{digest}.part"
        shutil.copyfile(path, incoming)
        incoming.replace(target)
    return target, digest, "unknown", path.stem
