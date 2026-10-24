"""`vjournalist read <folder|file|URL>`: Read for every video; resumable, cache by SHA-256."""

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

from vjournalist.llm import LLMRateLimit
from vjournalist.storage import atomic_json, read_json, sha256, slug

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
VERSION = 6
DEFAULT_POLL_S = 900


def default_output(source, title=None):
    """Where `read` writes INDEX.md, articles/, cards/, archive/.

    Folder: <parent>/OUTPUT/<folder name>. A single file or a URL: ./OUTPUT/<file stem or title>.
    """
    path = Path(source).expanduser()
    if path.is_dir() or (not path.is_file() and path.suffix.lower() not in VIDEO_EXT):
        path = path.resolve()
        return path.parent / "OUTPUT" / path.name
    return Path.cwd() / "OUTPUT" / (slug(title or path.stem) or "video")


def cache_dir(config, digest):
    return config.data / "cache" / digest / "roles" / "knowledge" / f"v{VERSION}"


def historical_cost(config, digest):
    path = cache_dir(config, digest) / "analysis.json"
    return sum((u.get("cost_usd") or 0) for u in read_json(path).get("usage", []))


def outputs_exist(config, digest):
    provenance = config.data / "cache" / digest / "provenance.json"
    if not provenance.exists():
        return False
    bridge = config.bridge or config.data.parent / "OUTPUT"
    name = f"{slug(read_json(provenance)['name'])}-{digest[:12]}.md"
    return (bridge / "articles" / name).exists()


def bridge_id(config, digest):
    provenance = config.data / "cache" / digest / "provenance.json"
    return f"{slug(read_json(provenance)['name'])}-{digest[:12]}" if provenance.exists() else None


def token_metrics(config, rows):
    """Review metrics over the results of this run (cards present in the bridge); None without any."""
    from collections import Counter

    from vjournalist.bridge.tokens import metrics, token_rows

    bridge = config.bridge or config.data.parent / "OUTPUT"
    total, cards = Counter(), 0
    for row in rows:
        id_ = bridge_id(config, row["sha256"]) if row.get("status") in ("analyzed", "cache") else None
        try:
            found, _ = token_rows(bridge, id_) if id_ else ([], None)
        except (OSError, KeyError, ValueError, TypeError):
            continue
        if found:
            total.update(metrics(found))
            cards += 1
    return {"cards": cards, **total} if cards else None


def read_metrics(config, rows):
    """The three Read quality metrics over the results of this run (see vjournalist.bridge.quality); None without any."""
    from collections import Counter

    from vjournalist.bridge.quality import measure, rates

    bridge = config.bridge or config.data.parent / "OUTPUT"
    total = Counter()
    for row in rows:
        id_ = bridge_id(config, row["sha256"]) if row.get("status") in ("analyzed", "cache") else None
        try:
            total.update(measure(bridge, [id_]) if id_ else {})
        except (OSError, KeyError, ValueError, TypeError, IndexError):
            continue
    return rates(total) if total["cards"] else None


def list_videos(folder, recursive=False):
    pattern = "**/*" if recursive else "*"
    return sorted(p for p in Path(folder).glob(pattern) if p.is_file() and p.suffix.lower() in VIDEO_EXT)


