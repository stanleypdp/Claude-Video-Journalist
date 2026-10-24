"""Rejection lines of a Read card: parsed back into kind and fields, shortened for the card.

The full lines (they quote the rejected text) go to `archive/<id>.rejections.md`; the card keeps only
"field: reason" so that an agent reading the card cannot rebuild what the source check removed.
"""

import re
from collections import Counter
from pathlib import Path

from vjournalist.bridge import lang as L

# More specific templates first; `rej_sentence` ("{key}: {text} — {reason}") matches almost anything.
KINDS = (
    "rej_number_field",
    "rej_cut",
    "rej_derived",
    "rej_table_label_number",
    "rej_table_number",
    "rej_table_value",
    "rej_table_unlabeled",
    "rej_table_trimmed",
    "rej_quote",
    "rej_reattributed",
    "rej_stub",
    "rej_general",
    "rej_moved",
    "rej_name",
    "rej_sentence",
)
QUOTED_ITEM = re.compile(r"[„“]([^”„“]+)[”]|\(([^)]*)\)")


def _pattern(template):
    parts = re.split(r"(\{\w+\})", template)
    return re.compile("".join(f"(?P<{p[1:-1]}>.+?)" if p.startswith("{") else re.escape(p) for p in parts), re.S)


PATTERNS = {
    (lang, kind): _pattern(L.MESSAGES[lang][kind]) for lang in L.MESSAGES for kind in KINDS if kind in L.MESSAGES[lang]
}


def parse(line):
    """(kind, fields) of one rejection line in any language; (None, {}) when no template fits."""
    line = line.strip().removeprefix("- ")
    for kind in KINDS:
        for lang in L.MESSAGES:
            if (found := PATTERNS[lang, kind].fullmatch(line)) is not None:
                return kind, found.groupdict()
    return None, {}


def reason_class(reason):
    """The reason without the rejected tokens it quotes ("not in OCR: Supertrend" -> "not in OCR")."""
    return re.sub(r"\s*\(.*\)$", "", reason.split(": ")[0]).strip()


def brief(line, lang):
    """The card version of a rejection line: field and reason, never the rejected content."""
    kind, fields = parse(line)
    if kind is None:
        return line.strip().removeprefix("- ").split(": ", 1)[0] + ": rejected"
    if kind == "rej_sentence":
        fields = {**fields, "reason": L.localize_reason(lang, reason_class(fields["reason"]))}
    return L.say(lang, f"brief_{kind}", **fields)


def brief_list(lines, lang):
    """Brief lines in order of first appearance; identical ones collapse to `… (×n)`."""
    counted = Counter(brief(x, lang) for x in lines)
    return [f"{text} (×{n})" if n > 1 else text for text, n in counted.items()]


def fragments(line):
    """(texts, against): the rejected fragments of a line and the sources the line says them missing from.

    against: `ocr` (rejected for not being on screen) or `both` (not in speech or OCR); texts is empty for
    rejections of numbers, stubs, derived items and generalizations (nothing to find in the source).
    """
    kind, f = parse(line)
    if kind == "rej_cut":
        return [a or b for a, b in QUOTED_ITEM.findall(f["cuts"])], "both"
    if kind in ("rej_quote", "rej_reattributed"):
        return [f["quote"]], "ocr"
    if kind == "rej_table_unlabeled":
        return [f["label"]], "both"
    if kind == "rej_table_trimmed":
        return [f["removed"]], "both"
    if kind == "rej_table_value":
        return [f["value"]], "ocr"
    if kind == "rej_name":
        return [f["name"]], "both"
    if kind == "rej_sentence":
        for prefix, against in (("not in speech or OCR: ", "both"), ("brak w mowie i OCR: ", "both"),
                                ("not in OCR: ", "ocr"), ("brak w OCR: ", "ocr")):  # fmt: skip
            if f["reason"].startswith(prefix):
                return [t.strip() for t in f["reason"][len(prefix) :].split(", ") if t.strip()], against
    return [], "both"


def rejection_lines(root, id_):
    """Full rejection lines of a result: the diagnostic file when it exists, else the card's own section."""
    root = Path(root)
    path = root / "archive" / f"{id_}.rejections.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not text:
        card = (root / "cards" / f"{id_}.md").read_text(encoding="utf-8")
        section = re.search(r"^## local_rejections\n+(.*?)(?=^## |\Z)", card, re.M | re.S)
        text = section[1] if section else ""
    return [x.strip().removeprefix("- ") for x in text.splitlines() if x.strip().startswith("- ")]
