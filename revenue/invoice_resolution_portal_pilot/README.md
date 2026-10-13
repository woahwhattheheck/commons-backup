# Invoice Resolution Portal Pilot

A deterministic, read-only fulfillment core for the **$2,500 fixed pilot**: one invoice, one resolution workflow, and one buyer-facing intake surface. Commercial state is always `PROPOSED_NOT_ACCEPTED`; the separate **$5,000 integration** is represented only as an optional follow-on price, never as accepted work.

This package is generic and synthetic. It contains no buyer ticket, contact, payment-link, customer, or private invoice data.

## Product contract

The compiler binds every request and evidence item to one exact invoice generation: invoice ID, revision, snapshot SHA-256, observed timestamp, currency, integer minor-unit amounts, and an opaque non-contact `customer_ref`.

The intake surface supports exactly three request actions:

1. `ACKNOWLEDGE_BALANCE`
2. `OPEN_DISPUTE`
3. `REQUEST_PAYMENT_PLAN_DISCUSSION`

Those labels record what the customer asked for. They do **not** approve a plan, decide a dispute, change an invoice, or make an accounting/legal conclusion.

Every retained event is content-hashed into an ordered chain. A prior packet can supply its `next_checkpoint`; changing any event in that retained prefix produces `HOLD_PRIOR_CHAIN_MISMATCH`. Replaying the same request ID with identical semantics is idempotent. Reusing the same request ID or evidence ID with different semantics produces a HOLD rather than a second workflow.

## Data boundary

The schema intentionally has no raw free-text statement, email, phone, postal address, payment credential, bank/card field, or source-document body. Customer statements and attachments enter only as SHA-256 digests; the integration layer is responsible for retaining source bytes under the customer's own policy.

`customer_ref` must be an opaque system identifier, not a name, email, phone number, postal address, account number, payment credential, password, API key, session token, SSN, or tax identifier.

Generation isolation is explicit: every event repeats the invoice ID, revision, and snapshot SHA-256. A mismatch is a HOLD. A retained checkpoint proves that the new packet extends the same event prefix; it detects history mutation but does not make untrusted storage immutable by itself. Store delivered checkpoints in an independently controlled audit/delivery location when append-only continuity is contractual.

## Deterministic states and failure semantics

A clean one-request case emits `OWNER_REVIEW_READY`. Semantic uncertainty emits `HOLD` plus exact reasons:

- `HOLD_PRIOR_CHECKPOINT_OUT_OF_RANGE`
- `HOLD_PRIOR_CHAIN_MISMATCH`
- `HOLD_EVENT_CHRONOLOGY`
- `HOLD_FUTURE_EVENT`
- `HOLD_INVOICE_GENERATION_MISMATCH`
- `HOLD_REQUEST_REPLAY_MISMATCH`
- `HOLD_MULTIPLE_REQUESTS_OUT_OF_SCOPE`
- `HOLD_EVIDENCE_WITHOUT_REQUEST`
- `HOLD_EVIDENCE_REPLAY_MISMATCH`
- `HOLD_NO_REQUEST`

Malformed/ambiguous JSON, unknown fields, duplicate JSON keys/event IDs, non-finite numbers, raw free-text fields, invalid hashes/timestamps, and money encoded as booleans/floats are rejected before packet construction.

## Authority ceiling

Every packet hard-codes these capabilities to `false`: buyer send, taking payment, payment-plan approval, dispute adjudication, invoice mutation, accounting/legal conclusions, customer-acceptance claim, payment claim, and revenue claim.

`OWNER_REVIEW_READY` therefore means only that the evidence package is coherent enough for a human owner to review.

## Acceptance criteria

A pilot generation is source-ready when all of the following hold:

- one exact invoice generation is bound across every event;
- at most one canonical request is active for the fixed pilot scope;
- identical request replay does not duplicate work;
- conflicting request/evidence replay fails closed to HOLD;
- evidence cannot precede or silently transplant across request/invoice identity;
- a prior event-chain checkpoint must still match before extension;
- future/out-of-order evidence is held;
- source JSON is strict and synthetic fixtures contain no private material;
- packet receipt and semantic verifier both reject tampering;
- owner-review Markdown preserves the authority ceiling;
- the same focused suite passes in normal and optimized (`python -O`) execution.

## One-page implementation plan

