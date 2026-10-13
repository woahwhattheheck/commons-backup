# TITAN V3 G01 — ARGUS semantic-safety overlay

Operation: `titan-v3-g01-semantic-safety-20260909-sol-argus-01`

This is an additive repair and build harness for the G01 Gemini candidate landed by
PR #11371. It does **not** replace `exports/titan-current.tar.gz`, does not publish
a Kaggle submission, and makes no gameplay-strength claim.

## Why this exists

The original G01 overlay contains useful hypotheses, but its initial integration
crosses exact engine and controller ownership boundaries:

- O01 prepends `BUY_LAND`, although the engine truncates market queues to
  `maxMarketOrdersPerTurn` and executes atomic orders at their literal queue
  index. A full queue can lose its tenth inherited order, and a land purchase can
  consume cash before an existing obligation.
- E11 multiplies the absorption count from the **current step** by every remaining
  step. The canonical `absorption()` function is a per-step tick, so the estimate
  is zero on most turns and grossly inflated on shop/center ticks.
- The original E11 hooks run after seller `pending` is computed. The emitted
  action can then withhold a sale while the seller checkpoint records it as
  scheduled.
- O01 separately removes SELL orders, bypassing E11's absorption gate when both
  flags are enabled.
- E20 removes only the final HIRE and cannot enforce its low-demand allowance
  when multiple HIREs are queued. Its `hires_today == 0` branch is unreachable.
- SHOP multiplies exact integer absorption by `1.5`, creating a fractional market
  inventory that the official engine can never produce.

`AUDIT.md` records the evidence and disposition for each finding.

## Production-enabled scope

Only E11 is wired by the builder, at the seller-owned seam **before** pending
accounting. The builder patches both `scheduler.py` and `frozen_selected.py`
because the archive carries both implementations; only the selected runtime path
executes.

O01, E20, and SHOP are retained as tested callables for the corresponding owners:

- O01 appends `BUY_LAND` only into a free slot and never edits SELLs.
- E20 preserves queue positions and removes every excess low-demand HIRE beyond
  the remaining allowance.
- SHOP exposes a scoring multiplier but refuses to alter exact absorption.

They remain production-quarantined until the capital/route/scoring owners compose
them without bypassing their ledgers.

## Build the candidate

The builder accepts only canonical archive SHA-256
`3b4b083ec2647bb0e715978c2565e916da0ee94c08b234902e3a7e4d3418c320`, extracts
into a new directory, rejects traversal/link members, patches exact source
anchors, compiles every touched module, and writes `ARGUS-G01-BUILD.json` with
output hashes.

```bash
python3 build_candidate.py \
  --archive /path/to/titan-current.tar.gz \
  --output /tmp/titan-v3-g01-argus-safe
```

The source archive is never modified. The command refuses to overwrite an output
directory.

For the first gameplay arm, enable only:

```bash
export TITAN_E11_RIVAL_SELL=1
export TITAN_RIVAL_MODEL=0
export TITAN_E20_HIRE_GUARD=0
export TITAN_SHOP_ARB=0
```

Use the panel owner's existing paired-seed runner and compare this arm against the
same canonical archive. Do not promote from unit results; require paired gameplay,
zero errors/timeouts, both seats, per-opponent slices, and holdout.

## Tests

```bash
python3 -m unittest -v test_semantic_safety.py test_builder.py
python3 -m compileall -q .
```

Current local result: **20/20 passed**. Tests cover queue saturation, inherited
order preservation, exact future tick aggregation, terminal identity, fractional
transition rejection, multi-HIRE suppression, flag-off object identity, archive
hash gating, traversal rejection, patch ordering, and input immutability.

## Provenance

- G01 source PR: #11371, merge `3379fd799766609691b4bb777e13f7b3cae0da00`.
- Canonical source archive: SHA-256 `3b4b083e…c320`, size 420,356 bytes.
- Canonical source commit used by G01: `ba1efc8732073d7ad566ea5090fb9aa3e8b2bc33`.
- Official engine receipt: commit `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
- Claim-time Commons main: `d19deb16ad935c548aafa2fad4c133f546905e52`.

See `PROVENANCE.json` and `RESULTS.md` for machine-readable receipts and explicit
non-claims.
