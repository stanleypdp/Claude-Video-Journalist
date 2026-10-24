# polish-lexicon: this file holds Polish-language patterns/labels on purpose (Polish is a supported source language).
"""Read v5: deterministic card checks, conservative local repairs and Markdown exports."""

import re
from pathlib import Path

import yaml

from vjournalist.bridge import coverage as cov
from vjournalist.bridge import lang as L
from vjournalist.bridge import rejections as R
from vjournalist.bridge.numbers import digits_for_words, tokens
from vjournalist.bridge.transcript import (
    fmt,
    mmss,
    number_check,
    timed_sources,
    version_conflicts,
    write_archives,
)

FIELDS = {
    "analysis": [
        "claim",
        "author_conclusion",
        "reported",
        "method_stated",
        "not_stated",
        "caution",
        "agent_notes",
    ],
    "howto": ["goal", "steps", "tools_named", "not_stated", "caution"],
    "opinion": ["claims", "evidence_given", "not_stated", "caution"],
    "news_promo": ["claim", "what_is_promised", "evidence_given", "not_stated", "caution"],
}
LIST_MARKED = ("reported", "steps", "claims", "what_is_promised")
# What counts as "the source names the instrument / gives a sample size" (checked in speech, OCR, domain, title).
ASSETS = (
    r"NASDAQ|Nasdaq|S&P|\bSPX\b|\bSPY\b|\bQQQ\b|Dow Jones|\bDAX\b|\bNQ\b|\bES\b|Times.?FM|Google|"
    r"\b(?:gold|silver|oil|crude|copper|bitcoin|btc|ethereum|eth|crypto\w*|forex|futures|stocks?|equit\w+|"
    r"indices|index|etf|bonds?|currenc\w+|EUR/?USD|XAU\w*)\b"
)
SAMPLE = (
    r"\d[\d,.\s]*\s*(?:[A-Za-z-]+\s+){0,2}(?:trades?|sessions?|samples?|data points?|touch(?:es)?|runs?|traders?|"
    r"observations?|tests?|days?|candles?|bars?|events?|cases?|instances?|signals?|simulations?|variations?|"
    r"examples?|videos?|users?|respondents?)\b|sample size|\bn\s*="
)
REQUIREMENTS = {
    "analysis": {
        "instrument/obiekt": ASSETS,
        "źródło danych": r"data (?:from|source)|dataset|dane z",
        "okres badania": r"20\d\d|since|years|lat",
        "liczebność próby": SAMPLE,
        "metoda": r"test|simulat|train|benchmark",
        "koszty": r"cost|koszt",
        "istotność statystyczna": r"p.value|confidence interval|istotno",
    },
    "howto": {
        "wersje": r"version|wersj|v\d+\.\d+",
        "warunki": r"require|wymag|provided|if |jeśli",
        "koszty": r"cost|free|price|koszt|darmow",
    },
    "opinion": {
        "dowody": r"because|study|data|research|ponieważ|badan",
        "ograniczenia": r"limitation|however|but |ogranicz|jednak",
    },
    "news_promo": {
        "cena/koszt": r"price|cost|free|\$|€|cen[aęy]|koszt|darmow",
        "dostępność/wersja": r"available|version|release|open.?source|wersj|dostęp",
        "dowody/wyniki": r"benchmark|result|accuracy|test|wynik|dokładno",
    },
}
# A template gap is added only when no statement of the model already covers it.
COUNTERPARTS = {
    "instrument/obiekt": r"instrument|obiekt|kontrakt|nasdaq|asset|ticker|market|underlying",
    "źródło danych": r"źródł|dane z|dataset|data source|source of (?:the )?data|data (?:from|comes)",
    "okres badania": r"okres|period|\blat\b|20\d\d|time ?(?:span|frame)|years",
    "liczebność próby": r"prób|liczebn|sample|transakcj|number of|how many",
    "metoda": r"metod|procedur|method|procedure",
    "koszty": r"koszt|cen[aęy]|cost|price|opłat|fees?",
    "istotność statystyczna": r"istotn|p.?value|przedział|significan|confidence|interval",
    "wersje": r"wersj|version",
    "warunki": r"warunk|wymag|condition|requirement|prerequisite|require",
    "dowody": r"dowod|dane|wynik|evidence|proof|data|result",
    "ograniczenia": r"ogranicz|limit|caveat",
    "cena/koszt": r"koszt|cen[aęy]|cost|price|opłat|darmow|free|pricing",
    "dostępność/wersja": r"dostęp|wersj|version|availab|release",
    "dowody/wyniki": r"dowod|wynik|benchmark|dokładno|accuracy|evidence|result",
}
TOOL_SUBJECT = re.compile(
    r"^(?:@\d+(?:\.\d+)?\s+)?(?:claude|skill|narzędzi\w*|model|aplikacj\w*|system|komponent|agent"
    r"|the (?:tool|app|application|model|system|agent|skill|component|workflow)|it)\b",
    re.I,
)


def readable_ocr(payload):
    """OCR texts the checks may rely on: exact and approximate rows (as in the final screen), never unreadable."""
    return [r["text"] for r in payload.get("ocr", []) if r.get("text_confidence") in ("exact", "approximate")]


def card_text(card):
    # not_stated names what the source lacks (e.g. "definicja 1R"); its numbers are not claims.
    return "\n".join(str(card.get(k, "")) for k in FIELDS[card["profile"]] if k != "not_stated")


