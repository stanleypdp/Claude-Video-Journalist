"""read <folder>: SHA-256 skip, duplicates, errors, pause/resume at the Claude CLI limit, report."""

from dataclasses import replace

import pytest

from vjournalist.config import Config
from vjournalist.llm import LLMRateLimit, limit_error
from vjournalist.read_batch import VERSION, format_report, read_folder
from vjournalist.storage import atomic_json, sha256, slug


@pytest.fixture
def setup(tmp_path):
    folder = tmp_path / "videos"
    folder.mkdir()
    config = replace(
        Config.load(), data=tmp_path / "data", bridge=tmp_path / "bridge"
    )
    return folder, config


def video(folder, name, content):
    (folder / name).write_bytes(content)


def fake_analyze(config, calls, behaviour=None):
    def analyze(source, role, config=None, **_):
        calls.append(source)
        action = behaviour(len(calls)) if behaviour else None
        if isinstance(action, Exception):
            raise action
        digest = sha256(source)
        base = config.data / "cache" / digest
        atomic_json(base / "provenance.json", {"name": source.rsplit("/", 1)[-1][:-4]})
        atomic_json(base / f"roles/knowledge/v{VERSION}/analysis.json", {"usage": [{"cost_usd": 0.05}]})
        name = slug(source.rsplit("/", 1)[-1][:-4]) + f"-{digest[:12]}.md"
        (config.bridge / "articles").mkdir(parents=True, exist_ok=True)
        (config.bridge / "articles" / name).write_text("x")
        return {"cache": "MISS", "cost_usd_first_call": 0.05, "cost_usd_retries": 0, "llm_invocations": 1}

    return analyze


def test_new_cached_duplicate_and_error(setup):
    folder, config = setup
    video(folder, "a.mp4", b"A")
    video(folder, "b.mp4", b"B")
    video(folder, "b-copy.mp4", b"B")
    video(folder, "notes.txt", b"ignored")
    calls = []
    first = read_folder(folder, config, analyze=fake_analyze(config, calls))
    assert [r["status"] for r in first["rows"]] == ["analyzed", "analyzed", "duplicate"]
    assert first["summary"]["cost_usd"] == pytest.approx(0.1)
    second = read_folder(folder, config, analyze=fake_analyze(config, calls))
    assert len(calls) == 2  # nothing analysed again
    assert second["summary"]["cache"] == 2 and second["summary"]["cost_usd"] == 0
    assert second["summary"]["historical_cost_usd_cache"] == pytest.approx(0.1)

    video(folder, "c.mp4", b"C")
    failing = read_folder(
        folder, config, analyze=fake_analyze(config, calls, lambda n: ValueError("broken"))
    )
    assert failing["summary"]["errors"] == 1 and "broken" in format_report(failing)


def test_limit_pause_then_resume_same_file(setup):
    folder, config = setup
    video(folder, "a.mp4", b"A")
    video(folder, "b.mp4", b"B")
    calls, naps = [], []
    behaviour = lambda n: LLMRateLimit("limit", 120) if n == 2 else None  # noqa: E731
    report = read_folder(
        folder, config, analyze=fake_analyze(config, calls, behaviour), sleep=naps.append, log=lambda *_: None
    )
    assert naps == [120] and report["paused_s"] == 120
    assert len(calls) == 3 and calls[1] == calls[2]  # the interrupted file was retried
    assert report["summary"]["analyzed"] == 2 and report["summary"]["pending"] == 0


def test_limit_without_waiting_leaves_pending_and_resumes_later(setup):
    folder, config = setup
    for name in "abc":
        video(folder, f"{name}.mp4", name.encode())
    calls = []
    behaviour = lambda n: LLMRateLimit("limit", 60) if n == 2 else None  # noqa: E731
    stopped = read_folder(folder, config, analyze=fake_analyze(config, calls, behaviour), wait=False)
    assert [r["status"] for r in stopped["rows"]] == ["analyzed", "pending", "pending"]
    resumed = read_folder(folder, config, analyze=fake_analyze(config, calls))
    assert resumed["summary"]["cache"] == 1 and resumed["summary"]["analyzed"] == 2


def test_dry_run_calls_nothing(setup):
    folder, config = setup
    video(folder, "a.mp4", b"A")
    calls = []
    report = read_folder(folder, config, analyze=fake_analyze(config, calls), dry_run=True)
    assert calls == [] and report["rows"][0]["status"] == "pending"


def test_limit_error_detection():
    err = limit_error("Claude AI usage limit reached. Your limit will reset in 45 minutes")
    assert isinstance(err, LLMRateLimit) and err.reset_in_s == 2700
    assert limit_error("API Error: 429 Too Many Requests") is not None
    assert limit_error("Invalid API key") is None


def test_limit_rejection_frees_marker_for_retry(tmp_path, monkeypatch):
    from vjournalist import llm

    receipts = tmp_path / "llm"
    monkeypatch.setattr(llm, "preflight", lambda c: None)
    monkeypatch.setattr(llm, "_invoke", lambda *a: (_ for _ in ()).throw(LLMRateLimit("limit")))
    payload = {"_receipt_dir": str(receipts), "role": "knowledge"}
    with pytest.raises(LLMRateLimit):
        llm.analyze(payload, {})
    assert not (receipts / "started-1.json").exists()
    assert list(receipts.glob("limit-rejected-1-*.json"))
    with pytest.raises(LLMRateLimit):  # second call is allowed again (no "no response" refusal)
        llm.analyze(payload, {})
