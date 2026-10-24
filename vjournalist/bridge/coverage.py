# polish-lexicon: this file holds Polish-language patterns/labels on purpose (Polish is a supported source language).
"""Number and on-screen-claim coverage for Read (deterministic, no LLM).

Every number in a card, article or data table must occur in the transcript or in the final
`.screen.md` (tolerating O/0, thousands commas, ≈). Values computed by the system are allowed only in
`derived` with a formula whose operands are covered. Every "visible on screen" statement must be anchored
in the OCR, otherwise it is removed.
"""

import ast
import operator
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from vjournalist.bridge import lang as L
from vjournalist.bridge.numbers import digits_for_words, fix_ocr_digits, nums, tokens
from vjournalist.bridge.transcript import fmt
from vjournalist.pipeline.knowledge_text import clean_screen, local_screen_text
from vjournalist.pipeline.knowledge_text import normalized as _normalized

# @12.5 and "at 12.5s" / "at 28-30s": places in the video, not measurements
LOCATOR = re.compile(r"@\d+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?s\b(?!\w)")
SCREEN_MARK_PL = re.compile(
    r"na ekranie|widoczn\w*|widać|z ekranu|na planszy|plansz\w*|napis\w*|na slajdzie", re.I
)
# What an English sentence says when it reports the screen: "on-screen", "OCR shows", "the slide reads", `reads "…"`.
SCREEN_MARK_EN = re.compile(
    r"\bon[- ]?screen\b|\bOCR\b|\b(?:the |a |on the |on a )?(?:screen|slide|terminal|chart|banner|overlay|caption|"
    r"subtitle|title card|label|tooltip|prompt|window|dashboard|announcement|table|graphic|graph) "
    r"(?:reads?|says?|shows?|displays?|is labell?ed|is titled|is captioned|appears)\b|"
    r"\b(?:reads?|labell?ed|titled|captioned|marked)\s+(?:as\s+)?[„\"“]|"
    r"\b(?:shown|displayed|written|printed)\s+(?:on|in|as|at)\b|\bappears? on (?:the )?screen\b|"
    r"\bvisible (?:on|in)\b|\bon the (?:slide|chart|screen|board|banner)\b",
    re.I,
)
SCREEN_MARK = re.compile(SCREEN_MARK_PL.pattern + "|" + SCREEN_MARK_EN.pattern, re.I)
SPEECH_CUE = re.compile(
    r"\b(?:says?|said|states?|stated|claims?|calls?|called|asks?|tells?|told|announces?|mentions?|describes?|"
    r"explains?|argues?|adds?|spoken|autor\w*\s+(?:mówi|twierdzi)|mówi|twierdzi|według)\b",
    re.I,
)
NOT_IN_OCR = "[not in OCR]"
# a quotation with its optional [not in OCR] marker (group 2): the marker belongs to the quote before it
# and an optional [spoken] tag (group 3): the quote is given as speech, whatever the cue before it says
QUOTE = re.compile(r"[„\"“]([^„”\"“]{2,80})[”\"”](\s*\[not in OCR\])?(\s*\[(?:spoken|w mowie)\])?")
# Polish appearance words need their English counterpart on screen (OCR is English-only here).
VISUAL_TERMS = {
    r"ciemn\w+": r"dark",
    r"jasn\w+ (?:motyw|tł)\w*": r"light",
    r"suwak\w*": r"slider|intensity|nsity",
    r"przełącznik\w*": r"toggle|switch|theme",
    r"kolumn\w*": r"column|bar",
    r"siatk\w*": r"grid",
}
# Commands and proper names are verifiable tokens even without quotes: ALLCAPS (>=5), CamelCase, npm-like.
CMD_WORDS = {"npm", "npx", "pnpm", "yarn", "pip", "brew", "git", "uv", "docker", "curl"}
PROPER = re.compile(r"\b(?:[A-Z]{5,}|[A-Z][a-z]+[A-Z][A-Za-z]*|[a-z]+[A-Z][A-Za-z]+)\b")
# Sentences about the card/sources themselves are not claims about the screen.
META = re.compile(
    r"\b(?:karc\w+|kart[aęy]|tabel\w+|artykuł\w*|niżej|powyżej|wylicz\w+|liczb\w+|pochodz\w+|użyt\w+|"
    r"wyników|analiz\w+|screen_data|card|data table|article|below|above|computed|derived|numbers?)\b",
    re.I,
)
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def blank_locators(text):
    """`text` with @s locators blanked to spaces (same length, so spans stay valid)."""
    return LOCATOR.sub(lambda m: " " * len(m[0]), text)


