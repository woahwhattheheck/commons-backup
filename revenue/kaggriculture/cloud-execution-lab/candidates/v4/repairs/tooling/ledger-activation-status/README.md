# TITAN V4 ledger activation-status salvage

Coordination/tooling-only salvage from the earlier ledger reconciliation. This package does **not** change gameplay, runtime, defaults, composition, CURRENT/archive, or Kaggle state.

## Live defect bound

At intake, canonical `candidates/v4/check_integration_ledger.py` was Git blob `6b82182488ee45a353aa57d907cde2e514c3a79f`. Its retired/NO_BUILD conflict check classifies landed rows as active by substring membership over `("default_off", "promoted", "active", "enabled")`. That makes `default_off` positive by definition and lets `active` match inside `inactive`; statuses such as `not_runtime_promoted` also carry a positive `promoted` substring.

The earlier local reconciliation had already built and exercised a token-aware claim parser. `status_claims.py` recovers only that still-relevant helper against the current checker generation. Historical-gap custody and lane-reopening edits from the old patch are deliberately **not** replayed because current main already supersedes them.

## Contract

`claims_activation(status)` returns true only for an unnegated whole token `promoted`, `active`, `enabled`, or `activated`. It returns false for non-strings, `default_off`, `inactive`, and `not_(runtime|production)_promoted`/other explicit negations.

A canonical checker consumer should replace substring-based active-status detection with this predicate only after re-reading the live checker preimage. Do not replace the checker wholesale with the historical patch.

## Local gate

Run from this directory:

```bash
python test_status_claims.py
python -O test_status_claims.py
```

The package itself is source-only until the root checker consumes it. No activation/runtime authority is created by landing these files.
