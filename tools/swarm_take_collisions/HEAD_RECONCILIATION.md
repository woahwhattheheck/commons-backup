# Head-first recovery for stale paid-source TAKEs

Use only when recovering a source TAKE, resolving a collision, or preparing PR publication. This offline companion to audit.py and preflight.py consumes evidence the dispatcher has **already** obtained. It does no API calls, branch changes, Slack posts, or bounty claims.

Read the tracked branch's current full SHA once. If the head differs from the previous exact full SHA, acquire an **exhaustive** changed-file list for expected..observed (set comparison_complete false for truncated or failed responses). Preserve the original owner and operation ID.

Example JSON input (one object):

```json
{
  "operation_id": "PAID-ISSUE-273", "repo": "woahwhattheheck/pocketpay-sdk",
  "branch": "fix/issue-273", "owner": "source-agent", "origin": "slack:1791441921.239279",
  "lease_kind": "source", "expected_head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "observed_head": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "claimed_paths": ["src/transactions"], "touched_paths": ["docs/CONTRIBUTING.md"],
  "comparison_complete": true, "stale": true,
  "provider_readback": "github:compare/expected...observed"
}
```

Run: `python tools/swarm_take_collisions/head_reconcile.py snapshot.json`

Possible outcomes:
- UNCHANGED_STALE / HEAD_UNCHANGED: no branch evidence of completion; check the original source owner before reassignment.
- COLLISION_RECONCILIATION: changed files intersect the claimed path scope; inspect exact content and owner receipts, do not duplicate implementation. File paths alone are not completion proof.
- VERIFIED_COMPLETION: source scope overlaps and `completion_proof: {"verified": true, "reference": "..."}` explicitly binds the accepted implementation. Retires **source lease only**; publication and compensation/claim custody are not touched.
- ORTHOGONAL_ADVANCE: fully verified path changes are disjoint; after coordination update the expected branch head for a compare-and-swap guarded non-force write.
- INCOMPLETE_EVIDENCE: missing exact head, scope, compare or provider readback; fail closed.
- SEPARATE_CUSTODY: source changes cannot retire publication ownership or bounty/claim custody.

Paths compare on directory-segment boundaries. Include original operation, repo, branch, expected+observed head, source owner, affected paths, and provider readback in the result. Never perform continuous polling.

Focused checks only: `cd tools/swarm_take_collisions && python -m unittest -v test_head_reconcile.py`
