"""Local evidence for the Read role: transcript, OCR lines and at most six data frames."""

from vjournalist.pipeline.content_scan import extract_frame
from vjournalist.pipeline.knowledge_text import counter_hints, data_candidates

SCHEMA_VERSION = 6


def build_payload(common, video, work):
    candidates = data_candidates(common)
    # Uniform selection avoids spending the image budget on nearly identical opening frames.
    n = min(6, len(candidates))
    selected = [candidates[round(i * (len(candidates) - 1) / (n - 1)) if n > 1 else 0] for i in range(n)]
    screen = [
        r
        for r in common["scan"]["screen_text"]
        if r["timestamp_s"] < common["platform_info"]["content_duration_s"]
    ]
    # sampled frames may be gone when work/ was cleaned: they are cheap to re-extract
    for frame in selected:
        if not (work / frame["file"]).exists():
            extract_frame(video, work, frame["timestamp_s"], common["metadata"])
    return {
        "role": "knowledge",
        "schema_version": SCHEMA_VERSION,
        "output_language": str(common["transcript"].get("language") or "unknown"),
        "metadata": {"duration_s": common["metadata"]["duration_s"]},
        "transcript": common["transcript"],
        "ocr": [{k: r[k] for k in ("id", "timestamp_s", "text", "text_confidence")} for r in screen],
        "counter_hints": counter_hints(common),
        "data_images": [
            {
                "id": i + 1,
                "timestamp_s": f["timestamp_s"],
                "kind": f["kind"],
                "reason": "low OCR confidence",
            }
            for i, f in enumerate(selected)
        ],
        "images": [str((work / f["file"]).resolve()) for f in selected],
    }
