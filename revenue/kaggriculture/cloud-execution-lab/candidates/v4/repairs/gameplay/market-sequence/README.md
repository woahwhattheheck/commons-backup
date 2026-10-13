# Market sequence: physical-zero sale lots

**Status: built and tested, not activated. The named natural panel has zero engagement.**

This is a component in the one `main:candidates/v4` workspace. It is not a
second V4, a new producer, a replacement pressure-ranking controller, or a
release. `stockless_pressure.py` delegates the existing pressure transform once,
projects that returned action's actual unit vector with the existing finite-
capacity scheduler, and stably moves only provably zero-fill sale rows behind
productive sale rows. It never observes a rival's private inventory.

All raw rows, requested quantities, positive-fill order, unit actions, economic
barriers, and the non-executable suffix are retained. Sequential stock accounting
recognizes later exhausted duplicate lots without trimming partially filled
requests. The public price curve must match the visible quote and be bounded,
finite, and nonincreasing. Nonzero operating-input sales and every capital or
purchase order prevent this extension. Deadline cancellation propagates.

## Reproduced failure and exact scope

Pinned pressure `7261674962d10fc8bc6af5ff73ff9212c40f61ad` scores requested lots,
not their physical fills. With own shed MILK10/WOOL0, parent rows SELL MILK10 then
SELL WOOL100, and a simultaneous rival SELL MILK10, it ranks nonexistent WOOL
first. The exact official engine returns own1296/rival1506 instead of
own1411/rival1411. The extension recovers +115 own cash and +210 margin in **both
seats on that constructed witness**, with unchanged private inventories.

Both normal and optimized Python pass 15 tests. Each mode executes 2,400 paired
market cases (1,240 strict margin improvements, no negative cash/margin case in
that fixed sale-only rival panel), 256 full-interpreter unit/projection cases,
768 full interpreter calls and 4,804 direct official-market calls. DROP/PICKUP,
actor order, ignored surplus hand actions, finite shed overflow, day/end-game
boundaries, duplicate exhaustion, raw caps, malformed evidence, cancellation,
input custody, baseline identity and the prospective native call site are
covered. Nine behaviorally broken variants are rejected by assertion failures
in both modes; import failures do not count as mutation kills.

**Natural evidence is negative:** one seed9600912, both seats, native artifact
factory against PASS, 719 completed callbacks per seat and 517 eligible prefixes
per seat produced **zero stockless opportunities**. Returned actions were not
modified. This is not an opponent-diverse field gate or evidence of improved
playing strength. Do not activate or request broad game panels based only on the
synthetic gain. A later real activation witness must identify its exact parent,
unit vector, shed, raw market prefix, and opponent before an economic gate.

Earlier/later cash feedback remains material: lower rival sale income can make a
rival capital purchase fail, leaving **more** terminal rival cash. Therefore a
sale-receipt timing argument is not a universal cash-margin or whole-game
certificate. Public inventory near the $1 floor also need not remain identical.
The fixed sale-only rival test panel cannot establish either broader claim.

## Reproduce without running legacy materializers

Use the already-existing GitHub Actions artifact10123395668, run34400824037.
Extract its `final-pressure-runtime/` directory without running any archive code
or replacing production files. All 14 required runtime/engine/import-dependency
pins are checked before tests. From this directory:

```sh
python test_stockless_pressure.py --runtime /path/to/final-pressure-runtime --receipt normal.json
python -O test_stockless_pressure.py --runtime /path/to/final-pressure-runtime --receipt optimized.json
python run_mutations.py --runtime /path/to/final-pressure-runtime --receipt mutations-normal.json
python -O run_mutations.py --runtime /path/to/final-pressure-runtime --receipt mutations-optimized.json
python probe_native_engagement.py --runtime /path/to/final-pressure-runtime --seed 9600912 --seat 0 --output engagement-seat0.json
python probe_native_engagement.py --runtime /path/to/final-pressure-runtime --seed 9600912 --seat 1 --output engagement-seat1.json
```

The engagement probe labels its older artifact entrypoint2e70 explicitly; it uses
only that entrypoint's factory with source-pinned native runtimeb952, not the
current complete archive, hosted runner, or current4a8c whole-call outer timer.
Its probe is observational and does not feed candidate actions to the engine.
No paid compute, Actions dispatch, Kaggle login, or online fetch is required.

`NATIVE-CALLSITE.patch` records the exact prospective edit tested **in memory**
against the whole b952 native module. It is not applied to production and is not
a general current-source installer. A future integrator must recheck the current
final-pressure boundary, current scheduler/projector bytes, enabled/disabled
identity and deadline coverage, and bind the returned action before receipts.
Never run an old r04 materializer or replace a concurrent runtime with b952.

`RECEIPT.json` preserves both-mode results, all mutation outcomes, the negative
engagement panel and source/engine hashes. Positive-lot coalescing and quote-cache
optimization remain with their existing owners; this package does not supersede
those mechanisms or license independent pressure-source rewrites.
