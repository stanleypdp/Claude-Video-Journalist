"""Number/screen-claim coverage validator and the bridge gate."""
# polish-fixtures: the screen-claim checks below run on Polish sentences (a supported source language).

import pytest

from vjournalist.bridge.coverage import (
    check_bridge,
    derived_ok,
    drop_unanchored_parentheses,
    evaluate,
    screen_claim_problem,
    uncovered,
    values,
)

CARD = """---
id: x
type: thesis_card
profile: analysis
number_check:
  '55.2': ok
---
# Test

## reported

- Level touched in 55.2% of sessions @30
{extra}
"""
ARTICLE = """# Test

The author reports 55.2% of sessions.

## Data from charts and slides

| Time | Data | Value | Source | Confidence |
|---|---|---|---|---|
| 00:30 | Level | 55.2% | screen+speech | exact |
"""


def bridge(tmp_path, extra="", article=ARTICLE):
    for folder in ("cards", "articles", "archive"):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    (tmp_path / "cards/x.md").write_text(CARD.format(extra=extra))
    (tmp_path / "articles/x.md").write_text(article)
    (tmp_path / "archive/x.tx.md").write_text(
        "---\nid: x\nduration_s: 60\n---\n[00:30] The level was touched in 55.2% of sessions.\n"
    )
    (tmp_path / "archive/x.screen.md").write_text(
        "# Screen: x\n\nFirst and last appearance.\nFiltered: 0.\n\n[30.000–31.000s] 55.2%\n"
    )
    return tmp_path


def test_number_tolerance_ocr_o_commas_and_approx():
    assert values("≈ 1,00O SIMULATIONS") == {1000.0}
    assert values("1,096") == {1096.0} and values("55,2%") == {55.2}
    assert uncovered("result +4.4 pts @12", values("45.0 40.6")) == ["4.4"]


def test_derived_requires_formula_over_covered_numbers():
    covered = values("45.0 and 40.6")
    assert evaluate("45.0 - 40.6", covered) == pytest.approx(4.4)
    assert derived_ok({"value": "+4.4 pkt", "formula": "45.0 - 40.6"}, covered)
    assert not derived_ok({"value": "+4.4 pkt", "formula": "45.0 - 41"}, covered)
    assert not derived_ok({"value": "+9 pkt", "formula": "45.0 - 40.6"}, covered)
    assert not derived_ok({"value": "5", "formula": "__import__('os')"}, covered)


def test_screen_claims_need_tokens_present_in_ocr():
    ocr = "npx skills add acme/linekit\ntheme\nrate limiter"
    assert screen_claim_problem("Na ekranie widać komendę npx skills add acme/linekit.", ocr) is None
    assert "not in OCR" in screen_claim_problem("Widoczny na ekranie pakiet @someone/other-package.", ocr)
    assert screen_claim_problem("Na ekranie widać coś ładnego.", ocr)
    assert "dark" in screen_claim_problem("Na ekranie widać „rate limiter” w ciemnym motywie.", ocr)
    assert screen_claim_problem("Autor mówi o strategii.", ocr) is None
    assert (
        drop_unanchored_parentheses("Example (rate limiter) and (sales funnel)", ocr)
        == "Example (rate limiter) and"
    )


def test_clean_bridge_passes(tmp_path):
    assert check_bridge(bridge(tmp_path), ["x"]) == []


def test_uncovered_number_in_card_article_or_table_is_reported(tmp_path):
    root = bridge(tmp_path, extra="- Edge +4.4 pts @37")
    assert any("4.4" in p and "card" in p for p in check_bridge(root, ["x"]))
    root = bridge(tmp_path, article=ARTICLE.replace("55.2% of sessions.", "55.2% of sessions, and 77 times more."))
    assert any("number 77" in p for p in check_bridge(root, ["x"]))
    root = bridge(
        tmp_path, article=ARTICLE.replace("| 55.2% | screen+speech | exact", "| 55.2% | speech | speech")
    )
    assert any("speech" in p for p in check_bridge(root, ["x"]))
