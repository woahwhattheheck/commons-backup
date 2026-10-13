# Replay loss autopsy

Deterministic, stdlib-only research tooling for extracting exact Kaggriculture replay episodes from `farmer_actions.csv`, `market_orders.csv`, and `matches_meta.csv`, then comparing multiple source-bound extracts without inventing causal claims.

The tooling is intentionally descriptive rather than causal. It reports only fields present in the source CSVs: exact metadata rows, per-player/day action and market summaries, source hashes, resolved column names, extraction parameters, and a chronological final-callback event tail. It does not infer cash, tile state, inventory, opponent identity, economic value, or which policy mechanism caused a result.

## Extract one episode

```bash
python extract_episode.py \
  --farmer-actions /path/to/farmer_actions.csv \
  --market-orders /path/to/market_orders.csv \
  --matches-meta /path/to/matches_meta.csv \
  --episode 108020335 \
  --tail-callbacks 96 \
  --output episode-108020335.json
```

Common column names are resolved through a small alias table. If the dataset contains multiple plausible columns for the same semantic field, the tool fails closed instead of guessing. Supply an explicit JSON mapping with `--schema-json` when needed.

Every canonical extract records SHA-256 and byte length for all three inputs, the exact resolved columns, and the extraction parameters `tail_callbacks` and `turns_per_day`. Those parameters are evidence: changing `turns_per_day` changes day-bucket semantics, so downstream comparison must not mix extracts that used different values.

## Cross-episode recurrence

Once multiple episodes have been extracted from one frozen raw CSV snapshot, `compare_episode_extracts.py` reports exact descriptive action, market, and relative-tail tokens that recur across them:

```bash
python compare_episode_extracts.py \
  episode-108071852.json \
  episode-108073260.json \
  episode-108073343.json \
  --min-episodes 2 \
  --output recurrent-loss-signatures.json
```

The comparator accepts only canonical `titan.v4.replay-loss-autopsy.v1` extracts and fails closed unless every extract binds the same three raw-source hashes and byte lengths, identical `turns_per_day` and `tail_callbacks`, and identical resolved semantic-column mappings. Extracts produced by the older schema shape without serialized `parameters` must be re-extracted with the current canonical extractor.

It also rejects duplicate episode IDs, duplicate JSON keys, duplicate summary semantic keys, malformed source identities, boolean-as-integer evidence, malformed column maps, and tail evidence inconsistent with `coverage.max_step` or the bound tail window. Tail recurrence is normalized only by relative callback offset from each extract's reported `max_step`; it does not claim equivalent game state.

Recurring tokens are routing evidence only. They can show that the same descriptive pattern appears across multiple source-bound episodes, but they are not causal evidence and do not imply that changing the repeated action or market row would improve score.

## Fail-closed rules

- duplicate headers and malformed short/long CSV rows are rejected;
- ambiguous required aliases are rejected unless explicitly mapped;
- step and quantity parsing accepts strict integer text only, with no float/bool coercion;
- an episode absent from all three tables is an error;
- invalid tail/day parameters are errors and extraction parameters are serialized into the evidence;
- unknown or non-integer quantities remain visible through `qty_raw` and are excluded from `explicit_qty_sum` rather than coerced;
- multi-loss recurrence requires identical authenticated raw-source snapshots, extraction parameters, and resolved semantic columns;
- recurrence never grants mechanism, controller, activation, or causal-credit authority.

## Validation

`test_extract_episode.py` uses temporary synthetic CSVs and covers deterministic output, exact metadata preservation, explicit schema disambiguation, absent episodes, malformed rows, invalid parameters, and serialized custom day semantics.

`test_compare_episode_extracts.py` covers source-snapshot mismatch rejection, parameter and resolved-column mismatch rejection, duplicate episode/JSON/summary-key rejection, strict integer handling, deterministic CLI output, tail-custody consistency, relative-tail recurrence, and configurable recurrence thresholds.

The current package receipt in `VALIDATION.json` records the exact file identities and focused normal/optimized regression counts. This package is research-only. It does not modify Titan gameplay, configuration, defaults, production runtime, submissions, or Kaggle state.
