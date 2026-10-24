"""Screen validator, one number_check, howto order and interpretations. Includes Polish-source fixtures."""
# polish-fixtures: Polish-language source support is tested here, so Polish sentences are expected.

import yaml

from vjournalist.bridge.cards import (
    export_read,
    finalize_read,
    find_derivation,
    normalize_steps,
    unsupported_qualifiers,
)
from vjournalist.bridge.coverage import (
    check_bridge,
    claim_problem,
    cognate_hits,
    intact,
    repair_sentence,
    screen_claim_problem,
    split_sentences,
)

OCR = "npx skills add acme/linekit\nTypeScript\nInstitutional Trading\nInsider Trading\nTrading Volume\nStatistical Arbitrage"


def common(speech, screen=(), duration=60.0):
    segments = [{"start": i * 5.0, "end": i * 5.0 + 4, "text": t} for i, t in enumerate(speech)]
    records = [
        {
            "id": f"o{i}",
            "timestamp_s": 10.0 + i,
            "last_seen_s": 11.0 + i,
            "text": text,
            "text_confidence": "exact",
            "uncertain_content": False,
        }
        for i, text in enumerate(screen)
    ]
    return {
        "transcript": {"language": "en", "segments": segments},
        "scan": {"screen_text": records, "frames": []},
        "metadata": {"duration_s": duration},
        "platform_info": {"content_duration_s": duration},
    }


def value(card, article="Autor mówi o teście.", screen_data=()):
    return {
        "title": "Test",
        "card": {"domain": "test", **card},
        "article": [{"start": 0, "text": article}],
        "screen_data": list(screen_data),
    }


# --- 1. screen validator -------------------------------------------------------------------------


def test_tools_named_and_caution_are_scanned():
    ocr = "npx skills add acme/linekit"
    assert "npm" in claim_problem("npm @acme/linekit (widoczny na ekranie)", ocr)
    assert "ILLUSTRATIVE" in claim_problem("Wykresy z oznaczeniem ILLUSTRATIVE nie są wynikami.", ocr, "speech")
    assert claim_problem("Wykresy z oznaczeniem ILLUSTRATIVE nie są wynikami.", ocr + " ILLUSTRATIVE") is None


def test_close_but_different_token_is_not_present():
    assert "REQUIRED" in screen_claim_problem('Na ekranie widać napis "REQUIRED".', "requires\nrequirements.txt")
    assert screen_claim_problem('Na ekranie widać napis "REQUIRES".', "requires\nrequirements.txt") is None


def test_short_caps_name_in_parentheses_is_checked():
    sentence = "Na ekranie widać repozytorium acme/linekit (TypeScript, licencja MIT), opisane jako zestaw figur."
    ocr = "npx skills add acme/linekit\nTypeScript"
    text, cuts = repair_sentence(sentence, lambda t: claim_problem(t, ocr), ocr)
    assert cuts == ["(TypeScript, licencja MIT)"]
    assert text == "Na ekranie widać repozytorium acme/linekit, opisane jako zestaw figur."


def test_abbreviations_do_not_split_and_no_orphans():
    text = "Na ekranie widać listy prac, m.in. o handlu insiderów i wolumenie. Kolejne zdanie."
    assert split_sentences(text) == ["Na ekranie widać listy prac, m.in. o handlu insiderów i wolumenie.", "Kolejne zdanie."]
    assert not intact("o handlu insiderów, handlu instytucjonalnym i wolumenie.")
    assert not intact("Przykład (rate limiter) i")
    assert intact("Pełne zdanie z podmiotem.")
    assert intact("[akcja] @4 Wpisz komendę bez kropki", terminal=False)


