# Guarded starvation activation composition

Status: **source-composable on the current fast-tape runtime edge; default OFF; native natural gate COLD; not promoted**.

This closes the activation gap behind the existing `STARVATION.md` mechanism proof without creating another controller, V4 root, or feature key. The existing `r04_dead_feed_care` feature remains the sole W2 service opt-in. In the composed selected-action seam, repeated-FEED CARE salvage runs first; guarded starvation runs second; only then is the selected checkpoint/consumer snapshot published.

## What changed

`uncared_eod_feed_skip.py` retains the original mechanism APIs and adds `plan_guarded_starvation_skip` / `apply_guarded_uncared_eod_feed_skip`. Activation is deliberately narrower than the source theorem:

- still only EOD hour 23, `consecutive_unfed == 0`, uncared/unfed animal, exactly one authored FEED at the site, and no current CARE collision;
- pending CARE value on a current production boundary still blocks;
- at most **one** skip is admitted per EOD;
- all observed shed + carried physical inventory must fit the shed cap, and current HARVEST/COLLECT or product/animal buys block the proof, so the extra unconsumed WHEAT cannot displace other EOD cargo;
- the official EOD reset is modeled exactly: all carried inventory is dropped to the shed, hands are deleted, main farmer respawns at the NW shed-access tile, inventories reset;
- the authored next-day main-farmer tape must trace the one saved WHEAT through a shed `PICKUP` and an effective FEED at the **same animal site** no later than the next EOD;
- while the saved unit is still in shed, an authored hand `PICKUP WHEAT` or market `SELL WHEAT` invalidates custody; FEEDing another animal first consumes the lower-bound saved unit and invalidates the certificate;
- unknown custody-changing operations fail closed.

The old mechanism-only `apply_uncared_eod_feed_skip` is retained for its source tests. Native composition calls only the guarded activation API.

## One W2 seam; no new key

`compose_native.py` accepts the existing starvation helper as an optional authenticated source and copies it beside the already-authenticated CARE helper. Both are gated by `Features.r04_dead_feed_care`; no second feature field is added. The composed order is:

1. `selected = production.act(obs)`
2. existing W2 parent checkpoint/fallback
3. `dead_feed_care.apply_dead_feed_care(...)`
4. `uncared_eod_feed_skip.apply_guarded_uncared_eod_feed_skip(..., controller.R[cur])`
5. selected checkpoint + existing consumers

The composer also resolves the current fast-tape same-file edge. Fast-tape's exact reviewed runtime postimage is `git-blob:2b2bd80e...` / SHA-256 `5063e599...`. W2 is inserted before the fast-clone checkpoint and preserves the fast branch unchanged. Combined runtime is `git-blob:7f58e8f8...` / SHA-256 `54c93363...`; deleting only the W2 span restores fast-tape byte-for-byte.

## Focused source tests

The exact existing mechanism test file `git-blob:c1434a8e...` plus the new activation tests run together:

- 31/31 normal PASS
- 31/31 `python -O` PASS
- `py_compile` PASS

New cases include EOD capacity, current stock creation, current product/animal buys, missing pickup/feed, wrong-animal feed first, WHEAT sale/hand pickup before custody transfer, CARE/repeated-FEED collisions, unfed streak 1, malformed route, and at-most-one admission.

## Native receipt

Foundation: artifact `10175943272`, archive SHA-256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.

Current runtime-surface chain:

`b952c9c...` (foundation runtime) -> `2b2bd80e...` (fast-tape reviewed postimage) -> `7f58e8f8...` (fast-tape + W2 guarded-starvation composition).

Both seats, official engine, starter opponent, seed 17, 719 callbacks:

- baseline fast-tape vs W2-disabled: exact action/state trace identity;
- W2-disabled vs guarded-ON: exact action/state trace identity;
- 719/719 callbacks completed on each seat; zero deadline fallback;
- normal and optimized ON/OFF parity both passed;
- 1,438 guarded calls total, 56 EOD admission checks, **0 mechanism candidates / 0 admissions / 0 rewrites**.

Therefore the natural gate is **COLD**, not economically accepted or rejected. No score improvement is claimed. The current source graph's LOOM-4 scheduler/frozen/selected/early-capital postimages are receipt-only source transforms (`SOURCE_COMPOSITION_RECEIPT_NOT_RELEASED`), not a released whole native package, so no claim is made that this seed-17 native run includes those disjoint source-only postimages. The W2-vs-fast-tape collision itself is closed exactly.

No default, production config, archive, hosted Kaggle, or submission is changed.
