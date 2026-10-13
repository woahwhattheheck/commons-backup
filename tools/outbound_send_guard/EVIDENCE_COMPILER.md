# Outbound send evidence compiler

The send guard only makes a decision from evidence it is given. This companion compiler closes the layer immediately above that decision: it turns **complete recipient-scoped exports** from a mailbox reader and Slack receipt reader into the exact `outbound-send-evidence/v1` object accepted by `guard.py`, plus a content-addressed provenance receipt.

It is intentionally offline. It does not call Gmail, Slack, an ESP, a CRM, or a scheduler, and it never authorizes or performs a send.

## Source contracts

Both source exports are strict JSON and share the same `capture_id`, normalized recipient, and `as_of` boundary. Collectors can run at different wall-clock times (`collected_at`), but every included observation must be at or before the shared `as_of`.

A mailbox export uses `outbound-mailbox-export/v1` and must declare:

- `complete: true`;
- `next_page_token: null` (otherwise pagination is not complete);
- a stable `query_id` describing the bidirectional recipient query;
- rows whose `counterparty` is exactly the recipient scope;
- outbound rows only when the provider state is `sent`, inbound rows only when provider state is `received`.

A Slack export uses `outbound-slack-export/v1` and must declare:

- `complete: true`;
- `next_cursor: null`;
- a stable `query_id`;
- `lead`, `sent`, or `hard_dnr` events for exactly the recipient scope.

If a Slack `sent` event names a `provider_message_id`, the complete mailbox export must contain that exact provider id as outbound/SENT evidence. If both sides bind an `offer_id`, they must agree. This prevents a Slack receipt from claiming a provider send that the provider evidence cannot prove.

Exact duplicate source rows collapse. Reuse of the same message/event id with different facts is a hard compile failure.

## Outputs

The compiler publishes two files as one rollback-capable pair:

1. `outbound-send-evidence/v1` — directly consumable by `guard.py` with no extra fields;
2. `outbound-send-evidence-compile-receipt/v1` — SHA-256 of each raw source export, SHA-256 of canonical compiled evidence, normalized capture/query metadata, row counts, and exact-duplicate counts.

Every receipt sets `side_effects_authorized=false`.

## CLI

```bash
python -m tools.outbound_send_guard.evidence_compiler \
  --mailbox mailbox-export.json \
  --slack slack-export.json \
  --evidence-out evidence.json \
  --receipt-out evidence.receipt.json
```

Optional `--policy policy.json` accepts only the three policy integers already understood by the guard: `cross_offer_cooldown_days`, `max_evidence_age_seconds`, and `max_future_skew_seconds`.

Inputs and outputs must be path-distinct, including hardlink/symlink aliases. Both outputs are staged and fsynced before publication; if the second publication fails, pre-existing evidence and receipt files are restored.

## Regression gate

```bash
python -m py_compile \
  tools/outbound_send_guard/evidence_compiler.py \
  tools/outbound_send_guard/test_evidence_compiler.py
python -m unittest -v tools.outbound_send_guard.test_evidence_compiler
python -O -m unittest -v tools.outbound_send_guard.test_evidence_compiler
```

The suite includes the live visibility failure which motivated the send guard: provider-SENT mail with no Slack send receipt compiles intact and causes the downstream guard to refuse a duplicate exact-offer send.
