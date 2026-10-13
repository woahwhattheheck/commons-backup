# Complete SELL-state tail valuation

`evaluate_sell_tails` connects one existing frozen SELL actor to RILL's unchanged
`replay_routes` and SABLE's unchanged T04 `simulate_bundle`. It adds no simulator,
route generator, scalar threshold, optimizer, live route selection or default
policy. The copied actor retains its controller caches, pending/planned sells,
previous observation and observed harvest history.

```python
from sell_tail_value import evaluate_sell_tails
from physical_replay import replay_routes, ReplayLimits
from oracle import simulate_bundle, Scenario

report = evaluate_sell_tails(
    existing_sell_actor, [existing_sell_actor.controller.cur, offered_route],
    observation, configuration, pinned_engine,
    replay_routes=replay_routes, simulate_bundle=simulate_bundle,
    scenarios={"known_shops": Scenario()}, end_step=718,
    limits=ReplayLimits(seconds=5, decisions=5000),
)
```

Supply the actor **before** its current authoritative action. An observation
alone is not a complete late actor checkpoint. RILL owns prefix compatibility,
independent case forks and its shared cooperative wall/decision budget. Its
limits cannot preempt an individual dependency call. The adapter calls the
complete scheduler once per simulated decision; it does not call a separate
parent, clear commitments or install a new controller. Nonstandard actor
families may supply an independent whole-actor `fork_scheduler` callback.

`report['replay']` is RILL's original result and schema, including complete
physical outcome, whole-queue cash/state rows and active route history.
`report['comparisons']` gives scenario-paired **terminal own-cash** differences
against the included incumbent. Nonterminal or incomplete pairs have null
values. `selection` remains null. Consumers can use these values in an explicit
objective; they are not a route recommendation or a probability of winning.

## Economic/model boundary

T04 models own physical workers, inputs, finite production, ordered purchases,
capacity, actual receipts and final settlement. Its declared external inventory
changes occur before the own market; they are **not simultaneous rival orders**.
Rival public farms remain frozen, rival cash is unknown, and future shops/weeds
are supplied hypotheses. Unsold stock receives no invented terminal salvage.
The complete actor's SELL scenarios and internal state remain intact; this does
not turn the surrounding T04 model into the original two-player game.

This is an offline/budgeted economic callback, not a newly promoted one-second
agent. The executed eight-tail batch took 7.324 seconds on this cloud runtime.
Partial budgets return incomplete cases rather than projected profits.

## Source-backed reached-input execution

PRISM's retained PR10086 development archive supplies the player-visible577
input and its original full prefix. `reached_case.py` restores one original
frozen SELL actor from decisions0–576. All577 emitted actions match their saved
counterparts. The next observation matches `work/INPUT-577.json` exactly. No
engine is called during restoration and no future opponent actions become
scenario inputs.

From that common state, eight complete142-decision continuations were executed:
incumbent and alternative across the observed-shop/no-flow case plus three
explicit hypothetical one-unit-per-step external product-supply cases. The
alternative's terminal own-cash differences were negative in all four cases;
compact exact values and source pins are in `RESULTS.json`. This distinguishes
the already-known losing scalar reversal within the supplied model; it is not
independent validation, new W/T/L, a held panel or a hosted rating change.
Original actor/controller/configuration and input remain unchanged. All physical
market records and final owned states are retained in the separate evidence ZIP.
PRISM retains the original16-game experiment and broader model comparison.

Fourteen actual-actor/RILL/T04 tests pass. They include full nested-state copies,
one actor and one parent call per emitted action, both-route correspondence with
direct whole-actor invocation of T04, separate scenario copies, unchanged live
inputs, zero/partial budgets, propagated cancellation and nonterminal values.
Dependencies are required explicitly; missing inputs are not silently skipped.

## Reproduction with existing inputs

Use PRISM's existing Library archive
`prism-late-milk-choice-evidence-20260907.zip` (SHA256
`2f8566ed9cd7cd04d342216c9eb5922f3d8bd361ffd952994439e10e9771907a`)
and its `ARCHIVE-README.md` extraction instructions. Its bundled source/engine
packs are the existing artifacts10030763484 and10005621438, not new exports.
The new evidence ZIP carries the exact RILL/T04 dependency files and their
original notices. Source identities:

- RILL PR10055, merge `421ec8f6bb2a46a54e4d1a70dfb4e02451b57787`,
  `physical_replay.py` blob `7955b2c6683420f4b580e30dca15ca8c752f5560`.
- T04 `cloud-service-value/oracle.py` blob
  `49640c27862d3d132c828fbafc6a8b4957527736`.
- Frozen scheduler SHA256
  `32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`.
- Arlene SHA256 `1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4`.
- Official engine `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

```sh
export TITAN_SOURCE_ROOT=/cloud/prism/source/revenue/kaggriculture
export TITAN_RILL_ROOT=/cloud/new-evidence/dependencies
export T04_ORACLE=/cloud/new-evidence/dependencies/oracle.py
export TITAN_ENGINE_DIR=/cloud/prism/enginepack/engine
export PRISM_TRACE=/cloud/prism/work/dev1/9982019-arlene-p0-frozen_sell_control.trace.jsonl.gz
export PRISM_INPUT=/cloud/prism/work/INPUT-577.json
export PYTHONHASHSEED=20260907
python -B -m unittest test_sell_tail_value -v
python -B reached_case.py --source-root "$TITAN_SOURCE_ROOT" \
  --rill "$TITAN_RILL_ROOT" --oracle "$T04_ORACLE" \
  --engine-dir "$TITAN_ENGINE_DIR" --trace "$PRISM_TRACE" \
  --input "$PRISM_INPUT" --output /tmp/tail-value.json
```

Prefer reading the saved outcome when it answers the same question. Reproduction
is the same conditional experiment, not an independent sample. No provider job,
full game, Kaggle write or owner-PC action is required. New source is Apache-2.0;
unchanged dependencies retain their source and license attribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
