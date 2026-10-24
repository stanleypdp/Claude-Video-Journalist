"""Read quality metrics over written cards (deterministic, no LLM).

false_rejection_rate   share of rejections whose removed content is in the source after all
screen_attribution_ok  share of quotes given as on-screen text that stand in the OCR without a marker
not_in_ocr_per_card    average number of [not in OCR] markers per card and article
"""

import re
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from vjournalist.bridge import coverage as cov
from vjournalist.bridge import rejections as R

THRESHOLD = 0.8


class Source:
    """A source text prepared for coverage checks: spaceless normalized form and the set of its words."""

    def __init__(self, text):
        self.norm = cov.source_norm(text)
        self.words = set(re.findall(r"[^\W_]+", cov.source_norm_words(text)))


def covered(fragment, source):
    """The fragment is in the source: a single word by similarity to one source word (so "often" is not found
    inside "soften"), longer text as a whole or as two adjacent content words (spaces and case ignored)."""
    words = [w for w in re.findall(r"[^\W_]+", cov.source_norm_words(fragment)) if len(w) >= 3 and w not in cov.STOP_WORDS]
    if len(words) <= 1:
        word = words[0] if words else cov.source_norm(fragment)
        return bool(word) and any(
            abs(len(word) - len(w)) <= 2 and SequenceMatcher(None, word, w).ratio() >= THRESHOLD for w in source.words
        )
    return cov.fuzzy_in(cov.source_norm(fragment), source.norm, THRESHOLD) or any(
        len(a + b) >= 6 and (a + b) in source.norm for a, b in zip(words, words[1:], strict=False)
    )


def sources(root, id_):
    """(speech, ocr) texts of a written result, read from its archive files."""
    archive = Path(root) / "archive"
    speech = re.sub(r"^\[\d+:\d+\]", "", cov.body(archive / f"{id_}.tx.md"), flags=re.M)
    lines = (archive / f"{id_}.screen.md").read_text(encoding="utf-8").splitlines()[5:]
    return speech, "\n".join(re.sub(r"^\[[\d.]+–[\d.]+s\]\s*(?:≈ )?", "", x) for x in lines)


def local_source(speech, ocr_text, value):
    """Speech sentences (the one with the number and its neighbours) and OCR rows that carry `value`."""
    numbers = cov.values(value)
    sentences = cov.split_sentences(speech)
    near = {j for i, x in enumerate(sentences) if numbers & cov.values(x, words=True) for j in (i - 1, i, i + 1)}
    rows = [x for x in ocr_text.splitlines() if numbers & cov.values(x, words=True)]
    return " ".join([sentences[j] for j in sorted(near) if 0 <= j < len(sentences)] + rows)


# a marked or re-attributed quote is a correction of the attribution, not a removal of content
NOT_REMOVALS = ("rej_quote", "rej_reattributed")


def statements(root, id_):
    """Sentences of the card (claims, not the diagnostics) and of the article prose."""
    from vjournalist.bridge import lang as L

    card = (Path(root) / "cards" / f"{id_}.md").read_text(encoding="utf-8")
    sections = dict(re.findall(r"^## (\w+)\n(.*?)(?=^## |\Z)", card.split("---", 2)[2], re.M | re.S))
    out = []
    for name, text in sections.items():
        if name in cov.SKIP_SECTIONS or name == "derived":
            continue
        out += [s for line in text.splitlines() for s in cov.split_sentences(line.removeprefix("- ")) if s]
    prose, _ = L.split_article((Path(root) / "articles" / f"{id_}.md").read_text(encoding="utf-8"))
    out += [s for p in prose.split("\n\n") if not p.startswith("#") for s in cov.split_sentences(p)]
    return out, card, prose


def measure(root, ids):
    """Totals of the three metrics (and their counts) over the given results of one output folder."""
    total = dict.fromkeys(("cards", "rejections", "false_rejections", "screen_phrases", "screen_phrases_ok", "not_in_ocr"), 0)
    for id_ in ids:
        speech, ocr_text = sources(root, id_)
        ocr_norm = cov.source_norm(ocr_text)
        ocr_source, both = Source(ocr_text), Source(speech + "\n" + ocr_text)
        total["cards"] += 1
        for line in R.rejection_lines(root, id_):
            kind, fields = R.parse(line)
            if kind in NOT_REMOVALS:
                continue
            total["rejections"] += 1
            texts, against = R.fragments(line)
            haystack = ocr_source if against == "ocr" else both
            if kind in ("rej_table_unlabeled", "rej_table_trimmed"):  # a label counts where it stands next to its number
                haystack = Source(local_source(speech, ocr_text, fields["value"]))
            # rejected for every fragment it lists: false only when all of them are in the source after all
            total["false_rejections"] += bool(texts) and all(covered(t, haystack) for t in texts)
        sentences, _, prose = statements(root, id_)
        for sentence in sentences:
            for m, quote in cov.screen_quotes(sentence, marked=True):
                total["screen_phrases"] += 1
                total["screen_phrases_ok"] += not m[2] and cov.in_ocr(quote, ocr_text, ocr_norm)
        card_body = (Path(root) / "cards" / f"{id_}.md").read_text(encoding="utf-8").split("---", 2)[2]
        total["not_in_ocr"] += (card_body.partition("## local_rejections")[0] + prose).count(cov.NOT_IN_OCR)
    return total


def rates(total):
    """The three published metrics from `measure` totals (plus the counts they come from)."""
    ratio = lambda a, b, empty: round(a / b, 4) if b else empty  # noqa: E731
    return {
        "cards": total["cards"],
        "rejections": total["rejections"],
        "false_rejections": total["false_rejections"],
        "false_rejection_rate": ratio(total["false_rejections"], total["rejections"], 0.0),
        "screen_phrases": total["screen_phrases"],
        "screen_phrases_ok": total["screen_phrases_ok"],
        "screen_attribution_ok": ratio(total["screen_phrases_ok"], total["screen_phrases"], 1.0),
        "not_in_ocr": total["not_in_ocr"],
        "not_in_ocr_per_card": ratio(total["not_in_ocr"], total["cards"], 0.0),
    }


def measure_all(roots):
    """`roots`: [(root, ids)] -> rates over all of them."""
    sums = {}
    for root, ids in roots:
        for k, v in measure(root, ids).items():
            sums[k] = sums.get(k, 0) + v
    return rates(sums)


def card_ids(root):
    return sorted(p.stem for p in (Path(root) / "cards").glob("*.md") if yaml.safe_load(p.read_text(encoding="utf-8").split("---", 2)[1]))
