# INDEX.md format

```
# Read: card index

| id | profile | lang | status | thesis | thesis_source | domain | file |
|---|---|---|---|---|---|---|---|
| sample-55de012bbcb5 | analysis | en | untested | The Zorbex beacon signal has a small predictive effect but is not profitable after costs. | card | trading signal testing | [card](cards/sample-55de012bbcb5.md) |
```

| column | content |
|---|---|
| `id` | card id, also the file name stem in `cards/`, `articles/`, `archive/` |
| `profile` | `analysis`, `howto`, `opinion`, `news_promo`, `other` |
| `lang` | language of the video and of the card |
| `status` | `untested`, `in_test`, `confirmed`, `rejected` (read from the card header) |
| `thesis` | one sentence; with `thesis_source: fallback` it is the first sentence of the article and the profile is `other` |
| `thesis_source` | `card` or `fallback` |
| `domain` | the field, in the source language |
| `file` | link to the card |

One row per card, sorted by file name. `INDEX.md` is generated from the card headers (no model call), so it is always consistent with them. After you change a card's `status`, regenerate the index with `python -m vjournalist index <OUTPUT/X>` (no model call, cards untouched). Without the CLI, edit the row's `status` cell by hand to match the card.

Use the index to decide what to open: filter by `domain` and `status`, read `thesis`, open the file. A thesis is a pointer, not the claim in full; the card has the numbers and gaps.
