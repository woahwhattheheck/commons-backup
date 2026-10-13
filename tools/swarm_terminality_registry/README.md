# Swarm work terminality / supersession registry

This offline product converts a retained provider census into a deterministic answer to a narrow question: **is a visible work item terminal, superseded, actively owned, eligible for stale recovery, or insufficiently evidenced?**

It is deliberately separate from Muse/OneWriter outbound single-writer arbitration and from work-feed prioritization. A terminality report never grants ownership or mutation authority. It reduces rediscovery cost; an agent must still re-read live provider state immediately before changing GitHub, Slack, Muse, or any external system.

## States

- `TERMINAL_MERGED` — a current GitHub PR observation is merged.
- `TERMINAL_CLOSED` — a current issue/PR/operation observation is closed and no canonical successor edge is needed.
- `SUPERSEDED` — an explicit one-successor edge is backed by current observations for predecessor and successor.
- `ACTIVE_CUSTODY` — work is open/present and at least one retained owner heartbeat is current and unexpired.
- `RECOVERY_ELIGIBLE` — work is open/present, provider evidence is current, no active owner heartbeat exists, and no canonical successor is active.
- `HOLD_INCOMPLETE_EVIDENCE` — provider evidence is stale/future/unknown/branch-absent, successor evidence is stale, or another retained-evidence problem blocks a terminality conclusion.

`RECOVERY_ELIGIBLE` is not a lease. It means only that the supplied retained snapshot has no current contradiction to a recovery take.

## Strictness

Input rejects duplicate JSON keys, unknown fields, nonfinite numbers, bool-as-int ages, malformed IDs/digests/object IDs, unsafe source URLs, dangling refs, cross-item provider/heartbeat evidence transplants, impossible kind/state combinations, multiple canonical successors, and successor cycles. `MERGED` requires a merge object ID; present branches require a head object ID. Successor edges must cite observations bound to both items.

A semantic verifier exact-recompiles the candidate snapshot and byte-compares report JSON, Markdown, and receipt. Rewriting a classification/authority field and resealing a digest does not verify.

## CLI

```bash
python -m tools.swarm_terminality_registry.cli compile snapshot.json out
python -m tools.swarm_terminality_registry.cli verify snapshot.json out.report.json out.report.md out.receipt.json
```

Outputs are create-exclusive mode `0600`. Each file is fully written and synced in a private sibling staging directory before an exclusive hard link publishes its final name. A handled write failure removes that staging directory and leaves the failed destination available for retry; existing files and symlinks remain unchanged. The destination filesystem must support hard links.

Publication is per file. If a later output fails after an earlier file has completed, retain the completed file and use a new output prefix for another full compile. Inputs are bounded regular files opened with `O_NOFOLLOW` when available.

`example.json` is synthetic and demonstrates merged, superseded, active, recovery-eligible, and incomplete-evidence items.