1. **Generation adapter** — map one customer invoice export into the strict invoice-generation object while retaining source bytes outside this package.
2. **Intake surface** — expose only the three bounded actions and digest any raw statement before it crosses the compiler boundary.
3. **Evidence log** — append request/evidence events with exact invoice binding; persist the previous packet checkpoint and require the next generation to extend it.
4. **Owner review** — compile JSON packet + Markdown owner-review export; HOLD on generation drift, replay conflict, chronology/future evidence, or out-of-scope multiple requests.
5. **Delivery proof** — run compile -> verify on the customer's synthetic/minimized acceptance fixture, retain packet receipt + chain root, and complete the delivery receipt below.

Acceptance demo: clean synthetic case -> `OWNER_REVIEW_READY`; wrong invoice generation -> HOLD; mutated checkpoint prefix -> HOLD; request/evidence ID semantic reuse -> HOLD; evidence before request -> HOLD; future/out-of-order event -> HOLD; second request -> HOLD; packet tamper -> verify false; raw/private-field attempt -> structural rejection.

The optional integration is a separate commercial scope. It may add read-only source adapters and controlled publication around this compiler, but it must not turn the pilot into a payment processor, dispute adjudicator, invoice editor, plan-approval engine, or accounting/legal decision system.

## Customer input checklist

Before a paid pilot starts, confirm the customer can provide a **synthetic or safely minimized** fixture with:

- [ ] one invoice ID and revision;
- [ ] SHA-256 of the exact invoice snapshot;
- [ ] ISO currency, invoice amount and balance in integer minor units;
- [ ] source-observed UTC timestamp;
- [ ] opaque non-contact customer reference;
- [ ] one allowed request action;
- [ ] SHA-256 of the customer statement;
- [ ] optional evidence IDs/classes + SHA-256 digests;
- [ ] prior event-chain checkpoint if this extends an earlier delivered packet.

Do not send this compiler raw card/bank information, credentials, passwords, API tokens, customer contact data, unrestricted statement narrative, or source invoice documents.

## Delivery receipt template

**Pilot:** Invoice Resolution Portal — one invoice / one workflow / one intake surface  
**Commercial state:** `PROPOSED_NOT_ACCEPTED` until separately accepted by the customer  
**Pilot price:** $2,500 fixed  
**Optional integration:** $5,000 separate scope, only if useful

- Source generation / commit: `<sha>`
- Input fixture SHA-256: `<sha256>`
- Packet receipt SHA-256: `<receipt_sha256>`
- Event-chain root SHA-256: `<event_chain_root_sha256>`
- Event count: `<count>`
- Compile command/result: `<receipt>`
- Verify command/result: `<receipt>`
- Normal test result: `<count>/<count>`
- `python -O` test result: `<count>/<count>`

Acceptance evidence checklist: exact invoice generation demonstrated; three bounded actions demonstrated; identical replay idempotent; conflicting replay HOLDs; retained checkpoint mutation HOLDs; future/out-of-order evidence HOLDs; raw private fields rejected; packet tampering fails; owner-review export states authority ceiling.

This receipt proves only delivery/integrity of the named software generation and acceptance fixture. It does not prove customer acceptance, payment, revenue, plan approval, dispute adjudication, invoice modification, or accounting/legal conclusions.

## Usage

```bash
python -m revenue.invoice_resolution_portal_pilot compile \
  --input revenue/invoice_resolution_portal_pilot/sample_input.json \
  --packet-out /tmp/pilot-packet.json \
  --report-out /tmp/pilot-report.md

python -m revenue.invoice_resolution_portal_pilot verify \
  --input revenue/invoice_resolution_portal_pilot/sample_input.json \
  --packet /tmp/pilot-packet.json
```

Output paths are create-exclusive: an existing packet/report is never silently overwritten.

## Test topology

`revenue/invoice_resolution_portal_pilot/test_core.py` is the focused suite. The repository-root `test_invoice_resolution_portal_pilot.py` bridge enrolls that suite in Commons' retained root battery, so the product does not depend on a new dedicated workflow.

Reference generation: 22 focused tests pass normally and under `python -O`; sample packet receipt is `28a3fdf7f3e4f1494dd5ecdc4bb7d782c86a19c6ff1d90e1f30fa71ae6c4e31b`.
