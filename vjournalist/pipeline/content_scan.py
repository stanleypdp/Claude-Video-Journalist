"""Shared, local OCR/content-change scan. No LLM and no role-specific interpretation."""

import re
from collections import Counter

import numpy as np
from PIL import Image, ImageChops, ImageStat

from vjournalist.storage import run

FRAME_RETRIES = 12  # 12 steps of FRAME_STEP_S: look back at most ~0.5 s from the requested time
FRAME_STEP_S = 0.04


def extract_frame(video, work, time_s, metadata, width=720):
    fps = metadata.get("fps") or 25
    time_s = min(max(0, time_s), max(0, metadata["duration_s"] - 1 / fps))
    path = work / "frames" / f"w{width}" / f"{round(time_s * 1000):09d}.jpg"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # The container can outlast the video stream (longer audio track): a seek past the last frame
        # yields no frame. Depending on the ffmpeg build it exits with 234 or exits 0 and writes nothing.
        # Step back until a frame is decoded, for at most FRAME_RETRIES * FRAME_STEP_S seconds.
        for back in range(FRAME_RETRIES + 1):
            at = max(0, time_s - back * FRAME_STEP_S)
            try:
                run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-nostdin",
                        "-y",
                        "-threads",
                        "2",
                        "-ss",
                        f"{at:.4f}",
                        "-i",
                        video,
                        "-frames:v",
                        "1",
                        "-vf",
                        f"scale={width}:-2",
                        "-threads",
                        "2",
                        path,
                    ]
                )
                if path.exists() and path.stat().st_size > 0:
                    break
                path.unlink(missing_ok=True)
            except RuntimeError:
                path.unlink(missing_ok=True)
            if back == FRAME_RETRIES or at == 0:
                break
    if not path.exists():
        raise RuntimeError("No frame could be extracted during the local scan.")
    return path


def text_kind(text):
    chart = bool(
        re.search(
            r"\b(poc|nasdaq|value area|random level|price|axis|profit|trades|chart|percent)\b|\d+[.,]\d+\s*%",
            text,
            re.I,
        )
    )
    code = bool(re.search(r"\b(npm|npx|function|const|import|return|git clone)\b|/[a-z]+-[a-z]+", text, re.I))
    table = bool(re.search(r"\b(summary|table|results|size|filename)\b", text, re.I))
    return "chart" if chart else "code" if code else "table" if table else "text"


def scan_content(video, work, metadata, scenes, engine=None):
    if engine is None:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR(intra_op_num_threads=6, inter_op_num_threads=1, print_verbose=False)
    duration = metadata["duration_s"]
    times = {0.2, max(0, duration - 0.2)}
    times.update(float(t) for t in np.arange(0.3, duration, 2.5))
    times.update(float(t) for t in np.arange(max(0, duration - 5.5), duration, 0.5))
    for scene in scenes:
        pad = min(0.2, (scene["end"] - scene["start"]) / 4)
        times.update((scene["start"] + pad, scene["end"] - pad))
    records, frames, by_text = [], [], {}
    previous = None
    previous_items = []
    for time_s in sorted(
        {round(min(t, max(0, duration - 1 / (metadata.get("fps") or 25))), 3) for t in times}
    ):
        path = extract_frame(video, work, time_s, metadata)
        with Image.open(path) as im:
            gray = im.convert("L").resize((90, 160))
            w, h = im.size
            diff = (
                ImageStat.Stat(ImageChops.difference(gray, previous)).mean[0] / 255
                if previous is not None
                else 1.0
            )
            brightness = ImageStat.Stat(gray).mean[0] / 255
        if previous is not None and diff < 0.0001:
            items = previous_items
        else:
            result, _ = engine(str(path))
            items = [
                {
                    "text": str(item[1]).strip(),
                    "score": float(item[2]),
                    "box": [[round(float(x) / w, 4), round(float(y) / h, 4)] for x, y in item[0]],
                }
                for item in (result or [])
                if str(item[1]).strip()
            ]
        previous, previous_items = gray, items
        joined = " ".join(item["text"] for item in items)
        kind = text_kind(joined)
        weak = [item for item in items if item["score"] < 0.95]
        # Only data-bearing frames with uncertain OCR may be sent to KNOWLEDGE.
        needs_image = kind in ("chart", "code", "table") and (
            not items or len(weak) >= max(1, len(items) * 0.15)
        )
        for item in items:
            normalized = " ".join(item["text"].casefold().split())
            if normalized not in by_text:
                confidence = (
                    "exact"
                    if item["score"] >= 0.96
                    else "approximate"
                    if item["score"] >= 0.5
                    else "unreadable"
                )
                by_text[normalized] = len(records)
                records.append(
                    {
                        "id": len(records) + 1,
                        "timestamp_s": time_s,
                        "last_seen_s": time_s,
                        "text": item["text"] if confidence != "unreadable" else "unknown",
                        "text_confidence": confidence,
                        "ocr_score": round(item["score"], 4),
                    }
                )
            else:
                records[by_text[normalized]]["last_seen_s"] = time_s
        frames.append(
            {
                "timestamp_s": time_s,
                "file": str(path.relative_to(work)),
                "difference": round(diff, 5),
                "brightness": round(brightness, 5),
                "kind": kind,
                "needs_data_image": needs_image,
                "items": items,
            }
        )
    return {
        "version": 3,
        "interval_s": 2.5,
        "frame_count": len(frames),
        "frames": frames,
        "screen_text": records,
    }


