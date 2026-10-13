# Agent-index predictability

Research-only tooling for measuring whether the target agent's player/seat index predicts outcome after controlling for seed and opponent identity. This lane does **not** change gameplay, defaults, production code, or Kaggle activation.

## Why matched pairs

A pooled seat-0 vs seat-1 average is not trustworthy when opponent assignment differs by seat. The analyzer therefore treats the primary observation as an exact `(seed, opponent)` pair with the target run once in seat 0 and once in seat 1. It reports the target-margin delta `seat1 - seat0`, plus an equal-opponent-weighted mean so a frequently sampled opponent cannot dominate the conclusion.

It also reports raw opponent-assignment total-variation distance and matched-pair coverage. Large assignment TV or poor coverage is a warning that unpaired seat averages are confounded.

## Input custody

Input may be a JSON array or JSONL. Each record needs:

- seed: `seed`, `episode_seed`, or `game_seed`;
- opponent identity: `opponent`, `opponent_id`, or `opponent_name`;
- target seat: literal integer 0 or 1 in `target_seat`, `seat`, `player_index`, `agent_index`, or `player`;
- outcome as target-relative `margin`, a two-item `rewards` list, or `score` + `opponent_score`.

Seed and opponent identifiers may be strings or integers, but **one dataset must use one primitive type per identifier domain**. The report retains the historical string representation only after that dataset-level custody check. This prevents integer `1` and string `"1"` from collapsing into the same matched provenance cell or false duplicate.

If a record contains more than one outcome representation, all supplied representations must agree exactly after numeric validation or the record fails closed. There is deliberately no relative-tolerance comparison: without an authenticated magnitude bound, a tiny relative difference can still be an enormous absolute contradiction. Integer values are retained exactly after finite-range validation so disagreements above the IEEE-754 exact-integer range cannot collapse through float conversion.

Derived reward/score subtraction is revalidated for finiteness, and the paired estimand `seat1 - seat0` is independently revalidated after matching. Thus individually finite margins such as `-1e308` and `+1e308` cannot manufacture an infinite seat effect.

There is deliberately **no built-in reward ceiling**. A historical Antigravity proposal suggested clipping final margins to +/-65,000, but a measured pinned-engine control produced a legitimate `168572 - 3550 = 165022` margin. Clipping would silently falsify that record.

For ingestion where outcome records are not inherently trusted, two opt-in guards preserve the useful part of that hardening idea without inventing a universal score cap:

- `--require-structured-outcome` rejects margin-only records and requires `rewards` or `score + opponent_score`. A redundant direct `margin` may still be present, but it must agree exactly with the structured representation.
- `--authenticated-max-abs-margin N` accepts a positive finite bound only when the caller has authenticated that bound from the producing engine or dataset contract. A record outside the bound is **rejected, never clipped**. The default is no magnitude bound.

These guards are also available through `analyze(..., require_structured_outcome=..., authenticated_max_abs_margin=...)` and `normalize_record(...)`. Provenance for an optional bound remains the caller's responsibility.

Duplicate exact `(seed, opponent, seat)` cells fail closed. `--require-complete` rejects any seed/opponent group missing one seat.

Example:

```json
{"seed":1909087201,"opponent":"LARK","seat":0,"rewards":[101200,99800]}
{"seed":1909087201,"opponent":"LARK","seat":1,"rewards":[99800,101200]}
```

For a trusted engine export whose authenticated absolute target-margin limit is 200,000:

```text
python analyze_agent_index.py panel.jsonl \
  --require-complete \
  --require-structured-outcome \
  --authenticated-max-abs-margin 200000
```

Do not substitute `65000` or any other guessed constant merely because it sounds plausible.

## Output

The JSON report includes matched-pair coverage; matched seat-0 / seat-1 mean margins; paired mean and median `seat1 - seat0`; equal-opponent-weighted mean delta; paired sign-test counts and exact two-sided p-value; Cohen's paired standardized effect where finite/defined; per-opponent pair counts and mean deltas; raw opponent-assignment total-variation distance; missing-cell examples; and an `input_guard` receipt recording the optional ingestion guards.

A constant nonzero paired delta has zero variance and therefore no finite Cohen `d_z`; the tool emits JSON `null` for that degenerate statistic while preserving the raw paired mean and sign test. Any non-finite standardized effect also degrades to `null`; primary paired deltas themselves must always be finite or the dataset is rejected.

## Verification and convergence

Current successor analyzer Git blob: `531a0d6b14a9084bd768672cc0b88c03c9b5b61e`.

Current successor regression Git blob: `d4db9300e6f979106004f2d95a5c49ba3aa7715f`.

The focused suite contains 25 methods covering the original matched-pair/statistical contracts plus derived finite-operand overflow rejection, paired-delta overflow rejection, integer/string seed and opponent identity collisions, mixed identifier-domain rejection, the legitimate 165,022-margin control, authenticated reject-not-clip behavior, structured-outcome enforcement, explicit no-bound default compatibility, and input-guard receipt coverage.

Repository workflow `TITAN V4 agent-index analyzer hardening` runs the focused suite under normal Python and `python -O`, then `py_compile`, on the literal PR head. A queued or pending workflow is not green.

Gemini/Antigravity proposition convergence is **not duplicated in this package or workflow**. The already-merged canonical `gemini-antigravity-convergence/HISTORICAL-DIRECT.json` owns the `gemini.analyzer-margin-clipping` and `gemini.terminal-mass-hire` coverage records and points to the current analyzer and terminal-labor evidence. The superseded standalone addendum JSON/tests formerly carried by this PR were intentionally removed during convergence.

At initial landing, default-branch searches did not surface a committed replay corpus containing the required matched seed/opponent/seat/outcome cells. A replay-capable/data seat should run this analyzer against an exact paired panel rather than infer a result from unmatched hosted games.
