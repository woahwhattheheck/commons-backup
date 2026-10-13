# Exact-current base closure guard

`exact-head` and `exact-current` are different claims. Checking out a pull-request head and proving `HEAD^` equals a hard-coded historical commit establishes only the first. It does not prove that the branch contains the base tip that was live when a queued or rerun job began.

This guard is a network-free, standard-library preflight for score-facing TITAN workflows. The workflow first fetches the live base branch into `refs/remotes/<remote>/<base-ref>`. Before dependency installation or gameplay, the guard then requires all of the following:

1. strict, duplicate-key-free GitHub event JSON with a real pull-request object and matching positive PR numbers;
2. the event repository, base repository, and head repository are all the declared same repository;
3. the checked-out commit is exactly `pull_request.head.sha`;
4. the event base SHA is exactly the newly fetched live base tip, so an old workflow rerun cannot certify a stale payload;
5. the live base tip is the exact merge base and an ancestor of the checked-out head;
6. the head is zero commits behind and at least one commit ahead;
7. the worktree is clean before and after evaluation;
8. every changed path and status is inside the declared allowlist, every required path is present, and rename/copy records fail closed; and
9. the receipt binds the event bytes, logical guard source, head/base commits and trees, merge base, ahead/behind counts, and literal changed-path inventory.

A branch that still satisfies `HEAD^ == OLD_BASE` after `main` advances is a named negative control. A direct branch from the live base and a branch that merges the live base are positive controls.

## Connector-safe source carrier

The readable logical source and test suite are retained as canonical zlib/base64 payloads. Their tiny Python loaders independently bind encoded bytes, compressed bytes, decoded byte count, and logical SHA-256 before compiling anything in memory. They reject extra compressed frames, trailing data, noncanonical line shape, corruption, or hash drift. No decoded file is written to the checkout. Review reconstruction is deterministic:

```bash
base64 -d exact_current_base.py.zlib.b64 | python3 -c \
  'import sys,zlib; sys.stdout.buffer.write(zlib.decompress(sys.stdin.buffer.read()))'
```

The PASS receipt reports the decoded logical guard SHA-256; the Git head/tree and exact path inventory bind both loaders and encoded payloads.

## Invocation

```bash
git fetch --no-tags --force origin \
  '+refs/heads/main:refs/remotes/origin/main'

PYTHONDONTWRITEBYTECODE=1 python3 -B exact_current_base.py \
  --repo-root "$GITHUB_WORKSPACE" \
  --event-json "$GITHUB_EVENT_PATH" \
  --repository "$GITHUB_REPOSITORY" \
  --expected-base-ref main \
  --allow-path '.github/workflows/example-panel.yml' \
  --allow-path 'revenue/kaggriculture/example-panel/**' \
  --require-path '.github/workflows/example-panel.yml' \
  --receipt "$RUNNER_TEMP/exact-current-base.json"
```

Default changed statuses are `A` and `M`. Additional statuses require explicit `--allow-status`; rename and copy records are always rejected. `--min-ahead` and `--max-ahead` can constrain branch cardinality. The receipt is written on both PASS and ordinary fail-closed rejection; exit `0` means PASS, `1` means a guard rejection, and `2` means the failure receipt itself could not be written.

The caller must place the receipt outside the checkout. A score-facing workflow should upload it under `if: always()` and stop before package installation, engine construction, or games when the guard returns nonzero. For a long setup, fetch `main` and invoke the guard once before dependency work and again immediately before game launch; the second pass rejects base movement during setup.

## Executed local contracts

```text
loader/payload identity checks — PASS
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest -v test_exact_current_base.py
Ran 17 tests — OK
```

The contracts use real temporary Git repositories and bare remotes. They cover direct-current and merge-current acceptance; the historical-parent false green; stale rerun payload; wrong checkout; cross-repository head; non-PR and duplicate-key events; out-of-scope paths; rename, deletion, and missing-required-path rejection; ahead bounds; dirty tracked and untracked trees; deterministic receipts; and fail-receipt emission.

## Boundary

This component changes no controller, policy, runtime, configuration, canonical archive or pointer, evaluator, opponent, seed, provider, Kaggle, or submission state. It proves execution ancestry and path custody only. It does not turn a green source check into a playing-strength, integration, promotion, or leaderboard claim.