def test_removed_fragment_never_leaves_dangling_separator():
    ocr = "a sales funnel"

    def repair(sentence):
        return repair_sentence(sentence, lambda t: screen_claim_problem(t, ocr), ocr)

    ok = ("Na ekranie widać „a sales funnel”.", ["„zero-shot”"])
    assert repair("Na ekranie widać „zero-shot” oraz „a sales funnel”.") == ok
    assert repair("Na ekranie widać „a sales funnel” oraz „zero-shot”.") == ok
    assert repair("Na ekranie widać „zero-shot”, „a sales funnel”.") == ok
    assert repair("Na ekranie widać „zero-shot”.") == (None, [])  # nothing verifiable is left


def test_meta_sentences_are_not_screen_claims_but_vague_claims_are():
    assert screen_claim_problem("Liczby w karcie pochodzą z mowy i wyraźnych napisów.", OCR) is None
    assert screen_claim_problem("Te same liczby pojawiają się na planszach.", OCR) is None
    assert "without a token" in screen_claim_problem("Na ekranie widać coś ładnego.", OCR)


def test_sentence_covered_by_ocr_stays():
    sentence = (
        "Na ekranie widać listy prac, m.in. o handlu insiderów, handlu instytucjonalnym i wolumenie, "
        "arbitrażu statystycznym oraz dispersion trading."
    )
    assert len(cognate_hits(sentence, OCR)) >= 2
    assert screen_claim_problem(sentence, OCR) is None


# --- 2. one number_check -------------------------------------------------------------------------


def test_card_and_archive_share_number_status(tmp_path):
    speech = ["POC was touched in 55.2% of sessions.", "I compared 1000 random simulations.", "The edge was 2.6 points."]
    screen = ["55.2%", "≈ 1,00O SIMULATIONS"]
    card = {
        "profile": "analysis",
        "claim": "POC dotknięty w 55,2% sesji @10",
        "author_conclusion": "Edge 2,6 pkt @10",
        "reported": ["Wynik 1000 symulacji @5", "Przewaga 2,6 pkt @10"],
        "method_stated": [],
        "not_stated": [],
        "caution": [],
        "agent_notes": [],
    }
    c = common(speech, screen)
    export_read("x", value(card), c, tmp_path)
    card_meta = yaml.safe_load((tmp_path / "cards/x.md").read_text().split("---")[1])
    archive_meta = yaml.safe_load((tmp_path / "archive/x.tx.md").read_text().split("---")[1])
    shared = set(card_meta["number_check"]) & set(archive_meta["number_check"])
    assert {"55.2", "1000", "2.6"} <= shared
    assert all(card_meta["number_check"][n] == archive_meta["number_check"][n] for n in shared)
    assert card_meta["number_check"]["1000"] == "ok"
    assert card_meta["number_check"]["2.6"] == "speech_only"
    assert check_bridge(tmp_path, ["x"]) == []


def test_difference_of_cited_numbers_goes_to_derived(tmp_path):
    c = common(["The level came back in 45% of sessions versus 40.6% for random."], ["45%", "40.6%"])
    card = {
        "profile": "analysis",
        "claim": "45% vs 40,6% @0",
        "author_conclusion": "x",
        "reported": ["Otwarcie powyżej POC: 45% vs 40,6% @0"],
        "method_stated": [],
        "not_stated": [],
        "caution": [],
        "agent_notes": [],
    }
    screen_data = [{"timestamp_s": 0, "label": "Różnica", "value": "+4.4 pkt", "confidence": "exact"}]
    v, report = finalize_read(value(card, screen_data=screen_data), c)
    assert v["card"]["derived"][0]["formula"] == "45 - 40.6"
    assert v["screen_data"][0]["source"] == "computed"
    assert report["rejected_numbers"] == []
    assert find_derivation(3.0, [40.6, 45.0, 55.2]) is None  # no pair gives 3.0


# --- 3. howto and interpretations ----------------------------------------------------------------


