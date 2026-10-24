# Output format

## Ids and folders

`<id>` = slugified video file name + `-` + the first 12 characters of the file's SHA-256, e.g. `sample-55de012bbcb5`. Titles of downloaded videos serve as the name.

Where results go:

| Input | Default output |
|---|---|
| a folder `~/clips/A` | `~/clips/OUTPUT/A/` |
| a single file `clip.mp4` | `./OUTPUT/clip/` (relative to the working directory) |
| a URL | `./OUTPUT/<slug of the title>/` |

`--output DIR` overrides all of them. Several runs into one directory add to the same `INDEX.md`.

## Files

### `INDEX.md`
One table row per card: `id | profile | lang | status | thesis | thesis_source | domain | file`. `thesis_source` is `card` (taken from the card), `fallback` (first sentence of the article, profile shown as `other`). Details for consumers: the `claim-cards` skill, `references/index-format.md`.

### `cards/<id>.md`
YAML header (`id, type, card_version, schema_version, lang, profile, domain, thesis, thesis_source, status, source_reliability, archive_tx, number_check_legend, number_check`), then `# <title>` and one `## <field>` section per field of the profile. Fields per profile are in `claim-cards/references/card-format.md`. `status` starts as `untested` and `source_reliability` as `unverified_claim`: the card records what the author *says*.

### `articles/<id>.md`
Narration in the order of the video, attributed to the author, followed by `## Data from charts and slides` with a table `Time | Data | Value | Source | Confidence`. Source is `speech`, `screen`, `screen+speech` or `computed`. Headings and labels follow the source language.

### `archive/<id>.tx.md`
Header (`id, type: transcript, lang, duration_s, asr, verified_by_ear: false, number_check`) then blocks of about 10 seconds: `[mm:ss] text`. `[?]` marks low-confidence ASR. `asr:` is `faster-whisper <model>` or `platform_captions`. `verified_by_ear: false` is always true: nobody listened to it.

### `archive/<id>.screen.md`
Legend, filter counts, then `[first-last s] text` lines of de-duplicated OCR; `≈` marks an uncertain reading.

### `archive/<id>.rejections.md`
Content the validator removed or corrected (numbers without coverage, unverified on-screen quotes, proper names not in the source, ...). It exists for people reviewing quality. The card itself carries only `field: reason` in `## local_rejections`.

## number_check

Per number in the card: `ok` (in speech and on screen), `speech_only`, `screen_only`, or `conflict(OCR:x)` (speech and screen disagree, e.g. 55.2 spoken, 55.7 on screen). Computed values live only in `## derived` as `value = formula` over source numbers.