def content_numbers(text, covered=None):
    """Keys of the card's number_check: one value per number token (the reading the source covers, else the
    primary one); @s is a source locator, not a reported measurement."""
    keys = set()
    for _, _, alts in tokens(cov.fix_ocr_digits(cov.blank_locators(text)), glued=False):
        keys.add(fmt(next((a for a in alts if covered and cov.covered_by((a,), covered)), alts[0])))
    return keys


def blank_uncovered(text, covered):
    """(text with every number the source does not cover replaced by [n/a], those numbers)."""
    bad = cov.uncovered(text, covered)
    return (cov.blank_numbers(text, bad)[0], bad) if bad else (text, [])


def tag_step(step, lang="pl"):
    if step.startswith(L.STEP_TAGS):
        return step
    return L.say(lang, "effect" if TOOL_SUBJECT.match(step) else "action") + " " + step


def normalize_steps(card, lang="pl"):
    """Steps stay in the order of execution given by the model; @s is evidence, not a sort key."""
    card["steps"] = [tag_step(t, lang) for t in card.get("steps", []) if isinstance(t, str)]
    card.pop("order_logical", None)


def gap_missing(label, pattern, haystack, existing):
    """A template gap is added only after a negative check: the source says nothing about it."""
    return not re.search(pattern, haystack, re.I) and not re.search(COUNTERPARTS.get(label, r"$^"), existing, re.I)


def normalize_read(value, payload):
    """Pre-store pass: numbers the source does not cover become [n/a] (never a whole field)."""
    card = value.get("card")
    if not isinstance(card, dict) or card.get("profile") not in FIELDS:
        return value
    profile = card["profile"]
    lang = L.language(payload["transcript"])
    source = " ".join(s["text"] for s in payload["transcript"]["segments"])
    screen = readable_ocr(payload)
    covered = cov.values(source, words=True) | cov.values(" ".join(screen), words=True)
    rejected = list(card.get("local_rejections", []))

    def cleaned(key, text):
        out, bad = blank_uncovered(text, covered)
        if bad:
            rejected.append(L.say(lang, "rej_number_field", key=key, text=text[:90], numbers=", ".join(bad)))
        return out, bad

    for key in FIELDS[profile]:
        if key == "not_stated":
            continue
        field = card.get(key)
        if isinstance(field, list):
            keep = []
            for t in field:
                if not isinstance(t, str):
                    continue
                out, bad = cleaned(key, t)
                if bad and key == "reported" and not cov.values(out):
                    continue  # nothing but numbers the source does not have
                keep.append(out)
            card[key] = keep
        elif isinstance(field, str) and not field.startswith("unknown"):
            card[key] = cleaned(key, field)[0]
    card.setdefault("not_stated", [])
    card.setdefault("caution", [])
    if rejected:
        card["local_rejections"] = rejected
    if profile == "howto":
        normalize_steps(card, lang)
    existing = " ".join(card["not_stated"])
    haystack = " ".join([digits_for_words(source), *screen, str(card.get("domain", "")), str(value.get("title", ""))])
    for label, pattern in REQUIREMENTS[profile].items():
        if gap_missing(label, pattern, haystack, existing):
            card["not_stated"].append(L.say(lang, "gap", label=L.gap_label(lang, label)))
    card["not_stated"] = list(dict.fromkeys(card["not_stated"]))
    checks, _, _ = number_check(source, screen)
    card["number_check"] = {n: checks.get(n, "screen_only") for n in sorted(content_numbers(card_text(card), covered))}
    value["article"] = sorted(value.get("article", []), key=lambda p: p["start"])
    return value


# Words of editing/camera craft are forbidden only when the video does not talk about them itself
# (a video about AI camera moves legitimately says "camera"). Polish stems map to the English source word.
PRODUCTION = re.compile(
    r"\b(?:montaż\w*|kamer\w*|kolorystyk\w*|kadrowani\w*|montage|cameras?|colou?r grading|framing|footage|b-roll)\b",
    re.I,
)
PRODUCTION_IN_SOURCE = {"montaż": "edit|montage", "kamer": "camera", "kolorystyk": "colou?r", "kadrowani": "fram"}


def production_terms(text, source):
    """Craft vocabulary used in `text` that the transcript/OCR never uses."""
    source = source.lower()
    found = set()
    for match in PRODUCTION.finditer(text):
        word = match[0].lower()
        stem = next((k for k in PRODUCTION_IN_SOURCE if word.startswith(k)), None)
        seen = re.search(PRODUCTION_IN_SOURCE[stem], source) if stem else word[:5] in source
        if not seen:
            found.add(word)
    return sorted(found)


