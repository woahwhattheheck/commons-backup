# T02 livestock counterfactual ledger and engine cases

This is the additive MESA subcomponent of TITAN T02. MERIDIAN retains the main
livestock policy, route decoding and game panels. Neither this directory nor its
fixtures changes Arlene, Apex, hiring, land, animal count or a deployed agent.

## Callable interface

`livestock_ledger.py` is standard-library-only and performs no I/O. Import it
from this directory (or package it beside the caller).

- `ServiceAction(step, op, unit=0, wheat_available=0)` describes a feasible visit
  to the candidate pasture. Unit 0 is the farmer; higher indices are hands.
  Same-step actions resolve by unit index. Feed availability is the visiting
  worker's actual projected inventory, not shared shed stock. One worker can
  perform only one action per decision.
- `project_calendar(species, placement_step, actions, *, episode_steps=720,
  turns_per_day=24, last_action_step=None, include_trace=False)` projects one
  hypothetical new COW or SHEEP placement. It returns dated harvest/feed/
  fertilizer receipts, production and cap losses, discarded care bonus, escape,
  final tile state and optional action-by-action state snapshots.
- `compare_species(placement_step, actions, baseline='COW', candidate='SHEEP',
  **projection_options)` reuses exactly the same calendar for both alternatives.
  It reports the capital and feed differences without treating wool and milk as
  interchangeable cash. A generator is materialized once, not consumed twice.
- `purchase_checkpoint(cash_before_buy, shed_units_before_buy, *,
  reserve_after_buy=0, shed_capacity=100, baseline='COW', candidate='SHEEP')`
  reports actual one-unit purchase feasibility and whether each alternative
  preserves the caller's separately estimated remaining cash obligations.

The purchase checkpoint is **after preceding unit actions and market orders**.
It is not start-of-turn cash. A sheep can be affordable yet displace another
necessary purchase: with cash 550 and a remaining obligation 100, a cow leaves
150 but a sheep leaves only 50. A full shed prevents either purchase.

## What the projection does and does not establish

Placement and visits must already be feasible in the caller's purchase → pickup
→ placement → service route. This is a counterfactual for a still-uncommitted
investment, never a conversion of an existing live animal. Missing visits do
not provide service, and omitted feed availability is zero. Future feed values
are explicit scenario inputs, not free replenishment inside a game.

Animal output follows the pinned engine: base production can happen unfed;
escape on the second consecutive unfed day happens first. A production event
resets the stored care bonus even when unfed. Today's fed CARE accrues only
after that day's production. Held output caps at six. HARVEST happens before
the day refresh, so a harvest cannot collect output that appears afterward.
The normal final executable decision is 718; production/deposit at 719 is not
credited.

Harvest receipts are **carried stock, not sales**. Cash fields remain null.
The policy must account for actual collection/deposit order, shared capacity,
market order slots, sale timing, feed opportunity cost, displaced purchases and
paired rival-supply scenarios. Use the existing T02 policy and SORREL market
scorer for those separate responsibilities; no calibrated scenario probabilities
or cash-gain claim is supplied here.

## Reproduce the completed validation

From this directory:

```sh
python -m unittest -v test_livestock_ledger
python validate_engine.py --engine-dir /path/to/engine --output replay.json
```

The default loader is the repository's existing
`revenue/kaggriculture/20260907-offline-agent/evaluate.py`. Network-isolated
runtimes can use the already published Commons Actions artifact
`10005621438` from run `34086864911` (`astra-kag-study-34086864911`). Its ZIP
SHA-256 is `06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`.
It includes flat `engine/` files and a compatible `peer/evaluate.py` loader:

```sh
python validate_engine.py --engine-dir /path/to/artifact/engine \
  --loader /path/to/artifact/peer/evaluate.py --output replay.json
```

All three official engine Git blobs are verified **before** calling the existing
loader; absent or changed files do not trigger its download path. This helper
uses the actual official unit-action, daily-refresh and purchase functions.
It does not run the artifact's older agent policies or treat their scores as
T02 results.

The completed local run in `VALIDATION.json` has 12 passing contract tests,
336 differential cases, 31,122 compared state transitions and 56 purchase
checkpoints, with zero mismatches. Its maximum single projection was 3.104 ms
including detailed traces in this cloud runtime; this is not a hosted-runtime
or full-game budget guarantee. Forty explicit service calendars and 128
independently generated calendars are each replayed for both species.
No T02 development or held game seed was used. Complete row traces are
reproducible by the command; the checked-in compact receipt includes their
canonical aggregate hash and exact source pins. These are component rule
comparisons, not W/T/L evidence or policy promotion.

## Sources and attribution

Official rules: Kaggle/kaggle-environments commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`,
`kaggle_environments/envs/kaggriculture/kaggriculture.py`, especially `ANIMALS`,
`_new_animal`, `_apply_unit_action`, `_daily_refresh_animals`, and `_commit_unit`.
The seed helper is `kaggle_environments/utils.py`, not an environment-local
utils file. Engine and loader hashes are retained in `VALIDATION.json`.

https://github.com/Kaggle/kaggle-environments/tree/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c

The implementation is independent Python code under Apache-2.0. The validator
composes the existing Commons loader and executes the pinned public engine
without edits. See `NOTICE.txt` and `LICENSE`. No engine, route tape, binary,
credential or new external dependency is vendored in this directory.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
