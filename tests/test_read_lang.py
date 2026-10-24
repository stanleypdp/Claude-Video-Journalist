"""Source language, rejected-answer handling, thesis in INDEX, output folder. Includes Polish-source fixtures."""
# polish-fixtures: Polish-language source support is tested here, so Polish sentences are expected.

import json
import subprocess

import pytest

from vjournalist.pipeline import content_scan


@pytest.fixture
def audio_outlasts_video(tmp_path):
    """Container 1.5 s, video stream 1.2 s: the layout of the failing file (audio 45.30 s, video 45.28 s)."""
    path = tmp_path / "long-audio.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=160x288:r=25:d=1.2",
         "-f", "lavfi", "-i", "sine=f=440:d=1.5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(path)],
        check=True,
    )  # fmt: skip
    return path


def test_last_frame_when_audio_outlasts_video(audio_outlasts_video, tmp_path, monkeypatch):
    metadata = {"duration_s": 1.5, "fps": 25}
    work = tmp_path / "work"
    frame = content_scan.extract_frame(str(audio_outlasts_video), work, 1.46, metadata)
    assert frame.exists() and frame.stat().st_size > 0
    monkeypatch.setattr(content_scan, "FRAME_RETRIES", 0)
    with pytest.raises(RuntimeError):
        content_scan.extract_frame(str(audio_outlasts_video), tmp_path / "work2", 1.46, metadata)


def test_last_frame_when_ffmpeg_exits_zero_without_output(audio_outlasts_video, tmp_path, monkeypatch):
    """Older ffmpeg builds (Linux CI) exit 0 and write nothing when the seek is past the last video frame."""
    real_run = content_scan.run

    def lenient_run(args, *a, **kw):
        if float(args[args.index("-ss") + 1]) > 1.2:
            return ""
        return real_run(args, *a, **kw)

    monkeypatch.setattr(content_scan, "run", lenient_run)
    frame = content_scan.extract_frame(
        str(audio_outlasts_video), tmp_path / "work", 1.46, {"duration_s": 1.5, "fps": 25}
    )
    assert frame.exists() and frame.stat().st_size > 0


# --- source language ----------------------------------------------------------------------

from copy import deepcopy  # noqa: E402

import yaml  # noqa: E402

from tests.test_read_fixes import common, value  # noqa: E402
from vjournalist.bridge import lang as L  # noqa: E402
from vjournalist.bridge.cards import (  # noqa: E402
    build_index,
    card_thesis,
    clean_prose,
    export_read,
    finalize_read,
    normalize_read,
    production_terms,
    tag_step,
    validate_read,
)
from vjournalist.bridge.coverage import claim_problem, repair_sentence  # noqa: E402
from vjournalist.config import ROOT, Config  # noqa: E402
from vjournalist.pipeline.payload import build_payload  # noqa: E402
from vjournalist.read_batch import default_output  # noqa: E402
from vjournalist.roles import schema_for_role  # noqa: E402
from vjournalist.service import reuse_common  # noqa: E402
from vjournalist.storage import atomic_json  # noqa: E402

SPEECH = ["NASDAQ tested 55.2% since 2020.", "Profit was 136R before costs.", "We prompt six camera moves."]


def payload_for(language, speech=SPEECH):
    return {
        "role": "knowledge",
        "schema_version": 6,
        "metadata": {"duration_s": 60},
        "transcript": {
            "language": language,
            "segments": [{"start": i * 5.0, "end": i * 5.0 + 4, "text": t} for i, t in enumerate(speech)],
        },
        "ocr": [{"text": "55.2%", "text_confidence": "exact"}],
    }


def english_answer():
    return {
        "schema_version": 6,
        "role": "knowledge",
        "title": "Does NASDAQ drift to the POC?",
        "tags": ["trading", "NASDAQ"],
        "article": [{"start": 0, "text": 'The author says: "NASDAQ tested 55.2% since 2020."'}],
        "screen_data": [],
        "card": {
            "profile": "analysis",
            "domain": "finance",
            "claim": "NASDAQ tested 55.2% since 2020.",
            "author_conclusion": "Profit was 136R before costs.",
            "reported": ["55.2% @0"],
            "method_stated": [],
            "not_stated": [],
            "caution": ["The author's claims are unverified."],
            "agent_notes": [],
        },
    }


def test_schema_prompt_and_payload_carry_the_language_rule(tmp_path):
    schema = schema_for_role("knowledge", {"schema_version": 6})
    assert schema["properties"]["schema_version"]["const"] == 6
    prompt = (ROOT / "prompts/knowledge.txt").read_text()
    assert "never translate" in prompt and "Quote verbatim" in prompt and "schema v6" in prompt
    c = common(SPEECH)
    c["transcript"]["language"] = "en"
    c["platform_info"] = {"content_duration_s": 60.0}
    c["scan"]["frames"] = []
    c["metadata"]["duration_s"] = 60.0
    payload = build_payload(c, None, tmp_path)
    assert payload["schema_version"] == 6 and payload["output_language"] == "en"


