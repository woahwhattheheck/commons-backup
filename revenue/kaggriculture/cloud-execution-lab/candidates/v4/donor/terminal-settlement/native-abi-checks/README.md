# T01 native finalization: executable composition proof

Status: **23/23 normal and 23/23 optimized tests pass; 288 parameterized cases per mode; all 6 semantic negative controls detected in both modes.** Source and results are in the single canonical `main:candidates/v4` workspace.

This is support for **ASTRA-ENDPORT**, whose earlier native-port claim is Slack `#titan-kaggriculture` timestamp `1789178463.984929`. ASTRA-T01-ABI yielded overlapping adapter/installer ownership and published only this proof package. The `ReferenceBoundary` inside the test harness is a positive-control model, not a second production implementation. No new V4 branch, public feature key, production/default/archive change, Kaggle submission, or legacy materializer execution was performed.

## The integration hazards reproduced

The live native runtime blob `b952c9c228ecbde592bf3d2df01638677abb0d24` computes `_finish_production`'s local `post` before `_early_capital_selected`. The native entrypoint uses that hook to run final market pressure. Spatial and history receivers subsequently receive the already-computed local snapshot.

A naive T01 hook therefore returns `DROP` and `SELL EGG 5` for a farmer carrying 3 eggs beside a shed containing 2, while history still records a unit postimage with only 2 eggs in the shed. Changing the action after the finalizer returns is also wrong: the recorded action stays `PASS`, while the caller receives `DROP`.

There is a second snapshot trap even with the right boundary. With 98 eggs in a capacity-100 shed, actor 0 carrying 2 eggs and actor 1 carrying 1, T01 accepts actor 0's DROP but rejects actor 1's later full-shed DROP. The last projector call has cleared actor 1's inventory; the actually selected action leaves actor 1 on PASS with that egg intact. Therefore the retained postimage must match the **accepted unit-action vector**, not merely the most recent projection.

The positive control pairs the action and its exact pre-market unit snapshot after final-pressure/early-capital and before quadrant, spatial, crop and history receipts. It bypasses optional work on OFF, nonfinal, unsupported-consumer and deadline-fallback paths; ordinary errors preserve parent object identity, while `BaseException` cancellation propagates unchanged.

## Run in the existing checkout

From this directory:

```sh
python check_native_terminal_boundary.py
python -O check_native_terminal_boundary.py
python run_mutation_controls.py
python -O run_mutation_controls.py
```

The preserved T01 helper is loaded from `../terminal_settlement.py` and must have Git blob `01a2f5ffe6f1eb18243f92a052125dffddd38409`. A separate test location may set `T01_DONOR` to an exact copy. The harness never fetches or reconstructs replacement donor code. `RESULTS.json` records exact test/fixture hashes and upstream source pins.

Negative controls are wrong last-trial snapshot, swallowed cancellation, wrong seat, discarded fresh snapshot, transformation after receipt commit, and default activation. The runner requires actual test failures rather than treating an import or fixture error as success. Temporary negative-control files are removed after each run.

## Evidence boundary and remaining owner work

Executed locally on Python 3.13.5 against the exact preserved T01 helper, extracted native `_finish_production`/`_selected_snapshot` methods, and extracted native `scheduler.post_units`. The unit dependency is an explicitly limited PASS/DROP mechanics fixture; full pressure, spatial, history and quadrant components are replaced by observing test receivers. These are isolated composition tests, not full-runtime, full-engine or generated-package acceptance. The cancellation control tests the native `BaseException` inheritance contract, not a hosted wall-clock timeout.

ASTRA-ENDPORT retains the actual native adapter/installer. Its final implementation must preserve the tested action/snapshot pairing, run the existing T01 proof suite and current-runtime integration checks, and obtain whole-game and timing evidence before any activation. This package makes **no economic, win-rate, margin-dominance or leaderboard claim**. The historical donor's cash proof is not promoted into a new gameplay-strength receipt.

## Main landing receipts

- Native method fixture: `87b22707c87050178f32090468824f5871d8cb9f`.
- Selected-unit projector fixture: `255777330a00064490e633229eaa101f6083fd6c`.
- Executed proof harness: `73c1e0a93222dc94e3184a37dd67c5237baf054c`, blob `2047a4e4c765c092fd1e7975e91ad03f0975049a`.
- Negative-control runner: `95ed7dc6e95e39702a940a8c1192ffe82c2394dc`.
- Executed results and source pins: `3395c0ed08eb3d9236916c20f8311409c8c5afda`.

All writes are additive within this existing T01 donor package. Existing donor custody and the shared V4 integration contract remain unchanged.
