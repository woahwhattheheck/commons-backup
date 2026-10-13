# F1: native conversion of fertilizer that would otherwise spill

Status: source, source-bound native composition, engaged engine controls and native census implemented. Default OFF. Main is the sole V4 integration line. ASTRA-REKINDLE's source claim is complete when this package is merged; this is not a second agent or submission.

## What changed

The original F1 donor (#12596, `4a91b3d10d51c1c5aaadfe08df40d497b3523403`) could only dispatch an extra fertilizer hand registered by the old R04 parent. A ship-stack run in which that parent never hired could not test F1. The exact two donor modules are preserved under `legacy/`; they are evidence, not executed by this native variant. Do not run their materializer on the current ABI. This package is distinct from the existing WF1/S1 yield-credit module.

`f1_spill.py` removes the extra-hand dependency for a bounded new opportunity: an existing worker, carrying fertilizer, is literally PASSing on eligible WHEAT at hour 23. It changes at most that one action to FERTILIZE, and only when the last carried fertilizer unit is certified to be discarded by the imminent end-of-day transfer. It does not hire, buy, move, replace parent routes, shift market rows or create a cross-turn obligation.

`discarded_tail` takes the exact post-unit private state and final market rows. It retains raw slot admission and insertion/worker order. The sum of all admitted requested product SELL quantities bounds the most shed space any fills could release. Buys cannot increase that bound. If the inventory prefix through the last focal fertilizer unit exceeds even this maximum free space, removing that unit cannot alter the admitted end-of-day inventory. Unsupported inputs fail closed. Entry-full storage alone is NOT a certificate: a same-turn SELL can free room.

The candidate's own-unit projection must equal the parent's except for exactly one fertilizer consumption and the intended crop coverage field. Later WATER/HARVEST interactions that violate this condition are rejected. The future yield screen is optimistic: it is not a promise that future WATER, HARVEST, storage admission or sale will occur.

## Native integration

`compose_native.py` is a test-tree composer, not a production materializer. It verifies the entire native runtime blob `b952c9c228ecbde592bf3d2df01638677abb0d24`, scheduler `a483b24dd72b580d7d8811636b54d2d44f391575`, and mechanics `044a4f9c0a4a44dde10ada57563238bcaf82075d`. It refuses source drift and existing output directories. Its output runtime is `aeeee8bbde8f76f42f17aa2253a2575093cfb25d`.

The existing `r04_fert_mix` key is false by default, requires an actual boolean, and requires the native frozen consumer. The hook is AFTER final market guards/pressure and BEFORE route/history receipt commits inside `_finish_production`. Its changed action gets a fresh exact post-unit snapshot and matching consumer binding. Deadline fallback and owned crop, delivery, spatial and quadrant plans preserve the parent. Empty pending bookkeeping alone does not block an otherwise idle worker. Existing ignored commands for non-existent actors are preserved, not executed or treated as extra workers.

Current native assembler owns combined-stack activation. Do not replace a newer runtime with the complete pinned output. Reconcile this small finalizer seam with current owners, retain their final market guards, and rerun a source-bound combined gate. Do not apply both an outer-return hook and this native finalizer hook.

## Executed evidence

23/23 tests pass in normal Python and `-O`; each suite makes 533 full interpreter calls and 1,213 direct ordered-transfer conservation comparisons. Eight behavioral mutants are assertion-rejected in each mode, with zero mutant errors. Faults cover tail boundary, ignored SELL space, compacted slots, sorted inventory keys, ignored earlier workers, unit-stage collateral, stale snapshots and rejected inherited extra actor rows.

A legal initialized grower trajectory executes BUY, optional real HIRE, PLANT, WATER, FERTILIZE, HARVEST, DROP and filled SELL in both seats with the farmer and a hired hand. It uses seed 17 and **startingMoney=5000**, not the default bankroll. No assets, workers or mature plants are injected in this trajectory. Only step 23 changes. End-of-day private state is identical at spend; later harvested WHEAT increases 2 to 3 and cash increases by $26 in all four cells. This is a 53-callback configured witness, not default-stack or competitive field EV. Separate constructed-state tests cover immediate conservation and later storage/sale behavior.

The full native panel uses the checked `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9` archive from workflow artifact 10175943272, not a claim about every current-main component. All 110 archive files were compared byte-for-byte; composed arms change only runtime/config and add the exact helper. Seeds 17/101, both seats, and baseline/OFF/ON total 12 completed games against the official starter: 8,628 completed native callbacks, zero fallbacks, identical returned-action/state hashes and scores in all four triplets. **Zero certified spill proposals.** That panel is unengaged evidence, neither a kill nor economic promotion. Full games were run in normal Python, not `-O`. Maximum call times are diagnostics, not a performance certification. Full replay streams are represented by hashes, not retained JSON traces.

`VALIDATION.json` contains source pins, execution summaries, configured witness cells and native results. `EXECUTION.json.gz` contains the full JSON receipt: unit logs, all 110 archive member blobs, 16 mutant outcomes and all 12 native rows/configs. Read it with `gzip -dc EXECUTION.json.gz`. The official engine/JSON/utils and loader are authenticated before import by the executable tests and runner.

## Reproduce

From this directory, use the extracted authenticated checked archive as `$NATIVE`; choose new sibling scratch paths `$OFF` and `$ON`.

```sh
python -B test_f1_spill.py --native "$NATIVE"
python -B -O test_f1_spill.py --native "$NATIVE"
python -B mutation_controls.py --native "$NATIVE" --output mutations.json
python -B compose_native.py "$NATIVE" "$OFF"
python -B compose_native.py "$NATIVE" "$ON" --enabled
mkdir -p results
for seed in 17 101; do
  for seat in 0 1; do
    python -B field_gate.py --native "$NATIVE" --seed "$seed" --seat "$seat" --output "results/base-$seed-$seat.json"
    python -B field_gate.py --native "$OFF" --seed "$seed" --seat "$seat" --output "results/off-$seed-$seat.json"
    python -B field_gate.py --native "$ON" --seed "$seed" --seat "$seat" --output "results/on-$seed-$seat.json"
  done
done
```

Promotion still needs a genuinely engaged native/composed setup, actual harvested/admitted/sold incremental units and paired whole-game economics. Do not manufacture spare fertilizer by forcing an uneconomic hire or purchase. Additional yield can itself crowd future storage; immediate input conservation does not settle that future tradeoff. No production/default/archive/Kaggle change is included here.