def values(text, words=False, primary=False):
    """Numeric values (floats) found in prose; locators and identifiers excluded.

    `words=True` also reads spoken numerals (`one`, `eight`): for the covering side (transcript, OCR) only.
    Each token may stand for several values (`59k` = 59000 or 59); `primary` keeps the first reading.
    """
    return set(nums(fix_ocr_digits(blank_locators(text)), words, primary))


def covered_by(alts, covered):
    return any(abs(a - c) < 1e-9 for a in alts for c in covered)


def uncovered(text, covered):
    """Numbers of `text` none of whose readings is in `covered`, as sorted strings."""
    found = {
        alts[0]
        for _, _, alts in tokens(fix_ocr_digits(blank_locators(text)), glued=False)
        if not covered_by(alts, covered)
    }
    return sorted(fmt(v) for v in found)


def covers(text, pool):
    """Every number of `text` (glued ones such as x0.0008 included) is in `pool`; False without numbers."""
    found = tokens(fix_ocr_digits(blank_locators(text)))
    return bool(found) and all(covered_by(alts, pool) for _, _, alts in found)


UNIT_AFTER = re.compile(r"(?:%|‰|[A-Za-z]{1,2}(?![A-Za-z]))")
NA = "[n/a]"


def blank_numbers(text, bad):
    """(`text` with every number whose primary reading is in `bad` replaced by [n/a], values replaced).

    The unit glued to the number goes with it (`94.9R`, `96%`); nothing else of the text changes.
    """
    clean = fix_ocr_digits(blank_locators(text))
    out, position, replaced = [], 0, set()
    for start, end, alts in tokens(clean, glued=False):
        if not any(abs(alts[0] - float(b)) < 1e-9 for b in bad):
            continue
        unit = UNIT_AFTER.match(text, end)
        stop = unit.end() if unit and text[end : end + 1] != " " else end
        out.append(text[position:start])
        out.append(NA)
        position = stop
        replaced.add(alts[0])
    out.append(text[position:])
    return "".join(out), sorted(fmt(v) for v in replaced)


def source_norm(text):
    """Text as compared against quotes and names: spoken numerals as digits, case/punctuation folded."""
    return _normalized(digits_for_words(text))


def source_norm_words(text):
    """Like source_norm but word boundaries kept (lowercase, punctuation as spaces)."""
    return re.sub(r"[\W_]+", " ", digits_for_words(text).casefold())


def normalized(text):
    return _normalized(text)


SHORT_CAPS = re.compile(r"\b[A-Z]{3,4}\b")
NOT_NAMES = {"OCR", "ASR", "LLM", "JSON", "CLI", "URL"}


def anchors(sentence, short=False):
    """Verifiable tokens: quoted strings, Latin words in parentheses, identifiers/paths/commands.

    `short` adds 3-4 letter ALLCAPS names (MIT, REST) for claims about what is visible.
    """
    found = [m[1] for m in QUOTE.finditer(sentence) if not m[2] and len(m[1]) <= 60]
    found += [
        x for x in re.findall(r"\(([A-Za-z][\w' -]{2,40})\)", sentence) if not SCREEN_MARK.search(x)
    ]
    for word in re.findall(r"\S+", LOCATOR.sub("", sentence)):
        word = word.strip(".,;:()„”\"“")
        if re.fullmatch(r"[\d.,]+", word):
            continue
        if word in CMD_WORDS:
            found.append(word)
        if (len(word) >= 4 and re.search(r"[/@_]\w|\w[/@]", word)) or (
            len(word) >= 6 and re.search(r"\w\.[A-Za-z]{2,}\b", word)
        ):
            found.append(word)
    found += PROPER.findall(sentence)
    if short:
        found += [t for t in SHORT_CAPS.findall(sentence) if t not in NOT_NAMES]
    return list(dict.fromkeys(a.strip() for a in found if a.strip()))


def proper_tokens(sentence):
    words = [w.strip(".,;:()„”\"“") for w in re.findall(r"\S+", LOCATOR.sub("", sentence))]
    return list(dict.fromkeys(PROPER.findall(sentence) + [w for w in words if w in CMD_WORDS]))


