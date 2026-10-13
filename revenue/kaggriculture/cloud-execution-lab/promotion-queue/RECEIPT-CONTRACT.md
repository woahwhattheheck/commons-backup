# Promotion receipt contract — `titan-promotion-queue-receipt/v1`

A receipt is a single JSON document sealing one promotion attempt. Field
order is irrelevant: the integrity digest is computed over the canonical
encoding (`sort_keys=True`, `separators=(",",":")`, `ensure_ascii=True`,
`allow_nan=False`).

## Top-level fields

| field | meaning |
| --- | --- |
| `schema_version` | `1` |
| `receipt_type` | `titan-promotion-queue-receipt/v1` |
| `receipt_id` | `r-<submission-id>-a<attempt>` |
| `submission_id` | queue submission id (equals the pin id) |
| `attempt` | 1-based attempt number for this submission |
| `created_at` | UTC ISO-8601 sealing time |
| `policy_version` | promotion policy version, e.g. `promotion-policy/v1` |
| `verdict` | `PROMOTE` or `REJECT` |
| `queue_pin` | pin id, input digest, and per-input `{sha256, bytes}` |
| `predecessors` | per slot: name, artifact/games/contract/evidence SHA-256, panel id |
| `comparisons` | per slot: strategy, verdict, gate exit code, report SHA-256, grid, failed checks, aggregate deltas, input hashes, duration |
| `timings` | started/finished timestamps, total and per-slot milliseconds |
| `integrity` | see below |
| `extra` | strategy used and the SHA-256 of the gate scripts invoked |

## Integrity

```json
"integrity": {
  "algorithm": "sha256-canonical-json-v1",
  "digest": "<sha256 of the canonical receipt with integrity.digest removed>",
  "prev_receipt_digest": "<digest of the previous attempt's receipt, or null>"
}
```

Verification recomputes the digest from the presented bytes: any edit to
inputs, results, policy version, timings, or metadata invalidates it.
`promote.py receipt <id> --verify` performs this check. Repeated attempts
(reruns) link via `prev_receipt_digest`, forming a per-submission hash
chain — history cannot be rewritten without breaking the chain.

## Optional key signature

With `promote.py run --signing-key <keyfile>` (or `ReceiptStore.build(...,
signing_key=...)`), the queue additionally seals each receipt with an
HMAC-SHA256 signature:

```json
"integrity": {
  "algorithm": "hmac-sha256-v1",
  "digest": "<sha256 of the canonical receipt with integrity.digest and integrity.signature removed>",
  "signature": "<hmac-sha256 over the canonical receipt with integrity.signature removed>",
  "prev_receipt_digest": "<digest of the previous attempt's receipt, or null>"
}
```

The signature covers the sealed digest, so a gate consuming the receipt can
verify both integrity (digest) and attribution (signature) with
`ReceiptStore.verify(receipt, signing_key=key)`. Keys are raw bytes read
from a file the operator supplies; keys never appear in receipts, logs, or
queue state. `promote.py receipt <id> --verify --signing-key <keyfile>`
verifies both. Without `--signing-key` the receipt stays tamper-evident
only, exactly as before.

## What the receipt does NOT claim

* Without `--signing-key`, it does not sign with a private key (tamper-evident, not key-signed).
* `PROMOTE` means only "the pinned candidate satisfied the pinned policy
  against the pinned predecessor panels under the pinned gate scripts" —
  the same bounded meaning the gate's own verdict carries. It is not a
  Kaggle submission, leaderboard claim, or release authorization.
