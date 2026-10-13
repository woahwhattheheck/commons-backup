# Explicit remittance review — AR Leakage Desk extension

This is an operational extension of the existing Accounts Receivable Leakage Desk,
not a second reconciliation product or a new price. It answers a specific intake
question: **do these explicit remittance allocations fit the supplied unapplied
receipt and invoice-remaining snapshots, and what remains unresolved?**

The existing `engine.py` owns invoice/payment/credit/dispute aging. This sidecar
never rewrites its packet, recomputes aging, or turns hypothetical allocations into
posted payment evidence. Use a separately prepared remaining-balance snapshot for
this review. No FIFO, amount-only matching, guessed invoice, fuzzy account match,
discount, write-off, FX conversion, reversal, credit transfer, or posting occurs.

## Commercial use

The canonical desk's existing **$2,500 fixed diagnostic reference** and maximum
5,000-invoice scope remain unchanged; this extension does not assert that its work
is included in an accepted contract. Confirm the actual diagnostic scope with the
buyer before delivery. No customer, accepted scope, invoice, payment, recovery,
savings, revenue or third-party integration is claimed by this source package.

A useful paid workflow for accounting/CAS teams, fractional controllers, and
internal AR teams is: agree the snapshot boundary; normalize sanitized exports;
review explicit remittance instructions; resolve the exception queue with the
customer's operator; rerun on a new snapshot; hand back the evidence and residuals.
That is a proposed commercialization path, not evidence of demand or a partnership.
Custom ERP adapters and production writeback remain separately scoped work.

## Inputs and limits

Python 3.10+ standard library on POSIX systems with descriptor-relative file
operations (locally verified on Linux / Python 3.13.5). Run from the repository
root. Inputs must be
sanitized, using opaque IDs rather than names, addresses, email, bank-account
numbers, payment credentials, or free-form remittance text. ID syntax alone is not
a PII detector: the operator must sanitize before the files enter the workflow.

One packet uses schema `ar-explicit-remittance/v1`, a `snapshot_id`, an explicit
`analysis_date` in YYYY-MM-DD format, `currency: "USD"`, and three arrays. The date
is a supplied analytical horizon, **not a current-process or live-bank assertion**.
Every row carries that same `snapshot_id`; mismatched CSV generations are rejected.
The row names below are the exact CSV headers, in any order, with no extra columns.

| File / array | Required columns |
| --- | --- |
| invoices | snapshot_id, invoice_id, account_id, currency, issue_date, remaining_minor, status, source_event_id |
| payments | snapshot_id, payment_id, account_id, currency, received_date, available_minor, source_event_id |
| allocations | snapshot_id, allocation_id, payment_id, invoice_id, amount_minor, remittance_ref |

`remaining_minor` is the owner-supplied invoice balance still available for this
proposal, not the original invoice face amount. `available_minor` is the receipt
amount not already allocated in the source system, not a new deposit to make.
Preparing those balances and excluding already-posted applications is an intake
responsibility; the program cannot authenticate or independently complete an ERP
or bank export. It retains the exact supplied numbers and makes this limitation
explicit in every review.

Invoice `status` is OPEN, DISPUTED, VOID or CONFLICT. The last three hold connected
allocations. Native `source_event_id` must be unique within each invoice/payment
source: changing a display ID cannot duplicate the same retained native event.
Two equal amounts with distinct native events are not silently collapsed. Changed
native IDs for the same real event cannot be detected without upstream evidence.
`remittance_ref` is an opaque reference to owner-held instructions, not a copied
message and not proof of customer authorization or source authenticity.

Limits: 5,000 invoices, 10,000 receipts, 20,000 allocation instructions, 8 MiB input
across the three CSV files or one JSON file, and 0 through 10^15 cents per balance.
Allocation amounts are strictly positive integers. All totals use exact Python
integer arithmetic. USD only: foreign currency is rejected, never mixed or
implicitly converted. Negative/reversal/credit balances require a separately
normalized source workflow rather than silent sign changes here.

CSV accepts UTF-8 (including a BOM), quoted fields and reordered headers. Money
columns contain integer cents, for example `12500`, never `$125.00`, `125.00`,
`+12500`, `1.25e4`, commas, or implicit rounding. Duplicate headers, blank/ragged
rows, unknown fields, oversized values, noncanonical dates, duplicate stable IDs,
and duplicate native events are rejected. JSON additionally rejects duplicate
keys, floats/nonfinite numbers, excessive depth and non-plain Python inputs.

## Review behavior

An allocation binds its exact payment and invoice. The program checks existence,
account identity, chronology, invoice status, duplicate payment/invoice pairs,
payment capacity and invoice capacity. Receipts earlier than the invoice are held
for human review; that does not declare a genuine customer deposit invalid.

Allocations form a bipartite payment/invoice graph. **Any finding holds the entire
connected component.** For example, when a receipt covers invoices A and B, and a
second receipt overfills B, neither receipt wins because its CSV line happened to
come first. The whole linked component proposes zero; independent components can
still produce consistent proposals. Duplicate pairs are held, not silently summed.
Consolidate genuinely separate instructions for the same pair upstream with
retained evidence, then create a new snapshot for review.

