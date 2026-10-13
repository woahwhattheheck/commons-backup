# Procurement award source adapters

This layer turns a small set of **buyer-hosted public procurement source shapes** into the strict input consumed by `procurement_award_price_intelligence.engine`. It is internal price research only: adapters do not create a quote, authorize a bid, contact a buyer or partner, recognize an award, invoice, payment, or revenue.

## Trust boundary

`compile_adapter()` fetches the official HTTPS source itself from a code-owned allowlist. The caller does not supply the source hash, source authority, content type, source class, or capture timestamp. The receipt binds the exact fetched bytes (`source_sha256`), final URL, media type, adapter profile, lineage, extraction method/state/coverage, normalized output hash, and hard-false commercial authority. `verify_adapter()` re-fetches the source; if the buyer-hosted bytes have drifted, verification fails rather than silently blessing old extracted rows.

Two profiles ship in v1:

- `LEGISTAR_AWARD_HTML_V1`: code parses a complete public Legistar record. Caller-authored rows are forbidden. Current code-owned hosts are Coral Gables, MWRD, Aurora IL, and Ocala Legistar.
- `BUYER_BID_TABULATION_PDF_V1`: the adapter binds a complete, human-reviewed text extraction to the exact live PDF hash. Current code-owned hosts are City of Coweta and City of Topeka public file hosts.

The PDF profile is intentionally stricter than “someone typed a number from a PDF.” Only `TABULAR_PDF_TEXT / REVIEWED / COMPLETE_TABLE` can promote rows. OCR, ambiguous extraction, partial/unknown table coverage, or any row whose source disposition is `UNKNOWN` yields `HOLD_AMBIGUOUS_EXTRACTION` with zero promoted observations. Rows explicitly marked `REJECTED_BY_SOURCE` are preserved in the receipt’s exclusion list and cannot become comparable bids.

Every held row is still strictly type-checked. A HOLD is not a route for floats, booleans-as-money, malformed dates, duplicate record IDs, or bad currency/basis/unit semantics to enter artifacts.

## Amendment / option / renewal lineage

Requests bind `relation`, `sequence`, and `parent_source_sha256`. `ORIGINAL` requires sequence 0 and a null parent. Later lineage requires a positive sequence plus parent hash. `AMENDMENT` emits source class `AMENDMENT`. `OPTION` and `RENEWAL` emit those price kinds instead of base `AWARD`/`BID`, so the downstream engine cannot silently treat them as historical base-price anchors.

## Current first-party source-shape checks

The shapes were checked against current buyer-hosted public records during implementation:

- MWRD Legistar File 26-0350: final action 2026-05-21; award language names Porter Pipe & Supply Company and a not-to-exceed amount of $94,191.14.
- Coral Gables Legistar File 26-1459: final action 2026-05-05; award language names Coreland Construction Corp. and an estimated amount of $829,898.94.
- City of Coweta 2026 Police Department radio-tower bid tabulation: the official PDF exposes a complete vendor/total table and explicitly marks Second Sight Systems rejected.
- City of Topeka Bid No. 6 (released 2026-02-11): the official PDF exposes complete bidder totals.

These are schema/adapter anchors, not TJLabs bid prices and not buyer commitments. The checked-in Coweta JSON is a reviewed-source example; running it fetches the current official PDF and binds its current bytes before any row can promote.

## CLI

```bash
python -m revenue.procurement_award_price_intelligence.adapters compile \
  --input revenue/procurement_award_price_intelligence/example_adapter_coweta.json \
  --out-dir /tmp/procurement-adapter

python -m revenue.procurement_award_price_intelligence.adapters verify \
  --input revenue/procurement_award_price_intelligence/example_adapter_coweta.json \
  --normalized /tmp/procurement-adapter/normalized.json \
  --receipt /tmp/procurement-adapter/adapter-receipt.json
```

Output files are create-exclusive. Feed `normalized.json` into the existing engine compile/verify flow only after reviewing the adapter receipt and current source.

## Hostile coverage

`test_adapters.py` covers Legistar code-derived parsing; complete reviewed PDF rows; source hashes; rejected/unknown dispositions; OCR/ambiguous/partial holds; option/renewal/amendment lineage; unknown hosts and off-host redirects; media-type/PDF magic mismatches; duplicate JSON/record IDs; bool/float money; exact verification; output tampering; future capture timestamps; and live-source byte drift. The path-scoped workflow runs both normal and `python -O` suites.
