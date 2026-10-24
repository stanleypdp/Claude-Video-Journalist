import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_read_contract import example
from vjournalist import llm
from vjournalist.bridge.cards import normalize_read
from vjournalist.roles import schema_for_role
from vjournalist.storage import atomic_json


@pytest.fixture
def payload(tmp_path):
    p, _ = example()
    return {**p, "schema_version": 6, "output_language": "pl", "images": ["missing-image.jpg"], "_receipt_dir": str(tmp_path / "receipts")}


def valid_answer():
    p, v = example()
    return normalize_read(v, p)


def test_one_repair_only_and_usage_separated(payload, config, monkeypatch):
    monkeypatch.setattr(llm.Config, "load", lambda: config)
    monkeypatch.setattr(llm, "preflight", lambda *_: None)
    calls = []

    def fake(evidence, schema, feedback, _):
        calls.append(feedback)
        value = valid_answer()
        if feedback is None:
            value.pop("title")
        else:
            assert set(feedback) == {"invalid_json", "validation_errors"}
        return {"result": json.dumps(value), "usage": {"input_tokens": 100, "output_tokens": 50}}

    monkeypatch.setattr(llm, "_invoke", fake)
    schema = schema_for_role("knowledge", payload)
    result = llm.analyze(payload, schema)
    assert result["invocations"] == 2 and len(calls) == 2
    assert len(result["usage"]) == 2
    # Replaying stored receipts makes no additional paid invocation.
    assert llm.analyze(payload, schema)["analysis"] == result["analysis"]
    assert len(calls) == 2


def test_actual_repair_transport_omits_images_and_transcript(payload, config, monkeypatch):
    calls = []

    def fake(args, **kwargs):
        calls.append(json.loads(kwargs["input"]))
        assert "--tools" in args and args[args.index("--tools") + 1] == ""
        assert args[args.index("--output-format") + 1] == "stream-json"
        assert "--verbose" in args and "--safe-mode" in args
        return SimpleNamespace(returncode=0, stdout='{"type":"result","result":"{}"}')

    monkeypatch.setattr(llm.subprocess, "run", fake)
    llm._invoke(
        payload,
        schema_for_role("knowledge"),
        {"invalid_json": "{}", "validation_errors": ["title missing"]},
        config,
    )
    content = calls[0]["message"]["content"]
    assert len(content) == 1 and content[0]["type"] == "text"
    request = json.loads(content[0]["text"])
    assert set(request) == {"invalid_json", "validation_errors", "schema"}
    assert "NASDAQ tested" not in json.dumps(request)
    assert "missing-image.jpg" not in json.dumps(request)


def test_two_bad_responses_stop_and_do_not_make_third_call(payload, config, monkeypatch):
    monkeypatch.setattr(llm.Config, "load", lambda: config)
    monkeypatch.setattr(llm, "preflight", lambda *_: None)
    calls = []
    monkeypatch.setattr(llm, "_invoke", lambda *_: calls.append(1) or {"result": "{}"})
    schema = schema_for_role("knowledge", payload)
    with pytest.raises(llm.LLMError, match="repair attempt"):
        llm.analyze(payload, schema)
    assert len(calls) == 2
    with pytest.raises(llm.LLMError):
        llm.analyze(payload, schema)
    assert len(calls) == 2


def test_ambiguous_crash_does_not_retry(payload, config, monkeypatch):
    monkeypatch.setattr(llm.Config, "load", lambda: config)
    atomic_json(Path(payload["_receipt_dir"]) / "started-1.json", {"attempt": 1})
    monkeypatch.setattr(llm, "_invoke", lambda *_: pytest.fail("must not repeat uncertain call"))
    with pytest.raises(llm.LLMError, match="paying twice"):
        llm.analyze(payload, schema_for_role("knowledge", payload))


def test_effort_low_and_image_limit(config, tmp_path, monkeypatch):
    args_seen = []

    def fake(args, **kwargs):
        args_seen.append(args)
        return SimpleNamespace(returncode=0, stdout='{"type":"result","result":"{}"}')

    monkeypatch.setattr(llm.subprocess, "run", fake)
    payload = {"role": "knowledge", "schema_version": 6, "_receipt_dir": str(tmp_path), "images": [], "ocr": []}
    llm._invoke(payload, {}, None, config)
    assert args_seen[0][args_seen[0].index("--effort") + 1] == "low"
    payload["images"] = ["unused"] * 7
    with pytest.raises(llm.LLMError, match="limit"):
        llm._invoke(payload, {}, None, config)


def test_stream_selects_final_result_and_usage():
    events = [
        {"type": "system", "subtype": "init", "tools": [], "mcp_servers": [], "skills": []},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "partial"}]}},
        {
            "type": "result",
            "result": '{"title":"done"}',
            "usage": {"input_tokens": 123, "output_tokens": 45},
            "total_cost_usd": 0.01,
            "num_turns": 1,
        },
    ]
    result = llm.parse_stream("\n".join(json.dumps(event) for event in events))
    assert json.loads(result["result"]) == {"title": "done"}
    assert result["usage"]["input_tokens"] == 123
    assert result["total_cost_usd"] == 0.01


def test_stream_missing_result_or_enabled_tools_fails():
    with pytest.raises(llm.LLMError, match="result"):
        llm.parse_stream('{"type":"assistant"}\n')
    with pytest.raises(llm.LLMError, match="MCP"):
        llm.parse_stream(
            '{"type":"system","subtype":"init","tools":["Read"]}\n{"type":"result","result":"{}"}\n'
        )
