# Verification receipt

Parent operation: `titan-v3-paired-game-gate-20260909-sol-argus-02`

Hardening operation:
`titan-v3-paired-game-gate-snapshot-binding-20260909-sol-kiln-01`

## Executed on the hardening bytes before publication

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
  python3 -m unittest -v test_validation.py test_policy_cli.py

Ran 27 tests in 1.413s
OK
```

```text
python3 -m compileall -q .
PASS
```

The added race contract snapshots a valid candidate file and then truncates its
original path before parsing begins. The gate still reports the SHA-256 and byte
count of the preimage and evaluates that same preimage. This directly exercises
the prior hash-then-reopen time-of-check-to-time-of-use defect.

The example and test fixtures are synthetic interface evidence only. No official
game, hosted run, Kaggle submission, leaderboard query, runtime mutation,
archive replacement, or promotion action was performed.

## Adversarial coverage

The test suite proves fail-closed behavior for:

- missing, extra, duplicate, failed, and timed-out cells;
- baseline failures as well as candidate failures;
- non-finite values, numeric overflow, malformed score cardinality, and invalid
  seats;
- duplicate JSON object keys, boolean schema versions, and duplicate seed
  declarations;
- omission of either candidate seat;
- provenance mismatch and terminal symlink substitution;
- replacement of an original input after its single-open snapshot;
- a positive global cash mean hiding a W-to-L regression;
- a positive global cash mean hiding a negative opponent stratum;
- an unchanged candidate when change is required;
- a worst-cell loss beyond the frozen policy floor;
- deterministic repeated reports and atomic CLI output;
- stable exit 0 (`PROMOTE`), exit 2 (`INVALID`), and exit 3 (`REJECT`).

## Explicit non-claims

- No candidate gameplay strength was measured.
- No statistical confidence or holdout generalization is claimed.
- No policy thresholds are asserted to be universally correct.
- No release pointer or canonical Titan artifact is changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
