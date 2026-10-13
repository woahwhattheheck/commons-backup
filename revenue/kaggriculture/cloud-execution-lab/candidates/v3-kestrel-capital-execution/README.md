# KESTREL — rival-lockstep-safe early capital

This is an isolated Titan V3 candidate for the already-enabled `early_capital`
callsite. It is not a selector, canonical release, score claim, or upload gate.

## Why this successor exists

The official engine does more than execute one player's queue in isolation:

1. it truncates each queue to `maxMarketOrdersPerTurn`;
2. it resolves both players at each queue index;
3. same-index product units use one pre-commit market quote;
4. cash, shed capacity, hires, and public inventory change between indices; and
5. unit actions first atomically block every same-crop PLANT request when total
   demand exceeds the seed ledger.

The original KESTREL candidate correctly fixed active-prefix membership and
proved its proposal against exact own-side market primitives. Two semantic gaps
remained: its standalone post-unit fallback replayed PLANT actions sequentially,
and an own-only market proof could not cover rival price movement.

The exact price counterexample is small. With own cash $900, one FERTILIZER,
FERTILIZER inventory 9870, WHEAT inventory 10000, and a rival buying two WHEAT
units at index zero, the predecessor accepts:

```text
BUY_PRODUCT WHEAT 1, BUY_LAND, SELL FERTILIZER 1
    -> SELL FERTILIZER 1, BUY_LAND, BUY_PRODUCT WHEAT 1
```

The original fills WHEAT and misses LAND. The proposal lands, leaves $26, then
misses WHEAT after the rival raises its quote to $27. That is an own execution
regression even though the isolated replay is green.

## Admission theorem

`kestrel_early_capital.py` remains the proposal and public-state own-replay gate.
`lockstep_early_capital.py` is the candidate runtime successor. A changed active
prefix is admitted only when all of the following are true:

- active-prefix membership and the inactive tail are unchanged;
- the queue contains exactly one `BUY_LAND` or `BUY_ANIMAL` order;
- every other effectful row is a `SELL` of a product rivals cannot buy;
- requested sale units for each product move no later at every prefix;
- the sole capital order is the last effectful candidate row; and
- the pinned public price curve is nonincreasing across the complete two-shed
  supply bound.

Counting sale rows is not enough: swapping a ten-unit sale with a one-unit sale
can move nine units later while preserving row counts. The successor checks
cumulative requested units per product.

For the admitted shape, each own sale unit sees no more preceding rival supply
than before. Rival actions cannot remove those products, and extra supply only
moves their checked price curves downward. Cash and freed shed capacity before
the single fixed-cost capital order therefore cannot be worse than the original
under the same hidden rival queue. No effectful own order follows capital, so an
extra capital execution cannot steal resources from work the original executed.

This proves **own-turn non-regression**, not universal capital gain. An exact
second witness freezes that boundary: three one-unit CARROT sales predict LAND
against the public market, but a rival's legal 100-CARROT sale can erase the
local gain. Both queues still miss LAND, and the earlier-sale candidate ends
with no less own cash. Paired official games remain the strength gate.

## Atomic post-unit binding

When FrozenSelected provides a captured completed post-unit pair, the candidate
uses it. Otherwise the wrapper:

- aggregates farmer and hand PLANT demand by crop;
- converts every over-demanded crop request to PASS; and
- only then applies the official extracted unit primitive in unit order.

One WHEAT seed plus two WHEAT requests consequently plants zero, matching the
official interpreter rather than the predecessor's sequential one-plant replay.

## Exported-entrypoint containment

The first merged KESTREL packet proved the theorem but carried an invalid game
entrypoint. Its hand-copied loop constructed raw `KestrelTitanAgent`, bypassing
the canonical local `FinalPressureAgent` and the canonical whole-call deadline,
fallback, stale-selection, reconstruction, and interrupted-instance destruction
contract. The 27-test semantic receipt therefore remains useful for the theorem
only; it is not paired-game evidence.

`candidate_main.py` now copies no entrypoint control flow. It exact-loads the
canonical source-tree `main.py` and exports that module's `agent` function object
itself. The candidate changes only construction:

1. verify the live `titan_runtime.TitanAgent` object is the exact predecessor
   base of `KestrelTitanAgent`;
2. under a process-local lock, substitute `KestrelTitanAgent` for that one
   factory symbol;
3. call the unchanged canonical `_new_instance`, causing its local
   `FinalPressureAgent` to be defined directly over KESTREL;
4. restore the predecessor symbol in `finally`; and
5. reject construction unless the resulting MRO is exactly
   `FinalPressureAgent -> KestrelTitanAgent -> TitanAgent`.

Canonical function globals still own `_INSTANCE`, the outer deadline timer,
terminal/PASS fallback, seller fallback receipt, readiness invalidation, and
partial-instance destruction. Canonical final pressure still runs after the
KESTREL early-capital call exactly once and remains suppressed at its old
in-pipeline position.

`test_candidate_entrypoint.py` loads the carrier with the candidate directory
absent from `sys.path`, constructs the real MRO, proves factory restoration on
success and exception, checks KESTREL-before-pressure ordering, invokes the
exported canonical function in the ordinary path, and trips the real outer timer
to prove current selected fallback, stale-selection clearing, and reconstruction
via `_INSTANCE = None`.

## Files

- `kestrel_early_capital.py` — unchanged predecessor proposal and own replay.
- `lockstep_early_capital.py` — atomic unit reconstruction and lockstep theorem.
- `candidate_runtime.py` — candidate-only early-capital override.
- `candidate_main.py` — exact canonical-entrypoint delegation and factory-only
  KESTREL carrier.
- `test_kestrel_early_capital.py` — original adversarial contracts.
- `test_runtime_binding.py` — captured-snapshot and atomic-fallback binding.
- `test_kestrel_lockstep_repair.py` — pinned-engine rival witnesses, PLANT
  discriminator, sale-unit ordering guard, and positive single-capital case.
- `test_candidate_entrypoint.py` — real exported-entrypoint/MRO/deadline tests.
- `reproduce_predecessor.py` / `PREDECESSOR-RESULTS.json` — predecessor receipt.
- `PANEL-HANDOFF.md` — frozen gameplay instructions; still HOLD until this
  containment head receives exact CI and independent readback.

## Verification

From `revenue/kaggriculture/cloud-execution-lab`:

```bash
python -m unittest -v \
  candidates/v3-kestrel-capital-execution/test_kestrel_early_capital.py \
  candidates/v3-kestrel-capital-execution/test_runtime_binding.py \
  candidates/v3-kestrel-capital-execution/test_kestrel_lockstep_repair.py \
  candidates/v3-kestrel-capital-execution/test_candidate_entrypoint.py

python candidates/v3-kestrel-capital-execution/reproduce_predecessor.py \
  --check candidates/v3-kestrel-capital-execution/PREDECESSOR-RESULTS.json

python -m py_compile \
  candidates/v3-kestrel-capital-execution/*.py
```

Candidate entrypoint:

```text
candidates/v3-kestrel-capital-execution/candidate_main.py::agent
```

## Promotion boundary

Do not interpret any KESTREL game run made through the superseded hand-copied
entrypoint. Do not copy candidate bytes into canonical `early_capital.py`
independently. Canonical source, `exports/titan-current.tar.gz`,
`CURRENT-SOURCE.json`, and `CURRENT-ARCHIVE.json` are one build-coupled
publication.

This containment branch must first pass its exact exported-entrypoint workflow
and independent MRO/deadline readback. Promotion then requires a fresh-main
collision audit and a complete winning paired panel through this repaired
entrypoint. No Kaggle upload is authorized by this candidate.