def read_folder(
    folder,
    config,
    *,
    analyze,
    recursive=False,
    dry_run=False,
    wait=True,
    poll_s=DEFAULT_POLL_S,
    max_wait_s=6 * 3600,
    sleep=time.sleep,
    log=print,
    files=None,
    captions=None,
):
    """Sequential Read; rows: cache | analyzed | duplicate | error | pending.

    `files` replaces the folder scan (a single file or a downloaded URL); `captions` maps a path to
    the uploader's caption file, used instead of ASR.

    Processed files are skipped by SHA-256 (cache for knowledge/v6). On a Claude CLI limit the run
    pauses and resumes the same file (the rejected call left no answer), or stops with `pending`
    when waiting is disabled/exhausted; rerunning the command continues from the cache.
    """
    folder = Path(folder).resolve()
    files = list(files) if files is not None else list_videos(folder, recursive)
    state = config.data / "read-batch" / f"{hashlib.sha256(str(folder).encode()).hexdigest()[:12]}.json"
    report = {
        "folder": str(folder),
        "started": datetime.now(UTC).isoformat(),
        "files": len(files),
        "rows": [],
        "paused_s": 0,
    }
    seen = {}
    waited = 0
    stopped = False
    for path in files:
        row = {"file": path.name}
        report["rows"].append(row)
        if stopped:
            row["status"] = "pending"
            continue
        digest = row["sha256"] = sha256(path)
        if digest in seen:
            row.update(status="duplicate", same_as=seen[digest])
            continue
        seen[digest] = path.name
        cached = (cache_dir(config, digest) / "analysis.json").exists()
        if dry_run:
            row["status"] = "cache" if cached else "pending"
            continue
        if cached and outputs_exist(config, digest):
            row.update(status="cache", cost_usd=0, historical_cost_usd=historical_cost(config, digest))
            continue
        while True:
            try:
                result = analyze(
                    str(path), "knowledge", config=config, **({"captions": captions[path]} if captions and path in captions else {})
                )
            except LLMRateLimit as exc:
                delay = min(max(exc.reset_in_s or poll_s, 60), poll_s * 4)
                atomic_json(
                    state,
                    {
                        "paused": True,
                        "file": path.name,
                        "reason": str(exc),
                        "retry_in_s": delay,
                        "at": datetime.now(UTC).isoformat(),
                    },
                )
                if not wait or waited + delay > max_wait_s:
                    row.update(
                        status="pending", note="Claude CLI limit; run the command again after the limit resets"
                    )
                    stopped = True
                    break
                log(f"Claude CLI limit. Pausing {delay} s, then resuming: {path.name}")
                sleep(delay)
                waited += delay
                continue
            except Exception as exc:
                row.update(status="error", error=str(exc)[:300])
                break
            if result.get("cache") == "HIT":
                row.update(
                    status="cache",
                    cost_usd=0,
                    historical_cost_usd=historical_cost(config, digest),
                    rendered_from_cache=True,
                )
            else:
                row.update(
                    status="analyzed",
                    cost_usd=round(
                        (result.get("cost_usd_first_call") or 0) + (result.get("cost_usd_retries") or 0), 6
                    ),
                    llm_invocations=result.get("llm_invocations"),
                )
            break
    report["paused_s"] = waited
    rows = report["rows"]
    count = lambda status: sum(r["status"] == status for r in rows)  # noqa: E731
    report["summary"] = {
        "files": len(files),
        "analyzed": count("analyzed"),
        "cache": count("cache"),
        "duplicates": count("duplicate"),
        "errors": count("error"),
        "pending": count("pending"),
        "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 6),
        "historical_cost_usd_cache": round(sum(r.get("historical_cost_usd") or 0 for r in rows), 6),
    }
    if not dry_run:
        report["token_metrics"] = token_metrics(config, rows)
        report["read_metrics"] = read_metrics(config, rows)
    report["finished"] = datetime.now(UTC).isoformat()
    if not dry_run:
        path = config.data / "reports" / f"read-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.json"
        atomic_json(path, report)
        report["report_file"] = str(path)
        if not report["summary"]["pending"] and state.exists():
            state.unlink()
    return report


def format_report(report):
    s = report["summary"]
    lines = [
        f"Folder: {report['folder']}",
        f"Files: {s['files']} | analyzed: {s['analyzed']} | from cache (SHA-256): {s['cache']} | "
        f"duplicates: {s['duplicates']} | errors: {s['errors']} | pending: {s['pending']}",
        f"Cost of this run: {s['cost_usd']:.4f} USD (historical cost of cache hits: "
        f"{s['historical_cost_usd_cache']:.4f} USD); pauses: {report['paused_s']} s",
    ]
    for r in report["rows"]:
        extra = r.get("error") or r.get("note") or r.get("same_as") or ""
        cost = r.get("cost_usd", r.get("historical_cost_usd"))
        lines.append(
            f"  {r['status']:9} {r['file']}"
            + (f"  {cost:.4f} USD" if cost is not None else "")
            + (f"  {extra}" if extra else "")
        )
    m = report.get("token_metrics")
    if m:
        share = lambda a, b: f"{a}/{b} ({100 * a / b:.0f}%)" if b else "0/0"  # noqa: E731
        lines += [
            f"OCR tokens in {m['cards']} cards (token table, quoted rows):",
            f"  without a literal token in the quote: numbers {share(m.get('number_not_literal', 0), m.get('number_rows', 0))}, "
            f"phrases {share(m.get('phrase_not_literal', 0), m.get('phrase_rows', 0))}",
            "  ok numbers matched inside a time/date pattern: "
            + share(m.get("ok_numbers_in_time_date", 0), m.get("ok_numbers", 0)),
            '  "on screen" phrases without a row: '
            + share(m.get("screen_phrases_without_row", 0), m.get("screen_phrases", 0)),
        ]
    r = report.get("read_metrics")
    if r:
        lines += [
            f"Read metrics in {r['cards']} cards:",
            f"  false_rejection_rate: {100 * r['false_rejection_rate']:.1f}% "
            f"({r['false_rejections']}/{r['rejections']} rejections; target < 3%)",
            f"  screen_attribution_ok: {100 * r['screen_attribution_ok']:.1f}% "
            f"({r['screen_phrases_ok']}/{r['screen_phrases']} on-screen quotes; target 100%)",
            f"  not_in_ocr_per_card: {r['not_in_ocr_per_card']:.2f} ({r['not_in_ocr']} [not in OCR] markers)",
        ]
    if report.get("report_file"):
        lines.append("Report: " + report["report_file"])
    return "\n".join(lines)
