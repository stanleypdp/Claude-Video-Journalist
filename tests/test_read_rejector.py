"""Rejector: spoken numerals and glued tokens, no field wiped by one number, whole-sentence cuts without
stubs, honest not_stated, on-screen quotes and table labels checked against the OCR."""
# polish-fixtures: one Polish-source case; Polish text is expected.

import warnings

import pytest
import yaml

from tests.test_read_fixes import common, value
from vjournalist.bridge import coverage as cov
from vjournalist.bridge.cards import export_read, finalize_read, normalize_read
from vjournalist.bridge.numbers import digits_for_words, nums
from vjournalist.bridge.transcript import chapters, number_check, version_conflicts

SPEECH_3 = [
    "I tested it on the NASDAQ and gold with default settings, a TR10 factor three.",
    "On the one hour chart it made 1,956 trades, plus 94.9R after costs.",
    "The four hour chart beat just 65% of random runs. Sounds like we found something.",
]
OCR_3 = ["ATR 10", "+94.9R", "H1", "65%"]


def sample3_answer():
    card = {
        "profile": "analysis",
        "claim": "A Supertrend-style indicator (ATR 10, factor 3) looked good on the 1-hour chart.",
        "author_conclusion": "The 1-hour result looked impressive until the indicator met unseen data.",
        "reported": ["1,956 trades on the 1-hour chart, +94.9R after costs @5", "4-hour chart beat just 65% @10"],
        "method_stated": ['"Default settings, a TR10 factor three." @0'],
        "not_stated": [],
        "caution": ['The on-screen text "Sounds like we found something" is the author\'s framing @10'],
        "agent_notes": [],
    }
    article = (
        'He says he tested it with default settings, "ATR 10, factor 3" (spoken as "a TR10 factor three"). '
        'The on-screen text reads "SUPERTREND". '
        "On the one hour chart he reports 1,956 trades, plus 94.9R after costs."
    )
    return value(card, article=article)


# --- 1. numbers read the way the source says them -----------------------------------------------------


@pytest.mark.parametrize(
    ("said", "card"),
    [
        ("On the one hour chart", "the 1-hour chart"),
        ("Eight versions tested", "8 versions"),
        ("a TR10 factor three", "ATR 10, factor 3"),
        ("risk 1R and RISK1R", "risk 1R"),
        ("the H1 chart", "the 1-hour chart"),
        ("around 17,073 touches", "≈ 17 073 touches"),
        ("17,073 level touches", "17073 touches"),
        ("it freed 59k tokens", "59,000 tokens"),
        ("it freed 59 thousand tokens", "59k tokens"),
        ("two point five percent", "2.5%"),
        ("twenty one trades", "21 trades"),
        ("a hundred and five", "105"),
    ],
)
def test_numbers_match_across_words_digits_and_tokens(said, card):
    assert cov.uncovered(card, cov.values(said, words=True)) == []


def test_words_never_become_requirements_and_pronouns_are_not_numbers():
    assert cov.values("one of the two charts") == set()  # card side: digits only
    assert nums("no one knows, one of them", words=True) == {}
    assert cov.uncovered("5 trades", cov.values("five trades")) == ["5"]  # covering side needs words=True
    assert nums("09:30 and v1.2.3") == {}
    assert digits_for_words("factor three and twenty-one") == "factor 3 and 21"


def test_ordinal_after_a_number_is_still_read():
    assert nums("on the NASDAQ 100. First, the standard setup", words=True) == {100.0: "100", 1.0: "First"}
    assert nums("59 thousand tokens", words=True) == {59000.0: "59", 59.0: "59"}  # the scale word is no number


def test_a_number_the_source_lacks_is_still_uncovered():
    assert cov.uncovered("1,957 trades", cov.values("1,956 trades one hour", words=True)) == ["1957"]
    assert cov.uncovered("at 12.5s the slide shows 40%", {40.0}) == []  # "12.5s" is a place in the video


