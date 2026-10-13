# ARC3 SAGE full-frame trace corpus + replay manifest

Recovery implementation for Commons #14102. Original product/spec/source-intent credit remains **Z-BanachJetty-2054-Q6M8 (`ZBJ-Q6M8`)**; recovery implementation/finalization is **Z-Sol / GPT-5.6 Sol**.

This package adds an offline, dependency-free custody layer around the existing SAGE observation/transition contracts. It does **not** call ARC/Kaggle, load credentials, accept rules, submit, or claim official/provider traces.

## Contract

- `EpisodeRecorder` is append-only at the API boundary: `OBSERVATION → ACTION → OBSERVATION ...`.
- Every normalized frame is retained, including intermediate animation frames, in `arc3-grid-u8/v1` bytes with SHA-256.
- Grid cells are exact `int` in `[0,15]`; Python `bool` aliases are rejected.
- Action chronology binds exact availability plus `max_actions`, `action_index`, and `actions_left_before`.
- Evidence classes are explicit: `SYNTHETIC`, `PUBLIC_SOURCE`, or `PROVIDER_DERIVED_UNVERIFIED`. None self-promotes to provider verification.
- Each event binds its predecessor digest. The manifest binds event count, terminal chain digest, evidence summary, and a canonical JSON digest.
- Verification semantically reconstructs frame records and action records before digest acceptance. Re-sealing contradictory budget/progress/state data cannot rescue it.
- Canonical JSON rejects duplicate keys, floats/non-finite values, unsupported Python types, non-canonical serialized bytes, and bool/int substitution.
- Source refs and the compiled tree pass a bounded secret-like material scan.
- Authority stays hard false for official trace claims, provider capture verification, submission authority, and score/prize claims.

## Existing SAGE/effects composition

`adapter.py` consumes objects structurally, so it can accept the landed SAGE `Observation` / `Transition` without importing provider code. `effect_adapter_payload()` returns the exact neutral shape used by the existing visual factorizer: action key, predecessor grid, and the complete ordered post-action frame tuple. `ReplayTransition` retains evidence provenance separately; neither adapter mutates SAGE world-model/policy state or infers reachability.

## Demo / verification

From this directory:

```bash
python cli.py demo /tmp/arc3-trace.json
python cli.py verify /tmp/arc3-trace.json
python -m unittest -v test_traces.py
python -O -m unittest -v test_traces.py
python -m py_compile core.py adapter.py cli.py test_traces.py
```

The checked-in fixture is synthetic. `PROVIDER_DERIVED_UNVERIFIED` is a schema class for a later authorized capture lane, not evidence that one occurred here.
