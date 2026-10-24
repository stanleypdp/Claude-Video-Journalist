from dataclasses import replace

import pytest

from vjournalist.config import Config
from vjournalist.storage import run


@pytest.fixture
def config(tmp_path):
    return replace(Config.load(), data=tmp_path / "data")


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "example.mp4"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=180x320:r=10:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=180x320:r=10:d=1",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[out]",
            "-map",
            "[out]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            path,
        ]
    )
    return path


def sample_value(schema):
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema["type"]
    if kind == "object":
        return {key: sample_value(value) for key, value in schema.get("properties", {}).items()}
    if kind == "array":
        return []
    if kind == "string":
        return "unknown"
    return schema.get("minimum", 0)


def role_analysis_for(payload):
    from vjournalist.roles import normalize_role, schema_for_role

    value = sample_value(schema_for_role("knowledge", payload))
    value["title"] = "Synthetic role fixture"
    value["article"] = [{"start": 0, "text": "Synthetic source content"}]
    return normalize_role(value, payload)


@pytest.fixture(autouse=True)
def local_ocr_test_double(monkeypatch):
    # No network/model downloads in unit tests; OCR extraction has a dedicated fake-engine test.
    from vjournalist.pipeline import content_scan

    original = content_scan.scan_content
    monkeypatch.setattr(
        content_scan, "scan_content", lambda v, w, m, s: original(v, w, m, s, engine=lambda *_: ([], None))
    )
