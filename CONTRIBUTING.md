# Contributing

Issues and pull requests are welcome.

- Setup: `./install.sh`, then `uv run pytest -q` and `uv run ruff check .`. Tests run without Whisper, network or a Claude login.
- Behaviour changes need a test first. Anything that changes cards or articles must keep `check` at 0 coverage problems on `examples/sample/OUTPUT`.
- Never add a second paid model call to repair output; repairs are code.
- No third-party footage, real account names or personal paths in tests, fixtures or examples. Use invented content, like the sample.
- Run `scripts/prepush_scan.sh` before pushing; it must report 0 hits.
- Skill changes: keep `SKILL.md` under 500 lines and update the cases in `skills/*/evals/`; `scripts/build_eval_fixtures.py` regenerates their input files.
