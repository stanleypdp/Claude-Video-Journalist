# Card format

File: `cards/<id>.md`. YAML header, `# <title>`, then one `## <field>` section per field of the card's profile. List fields are bullet lists.

## Header

| key | meaning |
|---|---|
| `id` | file name + 12 characters of SHA-256 |
| `type` | always `thesis_card` |
| `card_version`, `schema_version` | format versions (4 and 6 today) |
| `lang` | language of the video; every text field is in it |
| `profile` | `analysis`, `howto`, `opinion`, `news_promo`, or `other` |
| `profile_model` | only with `other`: the profile the model chose before the fallback |
| `domain` | the field in the source language ("trading signal testing") |
| `thesis` | one sentence, shown in `INDEX.md` |
| `thesis_source` | `card` or `fallback` (first sentence of the article) |
| `status` | `untested` -> `in_test` -> `confirmed` / `rejected` |
| `source_reliability` | `unverified_claim` for every card |
| `archive_tx` | relative path of the transcript archive |
| `number_check_legend`, `number_check` | where each number was found, see below |

## Profiles and fields

| profile | for | fields (in order) |
|---|---|---|
| `analysis` | claims backed by numbers and a method: markets, health, technology tests | `claim`, `author_conclusion`, `reported`, `method_stated`, `not_stated`, `caution`, `agent_notes` |
| `howto` | tutorial, course step list | `goal`, `steps`, `tools_named`, `not_stated`, `caution` |
| `opinion` | review or thesis without data | `claims`, `evidence_given`, `not_stated`, `caution` |
| `news_promo` | announcement or promotion of a product, tool or event, no test of the author's own | `claim`, `what_is_promised`, `evidence_given`, `not_stated`, `caution` |
| `other` | the model gave no usable thesis; the thesis is the first article sentence (`thesis_source: fallback`) | same sections as the model's profile (`profile_model`) |

After those, a card may have `## derived` and `## local_rejections`.

### Field semantics

- `reported`, `steps`, `claims`, `what_is_promised`: items end with `@<second>`, the place in the video. `@s` is a locator, not a measurement. `steps` keep the order of execution and start with `[action]` (the viewer does it) or `[effect]` (the tool does it); in Polish sources `[akcja]` / `[efekt]`. The `@s` of steps need not increase.
- `method_stated`, `evidence_given`: verbatim quotes of the source, with `@s`. They are present only when the author really described a procedure or showed proof. Product promises are never `method_stated`.
- `not_stated`: gaps. Some are added by code after a negative check of the source text (for example a missing data source, sample size or significance statement). Plain gap lines read `<label>: not stated in the provided source text`.
- `caution`: the author's own reservations and gaps in the material. Never outside knowledge.
- `agent_notes`: interpretation and your results. Lines starting with `assumption:` are interpretations the author did not make (for example whether a result is "after costs"). Consumers append here.
- `tools_named`: tools the author actually named.
- `derived`: `value = formula` over source numbers, computed by code.
- `local_rejections`: `field: reason` only; the removed text itself is in `archive/<id>.rejections.md`.

## number_check

A map from each number in the card to:

- `ok`: found in speech and on screen
- `speech_only` / `screen_only`: found in one source only
- `conflict(OCR:x)`: speech and screen show different values, x is the OCR reading

Times such as `09:30` are not numbers here. Spoken numerals ("five") are normalised to `5`.

## What the code guarantees, and what it does not

Guaranteed by the validator: every number in a card, article or table exists in the transcript or OCR; computed values are in `derived` with a formula; on-screen quotes exist in the OCR (otherwise they are marked `[not in OCR]` or re-attributed to speech); proper names in the thesis come from the source.

Not guaranteed: that the author is right; that the ASR heard correctly (`verified_by_ear: false`); that the choice of which values appear in a table is complete. The validator can also remove correct content (`false_rejection_rate`); the archive has the full source.