def test_english_answer_passes_and_gets_english_gaps():
    p = payload_for("en")
    v = normalize_read(english_answer(), p)
    validate_read(v, p)
    gaps = " ".join(v["card"]["not_stated"])
    assert "statistical significance: not stated in the provided source text" in gaps
    assert "brak w dostarczonym" not in gaps


def test_polish_gaps_stay_polish_for_a_polish_transcript():
    v = normalize_read(deepcopy(english_answer()), payload_for("pl"))
    assert any("istotność statystyczna: brak w dostarczonym tekście źródłowym" in t for t in v["card"]["not_stated"])


@pytest.mark.parametrize(
    "field,text",
    [
        ("title", "Czy NASDAQ wraca do POC?"),
        ("article", "Autor twierdzi, że NASDAQ rośnie."),
        ("reported", "Zysk 136R przed kosztami @5"),
        ("caution", "Wyniki są niezweryfikowane, ale jest to tylko deklaracja."),
    ],
)
def test_translated_content_is_rejected_for_english_transcript(field, text):
    p, v = payload_for("en"), english_answer()
    if field == "title":
        v["title"] = text
    elif field == "article":
        v["article"][0]["text"] = text
    else:
        v["card"][field] = [text]
    v = normalize_read(v, p)
    with pytest.raises(ValueError, match="never translate"):
        validate_read(v, p)


def test_polish_inside_verbatim_quotes_and_polish_transcripts_are_not_rejected():
    p, v = payload_for("en"), english_answer()
    v["article"][0]["text"] = 'The caption reads „Dzień dobry, to jest test”.'
    validate_read(normalize_read(v, p), p)
    pl = english_answer()
    pl["article"][0]["text"] = "Autor twierdzi, że NASDAQ rośnie."
    validate_read(normalize_read(pl, payload_for("pl")), payload_for("pl"))
    assert L.polish_in("Plain English with an ordinary sentence.") is None


def test_english_assumption_and_step_labels():
    c = common(["Profit was 136R and 97R.", "Costs took the rest."])
    c["transcript"]["language"] = "en"
    v = value({"profile": "analysis", "claim": "Profit was 136R after costs.", "author_conclusion": "x",
               "reported": ["Profit after costs was 97R @0"], "method_stated": [], "not_stated": [],
               "caution": [], "agent_notes": []}, article="The author reports two results.")  # fmt: skip
    out, _ = finalize_read(v, c)
    notes = " ".join(out["card"].get("agent_notes", []))
    assert "założenie" not in notes
    assert tag_step("Open the app @3", "en") == "[action] Open the app @3"
    assert tag_step("The tool shows a list @9", "en") == "[effect] The tool shows a list @9"
    assert tag_step("Wejdź na stronę @3", "pl") == "[akcja] Wejdź na stronę @3"
    assert tag_step("[akcja] Wejdź @1") == "[akcja] Wejdź @1"


def test_verbatim_quote_survives_finalize():
    c = common(["The slide says Buy the dip.", "Result was 12R."], screen=["Buy the dip", "12R"])
    c["transcript"]["language"] = "en"
    v = value({"profile": "analysis", "claim": 'The slide says "Buy the dip" and the result was 12R.',
               "author_conclusion": "x", "reported": ["Result 12R @5"], "method_stated": [],
               "not_stated": [], "caution": [], "agent_notes": []},
              article='On screen: "Buy the dip".')  # fmt: skip
    out, _ = finalize_read(v, c)
    assert "Buy the dip" in out["card"]["claim"] and "Buy the dip" in out["article"][0]["text"]
    assert not out["card"].get("local_rejections")


def test_export_writes_lang_and_index_column(tmp_path):
    c = common(["NASDAQ tested 55.2% since 2020.", "That is all."], screen=["55.2%"])
    c["transcript"]["language"] = "en"
    export_read("clip-1", english_answer(), c, tmp_path)
    front = yaml.safe_load((tmp_path / "cards/clip-1.md").read_text().split("---", 2)[1])
    assert front["lang"] == "en" and front["schema_version"] == 6 and front["thesis_source"] == "card"
    index = (tmp_path / "INDEX.md").read_text()
    assert "| id | profile | lang |" in index.splitlines()[2] and "| analysis | en |" in index


