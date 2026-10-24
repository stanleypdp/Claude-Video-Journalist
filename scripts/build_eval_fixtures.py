# polish-fixtures: one eval clip carries a stored answer written in Polish (a deliberately translated card).
"""Build the input files of the skill evals (fictional content only).

    uv run python scripts/build_eval_fixtures.py

Writes `files/` folders under skills/*/evals/<case>/. The same builders are used by tests/test_skill_evals.py,
which runs each case's steps and checks the facts its graders rely on.
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vjournalist.bridge.cards import export_read, normalize_read  # noqa: E402
from vjournalist.storage import atomic_json, slug  # noqa: E402

EVALS = ROOT / "skills" / "video-read" / "evals"
CARD_EVALS = ROOT / "skills" / "claim-cards" / "evals"


def common(speech, screen, language="en", duration=8):
    return {
        "transcript": {"language": language, "segments": [{"start": 0, "end": 6, "text": speech}]},
        "scan": {
            "screen_text": [
                {"id": i + 1, "timestamp_s": 2.0, "last_seen_s": 5.0, "text": text,
                 "text_confidence": "exact", "ocr_score": 0.97}
                for i, text in enumerate(screen)
            ],
            "frames": [],
        },
        "metadata": {"duration_s": duration},
        "platform_info": {"content_duration_s": duration},
    }


def answer(language, claim, conclusion, reported, domain, article, title="Level test"):
    return {
        "schema_version": 6, "role": "knowledge", "title": title, "tags": [],
        "article": [{"start": 0, "text": article}], "screen_data": [],
        "card": {
            "profile": "analysis", "domain": domain, "claim": claim, "author_conclusion": conclusion,
            "reported": reported, "method_stated": [], "not_stated": [], "caution": [], "agent_notes": [],
        },
    }


def seed(case_files, name, digest_char, common_value, value, with_output=True):
    """A cached raw answer under data/ and the OUTPUT it produced, as `read` would have left them."""
    digest = digest_char * 64
    id_ = f"{slug(name)}-{digest[:12]}"
    cache = case_files / "data" / "cache" / digest
    atomic_json(cache / "provenance.json", {"name": name, "sha256": digest})
    directory = cache / "roles" / "knowledge" / "v6"
    payload = {
        "role": "knowledge", "schema_version": 6, "metadata": common_value["metadata"],
        "transcript": common_value["transcript"],
        "ocr": [{"text": r["text"], "text_confidence": r["text_confidence"]} for r in common_value["scan"]["screen_text"]],
    }
    atomic_json(directory / "analysis.json", {"invocations": 1})
    atomic_json(directory / "payload.json", payload)
    atomic_json(directory / "common.json", common_value)
    atomic_json(directory / "llm" / "response-1.json", {"result": json.dumps(value)})
    return id_, payload


def build_planted_error(files):
    """The stored transcript says 55.7% where the slide (and the model's answer) say 55.2%: a rebuild must flag it."""
    original = common("The level was touched in 55.2% of sessions.", ["HIT RATE 55.2%"])
    planted = common("The level was touched in 55.7% of sessions.", ["HIT RATE 55.2%"])
    v = answer("en", "Level touched in 55.2% of sessions", "Small edge", ["Level touched in 55.2% of sessions @3"],
               "market testing", "The author says the level was touched in 55.2% of sessions.")
    id_, payload = seed(files, "clip", "a", planted, v)
    # The OUTPUT of the original, unplanted run: speech and screen agree, number_check says `ok`.
    export_read(id_, normalize_read(json.loads(json.dumps(v)), payload), original, files / "OUTPUT" / "clip")
    return id_


def build_language(files):
    """One clip whose card is English, one whose stored answer was written in Polish for an English transcript."""
    english = common("Costs fall by 75 percent with this tool.", ["Costs: -75%"])
    good = answer("en", "Costs fall by 75% with this tool", "The tool cuts costs", ["Costs fall by 75% @1"],
                  "tooling", "The author says costs fall by 75% with this tool.", "Cost tool")
    translated = answer("pl", "Koszty spadają o 75% dzięki temu narzędziu", "Narzędzie obniża koszty",
                        ["Koszty spadają o 75% @1"], "narzędzia", "Autor twierdzi, że koszty spadają o 75% dzięki temu narzędziowi.", "Narzędzie kosztowe")
    g_id, g_payload = seed(files, "good", "b", english, good)
    t_id, _ = seed(files, "translated", "c", english, translated)
    out = files / "OUTPUT" / "clips"
    export_read(g_id, normalize_read(json.loads(json.dumps(good)), g_payload), english, out)
    # a stand-in card for the translated clip (what an earlier, unchecked run could have left behind)
    shutil.copy(out / "cards" / f"{g_id}.md", out / "cards" / f"{t_id}.md")
    text = (out / "cards" / f"{t_id}.md").read_text().replace(g_id, t_id)
    (out / "cards" / f"{t_id}.md").write_text(text)
    return g_id, t_id


def build_uncovered(files):
    """A finished result whose card carries a number that is in neither transcript nor OCR."""
    out = files / "OUTPUT" / "clip"
    for folder in ("cards", "articles", "archive"):
        (out / folder).mkdir(parents=True, exist_ok=True)
    (out / "cards" / "x.md").write_text(
        "---\nid: x\ntype: thesis_card\nprofile: analysis\nnumber_check:\n  '55.2': ok\n---\n# Level test\n\n"
        "## reported\n\n- Level touched in 55.2% of sessions @30\n- Edge of +4.4 pts @37\n"
    )
    (out / "articles" / "x.md").write_text(
        "# Level test\n\nThe author reports 55.2% of sessions.\n\n## Data from charts and slides\n\n"
        "| Time | Data | Value | Source | Confidence |\n|---|---|---|---|---|\n"
        "| 00:30 | Level | 55.2% | screen+speech | exact |\n"
    )
    (out / "archive" / "x.tx.md").write_text(
        "---\nid: x\nduration_s: 60\n---\n[00:30] The level was touched in 55.2% of sessions.\n"
    )
    (out / "archive" / "x.screen.md").write_text(
        "# Screen: x\n\nFirst and last appearance.\nFiltered: 0.\n\n[30.000-31.000s] 55.2%\n"
    )
    (out / "INDEX.md").write_text("# Read: card index\n")


def build_all():
    for case, builder in (
        ("rejects-uncovered-number", build_uncovered),
        ("detects-planted-number-error", build_planted_error),
        ("source-language-kept", build_language),
    ):
        files = EVALS / case / "files"
        shutil.rmtree(files, ignore_errors=True)
        files.mkdir(parents=True)
        builder(files)
    files = CARD_EVALS / "plan-from-card-only" / "files"
    shutil.rmtree(files, ignore_errors=True)
    shutil.copytree(ROOT / "examples" / "sample" / "OUTPUT", files / "OUTPUT")


if __name__ == "__main__":
    build_all()
    print("fixtures written")
