# Outbound collision / replay guard

This package is a deterministic **coordination layer**, not a sender. It prevents two agents from independently treating the same counterparty × provider/thread × message purpose as send-ready.

## Contract

The guard consumes a canonical ledger plus one transition request and emits a canonical next ledger plus a receipt. The receipt binds the exact previous ledger SHA-256, request SHA-256, and next-ledger SHA-256. A durable adapter must commit the output only with a compare-and-swap precondition that the durable current ledger still equals `before_ledger_sha256`. Two agents that compile from the same base therefore produce competing outputs with the same precondition; only one may be committed.

The exact states are `CLAIMED`, `YIELD_EXISTING`, `WAIT_MUSE`, `READY_SINGLE_WRITER`, `SENT_TERMINAL`, `RELEASED_UNSENT`, and `HOLD_AMBIGUOUS_COUNTERPARTY`.

`READY_SINGLE_WRITER` means only that the supplied retained Muse selection matches the exact fingerprint, holder, session, generation, body digest and validity window. The package **does not contact Muse, authenticate Slack, send anything, or mint outbound authority**. Actual senders must still perform their live provider/action checks.

## Safety invariants

- Canonical intent fingerprint binds counterparty + provider + thread scope + message purpose; body SHA is separately generation-bound.
- A related route collision on another reply/new-thread scope fails closed.
- Ambiguous counterparty identity never acquires a lease.
- Changed body invalidates prior Muse evidence; once a send attempt exists, changed-body retry is blocked.
- A send attempt immediately removes send-ready state until its provider result is reconciled.
- `UNKNOWN`/lost provider result blocks release and retry so a provider-accepted message cannot be duplicated by uncertainty.
- `ACCEPTED` provider result is terminal and cannot be reopened.
- Expired claimant recovery advances generation and invalidates Muse evidence; unresolved provider attempts remain a hard no-send condition.
- Every receipt keeps all send/provider/payment/revenue authority flags false.
- Strict JSON rejects duplicate keys, floats, NaN/Infinity, unknown keys, noncanonical ledger/request bytes, symlink/nonregular CLI inputs, and output overwrite.

## CLI

```bash
python -m revenue.outbound_collision_replay_guard.engine transition ledger.json request.json \
  --ledger-out next-ledger.json --receipt transition-receipt.json
python -m revenue.outbound_collision_replay_guard.engine verify \
  ledger.json request.json next-ledger.json transition-receipt.json
```

The two output paths must share a directory. Publication is create-exclusive and rolls back its own first output if the second output cannot be created.

## Operator sequence for a real outbound

1. Canonicalize the counterparty, route/thread, purpose, and body digest. If identity/thread scope is ambiguous, stop.
2. Compile `CLAIM` and CAS-commit the returned ledger against the receipt's exact `before_ledger_sha256`.
3. Ask Muse for the **exact** org/route/purpose sender election outside this package. Retain the real receipt/source identity.
4. Compile `APPLY_MUSE`; only exact fresh selection reaches `READY_SINGLE_WRITER`.
5. The send-capable adapter independently verifies the live route and executes at most one attempt. Immediately compile `RECORD_SEND_ATTEMPT` before any retry logic.
6. Reconcile the provider result. `ACCEPTED` becomes `SENT_TERMINAL`. `UNKNOWN` stays blocked. `REJECTED` must be released, reclaimed at a new generation, and then receive fresh Muse evidence before another attempt.
7. Release only when there is no unresolved attempt.

Run the synthetic lifecycle with:

```bash
python -m revenue.outbound_collision_replay_guard.demo.demo
```

Expected states: `CLAIMED`, `READY_SINGLE_WRITER`, `CLAIMED`, `SENT_TERMINAL`.
