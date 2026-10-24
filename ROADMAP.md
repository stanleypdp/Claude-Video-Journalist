# Roadmap (after 0.1.0)

Known gaps, in rough order of value. Nothing here is promised for a date.

**Quality**
- Lower the false-rejection rate (5.4% on earlier real runs, 2 of 3 rejections on the sample): the table-label check fails when OCR fuses words (`OPENABOVEBEACON`); it needs a smarter matching window, not a looser one.
- Remove heuristics tied to one early test video from `pipeline/knowledge_text.py` (a hard-coded set of chart labels) and give the gap checks in `bridge/cards.py` English ids (they are Polish ids mapped to English labels today).
- Choice of which values appear in the slide-data table is the model's; the labels are checked, the selection is not.
- Calibrate chapter validation for videos over about 5 minutes; measure the token saving of cards against transcripts on long videos (on 1-2 minute clips a card is not smaller).

**Input**
- Optional use of platform *automatic* captions, flagged as lower quality; clearer handling of several caption languages.
- Cookies for private or login-gated videos, playlists, batches of URLs.
- Larger Whisper models and Apple-silicon acceleration.

**Skills and packaging**
- Run the graded evals with a model, and the description-optimization loop with the 20 trigger queries per skill (not run for 0.1.0: it needs many model calls).
- A `pipx`/`pip` installable package with a `vjournalist` entry point, and a `.skill` bundle that carries the package.
- A `vjournalist status <id> <status>` command so consumers need not edit card headers by hand.
- Dispatcher and reviewer agent definitions, and a review-package builder, for people who want independent quality checks.

**Platform**
- Full-pipeline tests on Linux and Windows (CI covers unit tests only).
