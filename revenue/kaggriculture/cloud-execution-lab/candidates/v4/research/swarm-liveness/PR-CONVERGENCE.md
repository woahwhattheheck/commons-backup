# PR ↔ Main Convergence Classifier

`pr_main_convergence.py` is a read-only companion to the swarm-liveness auditor. It answers a different question: given **explicit, already-fetched** PR postimage blob identities and verified current-main path identities, is a carrier already present on main, a new additive delta, an overlap requiring review, or missing enough evidence that no conclusion is safe?

It never talks to GitHub, never merges or closes a PR, and its output is not write authority. A live connector must re-fetch PR state and current main before any mutation.

## Evidence contract

The input is one JSON document. `main.files` is a coverage map, not a repository listing: every PR path being evaluated should be present. A string is the verified current-main Git blob identity; `null` means the connector verified that path is absent. A missing key means **not checked** and therefore produces `INSUFFICIENT_EVIDENCE`, never `UNIQUE_DELTA`.

```json
{
  "schema_version": 1,
  "canonical_base": "main",
  "main": {
    "ref": "main@<fresh-sha>",
    "files": {
      "path/already.py": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "path/new.py": null
    }
  },
  "prs": [
    {
      "number": 12755,
      "state": "open",
      "base": "main",
      "head": "<fresh-head-sha>",
      "intent": "agent-index-hardening",
      "files": {
        "path/already.py": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    }
  ]
}
```

Blob identifiers must be lowercase 40- or 64-hex strings. Paths must be canonical repository-relative POSIX paths.

## Classifications

- `EXACT_ALREADY_ON_MAIN`: every supplied PR postimage blob exactly matches the freshly verified blob at the same path on main.
- `UNIQUE_DELTA`: every PR path was freshly verified absent on main.
- `PARTIAL_OVERLAP_REVIEW`: main has a different blob on any PR path, or the PR mixes already-present and absent paths. This deliberately demands review.
- `INSUFFICIENT_EVIDENCE`: any PR path lacks current-main coverage, the PR file map is empty, or the PR targets a noncanonical base.

Open carriers with exactly the same path→blob map are reported as `exact_duplicate_groups`. Optional normalized `intent` labels can surface `intent_overlap_reviews` when two open PRs declare the same intent but carry different postimages; those are never called duplicates automatically. This is the distinction between the byte-identical #12749/#12755 race and the conceptually overlapping but non-identical #12750/#12764 race.

## Safety boundary

The emitted policy object pins the invariant: `decision_authority=false`, `auto_close=false`, `auto_merge=false`, and `requires_live_reverification_before_write=true`. The classifier is routing evidence for CONSOLIDATOR/INTAKE, not a substitute for current GitHub state, CI, ownership, composition, or reviewer judgment.

Run:

```bash
python -B pr_main_convergence.py evidence.json
python -B -m unittest -v test_pr_main_convergence.py
python -O -B -m unittest -v test_pr_main_convergence.py
```
