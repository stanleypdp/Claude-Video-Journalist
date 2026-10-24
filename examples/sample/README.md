# Sample

An invented 48-second video: six slides ("Zorbex Beacon", "Lumen 40" - neither exists) with a synthetic voice from macOS `say`. No third-party footage.

- `make_sample.py` builds `sample.mp4` (needs ffmpeg, macOS `say`, Pillow). The video itself is not committed.
- `OUTPUT/` is what `read` produced from it with one Claude CLI call (0.0457 USD-equivalent), then rebuilt from the cache after INDEX/path fixes:

```bash
uv run python examples/sample/make_sample.py
LLM_ATTEMPTS=1 uv run python -m vjournalist read examples/sample/sample.mp4 --output examples/sample/OUTPUT
uv run python -m vjournalist check examples/sample/OUTPUT      # OK: 1 card(s), 0 coverage problems
```

The slide "TRADED RESULT" shows `Cost per trade: 0.04R`, a number the narrator never says: its `number_check` is `screen_only`. `3.8` and `500` are `speech_only`.