def validate_read(value, payload):
    card = value["card"]
    source = " ".join(s["text"] for s in payload["transcript"]["segments"])
    screen = readable_ocr(payload)
    covered = cov.values(source, words=True) | cov.values(" ".join(screen), words=True)
    missing = content_numbers(card_text(card), covered) - card["number_check"].keys()
    if missing:
        raise ValueError(f"Card number_check missing: {sorted(missing)}")
    checks, sp, sc = number_check(source, screen)
    for n, status in card["number_check"].items():
        if n not in sp | sc or status != checks.get(n, "screen_only"):
            raise ValueError("Number check lacks source evidence")
    for key in LIST_MARKED:
        for line in card.get(key, []):
            markers = re.findall(r"@(\d+(?:\.\d+)?)", line)
            if not markers or any(float(t) > payload["metadata"]["duration_s"] for t in markers):
                raise ValueError(f"{key}: source timestamp missing or outside video")
    for p in value["article"]:
        if p["start"] > payload["metadata"]["duration_s"]:
            raise ValueError("Article timestamp outside video")
    screen_source = " ".join(r["text"] for r in payload.get("ocr", []))
    for p in value["article"]:
        if terms := production_terms(p["text"], source + " " + screen_source):
            raise ValueError(f"Read contains visual production description not present in the video: {terms}")
    L.check_language(value, L.language(payload["transcript"]))


HANDLE_PAREN = re.compile(r"\s*\([^()]*@\w[^()]*\)")
UNRELATED_SCREEN = re.compile(
    r"(?:plansz|ekran)[^.!?]*niezwiąz|niezwiąz[^.!?]*(?:plansz|ekran)"
    r"|(?:slide|screen)s?[^.!?]*unrelated|unrelated[^.!?]*(?:slide|screen)",
    re.I,
)
SHOT_TERMS = re.compile(
    r"\b(?:ujęci\w*|klatk\w*|cięci\w*|przejści\w*|scen[aąyęie]\b|(?<![-\w])shots?\b|b-roll|jump[- ]cuts?|cutaways?)", re.I
)
AXIS_LABEL = re.compile(r"\b(?:ośk?i?|axis|tick|legend\w*)\b", re.I)
FOREIGN_SCRIPT = re.compile(r"[\u2e80-\u9fff\uac00-\ud7af\u0400-\u04ff\ufffd]")
CONFIDENCE = {"exact": "dokładna", "approximate": "przybliżona"}


def clean_prose(text, source=""):
    """Reader text: no handles, no remarks about unrelated screens, no shot/edit metadata.

    Shot vocabulary is kept when the transcript/OCR itself uses the word (`source`).
    """
    text = HANDLE_PAREN.sub("", text)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    source = source.lower()

    def shot_metadata(sentence):
        return any(m[0].lower()[:5] not in source for m in SHOT_TERMS.finditer(sentence))

    kept = [x for x in sentences if not UNRELATED_SCREEN.search(x) and not shot_metadata(x)]
    return " ".join(kept)


def damaged(text):
    text = str(text)
    return (
        bool(FOREIGN_SCRIPT.search(text))
        or (len(re.sub(r"\W", "", text)) <= 2 and not re.search(r"\d", text))
        or any(len(w) > 28 and "/" not in w and "." not in w for w in text.split())
    )


def clean_screen_data(rows):
    """Sorted by time; no axis labels, damaged tokens, unreadable or repeated readings."""
    out, seen = [], set()
    for r in sorted(rows, key=lambda r: r["timestamp_s"]):
        label, value = str(r["label"]).strip(), str(r["value"]).strip()
        if r["confidence"] == "unreadable" or not label or not value or value.lower() == "unknown":
            continue
        if AXIS_LABEL.search(label) or damaged(label) or damaged(value):
            continue
        key = (re.sub(r"\W", "", label.casefold()), re.sub(r"\s", "", value.casefold()))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def clean_title(title):
    return re.sub(r"\s+", " ", HANDLE_PAREN.sub("", title)).strip()


def render_article(value, source="", lang="pl"):
    lines = ["# " + clean_title(value["title"]), ""]
    lines += [t + "\n" for t in (clean_prose(p["text"], source) for p in value["article"]) if t]

    def clean(t):
        return str(t).replace("|", "\\|").replace("\n", " ")

    rows = [r for r in clean_screen_data(value["screen_data"]) if r.get("pewnosc")]
    if rows:
        lines += [f"## {L.say(lang, 'table_heading')}", "", L.say(lang, "table_header"), "|---|---|---|---|---|"]
        for r in rows:
            lines.append(
                f"| {mmss(r['timestamp_s'])} | {clean(r['label'])} | {clean(r['value'])} "
                f"| {r['source']} | {r['pewnosc']} |"
            )
    return "\n".join(lines).rstrip() + "\n"


# Interpretations of the card's author: allowed only as an assumption (agent_notes) unless the author
# of the video said it next to the same numbers.
INTERPRETATION = {
    r"po (?:uwzględnieniu )?koszt\w+|netto": r"after (?:trading )?costs|net of costs|costs included|after fees|\bnet\b",
    r"przed koszt\w+|brutto": r"before (?:trading )?costs|gross",
    r"większoś\w+|większa część|większej części": r"\bmost\b|majority|bulk",
    # the same cues written in English: the source must say them near the same numbers
    r"\bafter (?:trading )?costs\b|\bnet of costs\b|\bafter fees\b": r"after (?:trading )?costs|net of costs|costs included|after fees|\bnet\b",
    r"\bbefore (?:trading )?costs\b|\bgross\b": r"before (?:trading )?costs|gross",
    r"\bmost of (?:the|it|that)\b|\bthe majority\b|\bthe bulk\b": r"\bmost\b|majority|bulk",
}
INTERPRETATION_LABEL = re.compile(
    r"\s*\((?:po|przed)\s[^)]*\)|\s+(?:" + "|".join(INTERPRETATION) + r")(?:\s+\w+)?", re.I
)
GENERALIZATION = re.compile(
    r"\b(?:mogą|może|zwykle|zazwyczaj|często|bywa|generalnie|ogólnie|may|might|often|usually|typically|generally|commonly)\b",
    re.I,
)
AUTHOR_REFERENCE = re.compile(
    r"\bautor\w*|\bwedług\b|\btwierdz\w+|\bdeklar\w+|\bauthor\b|\baccording to\b|\bclaims?\b|\bstates?\b|\bsays?\b|\bspeaker\b",
    re.I,
)