def test_blank_numbers_replaces_number_and_unit_only():
    text, replaced = cov.blank_numbers("It made +94.9R after costs and beat 96% of runs.", ["94.9"])
    assert text == "It made [n/a] after costs and beat 96% of runs." and replaced == ["94.9"]


# --- 1. rejector keeps the field, the profile and the true numbers ------------------------------------


def test_sample3_keeps_claim_profile_and_the_headline_result(tmp_path):
    c = common(SPEECH_3, OCR_3, duration=40.0)
    export_read("s3", sample3_answer(), c, tmp_path)
    card = (tmp_path / "cards/s3.md").read_text()
    meta = yaml.safe_load(card.split("---")[1])
    assert meta["profile"] == "analysis" and meta["thesis_source"] == "card"
    assert "profile_model" not in meta
    assert "ATR 10, factor 3" in card.split("## author_conclusion")[0]
    assert "1,956 trades on the 1-hour chart, +94.9R after costs" in card
    assert "unknown" not in card.split("## method_stated")[0]


def test_sample3_article_has_no_stubs(tmp_path):
    c = common(SPEECH_3, OCR_3, duration=40.0)
    export_read("s3", sample3_answer(), c, tmp_path)
    article = (tmp_path / "articles/s3.md").read_text()
    assert "SUPERTREND" not in article and "reads." not in article and "(spoken as )" not in article
    assert "1,956 trades" in article and 'default settings, "ATR 10, factor 3"' in article
    assert not [s for s in cov.split_sentences(article.partition("##")[0]) if cov.stub_problem(s, 3)]


def test_one_uncovered_number_blanks_the_number_not_the_field():
    card = {
        "profile": "analysis",
        "claim": "Costs fall by 75% with this tool today.",
        "author_conclusion": "It made 12R in a year.",
        "reported": ["Costs fell 75% @0", "12R in a year @1"],
        "method_stated": [],
        "not_stated": [],
        "caution": [],
        "agent_notes": [],
    }
    v, _ = finalize_read(value(card), common(["It made 12R in a year."], ["12R"]))
    c = v["card"]
    assert c["claim"] == "Costs fall by [n/a] with this tool today."
    assert c["author_conclusion"] == "It made 12R in a year."
    assert c["reported"] == ["12R in a year @1"]  # an item that is nothing but the missing number goes
    assert any("[n/a]" in r for r in c["local_rejections"])


def test_stubs_are_detected_and_whole_sentences_are_cut():
    for stub in ('The on-screen text reads.', "Set to default (spoken as ).", 'He wrote "".', "It shows [ ] now."):
        assert cov.stub_problem(stub, 3), stub
    assert cov.stub_problem("As the author says.", 3) is None
    for whole in ("W materiale pokazano odpowiedź Claude'a.", "His read: the 55% was never about 10am.",
                  'The caption reads "THE GOAL ISN\'T" "TO PREDICT THE MOVE." Fine.', "The slide moves on."):  # fmt: skip
        assert cov.stub_problem(whole, 3) is None, whole
    for stub in ("It shows a block titled.", "Win rate 48% (the on-screen text says ), with costs."):
        assert cov.stub_problem(stub, 3), stub
    assert cov.stub_problem("Two words", 3)
    c = common(["Plain speech about trading."], ["ATR 10"])
    article = 'He tested it, "ATR 10" (spoken as "nonsense words"). The on-screen text reads "SUPERBAND". Plain trading speech.'
    v, _ = finalize_read(value({"profile": "opinion", "claims": ["Trading @0"], "evidence_given": [], "not_stated": [], "caution": []}, article=article), c)
    text = v["article"][0]["text"]
    assert "reads" not in text and "( )" not in text and "(spoken as )" not in text
    assert text.endswith(".") and cov.stub_problem(text, 3) is None