def test_howto_steps_keep_execution_order_without_order_logical():
    card = {
        "profile": "howto",
        "steps": ["@10 Dodaj skill", "@4 Wpisz komendę", "@20 Claude zbuduje komponent"],
        "order_logical": [2, 1, 3],
    }
    normalize_steps(card)
    assert [s.split()[1] for s in card["steps"]] == ["@10", "@4", "@20"]
    assert "order_logical" not in card


def test_interpretation_moves_to_agent_notes_as_assumption(tmp_path):
    speech = ["Plus 97R.", "Before costs, it made 136R.", "Costs took the rest."]
    card = {
        "profile": "analysis",
        "claim": "x",
        "author_conclusion": "x",
        "reported": ["Wynik +97R @0", "Przed kosztami 136R @5"],
        "method_stated": [],
        "not_stated": [],
        "caution": ["Koszty zabrały większość wyniku (136R vs +97R) @5", "Autor niczego nie dowodzi."],
        "agent_notes": [],
    }
    table = [{"timestamp_s": 0, "label": "Wynik strategii (po kosztach)", "value": "+97R", "confidence": "exact"}]
    v, _ = finalize_read(value(card, screen_data=table), common(speech, ["Wynik strategii +97R", "136R"]))
    assert v["card"]["caution"] == ["Autor niczego nie dowodzi."]
    notes = v["card"]["agent_notes"]
    assert len(notes) == 1 and "39R = 29%" in notes[0] and "większość" not in notes[0]
    assert v["screen_data"][0]["label"] == "Wynik strategii"


def test_said_qualifier_stays():
    segments = [{"text": "But after trading costs, most of that edge disappeared."}]
    assert unsupported_qualifiers("Po kosztach transakcyjnych większość przewagi zniknęła", segments) == []
    assert unsupported_qualifiers("Wynik po kosztach", [{"text": "Plus 97R."}]) == ["po kosztach"]


def test_caution_with_outside_knowledge_is_rejected():
    speech = ["Steal strategies from the social science research network."]
    card = {
        "profile": "opinion",
        "claims": ["Autor radzi kopiować pomysły @0"],
        "evidence_given": [],
        "not_stated": [],
        "caution": [
            "Opublikowane badania mogą nie przekładać się na zyski po upublicznieniu.",
            "Twierdzenie jest opinią autora, bez dowodów.",
        ],
    }
    v, _ = finalize_read(value(card), common(speech))
    assert v["card"]["caution"] == ["Twierdzenie jest opinią autora, bez dowodów."]
    assert any("knowledge from outside the material" in r for r in v["card"]["local_rejections"])



# --- review 4: method_stated and package -----------------------------------------------------------


def test_method_stated_has_content_locator_or_nie_podano():
    speech = ["I compared two random levels.", "Then I traded it."]
    card = {
        "profile": "analysis",
        "claim": "x",
        "author_conclusion": "x",
        "reported": [],
        "method_stated": ["I compared two random levels."],
        "not_stated": [],
        "caution": [],
        "agent_notes": [],
    }
    v, _ = finalize_read(value(card), common(speech))
    assert v["card"]["method_stated"] == ["I compared two random levels. @0"]
    card["method_stated"] = []
    v, _ = finalize_read(value(card), common(speech))
    assert v["card"]["method_stated"] == ["not stated"]


def test_label_with_unsaid_interpretation_is_stripped():
    card = {
        "profile": "analysis",
        "claim": "x",
        "author_conclusion": "x",
        "reported": [],
        "method_stated": [],
        "not_stated": [],
        "caution": [],
        "agent_notes": [],
    }
    table = [{"timestamp_s": 0, "label": "Wynik przed kosztami", "value": "+10.2R", "confidence": "exact"}]
    v, _ = finalize_read(value(card, screen_data=table), common(["The result? Plus 10.2R."], ["Wynik +10.2R"]))
    assert v["screen_data"][0]["label"] == "Wynik"