def unsupported_qualifiers(text, segments):
    """Interpretive qualifiers the video does not say in the same segment as the item's numbers."""
    numbers = cov.values(text)
    near = [s["text"] for s in segments if numbers & cov.values(s["text"])] if numbers else []
    pool = near or [s["text"] for s in segments]
    return [
        m[0]
        for polish, english in INTERPRETATION.items()
        if (m := re.search(polish, text, re.I)) and not any(re.search(english, t, re.I) for t in pool)
    ]


def find_derivation(target, pool):
    """`a - b` / `a + b` over cited, covered numbers equal to |target|; only when unique."""
    found = set()
    for i, a in enumerate(pool):
        for b in pool[i + 1 :]:
            for formula, value in ((f"{fmt(b)} - {fmt(a)}", b - a), (f"{fmt(a)} + {fmt(b)}", a + b)):
                if abs(value - abs(target)) <= 0.051:
                    found.add(formula)
    return found.pop() if len(found) == 1 else None


GENERIC_LABEL_WORDS = frozenset(
    "result results share overall onward total value median average rate percent count number data".split()
)
NUMBER_WORD = re.compile(r"^\d+$")


def label_words(label):
    return {
        w
        for w in cov.content_words(re.sub(r"[^A-Za-z0-9]+", " ", label))
        if w not in GENERIC_LABEL_WORDS and not NUMBER_WORD.match(w)
    }


def word_confirmed(core, words, compact, neighbours=()):
    """A label word is in the haystack: as a word (plural ignored), by its first four letters (beaten ~ beat),
    glued inside an OCR word (MAXDRAWDOWN: long words, or short ones next to a neighbour: max+drawdown)."""
    if {core, core.removesuffix("s")} & words:
        return True
    if len(core) >= 5 and any(w.startswith(core[:4]) for w in words if len(w) >= 4):
        return True
    return (len(core) >= 7 and core in compact) or any(core + n in compact or n + core in compact for n in neighbours)


def trim_label(label, haystack):
    """(kept label, removed words): the longest stretch of `label` the haystack confirms, when it carries at
    least half of the label's distinctive words; the rest is removed.

    Neutral words (generic, short, numbers) stay only inside the stretch. (label, []) when every word is
    confirmed or the label has no distinctive word to check; (None, words) when too little is confirmed.
    """
    if not label_words(label):
        return label, []
    words = set(re.findall(r"[a-z0-9]+", haystack.lower()))
    compact = re.sub(r"[^a-z0-9]", "", haystack.lower())
    tokens = label.split()
    cores = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in tokens]
    status = []
    for i, core in enumerate(cores):
        if not (len(core) >= 3 and not NUMBER_WORD.match(core) and core not in GENERIC_LABEL_WORDS):
            status.append("neutral")
            continue
        near = [c for c in cores[max(0, i - 1) : i] + cores[i + 1 : i + 2] if len(c) >= 3]
        status.append("confirmed" if word_confirmed(core, words, compact, near) else "removed")
    if "removed" not in status:
        return label, []
    best, run = (0, 0, 0), None  # (confirmed words, start, end) of the longest stretch
    for i, x in enumerate(status):
        if x == "removed":
            run = None
        elif x == "confirmed":
            run = (0, i, i) if run is None else run
            run = (sum(status[j] == "confirmed" for j in range(run[1], i + 1)), run[1], i)
            best = max(best, run)
    total = status.count("confirmed") + status.count("removed")
    if best[0] == 0 or 2 * best[0] < total:
        return None, [t for t, x in zip(tokens, status, strict=True) if x == "removed"]
    kept = " ".join(tokens[best[1] : best[2] + 1])
    if kept.count("(") != kept.count(")"):
        kept = re.sub(r"[()]", "", kept)
    kept = kept.strip(" ,;:-–")
    removed = [t for i, t in enumerate(tokens) if not best[1] <= i <= best[2]]
    return kept, removed