def platform_info(metadata, scenes, scan):
    """A centered terminal logo/account is different from a corner watermark on content."""
    duration = metadata["duration_s"]
    terminals = []
    accounts = []
    brand = "unknown"
    for frame in scan["frames"]:
        items = frame["items"]
        centered_brand = False
        centered_account = False
        has_brand = any(
            "tiktok" in re.sub(r"\s+", "", i["text"]).lower() or "instagram" in i["text"].lower()
            for i in items
        )
        for item in items:
            text = item["text"]
            box = item["box"]
            x = sum(point[0] for point in box) / len(box)
            y = sum(point[1] for point in box) / len(box)
            centered = 0.2 < x < 0.8 and 0.15 < y < 0.8
            # TikTok search endcards often display a known handle without '@'.
            if (
                centered
                and item["score"] >= 0.96
                and text.strip().lstrip("@") in {a.lstrip("@") for a in accounts}
            ):
                centered_account = True
            if centered and ("tiktok" in re.sub(r"\s+", "", text).lower() or "instagram" in text.lower()):
                centered_brand = True
                brand = "tiktok" if "tik" in text.lower() else "instagram"
            account = re.search(r"(?<!\w)@[a-zA-Z0-9_][a-zA-Z0-9_.]{1,45}", text)
            if account and has_brand:
                centered_account |= centered
                if (
                    item["score"] >= 0.96
                    and not re.search(r"\.\.\.|…", text)
                    and not account.group().endswith(".")
                ):
                    accounts.append(account.group())
        if frame["timestamp_s"] >= duration - 5 and centered_brand and centered_account:
            terminals.append(frame["timestamp_s"])
    artifact_start = None
    if terminals:
        first = min(terminals)
        scene = next((s for s in scenes if s["start"] <= first < s["end"]), None)
        artifact_start = scene["start"] if scene and scene["start"] >= duration - 5 else first
        previous = next((s for s in scenes if abs(s["end"] - artifact_start) < 0.01), None)
        if previous and previous["duration_s"] <= 0.6:
            frames = [f for f in scan["frames"] if previous["start"] <= f["timestamp_s"] < previous["end"]]
            if frames and all(f["brightness"] < 0.04 for f in frames):
                artifact_start = previous["start"]
    if artifact_start is not None and duration - artifact_start > 5:
        artifact_start = None
    content_duration = artifact_start if artifact_start is not None else duration
    account = Counter(accounts).most_common(1)[0][0] if accounts else "unknown"
    annotated = []
    for scene in scenes:
        if artifact_start is not None and scene["start"] < artifact_start < scene["end"] - 0.01:
            annotated.extend(
                [
                    {
                        **scene,
                        "end": artifact_start,
                        "duration_s": round(artifact_start - scene["start"], 4),
                        "platform_artifact": False,
                    },
                    {
                        **scene,
                        "start": artifact_start,
                        "duration_s": round(scene["end"] - artifact_start, 4),
                        "platform_artifact": True,
                    },
                ]
            )
        else:
            annotated.append(
                {
                    **scene,
                    "platform_artifact": artifact_start is not None
                    and scene["start"] >= artifact_start - 0.001,
                }
            )
    for i, scene in enumerate(annotated):
        scene["number"] = i + 1
    content = [s for s in annotated if not s["platform_artifact"]]
    return {
        "platform": brand,
        "source_account": account,
        "source_account_confidence": "exact" if account != "unknown" else "unreadable",
        "artifact_start_s": artifact_start,
        "content_duration_s": round(content_duration, 4),
        "scenes": annotated,
        "cuts_per_second": round(max(0, len(content) - 1) / content_duration, 4) if content_duration else 0,
        "detection": "local OCR: centered platform logo + account in terminal <=5s; optional preceding black frame",
    }
