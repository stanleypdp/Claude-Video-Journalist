"""Cheap local measurements. Music detection is explicitly heuristic, never ground truth."""

import math
import re
import subprocess
import wave

import numpy as np


def beat_estimate(samples, rate):
    """Onset spectral flux + FFT autocorrelation, 60–200 BPM; no periodicity => unknown."""
    frame, hop = 1024, 256
    if len(samples) < rate * 4 or np.max(np.abs(samples)) < 0.001:
        return "unknown", 0.0, 0.0
    windows = np.lib.stride_tricks.sliding_window_view(samples, frame)[::hop]
    flux_parts, previous, tonal, active_count = [], None, 0, 0
    window = np.hanning(frame)
    for offset in range(0, len(windows), 256):
        batch = windows[offset : offset + 256]
        spectrum = np.abs(np.fft.rfft(batch * window, axis=1))
        flatness = np.exp(np.mean(np.log(spectrum + 1e-8), axis=1)) / (spectrum.mean(axis=1) + 1e-8)
        active = np.mean(batch * batch, axis=1) > 1e-6
        tonal += int(np.sum((flatness < 0.25) & active))
        active_count += int(np.sum(active))
        joined = np.vstack([previous, spectrum]) if previous is not None else spectrum
        flux_parts.append(np.maximum(np.diff(joined, axis=0), 0).mean(axis=1))
        previous = spectrum[-1:]
    flux = np.concatenate(flux_parts)
    flux = np.maximum(flux - np.median(flux), 0)
    if np.max(flux) <= 1e-8:
        return "unknown", 0.0, 0.0
    centered = flux - flux.mean()
    size = 1 << (2 * len(centered) - 1).bit_length()
    transform = np.fft.rfft(centered, size)
    correlation = np.fft.irfft(transform * transform.conj(), size)[: len(centered)]
    correlation /= np.maximum(np.arange(len(centered), 0, -1), 1)
    low, high = math.ceil(60 * rate / hop / 200), math.floor(60 * rate / hop / 60)
    if high >= len(correlation) or correlation[0] <= 1e-10:
        return "unknown", 0.0, 0.0
    lag = low + int(np.argmax(correlation[low : high + 1]))
    confidence = float(np.clip(correlation[lag] / correlation[0], 0, 1))
    tonal_share = tonal / max(1, active_count)
    bpm = round(60 * rate / hop / lag, 1) if confidence >= 0.2 else "unknown"
    return bpm, round(confidence, 3), tonal_share


def measure_audio(work, metadata, transcript=None, content_duration=None):
    duration = min(
        metadata["duration_s"], content_duration if content_duration is not None else metadata["duration_s"]
    )
    if not metadata["has_audio"]:
        return {
            "audio_evidence": "measured",
            "audio_ready": False,
            "window_start_s": 0,
            "window_end_s": duration,
            "rms_dbfs": -240,
            "peak_dbfs": -240,
            "clipping_percent": 0,
            "flux_mean": 0,
            "flux_p95": 0,
            "speech_words_per_minute": 0,
            "method": "No audio stream",
            "bpm": "unknown",
            "beat_confidence": 0,
            "speech_percent": 0.0,
            "music_percent_estimate": 0.0,
            "silence_s": duration,
            "silence_percent": 100.0,
            "unknown_sound_percent": 0.0,
            "notes": ["No audio stream; no sound in the whole material."],
        }
    audio = work / "audio.wav"
    with wave.open(str(audio), "rb") as wav:
        rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768
    samples = samples[: round(duration * rate)]
    if rate != 16000:
        raise ValueError("Audio metrics require mono 16 kHz WAV")
    actual_duration = min(duration, len(samples) / rate)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-i",
            str(audio),
            "-t",
            str(duration),
            "-af",
            "silencedetect=noise=-40dB:d=0.25",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError("ffmpeg silencedetect failed.")
    # A 10 ms timeline makes speech/music/silence exclusive and prevents double-counting.
    hop_s = 0.01
    timeline = np.zeros(max(1, math.ceil(duration / hop_s)), dtype=np.uint8)
    pending = None
    for match in re.finditer(r"silence_(start|end):\s*([0-9.]+)", proc.stderr):
        kind, value = match.group(1), float(match.group(2))
        if kind == "start":
            pending = value
        elif pending is not None:
            timeline[int(pending / hop_s) : min(len(timeline), math.ceil(value / hop_s))] = 1
            pending = None
    if pending is not None:
        timeline[int(pending / hop_s) :] = 1
    timeline[math.ceil(actual_duration / hop_s) :] = 1
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    speech = get_speech_timestamps(
        samples,
        VadOptions(min_speech_duration_ms=150, min_silence_duration_ms=150, speech_pad_ms=0),
        sampling_rate=rate,
    )
    speech_mask = np.zeros_like(timeline, dtype=bool)
    for segment in speech:
        speech_mask[int(segment["start"] / rate / hop_s) : math.ceil(segment["end"] / rate / hop_s)] = True
    timeline[speech_mask & (timeline != 1)] = 2
    bpm, confidence, tonal_share = beat_estimate(samples, rate)
    # Residual activity is only called music-like when sustained tonality AND periodicity exist.
    # Speech with background music is counted as speech; stems are not separated.
    if bpm != "unknown" and confidence >= 0.2 and tonal_share >= 0.5:
        timeline[timeline == 0] = 3

    def share(key):
        return round(float(np.mean(timeline == key)) * 100, 2)

    rms = float(np.sqrt(np.mean(samples**2))) if len(samples) else 0
    peak = float(np.max(np.abs(samples))) if len(samples) else 0
    n = len(samples) // 512
    if n > 1:
        spectra = np.abs(np.fft.rfft(samples[: n * 512].reshape(n, 512) * np.hanning(512), axis=1))
        flux = np.maximum(np.diff(spectra, axis=0), 0).mean(axis=1)
    else:
        flux = np.array([0.0])
    segments = (transcript or {}).get("segments", [])
    words = sum(
        len(s["text"].split())
        * max(0, min(s["end"], duration) - max(0, s["start"]))
        / max(0.001, s["end"] - s["start"])
        for s in segments
        if s["start"] < duration
    )
    return {
        "audio_evidence": "measured",
        "audio_ready": False,
        "window_start_s": 0,
        "window_end_s": duration,
        "rms_dbfs": round(20 * math.log10(max(rms, 1e-12)), 3),
        "peak_dbfs": round(20 * math.log10(max(peak, 1e-12)), 3),
        "clipping_percent": round(float(np.mean(np.abs(samples) >= 32767 / 32768)) * 100, 6),
        "flux_mean": round(float(flux.mean()), 6),
        "flux_p95": round(float(np.percentile(flux, 95)), 6),
        "speech_words_per_minute": round(words / max(duration, 0.001) * 60, 2),
        "method": "ffmpeg silencedetect -40dB/0.25s + Silero VAD + NumPy spectral-flux autocorrelation",
        "bpm": bpm,
        "beat_confidence": confidence,
        "speech_percent": share(2),
        "music_percent_estimate": share(3),
        "silence_percent": share(1),
        "silence_s": round(np.mean(timeline == 1) * duration, 3),
        "unknown_sound_percent": share(0),
        "notes": [
            "Proportions are a local estimate, not track separation. Speech over background music counts as speech.",
            "Music means rhythmic/tonal sound without detected speech; it can be confused with SFX or speech rhythm.",
            "BPM can describe the rhythm of speech or be a multiple/division of the tempo; unknown when periodicity is weak.",
        ],
    }
