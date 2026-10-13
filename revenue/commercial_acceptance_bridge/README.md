# Commercial Acceptance Bridge

This package turns a **human-reviewed, normalized buyer response** into a deterministic closing handoff state that can sit between inbound-reply custody and paid-fulfillment/payment gates.

It deliberately does **not** parse raw email or infer intent from prose. A caller must supply the reviewed response class and SHA-256 reviewer attestation. It also does not determine signer/legal authority, create or execute contracts, create invoices/checkouts, charge money, start fulfillment, or recognize revenue.

## Evidence contract

An offer version is bound to exact offer series/version lineage, counterparty + provider thread, SHA-256 scope/acceptance/commercial-term snapshots, exact currency + minor-unit price, and canonical UTC issue/expiry times. A reviewed response is bound to the same offer version, counterparty/thread, received time, provider message ID, content snapshots, price/currency, review class, and reviewer-attestation digest.

`EXACT_ACCEPT` becomes `HUMAN_CLOSING_READY` only when all bound commercial fields equal the current non-superseded offer version, the response falls inside the issue/expiry/snapshot window, and the evidence snapshot is still fresh at a **trusted evaluation time**. Even then all contract, signer, payment, fulfillment and revenue authority flags remain `false`; the next action is human closing review.

Other response classes route conservatively: `COUNTEROFFER` → `COUNTEROFFER_REVIEW`, `PARTIAL_ACCEPT` → `CLARIFICATION_REQUIRED`, `QUESTION` → `OWNER_REPLY_REQUIRED`, `DECLINE` → `DECLINED`, and `AMBIGUOUS` → `HUMAN_REVIEW_REQUIRED`.

Changed payload under one event ID fails idempotency. Same provider message mapped to different normalized responses fails closed. Superseded-version replies are quarantined; current-scope temporal/thread/counterparty/exact-match inconsistencies block closing rather than falling back to an earlier reply.

## Receipt trust + time boundary

`receipt_self_digest_matches()` answers only whether the receipt's embedded checksum matches its current bytes. That is an integrity check, **not** proof that the receipt came from this bridge or that its semantics are trusted; anyone who can author arbitrary JSON can also calculate its checksum.

`verify_receipt()` therefore requires all three independent authorities before returning true:

1. an out-of-band expected receipt SHA-256;
2. the normalized source batch from a trusted source channel, which is fully replayed and must reproduce the receipt exactly;
3. trusted evaluation time. Production callers omit the test-only `evaluated_at` override so current UTC is used.

The source snapshot may not be in the future and may be at most **300 seconds** old. During fresh replay, an `EXACT_ACCEPT` whose current offer has since expired is downgraded to `HUMAN_REVIEW_REQUIRED` with `OFFER_EXPIRED_AT_EVALUATION`. Consequently a historically valid closing-ready receipt cannot remain closing-authorizing indefinitely: after snapshot staleness or offer expiry, current verification fails closed.

The expected digest, source batch and trusted time must not be copied from attacker-controlled fields in the receipt under inspection. A self-authored checksum is not a trust root.

## Acceptance fixture

`acceptance.py` produces 60 synthetic offer series / 65 versions and a 125-record input batch with 120 unique events + five exact retries. Expected states are 15 `HUMAN_CLOSING_READY`, 10 `COUNTEROFFER_REVIEW`, 5 `CLARIFICATION_REQUIRED`, 5 `OWNER_REPLY_REQUIRED`, 5 `DECLINED`, 10 `HUMAN_REVIEW_REQUIRED`, 5 `AWAITING_RESPONSE`, and 5 `EXPIRED_NO_ACCEPTANCE`. It also forces five superseded-version acceptance attempts and five exact-accept content mismatches into quarantine. The deterministic fixture evaluates exactly at its frozen snapshot and retains receipt commitment:

`dede4ae4fb681198b46e5d4433f182f05afe4583539d2f62487672bda27767fb`

That frozen fixture receipt is regression evidence, **not** a permanently current closing authorization. Production verification always uses current UTC.

## Run

From the Commons repository root:

```bash
python -m unittest revenue.commercial_acceptance_bridge.test_gate -v
python -O -m unittest revenue.commercial_acceptance_bridge.test_gate -v
python -m revenue.commercial_acceptance_bridge.acceptance \
  --write-receipt /tmp/commercial-acceptance-receipt.json \
  --write-source-batch /tmp/commercial-acceptance-source.json
```

Trusted verification of a *current* receipt requires its independent commitment and trusted source batch:

```bash
python -m revenue.commercial_acceptance_bridge.acceptance \
  --verify-receipt /path/to/current-receipt.json \
  --source-batch /path/to/trusted-source-batch.json \
  --expected-receipt-sha256 <out-of-band-sha256>
```

The frozen fixture above will intentionally stop passing current-time verification once it is stale; deterministic fixture checks inject the frozen snapshot only inside tests. No production validation depends on Python `assert`, so optimized mode preserves the same fail-closed checks.
