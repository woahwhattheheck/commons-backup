# Field Service Quote-to-Job Workspace

A local-first customer and operator workspace for small home-service and trade contractors. It carries a qualified job through **quote → customer approval → resource scheduling → change orders → completed approved scope → invoice draft** without pretending that a local workflow sent a message, collected payment, posted accounting entries, or recognized revenue.

This is a customer workflow product, not a proof/evidence SKU. It is designed to sit after lead intake/qualification and before whatever accounting/payment system a contractor already uses.

## Suggested launch offer

A reasonable first-customer shape is **$1,500 setup + $199/month per small operation**, adjusted after direct customer discovery. That is an internal offer hypothesis, not a signed customer contract or recognized revenue.

## What is included

- exact-cent quote line items; floats and bool-as-int money are rejected;
- immutable quote content fingerprint exposed to the customer and required at approval;
- opaque customer capability token stored only as SHA-256 at rest;
- quote approve/decline with request-key replay protection;
- exactly one job per approved quote;
- resource scheduling using half-open UTC intervals, with serialized overlap prevention;
- customer-visible change-order line items and immutable change fingerprint;
- change orders affect scope/value only after customer approval;
- completion tracking for every approved base/change scope item;
- job completion blocked by pending change decisions or incomplete approved scope;
- deterministic invoice **draft** derived only from approved, completed scope;
- deterministic content-addressed job export and invoice draft;
- restart-safe SQLite state and mutation receipts;
- loopback-only browser customer portal with no-store/CSP/frame/origin/host guardrails;
- standard-library-only CLI, portal, demo, and tests.

## Quick demo

```bash
cd revenue/hive/field-service-workspace
python -m py_compile workspace.py portal.py demo.py test_workspace.py test_portal.py
python -m unittest -v test_workspace.py test_portal.py
python -O -m unittest -v test_workspace.py test_portal.py

rm -f /tmp/field-service-demo.db*
python demo.py --db /tmp/field-service-demo.db
```

The deterministic demo creates a synthetic two-line USD quote, obtains a customer-bound approval of the exact quote digest, schedules a crew, obtains approval for a $50.00 change, completes all three approved scope items, completes the job, and emits an invoice draft. Running the same demo a second time against the same database replays the same request receipts rather than duplicating state.

## Customer portal

Start the browser surface only on loopback:

```bash
python portal.py --db /tmp/field-service.db --host 127.0.0.1 --port 8086
```

Open `http://127.0.0.1:8086/`. The customer enters the opaque quote reference and a separately delivered capability token. The portal shows the exact line items, total, and content fingerprint before approval. Pending change orders likewise show exact line items and a change fingerprint before the customer can decide.

The demo package intentionally does **not** choose a token-delivery channel. A production deployment must use the operator's authorized customer identity/delivery system and should terminate TLS before exposing any capability remotely. This checked-in portal refuses non-loopback binds.

Generate real capability values outside this repository with a cryptographic secret generator, for example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Do not put real customer tokens in source control, command history, support tickets, or shared logs.

## Operator flow

`workspace.py` exposes the same operations as a CLI. `create-quote` and `propose-change` consume JSON files so line-item structure is not lossy.

Example quote input:

```json
{
  "quote_id": "quote-2026-001",
  "currency": "USD",
  "customer_token": "use-a-real-generated-secret-of-at-least-32-bytes",
  "items": [
    {"item_id": "labor", "description": "Repair labor", "quantity": 2, "unit_cents": 12500},
    {"item_id": "part", "description": "Replacement component", "quantity": 1, "unit_cents": 8750}
  ],
  "created_at": "2026-09-13T14:00:00Z",
  "request_key": "create-quote-2026-001"
}
```

Then:

```bash
python workspace.py --db /tmp/field-service.db create-quote --input quote.json
python workspace.py --db /tmp/field-service.db publish-quote quote-2026-001 2026-09-13T14:01:00Z publish-quote-2026-001
python workspace.py --db /tmp/field-service.db summary
```

After the customer approves in the portal, the operator can schedule the deterministic `job-*` reference, propose changes, complete scope items, complete the job, and emit `invoice-draft` / `export-job` JSON.

All mutation commands carry a `request_key`. Reusing the same key with the exact same operation/content returns the original result. Reusing it with changed content fails closed.

## Commercial truth boundaries

The product distinguishes workflow facts from external authority:

- `APPROVED` means the supplied customer capability approved the exact locally displayed content fingerprint; it does not prove legal identity beyond the token-delivery system the operator chose.
- `JOB_COMPLETED` means every locally approved scope item was marked complete and no customer change decision remained pending; it is not a warranty, inspection, or regulatory certification.
- `invoice-draft` is a deterministic draft/export. It is **not sent**, **not posted to accounting**, **not a payment request**, **not payment/settlement evidence**, and **not recognized revenue**.
- no email/SMS, calendar provider, payment processor, accounting system, CRM, or customer contact is invoked by this package;
- no live tax calculation, licensing determination, consumer-credit decision, collections action, or legal-contract interpretation is performed.

## Concurrency and replay rules

SQLite mutations use `BEGIN IMMEDIATE`, so two workers racing to schedule overlapping intervals for the same resource serialize: one schedule commits and the other sees the conflict. Customer/operator mutation receipts are written in the same transaction as the business state, avoiding a committed effect without its request-key receipt.

Customer decisions bind both the capability digest and the exact quote/change digest. A stale browser form cannot silently approve changed content. The database stores only the capability digest; tests also assert the synthetic raw token bytes are absent from the SQLite file.

## Verification

Focused acceptance covers:

- exact-cent and scalar traps;
- wrong/cross-quote capabilities with no existence oracle;
- raw-token-at-rest absence;
- canonical UTC enforcement;
- exact replay and changed-payload conflicts;
- exactly-one-job approval semantics;
- decline terminality;
- quote/change fingerprint mismatch rejection;
- line-item visibility before change approval;
- half-open scheduling and concurrent overlap races;
- schedule mutation conflicts;
- pending/declined/approved change behavior;
- scope-before-schedule rejection;
- pending-change/incomplete-scope completion blocks;
- invoice basis and all non-authority flags;
- restart durability;
- deterministic/tamper-detecting export digests;
- loopback bind, Host/Origin, CSP/no-store, no GET token acceptance, and HTML escaping.

Run both normal and optimized Python. No correctness condition depends on `assert`.