def present(token, ocr_norm):
    t = source_norm(token)
    if not t:
        return True
    if t in ocr_norm:
        return True
    if len(t) < 5:
        return False
    n = len(t)
    # short single words must match (OCR noise in a long path is tolerated; required != requires is not)
    threshold = 0.85 if n >= 12 else 0.92
    return any(
        SequenceMatcher(None, t, ocr_norm[i : i + n]).ratio() >= threshold
        for i in range(max(1, len(ocr_norm) - n + 1))
    )


def stem(word):
    return unicodedata.normalize("NFKD", word.lower()).encode("ascii", "ignore").decode()


def cognate_hits(sentence, ocr_text):
    """Polish content words of the sentence that have an English cognate in the OCR (insider/insider)."""
    body = SCREEN_MARK.sub(" ", sentence)
    words = {stem(w) for w in re.findall(r"[^\W\d_]{6,}", body)}
    ocr_words = {stem(w) for w in re.findall(r"[A-Za-z]{5,}", ocr_text)}
    hits = set()
    for w in words:
        for o in ocr_words:
            if SequenceMatcher(None, w[: len(o) + 1], o).ratio() >= 0.75:
                hits.add(o)
                break
    return hits


STOP_WORDS = frozenset(
    "the and for with this that your you our from are was were its not but can has have had into about over "
    "then than them they his her she who how what when where which while will would could should also just "
    "jest oraz który które przez dla nie się tak jak".split()
)


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in STOP_WORDS}


def in_ocr(token, ocr_text, ocr_norm=None):
    """The token is on screen: literal (spaces and case ignored, OCR noise tolerated) or >=2 content words
    shared with one OCR line."""
    if present(token, ocr_norm if ocr_norm is not None else source_norm(ocr_text)):
        return True
    words = content_words(token)
    return len(words) >= 2 and any(len(words & content_words(line)) >= 2 for line in ocr_text.splitlines())


def screen_claim_problem(sentence, ocr_text):
    """None when the sentence is no screen claim or is anchored in OCR; else the reason it fails."""
    if not SCREEN_MARK.search(sentence):
        return None
    ocr = source_norm(ocr_text)
    found = anchors(sentence, short=True)
    visual = next(
        (
            f"appearance description without a counterpart in the OCR ({english})"
            for polish, english in VISUAL_TERMS.items()
            if re.search(polish, sentence, re.I) and not re.search(english, ocr_text, re.I)
        ),
        None,
    )
    if not SCREEN_MARK_PL.search(sentence):
        # English: the quotes the sentence gives as screen text are what can be checked, not its other names
        missing = [q for _, q in screen_quotes(sentence) if not in_ocr(q, ocr_text, ocr)]
        return ("not in OCR: " + ", ".join(missing)) if missing else None
    if not found:
        if META.search(sentence):
            return None  # remark about the card/sources
        if len(cognate_hits(sentence, ocr_text)) >= 2:
            return visual  # content of the sentence is covered by the OCR
        return "claim about the screen without a token to check in the OCR"
    missing = [a for a in found if not in_ocr(a, ocr_text, ocr)]
    if missing:
        return "not in OCR: " + ", ".join(missing)
    return visual


def screen_quotes(sentence, marked=False):
    """[(match, quote)] of the quotes a sentence gives as screen text: a screen cue precedes the quote
    and no speech cue ("he says") comes after it. `marked` also returns quotes already carrying [not in OCR]."""
    out = []
    for m in QUOTE.finditer(sentence):
        if (m[2] and not marked) or m[3]:
            continue  # already marked, or given as speech
        before = sentence[max(0, m.start() - 90) : m.start()]
        cues = list(SCREEN_MARK.finditer(before))
        said = list(SPEECH_CUE.finditer(before))
        if cues and not (said and said[-1].start() > cues[-1].start()):
            out.append((m, m[1]))
    return out


SPOKEN_MATCH = 0.8  # similarity of a quote to the transcript at which it counts as said aloud


def fuzzy_in(text, haystack, threshold=SPOKEN_MATCH):
    """`text` (source_norm) occurs in `haystack` (source_norm) exactly or with a similarity >= threshold."""
    if not text:
        return False
    if text in haystack:
        return True
    n = len(text)
    if n < 4 or len(haystack) < n:
        return False
    starts = set()
    for gram in {text[i : i + 3] for i in range(n - 2)}:
        at = haystack.find(gram)
        while at != -1 and len(starts) < 4000:
            starts.update(range(max(0, at - n), at + 1))
            at = haystack.find(gram, at + 1)
    # windows of the text's own length and one longer (a word may carry an extra letter: Grok ~ Grock)
    return any(
        SequenceMatcher(None, text, haystack[i : i + size]).ratio() >= threshold
        for i in sorted(starts)
        for size in (n, n + 1)
        if i + size <= len(haystack)
    )


