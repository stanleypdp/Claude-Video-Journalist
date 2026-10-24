# polish-lexicon: this file holds Polish-language patterns/labels on purpose (Polish is a supported source language).
"""Local OCR presentation and evidence hints; never manufacture source readings."""

import re
from difflib import SequenceMatcher


def normalized(text):
    text = re.sub(
        r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
        lambda m: str(
            [
                "zero",
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
                "ten",
                "eleven",
                "twelve",
            ].index(m[0])
        ),
        text.casefold(),
    )
    return re.sub(r"[^\w]", "", text)


def repeats_speech(record, transcript):
    text = normalized(record["text"])
    if len(text) < 6:
        return False
    nearby = [
        segment
        for segment in transcript["segments"]
        if segment["start"] <= record.get("last_seen_s", record["timestamp_s"]) + 3
        and segment["end"] >= record["timestamp_s"] - 3
    ]
    # OCR captions can straddle two speech segments.
    for segment in nearby + [{"text": " ".join(s["text"] for s in nearby)}]:
        speech = normalized(segment["text"])
        if text in speech:
            return True
        # Sliding window also handles OCR joining words and partial subtitles.
        for n in {len(text), min(len(speech), round(len(text) * 1.15))}:
            for start in range(max(1, len(speech) - n + 1)):
                if SequenceMatcher(None, text, speech[start : start + n]).ratio() >= 0.86:
                    return True
    return False


def illustrative(frame):
    return any("illustrative" in normalized(i["text"]) for i in frame.get("items", []))


def counter_hints(common):
    groups = {}
    for record in common["scan"]["screen_text"]:
        match = re.fullmatch(r"\s*([\d, .]+)\s+(TRADES|SESSIONS|TRANSACTIONS)\s*", record["text"], re.I)
        if match:
            number = int(re.sub(r"\D", "", match[1]))
            groups.setdefault(match[2].upper(), []).append((record["timestamp_s"], number, record["id"]))
    hints = []
    speech = normalized(" ".join(s["text"] for s in common["transcript"]["segments"]))
    for label, readings in groups.items():
        readings.sort()
        cluster = []
        for reading in readings:
            if cluster and reading[0] - cluster[-1][0] > 5:
                cluster = []
            cluster.append(reading)
            if len(cluster) >= 2 and all(a[1] < b[1] for a, b in zip(cluster, cluster[1:])):
                final = cluster[-1][1]
                if str(final) in speech:
                    hints = [h for h in hints if h["label"] != label]
                    hints.append(
                        {
                            "label": label,
                            "readings": [{"time": t, "value": v, "ocr_id": ref} for t, v, ref in cluster],
                            "final": final,
                            "evidence": "inferred_from_successive_ocr; final confirmed by narration",
                        }
                    )
    return hints


def local_screen_text(common):
    """Deduplicate locally, suppress speech subtitles and illustrative axes/labels."""
    result, seen = [], []
    hints = counter_hints(common)
    intermediate = {r["ocr_id"] for h in hints for r in h["readings"][:-1]}
    frames = common["scan"]["frames"]
    illustrative_texts = {
        normalized(i["text"])
        for f in frames
        if illustrative(f)
        for i in f["items"]
        if (sum(p[1] for p in i["box"]) / len(i["box"])) < 0.7
    }
    for record in common["scan"]["screen_text"]:
        if record["timestamp_s"] >= common["platform_info"]["content_duration_s"]:
            continue
        text = record["text"].strip()
        # Bare numeric axes and fused OCR data labels are not readable standalone evidence.
        if re.fullmatch(r"[-+\d,.\s]+", text) or re.search(r"\d[.,]?\d*%[A-Za-z]{2,}\d", text):
            continue
        key = normalized(text)
        if record["text_confidence"] == "unreadable" or not key or text == "unknown":
            continue
        if re.search(r"tiktok|instagram|@", text, re.I) or record["id"] in intermediate:
            continue
        # Numeric axes recurring on illustrative panels are excluded along with their labels.
        near_illustration = any(
            abs(f["timestamp_s"] - record["timestamp_s"]) <= 5 and illustrative(f) for f in frames
        )
        if (key in illustrative_texts or near_illustration) and (
            re.fullmatch(r"[-+\d,.\s]+", text)
            or key in {"yesterday", "today", "poc", "random", "samedistance", "todaysopen"}
            or "illustrative" in key
        ):
            continue
        if repeats_speech(record, common["transcript"]):
            continue
        if any(
            key == prior or (len(key) >= 8 and SequenceMatcher(None, key, prior).ratio() >= 0.92)
            for prior in seen
        ):
            continue
        seen.append(key)
        substantive = bool(re.search(r"\d|costs|edge|return|profit|koszt|wynik|przewag", text, re.I))
        result.append({**record, "uncertain_content": substantive and record["text_confidence"] != "exact"})
    return sorted(result, key=lambda r: r["timestamp_s"])


