"""Read after review 8: attribution corrected instead of marked, table labels trimmed, rejected content kept
out of the card, proper names checked in thesis/claim/title, and the three review metrics."""

import yaml

from tests.test_read_fixes import common, value
from vjournalist.bridge import coverage as cov
from vjournalist.bridge import quality as Q
from vjournalist.bridge import rejections as R
from vjournalist.bridge.cards import export_read, finalize_read

OPINION = {"profile": "opinion", "claims": ["Plan mode saves context @0"], "evidence_given": [], "not_stated": [], "caution": []}


def opinion(**fields):
    return {**OPINION, **fields}


# --- 1. screen vs speech: the attribution is corrected, no marker --------------------------------------


def test_spoken_quote_given_as_ocr_text_is_attributed_to_the_speech():
    speech = ["Stop using Make.com and start using OpenClock, which is later spelled Open Claw."]
    c = common(speech, ["Make.com"])
    article = 'He says to stop using Make.com and start using OpenClock (OCR shows "OpenClaw").'
    v, _ = finalize_read(value(opinion(), article=article), c)
    text = v["article"][0]["text"]
    assert 'OpenClock (the author says "OpenClaw")' in text
    assert cov.NOT_IN_OCR not in text and "OCR shows" not in text
    assert any("is spoken" in r or "but is spoken" in r for r in v["card"]["local_rejections"])


def test_on_screen_text_noun_becomes_spoken_line_in_a_card_field():
    speech = ["We looked at the result.", "Sounds like we found something.", "Then it fell apart."]
    c = common(speech, ["ATR 10"])
    card = opinion(caution=['The on-screen text "Sounds like we found something" is the author\'s own framing @5'])
    v, _ = finalize_read(value(card), c)
    line = v["card"]["caution"][0]
    assert line.startswith('The spoken line "Sounds like we found something" is the author\'s own framing')
    assert cov.NOT_IN_OCR not in line and "on-screen" not in line


def test_shared_cue_with_a_verified_quote_tags_the_spoken_one():
    c = common(["Use /model opus plan.", "It saves context."], ["/model"])
    article = 'The terminal shows the "/model" command and the "/model opus plan" option.'
    v, _ = finalize_read(value(opinion(), article=article), c)
    text = v["article"][0]["text"]
    assert '"/model" command' in text and '"/model opus plan" [spoken] option' in text
    assert cov.NOT_IN_OCR not in text
    assert not cov.screen_quotes(text, marked=True) or all(q == "/model" for _, q in cov.screen_quotes(text, marked=True))


def test_quote_in_neither_source_is_still_cut_and_never_marked():
    c = common(["Plain speech about context."], ["Fewer tokens."])
    article = 'A slide reads "Compress your CONTEXT" and "Fewer tokens.", then it moves on.'
    v, _ = finalize_read(value(opinion(), article=article), c)
    text = v["article"][0]["text"]
    assert "Compress your CONTEXT" not in text and cov.NOT_IN_OCR not in text and '"Fewer tokens."' in text


# --- 2. table labels are trimmed, not wiped -----------------------------------------------------------


def labelled(label, value_, ocr, speech, **kw):
    c = common(speech, ocr)
    rows = [{"timestamp_s": 10.0, "label": label, "value": value_, "confidence": "approximate"}]
    return finalize_read(value(opinion(), screen_data=rows), c)[0], c


def test_label_keeps_the_part_confirmed_next_to_the_number():
    v, _ = labelled("BEST VERSION AFTER COSTS", "−227R", ["−227R"], ["Results.", "Other.", "After costs, minus 227R."])
    label = v["screen_data"][0]["label"]
    assert "after costs" in label.lower() and "best" not in label.lower() and "version" not in label.lower()
    assert any("removed words" in r and "BEST VERSION" in r for r in v["card"]["local_rejections"])


def test_label_without_any_confirmed_word_is_unlabeled():
    v, _ = labelled("Agentic coding (SWE-bench Pro), Opus 4.7", "64.3%", ["64.3%"], ["Opus launched today."])
    assert v["screen_data"][0]["label"] == "unlabeled"


def test_scattered_confirmed_words_do_not_make_a_label():
    # "Agentic" and "Opus" are around the number, but not next to each other: stitching them would invent a label
    ocr = ["64.3%", "Claude Opus 4.7"]
    v, _ = labelled("Agentic coding (SWE-bench Pro), Opus 4.7", "64.3%", ocr, ["Agentic work.", "x", "y"])
    assert v["screen_data"][0]["label"] == "unlabeled"


def test_glued_ocr_words_confirm_the_label_and_inflections_count():
    v, _ = labelled("Max drawdown", "19.7%", ["MAXDRAWDOWN 19.7%"], ["Nothing."])
    assert v["screen_data"][0]["label"] == "Max drawdown"
    v, _ = labelled("Share of random runs beaten", "96%", ["96%"], ["It beat 96% of random runs.", "x", "y"])
    assert v["screen_data"][0]["label"] == "Share of random runs beaten"