def finalize_read(value, common, lang=None):
    """Source-coverage pass on the stored answer; returns (value, report). No LLM.

    Numbers without cover in transcript/final OCR become [n/a] in the card (never a whole field) and cost
    the article its sentence; on-screen quotes the OCR does not hold are marked [not in OCR] (invented
    ones are cut with their sentence); table labels the OCR does not hold become `unlabeled`; `derived` is
    validated, needed differences derived, interpretations moved to agent_notes as assumptions and
    number_check regenerated (same time windows as the transcript archive).

    `lang` overrides the language of the labels when a result is written in another language than its
    transcript (the Polish round-4 samples of English videos).
    """
    card = value["card"]
    profile = card["profile"]
    lang = lang or L.language(common["transcript"])
    segments = common["transcript"]["segments"]
    speech = " ".join(s["text"] for s in segments)
    corpus = "\n".join(
        [card_text(card)]
        + [p["text"] for p in value["article"]]
        + [f"{r['label']} {r['value']}" for r in value["screen_data"]]
    )
    rows, counts = cov.final_screen(common, corpus)
    ocr = cov.screen_text(rows)
    covered = cov.values(speech, words=True) | cov.values(ocr, words=True)
    rejections = list(card.get("local_rejections", []))
    rejected_numbers = set()
    assumptions = []
    cited = sorted(v for v in cov.values(card_text(card)) if v in covered)

    kept_derived = []
    for item in card.pop("derived", []):
        if cov.derived_ok(item, covered):
            kept_derived.append(item)
        else:
            rejections.append(L.say(lang, "rej_derived", value=item.get("value"), formula=item.get("formula")))
            rejected_numbers |= cov.values(item.get("value", ""))
    allowed = covered | {v for item in kept_derived for v in cov.values(item["value"])}

    def derive(number, label, shown):
        formula = find_derivation(number, cited)
        item = {"label": label, "value": shown, "formula": formula}
        if formula and cov.derived_ok(item, covered):
            kept_derived.append(item)
            allowed.add(number)
            return True
        return False

    def cost_gap_note(text):
        """Facts instead of a paraphrase the author did not make: the two numbers, their gap and the author's words."""
        pair = sorted(cov.values(text), reverse=True)[:2]
        if len(pair) < 2:
            return None
        hi, lo = pair
        unit = (re.search(rf"{re.escape(fmt(hi))}\s*([A-Za-z]{{1,2}})\b", text) or [None, ""])[1]
        gap = {"label": L.say(lang, "label_gap"), "value": f"{fmt(hi - lo)}{unit}", "formula": f"{fmt(hi)} - {fmt(lo)}"}
        share = {
            "label": L.say(lang, "label_share"),
            "value": f"{round((hi - lo) / hi * 100)}%",
            "formula": f"({fmt(hi)} - {fmt(lo)}) / {fmt(hi)} * 100",
        }
        if not all(cov.derived_ok(i, covered) for i in (gap, share)):
            return None
        kept_derived.extend((gap, share))
        allowed.update(cov.values(gap["value"]) | cov.values(share["value"]))
        sentences = cov.split_sentences(speech)
        index = next((i for i, x in enumerate(sentences) if hi in cov.values(x)), None)
        after = sentences[index + 1].strip() if index is not None and index + 1 < len(sentences) else None
        at = next((x["start"] for x in segments if after and cov.normalized(after)[:8] in cov.normalized(x["text"])), None)
        words = L.say(lang, "author_said", text=after) + (f" @{round(at)}." if at is not None else "") if after else ""
        return (
            L.say(lang, "gap_note", hi=fmt(hi), lo=fmt(lo), unit=unit, gap=gap["value"], share=share["value"]) + words
        )

    def unresolved(text):
        """Numbers neither covered by the source nor derivable from covered ones."""
        bad = cov.uncovered(text, allowed)
        for b in list(bad):
            if derive(float(b), re.sub(r"\s*@\d+(?:\.\d+)?", "", text)[:60], b):
                bad.remove(b)
        return bad

    def problem(text, numbers=True):
        bad = unresolved(text) if numbers else []
        if bad:
            rejected_numbers.update(float(b) for b in bad)
            return L.say(lang, "rej_number", numbers=", ".join(bad))
        return L.localize_reason(lang, cov.claim_problem(text, ocr, speech))

    def tidy(text):
        return re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()

    def repair(text, key, numbers=True, terminal=True, blank=False):
        """(text, None) or (None, reason). `blank`: card fields keep their text, numbers go to [n/a]."""
        original, min_words = text, (3 if terminal else 0)
        if blank and numbers and (bad := unresolved(text)):
            rejected_numbers.update(float(b) for b in bad)
            text, replaced = cov.blank_numbers(text, bad)
            rejections.append(
                L.say(lang, "rej_number_field", key=key, text=original[:90], numbers=", ".join(replaced))
            )
            if key == "reported" and not cov.values(text):
                return None, L.say(lang, "rej_number", numbers=", ".join(replaced))
        text, reattributed, invented = cov.mark_unverified_quotes(text, ocr, speech, lang)
        if invented:
            cut, removed = cov.prune_quoted(text, ocr, drop=set(invented))
            cut = tidy(cut)
            if why := cov.stub_problem(cut, min_words) or (None if cov.intact(cut, terminal) else "not whole"):
                return None, L.say(lang, "reason_stub", why=why)
            rejections.append(
                L.say(lang, "rej_cut", key=key, cuts=", ".join(f"„{x}”" for x in removed), text=original[:70])
            )
            text = cut
        fixed, cuts = cov.repair_sentence(text, lambda t: problem(t, numbers), ocr, speech, terminal)
        if fixed is None:
            return None, problem(text, numbers)
        if cuts:
            rejections.append(L.say(lang, "rej_cut", key=key, cuts=", ".join(cuts), text=original[:70]))
        if why := cov.stub_problem(fixed, min_words if cuts or invented else 0):
            return None, L.say(lang, "reason_stub", why=why)
        rejections.extend(L.say(lang, "rej_reattributed", key=key, quote=q) for q in reattributed)
        return fixed, None

    for key in FIELDS[profile]:
        field = card.get(key)
        if isinstance(field, list):
            keep = []
            for item in field:
                if not isinstance(item, str):
                    continue
                text, reason = repair(item, key, key != "not_stated", terminal=False, blank=key != "not_stated")
                if reason:
                    rejections.append(L.say(lang, "rej_sentence", key=key, text=item, reason=reason))
                elif key not in ("agent_notes", "not_stated") and (q := unsupported_qualifiers(text, segments)):
                    note = cost_gap_note(text) if q[0].lower().startswith("większ") else None
                    assumptions.append(note or L.say(lang, "assumption", text=text))
                elif key == "caution" and GENERALIZATION.search(text) and not AUTHOR_REFERENCE.search(text) and not cov.values(text) and "@" not in text:
                    rejections.append(L.say(lang, "rej_general", key=key, text=item))
                else:
                    keep.append(text)
            card[key] = keep or ([] if key in ("agent_notes", "method_stated") else [L.say(lang, "none_given")])
        elif isinstance(field, str) and not field.startswith("unknown"):
            sentences, dropped = [], False
            for sentence in cov.split_sentences(field):
                text, reason = repair(sentence, key, blank=True)
                if reason:
                    dropped = True
                    rejections.append(L.say(lang, "rej_sentence", key=key, text=sentence, reason=reason))
                else:
                    sentences.append(text)
            if dropped or sentences != cov.split_sentences(field):
                card[key] = " ".join(sentences) or L.say(lang, "unknown")

    paragraphs = []
    source_words = speech + "\n" + ocr
    for p in value["article"]:
        keep = []
        for sentence in cov.split_sentences(clean_prose(p["text"], source_words)):
            text, reason = repair(sentence, L.say(lang, "key_article"))
            if reason:
                rejections.append(L.say(lang, "rej_sentence", key=L.say(lang, "key_article"), text=sentence, reason=reason))
            else:
                keep.append(text)
        if keep:
            paragraphs.append({**p, "text": " ".join(keep)})
    value["article"] = paragraphs or value["article"][:1]

    table = []
    ocr_values = cov.values(ocr, words=True)
    speech_values = cov.values(speech, words=True)
    for r in value["screen_data"]:
        numbers = cov.values(r["value"])
        label = r["label"]
        if invented := cov.uncovered(label, allowed):
            # an ordinal the model added to the label ("Rule 01") that neither speech nor OCR contains
            stripped = re.sub(rf"\b0*(?:{'|'.join(map(re.escape, invented))})\b", "", label)
            label = re.sub(r"\s{2,}", " ", stripped).strip(" :-")
            rejections.append(L.say(lang, "rej_table_label_number", label=r["label"], numbers=", ".join(invented)))
        if numbers and cov.uncovered(r["value"], allowed):
            primary = cov.values(r["value"], primary=True)
            if len(primary) == 1 and derive(next(iter(primary)), label, r["value"]):
                table.append({**r, "source": L.say(lang, "src_computed"), "pewnosc": L.say(lang, "conf_computed")})
                continue
            rejected_numbers.update(primary)
            rejections.append(L.say(lang, "rej_table_number", label=r["label"], value=r["value"]))
            continue
        if not numbers and not cov.present(r["value"], cov.source_norm(ocr)):
            rejections.append(L.say(lang, "rej_table_value", label=r["label"], value=r["value"]))
            continue
        on_screen = not numbers or cov.covers(r["value"], ocr_values)  # a value without numbers was required in the OCR above
        on_speech = bool(numbers) and cov.covers(r["value"], speech_values)
        if not (on_screen or on_speech or not numbers):
            continue
        if unsupported_qualifiers(f"{label} {r['value']}", segments):
            stripped = INTERPRETATION_LABEL.sub("", label).strip()
            known = " ".join([*card.get("agent_notes", []), *assumptions])
            if not numbers & cov.values(known):
                assumptions.append(
                    L.say(
                        lang,
                        "assumption_result",
                        value=r["value"],
                        label=label.strip().lower().removeprefix("wynik ").removeprefix("result "),
                    )
                )
            label = stripped or label
        if numbers and on_screen:
            # the label has to stand next to the number on the slide or be what is said next to it (±3 s):
            # the confirmed part stays, only the unconfirmed words go
            hits = [row for row in rows if numbers & cov.values(row["text"])]
            spans = [(h["first"], h["last"]) for h in hits] + [
                (x["start"], x["end"]) for x in segments if numbers & cov.values(x["text"], words=True)
            ]
            spans = spans or [(r.get("timestamp_s", 0),) * 2]
            near = lambda a, b: any(a <= end + 3 and b >= start - 3 for start, end in spans)  # noqa: E731
            haystack = " ".join(
                [row["text"] for row in rows if near(row["first"], row["last"])]
                + [x["text"] for x in segments if near(x["start"], x["end"])]
            )
            trimmed, removed = trim_label(label, haystack)
            if trimmed is None:
                rejections.append(L.say(lang, "rej_table_unlabeled", label=label, value=r["value"]))
                label = L.say(lang, "unlabeled")
            elif removed:
                rejections.append(
                    L.say(lang, "rej_table_trimmed", label=label, removed=" ".join(removed), value=r["value"])
                )
                label = trimmed
        source = (
            L.say(lang, "src_screen_speech")
            if on_screen and on_speech
            else L.say(lang, "src_screen")
            if on_screen
            else L.say(lang, "src_speech")
        )
        approximate = r["confidence"] == "approximate" or any(
            row["uncertain"] or cov.fix_ocr_digits(row["text"]) != row["text"]
            for row in rows
            if cov.values(row["text"]) & numbers
        )
        pewnosc = (
            (L.say(lang, "conf_approx") if approximate else L.say(lang, "conf_exact"))
            if on_screen or not numbers
            else L.say(lang, "conf_speech")
        )
        table.append({**r, "label": label, "source": source, "pewnosc": pewnosc})
    value["screen_data"] = table

    names_source = cov.source_norm(speech) + cov.source_norm(ocr)

    def checked(text, key):
        out, names = cov.verify_names(text, names_source)
        rejections.extend(
            L.say(lang, "rej_name", key=key, name=n, action=L.say(lang, "name_marked" if cov.NAME_MARK in out else "name_generic"))
            for n in names
        )
        return out

    thesis_key = THESIS_FIELD[profile]
    thesis_field = card.get(thesis_key)
    if isinstance(thesis_field, list):
        card[thesis_key] = [checked(t, thesis_key) if isinstance(t, str) else t for t in thesis_field]
    elif isinstance(thesis_field, str) and not thesis_field.startswith("unknown"):
        card[thesis_key] = checked(thesis_field, thesis_key)
    value["title"] = checked(value["title"], "title")

    if "method_stated" in FIELDS[profile]:
        method = []
        for line in card.get("method_stated", []):
            at = next((x["start"] for x in segments if cov.normalized(line)[:25] in cov.normalized(x["text"])), None)
            method.append(line if "@" in line or at is None else f"{line} @{round(at)}")
        card["method_stated"] = method or [L.say(lang, "method_none")]
    if kept_derived:
        card["derived"] = kept_derived
    if assumptions:
        if "agent_notes" in FIELDS[profile]:
            card["agent_notes"] = list(dict.fromkeys([*card.get("agent_notes", []), *assumptions]))
        else:
            rejections += [L.say(lang, "rej_moved", text=a) for a in assumptions]

    ocr_fixed = [cov.fix_ocr_digits(row["text"]) for row in rows]
    speech_at, screen_at = timed_sources(segments, rows)
    checks, speech_numbers, _ = number_check(speech, ocr_fixed, speech_at, screen_at)
    mentioned = card_text(card).lower()
    for name, spoken, shown in version_conflicts(speech, ocr_fixed, speech_at, screen_at):
        note = L.say(lang, "version_conflict", name=name.capitalize(), spoken=spoken, shown=shown)
        if name in mentioned and "caution" in FIELDS[profile] and note not in card.get("caution", []):
            card["caution"] = [*card.get("caution", []), note]
    computed = {fmt(v) for item in kept_derived for v in cov.values(item["value"])} - {fmt(v) for v in covered}
    card["number_check"] = {
        n: checks.get(n, "screen_only") for n in sorted(content_numbers(card_text(card), covered) - computed)
    }
    for line in rejections:
        for group in re.findall(r"(?:number|liczba) (\S+(?:, \S+)*) (?:replaced by|zastąpiona)", line):
            rejected_numbers |= {float(x) for x in re.findall(r"\d+(?:\.\d+)?", group)}
    if rejections:
        card["local_rejections"] = rejections
    report = {
        "rejected_numbers": sorted(fmt(n) for n in rejected_numbers),
        "rejections": rejections,
        "ocr_rows": len(rows),
        "ocr_filter": counts,
    }
    value["_finalize"] = report
    return value, report


