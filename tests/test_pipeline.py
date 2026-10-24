import shutil

import pytest

from tests.conftest import role_analysis_for as analysis_for
from vjournalist import llm
from vjournalist.service import analyze_video
from vjournalist.storage import pipeline_lock


def fake_analyze(calls):
    def fake(payload, schema):
        calls.append(payload)
        return {
            "analysis": analysis_for(payload),
            "usage": [
                {
                    "usage": {
                        "input_tokens": 40,
                        "output_tokens": 60,
                        "cache_read_input_tokens": 20,
                        "cache_creation_input_tokens": 10,
                    }
                }
            ],
            "invocations": 1,
        }

    return fake


def test_cache_survives_work_cleanup_and_missing_cli(video, config, tmp_path, monkeypatch):
    from dataclasses import replace

    config = replace(config, bridge=tmp_path / "OUTPUT" / "X")
    calls = []
    monkeypatch.setattr(llm, "preflight", lambda *_: None)
    monkeypatch.setattr(llm, "analyze", fake_analyze(calls))
    first = analyze_video(str(video), "knowledge", config=config)
    assert first["status"] == "done" and first["cache"] == "MISS"
    assert first["tokens_first_call"] == 130 and first["tokens_retries"] == 0
    assert len(calls) == 1 and calls[0]["schema_version"] == 6
    assert "scenes" not in calls[0]
    assert (config.bridge / "INDEX.md").exists()
    texts = {p.name: p.read_text() for p in config.bridge.glob("cards/*.md")}
    shutil.rmtree(config.data / "work")
    monkeypatch.setattr(llm, "preflight", lambda *_: pytest.fail("cache must not need CLI"))
    second = analyze_video(str(video), "knowledge", config=config)
    assert second["cache"] == "HIT" and second["llm_invocations"] == 0
    assert second["tokens_first_call"] == second["tokens_retries"] == 0
    assert len(calls) == 1
    assert {p.name: p.read_text() for p in config.bridge.glob("cards/*.md")} == texts


def test_taste_role_is_not_available(video, config):
    with pytest.raises(ValueError, match="knowledge"):
        analyze_video(str(video), "taste", config=config)


def test_failed_video_is_recorded_and_does_not_block_next(video, config, tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")
    with pytest.raises(Exception):  # noqa: B017 - any media failure
        analyze_video(str(broken), "knowledge", config=config, prepare_only=True)
    assert analyze_video(str(video), "knowledge", config=config, prepare_only=True)["status"] == "prepared"


def test_checkpoints_resume_without_repeating_media(video, config, monkeypatch):
    first = analyze_video(str(video), "knowledge", prepare_only=True, config=config)
    from vjournalist.pipeline import media

    for name in ("probe", "transcribe", "detect_scenes"):
        monkeypatch.setattr(media, name, lambda *_: pytest.fail("checkpoint must be reused"))
    second = analyze_video(str(video), "knowledge", prepare_only=True, config=config)
    assert second["sha256"] == first["sha256"]


def test_global_lock(config):
    with pipeline_lock(config.data):
        with pytest.raises(RuntimeError, match="Another video"):
            with pipeline_lock(config.data):
                pytest.fail("should not acquire lock")


def test_quota_refuses_before_ingest(video, config):
    from dataclasses import replace

    with pytest.raises(RuntimeError, match="limit"):
        analyze_video(str(video), "knowledge", config=replace(config, max_bytes=1), prepare_only=True)


def test_force_archives_cache_and_calls_again(video, config, tmp_path, monkeypatch):
    from dataclasses import replace

    config = replace(config, bridge=tmp_path / "OUTPUT" / "X")
    calls = []
    monkeypatch.setattr(llm, "preflight", lambda *_: None)
    monkeypatch.setattr(llm, "analyze", fake_analyze(calls))
    first = analyze_video(str(video), "knowledge", config=config)
    assert analyze_video(str(video), "knowledge", config=config)["cache"] == "HIT"
    assert len(calls) == 1
    assert analyze_video(str(video), "knowledge", force=True, config=config)["cache"] == "MISS"
    assert len(calls) == 2
    roles = config.data / "cache" / first["sha256"] / "roles" / "knowledge"
    assert len(list(roles.glob("v6-run-*"))) == 1