def test_fully_confirmed_label_is_untouched():
    v, _ = labelled("Win rate", "57%", ["57%", "WIN RATE"], ["Opus launched today."])
    assert v["screen_data"][0]["label"] == "Win rate"
    assert not v["card"].get("local_rejections")


# --- 2. rejected content leaves the card -----------------------------------------------------------------


def test_card_lists_only_field_and_reason_and_the_file_keeps_the_content(tmp_path):
    ocr = ["64.3%", "53.4%"]
    c = common(["Opus launched today."], ocr)
    rows = [
        {"timestamp_s": 10.0, "label": "Agentic coding (SWE-bench Pro), Opus 4.7", "value": "64.3%", "confidence": "approximate"},
        {"timestamp_s": 11.0, "label": "Agentic search, Opus 4.6", "value": "53.4%", "confidence": "approximate"},
    ]
    export_read("s4", value(opinion(), screen_data=rows), c, tmp_path)
    card = (tmp_path / "cards/s4.md").read_text()
    rejections = (tmp_path / "archive/s4.rejections.md").read_text()
    assert "SWE-bench" not in card and "Agentic" not in card
    assert "table: label not confirmed next to the number; row kept without a label (×2)" in card
    assert "SWE-bench Pro" in rejections and "64.3%" in rejections


def test_no_rejections_means_no_file_and_no_section(tmp_path):
    c = common(["Plain speech."], [])
    export_read("clean", value(opinion()), c, tmp_path)
    export_read("clean", value(opinion()), c, tmp_path)
    assert "local_rejections" not in (tmp_path / "cards/clean.md").read_text()
    assert not (tmp_path / "archive/clean.rejections.md").exists()


def test_stale_rejections_file_is_removed_on_rebuild(tmp_path):
    c = common(["Plain speech."], ["64.3%"])
    rows = [{"timestamp_s": 10.0, "label": "Made up label", "value": "64.3%", "confidence": "approximate"}]
    export_read("x", value(opinion(), screen_data=rows), c, tmp_path)
    assert (tmp_path / "archive/x.rejections.md").exists()
    export_read("x", value(opinion()), c, tmp_path)
    assert not (tmp_path / "archive/x.rejections.md").exists()


def test_brief_never_quotes_the_rejected_tokens():
    line = "article: The screen shows SUPERBAND now. — not in OCR: SUPERBAND"
    assert R.brief(line, "en") == "article: sentence removed — not in OCR"
    assert "SUPERBAND" not in R.brief(line, "en")


def test_every_message_the_code_writes_parses_back():
    from vjournalist.bridge import lang as L

    fields = {k: "x" for k in ("key", "text", "reason", "numbers", "cuts", "label", "value", "quote", "removed", "name", "action", "formula")}
    for lang in L.MESSAGES:
        for kind in R.KINDS:
            line = L.say(lang, kind, **fields)
            assert R.parse(line)[0] == kind, (lang, kind)
            assert R.brief(line, lang)


# --- 3. proper names in thesis, claim, title --------------------------------------------------------------

SPEECH_3 = ["I tested it with default settings, a TR10 factor three.", "On the one hour chart it made 1,956 trades."]


def analysis(claim, **extra):
    return {
        "profile": "analysis",
        "claim": claim,
        "author_conclusion": "It looked good.",
        "reported": ["1,956 trades on the 1-hour chart @5"],
        "method_stated": [],
        "not_stated": [],
        "caution": [],
        "agent_notes": [],
        **extra,
    }


def test_name_missing_in_the_source_is_marked_and_the_rest_of_the_thesis_stays():
    c = common(SPEECH_3, ["ATR 10"])
    v, _ = finalize_read(value(analysis("A Supertrend-style indicator (ATR 10, factor 3) looked good on the 1-hour chart.")), c)
    claim = v["card"]["claim"]
    assert "Supertrend" not in claim
    assert claim == "A [name not in source]-style indicator (ATR 10, factor 3) looked good on the 1-hour chart."
    assert any("Supertrend" in r and "proper name" in r for r in v["card"]["local_rejections"])


def test_model_generic_description_in_brackets_replaces_the_name():
    c = common(SPEECH_3, ["ATR 10"])
    v, _ = finalize_read(value(analysis("The test of Supertrend (a trend-following indicator) looked good @5.")), c)
    assert v["card"]["claim"] == "The test of a trend-following indicator looked good @5."


