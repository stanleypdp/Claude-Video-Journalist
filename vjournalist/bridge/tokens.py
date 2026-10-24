# polish-lexicon: this file holds Polish-language patterns/labels on purpose (Polish is a supported source language).
"""What a Read result relies on from the screen, each item with the OCR row it cites (deterministic).

Kinds: data-table rows sourced from the screen, number_check entries seen on screen, tokens of
"on screen" sentences (Polish: "na ekranie widać"), identifiers (URLs, paths, commands) and tools_named.
"""

import re

import yaml

from vjournalist.bridge import lang as L
from vjournalist.bridge.coverage import (
    SCREEN_MARK,
    anchors,
    body,
    cognate_hits,
    fix_ocr_digits,
    normalized,
    split_sentences,
    values,
)

WATERMARK_SHARE = 0.5  # a row visible for more than this share of the video is a watermark, not evidence
TIME_DATE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?|\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}")
ROW = re.compile(r"^\[([\d.]+)–([\d.]+)s\]\s*(?:≈ )?(.*)$")
STOP = {"this", "that", "with", "from", "have", "will", "your", "jest", "oraz", "który", "które", "przez"}
IDENTIFIER = re.compile(r"@|\b[a-z0-9-]+\.[a-z]{2,}\b|^/\w|[A-Za-z]+[-_.][A-Za-z]+/|/[\w-]*[-_.A-Z]")
FIELD_NAME = re.compile(r"[a-z]+(?:_[a-z]+)+")


def load_rows(bridge, id_):
    """([(first, last, text)] all final OCR rows, set of watermark rows, duration_s)."""
    archive = bridge / "archive"
    duration = float(yaml.safe_load((archive / f"{id_}.tx.md").read_text().split("---")[1])["duration_s"])
    rows = []
    for line in (archive / f"{id_}.screen.md").read_text().splitlines():
        if m := ROW.match(line):
            rows.append((float(m[1]), float(m[2]), m[3]))
    return rows, {r for r in rows if r[1] - r[0] > WATERMARK_SHARE * duration}, duration


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]{4,}", normalized_words(text)) if w not in STOP}


def normalized_words(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower())


def literal_number(token, row_text):
    wanted = token.replace(",", "").lstrip("+")
    text = fix_ocr_digits(row_text).replace(",", "")
    return bool(re.search(rf"(?<![\d.:]){re.escape(wanted)}(?!\d|[.:]\d)", text))


def only_in_time_or_date(number, row_text):
    """True when the number occurs in the row only inside a time/date pattern."""
    outside = TIME_DATE.sub(" ", row_text)
    return bool(values(number) & values(row_text)) and not values(number) & values(outside)


def find_number(token, rows):
    wanted = values(token)
    return next(((r, literal_number(fmt_token(token), r[2])) for r in rows if wanted and wanted & values(r[2])), None)


def fmt_token(token):
    m = re.search(r"[+-]?\d[\d,]*(?:\.\d+)?", token)
    return m[0] if m else token


def find_phrase(token, rows, watermarks=frozenset(), sentence=False):
    """Literal substring in any row, else >=2 content words of the phrase in one non-watermark row
    (>=2 cognates for Polish sentences). A row visible for >50% of the video never matches loosely."""
    key = normalized(token)
    for r in rows:
        if key and key in normalized(r[2]):
            return r, True
    rows = [r for r in rows if r not in watermarks]
    words = content_words(token)
    if sentence:
        best = max(rows, key=lambda r: len(cognate_hits(token, r[2])), default=None)
        return (best, False) if best and len(cognate_hits(token, best[2])) >= 2 else None
    if len(words) >= 2:
        return next(((r, False) for r in rows if len(words & content_words(r[2])) >= 2), None)
    return None


