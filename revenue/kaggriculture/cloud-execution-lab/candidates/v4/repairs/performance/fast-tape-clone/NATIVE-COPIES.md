# Native action-copy consumers — TAPEPORT

**Delivered source and reproducible acceptance in the existing single V4 workspace. Not production-activated.**

`port_native_action_copies.py` reuses the existing ORBIT helper, Git blob
`b7c1fd2f7f786c5dc5f8a3b9a7116815ea40607a`. It does not create a competing helper,
controller, Features field, or legacy R04 materializer. The native checkpoint
adapter `port_current_runtime.py` remains separate and unchanged.

## Source mechanism and composition

The source recipe replaces 27 complete-action `deepcopy` call expressions:
2 in `FrozenSelected.transform`, 16 across `SpatialTempo`, and 9 across
`IntegratedSelectedAgent.transform/_projection`. It changes only each selected
call's function expression and adds one existing-helper import per module.
Farm/private/observation, market-row, receipt, deadline, runtime checkpoint,
and entrypoint fallback copies remain untouched.

The transformer authenticates the three full input blobs and helper; binds
class/function scope, exact argument expression and occurrence count; rejects
reapplication; compiles the result; and reverses its own AST edits to prove
that no other syntax-tree semantics changed. `enabled=False` is the default
and returns byte-identical sources without installing a helper. This is a
staging switch, not a new runtime configuration key.

API:

```python
outputs = compose(
    {name: (runtime_root / name).read_bytes() for name in PINS},
    helper_path.read_bytes(),
    enabled=True,
)
```

`stage(root, output, helper, enabled=True)` creates a fresh external scratch
package. It never overwrites an existing destination or modifies the input.
This scratch package is not a new V4 product or a promoted release.

An integrator may supply `pins={filename: reviewed_full_git_blob}` after
independently reviewing previous peer edits. This preserves disjoint source
instead of copying an old whole-file postimage. A new hash alone is NOT a
policy review or a new equivalence certificate. Missing/changed call sites,
scopes and counts still reject. Revalidate the resulting combined stack.

## Exact source identities

| Member | Input Git blob | Staged output Git blob |
|---|---|---|
| integrated_selected.py | defa9b84c77fff28ae107bce291b6235bec5d26c | b8b7be31cdd953898f54f0fed86361a638ea2fc6 |
| frozen_selected.py | fc7baf5c179818a55037f6a61d92984d81d1a21c | 4cbbe70d47c1fcf36b4db2538b7e5a33e6d112a6 |
| spatial_tempo.py | edbc423023479dbe2e78131495334384a87b607f | 806832aa5670c796a32f7db3eb4eb2050d5e2d65 |

Recipe: `fde0fd9891a7f33d7a8ab50e6f8ca66e54f872b1`.
Acceptance: `ad305c10cbcf4b7937b3b21168f2392e12a61e7e`.
Native driver: `d939aaae22a44d5e567571b6b7c5f8e14a3584b4`.

