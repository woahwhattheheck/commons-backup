# QUIETBOX — gauntlet contention certificate

Purpose: stop wall-clock host contention from being mistaken for TITAN strength. The published V4 gauntlet command used `--workers 8`, while the gauntlet owner separately observed the same mirror game moving from roughly `-6` on a quiet machine to `-561` under 8-worker load. That scale is larger than several positive micro-edges currently being stacked, so a strength receipt needs a load-stability check before small margins are trusted.

This package does **not** replace the gauntlet and does not change the 720-step engine, agent deadlines, opponents, policy, or production V4. `quietbox_gate.py` is a runner-independent certificate over real gauntlet JSONL output.

## Gate contract

Give QUIETBOX a quiet/reference result file (normally a mirror/control run with one worker) and a loaded result file (for example the normal 8-worker benchmark). Every quiet coordinate must appear in the loaded file. By default coordinates are inferred as `(opponent, seed, seat, replicate)` and margins are inferred from common `margin` or score fields. Dotted field overrides are available for the real runner schema.

QUIETBOX fails closed on:

- malformed JSON, duplicate coordinates, missing quiet coordinates;
- error/timeout/fallback rows or explicit non-success status;
- non-finite margins;
- fewer than two aligned rows or one-seat-only evidence by default;
- per-cell contention drift over `$100`, mean absolute drift over `$50`, or signed mean bias over `$50` (all configurable);
- when `--claimed-edge X` is supplied, max drift above 25% of `|X|` by default. This is the important gate for small stacked edges.

A loaded file may contain more opponents than the quiet file, so the quiet run can be a mirror/control subset. Use `--exact-coverage` when both files are intended to contain exactly the same panel.

## Commands

```bash
python3 quietbox_gate.py \
  --quiet results/mirror-workers1.jsonl \
  --loaded results/bench-workers8.jsonl \
  --out results/quietbox.json
```

For a lane claiming a `+$209` edge:

```bash
python3 quietbox_gate.py \
  --quiet results/mirror-workers1.jsonl \
  --loaded results/bench-workers8.jsonl \
  --claimed-edge 209 \
  --out results/quietbox-edge209.json
```

If the gauntlet uses different field names:

```bash
python3 quietbox_gate.py \
  --quiet q.jsonl --loaded l.jsonl \
  --key-fields opponent.id,seed,candidate_seat,replicate \
  --margin-field result.terminal_margin \
  --seat-key-index 2
```

Exit codes: `0` certified, `2` valid inputs but contention gate failed, `3` invalid/unhealthy evidence.

## Executed validation

Exact source bytes in this directory were executed under normal Python and `python -O`:

- 10/10 focused tests PASS in each mode;
- `py_compile` PASS;
- synthetic reproduction of the published quiet/load caveat (`-6 -> -561` on one seat, mirrored opposite seat) exits `2`, `certified=false`, with max/mean absolute drift `555`;
- tests cover stable certification, the contention rejection, missing/extra coordinates, exact-coverage mode, fallbacks, non-finite values, score-derived margins, relative claimed-edge budgeting, duplicate coordinates, and explicit nested schema fields.

See `QUIETBOX-VALIDATION.json`.

## Scope / non-claims

This is measurement trust infrastructure only. The validation receipt contains no new engine game, opponent, competitive EV, or promotion evidence. It does not authorize changing game deadlines to make a candidate look better. The quiet and loaded runs must use the same candidate, engine, opponent source, seeds, seats, and gameplay settings; only host contention / worker load should differ for the calibration comparison.

Slack claim / provenance: `#titan-kaggriculture` TS `1789183547.540799`; gauntlet caveat source TS `1789183196.420119` and current published gauntlet command TS `1789183372.027719`.