def test_mechanics_of_an_older_schema_version_are_reused(tmp_path):
    base = tmp_path / "cache" / "abc"
    old, new = base / "roles/knowledge/v5", base / "roles/knowledge/v6"
    full = {"transcript": {"language": "en", "segments": []}, "scan": {}, "metadata": {}, "platform_info": {}}
    atomic_json(old / "common.json", full)
    reused = reuse_common(base, new)
    assert reused["transcript"]["language"] == "en" and reused["mechanics_reused"] == ["common.json (v5)"]
    atomic_json(old / "common.json", {"transcript": {}})
    assert reuse_common(base, new) is None


# --- answer rejected for the word "camera" ---------------------------------------------------


def test_craft_words_are_allowed_when_the_video_says_them():
    assert production_terms("Six camera moves from one photo.", "we prompt six camera moves") == []
    assert production_terms("Ruchy kamery z jednego zdjęcia.", "we prompt six camera moves") == []
    assert production_terms("Slow camera work and colour grading.", "we talk about AI prompts") == ["camera", "colour grading"]
    p = payload_for("en")
    v = english_answer()
    v["article"][0]["text"] = "The author prompts six camera moves."
    validate_read(normalize_read(v, p), p)
    v["article"][0]["text"] = "Smooth camera work and framing."
    with pytest.raises(ValueError, match="production description"):
        validate_read(normalize_read(v, payload_for("en", ["Profit was 136R."])), payload_for("en", ["Profit was 136R."]))


def test_shot_vocabulary_is_removed_only_when_not_in_the_source():
    text = "The author shows the trade. The first shot is a chart."
    assert clean_prose(text, "we show the trade") == "The author shows the trade."
    assert "shot" in clean_prose(text, "the first shot is a chart")


# --- thesis in INDEX -------------------------------------------------------------------------


def body_with(claim="", rejected=""):
    text = f"# Title\n\n## claim\n\n{claim}\n\n## reported\n\n- x @1\n"
    return text + (f"\n## local_rejections\n\n- {rejected}\n" if rejected else "")


def test_thesis_levels():
    article = "# Title\n\nThe author compares two tools. A second sentence follows.\n"
    assert card_thesis("analysis", body_with("The author compares two tools @4."), article) == (
        "The author compares two tools.",
        "card",
    )
    for empty in ("", "@0 @10 @25", "unknown — claim requires source verification"):
        rejected = "claim: The author presents Ruflo as the strongest tool for Claude. — brak w OCR: Ruflo"
        assert card_thesis("news_promo", body_with(empty, rejected), article) == (
            "The author presents Ruflo as the strongest tool for Claude.",
            "claim_rejected",
        )
        numeric = "claim: Costs fall by 75% with this tool today. — liczba bez pokrycia w źródle (75)"
        assert card_thesis("news_promo", body_with(empty, numeric), article) == (
            "The author compares two tools.",
            "fallback",
        )
    assert card_thesis("news_promo", body_with(""), "# T\n\n")[0] == "unknown"  # no article at all: last resort


def test_index_never_has_an_empty_or_unknown_thesis_and_fallback_is_profile_other(tmp_path):
    cards, articles = tmp_path / "cards", tmp_path / "articles"
    cards.mkdir()
    articles.mkdir()
    for name, body in {
        "a": body_with("unknown — claim requires source verification"),
        "b": body_with("The claim is clear and complete @2."),
    }.items():
        meta = {"id": name, "profile": "news_promo", "status": "untested", "domain": "d", "lang": "en"}
        (cards / f"{name}.md").write_text(f"---\n{yaml.safe_dump(meta)}---\n{body}")
        (articles / f"{name}.md").write_text("# Title\n\nFirst sentence of the article. Another one.\n")
    build_index(tmp_path)
    rows = [r.split("|") for r in (tmp_path / "INDEX.md").read_text().splitlines() if r.startswith("| a ") or r.startswith("| b ")]
    a, b = [[c.strip() for c in r] for r in rows]
    assert (a[2], a[5], a[6]) == ("other", "First sentence of the article.", "fallback")
    assert (b[2], b[5], b[6]) == ("news_promo", "The claim is clear and complete.", "card")
    assert all(c[5] and not c[5].startswith("unknown") for c in (a, b))


def test_fallback_card_gets_profile_other_in_front_matter(tmp_path):
    c = common(["NASDAQ tested 55.2% since 2020."], screen=["55.2%"])
    c["transcript"]["language"] = "en"
    v = english_answer()
    v["card"]["claim"] = "unknown — claim requires source verification"
    export_read("clip-2", v, c, tmp_path)
    front = yaml.safe_load((tmp_path / "cards/clip-2.md").read_text().split("---", 2)[1])
    assert front["thesis_source"] in ("claim_rejected", "fallback") and front["thesis"]
    assert not front["thesis"].startswith("unknown")


# --- output folder ---------------------------------------------------------------------