Unreferenced receipts and invoices remain visible. Unknown reference instructions
are retained in the allocation queue, including their IDs and requested amounts.
Every original balance remains unchanged. For each receipt:

    available_minor = proposed_minor + hypothetical_unapplied_minor

For each invoice:

    remaining_minor = proposed_minor + hypothetical_remaining_minor

`PROPOSED_ONLY` / `CONSISTENT_PROPOSAL_ONLY` means only that the supplied instructions
fit this supplied snapshot. Neither status is a posting instruction, approval,
proof of cash receipt, collectible debt, source completeness, or accounting result.

## JSON run

```sh
python -m revenue.accounts_receivable_leakage_desk.remittance_review compile \
  --input revenue/accounts_receivable_leakage_desk/remittance_example.json \
  --out /tmp/ar-remittance-demo

python -m revenue.accounts_receivable_leakage_desk.remittance_review verify-bundle \
  --directory /tmp/ar-remittance-demo
```

The synthetic example contains 18,000 cents of invoice remaining balances and
17,000 cents of available receipt balances. Explicit instructions propose 13,000
cents, leaving hypothetical invoice residuals of 5,000 cents and receipt residuals
of 4,000 cents. These are fixture amounts, not business results.

## CSV run

```sh
python -m revenue.accounts_receivable_leakage_desk.remittance_review compile-csv \
  --snapshot-id YOUR-SNAPSHOT --analysis-date 2026-09-17 \
  --invoices invoices.csv --payments payments.csv --allocations allocations.csv \
  --out /tmp/ar-remittance-review
```

Create a new output directory for each run. Compilation refuses existing output
paths; it does not overwrite earlier evidence. The bundle contains original raw
input bytes, normalized `source.json`, `review.json`, `allocations.csv`,
`payments.csv`, `invoices.csv`, `review.md`, and a final `manifest.json`. The
Markdown report includes every finding, not merely a count. Generated review
artifacts have no Commons/GitHub customer links and no external contact mechanism.

`verify-bundle` reparses the retained raw source, recompiles the semantic review,
regenerates each output, and compares every member and the manifest byte-for-byte.
It rejects altered CSV/Markdown, forged totals, changed snapshot IDs, missing/extra
members, and a self-hash recomputed over a falsified report. JSON and CSV with the
same logical rows produce the same semantic review; raw byte manifests correctly
remain distinct. Row reordering does not change the semantic receipt.

SHA-256 receipts prove reproducibility/integrity relative to the retained inputs;
they are **not signatures or independent provider evidence**. Replacing every
input and every artifact with a different internally consistent bundle creates a
different review, not a cryptographically authenticated source history.

Use a private directory without concurrent untrusted writers. Reads require
bounded ordinary files and reject final-component symlinks on platforms with
`O_NOFOLLOW`; writes use an exclusive directory and descriptor-relative,
create-exclusive members, with the manifest written last. This is not a complete
sandbox against hostile parent-directory replacement or arbitrary interpreter
modification. A failed write can leave an incomplete exclusive directory; preserve
it for inspection and rerun under a new name. No cleanup deletes unrelated paths.

## Acceptance and proof

```sh
python -m unittest -q test_ar_remittance_review
python -O -m unittest -q test_ar_remittance_review
python -m py_compile revenue/accounts_receivable_leakage_desk/remittance_review.py
```

The root suite is discoverable by the existing repository battery. Its normal
run also launches the entire focused suite in a real optimized interpreter; that
extra launcher test is not defined inside optimized runs, preventing recursion.
No additional workflow slot is added. Local proof is distinct from hosted check
status, and a queued/missing hosted run is not a pass.

Acceptance covers split/partial payments, shared-component holds, independent
components, duplicates/reminted native IDs, unknown references, disputed/void and
conflicted balances, currency, chronology, raw ingress, report/source tampering,
all bundle outputs, exclusive file publication, actual JSON/CSV CLI roundtrips,
randomized conservation/permutation cases, and full declared row capacity.

## Workflow reference

Microsoft's Business Central documentation describes partial application, one
receipt applied to multiple customer entries, and explicit amounts per entry:
https://learn.microsoft.com/en-us/dynamics365/business-central/receivables-how-apply-sales-transactions-manually

It also distinguishes unmatched payments and lump-sum payments:
https://learn.microsoft.com/en-us/dynamics365/business-central/receivables-how-reconcile-customer-payments-list-unpaid-sales-documents

These primary sources informed the workflow shape, not an integration or Microsoft
endorsement. This sidecar deliberately stops before the ledger-posting operations
in those documents. Sources consulted 2026-09-17.

Implementation: Z-Cairn-Astra-917E. Preserve the original AR Leakage Desk source,
product and correction attribution; this module is a separate snapshot-review seam.
