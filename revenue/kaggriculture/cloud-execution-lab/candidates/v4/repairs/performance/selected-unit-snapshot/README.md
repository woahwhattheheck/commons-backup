# Selected-unit snapshot copy elision

ASTRA-QUARRY. One canonical V4 component under `main:candidates/v4`.
This package is built and locally executed, **not production-promoted**.
It adds no gameplay key, controller, cache, default, archive, workflow or submission.

## Change

Current `TitanAgent._selected_snapshot` deep-copies the observation, then discards
the copied own farm and private state in favor of the already-certified selected
unit pair. `selected_unit_snapshot.py` instead copies only retained root/farm
edges with a shared deepcopy memo. Rival/public data remain detached. Retained
aliases into the old own/private objects still receive their ordinary copies;
the new selected pair remains borrowed exactly as before. Root/farms cycles,
dictionary order, nested Struct types and PASS/ordered/binding authority are
covered. There is no cross-call state and no change to unit mechanics.

This is not a shallow observation copy or a global memo substitution of old own
objects with new ones. Both shortcuts are demonstrably wrong and are mutation
controls. Non-plain root dictionaries and farm-list subclasses use the exact
old operation. Native inputs have string keys and JSON-shaped descendants;
side effects of custom `__deepcopy__` implementations reachable only from
otherwise discarded edges are outside that native-data contract.

## Reproduce

Use the existing GitHub workflow artifact `10175943272` (run `34537404363`), not
a new Actions dispatch. Its `checked-package/exports/titan-current.tar.gz` is
429604 bytes, SHA256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
Safely unpack it to a local directory and export that **absolute** path:

```sh
export TITAN_PACKAGE=/absolute/path/to/unpacked/titan-current
python test_selected_snapshot.py && python -O test_selected_snapshot.py
python test_selected_snapshot_engine.py && python -O test_selected_snapshot_engine.py
python check_snapshot_mutations.py
python benchmark_selected_snapshot.py --loops 150 --repeats 7
```

No network access or installation is performed by these commands. Missing or
changed fixtures fail, rather than skip. The suite authenticates the exact
SOURCE.json SHA256 and all 109 runtime-map members, then checks the runtime blob.
The unchanged existing evaluator/loader supplies the pinned official engine.
Execution here used CPython 3.13.5; no Python 3.11 execution is claimed.

## Executed results

26 graph/current-class/composer tests plus 2 engine/native-opening tests passed
normally and with `python -O`: **28/28 per mode**. The graph suite includes 1000
randomized alias/cycle cases, ordered root edges, both seats, Struct containers,
input detachment and intentional pair identity. Six executable wrong copy
implementations were rejected by behavioral assertions in each mode.

Per engine-suite mode: 144 constructed selected-snapshot continuation pairs,
532 official interpreter calls, 192 actual native FinalPressureAgent.act calls
covering 96 paired opening callbacks (seeds 9922999 and 9922023, both seats,
24 callbacks per cell), 640 observed snapshot calls, and 256 selected-pair branch
engagements. Returned actions and snapshot graphs agree; both classes report
completed status throughout. Actual default native collaborators are used.
These are bounded component/opening checks, **not full games or hosted tests**.
The native-class test uses actual `main._new_instance`, but not the outer
`main.agent` entrypoint wrapper. It preserves raw returned hand rows.

Snapshot-only microbenchmark: seven alternating-order repeats of 150 calls per
arm; median microseconds below. GC is not disabled. Pair creation is outside
both timed arms. These are environment-dependent timings, not full-agent gains.

| Fixture | Predecessor | Candidate | Speedup |
| --- | ---: | ---: | ---: |
| Official engine initial observation | 87.597 | 44.411 | 1.972x |
| Constructed dense own farm | 491.455 | 45.332 | 10.841x |
| Constructed dense both farms | 864.091 | 406.786 | 2.124x |
| Retained aliases into old own/private graphs | 906.472 | 852.702 | 1.063x |

`benchmark.json` preserves all timing samples. `EXECUTION.txt.gz` preserves
exact dedicated and native-slice unittest output (read with `gzip -dc EXECUTION.txt.gz`). The fourth fixture deliberately
requires copying the old graphs: correctness takes priority over copy elision.

An additional unchanged 84-test native slice was run on separately materialized
parent and composed packages in both modes:

```sh
PYTHONPATH=.:checks python -m unittest checks.test_feed_stock checks.test_crop_release checks.test_idle_fertilizer checks.test_terminal_history_join
PYTHONPATH=.:checks python -O -m unittest checks.test_feed_stock checks.test_crop_release checks.test_idle_fertilizer checks.test_terminal_history_join
```

All four executions have the identical **82 passes, one failure and one error**:
`test_prelude_fallback_returns_and_sells_already_collected_unit` expects SOUTH
but the parent returns PASS; imported
`test_t08_pending_whole_lot_and_observed_carry_have_separate_accounting` lacks
`checks/reference/selected-action/t08/arrival_contract.py` in the supplied
archive. This is not an all-green repository claim. Existing lifecycle/fixture
owners retain those issues; this component does not rewrite unrelated sources.
An initial invocation omitted `checks` from PYTHONPATH and was superseded by
these corrected, fully enumerated 84-test runs.

## Compose exactly once

The composer changes only the final three lines of `_selected_snapshot` and
adds its helper import. All admission/binding/ordered/PASS gates remain exact.
It requires runtime blob `b952c9c228ecbde592bf3d2df01638677abb0d24` and produces
`650f63b524c96e177e17ab8ceeb93f71f3c9fdaa`. It refuses drift, reapplication,
same-path and existing-output writes. For a fresh scratch file:

```sh
python compose_selected_snapshot.py "$TITAN_PACKAGE/titan_runtime.py" /fresh/scratch/titan_runtime.py
```

Copy the exact helper beside that scratch runtime before importing it. This
command creates a component, not a complete release. Do not treat the old
SOURCE manifest as an authenticated postimage after composing a scratch package.
The sole runtime integrator must merge this small semantic seam with newer
lifecycle/seed/EOD work; never reset a newer runtime to the pinned predecessor or
run the legacy r04 materializer. Re-run exact current-package composition,
entrypoint/deadline and full-trajectory parity before production packaging.
No full-game speed, game-strength, economic improvement or activation is claimed.

`RECEIPT.json` records exact inputs, output, source/test blobs and scope. The
original FWD-BUY/EXEC-PACE intake request remains a separate transport issue:
local hash IDs did not establish accessible raw bytes; no mechanism was
reconstructed from prose and no source custody is claimed for those packets.
