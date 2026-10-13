# Fieldwork queue cancellation companion

`queue_cancel.py` is an operator-only companion for the shipped Fieldwork design-subscription desk. It closes an obsolete request without manufacturing a design delivery or approval, preserves the reason in request history, and advances the one-active-request queue when necessary.

## Status boundary

Approval and cancellation are different business outcomes and now remain different storage outcomes:

- the shipped Fieldwork `approve` action is the only path that produces `status='complete'`;
- this companion produces the distinct workflow-terminal `status='cancelled'` plus a `cancelled` history event beginning with `Cancellation is terminal; no delivery acceptance is implied.`

The shipped browser renders the raw request status as its badge, so a cancelled request is visibly `cancelled` instead of being presented as `complete`. The legacy desk may still allow brief metadata edits on an unknown terminal status, but those edits do not reopen the request or enter production/review/revision/queued workflow states. Queue and delivery actions remain unavailable for `cancelled`.

## Safe use

Read the target request's current `id` and `version` from `GET /api/workspaces/<workspace-id>` or the local SQLite-backed operator view, then run:

```bash
python queue_cancel.py <request-id> \
  --db ./data/desk.sqlite3 \
  --expected-version <current-version> \
  --reason "Customer withdrew the request" \
  --confirm-request-id <request-id>
```

The repeated request id is intentional. It prevents a copied or mistyped target from being cancelled accidentally. A stale version fails without mutation.

## Queue behavior

- Cancelling `production`, `review`, or `revision` closes that request and promotes exactly one queued request using Fieldwork's existing ordering: lowest priority number, then creation time, then request id.
- Cancelling a `queued` request closes only that request and does not disturb the active request.
- `complete` and `cancelled` are both terminal for this companion; repeat cancellation refuses without another event.
- All work happens in one `BEGIN IMMEDIATE` transaction. Two operators racing on the same expected version cannot both cancel or advance the queue.
- The tool refuses a missing database instead of silently creating an empty SQLite file.

No email, payment, customer, provider, hosted identity, or external deployment action is performed.

## Focused acceptance

From this directory:

```bash
python -W error::ResourceWarning -m unittest -v test_queue_cancel.py
python -m py_compile queue_cancel.py test_queue_cancel.py
```

The focused suite covers active and queued cancellation, explicit `cancelled`/`complete` separation, stale and terminal refusal, concurrent operators, missing-database safety, and exact-id confirmation. The test schema matches the current Fieldwork tables and partial unique index for one active request per workspace.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
