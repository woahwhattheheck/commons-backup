# Accounts Receivable Leakage Desk

A dependency-free, offline reconciliation product for one **sanitized** accounts-receivable export generation. It turns invoice, payment, credit, and dispute evidence into a deterministic owner-review packet without sending a reminder, guessing where money belongs, or claiming a legal debt.

## Fixed commercial shape

Reference offer: **$2,500 fixed diagnostic** for one sanitized USD export generation of up to **5,000 invoices**. The deliverables are canonical JSON, a buyer-readable Markdown review queue, a detailed integrity-conflict queue, unapplied-payment evidence, and an exact SHA-256 receipt. Integration, writeback, collections, ERP access, payment-provider access, and custom adapters are explicitly outside the diagnostic and should be separately scoped only after a paid diagnostic.

The checked-in price is a commercial reference, not evidence that a buyer accepted or paid anything.

## Input contract

`example.json` shows the closed schema. IDs must be opaque safe identifiers—not names, emails, addresses, message bodies, or credentials. Every invoice/event carries a row-level evidence SHA-256. The packet uses one explicit `analysis_date`; that date is an analytical horizon, not a claim of current/live provider truth.

Version 1 is mechanically limited to **USD integer minor units**. This is deliberate: the Markdown renderer uses a two-decimal USD exponent and must not silently misstate JPY or three-decimal currencies. A later multi-currency version must carry an independently validated exponent rather than infer one from a three-letter code.

`bool`, floats, duplicate JSON keys, non-finite values, unknown keys, unsafe identifiers, duplicate stable IDs, and evidence-digest replay fail closed.

Payments may intentionally have `invoice_id: null`. Such money is emitted as **unapplied payment evidence** and is never guessed onto an invoice. Payments, credits, and disputes that bind the wrong account/currency/invoice, postdate the analysis horizon, or predate the referenced invoice's issue date become explicit integrity conflicts and are excluded from that invoice's ordinary arithmetic/state. An event on the invoice issue date is admissible because the invoice source supplies day—not sub-day—precision.

An invoice whose `issue_date` is later than `analysis_date` is `CONFLICT`. Its face value remains visible as conflicted evidence, but it contributes zero to billed, applied, outstanding, disputed, or recovery-candidate economics for that analytical horizon.

## States

- `PAID` — evidence in this packet reduces the invoice balance to zero.
- `OPEN` — non-overdue balance with no applied payment/credit.
- `PARTIAL` — non-overdue balance after applied payment/credit.
- `OVERDUE` — balance beyond due date + explicit grace policy.
- `PARTIAL_OVERDUE` — overdue balance with some applied payment/credit.
- `DISPUTED_HOLD` — at least one exact dispute case is currently open; balance remains visible but is excluded from the recovery-candidate total.
- `VOID` — void source invoice with no usable balance.
- `CONFLICT` — integrity evidence is contradictory, over-applied, cross-account, cross-currency, outside the analysis universe, pre-invoice, or otherwise unsafe to treat as a normal balance.

`recovery_candidate_minor` is a **diagnostic owner-review total** over non-disputed, non-conflicted overdue rows. It is not a legal receivable determination, collection authority, recognized revenue, or cash receipt.

The Markdown report lists every conflict code, source row kind, source row ID, and bound invoice ID so the buyer-facing artifact does not hide reconciliation work behind a count.

## Run

From repository root:

```bash
python -m revenue.accounts_receivable_leakage_desk.cli compile \
  --input revenue/accounts_receivable_leakage_desk/example.json \
  --report /tmp/ar-report.json \
  --markdown /tmp/ar-report.md

python -m revenue.accounts_receivable_leakage_desk.cli verify \
  --input revenue/accounts_receivable_leakage_desk/example.json \
  --report /tmp/ar-report.json
```

The CLI reads bounded regular files through one retained descriptor, rejects final-component symlinks where the platform exposes `O_NOFOLLOW`, and creates outputs exclusively without overwrite.

## Acceptance / truth boundary

A successful report proves only that the exact supplied sanitized evidence reconciles under this reducer. It does not authenticate an ERP or bank source, contact a customer, send or alter an invoice, perform collections, allocate unattributed funds, waive a dispute, mutate accounting/provider state, determine legal enforceability, recognize revenue, or prove cash collection. All external-action authority fields are hard false.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
