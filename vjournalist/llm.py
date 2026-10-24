"""Replaceable backend: analyze(payload, schema) -> {analysis, usage, invocations}.

Images are sent as image blocks over stdin, not read using agent tools.
No subprocess shell, tools, MCP, or session persistence. At most one validation retry.
Receipts prevent paying twice when resuming after a render/commit failure.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from jsonschema import ValidationError

from vjournalist.config import ROOT, Config
from vjournalist.roles import normalize_role, validate_role
from vjournalist.storage import atomic_json, atomic_text, read_json


class LLMError(RuntimeError):
    pass


class LLMRateLimit(LLMError):
    """Account/usage limit reported by the CLI; the request was rejected, so it is safe to retry later."""

    def __init__(self, message, reset_in_s=None):
        super().__init__(message)
        self.reset_in_s = reset_in_s


LIMIT = re.compile(
    r"usage limit|rate.?limit|limit reached|too many requests|\b429\b|overloaded|limit will reset", re.I
)
RESET = re.compile(r"resets?\s+(?:in\s+)?(\d+)\s*(second|minute|hour|min|h|s)", re.I)


def limit_error(text):
    """LLMRateLimit when CLI output reports a limit (optionally with 'resets in N minutes'), else None."""
    text = str(text or "")
    if not LIMIT.search(text):
        return None
    m = RESET.search(text)
    seconds = None
    if m:
        unit = m[2].lower()
        seconds = int(m[1]) * (3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1)
    return LLMRateLimit("Limit Claude CLI: " + text.strip()[:200], seconds)


class LLMStartupError(LLMError):
    """CLI argument rejection confirmed before any model request."""


def preflight(config):
    binary = shutil.which(config.claude)
    if binary is None:
        raise LLMError("Claude CLI not found. Install it and log in locally, then run the analysis again.")
    result = subprocess.run([binary, "auth", "status"], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise LLMError("Claude CLI is not logged in. Run locally: claude auth login.")


def _invoke(payload, schema, feedback, config):
    if feedback is not None:
        # Deliberately no evidence, frames, transcript or previous conversation in the repair call.
        request = {
            "invalid_json": feedback["invalid_json"],
            "validation_errors": feedback["validation_errors"],
            "schema": schema,
        }
        images = []
    else:
        evidence = {
            key: value for key, value in payload.items() if key != "images" and not key.startswith("_")
        }
        from vjournalist.bridge.transcript import compact_ocr

        evidence = {**evidence, "ocr": compact_ocr(evidence.get("ocr", []))}
        request = {"evidence": evidence, "schema": schema}
        images = payload.get("images", [])
    content = [{"type": "text", "text": json.dumps(request, ensure_ascii=False)}]
    if len(images) > 6:
        raise LLMError("Image limit exceeded: Read takes at most 6 data frames.")
    for path in images:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(Path(path).read_bytes()).decode(),
                },
            }
        )
    message = {"type": "user", "message": {"role": "user", "content": content}}
    system_prompt = (ROOT / ("prompts/repair.txt" if feedback is not None else "prompts/knowledge.txt")).read_text()
    return _run_content(
        message,
        system_prompt,
        config,
        Path(payload["_receipt_dir"]),
        effort="low",
    )


def _run_content(message, system_prompt, config, receipt_dir, effort=None):
    args = [
        config.claude,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--input-format",
        "stream-json",
        "--model",
        config.model,
        "--tools",
        "",
        "--safe-mode",
        "--no-chrome",
        "--max-turns",
        "1",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--setting-sources",
        "",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        "--system-prompt",
        system_prompt,
    ]
    if effort:
        args += ["--effort", effort]
    environment = dict(os.environ)
    environment.pop("CLAUDECODE", None)
    # Keep subscription authentication; do not use --bare (it disables keychain/OAuth).
    config.data.mkdir(parents=True, exist_ok=True)
    with __import__("tempfile").TemporaryDirectory(prefix="vjournalist-llm-", dir=config.data) as cwd:
        proc = subprocess.run(
            args,
            input=json.dumps(message) + "\n",
            text=True,
            capture_output=True,
            timeout=config.llm_timeout,
            env=environment,
            cwd=cwd,
        )
    if proc.returncode:
        atomic_json(
            receipt_dir / "cli-error.json",
            {"returncode": proc.returncode, "stderr": proc.stderr, "stdout": proc.stdout},
        )
        if limited := limit_error(proc.stderr + proc.stdout):
            raise limited
        if proc.stderr.strip() == "Error: --input-format=stream-json requires output-format=stream-json.":
            raise LLMStartupError(
                "Claude CLI rejected the input/output format before sending the request. "
                "Details are in data/cache/<sha>/llm/cli-error.json."
            )
        raise LLMError(
            f"Claude CLI failed (exit code {proc.returncode}). Check the login and model access."
        )
    atomic_text(receipt_dir / "last-stream.jsonl", proc.stdout)
    response = parse_stream(proc.stdout)
    if response.get("is_error"):
        if limited := limit_error(response.get("result")):
            raise limited
        raise LLMError("Claude CLI reported a model or account-limit error. Check the CLI manually.")
    return response


def parse_stream(stdout):
    """Use only the final result event; never concatenate assistant event fragments."""
    try:
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    except json.JSONDecodeError:
        raise LLMError("Claude CLI returned an invalid JSON stream. Not retrying by another method.") from None
    results = [event for event in events if event.get("type") == "result"]
    if len(results) != 1:
        raise LLMError("Claude CLI did not return exactly one final result object.")
    response = results[0]
    initial = next(
        (event for event in events if event.get("type") == "system" and event.get("subtype") == "init"), {}
    )
    response["cli_runtime"] = {key: initial.get(key) for key in ("tools", "mcp_servers", "skills")}
    if any(response["cli_runtime"].get(key) for key in ("tools", "mcp_servers", "skills")):
        raise LLMError("Claude CLI enabled tools/MCP/skills despite the flags that disable them. Analysis halted.")
    return response


def _decode(response):
    if isinstance(response.get("structured_output"), dict):
        return response["structured_output"]
    content = response.get("result", "")
    if content.startswith("```json\n") and content.endswith("\n```"):
        content = content[8:-4]
    from vjournalist.bridge.repair import decode

    value, repaired = decode(content)
    response["local_syntax_repair"] = repaired
    return value


def analyze(payload, schema) -> dict:
    config = Config.load()
    receipt_dir = Path(payload["_receipt_dir"])
    receipt_dir.mkdir(parents=True, exist_ok=True)
    feedback = None
    usage = []
    attempts = max(1, min(2, int(os.getenv("LLM_ATTEMPTS", "2"))))  # 1 = no paid repair call
    for attempt in range(1, attempts + 1):
        receipt = receipt_dir / f"response-{attempt}.json"
        marker = receipt_dir / f"started-{attempt}.json"
        if receipt.exists():
            response = read_json(receipt)
        else:
            if payload.get("_receipts_only"):
                raise LLMError("Review from stored answers only; new call blocked.")
            if marker.exists():
                raise LLMError(
                    "The previous LLM call has no answer. Not retrying automatically, "
                    "to avoid paying twice. Check the account and use --force deliberately."
                )
            preflight(config)
            atomic_json(marker, {"model": config.model, "attempt": attempt})
            try:
                response = _invoke(payload, schema, feedback, config)
            except LLMStartupError:
                marker.rename(receipt_dir / f"startup-rejected-{attempt}.json")
                raise
            except LLMRateLimit:
                # Rejected by the account limit before any answer: a later retry cannot pay twice.
                marker.rename(receipt_dir / f"limit-rejected-{attempt}-{time.strftime('%Y%m%dT%H%M%S')}.json")
                raise
            atomic_json(receipt, response)
        usage.append(
            {
                "usage": response.get("usage", {}),
                "cost_usd": response.get("total_cost_usd"),
                "model_usage": response.get("modelUsage", {}),
                "response_text": response.get("result"),
                "runtime": response.get("cli_runtime", {}),
                "num_turns": response.get("num_turns"),
            }
        )
        try:
            value = _decode(response)
            value = normalize_role(value, payload)
            validate_role(value, schema, payload)
        except (ValidationError, ValueError, TypeError) as exc:
            feedback = {
                "invalid_json": response.get("structured_output", response.get("result", "")),
                "validation_errors": [str(exc)[:4000]],
            }
            if attempt == attempts:
                raise LLMError(
                    "Invalid LLM answer after one repair attempt. "
                    "Details are in the local answer files."
                ) from None
        else:
            return {
                "analysis": value,
                "usage": usage,
                "invocations": attempt,
                "response_text": response.get("result"),
            }
    raise AssertionError("unreachable")