THESIS_FIELD = {"analysis": "claim", "howto": "goal", "opinion": "claims", "news_promo": "claim"}
SENTENCE_SPLIT = r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ„\"“])"
STATUSES = {"untested", "in_test", "confirmed", "rejected"}


def first_sentence(text):
    text = re.sub(r"\s*@\d+(?:[.,]\d+)?\s*", " ", text)
    text = re.sub(r"\s*\(\s*[,;\s]*\)", "", text).strip(" -—")
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return re.split(SENTENCE_SPLIT, text.strip())[0].strip()


def usable(sentence):
    return len(re.findall(r"[^\W\d_]{2,}", sentence)) >= 3 and not sentence.lower().startswith("unknown")


def card_thesis(profile, body, article, rejections=None):
    """(thesis, source) for the INDEX; never empty and never `unknown`.

    source: `card` (the card's own claim/goal), `claim_rejected` (the model's claim that the source check
    removed, when the removal was not about a number), `fallback` (first sentence of the article).
    """
    field = THESIS_FIELD.get(profile)
    section = re.search(rf"^## {field}\n+(.*?)(?=^## |\Z)", body, re.M | re.S) if field else None
    for line in (section[1].splitlines() if section else []):
        if usable(sentence := first_sentence(line.strip().removeprefix("- "))):
            return sentence, "card"
    rejected = re.search(r"^## local_rejections\n+(.*?)(?=^## |\Z)", body, re.M | re.S)
    lines = rejections if rejections is not None else (rejected[1].splitlines() if rejected else [])
    for line in (lines if field else []):
        key, _, rest = line.strip().removeprefix("- ").partition(": ")
        text, _, reason = rest.rpartition(" — ")
        numeric = re.search(r"liczba bez pokrycia|number without coverage|\[n/a\]", reason)
        if key == field and not numeric and usable(sentence := first_sentence(text)):
            return sentence, "claim_rejected"
    paragraphs = [x.strip() for x in article.split("\n\n")[1:] if x.strip() and not x.startswith("#")]
    return first_sentence(paragraphs[0]) if paragraphs else "unknown", "fallback"