def test_default_output_is_parent_output_folder_name(tmp_path):
    folder = tmp_path / "videos" / "clips"
    assert default_output(folder) == (tmp_path / "videos" / "OUTPUT" / "clips").resolve()


def test_cli_read_uses_default_output_and_bridge_dir_overrides(tmp_path, monkeypatch, capsys):
    from vjournalist import cli, read_batch

    folder = tmp_path / "videos" / "clips"
    folder.mkdir(parents=True)
    seen = []

    def fake_read_folder(folder, config, **_):
        seen.append(config.bridge)
        return {"summary": {"files": 0, "analyzed": 0, "cache": 0, "duplicates": 0, "errors": 0, "pending": 0,
                            "cost_usd": 0, "historical_cost_usd_cache": 0}, "rows": [], "paused_s": 0, "folder": str(folder)}  # fmt: skip

    monkeypatch.setattr(read_batch, "read_folder", fake_read_folder)
    monkeypatch.delenv("BRIDGE_DIR", raising=False)
    for argv in (["read", str(folder)], ["read", str(folder), "--bridge-dir", str(tmp_path / "custom")]):
        monkeypatch.setattr("sys.argv", ["vjournalist", *argv])
        cli.main()
        monkeypatch.delenv("BRIDGE_DIR", raising=False)
    assert seen == [(tmp_path / "videos" / "OUTPUT" / "clips").resolve(), (tmp_path / "custom").resolve()]
    assert "OUTPUT" in capsys.readouterr().out


# --- fixes found on English samples ----------------------------------------------


def test_compact_ocr_is_lossless_and_shorter():
    from vjournalist.bridge.transcript import compact_ocr

    records = [
        {"id": i, "timestamp_s": 7.3 + i, "text": t, "text_confidence": c}
        for i, (t, c) in enumerate(
            [("npx skills add hairline", "exact"), ("Y142forks", "approximate"), ("unknown", "unreadable"), ("55.2%", "exact")]
        )
    ]
    text = compact_ocr(records)
    assert text.splitlines() == ["[7.3s] npx skills add hairline", "[8.3s] ≈ Y142forks", "[10.3s] 55.2%", "(+1 unreadable rows)"]
    assert len(text) < len(json.dumps(records)) / 2


def test_llm_request_sends_ocr_as_lines_for_read_v6(tmp_path, monkeypatch):
    from vjournalist import llm

    sent = []
    monkeypatch.setattr(llm, "_run_content", lambda message, *rest, **kw: sent.append(message) or {})
    payload = payload_for("en")
    payload["ocr"] = [{"id": 1, "timestamp_s": 4.0, "text": "55.2%", "text_confidence": "exact"}]
    payload["_receipt_dir"] = str(tmp_path)
    llm._invoke(payload, {"type": "object"}, None, Config.load())
    request = json.loads(sent[0]["message"]["content"][0]["text"])
    assert request["evidence"]["ocr"] == "[4s] 55.2%"
    assert payload["ocr"][0]["text"] == "55.2%"  # validators still read the structured rows


def test_table_labels_lose_invented_ordinals_and_text_rows_are_screen_source():
    ocr = ["hit areas don't move", "stagger by distance"]
    c = common(["Ten design rules behind this style."], screen=ocr)
    c["transcript"]["language"] = "en"
    rows = [
        {"timestamp_s": 10.0, "label": f"Rule 0{i} {k}", "value": t, "confidence": "exact"}
        for i, (k, t) in enumerate(zip(("hit", "order"), ocr), 1)
    ]
    v = value({"profile": "opinion", "claims": ["The rules matter @0"], "evidence_given": ["Slide @10"],
               "not_stated": [], "caution": []}, article="The slide lists the rules.", screen_data=rows)  # fmt: skip
    out, _ = finalize_read(v, c)
    assert [r["label"] for r in out["screen_data"]] == ["Rule hit", "Rule order"]
    assert {r["source"] for r in out["screen_data"]} == {"screen"}
    assert any("removed a number without coverage" in x for x in out["card"]["local_rejections"])


def test_cut_quote_must_not_leave_a_dangling_english_sentence():
    from vjournalist.bridge.coverage import intact

    assert not intact('The on-screen chart labelled is illustrative, so no results were taken.')
    assert intact('The on-screen chart is illustrative, so no results were taken.')
    sentence = 'The on-screen chart labelled "NASDAQ ILLUSTRATIVE" is illustrative.'
    text, cuts = repair_sentence(sentence, lambda t: claim_problem(t, "5M chart", "speech"), "5M chart")
    assert text is None and cuts == []


def test_hyphenated_shot_is_not_shot_metadata():
    assert clean_prose("The model works zero-shot on new series.") == "The model works zero-shot on new series."
    assert clean_prose("The first shot is a chart.") == ""
