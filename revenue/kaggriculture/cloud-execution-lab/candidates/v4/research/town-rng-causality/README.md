# V4 town-RNG causal regression — existing harness support

**State: recovered for publication into the canonical V4 workspace.**

Proposed destination in the sole canonical V4 workspace:
`revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/town-rng-causality/`

This is one research/test extension for the existing RNG3 and counterfactual
harness lanes. It is not a new agent, V4 branch, policy controller, or feature key.
No runtime, materializer, default, release archive, or submission was changed.

## What is established

The source-pinned engine consumes one `rng.random()` per currently empty tile
on both farms before using that same daily RNG for the shop draw. The existing
RNG3 donor already documents this mechanism. This package supplies actual-engine
state-dependent-offset witnesses and an observational trace collector, rather
than claiming that mechanism is new or replacing RNG3's boundary map.

At seed **0**, step **71**, both fixtures have the same initial market and cash:

| Player action | Weed RNG calls | Next shop |
|---|---:|---|
| PASS | 50 | YARN_STORE |
| PLANT TOMATO | 49 | ICE_CREAM_SHOP |

The action changes occupancy and therefore the shop draw, while immediate market
state and both players' money remain equal. This reproduces at either seat with
weedSpawnChance=0 or the standard 0.005. Setting weed probability to zero does
**not** eliminate weed RNG draws. Skipping the weed loop is not an equivalent
performance optimization.

Across seeds 0..255, 164/256 one-turn fixture pairs change the shop. Repeating the
panel at both seats and both weed settings gives the same count in each cell.
These are **256 distinct seeds and 1,024 fixture cells, not 1,024 independent
seeds or full games**. The fixtures are deliberately paired midgame states, not
recovered competitive-match trajectories.

## Existing counterfactual harness: adoption contract

The 20:43 EDT Slack announcement describes bit-exact RNG checking for two agent
trees. Its announcement cites local files, and the GitHub code search in this
session returned no counterfactual.py source. Consequently this is an independent
regression package, **not a claimed patch or source audit of that implementation**.

Use an A-vs-A replay as the exact reproducibility control. With different policies,
retain the official engine's state-dependent RNG and report the first shop/RNG
exposure divergence; do not automatically classify that divergence as nondeterminism.
`TownAudit` records post-refresh, pre-weed exposure for each farm, then the actual
shop result. It does not change the seed, substitute draws, or freeze the town.
`compare_traces` rejects empty, truncated, misaligned, missing, duplicate, and
skipped-day records, and reports rather than suppresses policy-induced divergence.

A same-seed score gain remains a valid **total policy effect** when shops change.
It is not, by itself, evidence that planting less improves direct crop economics.
A deliberately fixed-town intervention can diagnose direct effects, but is not an
unaltered official-engine match. This matters to the reported two-seed seed-hoard
result; the package does not claim to have rerun those original games.

No online seed-recovery or future-shop prediction mechanism is supplied. Seeds in
these tests are offline fixture inputs only. The earlier shop-steering audit's
hidden-seed limitation remains intact.

## Supporting actual-engine tomato witness

A full **719-callback PASS-vs-PASS** season at seed **7040**, using standard
configuration including weedSpawnChance=0.005, naturally draws:

`PIZZA_SHOP, PIZZA_SHOP, PIZZA_SHOP, PIZZA_SHOP, FARMERS_MARKET, PIZZA_SHOP, FARMERS_MARKET, PET_CAFE`

The first pre-market tomato quote at least $1,470 is **$1,491 at step 685**,
with public tomato inventory **9,271**. The peak executable pre-market quote is
**$1,803**. Both players finish with **$3,000**, because they only PASS.
This is proof that a large tomato-price window exists in the pinned simulation,
**not a TITAN profit gain**, competitive field result, or a claim that the same
seed will give the same shops under TITAN's different board occupancy.

A peer claimed the separate `tomato-scarcity-window` math lane at 21:59:39 EDT.
To avoid a second implementation, the earlier local price-bound helper was removed
from this package. Only this exact interpreter witness is retained as supporting
evidence for that existing owner.

## Run

Python standard library only. Tested on Python 3.13.5.

From this directory in the canonical repository, the default source lookup finds
`cloud-execution-lab/reference/engine/kaggriculture.py`:

```sh
python test_town_rng_audit.py -v
python -O test_town_rng_audit.py -v
python town_rng_audit.py --output RESULTS.json
```

For an explicit engine location:

```sh
python test_town_rng_audit.py --engine /path/to/kaggriculture.py -v
python -O test_town_rng_audit.py --engine /path/to/kaggriculture.py -v
python town_rng_audit.py --engine /path/to/kaggriculture.py --output RESULTS.json
```

The standalone ZIP includes the unchanged pinned engine, its configuration specification and license, so the
same commands work offline. The Git patch does **not** duplicate that engine in
the repository. A loader-only import shim rejects framework initialization;
all tested game transitions execute the unchanged pinned engine functions.

To instrument an existing single-threaded replay with a dedicated engine module:

```python
from town_rng_audit import TownAudit, compare_traces

with TownAudit(engine) as audit_a:
    run_existing_replay(engine, tree_a, seed)
with TownAudit(engine) as audit_b:
    run_existing_replay(engine, tree_b, seed)
comparison = compare_traces(audit_a.events, audit_b.events)
```

The helper intentionally does not create agents, configure a virtual clock, or
replace the existing counterfactual runner.

## Evidence and custody

Engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.
Recovered from existing GitHub artifact **10285621024**, source checkout
`8250aec877974e9a1feba2b8e33fcd51000857d4`. A subsequent read of main's engine
returned the same blob. No new Actions job was dispatched.

Prior RNG3 donor: `36a90365add6757d8e0896e2ef7de031d46d4c49`.
Existing counterfactual announcement: `#titan-kaggriculture`, TS
`1789173805.617209`. Earlier shop-steering audit: TS `1789168334.975199`.

Results: **25/25 tests normal; 25/25 under python -O; py_compile PASS**.
`TEST-RECEIPT.json` and the two test logs preserve the original execution evidence;
run `town_rng_audit.py --output RESULTS.json` to regenerate the full deterministic
report from the pinned engine.

Publication is intentionally additive under the sole canonical V4 workspace. The
source-search miss for the existing counterfactual runner is a custody gap from the
original build session, not proof that its author abandoned it.