def export_read(id_, value, common, root, lang=None):
    root = Path(root)
    (root / "cards").mkdir(parents=True, exist_ok=True)
    (root / "articles").mkdir(parents=True, exist_ok=True)
    value, report = finalize_read(value, common, lang)
    card = value["card"]
    lang = lang or L.language(common["transcript"])
    corpus = "\n".join(
        [card_text(card)]
        + [p["text"] for p in value["article"]]
        + [f"{r['label']} {r['value']}" for r in value["screen_data"]]
    )
    lines = ["# " + clean_title(value["title"]), ""]
    for field in FIELDS[card["profile"]]:
        v = card.get(field, [])
        if field == "agent_notes" and isinstance(v, list):
            v = [x.replace("screen_data", L.say(lang, "data_table")) for x in v]
        if field == "agent_notes" and not v:
            continue
        lines += ["## " + field, ""]
        lines += [f"- {x}" for x in v] if isinstance(v, list) else [v]
        lines.append("")
    if card.get("derived"):
        lines += ["## derived", ""] + [
            f"- {d['label'] + ': ' if d.get('label') else ''}{d['value']} = {d['formula']}" for d in card["derived"]
        ] + [""]
    full = list(card.get("local_rejections", []))
    # whole seconds everywhere in the card, like the model's own @s
    body = re.sub(r"@(\d+)\.(\d+)", lambda m: f"@{round(float(m[0][1:]))}", "\n".join(lines))
    speech = " ".join(x["text"] for x in common["transcript"]["segments"])
    article = render_article(
        value, speech + "\n" + "\n".join(r["text"] for r in common["scan"]["screen_text"]), lang
    )
    thesis, thesis_source = card_thesis(card["profile"], body, article, full)
    names_source = cov.source_norm(speech) + cov.source_norm("\n".join(r["text"] for r in common["scan"]["screen_text"]))
    thesis, thesis_names = cov.verify_names(thesis, names_source)
    for name in thesis_names:
        action = L.say(lang, "name_marked" if cov.NAME_MARK in thesis else "name_generic")
        full.append(L.say(lang, "rej_name", key="thesis", name=name, action=action))
    if full:  # the card keeps field and reason only; the rejected content goes to archive/<id>.rejections.md
        body = body.rstrip("\n") + "\n\n" + "\n".join(["## local_rejections", "", *(f"- {x}" for x in R.brief_list(full, lang)), ""])
    meta = {
        "id": id_,
        "type": "thesis_card",
        "card_version": 4,
        "schema_version": 6,
        "lang": lang,
        "profile": "other" if thesis_source == "fallback" else card["profile"],
        **({"profile_model": card["profile"]} if thesis_source == "fallback" else {}),
        "domain": card["domain"],
        "thesis": thesis,
        "thesis_source": thesis_source,
        "status": "untested",
        "source_reliability": "unverified_claim",
        "archive_tx": f"archive/{id_}.tx.md",
        "number_check_legend": L.say(lang, "number_check_legend"),
        "number_check": card["number_check"],
    }
    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    (root / "cards" / f"{id_}.md").write_text(f"---\n{front}\n---\n{body}", encoding="utf-8")
    write_rejections(root, id_, full, lang)
    (root / "articles" / f"{id_}.md").write_text(article, encoding="utf-8")
    write_archives(id_, common, root, corpus, lang)
    build_index(root)
    return report


