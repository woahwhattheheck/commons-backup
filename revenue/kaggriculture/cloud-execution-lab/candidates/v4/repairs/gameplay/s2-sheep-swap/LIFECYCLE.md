# S2 lifecycle and realized-stock repair

ASTRA-SHEPHERD delivers this component inside the existing `s2-sheep-swap` family of the sole `main:candidates/v4` workspace. This is source-only, default-OFF work. The original recovered donor and tests in this directory are preserved; the canonical donor is not overwritten, and no runtime, policy key, default, archive, workflow, or Kaggle submission is changed.

## Source contract

The composer consumes the current `candidates/v4/donor/overlay/r04_s2_sheep_swap.py`, Git blob `1e6771644ad897ec30c7420304f21c919414666a`. This parent already contains the S2-DAY complete-day cash-ownership proof and S2-PREFIX raw-market-cap repairs. Do not substitute the historical recovery blob `84b025aa9ead6bf362445ad9c3e97598c175c5fd`.

Native `mechanics.py` must be blob `044a4f9c0a4a44dde10ada57563238bcaf82075d`. The repair reuses its existing deterministic own-unit primitive instead of copying a second game simulator. The generated candidate is blob `5a8d4acbe78c2ff5a9157ce6362831f445058516`, SHA256 `bb84c00d8b732cb53288cc9561be999da0c580d3f415704de67932e29db079dd`.

`build_s2_lifecycle.py` changes only the shed projection, the worker/custody stage, and the duplicate placement-confirmation debit, then appends `s2_unit_custody.py`. The existing buy thresholds, configuration/observation guards, callback-gap reset, next-observation purchase confirmation, day proof, and raw order cap remain. Unexpected parent/mechanics bytes fail before composition. Repeating the CLI against an identical output is allowed; feeding an already-composed module as the parent is deliberately rejected.

## Repaired behavior

The unit-prefix projection follows actual actor order, animal PLACE fallback into the shed, capacity and item order, structure changes, and the interpreter's atomic PLANT census, including surplus raw worker commands. Wool credit is based on the actual projected inventory increase rather than repeatedly counting an observed tile yield.

Ownership follows real SHEEP pickups, drops, deposits, and placements. Successful placement is debited once, then confirmed on the next observation. End-of-day cleanup retires vanished hand identities and returns only a proven lower bound of retained sheep to reserved ownership.

That end-of-day lower bound deliberately ignores storage freed by sales and reserves room for every possible within-cap market deposit, including unaffordable buys. It can miss a legitimate recovery: a tested SELL-released-room control retains one sheep in the engine but credits zero ownership. This conservative false negative is not an exact end-of-day market forecast.

## Final-return consumption

The original `apply_s2_swap` remains a mutating API and must be used only when its action is actually the last accepted stage. A composing finalizer can instead use the appended one-shot receipt:

```python
proposal = s2.propose_s2_swap(
    observation, parent_action, live_s2_state,
    enabled=enabled, configuration=configuration, native_tape=native_tape,
)
proposed_action = proposal.action
# The existing finalizer chooses the actual action; this example adds no controller.
returned_action = existing_finalizer(proposed_action)
committed = proposal.commit(live_s2_state, returned_action)
return returned_action
```

The receipt rejects action substitution, type-changing quantities, live-state drift, and replay without mutating live state. A rejection consumes that receipt. The finalizer must not change the action again after committing. This is an in-process consistency contract, not a security boundary. No current native entrypoint wiring is included or claimed.

## Reproduce offline

From the repository root, with the pinned reference engine/loader already present:

```bash
ROOT="$PWD/revenue/kaggriculture/cloud-execution-lab"
PKG="$ROOT/candidates/v4/repairs/gameplay/s2-sheep-swap"
export S2_NATIVE_ROOT="$ROOT"
export S2_SOURCE="$ROOT/candidates/v4/donor/overlay/r04_s2_sheep_swap.py"
python "$PKG/build_s2_lifecycle.py" \
  --source "$S2_SOURCE" --mechanics "$ROOT/mechanics.py" \
  --output /tmp/s2-lifecycle-candidate.py
python "$PKG/test_s2_lifecycle.py"
python -O "$PKG/test_s2_lifecycle.py"
python "$PKG/check_s2_lifecycle_mutants.py"
```

The composer refuses to overwrite either input or an unrelated existing output. Use a new output path if the example path already contains other bytes. Tests fail for missing or changed inputs; they do not skip or download fixtures. The mutation runner requires the two explicit environment variables above because its isolated test copies run outside the repository hierarchy.

This execution used the already-existing native artifact `10175943272`, ZIP SHA256 `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`, containing runtime archive SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. The current donor was obtained separately, and the native mechanics blob was checked against current main. Only the explicitly listed dependencies are authenticated by this suite; this is not validation of all 109 runtime members or their combined agent.

The full official interpreter fixture is from `Kaggle/kaggle-environments` commit `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. `LIFECYCLE-VALIDATION.json` records the exact engine, JSON, utilities, and offline loader pins.

## Executed evidence

On Python 3.13.5, the 31 newly authored tests passed in both normal and `-O` modes, without failures, errors, or skips. Each full suite executed 3,479 official interpreter calls: 1,250 initializations and 2,229 completed transitions. These counts are not games. Coverage includes 720 constructed two-seat unit-prefix worlds, 480 custody worlds, positive/negative purchase and placement controls, callback gaps, inherited source-gate preservation, final-return receipt controls, and the segment below.

The repeatable mutation runner first reruns both complete green suites, then rejects eight deliberately broken semantic variants in each mode. Each of the 16 targeted runs fails through a behavioral assertion, with zero test errors; syntax/import failures are not accepted as evidence.

### Constructed asset-recovery segment, not a field gate

Each seat was tested with 248 callbacks per arm, the same authored action sequence, a PASS opponent, and a constructed midgame state containing one already-owned sheep on a departing hand. The parent strands that sheep after day-end cleanup. The repaired continuation picks it back up, places it, and harvests 10 wool. After liquidating remaining WHEAT and WOOL, parent cash is 3,974 and candidate cash is 6,014: a 2,040 increase in each seat. The parent retains an unplaced sheep; the candidate has the placed productive asset. This is a causal asset-recovery witness, not equal-terminal-asset EV, natural engagement, a complete game, or competitive strength evidence.

The original historical 19-test donor file was not executed by this contribution and is not included in the 31-test claim. Current `main.py::agent` composition, Python 3.11, natural/competitive full games, whole-agent deadline or performance measurements, and production activation remain NOT_RUN. Preserve the OFF state until the existing single native composer performs its current-source and field gates.
