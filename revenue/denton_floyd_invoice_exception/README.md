# Denton Floyd Invoice Exception Control

A deterministic, read-only evidence product for reconciling invoice, purchase-order, and vendor exports into a review queue without creating accounting or payment authority.

## What it does

The compiler ingests one JSON packet containing source-bound vendor, PO, and invoice snapshots. It validates exact JSON/runtime types, canonical timestamps and dates, exact-two-decimal money strings, known currency, unique identifiers, evidence freshness, and SHA-256-shaped source bindings. It then classifies each invoice as `READY` or `HOLD` and emits:

- `result.json` — canonical decision + manifest receipt;
- `decisions.csv` — review-friendly flat projection;
- `receipt.md` — human-readable summary;
- a manifest binding the exact packet and exact decisions by SHA-256.

The original acceptance fixture remains explicit: **12 invoices → exactly 7 READY / 5 HOLD**. The five seeded defects are missing PO, inactive vendor, amount over PO total, invoice predating PO, and due date preceding invoice date.

## Authority ceiling

This product is intentionally incapable of approving invoices, changing vendors, posting to a ledger, or releasing money. `READY` means only that the supplied evidence passed this bounded reconciliation policy. Humans and source systems retain all accounting, authorization, posting, and payment decisions.

## Run

```bash
cd revenue/denton_floyd_invoice_exception
python3 -m unittest -v test_engine.py
python3 engine.py compile fixture.json \
  --as-of 2026-09-13T10:45:00Z \
  --out-dir /tmp/denton-floyd-receipt
python3 engine.py verify fixture.json \
  /tmp/denton-floyd-receipt/result.json \
  --as-of 2026-09-13T10:45:00Z
```

## Fail-closed boundaries

Packets are rejected before classification for malformed or duplicate-key JSON, unknown fields, duplicate primary IDs, noncanonical instants, stale/future captures, unsupported currencies, malformed source digests, non-string money, negative money, or money not expressed with exactly two decimal places. Business exceptions such as missing PO/vendor, inactive vendor, PO mismatch, amount over PO, and date-order errors become deterministic `HOLD` reasons rather than silent coercions.

Semantic duplicate invoices are also held even when invoice IDs differ if vendor + source reference + amount + invoice date repeat. This makes replay and duplicate-export behavior visible without creating side effects.

### Cumulative PO utilization

After all row-level checks, the compiler totals exact-`Decimal` amounts for invoices that would otherwise be `READY`, grouped by referenced PO. If that candidate exposure exceeds the PO total, **every otherwise-ready invoice on that PO becomes `HOLD` with `PO_CUMULATIVE_AMOUNT_EXCEEDED`**. Exact equality remains allowed.

Rows already held for duplicate evidence, missing/mismatched/inactive vendor or PO evidence, PO status, an individual amount over the PO, or date defects do not consume candidate-ready utilization: the control is already refusing to treat those rows as authorized spend. This also prevents replayed duplicate evidence from inflating cumulative utilization while keeping every duplicate row visible in the HOLD queue.

Cumulative decision semantics are independent of invoice array order. The packet digest still binds the exact source array order, so reordering source evidence can change `packet_sha256` without changing the sorted decision set or `decisions_sha256`.

## Determinism and verification

Objects are hashed as canonical UTF-8 JSON (sorted keys, compact separators, finite JSON values only). `verify` recompiles from the original packet and `--as-of`, byte-compares the canonical result, then recomputes the manifest digest. A changed state, reason, count, source binding, or manifest field fails verification.

## Demo / buyer handoff

The module is suitable for a synthetic demonstration using exported data only. A buyer-specific pilot should replace the fixture with approved synthetic/deidentified export shapes and jointly map actual exception policy. Production credentials, live AP mutation, payment release, vendor edits, and automatic posting remain out of scope.