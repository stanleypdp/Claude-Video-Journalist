"""One reading of numbers for every Read check (cards, articles, tables, number_check).

A token is `(start, end, alts)`: the span in the text and the values it may stand for (`alts[0]` is the
primary one). Digits, glued digits (`H1`, `TR10`, `RISK1R`), thousands with a space (`17 073`), `k`/`M`
suffixes and `59 thousand` are read on every side. Spoken numerals (`one`, `eight`, `factor three`,
`two point five`) are read only on the covering side (`words=True`: transcript and OCR), so a paraphrase
on the card never creates a requirement the source cannot meet.
"""

import re

NUM = re.compile(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?")
SPACED = re.compile(r"(?<![\d.,])\d{1,3}(?:[    ]\d{3})+(?![\d]|[.,]\d)")
GLUED = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,12}(\d+(?:\.\d+)?)[A-Za-z]{0,12}(?![A-Za-z0-9]|\.\d)")
SCALE_WORD = {"thousand": 1e3, "million": 1e6, "billion": 1e9}
SUFFIX = {"k": 1e3, "K": 1e3, "M": 1e6}

UNITS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen".split()
    )
}
TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
ORDINALS = {
    w: i
    for i, w in enumerate("_ first _ third fourth fifth sixth seventh eighth ninth tenth".split())
    if w != "_"
}
FRACTIONS = {"half": 0.5, "quarter": 0.25}
# "one" is a pronoun more often than a count: these neighbours make it one.
ONE_BEFORE = {"no", "any", "every", "some", "each", "this", "that", "which", "another", "whichever"}
ONE_AFTER = {
    "of", "who", "that", "which", "where", "can", "could", "should", "would", "is", "was", "will", "must",
    "thing", "else", "another", "another's",
}
WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")


def value_of(raw):
    """float of '1,096' / '55,2' / '0.16' (comma = thousands unless it is a lone decimal comma), else None."""
    s = raw.lstrip("+-")
    if s.count(",") == 1 and "." not in s and len(s.rsplit(",", 1)[1]) != 3:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def inside_larger_number(text, m):
    """09:30, 1.2.3, 12,34,56 or a number glued to digits: the match is a piece of something else."""
    before, after = text[max(0, m.start() - 2) : m.start()], text[m.end() : m.end() + 2]
    return bool(re.search(r"\d[:.,]$", before) or re.match(r"[:.,]\d", after))


def _scaled(text, end, value):
    """Alternative reading of a number followed by k/M or 'thousand'/'million' (None when it has none)."""
    if end < len(text) and text[end] in SUFFIX and not text[end + 1 : end + 2].isalpha():
        return value * SUFFIX[text[end]]
    m = re.match(r"\s+(thousand|million|billion)\b", text[end : end + 12], re.I)
    return value * SCALE_WORD[m[1].lower()] if m else None


def digit_tokens(text, glued=True):
    """Digit tokens with span: plain, spaced thousands, scaled (59k) and, with `glued`, digits fused to
    letters (H1, TR10): names and units the source can cover but a card is never required to match."""
    tokens, blank = [], list(text)
    for m in SPACED.finditer(text):
        raw = re.sub(r"[    ]", "", m.group())
        tokens.append((m.start(), m.end(), (float(raw),)))
        blank[m.start() : m.end()] = " " * (m.end() - m.start())
    masked = "".join(blank)
    for m in NUM.finditer(masked):
        if inside_larger_number(masked, m):
            continue
        value = value_of(m.group())
        if value is None:
            continue
        scaled = _scaled(masked, m.end(), value)
        tokens.append((m.start(), m.end(), (scaled, value) if scaled is not None else (value,)))
    for m in GLUED.finditer(masked) if glued else ():
        tokens.append((m.start(1), m.end(1), (float(m[1]),)))
    return sorted(tokens)