# How the cue before a quote is rewritten when the quote is in the speech, not on the screen. Capitalization
# of the replaced words is kept; a cue shared with a quote that IS on screen is not rewritten (tagged instead).
_NOUNS = (
    r"OCR|screen|slide|terminal|chart|banner|overlay|caption|subtitle|title card|label|tooltip|prompt|window|"
    r"dashboard|announcement|table|graphic|graph|text"
)
CUE_REWRITES = (
    (
        re.compile(
            rf"\b(?:the |a |an |on the |on a )?(?:on[- ]?screen )?(?:{_NOUNS})\s+"
            r"(?:reads?|says?|shows?|displays?|is labell?ed|is titled|is captioned|appears)\b",
            re.I,
        ),
        "the author says",
    ),
    (re.compile(r"\bon[- ]?screen (?:text|caption|label|quote|line|remark|phrase)\b", re.I), "spoken line"),
    (re.compile(r"\b(?:reads?|labell?ed|titled|captioned|marked)(?:\s+as)?(?=\s+[„\"“])", re.I), "says"),
)


def rewrite_cue(sentence, cue):
    """(start, end, replacement) that turns the screen cue at `cue` (a span) into a speech attribution, or None."""
    for pattern, replacement in CUE_REWRITES:
        for m in pattern.finditer(sentence):
            if m.start() < cue[1] and m.end() > cue[0]:
                capital = m.start() == 0 or (m[0][0].isupper() and not m[0].startswith("OCR"))
                return m.start(), m.end(), replacement[:1].upper() + replacement[1:] if capital else replacement
    return None


def mark_unverified_quotes(sentence, ocr_text, speech="", lang="en"):
    """(sentence, reattributed, invented): quotes given as screen text that no OCR line supports.

    A quote that is in the speech (similarity >= SPOKEN_MATCH) stays, with its attribution corrected:
    the screen cue before it becomes "the author says" / "spoken line"; when the cue is shared with a quote
    that is on screen (or cannot be rewritten) the quote gets a [spoken] tag instead. A quote that is neither
    on screen nor spoken is invented by the model and returned in `invented` for the caller to cut.
    """
    ocr, spoken = source_norm(ocr_text), source_norm(speech)
    quotes = screen_quotes(sentence)
    cues = {}
    for m, _ in quotes:
        start = max(0, m.start() - 90)
        last = list(SCREEN_MARK.finditer(sentence[start : m.start()]))[-1]
        cues[m.start()] = (start + last.start(), start + last.end())
    on_screen = {cues[m.start()] for m, q in quotes if in_ocr(q, ocr_text, ocr)}
    reattributed, invented, edits = [], [], {}
    for m, quote in quotes:
        if in_ocr(quote, ocr_text, ocr):
            continue
        if not fuzzy_in(source_norm(quote), spoken):
            invented.append(quote)
            continue
        reattributed.append(quote)
        cue = cues[m.start()]
        rewrite = None if lang != "en" or cue in on_screen else rewrite_cue(sentence, cue)
        if rewrite:
            edits[rewrite[:2]] = rewrite[2]
        else:
            edits[m.end(), m.end()] = " " + L.say(lang, "spoken_tag")
    for (start, end), text in sorted(edits.items(), reverse=True):
        sentence = sentence[:start] + text + sentence[end:]
    return sentence, reattributed, invented


def inflected(token, source):
    """A CamelCase name with a plural or a Polish case ending (GitHuba, AirDrops) whose bare form the source has."""
    if not re.search(r"[a-z][A-Z]", token):
        return False
    for cut in (1, 2):
        stem = source_norm(token)[:-cut]
        if len(stem) >= 5 and stem in source:
            return True
    return False


def claim_problem(sentence, ocr_text, speech=""):
    """Names and commands must exist in speech or OCR; screen statements must be anchored in the OCR."""
    source = source_norm(ocr_text) + source_norm(speech)
    missing = [t for t in proper_tokens(sentence) if not (present(t, source) or inflected(t, source))]
    if missing and not SCREEN_MARK_PL.search(sentence):
        return "not in speech or OCR: " + ", ".join(missing)
    return screen_claim_problem(sentence, ocr_text)


