# Procurement Award Price Intelligence

Evidence-first pricing research for public procurements. This workbench answers a narrow question: **what historical prices are actually comparable to this target price basis?** It does not produce or authorize a quote.

A usable price observation must keep the dimensions that procurement teams routinely flatten by accident: currency, price basis, unit, term, price kind, vendor/opportunity identity, event date, and exact evidence sources. Buyer-official award/bid evidence can support a range; budgets, estimates, ceilings/NTEs, options and renewals remain visible inputs but never become an award/bid anchor in v1. Secondary indexes, self-authored notes and synthetic fixtures cannot create an admissible market anchor.

Statuses are deliberately small: `PRICE_EVIDENCE_READY`, `HOLD_NO_HISTORY`, `HOLD_STALE`, `HOLD_SOURCE_CONFLICT`, `HOLD_INCOMPARABLE`. Cross-currency records are incomparable in v1 instead of silently converted. Annual vs total-term, hourly/unit vs lump-sum, and different units/terms are separate classes. Conflicting buyer-official claims HOLD.

Money is integer minor units; JSON floats, booleans masquerading as integers, duplicate keys, BOMs and malformed timestamps/hashes are rejected. Compile output is canonical JSON + a Markdown memo + deterministic receipt. Verification recompiles from exact input bytes and catches packet/memo/receipt tampering.

Every output hard-codes external authority false: no quote, bid, submission, buyer/partner contact, signature, price commitment, award, invoice, payment, or revenue recognition.

The checked-in example is **synthetic fixture data only**, designed to HOLD rather than impersonate public-buyer evidence. Current first-party source-shape examples discovered during design include the State of Iowa contract portal (awarded vendor plus dated Bid Tabulation/contract attachments) and MWDOC's current D365 post-implementation support RFQ (fully burdened hourly rates plus optional prepaid blocks). Those references motivated the schema; they are not copied into the synthetic price fixture and do not price a TJLabs bid.

```bash
python -m revenue.procurement_award_price_intelligence.engine compile \
  --input revenue/procurement_award_price_intelligence/example.json --out-dir /tmp/price-intel
python -m revenue.procurement_award_price_intelligence.engine verify \
  --input revenue/procurement_award_price_intelligence/example.json \
  --packet /tmp/price-intel/packet.json --memo /tmp/price-intel/memo.md --receipt /tmp/price-intel/receipt.json
```
