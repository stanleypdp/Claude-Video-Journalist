import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_settings():
    path = ROOT / "config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.exists() else {}


@dataclass(frozen=True)
class Config:
    data: Path
    model: str
    whisper_model: str
    whisper_threads: int
    language: str
    ocr: bool
    bpm: bool
    sheet_frames: int
    llm_timeout: int
    claude: str
    max_bytes: int
    max_duration: float
    frame_limit: int = 36
    asr_initial_prompt: str = ""
    word_timestamps: bool = True
    bridge: Path | None = None

    @classmethod
    def load(cls):
        yml = load_settings()
        limits = yml.get("limits", {})

        def pick(env, key, default, source=yml):
            return os.getenv(env) if os.getenv(env) is not None else source.get(key, default)

        data = Path(pick("DATA_DIR", "data_dir", "data"))
        return cls(
            (data if data.is_absolute() else ROOT / data).resolve(),
            str(pick("MODEL_ANALYSIS", "model", "sonnet")),
            str(pick("WHISPER_MODEL", "whisper_model", "small")),
            max(1, min(6, int(pick("WHISPER_THREADS", "whisper_threads", 6)))),
            str(pick("WHISPER_LANGUAGE", "language", "auto")),
            str(pick("OCR", "ocr", True)).lower() in ("1", "true"),
            False,
            max(1, min(9, int(pick("SHEET_MAX_FRAMES", "sheet_frames", 9, limits)))),
            int(pick("LLM_TIMEOUT", "llm_timeout_s", 600, limits)),
            str(pick("CLAUDE_BIN", "claude_bin", "claude")),
            int(float(pick("MAX_STORAGE_GB", "max_storage_gb", 80, limits)) * 1024**3),
            float(pick("MAX_VIDEO_SECONDS", "max_video_seconds", 3600, limits)),
            max(3, min(36, int(pick("FRAME_LIMIT", "frame_limit", 36, limits)))),
            str(pick("ASR_INITIAL_PROMPT", "asr_dictionary", "")),
            str(pick("WHISPER_WORD_TIMESTAMPS", "word_timestamps", True)).lower() in ("1", "true"),
            Path(os.environ["BRIDGE_DIR"]).resolve() if os.getenv("BRIDGE_DIR") else None,
        )


def input_folders():
    return [Path(p).expanduser() for p in load_settings().get("input_folders", [])]