def test_names_found_in_speech_or_ocr_survive_even_spaced_or_hyphenated():
    c = common(["Stop using Make.com and start using Open Claw with Super-trend filters."], ["TradingView 5.0"])
    claim = "Teams moved from Make.com to OpenClaw and TradingView with Supertrend filters."
    v, _ = finalize_read(value(analysis(claim, reported=["Teams moved @0"])), c)
    assert v["card"]["claim"] == claim
    assert not v["card"].get("local_rejections")


def test_title_and_thesis_are_checked_but_domain_and_tags_are_not(tmp_path):
    c = common(SPEECH_3, ["ATR 10"])
    val = value(analysis("A Supertrend-style indicator looked good on the 1-hour chart."))
    val["title"] = "Why Supertrend failed on one hour"
    val["card"]["domain"] = "trading, Supertrend"
    val["tags"] = ["Supertrend"]
    export_read("n", val, c, tmp_path)
    card = (tmp_path / "cards/n.md").read_text()
    meta = yaml.safe_load(card.split("---")[1])
    assert "Supertrend" not in meta["thesis"] and "[name not in source]" in meta["thesis"]
    assert "# Why [name not in source] failed on one hour" in card
    assert meta["domain"] == "trading, Supertrend"
    article = (tmp_path / "articles/n.md").read_text()
    assert article.startswith("# Why [name not in source] failed on one hour")


# --- 4. the three metrics ---------------------------------------------------------------------------------


def built(tmp_path, speech, ocr, article, rows=(), card=None):
    c = common(speech, ocr)
    export_read("m", value(card or opinion(), article=article, screen_data=list(rows)), c, tmp_path)
    return tmp_path


def test_metrics_of_a_clean_result(tmp_path):
    built(tmp_path, ["Use the terminal."], ["npm install"], 'The terminal shows "npm install" on screen.')
    total = Q.rates(Q.measure(tmp_path, ["m"]))
    assert total["screen_attribution_ok"] == 1.0 and total["not_in_ocr_per_card"] == 0.0
    assert total["false_rejection_rate"] == 0.0


def test_a_legacy_marker_counts_against_attribution_and_in_the_marker_average(tmp_path):
    built(tmp_path, ["Use the terminal."], ["npm install"], 'The terminal shows "npm install" on screen.')
    path = tmp_path / "articles/m.md"
    path.write_text('# T\n\nOCR shows "OpenClaw" [not in OCR] and "npm install".\n')
    total = Q.rates(Q.measure(tmp_path, ["m"]))
    assert total["not_in_ocr"] == 1 and total["not_in_ocr_per_card"] == 1.0
    assert total["screen_phrases"] == 2 and total["screen_attribution_ok"] == 0.5


def test_false_rejection_is_a_removed_label_the_source_says_next_to_the_number(tmp_path):
    built(tmp_path, ["After costs, minus 227R."], ["−227R"], "Plain.")
    (tmp_path / "archive/m.rejections.md").write_text(
        "- table: label “BEST VERSION AFTER COSTS” is not in the OCR next to -227R; row kept without a label\n"
        "- table: label “Made up thing” is not in the OCR next to -227R; row kept without a label\n"
        "- steps: quote “/model opusplan” given as on-screen text is not in the OCR — marked [not in OCR]\n"
    )
    total = Q.measure(tmp_path, ["m"])
    assert total["rejections"] == 2 and total["false_rejections"] == 1  # a marked quote is no removal
    assert Q.rates(total)["false_rejection_rate"] == 0.5


def test_read_report_carries_the_three_metrics(tmp_path):
    from dataclasses import replace

    from vjournalist.config import Config
    from vjournalist.read_batch import format_report, read_metrics
    from vjournalist.storage import atomic_json, slug

    config = replace(Config.load(), data=tmp_path / "data", bridge=tmp_path / "bridge")
    digest = "a" * 64
    atomic_json(config.data / "cache" / digest / "provenance.json", {"name": "clip"})
    id_ = f"{slug('clip')}-{digest[:12]}"
    built_card = common(["Use the terminal."], ["npm install"])
    export_read(id_, value(opinion(), article='The terminal shows "npm install" on screen.'), built_card, config.bridge)
    metrics = read_metrics(config, [{"sha256": digest, "status": "analyzed"}, {"sha256": "b" * 64, "status": "error"}])
    assert metrics["cards"] == 1 and metrics["screen_attribution_ok"] == 1.0 and metrics["false_rejection_rate"] == 0.0
    report = {
        "folder": "f", "paused_s": 0, "rows": [],
        "summary": {"files": 1, "analyzed": 1, "cache": 0, "duplicates": 0, "errors": 0, "pending": 0,
                    "cost_usd": 0.0, "historical_cost_usd_cache": 0.0},
        "read_metrics": metrics,
    }  # fmt: skip
    text = format_report(report)
    assert "false_rejection_rate: 0.0%" in text and "screen_attribution_ok: 100.0%" in text
    assert "not_in_ocr_per_card: 0.00" in text
