# Admitted represented-market replay — ASTRA-CLEARING

One additive repair in `main:candidates/v4`, not a second V4 or an archive replacement.
Source claim: Slack `1789183142.010289`. Recovers the native execution gap behind
older #12055 (paid HIRE) and #12056 (raw market prefix), without running either
legacy materializer or copying an older controller over the current native.

## What changes

`apply_represented_market` used to grant requested goods and workers without
payment. The repair uses the existing pinned mechanics to admit each paid unit,
updates money/seeds/land/hands/shed/inventory in order, allows only WHEAT and
FERTILIZER product purchases, and honors real purchase capacity and the engine's
raw `max(1, maxMarketOrdersPerTurn)` prefix. Empty/malformed slots still count.
Known town demand and plant decay occur after market, before the next unit phase.
A SELL beyond the executable raw prefix no longer manufactures a horizon slot.
The actual `FrozenSelected.transform` call supplies the observed market snapshot.

This is explicitly a **no-additional-rival-trades scenario**, not a rival-proof
funding certificate. Original oversized unit-deposit pressure semantics remain;
this is not a complete executable-tape certificate. The replay declines to
cross an unmodeled day boundary. Missing market context cannot grant unpriced
purchase stock or use its uncertain remaining cash for a later HIRE.

## Source and composition

Checked artifact: `10175943272`, inner archive SHA256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
Native frozen blob `fc7baf5c179818a55037f6a61d92984d81d1a21c`;
mechanics `044a4f9c0a4a44dde10ada57563238bcaf82075d`.
The command checks both explicit input pins, writes only a NEW output directory,
and refuses changed method/callsite anchors or repeated application.

Standalone output frozen blob: `93820e20c69ea7be23f448ea579415d59d30eb75`.
Exact UNITFLOW recipe `e1127c4aad842278a9e617903b0718d21c00f348` composes in either
order with identical bytes: scheduler `eb289f87adebb7dc7e90046bfbec31a307cb5aaa`,
frozen `d18ded96a075cdc6c0e9114dc1fdc7ecd5393dbb`. The independent UNITFLOW
implementation is consumed from its existing location, not copied here.
LIVEPATH's copy-only seam remains unchanged; MOSAIC owns horizon-length
experiments. `_funding_trace`, funding objectives and seller ranking are unchanged.
No claim is made for untested later combinations or a latest-main complete build.

## Reproduce

Run from this directory, with `NATIVE` pointing to the extracted checked package.

```sh
python compose.py --package "$NATIVE" --output /tmp/clearing-new
python test_represented_market.py --package "$NATIVE" --receipt /tmp/normal.json
python -O test_represented_market.py --package "$NATIVE" --receipt /tmp/optimized.json
python validate.py --package "$NATIVE" --unitflow ../joint-unit-projection/compose.py --output /tmp/validation.json
python -O validate.py --package "$NATIVE" --unitflow ../joint-unit-projection/compose.py --output /tmp/validation-O.json
python native_game.py --package "$NATIVE" --arm candidate --seat 0 --output /tmp/game.json
```

Repeat the game with both arms, both seats, and Python normal/`-O` for the recorded
8-game control panel. Each invocation uses a fresh temporary package and process;
no network, user-PC work, paid compute or Actions dispatch is needed. To compose a
reviewed peer-modified input, supply its explicit `--frozen-blob`; do not bypass a
failed method anchor, overwrite newer source, or activate a release from this file.

## Executed evidence and limits

`EVIDENCE.json` retains the compact results, source identities and trace digests.
20/20 focused tests pass per Python mode, with 364 full interpreter calls per
suite. Both-seat witnesses remove unpaid/illegal/capacity-clipped purchases,
ghost workers, stale plant harvests and nonexecuting suffix slots; paid positive
controls and future sale-funded purchases remain active. Eight deliberately
broken variants fail behavioral assertions in each mode, with zero mutant errors.

Eight complete native `main.py::agent` games execute 5,752 callbacks, all completed,
no fallback. Baseline/candidate full action and observation trace hashes and final
scores match in both seats/modes against the pinned starter on seed 9922999. The
candidate's market method is exercised 4,213 times per game. This is runtime/control
parity, **not competitive EV, leaderboard strength or a natural bug-activation claim**.

The 28-test joint-market suite passes in each arm/mode. A broader 46-test inherited
probe is **not green**: 50 subtest failures from a stale pruning diagnostic oracle
and one missing `checks/reference/selected-action/t08/arrival_contract.py` error
occur in BOTH baseline and candidate. Complete logs match after normalization of
paths, function addresses and elapsed time. These failures are recorded, not hidden
or reported as passes; this repair does not modify those unrelated tests.

Production/default configuration, release archive, workflow definitions and Kaggle
submission are unchanged. The existing single-V4 assembler owns its final combined
gate; this is completed source delivery, not a queued implementation demand.
