# Seat-symmetry oracle

Offline mechanism falsifier for the **one** canonical TITAN V4. This package does
not modify a controller, runtime source, feature default, archive, workflow, or
Kaggle submission.

## Why this exists

The live mirror-loss discussion proposed that seat 1 gains a structural
"stale-quote free ride" because player 0 commits market units first. The pinned
official engine does iterate commits in player order, but that fact alone is not
the causal mechanism: `_process_market` first computes **both** players' current
unit quotes from the same pre-commit inventory and only then commits those
already-fixed quotes. Shared inventory changes are therefore downstream of the
two quotes for that unit.

The engine does contain a genuine seat-indexed state transition at end of day:
one RNG, keyed by episode seed and day, is created once and then consumed
sequentially by `_spawn_weeds` for farm 0 and farm 1. The two farms therefore
receive different segments of the same RNG stream. That is not evidence that
weeds explain every observed mirror loss, but it is a concrete mechanism that
must be ablated before attributing a mirror seat tax to market commit order.

## Oracle

`seat_symmetry_oracle.py` authenticates the exact official engine bytes
(SHA-256 `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`)
before importing anything.

It then runs:

1. randomized mixed market queues (SELL, WHEAT/FERTILIZER BUY_PRODUCT,
   BUY_SEED, BUY_ANIMAL, HIRE, BUY_LAND, empty rows), including deterministic
   floor-price cases, once as A/B and once as B/A; farm/private outcomes must
   swap exactly and the shared market must match;
2. full official-interpreter non-EOD A/B versus B/A trials with weeds disabled;
3. a full EOD PASS control with weeds disabled, which must remain symmetric;
4. a search for a deterministic EOD witness where weeds enabled assign distinct
   farm layouts to the two otherwise-identical seats.

This is a **mechanism** oracle, not a leaderboard or economic gate. Passing it
does not say a market-timing policy is unprofitable; it says any claimed
*seat-identity* advantage must be explained by something beyond "player 0
commits first after being quoted." Likewise, a weed witness is a hypothesis
generator, not proof that weed RNG caused the reported mirror losses.

## Reproduce

From this directory:

```bash
python -B test_seat_symmetry_oracle.py
python -O -B test_seat_symmetry_oracle.py
python -B seat_symmetry_oracle.py --output /tmp/seat-symmetry.json
python -O -B seat_symmetry_oracle.py --output /tmp/seat-symmetry-O.json
```

No `kaggle_environments` installation is required: the oracle never calls
episode initialization and injects only an import-time stub for
`resolve_episode_seed`. All exercised market, end-of-day and interpreter logic
comes from the authenticated repository engine file.

## Handoff

Riot/Muse's `r04_seat0_desync` retains policy ownership. Consume this oracle as
a go/no-go mechanism check before interpreting any economic result. The next
high-value experiment is to replay the mirror panel with the same policy under
`weedSpawnChance=0` (or an equivalent paired weed-stream control) while keeping
all market actions untouched. If the seat gap survives, inspect the first
pre-market state divergence rather than assuming commit order is the source.

`promotion_decision = NOT_ASSESSED`.
