import math
from fractions import Fraction

from vjournalist.pipeline.audio import measure_audio
from vjournalist.storage import atomic_json, read_json, run


def probe(video, config):
    info = __import__("json").loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                video,
            ]
        )
    )
    streams = info.get("streams", [])
    stream = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    if not stream:
        raise ValueError("The file has no supported video stream.")
    duration = float(info.get("format", {}).get("duration") or stream.get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0 or duration > config.max_duration:
        raise ValueError(f"Invalid video duration or limit of {config.max_duration:g} s exceeded.")
    width, height = int(stream["width"]), int(stream["height"])
    rotation = next(
        (s.get("rotation", 0) for s in stream.get("side_data_list", []) if "rotation" in s),
        stream.get("tags", {}).get("rotate", 0),
    )
    if abs(int(float(rotation))) % 180 == 90:
        width, height = height, width
    divisor = math.gcd(width, height)
    try:
        fps = float(Fraction(stream.get("avg_frame_rate", "0/1")))
    except (ValueError, ZeroDivisionError):
        fps = 0
    return {
        "duration_s": duration,
        "width": width,
        "height": height,
        "aspect": f"{width // divisor}:{height // divisor}",
        "fps": fps,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def transcribe(video, work, metadata, config, captions=None):
    if captions:
        from vjournalist.pipeline.captions import transcript_from_captions

        return transcript_from_captions(captions)
    if not metadata["has_audio"]:
        return {"language": "unknown", "segments": [], "audio_kind": "no_audio", "bpm": "unknown"}
    audio = work / "audio.wav"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-threads",
            "2",
            "-i",
            video,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            audio,
        ],
        timeout=600,
    )
    if config.whisper_model.endswith(".en"):
        raise ValueError("ASR requires a multilingual model, not an .en model")
    from faster_whisper import WhisperModel

    model = WhisperModel(
        config.whisper_model,
        device="cpu",
        compute_type="int8",
        cpu_threads=config.whisper_threads,
        num_workers=1,
        download_root=str(config.data / "models"),
    )
    segments, info = model.transcribe(
        str(audio),
        initial_prompt=config.asr_initial_prompt or None,
        word_timestamps=config.word_timestamps,
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
        language=None if config.language == "auto" else config.language,
    )
    result = {
        "engine": "faster-whisper",
        "model": config.whisper_model,
        "language": info.language,
        "language_probability": info.language_probability,
        "segments": [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text.strip(),
                "words": [
                    {"start": w.start, "end": w.end, "word": w.word, "probability": w.probability}
                    for w in (s.words or [])
                ],
                "avg_logprob": s.avg_logprob,
                "no_speech_prob": s.no_speech_prob,
            }
            for s in segments
        ],
        "audio_kind": "unknown",
        "bpm": "unknown",
    }
    return result


def detect_scenes(video, metadata):
    from scenedetect import ContentDetector, detect

    min_frames = max(1, round((metadata.get("fps") or 30) * 0.15))
    detected = detect(
        str(video), ContentDetector(threshold=27, min_scene_len=min_frames), start_in_scene=True
    )
    duration = metadata["duration_s"]
    starts = sorted(
        {0.0, *(round(a.get_seconds(), 4) for a, _ in detected if 0 < a.get_seconds() < duration)}
    )
    scenes = [
        {"number": i + 1, "start": start, "end": end, "duration_s": round(end - start, 4)}
        for i, (start, end) in enumerate(zip(starts, starts[1:] + [duration]))
    ]
    return {
        "scenes": scenes,
        "cuts_per_second": round((len(scenes) - 1) / duration, 4),
        "detector": "ContentDetector",
        "threshold": 27,
        "min_scene_frames": min_frames,
    }


def ocr_frames(work, sheets):
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    output = []
    samples = [s for sheet in sheets["sheets"] for s in sheet["samples"]]
    for index, sample in enumerate(samples):
        result, _ = engine(str(work / "sheets" / f"ocr-{index}.png"))
        output.append(
            {**sample, "text": [{"text": item[1], "confidence": float(item[2])} for item in result or []]}
        )
    return output


def prepare(video, work, config, log, captions=None):
    """Shared SHA checkpoints; role reanalysis never invalidates media artifacts."""
    from vjournalist.pipeline.content_scan import platform_info, scan_content

    reused = []

    def step(name, function):
        path = work / f"{name}.json"
        if path.exists():
            reused.append(name)
            log(name, "checkpoint")
            return read_json(path)
        log(name, "local processing")
        value = function()
        atomic_json(path, value)
        return value

    metadata = step("metadata", lambda: probe(video, config))
    if metadata["duration_s"] > config.max_duration:
        raise ValueError("The video exceeds the duration limit.")
    transcript = step("transcript", lambda: transcribe(video, work, metadata, config, captions))
    if (
        config.word_timestamps
        and not captions
        and metadata["has_audio"]
        and any(not s.get("words") for s in transcript["segments"])
    ):
        transcript = step("transcript-words-v5", lambda: transcribe(video, work, metadata, config))
    audio = step("audio_metrics", lambda: measure_audio(work, metadata))
    scenes = step("scenes", lambda: detect_scenes(video, metadata))
    scan = step("content-scan-v3", lambda: scan_content(video, work, metadata, scenes["scenes"]))
    platform = step("platform-v3", lambda: platform_info(metadata, scenes["scenes"], scan))
    audio = step(
        "audio-content-v5", lambda: measure_audio(work, metadata, transcript, platform["content_duration_s"])
    )
    return {
        "metadata": metadata,
        "transcript": transcript,
        "audio_metrics": audio,
        "scan": scan,
        "platform_info": platform,
        "mechanics_reused": reused,
        "scenes": platform["scenes"],
        "cuts_per_second": platform["cuts_per_second"],
    }
