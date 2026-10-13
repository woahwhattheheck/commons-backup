# V3 `apply_v3` transactional closure

Operation: `TITAN-V3-APPLY-TRANSACTIONAL-CLOSURE-20260910-01`

This additive handoff repairs one exact source-integrity defect in the authenticated V3 one-tree packet. It does not select gameplay features, alter the canonical export, publish the one-tree branch, run games, or touch Kaggle/provider state.

## Defect

The upstream `apply_v3.apply(path)` contract says it edits an extracted package in place and exact-anchor mismatches fail loudly. Its write order violates the fail-closed half of that contract:

1. render and write `titan_runtime.py`;
2. render and write `scheduler.py`;
3. only then validate the `frozen_selected.py` anchor;
4. later still validate the configuration collision set and release note.

A normal base mismatch can therefore return an exception while leaving executable files from two incompatible package generations in one directory. `HISTORICAL-WITNESS.json` records a real source-bound reproduction: the exact upstream integrator changes runtime and scheduler, then fails at the frozen seller anchor.

## Repair

`apply_v3.py` is a drop-in replacement for upstream SHA-256 `8e109342…4436`. Policy constants, injected methods, exact anchors, config defaults, and release prose are byte-for-byte unchanged. Only the application boundary changes:

- read all five targets before rendering;
- reject non-regular targets and invalid UTF-8 before mutation;
- render and validate all exact anchors, JSON, and key-collision constraints in memory;
- stage every new file and exact original-byte backup beside its target;
- preserve each target mode;
- replace only after the complete staged set exists;
- on any synchronous `BaseException`, restore committed targets in reverse order;
- leave an explicit backup only if rollback itself cannot complete;
- remove stage/backup residue after success or complete rollback.

Portable filesystems do not provide one syscall that atomically exchanges five unrelated files. The repair therefore makes every expected validation failure and every synchronous commit failure rollback-safe; it does not overclaim crash atomicity.

## Verification

```text
python -W error::ResourceWarning -m unittest -v test_transactional_apply.py
13 tests, all pass
python -m py_compile apply_v3.py upstream_apply_v3.py test_transactional_apply.py
pass
```

The contracts include:

- legacy predecessor: late frozen-anchor failure leaves runtime and scheduler modified;
- repaired late frozen-anchor failure: exact five-file identity;
- repaired late config collision: exact five-file identity;
- injected staging `fsync` failure: exact identity and no residue;
- injected third-replacement `KeyboardInterrupt`: reverse rollback to exact bytes;
- successful five-file closure with Python parse, config assertions, and mode preservation;
- second application fails before mutation;
- missing target, invalid UTF-8, and symlink target fail before mutation;
- authenticated upstream hash and policy-constant equality.

## Integration

The one-tree owner can replace `candidates/v3/apply_v3.py` with this file or apply `APPLY_V3_TRANSACTIONAL.patch`, add `test_transactional_apply.py` to the candidate checks, rebuild the source manifest, then rerun the exact pinned-base build and all-off identity gate. The owner retains publication, composition, gameplay, promotion, provider, and Kaggle custody.