def drop_parentheses(text, ocr_text, speech=""):
    """(text without unverifiable parenthetical remarks, removed remarks); the rest of the sentence stays."""
    source = source_norm(ocr_text) + source_norm(speech)
    removed = []

    def verdict(match):
        inner = match.group(0).strip()[1:-1]
        found = anchors(inner, short=True) or ([inner] if re.fullmatch(r"[A-Za-z][\w' -]{2,40}", inner) else [])
        if SCREEN_MARK.search(inner) and not found:
            return match.group(0)
        if all(present(a, source) for a in found):
            return match.group(0)
        removed.append(match.group(0).strip())
        return ""

    return re.sub(r"\s*\([^()]*\)", verdict, text), removed


def drop_unanchored_parentheses(text, ocr_text, speech=""):
    return drop_parentheses(text, ocr_text, speech)[0]


def prune_quoted(sentence, ocr_text, drop=None):
    """(sentence without quoted items missing in OCR, removed items); each list keeps valid separators.

    `drop` (set of quote texts) selects the items to remove instead of the OCR test.
    """
    ocr = source_norm(ocr_text)
    pattern = re.compile(
        r"(?P<lead>,\s*|\s+(?:i|oraz|lub|and|or)\s+)?[„\"“](?P<q>[^„”\"“]{2,60})[”\"”](?:\s*\[not in OCR\])?(?:\s*\[(?:spoken|w mowie)\])?"
    )
    runs = []  # consecutive quoted items joined only by list separators
    for match in pattern.finditer(sentence):
        if runs and runs[-1][-1].end() == match.start():
            runs[-1].append(match)
        else:
            runs.append([match])
    keep_it = (lambda q: q not in drop) if drop is not None else (lambda q: present(q, ocr))
    removed, out, position = [], [], 0
    for run in runs:
        out.append(sentence[position : run[0].start()])
        position = run[-1].end()
        kept = [m for m in run if keep_it(m["q"])]
        removed += [m["q"] for m in run if m not in kept]
        for k, m in enumerate(kept):
            lead = (run[0]["lead"] if k == 0 else m["lead"]) or ""
            out.append(lead + m.group(0)[len(m["lead"] or "") :])
    out.append(sentence[position:])
    return re.sub(r"\s{2,}", " ", "".join(out)), removed


DANGLING = re.compile(
    r"\b(?:labell?ed|titled|entitled|called|marked|named|captioned|reads?|says?|saying|showing|displays?)\s+(?:is|are|was|were|as|that|and|or)\b|"
    r"\s{2,}|[:,]\s+(?:i|oraz|lub)\s|\bwidać\s+(?:i|oraz|lub)\s|\s[,;:]|[,:;]\s*[,.;:!?]|\(\s*\)|\b(?:i|oraz|lub|a|że|m\.in|np|tj|and|or|that|e\.g|i\.e)\.?\s*[.!?]$|(?:m\.in|np|tzw|tj)\.\s*[,.]"
)


STUB = re.compile(
    r"\(\s*(?:spoken|shown|written|displayed|labell?ed|read|reads|said|called|rendered|transcribed)"
    r"(?:\s+(?:as|aloud))?\s*\)|"
    r"\([^()]*\b(?:as|reads?|shown|spoken|called|titled)\s*\)|"
    r"(?<![\w\"”“])[„\"“]\s*[”\"](?!\w)|\[\s*\]|\(\s*\)|"
    r"\b(?:reads?|labell?ed|titled|entitled|captioned|spoken as|shown as|written as|displayed as|marked as|appears as)"
    r"\s*(?:[.!?;)]|$)|"
    r"\b(?:text|label|caption|slide|screen|title|overlay|banner)\s+(?:says?|shows?|displays?)\s*(?:[.!?;:,)]|$)|"
    r"(?<![\w'’])(?:the|a|an|of|with|and|or|as|by)\s*[.!?]$",
    re.I,
)


def stub_problem(text, min_words=0):
    """Why a (cut) text is a stub: empty brackets/quotes, a verb with nothing after it ('reads.'),
    unbalanced quotes or brackets, fewer than `min_words` words. None when the text is whole."""
    text = text.strip()
    if found := STUB.search(text):
        return f"stub “{found[0].strip()}”"
    if text.count('"') % 2 or text.count("(") != text.count(")") or text.count("[") != text.count("]"):
        return "unbalanced quotes or brackets"
    if len(re.findall(r"\w+", text)) < min_words:
        return f"fewer than {min_words} words"
    return None


