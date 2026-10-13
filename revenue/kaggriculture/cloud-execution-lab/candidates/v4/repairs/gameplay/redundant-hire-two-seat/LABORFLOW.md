# ASTRA-LABORFLOW — multi-hand productive-detour convergence

This component extends the **existing** canonical V4 `redundant-hire-two-seat` repair family; it is not a new controller, runtime, V4 tree, or HIRE cadence.

## Why this lane exists

The current `reference/titan-current/redundant_hire.py` already contains the right economic primitive: before deleting a trailing redundant HIRE, it can certify one complete same-day `spawn -> harvest -> shed DROP -> exact route rejoin` job whose current observed marginal value exceeds that hand's exact wage. The implementation then stops after the first successful certificate with an unconditional `break`, so at most one otherwise-redundant hand can be converted into useful work even when several disjoint profitable jobs exist.

The live 2026-09-11 hire-cadence experiment made the missing link visible: adding labor without adding bound work collapsed all 96 candidate games below $100k. LABORFLOW therefore does **not** add blind HIREs. It only lifts the existing one-job ceiling inside the already-conservative redundant-hire proposal.

## Composition contract

`compose_laborflow_multi_detour.py` first executes the already-tested sibling `repair_redundant_hire_two_seat.py`, so the malformed public-seat fail-close repair is preserved. It then applies six exact anchors to that postimage:

1. pass cross-job reservations into `_productive_detour`;
2. reserve cumulative shed capacity for prior certified harvests;
3. reserve same-item public market units when valuing later jobs, preventing duplicate marginal-price credit;
4. refuse a second certified DROP on the same tick;
5. continue certifying a **contiguous prefix** of trailing redundant workers instead of stopping after one success;
6. expose reservation counts in the existing report.

A missing certificate still stops the loop immediately. This matters: only the latest suffix of HIRE orders is removed, so protecting a non-contiguous later worker could renumber actors and invalidate route indices. LABORFLOW never skips an uncertified earlier worker to save a later one.

Distinct harvest targets were already enforced by the parent `reserved` target set. Existing parent guards still reject touched targets, route switches, later HIREs, unbounded shifts, unaffordable current hires, shed overflow, expiry before harvest, concurrent pre-deposit DROP / shed PLACE, and pre-deposit product or animal purchases. No future sale, next-day persistence, opponent response, or terminal gain is credited.

## Disposition

**Source-ready research component; no runtime/default/config/archive/Kaggle activation in this commit.** The full current source transform remains Git-blob pinned through the sibling two-seat transformer (`9ded2a9... -> a58ba34...`) before these additional exact anchors are allowed to run.

The existing `idle-hands` donor is intentionally not merged here: its FIR economics probe produced a real -$76 counterexample in both seats for one WHEAT-fertilize activation. `spatial-hire-prefix` remains THISTLE's HIRE-boundary correctness lane; `jit-all-actors` remains fertilizer occupancy correctness. LABORFLOW only generalizes the already-profitable harvest/deposit/rejoin certificate.

## Focused tests

```bash
python -B test_compose_laborflow_multi_detour.py
python -O -B test_compose_laborflow_multi_detour.py
```

The tests prove exact-anchor drift rejection, cumulative capacity/quote reservations, same-tick DROP exclusion, contiguous-prefix actor stability, and wrong-input Git-blob fail-close. Current-native two-seat economics remain the activation gate; this package itself does not claim a competitive uplift.
