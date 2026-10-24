"""Whole-scene sampling: keep start/end together and never silently infer omitted scenes."""

import math

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat

from vjournalist.storage import run


def sampling_plan(scenes, metadata, config):
    groups = []
    for scene in scenes:
        start, end = scene["start"], scene["end"]
        duration = end - start
        pad = min(0.2, duration / 4)
        middle_count = 3 if duration > 8 else 2 if duration > 5 else 1 if duration > 3 else 0
        group = [{"scene": scene["number"], "role": "start", "time": start + pad}]
        group += [
            {
                "scene": scene["number"],
                "role": f"mid-{i + 1}",
                "time": start + duration * (i + 1) / (middle_count + 1),
            }
            for i in range(middle_count)
        ]
        group.append({"scene": scene["number"], "role": "end", "time": end - pad})
        groups.append(group)
    capacity = min(config.frame_limit, 4 * config.sheet_frames)
    budget = capacity - 1  # separate hook at 0.3 s
    selected = []
    for count in range(min(len(scenes), budget // 2), 0, -1):
        indices = sorted({round(i * (len(scenes) - 1) / max(1, count - 1)) for i in range(count)})
        if sum(len(groups[i]) for i in indices) <= budget:
            selected = indices
            break
    if not selected:
        # Very low custom cap: retain at least one complete start/end pair.
        selected = [0]
        groups[0] = [groups[0][0], *groups[0][1:-1][: max(0, budget - 2)], groups[0][-1]]
    samples = [{"scene": "hook", "role": "hook", "time": min(0.3, metadata["duration_s"] / 2)}]
    samples += [frame for i in selected for frame in groups[i]]
    last_time = max(0, metadata["duration_s"] - 1 / (metadata.get("fps") or 25))
    for sample in samples:
        sample["time"] = min(sample["time"], last_time)
    return samples, [scenes[i]["number"] for i in selected]


def make_sheets(video, work, metadata, scene_data, config):
    directory = work / "sheets"
    directory.mkdir(exist_ok=True)
    samples, selected = sampling_plan(scene_data["scenes"], metadata, config)
    entries, pairs = [], {}
    width, height = 360, 676
    font = ImageFont.load_default(size=18)
    for offset in range(0, len(samples), config.sheet_frames):
        group = samples[offset : offset + config.sheet_frames]
        sheet = Image.new("RGB", (width * 3, height * math.ceil(len(group) / 3)), "#171717")
        draw = ImageDraw.Draw(sheet)
        for slot, sample in enumerate(group):
            frame = work / "frame-tmp.png"
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
                    f"{sample['time']:.4f}",
                    "-i",
                    video,
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=360:-2",
                    "-threads",
                    "2",
                    frame,
                ]
            )
            if not frame.exists():
                raise RuntimeError("ffmpeg did not extract the frame.")
            with Image.open(frame) as source:
                fitted = ImageOps.contain(source.convert("RGB"), (width, height - 36))
                x, y = slot % 3 * width, slot // 3 * height
                sheet.paste(fitted, (x + (width - fitted.width) // 2, y + 36))
                draw.text(
                    (x + 6, y + 7),
                    f"S{sample['scene']} {sample['role']} | {sample['time']:.2f}s",
                    font=font,
                    fill="white",
                )
                if sample["role"] in ("start", "end"):
                    pairs.setdefault(sample["scene"], {})[sample["role"]] = (
                        source.convert("L").resize((90, 160)),
                        sample["time"],
                    )
            if config.ocr:
                frame.rename(directory / f"ocr-{offset + slot}.png")
            frame.unlink(missing_ok=True)
        filename = f"sheets/sheet-{offset // config.sheet_frames + 1}.jpg"
        sheet.save(work / filename, quality=88)
        entries.append({"file": filename, "samples": group})
    evidence = []
    for number in selected:
        start, st = pairs[number]["start"]
        end, et = pairs[number]["end"]
        difference = round(ImageStat.Stat(ImageChops.difference(start, end)).mean[0] / 255, 4)
        distinct = et - st >= 1 / (metadata.get("fps") or 25)
        evidence.append(
            {
                "scene": number,
                "start_time": st,
                "end_time": et,
                "pixel_difference": difference,
                "distinct_pair": distinct,
                "note": "Pixel difference is only an eligibility gate, not proof of camera motion.",
            }
        )
    return {
        "sheets": entries,
        "frame_count": len(samples),
        "frame_limit": config.frame_limit,
        "sampled_scene_numbers": selected,
        "unsampled_scene_numbers": [s["number"] for s in scene_data["scenes"] if s["number"] not in selected],
        "scene_evidence": evidence,
        "note": "Start/end samples support cautious change inference, not continuous motion/transition proof. "
        "Times are requested seek positions. Groups are sampled evenly if the frame budget is exceeded.",
    }
