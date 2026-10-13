# Swarm pre-claim fence — offline dry-run transcript

The transcript below mirrors the same pure evaluator used by the live read-only helper. No GitHub or Slack mutation is performed. Unsafe states return nonzero exit codes, so a caller can hard-block branch creation. SAFE requires a complete owner-PR census in addition to the other absence evidence.

## Executable entrypoint

Run the read-only fence through the repository entrypoint from any working directory:

```bash
./host/swarm_preclaim_fence.sh \
  --owner-fork woahwhattheheck/commons \
  --target upstream/repo#842 \
  --stable-id operation-key \
  --candidate-path src/fence.py \
  --semantic-token fence \
  --json
```

The wrapper resolves the sibling `swarm_preclaim_fence.py`, forwards every argument unchanged, and returns the evaluator's exact exit code. Set `PYTHON=/path/to/python` to select a specific interpreter. Current evaluator outcomes are `0` (`SAFE_TO_BIND_BRANCH`), `20` (`OWNED`), `21` (`ALREADY_ABSORBED`), and `22` (`NEEDS_MANUAL_DIFF`).

To replay an already-collected report without network access, pass its path explicitly:

```bash
./host/swarm_preclaim_fence.sh --offline-report /path/to/report.json --json
```

`--offline-report` is a path-valued option, not a boolean flag. The current evaluator has no `--show-evidence` or built-in `--self-test` switch; use `--json` for the machine-readable decision and the focused entrypoint tests for the five representative offline decision cases.

## A — exact target custody beats empty stable-id search

```text
Decision: OWNED
Branch writes allowed: NO
Exit code: 20
Slack evidence:
  stable_id_hits: 0
  exact_target_hits: 1
    - build-demand | 1 | TAKE SOURCE+MERGE upstream/repo#842
  path_semantic_hits: 0
Owner PR census: complete=True open=0 hits=0
Owner snapshot: owner/repo main@owner-head tree=owner-tree
Upstream snapshot: pull upstream/repo#842 head=donor-head changed=1
Blob comparisons:
  src/fence.py: owner=def upstream=abc status=modified match=False comparable=True
```

Decision JSON:

```json
{
  "decision": "OWNED",
  "branch_write_allowed": false,
  "exit_code": 20
}
```

## B — owner already contains donor blob

```text
Decision: ALREADY_ABSORBED
Branch writes allowed: NO
Exit code: 21
Slack evidence:
  stable_id_hits: 0
  exact_target_hits: 0
  path_semantic_hits: 0
Owner PR census: complete=True open=0 hits=0
Owner snapshot: owner/repo main@owner-head tree=owner-tree
Upstream snapshot: pull upstream/repo#842 head=donor-head changed=1
Blob comparisons:
  src/fence.py: owner=abc upstream=abc status=modified match=True comparable=True
```

Decision JSON:

```json
{
  "decision": "ALREADY_ABSORBED",
  "branch_write_allowed": false,
  "exit_code": 21
}
```

## C — owner differs from donor

```text
Decision: NEEDS_MANUAL_DIFF
Branch writes allowed: NO
Exit code: 22
Slack evidence:
  stable_id_hits: 0
  exact_target_hits: 0
  path_semantic_hits: 0
Owner PR census: complete=True open=0 hits=0
Owner snapshot: owner/repo main@owner-head tree=owner-tree
Upstream snapshot: pull upstream/repo#842 head=donor-head changed=1
Blob comparisons:
  src/fence.py: owner=def upstream=abc status=modified match=False comparable=True
```

Decision JSON:

```json
{
  "decision": "NEEDS_MANUAL_DIFF",
  "branch_write_allowed": false,
  "exit_code": 22
}
```