def _word_runs(text):
    """[(value, start, end)] for spoken numerals: twenty-one, two hundred and five, two point five, half."""
    words = [(m[0].lower(), m.start(), m.end()) for m in WORD.finditer(text)]
    out, i = [], 0
    while i < len(words):
        w, start, end = words[i]
        if w in FRACTIONS:
            out.append((FRACTIONS[w], start, end))
            i += 1
            continue
        if w == "couple" and i and words[i - 1][0] == "a":
            out.append((2.0, words[i - 1][1], end))
            i += 1
            continue
        if w in ORDINALS:
            out.append((float(ORDINALS[w]), start, end))
            i += 1
            continue
        if w not in UNITS and w not in TENS and w not in SCALES:
            i += 1
            continue
        total = current = 0
        last = None  # kind of the previous word of the run: unit | tens | scale
        j, stop = i, end
        while j < len(words):
            w, _, wend = words[j]
            joined = text[stop : words[j][1]] if j > i else ""
            if j > i and not re.fullmatch(r"[\s-]*", joined):
                break
            if w == "and" and last in ("hundred", "scale") and j + 1 < len(words):
                if words[j + 1][0] in UNITS or words[j + 1][0] in TENS:
                    j += 1
                    stop = wend
                    continue
                break
            if w in UNITS and last in (None, "scale", "hundred", "tens") and not (last == "tens" and UNITS[w] > 9):
                if last == "tens" and UNITS[w] == 0:
                    break
                current += UNITS[w]
                last = "tens_unit" if last == "tens" else "unit"
            elif w in TENS and last in (None, "scale", "hundred"):
                current += TENS[w]
                last = "tens"
            elif w == "hundred" and last in ("unit", "tens_unit"):
                current = (current or 1) * 100
                last = "hundred"
            elif w in ("thousand", "million", "billion") and last in (None, "unit", "tens", "tens_unit", "hundred"):
                total += (current or 1) * SCALES[w]
                current = 0
                last = "scale"
            elif w == "hundred" and last is None:
                current = 100
                last = "hundred"
            else:
                break
            stop = wend
            j += 1
        if j == i:
            i += 1
            continue
        value = float(total + current)
        # "two point five": single digit words after "point"
        if j + 1 < len(words) and words[j][0] == "point" and words[j + 1][0] in UNITS and UNITS[words[j + 1][0]] < 10:
            digits, k = "", j + 1
            while k < len(words) and words[k][0] in UNITS and UNITS[words[k][0]] < 10:
                digits += str(UNITS[words[k][0]])
                stop = words[k][2]
                k += 1
            value = float(f"{int(value)}.{digits}")
            j = k
        first = words[i][0]
        if first == "one" and j == i + 1:
            before = words[i - 1][0] if i else ""
            after = words[j][0] if j < len(words) else ""
            if before in ONE_BEFORE or after in ONE_AFTER:
                i = j
                continue
        out.append((value, start, stop))
        i = j
    return out


def word_tokens(text):
    return [(s, e, (v,)) for v, s, e in _word_runs(text)]


def tokens(text, words=False, glued=True):
    """All number tokens of `text`, ordered by position; spoken numerals only with `words=True`."""
    found = digit_tokens(text, glued)
    if words:
        taken = [(s, e) for s, e, _ in found]
        # "59 thousand": the scale word belongs to the digits before it, it is no number of its own
        found += [
            t
            for t in word_tokens(text)
            if not any(
                s < t[1] and t[0] < e or (0 <= t[0] - e <= 2 and text[t[0] : t[1]].lower() in SCALE_WORD)
                for s, e in taken
            )
        ]
    return sorted(found)


def fix_ocr_digits(text):
    """O/o read for 0 next to digits or separators: '1,00O' -> '1,000'."""
    return re.sub(r"(?<=[\d.,])[Oo](?=[\d.,]|\b)|\b[Oo](?=\d)", "0", text)


def nums(text, words=False, primary=False):
    """{value: raw text} of the numbers in `text` (all readings of each token unless `primary`)."""
    out = {}
    for start, end, alts in tokens(text, words):
        for v in alts[:1] if primary else alts:
            out.setdefault(v, text[start:end])
    return out


def digits_for_words(text):
    """`text` with spoken numerals replaced by digits ('factor three' -> 'factor 3'); for text matching."""
    out, position = [], 0
    for start, end, alts in word_tokens(text):
        value = alts[0]
        out.append(text[position:start])
        out.append(str(int(value)) if value == int(value) else str(value))
        position = end
    out.append(text[position:])
    return "".join(out)