def intact(sentence, terminal=True):
    """A cut text must still be whole: capital start, terminal stop (sentences), no dangling separators."""
    text = sentence.strip()
    return (
        len(text.split()) >= 3
        and (text[0].isupper() or text[0] in "„\"“@/([0123456789")
        and (not terminal or text[-1] in ".!?)”\"")
        and not DANGLING.search(text)
        and not stub_problem(text)
    )


def repair_sentence(sentence, problem, ocr_text, speech="", terminal=True):
    """(text|None, cuts): clean text; else minus unverifiable fragments if it is still whole; else None.

    `problem(text)` returns the reason a text fails, or None. Tried in order: drop the quoted items
    missing in OCR, drop unverifiable parentheses, both.
    """
    if not problem(sentence):
        return sentence, []

    def tidy(text):
        return re.sub(r"\s+([.,;:!?])", r"\1", text).strip()

    def quoted(text):
        # a screen statement is checked against the OCR, anything else against speech and OCR
        out, removed = prune_quoted(text, ocr_text if SCREEN_MARK.search(text) else ocr_text + "\n" + speech)
        return tidy(out), [f"„{x}”" for x in removed]

    def parens(text):
        out, removed = drop_parentheses(text, ocr_text, speech)
        return tidy(out), removed

    def both(text):
        out, first = quoted(text)
        out, second = parens(out)
        return out, first + second

    for strategy in (quoted, parens, both):
        text, cuts = strategy(sentence)
        if cuts and intact(text, terminal) and not problem(text):
            return text, cuts
    return None, []


ABBREVIATIONS = (
    "m.in.", "np.", "tzw.", "itd.", "itp.", "tj.", "tys.", "mln.", "mld.", "godz.", "ok.", "ang.",
    "e.g.", "i.e.", "vs.", "etc.", "approx.",
)  # fmt: skip
SENTENCE_START = r"(?=[A-ZĄĆĘŁŃÓŚŹŻ0-9„\"“@/(\[])"


QUOTED_SPAN = re.compile(r'"[^"\n]*"|“[^”\n]*”|„[^”“\n]*[”“]')


def split_sentences(text):
    """Split after . ! ? before a capital; abbreviations (m.in., np.), lowercase continuations and anything
    inside a quotation ("Fewer tokens. Same context.") never split."""
    guards = "".join(f"(?<!{re.escape(a)})" for a in ABBREVIATIONS)
    masked = QUOTED_SPAN.sub(lambda m: re.sub(r"([.!?])\s", "\\1\x00", m[0]), text.strip())
    parts = re.split(guards + r"(?<=[.!?])\s+" + SENTENCE_START, masked)
    return [p.replace("\x00", " ") for p in parts if p]

# --- proper names in the thesis, claim and title -----------------------------------------------------