def token_rows(bridge, id_):
    """List of dicts: kind, category (number|phrase), token, status (ok|missing), row, literal, pattern."""
    rows, watermarks, _ = load_rows(bridge, id_)
    article = (bridge / "articles" / f"{id_}.md").read_text()
    prose, table = L.split_article(article)
    meta = yaml.safe_load((bridge / "cards" / f"{id_}.md").read_text().split("---", 2)[1])
    card = body(bridge / "cards" / f"{id_}.md").split("## local_rejections")[0]
    found, seen = [], set()

    def add(kind, category, token, hit):
        if (kind, token) in seen:
            return
        seen.add((kind, token))
        row, literal = hit if hit else (None, False)
        found.append(
            {
                "kind": kind,
                "category": category,
                "token": token,
                "status": "ok" if row else "missing",
                "row": row,
                "literal": literal,
                "pattern": bool(row and category == "number" and only_in_time_or_date(token, row[2])),
            }
        )

    for line in table.splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 5 and L.source_kind(cells[3]) in ("screen", "screen+speech"):
            add("data table", "number", f"{cells[1]} = {cells[2]}", find_number(cells[2], rows))
    for number, status in (meta.get("number_check") or {}).items():
        if status in ("ok", "screen_only") or str(status).startswith("conflict"):
            add(f"number_check {status}", "number", number, find_number(number, rows))
    tools = card.split("## tools_named", 1)[-1].split("##", 1)[0] if "## tools_named" in card else ""
    for sentence in (x for ln in prose.splitlines() for x in split_sentences(ln) if SCREEN_MARK.search(x)):
        tokens = [a for a in anchors(sentence, short=True) if not FIELD_NAME.fullmatch(a)]
        for token in tokens:
            add("article phrase", "phrase", token, find_phrase(token, rows, watermarks))
        if not tokens:
            add("article phrase", "phrase", sentence[:90], find_phrase(sentence, rows, watermarks, sentence=True))
    for text in (prose, card):
        for token in dict.fromkeys(a for a in anchors(text) if IDENTIFIER.search(a) and re.search(r"[A-Za-z]", a) and not FIELD_NAME.fullmatch(a)):
            add("identifier", "phrase", token, find_phrase(token, rows, watermarks))
    for token in dict.fromkeys(a for x in tools.splitlines() for a in anchors(x, short=True)):
        add("tools_named", "phrase", token, find_phrase(token, rows, watermarks))
    return found, {"rows": len(rows), "watermark_rows": len(watermarks)}


def metrics(found):
    """Counts for the three review metrics (see vjournalist.read_batch.format_report)."""
    numbers = [t for t in found if t["category"] == "number"]
    phrases = [t for t in found if t["category"] == "phrase"]
    screen_phrases = [t for t in found if t["kind"] == "article phrase"]
    return {
        "number_rows": len(numbers),
        "number_not_literal": sum(not t["literal"] for t in numbers),
        "phrase_rows": len(phrases),
        "phrase_not_literal": sum(not t["literal"] for t in phrases),
        "ok_numbers": sum(t["status"] == "ok" for t in numbers),
        "ok_numbers_in_time_date": sum(t["pattern"] for t in numbers),
        "screen_phrases": len(screen_phrases),
        "screen_phrases_without_row": sum(t["status"] == "missing" for t in screen_phrases),
    }


def render_table(found, info, id_):
    lines = [
        f"{info['rows']} OCR rows ({info['watermark_rows']} of them visible in >50% of the video: not used to match phrases), "
        f"file `archive/{id_}.screen.md`; {len(found)} entries below.\n",
        "| Kind | Token | Status | OCR row | Literal |",
        "|---|---|---|---|---|",
    ]
    for t in found:
        row = f"[{t['row'][0]:.3f}–{t['row'][1]:.3f}s] {t['row'][2]}" if t["row"] else "—"
        lines.append(
            f"| {t['kind']} | {t['token'].replace('|', '/')} | {t['status']} | {row.replace('|', '/')} "
            f"| {'yes' if t['literal'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"
