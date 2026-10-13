# TITAN V4 lockstep raw-phase certificate

Research-only extension of the existing `research/lockstep-scale/` authority. It does not add a controller, runtime key, default, package, composition node, opponent classifier, or activation path.

## Engine fact

Pinned official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

`_process_market` truncates each player's raw market list to the executable prefix and then resolves equal raw indexes across players in lockstep. `_parse_order` accepts `BUY_PRODUCT` syntax generally, but the market executor quotes/commits `BUY_PRODUCT` only for `WHEAT` and `FERTILIZER`. Consequently, moving an existing executable WHEAT/FERT acquisition across a raw slot can change which rival row it shares a quote/commit phase with even when requested quantity and every other row remain unchanged.

This is the same raw-index fact that makes generic compaction unsafe. The new certificate uses it in the opposite direction: it proves a deliberately tiny *phase-only* edit without deleting or compacting anything.

## Certificate boundary

`raw_phase_contract.py::certify_adjacent_buy_phase()` admits only an exact one-slot swap between:

- one literal `['BUY_PRODUCT', item, quantity]`, where `item` is `WHEAT` or `FERTILIZER` and `quantity` is a plain positive integer; and
- one adjacent literal no-op (`None`, `[]`, or `['PASS']`).

The raw market list must retain the same length. Every other raw slot and every non-market field must remain exact under type-preserving canonical JSON. Both source and destination slots must stay inside `max(1, maxMarketOrdersPerTurn)`. Non-adjacent motion, cap crossing, queue compaction, extra BUY tokens, other market verbs, unsupported products, malformed quantities, type-poisoned caps, nonfinite evidence, and unrelated field drift fail closed.

A passing certificate remains `conditional_only=True` and `activation_authority=False`. It does **not** prove a rival row, requested-quantity completion, fill, funding, shed capacity, future need, or episode value. Those are downstream full-interpreter/economic obligations.

## Authored-route census boundary

`raw_phase_census.py` authenticates the canonical R01 tape bank `a43289b9cc5e34a2481fddf652762a7d92f427ef` and router `35541da59f23a161105245c98841acda4bb376f9`. Tape bytes are captured/authenticated once and those same bytes are compiled only to call the data-only `load_tapes()`; router bytes are captured/authenticated once and structurally parsed for literal route constants without executing router policy.

The census models the authored R01 splice: plan 0 before step 144, the selected reachable plan through step 647, forced plan 2 from step 648 through step 717, and no tape authority at step 718 because router `liquidate()` replaces the tape action.

**This is not current-native reachability.** Every report states `current_native_reach_authority=false` and `candidate_surface="authored_r01_tape_pre_transforms"`. A positive coordinate means only that the authenticated authored R01 tape surface contains the certified adjacent BUY/no-op shape before later current-native transforms. Zero coordinates is a valid falsifier. Any live-engagement claim requires a separate final-return/current-native census.

## Equal-horizon full-interpreter controls

`raw_phase_engine_controls.py` consumes the existing lockstep full-interpreter harness by exact Git blob `eedbb09261c0bc3a11d33a34e0d50b81139ddb98` and its pinned official engine `3c202c7ee921da239356789e266b694635103fc4`.

The controls compare one official callback against one official callback only: delay an existing WHEAT buy behind a rival same-callback WHEAT sell; advance an existing WHEAT buy into the rival WHEAT-buy phase; and a no-rival-market-order phase-shift control. There is deliberately no synthetic wait or next-callback baseline. They remain constructed research controls, not opponent prediction, current-native reach, or activation authority.

## Exact authored-byte gate

Current focused surface:

- `raw_phase_contract.py` Git blob `45df2f3eb2dc53720f2bdcaa795f04dddd88aa17`
- `test_raw_phase_contract.py` Git blob `0aaa560eb0a3dff8af93730f741660349ad858de`
- `raw_phase_census.py` Git blob `1a87a1c971735810deac5062f8e34e6b9f7f0600`
- `test_raw_phase_census.py` Git blob `0634a052d561a8a1b8f4ae906b046f5057a5cd20`
- `raw_phase_engine_controls.py` Git blob `d8b75ccbac0c7657aab8946a9116ba8b22726537`
- `test_raw_phase_engine_controls.py` Git blob `1a131193641bd5462c38e98e69f154ffdde37389`

Exact connector-authored/fetched bytes pass `32/32` tests under normal Python, `32/32` under `python -O`, and `py_compile`. This is a source/shape receipt only; it is **not** the outstanding repo-mounted R01 census or full-interpreter execution receipt.

## Next evidence

Run the source-pinned authored R01 census. If it yields candidates, separately census the final current-native returned actions before considering any gameplay seam. Independently execute the equal-horizon official-interpreter controls in both seats. A source certificate with zero authored reach, zero final-return reach, or failed constructed controls is a research result, not a reason to mint another scheduler.