NAME_WORD = re.compile(r"(?<![\w@/.\-])(?:[A-Z][a-z]{2,}[A-Za-z]*|[A-Z]{3,})(?![\w])")
NAME_GENERIC = re.compile(r"\s*\(([a-z][^()\d]{3,60})\)")
NAME_MARK = "[name not in source]"
NAME_FREE = {"The", "This", "That", "These", "Those", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


def sentence_starts(text):
    """Offsets of the first letter of each sentence (after any @s locator or [tag])."""
    starts = []
    for sentence in split_sentences(text):
        at = text.find(sentence)
        lead = re.match(r"\W*(?:@\d+(?:\.\d+)?\s+)?(?:\[[^\]]*\]\s*)?\W*", sentence)
        starts.append(at + lead.end())
    return starts


def ordinary(word, known):
    """The word, or its plain/inflected stem, is an ordinary English word (dictionary lookup)."""
    low = word.lower()
    stems = {low}
    for suffix, repl in (("s", ""), ("es", ""), ("ies", "y"), ("ed", ""), ("ed", "e"), ("d", ""), ("ing", ""),
                         ("ing", "e"), ("ly", ""), ("er", ""), ("ers", ""), ("'s", "")):  # fmt: skip
        if low.endswith(suffix) and len(low) > len(suffix) + 2:
            stems.add(low[: -len(suffix)] + repl)
    return bool(stems & known)


def unsourced_names(text, source):
    """[(start, end, name)] proper names of `text` that neither speech nor OCR (`source`, source_norm) holds.

    Candidates: CamelCase and ALLCAPS words anywhere, and Capitalized words that do not start a sentence and
    are not ordinary English words; quoted text is checked elsewhere. Spaces, hyphens and case are ignored in
    the comparison (OpenClaw = Open Claw).
    """
    known = dictionary()
    starts = set(sentence_starts(text))
    masked = QUOTED_SPAN.sub(lambda m: " " * len(m[0]), text)
    found = []
    for m in NAME_WORD.finditer(masked):
        word = m[0]
        if word in NAME_FREE or word in NOT_NAMES:
            continue
        if word[1:].islower() and (m.start() in starts or ordinary(word, known)):  # Xxxx: an ordinary word
            continue
        if not fuzzy_in(source_norm(word), source):
            found.append((m.start(), m.end(), word))
    return found


def verify_names(text, source):
    """(text, names): names missing in the source are replaced by the generic description the model put in
    brackets right after them, else marked [name not in source]."""
    names = unsourced_names(text, source)
    for start, end, _ in reversed(names):
        generic = NAME_GENERIC.match(text, end)
        text = text[:start] + (generic[1].strip() if generic else NAME_MARK) + text[generic.end() if generic else end :]
    return text, [x[2] for x in names]


def evaluate(formula, covered):
    """Value of +-*/ over covered numbers, else None."""
    try:
        tree = ast.parse(formula.replace("−", "-").replace("×", "*").replace(",", "."), mode="eval")
    except SyntaxError:
        return None

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            if node.value != 100 and not any(abs(abs(node.value) - c) < 1e-9 for c in covered):  # 100: percent
                raise ValueError
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            return -walk(node.operand) if isinstance(node.op, ast.USub) else walk(node.operand)
        raise ValueError

    try:
        return walk(tree)
    except (ValueError, ZeroDivisionError):
        return None


def derived_ok(item, covered):
    got = evaluate(item.get("formula", ""), covered)
    stated = values(item.get("value", ""))
    if got is None or len(stated) != 1:
        return False
    shown = next(iter(stated))
    # a whole number states a rounded value (28.7% shown as 29%)
    return abs(abs(got) - shown) <= (0.5 if shown == int(shown) else 0.051)


# --- final OCR (the single source of truth for `.screen.md` and for validation) -----------------

DICTIONARY = None


def dictionary():
    global DICTIONARY
    if DICTIONARY is None:
        path = Path("/usr/share/dict/words")
        DICTIONARY = {w.strip().lower() for w in path.open(errors="ignore")} if path.exists() else set()
    return DICTIONARY


def noisy(text):
    """Not protected, no digits/URL/command, and not mostly dictionary words: OCR noise."""
    if re.search(r"\d|[/@]|\w\.\w|\bnpx?\b", text):
        return False
    words = [w.lower() for w in re.findall(r"[A-Za-z]{2,}", text)]
    known = dictionary()
    if not known:
        return len(words) < 2
    return len(words) < 2 or sum(w in known for w in words) / len(words) < 0.7


def protected_terms(corpus):
    """Numbers and anchor tokens cited by the card/article; OCR rows containing them are never dropped."""
    names = set(PROPER.findall(corpus)) | CMD_WORDS  # names are checked against OCR, they do not protect noisy rows
    return {
        "numbers": values(corpus),
        "tokens": {normalized(a) for a in anchors(corpus) if a not in names and len(normalized(a)) >= 3},
    }


def final_screen(common, corpus=""):
    """(rows, counts): deduplicated OCR without noise, keeping everything the card/article cites."""
    records = common["scan"]["screen_text"]
    protect = protected_terms(corpus)
    rows = []
    for r in local_screen_text(common):
        same = [x for x in records if normalized(x["text"]) == normalized(r["text"])]
        text = r["text"]
        key = normalized(text)
        rows.append(
            {
                "first": r["timestamp_s"],
                "last": max(x.get("last_seen_s", x["timestamp_s"]) for x in same),
                "text": text,
                "uncertain": bool(r.get("uncertain_content")),
                "protected": bool(values(text) & protect["numbers"]) or any(t in key for t in protect["tokens"]),
            }
        )
    kept, counts = clean_screen(rows)
    out = []
    for row in kept:
        if not row["protected"] and noisy(row["text"]):
            counts["noise"] = counts.get("noise", 0) + 1
        else:
            out.append(row)
    return out, counts


def screen_text(rows):
    return "\n".join(r["text"] for r in rows)


# --- file-level verification of the written bridge ----------------------------------------------

SKIP_SECTIONS = {"number_check", "local_rejections", "not_stated"}


def body(path):
    text = Path(path).read_text(encoding="utf-8")
    return text.split("---", 2)[2] if text.startswith("---") else text


def check_bridge(root, ids):
    """Violations (strings) for cards/articles whose numbers or screen claims lack source coverage."""
    root = Path(root)
    problems = []
    for id_ in ids:
        tx = re.sub(r"^\[\d+:\d+\]", "", body(root / "archive" / f"{id_}.tx.md"), flags=re.M)
        screen_path = root / "archive" / f"{id_}.screen.md"
        screen_lines = [re.sub(r"^\[[\d.]+–[\d.]+s\]\s*", "", ln) for ln in screen_path.read_text().splitlines()[5:]]
        screen = "\n".join(screen_lines)
        covered = values(tx, words=True) | values(screen, words=True)
        card_text = (root / "cards" / f"{id_}.md").read_text(encoding="utf-8")
        _, front, card_body = card_text.split("---", 2)
        meta = yaml.safe_load(front)
        sections = dict(re.findall(r"^## (\w+)\n(.*?)(?=^## |\Z)", card_body, re.M | re.S))
        derived = []
        for line in sections.get("derived", "").splitlines():
            m = re.match(r"- (.+?) = (.+)", line)
            if m:
                item = {"value": m[1].split(": ")[-1], "formula": m[2]}
                derived.append(item)
                if not derived_ok(item, covered):
                    problems.append(f"{id_}: derived without a valid formula: {line}")
        covered |= {v for item in derived for v in values(item["value"])}
        for name, text in sections.items():
            if name in SKIP_SECTIONS or name == "derived":
                continue
            for number in uncovered(text, covered):
                problems.append(f"{id_}: card/{name}: number {number} not covered by the transcript or OCR")
            for line in text.splitlines():
                line = line.removeprefix("- ")
                if line.startswith(("założenie", "assumption")):
                    continue
                for sentence in split_sentences(line):
                    if reason := claim_problem(sentence, screen, tx):
                        problems.append(f"{id_}: card/{name}: {reason}: {sentence[:80]}")
                if reason := stub_problem(line):
                    problems.append(f"{id_}: card/{name}: {reason}: {line[:80]}")
        article = (root / "articles" / f"{id_}.md").read_text(encoding="utf-8")
        prose, table = L.split_article(article)
        if "order_logical" in card_text:
            problems.append(f"{id_}: card contains order_logical (steps must be in execution order)")
        data_rows = [
            [c.strip() for c in line.strip().strip("|").split("|")]
            for line in table.splitlines()
            if line.startswith("|") and not line.startswith("|---") and not L.is_table_header(line)
        ]
        cells_text = " ".join(" ".join(c[1:3]) for c in data_rows)
        for number in uncovered(prose + "\n" + cells_text, covered):
            problems.append(f"{id_}: article: number {number} not covered by the transcript or OCR")
        paragraphs = [x.strip() for x in prose.split("\n\n") if x.strip() and not x.startswith("#")]
        for paragraph in paragraphs:
            for sentence in split_sentences(paragraph):
                if reason := claim_problem(sentence, screen, tx):
                    problems.append(f"{id_}: article: {reason}: {sentence[:80]}")
                if reason := stub_problem(sentence, 3):
                    problems.append(f"{id_}: article: {reason}: {sentence[:80]}")
        for cells in data_rows:
            if len(cells) == 5:
                in_screen = covers(cells[2], values(screen, words=True)) or (
                    not values(cells[2]) and present(cells[2], source_norm(screen))
                )
                source, confidence = L.source_kind(cells[3]), L.confidence_kind(cells[4])
                if confidence == "speech" and in_screen:
                    problems.append(f"{id_}: table: source is 'speech' but the number is in the OCR: {cells[2]}")
                if confidence in ("exact", "approximate") and not in_screen:
                    problems.append(f"{id_}: table: confidence '{cells[4]}' but {cells[2]} is not in the OCR")
                if source == "screen" and not in_screen:
                    problems.append(f"{id_}: table: source '{cells[3]}' but {cells[2]} is not in the OCR")
        for number, status in (meta.get("number_check") or {}).items():
            v = values(number)
            on_screen = bool(v & values(screen, words=True))
            on_speech = bool(v & values(tx, words=True))
            expected = "ok" if on_screen and on_speech else "screen_only" if on_screen else "speech_only"
            if not str(status).startswith("conflict") and status != expected:
                problems.append(f"{id_}: number_check {number}={status}, but the sources indicate {expected}")
    return problems
