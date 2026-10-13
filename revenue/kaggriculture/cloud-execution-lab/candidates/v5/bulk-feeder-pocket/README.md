# TITAN V5 bulk-feeder pocket routing

Default-off research carrier for the canonical V5 route tape. This consumes the
`V5-FEEDER-CARRY-ROUTE-CENSUS` evidence demand; it is not feeder-policy authority.

## Source theorem

The pinned Kaggriculture mechanics currently authenticated by this carrier make
three facts explicit:

- shed-adjacent `PICKUP <item> <n>` accepts an integer quantity and clips only to
  observed shed availability;
- per-farmer `private["inventories"]` has no carrying-capacity check;
- `FEED` consumes exactly one carried `WHEAT`.

That creates a real route frontier when one worker repeatedly returns to the
shed for one-unit WHEAT pickups before later FEED actions.

## What this carrier does

`bulk_feeder.py` scans the canonical Arlene route branches for same-day repeated
WHEAT pickup/FEED windows. It can consolidate every pickup in one window into
the first pickup and replace only the later pickup actions with `PASS`.

The scan is intentionally only a proposal. A candidate is materialized only
after `verify_unit_window()` binds an exact observed `(player, step)`, requires
the canonical 24-turn route calendar, replays **all actors** from that observed
state with the pinned deterministic unit mechanics, and proves exact final
`farm` and `private` equality. This catches shared-shed timing conflicts such as
another worker depositing WHEAT after the first pickup. Witness-reported
action-slot opportunities are recomputed and movement savings are hard-pinned
to zero.

Market-bearing windows and day boundaries are rejected. The verifier fails
closed for noncanonical day lengths because the route scanner/validator is
24-turn-calendar-specific and does not simulate EOD lifecycle. Movement and
route length are not changed by this carrier, so elapsed-turn and travel-savings
claims remain deliberately `0`. The proved opportunity is only the number of
later pickup actions replaced by `PASS`, reported as
`reclaimable_pickup_action_slots`. Those PASS slots are substrate for a later
path compactor only after that movement rewrite gets its own exact-state proof
and evaluation evidence.

## Usage

```bash
python candidates/v5/bulk-feeder-pocket/bulk_feeder.py
python candidates/v5/bulk-feeder-pocket/bulk_feeder.py --route-json route.json
python -B candidates/v5/bulk-feeder-pocket/test_bulk_feeder.py
```

The CLI emits deterministic JSON under
`titan-v5-bulk-feeder-pocket-audit/v2`.

## Non-goals

This package does not edit `spatial_tempo.py`, root runtime code, defaults,
configuration, the canonical archive, or Kaggle activation. It does not claim
that a static opportunity is safe without an observed equality witness, and it
does not claim elapsed-turn or travel savings until movement itself is
separately proved.
