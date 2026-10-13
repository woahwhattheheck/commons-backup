# Swarm claim publication fence

This is a narrow retained-evidence compiler for a fleet failure that ordinary exact search cannot safely answer: **did my work-custody TAKE actually become visible in full channel chronology, and does search-index divergence make proceeding unsafe?**

It complements, rather than replaces, the swarm terminality registry and Muse/OneWriter. Terminality answers whether retained work looks terminal/active/recoverable. Muse coordinates human-facing sends. This product binds an exact `work_key × role × scope_digest_sha256` to one candidate Slack message and compares a retained full-channel history window with the exact-search result set.

## Fail-closed states

- `HOLD_NO_HISTORY_CENSUS` — the retained channel window is not asserted complete.
- `HOLD_CANDIDATE_NOT_VISIBLE` — the candidate TAKE is not present as the exact history row.
- `HOLD_EARLIER_CLAIM` — an earlier materially-same TAKE is visible; yield to it.
- `HOLD_SCOPE_DIGEST_CONFLICT` — full-channel history contains a second TAKE for the same work key and role but a *different* scope digest; coordinate ownership before any writer proceeds. This flags possible overlap, not proof that the scopes are identical.
- `HOLD_INDEX_DIVERGENCE` — full history has materially-same messages missing from exact search.
- `HOLD_HISTORY_MISMATCH` — exact search contains a materially-same message absent from the supplied full history window.
- `CANDIDATE_VISIBLE_EARLIEST` — candidate is visible and earliest and history/search sets converge.

Search-zero **never** establishes absence. A candidate is not publication-confirmed until its exact message is retained in the full-channel window. Later duplicate claims do not displace the earlier candidate.

The exact search is permitted to return only the requested digest. The **complete retained history** additionally checks all claims with the same `work_key × role`, irrespective of scope digest, and reports `scope_digest_conflict_count` plus `scope_digest_conflict_message_ts`. A conflicting digest holds even when the candidate is the earliest exact-digest TAKE; materially disjoint scopes require explicit ownership reconciliation or distinct work keys. Earlier exact claims and history/search integrity holds keep their existing precedence. No claim is granted by this report.

## Authority ceiling

The input packet is retained evidence supplied to this offline tool. The tool does not independently authenticate Slack or the completeness assertion, does not mint a lease, and does not mutate GitHub, Slack, Muse, providers, payments, or accounting. Even `CANDIDATE_VISIBLE_EARLIEST` means only: *this packet is internally consistent and supports proceeding to a separate fresh live mutation fence after provider recensus.*

## Strictness

The parser rejects duplicate JSON keys, unknown fields, non-finite numbers, bool-as-int, malformed Slack timestamps/channel/principal IDs, malformed digests, future/stale observations, inverted/out-of-window history, duplicate/transplanted provider message identities, and non-exact search matches. Output verification semantically recompiles the snapshot and byte-compares canonical JSON, Markdown, and receipt; rehashing a modified report is insufficient.

Input files are bounded UTF-8 regular files opened with `O_NOFOLLOW` when available. Compile outputs are create-exclusive mode `0600`; an existing output fails rather than overwriting evidence.

## CLI

```bash
python -m tools.swarm_claim_publication_fence.cli compile snapshot.json out/fence
python -m tools.swarm_claim_publication_fence.cli verify \
  snapshot.json out/fence.report.json out/fence.report.md out/fence.receipt.json
```

`example.json` demonstrates a publication-confirmed candidate followed by a later duplicate claim.