def write_rejections(root, id_, lines, lang):
    """archive/<id>.rejections.md: the full rejection lines (they quote what was removed); removed when none."""
    path = Path(root) / "archive" / f"{id_}.rejections.md"
    if not lines:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    text = [f"# Rejections: {id_}", "", L.say(lang, "rejections_note"), ""] + [f"- {x}" for x in lines]
    path.write_text("\n".join(text) + "\n", encoding="utf-8")


def archive_lang(root, id_):
    path = Path(root) / "archive" / f"{id_}.tx.md"
    if path.exists() and (found := re.search(r"^lang: (\S+)", path.read_text(encoding="utf-8"), re.M)):
        return found[1]
    return "unknown"


def build_index(root):
    """INDEX.md from the card files alone (no LLM); old cards without `lang`/`thesis` get them derived here."""
    root = Path(root)
    lines = [
        "# Read: card index",
        "",
        "| id | profile | lang | status | thesis | thesis_source | domain | file |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for path in sorted((root / "cards").glob("*.md")):
        _, front, body = path.read_text(encoding="utf-8").split("---", 2)
        m = yaml.safe_load(front)
        if m["status"] not in STATUSES:
            raise ValueError("Invalid card status")
        if m.get("thesis"):
            thesis, source, profile = m["thesis"], m.get("thesis_source", "card"), m["profile"]
        else:
            article_path = root / "articles" / path.name
            article = article_path.read_text(encoding="utf-8") if article_path.exists() else ""
            thesis, source = card_thesis(m["profile"], body, article)
            profile = "other" if source == "fallback" else m["profile"]
        lang = m.get("lang") or archive_lang(root, m["id"])
        lines.append(
            f"| {m['id']} | {profile} | {lang} | {m['status']} | {thesis.replace('|', '/')} | {source} "
            f"| {str(m['domain']).replace('|', '/')} | [card](cards/{path.name}) |"
        )
    (root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
