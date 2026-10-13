# ASTRA-FASTING — uncared EOD FEED-skip admission

This is **not** a revival of blanket alternate-day feeding.

The exact official engine (`reference/engine/kaggriculture.py`, Git blob `3c202c7ee921da239356789e266b694635103fc4`) permits one unfed end-of-day transition: an animal at `consecutive_unfed == 0` advances to `1` and survives; scheduled base production still runs and `fertilizer_available` is set. However, CARE economics are feed-dependent: a pending CARE bonus is realized on a production boundary only when the animal is fed, and a new CARE bonus is banked only from `cared_today && fed_today`.

## Historical falsifier retained

The earlier ASTRA/SOL INTERVAL-FEED red-team on the exact 18 live V3.1 tapes already rejected the broad idea. Replacing mature cow FEED+CARE with PASS on non-production days saved about **60.9 successful WHEAT feeds/game** but reported mean **Δown ≈ -$3,695.6/game** and **Δmargin ≈ -$8,127.2/game** (8 cells own-better / 10 worse) because the policy destroyed real pending CARE-bonus milk. Its theorem-safe pre-first-yield cap subcase fired once in 18 cells (+$46 own / +$47 margin) and was otherwise inert. Slack provenance: `1789166406.644339` in the TITAN V4 board thread.

FASTING therefore does not claim that feeding every other day is profitable and does not own or resurrect any historical ALTDAY/INTERVAL controller.

## New current-native admission contract

`uncared_eod_feed_skip.py` exports a default-off transform which may change an exact `FEED` row to `PASS` only when all of the following are public/current-state certainties:

- exact default 10×10 / 24-turn day / 720-step season;
- callback is hour 23, so no later same-day unit callback can add CARE;
- placed GOOSE/COW/SHEEP tile is structurally valid;
- `consecutive_unfed == 0` (never suppress when the next miss would cause escape);
- `fed_today == False` and `cared_today == False`;
- exactly one authored FEED targets the site;
- no authored CARE targets the site;
- a repeated same-site FEED is left untouched for the existing `dead_feed_care.py` FEED→CARE salvage;
- if the next EOD is a production boundary, `pending_care_bonus` must be zero;
- the targeted actor physically carries WHEAT, so the rewrite certifies one actually avoidable feed rather than deleting a no-op.

The transform changes no market row, no actor-row cardinality, no other unit row, no tile/state, and no global runtime policy. Disabled or uncertified input is exact identity.

## Composition authority

This file lives in the existing `repairs/gameplay/dead-feed-care/` family on purpose.

- `dead_feed_care.py` (`51c17ea3245755673ffead8e86d4b04e7766c949`) remains the sole W2 redundant-FEED→CARE helper.
- AFTERCARE (`aftercare_engine.py` blob `9ad59d1143cead79ca22c86b88e1b9850af2e44b`) remains the independent CARE collateral/economic oracle.
- ASTRA-STARVEORACLE owns the independent exact-official-engine all-species cadence proof/receipt for this newly narrowed theorem.
- Existing native assembler/composer owners retain runtime materialization and final-stack admission.

FASTING must never run in a way that steals a repeated-FEED CARE opportunity. The admission helper already fails closed on that surface.

## Authored validation

Exact authored source/test bytes were executed locally before publication:

- `test_uncared_eod_feed_skip.py`: **15/15 PASS** under normal Python;
- same exact bytes: **15/15 PASS** under `python -O`;
- `py_compile`: PASS;
- all-species production-boundary pending-bonus blockers are enumerated;
- malformed/default-config/type-poison, escape-boundary, current CARE, repeated FEED, missing physical WHEAT, unrelated unit rows, raw cardinality and market preservation are covered.

These are source/admission regressions, **not** full-engine economics or native reachability evidence.

## Activation gate

Keep default OFF. No production/default/archive/Kaggle mutation is justified by this source packet alone. Before any activation language, require all of:

1. STARVEORACLE exact official-engine receipt proving the admitted state transition for all species and the CARE/fertilizer/held-cap boundaries;
2. current-native composition into the one V4 stack without replacing W2/AFTERCARE semantics;
3. a natural engagement census identifying how often certified rows occur;
4. both-seat economics against current opponents/gauntlet, with WHEAT saved, product/fertilizer output, CARE bonus, fallback/deadline and terminal margin recorded.

If natural engagement is zero, classify this `COLD/UNREACHED`, not profitable and not harmful.