def test_package_has_no_placeholders_and_lists_ocr_tokens(tmp_path):

    from vjournalist.bridge.tokens import render_table, token_rows

    def ocr_tokens(bridge, label):
        found, info = token_rows(bridge, label)
        return render_table(found, info, label)

    root = tmp_path
    for folder in ("cards", "articles", "archive"):
        (root / folder).mkdir()
    (root / "articles/x.md").write_text("---\n---\nNa ekranie widać „Dobry token”.\n")
    (root / "archive/x.screen.md").write_text("# Screen\n\n\n\n\n[1.000–2.000s] Dobry token\n")
    (root / "archive/x.tx.md").write_text("---\nid: x\nduration_s: 10\n---\n[00:00] x\n")
    (root / "cards/x.md").write_text(
        "---\nid: x\nnumber_check: {}\n---\n## tools_named\n\n- npx skills\n\n## local_rejections\n\n- Na ekranie widać „Zły”.\n"
    )
    table = ocr_tokens(root, "x")
    assert "| Dobry token | ok |" in table and "Zły" not in table


# --- review 5 ---------------------------------------------------------------------------------------



def test_method_stated_seconds_are_whole():
    card = {
        "profile": "analysis",
        "claim": "x",
        "author_conclusion": "x",
        "reported": [],
        "method_stated": ["I compared two random levels."],
        "not_stated": [],
        "caution": [],
        "agent_notes": [],
    }
    c = common(["I compared two random levels."])
    c["transcript"]["segments"][0]["start"] = 3.72
    v, _ = finalize_read(value(card), c)
    assert v["card"]["method_stated"] == ["I compared two random levels. @4"]


def test_gap_note_quotes_author_and_gives_numbers_without_putting_words_in_his_mouth():
    speech = ["Before costs, it made 136R. Costs took the rest.", "Plus 97R."]
    card = {
        "profile": "analysis",
        "claim": "x",
        "author_conclusion": "x",
        "reported": [],
        "method_stated": [],
        "not_stated": [],
        "caution": ["Koszty zabrały większość wyniku (136R vs +97R) @5"],
        "agent_notes": [],
    }
    v, _ = finalize_read(value(card), common(speech, ["136R", "+97R"]))
    note = v["card"]["agent_notes"][0]
    assert "39R = 29%" in note and "Costs took the rest" in note and "większość" not in note
    assert {d["value"] for d in v["card"]["derived"]} == {"39R", "29%"}
    assert not any(n in v["card"]["number_check"] for n in ("39", "29"))


# --- review 6: matchers and metrics -----------------------------------------------------------------


def test_number_matcher_respects_token_boundaries():
    from vjournalist.bridge.coverage import values

    assert values("09:30") == set() and values("v1.2.3") == set()
    assert values("15MIN 27R 99.9% 1,096 trades.") == {15.0, 27.0, 99.9, 1096.0}
    c = common(["The 30 minute range."], ["09:30"])
    v, _ = finalize_read(
        value(
            {
                "profile": "analysis",
                "claim": "Zakres 30 minut @0",
                "author_conclusion": "x",
                "reported": [],
                "method_stated": [],
                "not_stated": [],
                "caution": [],
                "agent_notes": [],
            }
        ),
        c,
    )
    assert v["card"]["number_check"] == {"30": "speech_only"}  # 09:30 on screen is a time, not 30


def test_phrase_matcher_needs_two_content_words_and_skips_watermarks():
    from vjournalist.bridge.tokens import find_phrase

    rows = [(1.0, 3.0, "Add the skill to your project"), (0.0, 50.0, "skill project watermark")]
    watermarks = {rows[1]}
    assert find_phrase("add the skill", rows, watermarks)[0] == rows[0]
    assert find_phrase("project skill", rows, watermarks)[0] == rows[0]  # words of the watermark row do not count
    assert find_phrase("single", rows, watermarks) is None
    assert find_phrase("watermark", rows, watermarks)[1] is True  # a literal token may sit in a long row

