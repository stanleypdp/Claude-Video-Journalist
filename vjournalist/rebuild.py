"""`rebuild <OUTPUT/X>`: cards, articles and archives again from the cached raw answers. Zero LLM calls.

The raw answer (`llm/response-N.json`) goes through the current normalizer and validator, then
`export_read` writes the Markdown. The cache itself is never modified.
"""

import re
import tempfile
from pathlib import Path

import yaml

from vjournalist.bridge.cards import export_read
from vjournalist.bridge.transcript import chapters
from vjournalist.config import Config
from vjournalist.llm import _decode
from vjournalist.roles import normalize_role, schema_for_role, validate_role
from vjournalist.storage import read_json, slug

CACHE_SUBDIR = Path("roles") / "knowledge" / "v6"


def cache_index(config):
    """id -> cache directory, from provenance.json of every cached video."""
    found = {}
    for provenance in sorted((config.data / "cache").glob("*/provenance.json")):
        meta = read_json(provenance)
        directory = provenance.parent / CACHE_SUBDIR
        if (directory / "analysis.json").exists():
            found[f"{slug(meta['name'])}-{meta['sha256'][:12]}"] = directory
    return found


def renormalized(directory):
    """(common, value): the raw answer of one cache directory through the current normalizer/validator."""
    result = read_json(directory / "analysis.json")
    payload = read_json(directory / "payload.json")
    common = read_json(directory / "common.json")
    response = read_json(directory / "llm" / f"response-{result['invocations']}.json")
    value = normalize_role(_decode(response), payload)
    validate_role(value, schema_for_role("knowledge", payload), payload)
    return common, value


def recorded_results(existing, fresh):
    """True when the card on disk carries consumer results the fresh render would erase.

    A consumer moves `status` off `untested` and appends lines to `agent_notes`; rebuilding must not lose them.
    """

    def parts(text):
        _, front, body = text.split("---", 2)
        notes = re.search(r"^## agent_notes\n+(.*?)(?=^## |\Z)", body, re.M | re.S)
        lines = {line for line in (notes[1].splitlines() if notes else []) if line.strip()}
        return yaml.safe_load(front).get("status"), lines

    status, notes = parts(existing)
    _, fresh_notes = parts(fresh)
    return status != "untested" or not notes <= fresh_notes


def rebuild(output, only=None, config=None, overwrite=False):
    config = config or Config.load()
    output = Path(output)
    index = cache_index(config)
    report = {"output": str(output), "rebuilt": [], "failures": [], "chapters_skipped": [], "kept": []}
    for card in sorted((output / "cards").glob("*.md")):
        id_ = card.stem
        if only and id_ != only:
            continue
        directory = index.get(id_)
        if directory is None:
            report["failures"].append((id_, "not in cache"))
            continue
        try:
            common, value = renormalized(directory)
            if not overwrite:
                with tempfile.TemporaryDirectory() as scratch:
                    export_read(id_, value, common, Path(scratch))
                    fresh = (Path(scratch) / "cards" / f"{id_}.md").read_text(encoding="utf-8")
                if recorded_results(card.read_text(encoding="utf-8"), fresh):
                    report["kept"].append(id_)
                    continue
            export_read(id_, value, common, output)
            if chapters(id_, common["transcript"], common["metadata"]["duration_s"], config, output, llm=False) is None:
                if common["metadata"]["duration_s"] > 300:
                    report["chapters_skipped"].append(id_)
            report["rebuilt"].append(id_)
        except Exception as exc:  # noqa: BLE001 - reported per file, the rest continues
            report["failures"].append((id_, f"{type(exc).__name__}: {str(exc)[:200]}"))
    return report


def format_rebuild(report):
    lines = [
        f"Directory: {report['output']}",
        f"Rebuilt from cache (0 LLM): {len(report['rebuilt'])} | errors: {len(report['failures'])}",
    ]
    lines += [f"  ERROR {id_}: {reason}" for id_, reason in report["failures"]]
    if report["kept"]:
        lines.append(
            f"Kept as is (status changed or agent_notes written; use --overwrite to rebuild anyway): {len(report['kept'])}"
        )
    if report["chapters_skipped"]:
        lines.append(f"Chapters without a stored answer (skipped, no LLM): {len(report['chapters_skipped'])}")
    return "\n".join(lines)
