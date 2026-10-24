"""Frame-difference measurement that separates hard cuts from smooth motion with periodic peaks."""

import subprocess
from statistics import median

import numpy as np

W, H, FPS = 64, 114, 30


def diff_series(video, end):
    """Mean absolute grayscale difference between consecutive frames (0..1), one value per frame."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-t", str(end), "-i", str(video), "-vf", f"fps={FPS},scale={W}:{H},format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True,
        check=True,
    ).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, H, W).astype(np.float32) / 255
    d = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    return [(round((i + 1) / FPS, 4), float(v)) for i, v in enumerate(d)]


def peaks(series, level, gap):
    out = []
    for i in range(1, len(series) - 1):
        t, v = series[i]
        if v >= level and v >= series[i - 1][1] and v > series[i + 1][1] and (not out or t - out[-1][0] >= gap):
            out.append((t, v))
    return out


MOTION_FLOOR = 0.02
MIN_MOTION_RATIO = 0.5
SOFT_CUT_MAX = 0.2
MIN_RUN = 3
CANDIDATE_LEVEL = 0.14
CANDIDATE_GAP = 0.5


def review_cuts(series, scenes):
    """Demote detector cuts inside runs of continuous low-contrast motion to unconfirmed candidates.

    A run is >=3 consecutive scenes whose frames move almost everywhere (ratio of frames above the
    motion floor) while the difference at each boundary stays weak. Peaks inside it are candidates
    for the user to confirm, never counted as cuts.
    """
    times = np.array([t for t, _ in series])
    values = np.array([v for _, v in series])
    rows = []
    for s in scenes:
        inside = values[(times > s["start"]) & (times <= s["end"])]
        near = values[(times >= s["start"] - 0.07) & (times <= s["start"] + 0.07)]
        rows.append(
            {
                "scene": s,
                "motion_ratio": float((inside > MOTION_FLOOR).mean()) if len(inside) else 0.0,
                "cut_diff": float(near.max()) if len(near) else 0.0,
            }
        )
    runs, current = [], []
    for row in rows + [None]:
        smooth = (
            row is not None
            and not row["scene"]["platform_artifact"]
            and row["motion_ratio"] >= MIN_MOTION_RATIO
            and row["cut_diff"] < SOFT_CUT_MAX
        )
        if smooth:
            current.append(row)
            continue
        if len(current) >= MIN_RUN:
            runs.append(current)
        current = []
    merged = []
    demoted = set()
    for run in runs:
        start, end = run[0]["scene"]["start"], run[-1]["scene"]["end"]
        cuts = [r["scene"]["start"] for r in run[1:]]
        demoted.update(cuts)
        found = [(t, v) for t, v in peaks(series, CANDIDATE_LEVEL, CANDIDATE_GAP) if start < t < end]
        candidates = {round(t, 3): {"time_s": round(t, 3), "diff": round(v, 3), "source": "frame_difference_peak"} for t, v in found}
        for t in cuts:
            row = candidates.setdefault(round(t, 3), {"time_s": round(t, 3), "source": "detector_cut"})
            row["detector_cut"] = True
        gaps = [b - a for (a, _), (b, _) in zip(found, found[1:])]
        merged.append(
            {
                "start_s": start,
                "end_s": end,
                "scene_numbers": [r["scene"]["number"] for r in run],
                "motion_ratio_min": round(min(r["motion_ratio"] for r in run), 3),
                "boundary_diff_max": round(max(r["cut_diff"] for r in run[1:]), 3),
                "peak_gap_median_s": round(median(gaps), 3) if gaps else None,
                "candidates": sorted(candidates.values(), key=lambda c: c["time_s"]),
                "status": "unconfirmed_candidates_for_user",
            }
        )
    return {
        "method": f"ffmpeg {FPS} fps {W}x{H} gray mean abs frame difference; run = >={MIN_RUN} scenes with "
        f"motion_ratio>={MIN_MOTION_RATIO} (frames >{MOTION_FLOOR}) and boundary diff <{SOFT_CUT_MAX}",
        "merged_runs": merged,
        "demoted_detector_cuts_s": sorted(demoted),
    }


def merge_scenes(scenes, review):
    """Scene list with every demoted run collapsed into one shot (numbers kept from the first scene)."""
    out = []
    for s in scenes:
        run = next((r for r in review["merged_runs"] if r["start_s"] <= s["start"] < r["end_s"]), None)
        if run and s["start"] != run["start_s"]:
            continue
        if run:
            s = {**s, "end": run["end_s"], "duration_s": round(run["end_s"] - run["start_s"], 4), "merged_scenes": run["scene_numbers"]}
        out.append(s)
    return out
