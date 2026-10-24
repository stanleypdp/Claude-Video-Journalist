"""Referencyjna implementacja mechanizmu transkrypcji (bridge). Deterministyczna, bez LLM.

Input: ASR segments (transcript.json or common.json from the pipeline) and on-screen text (OCR).
Output: the transcript archive in `[mm:ss] text` blocks and the speech-vs-screen number check.
"""

import json
import re
import warnings
from pathlib import Path

from vjournalist.bridge.numbers import NUM, fix_ocr_digits, inside_larger_number, nums  # noqa: F401

SENT_END = re.compile(r"[.?!][\"')\]]*$")


def mmss(t):
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def norm_ws(s):
    return " ".join(s.split())


def load(path):
    """Returns (transcript, screen_texts, raw). Accepts transcript.json and common.json."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    tr = d["transcript"] if "transcript" in d else d
    screen = [x["text"] for x in d.get("scan", {}).get("screen_text", [])]
    return tr, screen, d


def is_low(seg, logprob=-0.8, no_speech=0.6):
    return seg.get("avg_logprob", 0.0) < logprob or seg.get("no_speech_prob", 0.0) > no_speech


def build_blocks(segments, target_s=10.0, max_s=20.0):
    """A block ends at a sentence end once target_s is reached (or hard at max_s).
    The block start is the real start of its first ASR segment."""
    blocks, cur = [], []
    for seg in segments:
        if seg["end"] - seg["start"] > max_s:
            raise ValueError("ASR segment exceeds 20s; regenerate with word timestamps")
        if cur and seg["end"] - cur[0]["start"] > max_s:
            blocks.append(cur)
            cur = []
        cur.append(seg)
        span = seg["end"] - cur[0]["start"]
        if (span >= target_s and SENT_END.search(seg["text"].strip())) or span >= max_s:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def block_text(block):
    return " ".join(norm_ws(s["text"]) + (" [?]" if is_low(s) else "") for s in block)


def block_line(block):
    return f"[{mmss(block[0]['start'])}] {block_text(block)}"


def fmt(v):
    return ("%f" % v).rstrip("0").rstrip(".")


def _lev_le1(a, b):
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) != len(b) or min(len(a.replace(".", "").strip("0")), len(b.replace(".", "").strip("0"))) < 2:
        return False  # at least 2 significant digits (1000 vs 9000 is not a mishearing); a missing or extra digit gives too many false alarms (e.g. 1000 vs 100)
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) == 1:
        return a[diff[0]].isdigit() and b[diff[0]].isdigit()  # podstawienie jednej cyfry
    return (
        len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    )  # przestawienie


CONFLICT_WINDOW_S = 3.0


def _near_in_time(v, c, speech_at, screen_at):
    """A spoken `v` and a screen `c` within CONFLICT_WINDOW_S of each other; always True without times."""
    if speech_at is None or screen_at is None:
        return True
    said = [(a, b) for a, b, text in speech_at if v in nums(text, words=True)]
    shown = [(a, b) for a, b, text in screen_at if c in nums(text, words=True)]
    return any(a - CONFLICT_WINDOW_S <= y and x <= b + CONFLICT_WINDOW_S for a, b in said for x, y in shown)


VERSIONED = re.compile(r"(?<![A-Za-z])([A-Za-z][A-Za-z-]{2,})\s*v?(\d+\.\d+(?:\.\d+)?)")
NOT_PRODUCTS = {
    "version", "step", "chapter", "part", "page", "line", "level", "day", "episode", "number", "item", "figure",
    "tip", "rule", "hack", "stage", "round", "phase", "lesson", "video", "section", "slide", "plus", "minus",
    "around", "about", "over", "under", "above", "below", "only", "than", "was", "from", "with", "and",
}


def version_pairs(text):
    """{(product, version)} of 'Opus 4.7', 'Opus4.6inplanmode', 'Sonnet v4.6' (lowercase product)."""
    return {
        (m[1].lower(), m[2]) for m in VERSIONED.finditer(text) if m[1].lower() not in NOT_PRODUCTS
    }


def version_conflicts(speech_text, screen_texts, speech_at=None, screen_at=None):
    """[(product, spoken, shown)]: the screen shows another version of a product than the speech names.

    Needs the shown pair to be unsaid; with times, both must fall within CONFLICT_WINDOW_S of each other.
    """
    said = version_pairs(speech_text)
    out = set()
    for text in screen_texts:
        for name, shown in version_pairs(text) - said:
            for name2, spoken in said:
                if name2 != name or spoken == shown:
                    continue
                if speech_at is not None and screen_at is not None:
                    a = [(x, y) for x, y, t in speech_at if (name, spoken) in version_pairs(t)]
                    b = [(x, y) for x, y, t in screen_at if (name, shown) in version_pairs(t)]
                    if not any(x - CONFLICT_WINDOW_S <= v and u <= y + CONFLICT_WINDOW_S for x, y in a for u, v in b):
                        continue
                out.add((name, spoken, shown))
    return sorted(out)


def number_check(speech_text, screen_texts, speech_at=None, screen_at=None):
    """Status of every number said: ok (on screen too) | speech_only | conflict(OCR:x).

    `conflict` means the screen shows a one-digit misreading of the spoken number: the screen value is not
    itself spoken (a different quantity such as 0.13R vs 0.16R is no conflict) and, when the times are
    known (`speech_at`/`screen_at`: [(from_s, to_s, text)]), both appear within CONFLICT_WINDOW_S.
    """
    sp = nums(speech_text, words=True)
    sc = {}
    for t in screen_texts:
        sc.update(nums(t, words=True))
    res = {}
    for v in sorted(sp):
        if v in sc:
            res[fmt(v)] = "ok"
            continue
        near = [
            c
            for c in sc
            if c not in sp and _lev_le1(fmt(v), fmt(c)) and _near_in_time(v, c, speech_at, screen_at)
        ]
        res[fmt(v)] = f"conflict(OCR:{fmt(sorted(near)[0])})" if near else "speech_only"
    for _, spoken, shown in version_conflicts(speech_text, screen_texts, speech_at, screen_at):
        if spoken in res:
            res[spoken] = f"conflict(OCR:{shown})"  # same product, another version on screen
    return res, set(map(fmt, sp)), set(map(fmt, sc))


def number_statuses(speech_text, screen_texts, cited=(), speech_at=None, screen_at=None):
    """One status map for card and archive: ok | speech_only | screen_only | conflict(OCR:x).

    Covers every number spoken, plus the screen-only numbers in `cited` (those the card relies on).
    """
    res, sp, sc = number_check(speech_text, screen_texts, speech_at, screen_at)
    cited = {fmt(v) for v in cited}
    return {**res, **{n: "screen_only" for n in sorted((sc - sp) & cited)}}


def numbers_line(res):
    ok = [k for k, v in res.items() if v == "ok"]
    so = [k for k, v in res.items() if v == "speech_only"]
    cf = [f"{k}~{v[13:-1]}" for k, v in res.items() if v.startswith("conflict")]
    return f"ok[{' '.join(ok)}] speech_only[{' '.join(so)}] conflict[{' '.join(cf)}]"


def render_archive(id_, tr, blocks, duration_s, asr, numbers):
    if isinstance(numbers, dict):
        import yaml

        numbers = (
            "\n" + yaml.safe_dump(numbers, sort_keys=False).rstrip().replace("\n", "\n  ").join(["  ", ""])
            if numbers
            else "{}"
        )
    head = [
        "---",
        f"id: {id_}",
        "type: transcript",
        f"lang: {tr.get('language', 'unknown')}",
        f"duration_s: {duration_s}",
        f"asr: {asr}",
        "verified_by_ear: false",
        f"number_check: {numbers}",
        "---",
    ]
    return "\n".join(head + [block_line(b) for b in blocks]) + "\n"


def fragment(archive, at, window=20):
    """Return overlapping blocks, retaining the block preceding the requested time."""
    rows = [(int(m[1]) * 60 + int(m[2]), m[0]) for m in re.finditer(r"^\[(\d+):(\d+)\] .*$", archive, re.M)]
    start, end = max(0, at - window / 2), at + window / 2
    return "\n".join(
        line
        for i, (t, line) in enumerate(rows)
        if t <= end and (rows[i + 1][0] if i + 1 < len(rows) else float("inf")) > start
    )


def compact_ocr(records):
    """OCR rows for the model as text lines: `[12.5s] text`, `[12.5s] ≈ text` for approximate readings.

    Lossless: the model gets the same texts, times and confidence as the JSON records, without repeating
    keys on every row (about 4/5 of the OCR block). Unreadable rows carry no text and are only counted.
    """
    lines, unreadable = [], 0
    for r in records:
        if r.get("text_confidence") == "unreadable":
            unreadable += 1
            continue
        lines.append(f"[{r['timestamp_s']:g}s] " + ("≈ " if r.get("text_confidence") == "approximate" else "") + r["text"])
    return "\n".join(lines) + (f"\n(+{unreadable} unreadable rows)" if unreadable else "")


def timed_sources(segments, rows):
    """(speech_at, screen_at) for number_check: [(from_s, to_s, text)] of speech segments and final OCR rows."""
    return (
        [(x["start"], x["end"], x["text"]) for x in segments],
        [(r["first"], r["last"], fix_ocr_digits(r["text"])) for r in rows],
    )


def write_archives(id_, common, root, corpus="", lang=None):

    directory = Path(root) / "archive"
    directory.mkdir(parents=True, exist_ok=True)
    from vjournalist.bridge import lang as L
    from vjournalist.bridge.coverage import final_screen, values

    tr = common["transcript"]
    lang = lang or L.language(tr)
    kept, counts = final_screen(common, corpus)
    # same inputs and semantics as the card's number_check: final OCR rows, digits repaired, same time windows
    speech_at, screen_at = timed_sources(tr["segments"], kept)
    check = number_statuses(
        " ".join(s["text"] for s in tr["segments"]),
        [fix_ocr_digits(r["text"]) for r in kept],
        values(corpus),
        speech_at,
        screen_at,
    )
    asr = (
        "platform_captions"
        if tr.get("engine") == "platform_captions"
        else f"{tr.get('engine', 'unknown')} {tr.get('model', 'unknown')}"
    )
    archive = render_archive(
        id_, tr, build_blocks(tr["segments"]), common["metadata"]["duration_s"], asr, check
    )
    (directory / f"{id_}.tx.md").write_text(archive, encoding="utf-8")
    lines = [
        f"# Screen: {id_}",
        "",
        L.say(lang, "screen_legend"),
        L.say(
            lang,
            "screen_filtered",
            damaged=counts["damaged"],
            axis=counts["axis"],
            noise=counts.get("noise", 0),
            merged=counts["merged_variants"],
        ),
        "",
    ]
    for r in kept:
        lines.append(f"[{r['first']:.3f}–{r['last']:.3f}s] " + ("≈ " if r["uncertain"] else "") + r["text"])
    (directory / f"{id_}.screen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return archive


def chapters(id_, transcript, duration, config, root, llm=True):
    """One small, receipted call for >5 minutes; timestamps validated locally.

    `llm=False` (rebuild): only a stored receipt is used; without one nothing is written and nothing is called."""
    if duration <= 300:
        return None
    if not llm and not (config.data / "chapters" / id_ / "response.json").exists():
        return None
    from vjournalist.llm import _run_content
    from vjournalist.storage import atomic_json

    target = Path(root) / "archive" / f"{id_}.chapters.md"
    receipt = config.data / "chapters" / id_
    receipt.mkdir(parents=True, exist_ok=True)
    response_path = receipt / "response.json"
    if response_path.exists():
        response = json.loads(response_path.read_text())
    else:
        marker = receipt / "started.json"
        if marker.exists():
            raise RuntimeError("Chapter call interrupted; refusing an automatic repeat")
        atomic_json(marker, {"id": id_})
        text = "\n".join(block_line(b) for b in build_blocks(transcript["segments"]))
        message = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        response = _run_content(
            message,
            "Return only chapter lines [mm:ss] title. One chapter every 2-3 minutes; use source times. "
            "Write titles in the language of the transcript; never translate. No other text.",
            config,
            receipt,
            effort="low",
        )
        atomic_json(response_path, response)
    text = response["result"].strip()
    times = []
    for line in text.splitlines():
        m = re.fullmatch(r"\[(\d+):(\d{2})\] .+", line)
        if not m:
            raise ValueError("Invalid chapter format")
        times.append(int(m[1]) * 60 + int(m[2]))
    if not times or times != sorted(set(times)) or times[-1] >= duration:
        raise ValueError("Invalid chapter times")
    if any(not 120 <= b - a <= 180 for a, b in zip(times, times[1:])):
        # a guideline for the model, not a defect of the result: the chapters are still real source times
        warnings.warn(f"{id_}: chapter spacing outside 2-3 minutes", stacklevel=2)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text + "\n", encoding="utf-8")
    return target
