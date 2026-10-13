# V4 scheduler action-prefix repair

Status: implemented and component-tested source repair in the sole `main:candidates/v4` workspace. Not wired into the production runtime, not a new V4 branch, and not an economic promotion.

## Defect and repair

The pinned engine truncates each market queue before parsing any row: raw positions at or beyond `max(1, maxMarketOrdersPerTurn)` cannot execute. Main's exact scheduler `a483b24dd72b580d7d8811636b54d2d44f391575` nevertheless lets suffix SELLs contribute to current baseline quantities, future reference quantities, full-prefix offered capacity, and final pending/planned retirement. The output loop also rewrites those inert rows.

For example, with cap 1, shed CARROT=5, market `[[], ["SELL", "CARROT", 5]]` and a future five-unit plan, the predecessor treats the inert sale as current execution and clears the pending inventory and plan. The repair preserves both raw rows, records five units still pending, and retains the future plan.

`scheduler_action_prefix.py` uses one shared prefix helper for six consumers: cash reserve, receipt projection, current baseline quantities, future reference quantities, offered-capacity admission, and pending/planned retirement. Output assembly preserves capped suffix values without parsing them and uses the same minimum-one cap for appends. It does not compact, shift, or truncate the returned raw market vector.

## Existing work composed, not replaced

The exact original two-consumer donor `5e8f54ca20fa755bc6ced55decdcdf0193cda812` is preserved as `upstream_two_consumer_donor.py`, for provenance only. Its shared helper and cash/receipt-loop changes are included here. Do not run both transformers sequentially.

That donor targets legacy scheduler `da1b6fb571e79ba7dab54c8d816e45afb934e4d2`, not current main. This package deliberately targets the newer `a483b24d` source and retains its uncapped current-unit capacity accounting and optimizer pruning. The legacy source also has an extra current-market preloop in `receipt_profile`; the old two-loop transform must not be mistaken for complete closure of that older source.

`scheduler_before.py` preserves exact reviewed predecessor bytes. The transformer rejects any other input, including an already-repaired source; it never imports the scheduler. The generated postimage is derived, not a second runtime authority. No legacy `apply_v4.py` is executed.

## Reproduce

From this directory, using Python 3.10 or later:

```sh
python test_scheduler_action_prefix.py
python -O test_scheduler_action_prefix.py
python scheduler_action_prefix.py scheduler_before.py > /tmp/titan-scheduler-action-prefix.py
python -m py_compile /tmp/titan-scheduler-action-prefix.py
```

The negative-control commands intentionally exit 1:

```sh
python test_scheduler_action_prefix.py --predecessor
python -O test_scheduler_action_prefix.py --predecessor
```

The transformer writes only to stdout. Never redirect stdout over its input or over a live production file. For integration, compare the then-current source, port the semantic changes into that source, and validate the resulting package instead of replacing a newer scheduler with this frozen predecessor.

## Executed validation

Local exact-source results: 33/33 tests passed in normal Python and 33/33 under `python -O`. This includes a 108-cell suffix-equivalence matrix over caps 1/3/10, prefix quantities 0/2/5, six inert row shapes, and current/future placement. Both predecessor runs executed 27 mechanism test methods and failed with 65 assertion failures and 32 errors across subcases. The test errors include deliberately malformed suffixes reaching predecessor parsers. Source and test compilation passed.

The suite executes the actual scheduler's AST-extracted `post_units`, `_order_spend`, and `SellScheduler` definitions. External controller, quote/economic optimizer, and mechanics dependencies are explicit deterministic test doubles. These are component and source-preservation results, not full official-engine, materialized-package, hosted-CI, replay, paired-score, latency, or leaderboard results. The official engine's `_process_market` source was inspected directly; its full engine was not executed by this suite.

The scope does not claim general malformed-prefix handling, realized-sale feedback, purchase affordability parity, terminal-settlement changes, or a measured economic gain. Pricing/optimizer definitions and unrelated scheduler methods remain AST-identical. Production files, exports, feature defaults, checker/workflow files, legacy refs and Kaggle state are unchanged by this package.

Coordination: existing salvage PR #12643, claim comment 5642669842. Consume this one repair package; do not create a sibling scheduler/V4 carrier.