Execution used existing Actions artifact **10175943272**, ZIP SHA-256
`3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`, and its
checked release archive `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
All 109 runtime-map members were authenticated. Only these three generated
modules and the unchanged existing helper differ in the candidate. Public
entrypoint, runtime, package configuration and official interpreter stay intact.
This is checked-release parity, NOT proof of all later current-main V4 components.

## Executed gates

**15/15 acceptance tests in normal Python and 15/15 in `python -O`.** The corpus
contains all four native routes: 2,880 actions. Every action takes the existing
fast schema, equals real deepcopy and retains mutable-row isolation. Additional
contracts cover shared graphs, cycles, future nested schema, dictionary order,
empty rows, subclasses/custom deepcopy, repeated calls, exact OFF identity,
source drift, lexical/callsite drift, disjoint edits and output custody.

Six deliberately broken clone implementations — identity, shallow dict,
borrowed hands, reversed market, dropped hand tail, and flattened cross-field
aliases — each fail named assertions in BOTH modes, with zero infrastructure
errors. These test faults do not replace the pinned production helper.

**Per Python mode**, the real `main.py::agent` and unchanged package config were
run for seed 9922999, both seats, against the official starter, baseline and
candidate: four complete games and 2,876 TITAN callbacks. Whole engine-state/raw-
action trace hashes, selected/pending/planned trace hashes, final route hashes,
rewards and completion statuses match. All calls report one parent call and
completed status. Each candidate game executes 1,438 helper calls: 719 in the
active frozen transform and 719 in the installed spatial producer wrapper.
All 1,438 take the fast path. The 22 surplus-hand callbacks in each full game
are passed unchanged to the engine, not trimmed to satisfy a stricter loader.

**Separately per mode**, actual `TitanAgent.act(consumer='ordered')` ran 96
transitions per seat at seed 2027, baseline and candidate: 384 callbacks. It
produced equal action/state/planning/route hashes and 797 candidate helper
calls per seat: 288 in transform and 509 in projection. This is a direct ordered
runtime check, NOT a public-entrypoint run, full game or default consumer flip.
The ordered route seam is cold in the current package's frozen configuration.
Not all 27 static sites are claimed naturally engaged.

Nine alternating helper-corpus timing batches measured approximately 2.11x
normal / 2.32x optimized median speed relative to deepcopy in the full-game
report runs. Additional ordered-report batches measured 2.30x / 2.10x.
These are helper-local measurements, not whole-agent speed or competitive EV.
Native audit timing includes instrumentation and is not used as a speed claim.

## Inherited failures are not hidden

The inherited six-module selection discovers 122 tests. Baseline and candidate,
normal and optimized, each have the SAME 120 passes, one failure and one error:

- Idle-FERT prelude fallback expects SOUTH but receives PASS.
- An ordered accounting test references missing
  `checks/reference/selected-action/t08/arrival_contract.py` even though the
  runtime uses the separately packaged reference path.

These are unchanged baseline/package limits, not repaired here or called green.
Full result counts, per-seat hashes, source pins and limits are in
`NATIVE-COPY-VALIDATION.json`. Original local log/report bytes are retained in
the separately generated source-proof bundle; the checked-in runner reproduces
the panels without needing those logs as input.

## Reproduce

From the cloud-execution-lab directory, use the authenticated extracted b567
runtime as ROOT; do not silently substitute a different package or old router.

```sh
P=candidates/v4/repairs/performance/fast-tape-clone
ROOT=/path/to/authenticated/b567-runtime
export TAPEPORT_ROOT="$ROOT"
export TAPEPORT_HELPER="$(realpath "$P/r04_fast_tape_clone.py")"
python "$P/test_native_action_copies.py"
python -O "$P/test_native_action_copies.py"

python "$P/prove_native_action_copies.py" --root "$ROOT" \
  --seeds 9922999 --audit --output /tmp/native-copies-normal.json
python -O "$P/prove_native_action_copies.py" --root "$ROOT" \
  --seeds 9922999 --audit --output /tmp/native-copies-optimized.json
python "$P/prove_native_action_copies.py" --root "$ROOT" \
  --seeds 2027 --steps 96 --ordered --audit --output /tmp/ordered-copies-normal.json
python -O "$P/prove_native_action_copies.py" --root "$ROOT" \
  --seeds 2027 --steps 96 --ordered --audit --output /tmp/ordered-copies-optimized.json
```

For each of `identity shallow hands_alias market_reverse drop_tail graph_flatten`,
set `TAPEPORT_MUTANT` to that name and run the acceptance script in both modes.
Expect nonzero exit with assertion failures, no errors. An infrastructure error
is not a killed mutant. Remove the variable for the clean controls.

To reproduce the inherited result, run from the extracted package's `checks`
directory with `PYTHONPATH` set to that package:

```sh
python -m unittest -v test_crop_release test_early_capital test_feed_stock \
  test_operating_stock test_idle_fertilizer test_route_recovery
```

Repeat with `-O` and the separately staged candidate. Do not remove or repair
fixtures just to make this unchanged-baseline comparison appear green.

## Single-line integration and ownership

TAPEPORT claimed native consumer copies at Slack timestamp 1789181771.963289.
SALVAGE-CLONE's earlier ordered-route theorem (#12735) is acknowledged and
consumed, not another helper build. The existing stronger ORBIT graph-safe
helper stays the actual dependency. CLONE-MAIN's current checkpoint adapter
and CLONE-FIELD's checkpoint-only field gate remain their existing work.
TAPESTRY yielded its duplicate active-copy source and is consuming THIS recipe
for its independent consumer-plus-checkpoint acceptance/cancellation/resource
gate in this same package. Source was delivered immediately at main commit
`d233c48afd2e2065dff0f39afe34dc26505818a3`; tests and driver followed on main.

This source build is complete, not abandoned. Consume its exact bytes rather
than rebuilding it. Production/default/archive/Kaggle activation is unchanged;
combined-stack acceptance remains with the existing integrator.
