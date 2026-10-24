---
name: claim-cards
description: How an agent should read and use claim cards produced by video-read (an INDEX.md plus one card file per video, under cards/, with claims, numbers, stated method and gaps) - load the index first, open only the cards you need, treat every claim as the author's untested hypothesis, build a test plan from the card, verify a number against the transcript archive, and write results back to the card. Use this skill whenever a task involves files in an OUTPUT folder with cards/, articles/ and archive/, whenever the user asks to test, check, reproduce, compare or act on a claim from a video or reel, or says things like "use the knowledge from these reels", "which of these claims can we test", "check the number in this card" - even if they never mention "claim cards".
---

# claim-cards

A card is what a video's author **says**, with the evidence needed to check it. It is not a fact. This skill is plain text: no dependencies, no scripts. It tells you how to spend as few tokens as possible and how to stay honest about what is established.

## Loading order

1. Read `INDEX.md` first. One row per video: `id | profile | lang | status | thesis | thesis_source | domain | file`. Choose cards from the thesis and domain columns. Do not open every card.
2. Open `cards/<id>.md` only for the theses you need. A card is about 600 tokens.
3. Open `articles/<id>.md` only when the card lacks context (what the author showed, the table of on-screen data).
4. Open `archive/<id>.tx.md` (transcript) or `archive/<id>.screen.md` (on-screen text) only to verify one number or quote, and only the block near the second you are checking. Never load the archive wholesale; that is the expensive part.
5. Ignore `archive/<id>.rejections.md` as evidence. It lists what the validator removed.

Field names and profiles: `references/card-format.md`. Index columns and statuses: `references/index-format.md`.

## How to treat a card

- `status: untested` with `source_reliability: unverified_claim` means **"according to the author"**. Say so when you repeat a claim ("the author reports 54.2%..."), never state it as established.
- `reported` holds the author's numbers, each with `@s`, the second in the video where it was said or shown. `method_stated` holds verbatim quotes of how the test was done. `not_stated` lists what you would need to repeat the test and the author did not give. `caution` lists the author's reservations. `agent_notes` may hold `assumption: ...` lines: interpretations nobody confirmed.
- `number_check` tells where each number was found: `ok` (speech and screen), `speech_only`, `screen_only`, `conflict(OCR:x)`. A `conflict` means speech and screen disagree: verify before using either value.
- Numbers under `## derived` were computed by code from source numbers (`value = formula`). They are not the author's.
- The card's language is the video's language. Do not translate quotes in `method_stated`; they are evidence.

## Building a test plan from a card

Use only the card (and INDEX). Do not open the archive to write the plan.

1. **Hypothesis**: copy `claim` / `author_conclusion` and prefix it "According to the author".
2. **What was measured**: the entries of `reported`, with their `@s` and `number_check`.
3. **How the author says it was done**: `method_stated`, verbatim.
4. **Gaps to close before testing**: `not_stated`. Each is a decision you must make and record (data source, period, sample size, costs, definitions).
5. **Success criteria**: derive only from numbers that are in the card. Do not invent thresholds or add figures from memory.
6. **Risks**: `caution` plus every `assumption:` in `agent_notes`.

Example, from the sample card (a fictional signal test):

```
Hypothesis (according to the author): the Zorbex beacon predicts the next move better than a coin flip.
Reported: right in 54.2% of sessions vs 50.4% for the coin flip (@15); 58% vs 49.6% when the market
  opened above the beacon (@23); 812 trades over 5 years, +7.4R before costs (@33). Costs: 0.04R per
  trade, screen_only (@33).
Method as stated: "...drew a random coin flip at the same time, and compared the two across 500 simulated runs." (@7)
Open before testing (not_stated): how the signal is defined; trade entry/exit rules; sessions per run;
  the result after costs as a number.
Criterion: reproduce 54.2% vs 50.4% on the same definition, then check that the edge survives 0.04R/trade.
Risks: the author calls index and runs fictional; the after-costs claim is an assumption (agent_notes).
```

## Verifying a number

1. Find the number's `@s` in the card.
2. Read the transcript block around that second: `python -m vjournalist tx <id> --at <s> --window 20 --output <OUTPUT/X>`, or open `archive/<id>.tx.md` and read the `[mm:ss]` blocks near it. Check the OCR file for the same moment when `number_check` is `screen_only`, `ok` or `conflict`.
3. Record what you found in `agent_notes`, e.g. `verified: 54.2% heard at [00:15], also on screen`. If the archive disagrees with the card, say so; do not silently pick one.

## Writing results back

- Change `status` in the card header only through the cycle `untested -> in_test -> confirmed | rejected`. `in_test` when you start, `confirmed` or `rejected` when your own test has finished and you can name the evidence. Then refresh the index: `python -m vjournalist index <OUTPUT/X>` (or edit the row's `status` cell by hand).
- Append one line per result to `agent_notes` (date, what you ran, outcome, where the evidence is). Keep earlier lines.
- Never edit `reported`, `method_stated`, `number_check` or the archive files. They are the record of what the video said; your results belong in `agent_notes`.
- `confirmed` means *your* test confirmed it, under the conditions you wrote down. It does not upgrade the author's wording to a general truth.