def data_candidates(common):
    """Spend images only on weak data text, not low-confidence prose/axes."""
    candidates = []
    intermediate_times = {r["time"] for h in counter_hints(common) for r in h["readings"][:-1]}
    for frame in common["scan"]["frames"]:
        if frame["timestamp_s"] in intermediate_times:
            continue
        if (
            not frame["needs_data_image"]
            or frame["timestamp_s"] >= common["platform_info"]["content_duration_s"]
        ):
            continue
        if illustrative(frame):
            continue
        items = frame.get("items")
        if items is None:  # callers with older/minimal mechanics metadata
            candidates.append(frame)
            continue
        # Two numeric data labels (%, R, etc.) provide evidence of data rather than a price axis.
        weak_data = [
            i
            for i in items
            if i["score"] < 0.95
            and not repeats_speech(
                {"text": i["text"], "timestamp_s": frame["timestamp_s"]}, common["transcript"]
            )
            and re.search(r"\d.*(?:%|\bR\b|PTS|TRADES)", i["text"], re.I)
        ]
        if frame["kind"] in ("code", "table") or weak_data:
            candidates.append(frame)
    return candidates


FOREIGN = re.compile(r"[⺀-鿿가-힯Ѐ-ӿ�]")
TICK = re.compile(
    r"(?:\d{1,2}:\d{2}|(?:19|20)\d\d|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
)


def _same_text(a, b):
    na, nb = normalized(a), normalized(b)
    if not na or not nb or re.sub(r"\D", "", a) != re.sub(r"\D", "", b):
        return False
    short, long = sorted((na, nb), key=len)
    if len(short) >= 5 and short in long and len(short) / len(long) >= 0.6:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= 0.8


def _damaged(text, uncertain):
    letters = re.sub(r"[\W\d_]", "", text)
    if (
        FOREIGN.search(text)
        or not re.search(r"\w", text)
        or re.search(r"[^\W\d_]{20,}|[^\W\d_-]+-[^\W\d_]{20,}", text)
    ):
        return True  # also fused words: OCR lost the spaces
    if re.search(r"(?i)tik\s*t|\bikto\b", text) or any(
        len(w) >= 12 and re.search(r"[^aeiouyąęó\W\d_]{5,}", w, re.I) for w in re.findall(r"[^\W\d_]+", text)
    ):
        return True  # garbled platform watermark / consonant-heavy gibberish
    if len(re.sub(r"\W", "", text)) <= 2 and not re.search(r"\d", text):
        return True
    # Uncertain readings without one properly formed word (>=4 letters, with a vowel) are noise.
    if uncertain and not any(
        len(w) >= 4 and re.search(r"[aeiouyąęó]", w, re.I) for w in re.findall(r"[^\W\d_]+", text)
    ):
        return True
    return len(letters) >= 3 and not re.search(r"[aeiouyąęó]", letters, re.I)


def clean_screen(rows):
    """rows: dicts first,last,text,uncertain. Drops damaged tokens and axis ticks, merges variants.

    Returns (kept, counts); first/last of a merged group span all of its variants.
    """
    counts = {"damaged": 0, "axis": 0, "merged_variants": 0}
    candidates = []
    for order, r in enumerate(rows):
        if _damaged(r["text"], r["uncertain"]):
            counts["damaged"] += 1
        else:
            candidates.append({**r, "order": order})
    ticks = [r for r in candidates if TICK.fullmatch(r["text"].strip())]
    axis = {
        id(r) for r in ticks if len({t["text"] for t in ticks if abs(t["first"] - r["first"]) <= 1.0}) >= 3
    }
    counts["axis"] = len(axis)
    groups = []
    for r in sorted(
        (r for r in candidates if id(r) not in axis),
        key=lambda r: (r["uncertain"], -len(r["text"]), r["order"]),
    ):
        for g in groups:
            if (
                _same_text(g["text"], r["text"])
                and r["first"] <= g["last"] + 3
                and r["last"] >= g["first"] - 3
            ):
                g["first"], g["last"] = min(g["first"], r["first"]), max(g["last"], r["last"])
                counts["merged_variants"] += 1
                break
        else:
            groups.append(r)
    return sorted(groups, key=lambda g: (g["first"], g["order"])), counts  # keep reading order within a frame
