# Cost and cache

## What costs money

Only the Claude CLI call: **one per new video**, no tools, no MCP, no session, one turn. ffmpeg, Whisper and OCR run locally and are free. The cost is reported per run as USD-equivalent of subscription usage. The synthetic sample in `examples/sample/` cost 0.0457 USD-equivalent (one call, 48 s clip); real clips of one to two minutes cost 0.10-0.14 in earlier runs, longer clips cost more.

A validation failure normally triggers one repair call (`LLM_ATTEMPTS=2`, default). Set `LLM_ATTEMPTS=1` to forbid it. Repairs of anything else are done by code.

## Cache

Key: `data/cache/<sha256>/roles/knowledge/v6/`. The same file (any name, any folder) is never analysed twice. `read` prints cache hits with their historical cost and charges 0 for them.

- `rebuild <OUTPUT/X>` regenerates cards, articles and archives from the stored raw answers with the current validator. Zero calls. Use it after upgrading the code.
- Mechanics (ASR, OCR, scene scan) are stored per SHA-256 under `data/work/<sha256>/` and reused.
- To redo a video from scratch, delete its `data/cache/<sha256>/` directory. There is no flag that silently repeats a paid call.
- If a call was started but left no answer (crash), the code refuses to repeat it automatically, to avoid paying twice.

## Limits and pauses

When the Claude CLI limit is hit, the run waits and resumes (default), or with `--no-wait` stops with exit code 75 and the pending list. `config.yaml` limits: video length (3600 s), data folder size (80 GB), LLM timeout (600 s).

## Keeping it local

`data/` (cache, work files, Whisper model) is in `.gitignore`. Nothing is sent anywhere except the transcript, OCR lines and a few frames to the Claude CLI.
