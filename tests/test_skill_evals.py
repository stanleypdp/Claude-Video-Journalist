"""The skill evals are well-formed, and the facts their graders rely on are what the code actually does.

The graded runs themselves need a model (`claude plugin eval skills/video-read`); these tests run the
deterministic half of each case offline: the steps the prompt asks for, on the case's own input files.
"""

import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from vjournalist.bridge.coverage import check_bridge
from vjournalist.config import Config
from vjournalist.rebuild import rebuild

ROOT = Path(__file__).resolve().parents[1]
CASES = sorted(p.parent for p in ROOT.glob("skills/*/evals/*/prompt.md"))
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def files_of(name, tmp_path):
    source = next(c for c in CASES if c.name == name) / "files"
    target = tmp_path / name
    shutil.copytree(source, target)
    return target


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_case_folder_is_well_formed(case):
    assert re.fullmatch(r"[a-z][a-z0-9-]*", case.name)
    meta = yaml.safe_load((case / "case.yaml").read_text())
    assert meta["schema_version"] == "1.1" and meta["name"] == case.name and meta["expected_outcome"].strip()
    prompt = (case / "prompt.md").read_text()
    settings = yaml.safe_load(FRONT.match(prompt)[1])
    assert set(settings) <= {"tags", "max_turns", "timeout_seconds", "allowed_tools"}
    assert "Input files:" in prompt and (case / "files").is_dir()
    assert (case / "place-files.sh").stat().st_mode & 0o111
    graders = sorted((case / "graders").glob("*.md"))
    assert graders and all(re.fullmatch(r"\d\d-[a-z0-9-]+\.md", g.name) for g in graders)
    for grader in graders:
        header = yaml.safe_load(FRONT.match(grader.read_text())[1])
        assert header["type"] == "llm" and header["focus"] in ("trace", "output") and header["weight"] == 1
        assert grader.read_text().split("---\n", 2)[2].strip()


def test_every_skill_has_cases_and_a_trigger_set():
    for skill in ("video-read", "claim-cards"):
        assert any(c.parent.parent.name == skill for c in CASES)
        queries = __import__("json").loads((ROOT / "skills" / skill / "evals" / "trigger-eval.json").read_text())
        assert len(queries) == 20 and {q["should_trigger"] for q in queries} == {True, False}
        assert all(q["query"].strip() for q in queries)


def test_rejects_uncovered_number(tmp_path):
    root = files_of("rejects-uncovered-number", tmp_path) / "OUTPUT" / "clip"
    problems = check_bridge(root, ["x"])
    assert any("4.4" in p and "card/reported" in p for p in problems)
    assert not any("55.2" in p for p in problems)


def rebuild_in(name, tmp_path, monkeypatch, folder):
    case = files_of(name, tmp_path)
    monkeypatch.setenv("DATA_DIR", str(case / "data"))
    config = replace(Config.load(), data=case / "data")
    return case, rebuild(case / "OUTPUT" / folder, config=config)


def test_planted_number_error_becomes_a_conflict(tmp_path, monkeypatch):
    case, report = rebuild_in("detects-planted-number-error", tmp_path, monkeypatch, "clip")
    assert len(report["rebuilt"]) == 1 and not report["failures"]
    archive = next((case / "OUTPUT" / "clip" / "archive").glob("*.tx.md")).read_text()
    assert "'55.7': conflict(OCR:55.2)" in archive


def test_translated_answer_is_rejected_and_english_one_is_rebuilt(tmp_path, monkeypatch):
    case, report = rebuild_in("source-language-kept", tmp_path, monkeypatch, "clips")
    assert [i.split("-")[0] for i in report["rebuilt"]] == ["good"]
    [(failed, reason)] = report["failures"]
    assert failed.startswith("translated") and "is Polish" in reason and "never translate" in reason
    card = next((case / "OUTPUT" / "clips" / "cards").glob("good-*.md")).read_text()
    assert "lang: en" in card and "Costs fall by 75%" in card


def test_plan_case_card_has_what_the_graders_look_for():
    card = (ROOT / "skills/claim-cards/evals/plan-from-card-only/files/OUTPUT/cards").glob("*.md")
    text = next(card).read_text()
    assert "status: untested" in text
    for needle in ("54.2%", "50.4%", "58%", "49.6%", "@15", "@23", "500 simulated runs", "How the beacon signal is defined"):
        assert needle in text, needle
    assert "Trade entry and exit rules" in text and "Result after costs as a number" in text