def test_not_stated_template_needs_a_negative_check():
    speech = ["We tested gold over 6 years.", "More than 17,000 level touches were measured, 45.5% rejected."]
    payload = {
        "transcript": {"language": "en", "segments": [{"start": 0, "end": 4, "text": t} for t in speech]},
        "ocr": [],
        "metadata": {"duration_s": 60},
    }
    card = {"profile": "analysis", "domain": "trading, gold", "claim": "x", "author_conclusion": "x",
            "reported": ["45.5% rejected @1"], "method_stated": [], "not_stated": [], "caution": [], "agent_notes": []}  # fmt: skip
    out = normalize_read(value(card), payload)["card"]["not_stated"]
    assert not any("sample size" in x or "instrument" in x for x in out)
    assert any("costs" in x for x in out)  # nothing said about costs: the gap stays
    silent = {**payload, "transcript": {"language": "en", "segments": [{"start": 0, "end": 4, "text": "It worked."}]}}
    out = normalize_read(value({**card, "domain": "trading", "reported": []}), silent)["card"]["not_stated"]
    assert any("sample size" in x for x in out) and any("instrument" in x for x in out)


# --- number_check: false conflicts and version mismatches ---------------------------------------------


def test_a_screen_number_that_is_also_spoken_is_no_conflict():
    res, _, _ = number_check("The signal lost 0.16R, the random run lost 0.13R.", ["0.16R"])
    assert res == {"0.13": "speech_only", "0.16": "ok"}
    res, _, _ = number_check("The 15 minute chart lost, the 4 hour chart beat 65%.", ["65%"])
    assert res["15"] == "speech_only"
    res, _, _ = number_check("It lost 124R.", ["It lost 125R"])
    assert res["124"] == "conflict(OCR:125)"


def test_conflict_needs_the_same_moment():
    speech_at = [(0.0, 4.0, "It lost 124R.")]
    far = [(30.0, 31.0, "125R")]
    near = [(2.0, 5.0, "125R")]
    assert number_check("It lost 124R.", ["125R"], speech_at, far)[0]["124"] == "speech_only"
    assert number_check("It lost 124R.", ["125R"], speech_at, near)[0]["124"] == "conflict(OCR:125)"


def test_screen_version_that_differs_from_speech_is_a_conflict_and_a_caution():
    speech = ["Three hacks.", "Sonnet 4.6 for the rest.", "Claude uses Opus 4.7 only for planning."]
    ocr = ["Set model to", "Opus4.6inplanmode"]
    c = common(speech, ocr)
    assert version_conflicts(" ".join(speech), ocr) == [("opus", "4.7", "4.6")]
    card = {"profile": "howto", "goal": "Plan with Opus 4.7 @0", "steps": ["[action] Use Opus 4.7 for planning @0"],
            "tools_named": ["Opus 4.7"], "not_stated": [], "caution": []}  # fmt: skip
    v, _ = finalize_read(value(card), c)
    assert v["card"]["number_check"]["4.7"] == "conflict(OCR:4.6)"
    assert any("version mismatch" in x and "Opus 4.6" in x for x in v["card"]["caution"])


# --- 2. on-screen quotes and table labels --------------------------------------------------------------


def test_spoken_screen_quote_is_attributed_to_the_speech_and_invented_one_is_cut():
    speech = ["Use /model opus plan.", "It saves a lot of context overall."]
    ocr = ["/model", "Fewer tokens. Same context."]
    c = common(speech, ocr)
    article = (
        'The terminal shows the "/model" command and the "/model opus plan" option. '
        'A slide reads "Compress your CONTEXT" and "Fewer tokens. Same context.", then it moves on.'
    )
    card = {"profile": "opinion", "claims": ["Plan mode saves context @0"], "evidence_given": [], "not_stated": [], "caution": []}
    v, _ = finalize_read(value(card, article=article), c)
    text = v["article"][0]["text"]
    assert '"/model opus plan" [spoken]' in text and cov.NOT_IN_OCR not in text
    assert "Compress your CONTEXT" not in text and '"Fewer tokens. Same context."' in text
    rejections = " ".join(v["card"]["local_rejections"])
    assert "but is spoken" in rejections and "Compress your CONTEXT" in rejections


