# EOD interval rescue — existing V4 key, no second agent

Owner: ASTRA-INTERVAL. Claim: Slack `1789177904.696329`.
Existing mechanism: PR #12612, `r04_eod_capacity_rescue` (default OFF).
Integration destination is `main:candidates/v4`, per `CANONICAL.json`
blob `00142be0ff2314dcb23068c8133b34d290661923`.
ASTRA-EOD-ENGINE retains the full-engine/package integration lane.

## What the whole-vector restriction misses

A shed contains 48 WHEAT and 48 WOOL; one actor carries 5 of each.
The baseline has four free slots, so the full discarded product vector
varies with inventory-key order. Donor `9ad40924...` correctly declines
that whole-vector proof. Nevertheless, selling **one WHEAT and one WOOL**
creates two slots and yields exactly the same final private shed as the
baseline, for either key order. The extra sold units would otherwise be
lost. The implementation also handles safe smaller rescues when later
products lack shed stock or the remaining raw market slots are limited.

This is a constructed executable witness, not an observed replay activation
or a competitive-strength result.

## Proof and bounded implementation

Let `A(t)` be the admitted cargo vector when the shed has `t` free slots.
A sale vector `R`, with `k = sum(R)`, preserves private shed composition iff
`A(r+k) - A(r) == R` for every within-actor key order. This is the cargo
stream interval `[r, r+k)`; actor list order is never permuted by the solver.

For a product block, every possible start is the sum of a subset of the
other product quantities in that actor. The proof checks the block's
intersection with the interval at every such start. All intersections
must agree. Independent actor orders cannot cancel a variable contribution.
The solver searches lengths downward, selecting the largest feasible
**unit count**, not the largest expected cash or competitive margin.

There are at most 100 lengths and 256 subset starts per product for the
nine official products. Cargo is never expanded into individual units.
A defensive 256-actor bound is an implementation limit, not an engine fact.
Positive animal cargo, malformed quantities, unrecognized items, inadequate
stock, ambiguous intervals and insufficient slots fail closed.

## Consumption on the existing helper

`donor_9ad40924.py` preserves the exact completed whole-vector donor blob.
`compose_eod_interval.py` authenticates that donor and this solver, then
changes exactly one vector-selection assignment in the existing helper's
executable body and appends the pure proof. It adds no import dependency,
wrapper, feature key, runtime default or installation path. Existing
configuration, EOD timing, cargo/market neutrality, actor, price, stock,
raw-slot and output-copy guards remain in the executable body.
The old whole-vector helper is retained for predecessor tests.

From this directory:

```sh
python -B -m unittest -q test_eod_interval test_eod_composition
python -O -B -m unittest -q test_eod_interval test_eod_composition
python compose_eod_interval.py donor_9ad40924.py /tmp/r04_eod_capacity_rescue.py
```

Output must not exist. Expected composed helper Git blob:
`d31f5c8d97100a75e17a6a393e7c663363a70909` (14,778 bytes).
If the whole-vector donor has changed, rebase the same semantic delta
explicitly; do not strip its newer guards or bypass the byte pin.
Do not execute the legacy V4 materializer against the production runtime.
Preserve composition order `M1 -> EOD -> B10 -> C5`.

## Executed evidence and limits

32 tests PASS under normal Python and `python -O`. Included are 4,027
exhaustive interval cases, 2,592 stock/slot-constrained optimizer cases,
1,575 single-product cases and 400 seeded worlds. They test independent
permutations, full private-state conservation, both seat labels, floor-price
sales, failed-guard identity, nonmutation, reapplication identity, exact
source scope and exclusive output creation.

`engine_oracle.py` contains literal `_commit_unit` and
`_drop_inventories_to_shed` excerpts from official engine blob
`3c202c7ee921da239356789e266b694635103fc4`. This is not execution of the full
interpreter. Component tests explicitly double H3c/router dependencies;
AST comparison independently checks unchanged predecessor code.

Old tests that unconditionally forbid every partial vector must distinguish
the new proved cases from genuinely unsafe partial sales. Do not weaken
stock, raw-slot or conservation assertions. Full-package/full-engine
validation and a paired economic gate remain outstanding. Earlier cash and
public-market supply may alter rival outcomes; private-state equality is
not economic noninterference. No default activation, archive replacement,
Kaggle action, hosted-CI success or leaderboard improvement is claimed.