def test_quotes_with_two_shared_words_with_one_ocr_line_are_kept():
    assert cov.in_ocr("Squeezes chat into summary", "Squeezes your chat into a tight summary")
    assert not cov.in_ocr("Compress your CONTEXT", "Squeezes your chat into a tight summary")
    assert not cov.in_ocr("/model opusplan", "/model\nSet model to")


def test_sentence_split_keeps_quotations_whole():
    parts = cov.split_sentences('A slide reads "Fewer tokens. Same context." and more. Next one.')
    assert parts == ['A slide reads "Fewer tokens. Same context." and more.', "Next one."]


def test_table_rows_without_a_label_in_the_ocr_become_unlabeled():
    ocr = ["64.3%", "53.4%", "WIN RATE", "57%"]
    c = common(["Opus launched today."], ocr)
    rows = [
        {"timestamp_s": 10.0, "label": "SWE-bench Pro, Opus 4.7", "value": "64.3%", "confidence": "approximate"},
        {"timestamp_s": 10.0, "label": "Agentic search, Opus 4.6", "value": "53.4%", "confidence": "approximate"},
        {"timestamp_s": 12.0, "label": "Win rate", "value": "57%", "confidence": "exact"},
    ]
    card = {"profile": "opinion", "claims": ["Launch @0"], "evidence_given": [], "not_stated": [], "caution": []}
    v, _ = finalize_read(value(card, screen_data=rows), c)
    assert [r["label"] for r in v["screen_data"]] == ["unlabeled", "unlabeled", "Win rate"]
    assert sum("row kept without a label" in x for x in v["card"]["local_rejections"]) == 2


# --- 3. language of the labels, soft chapter spacing ---------------------------------------------------


def test_english_files_have_english_labels_and_polish_files_keep_polish(tmp_path):
    for lang, heading, header, none in (
        ("en", "## Data from charts and slides", "| Time | Data | Value | Source | Confidence |", "none given in the source"),
        ("pl", "## Dane z wykresów i plansz", "| Czas | Dane | Wartość | Źródło | Pewność |", "brak w źródle"),
    ):
        c = common(["Wynik to 12R."], ["12R"])
        c["transcript"]["language"] = lang
        rows = [{"timestamp_s": 1.0, "label": "Wynik", "value": "12R", "confidence": "exact"}]
        card = {"profile": "opinion", "claims": ["Wynik @0"], "evidence_given": [], "not_stated": [], "caution": []}
        export_read(f"x-{lang}", value(card, screen_data=rows), c, tmp_path)
        article = (tmp_path / "articles" / f"x-{lang}.md").read_text()
        assert heading in article and header in article
        text = (tmp_path / "cards" / f"x-{lang}.md").read_text()
        assert none in text
        screen = (tmp_path / "archive" / f"x-{lang}.screen.md").read_text()
        assert ("First and last appearance" in screen) == (lang == "en")


def test_chapter_spacing_is_a_warning_not_an_error(tmp_path):
    from types import SimpleNamespace

    receipt = tmp_path / "chapters" / "long"
    receipt.mkdir(parents=True)
    (receipt / "response.json").write_text('{"result": "[00:00] Intro\\n[01:00] Middle\\n[08:00] End"}')
    tr = {"segments": [{"start": 0, "end": 5, "text": "Hello there."}]}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        target = chapters("long", tr, 600, SimpleNamespace(data=tmp_path), tmp_path / "bridge")
    assert target.read_text().startswith("[00:00] Intro")
    assert any("chapter spacing" in str(w.message) for w in caught)
    (receipt / "response.json").write_text('{"result": "[00:00] Intro\\n[01:00] Middle\\n[bad] End"}')
    with pytest.raises(ValueError, match="Invalid chapter format"):
        chapters("long", tr, 600, SimpleNamespace(data=tmp_path), tmp_path / "bridge")
