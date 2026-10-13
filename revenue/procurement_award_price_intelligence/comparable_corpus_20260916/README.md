# Public procurement award comparable corpus — 2026-09-16

Operation: `PUBLIC-PROCUREMENT-AWARD-COMPARABLE-CORPUS-20260916`  
Carrier: Commons issue #15160  
Truth boundary: `INTERNAL_PRICE_RESEARCH_ONLY`

This is the current-data successor to `revenue/procurement_award_price_intelligence`; it does **not** replace the existing engine or live source-adapter trust boundary.

## Snapshot

The retained snapshot contains **25 included records**, **20 official buyer source pages/documents**, and **3 buyers**: MWRD, City of Coral Gables, and City of Coweta. It spans **19 AWARD** observations plus **6 BID** observations using the existing Legistar award-HTML and buyer-hosted bid-tabulation PDF source shapes. One Coweta bid is retained only as an exclusion because the official tabulation marks it rejected.

The data deliberately spans exact contract-total values from small supply awards through large infrastructure awards. That breadth tests source custody and exact-class filtering; it does not make unrelated scopes economically comparable.

## Fail-closed raw-source custody

The regular-chat research surface verified the official buyer pages, but the local code container could not reach public DNS and the web surface does not expose buyer response bytes. Therefore no parsed-page digest is mislabeled as the buyer's raw SHA-256.

Every source has a content-addressed canonical research snapshot and every record a canonical extracted-claim digest, but checked-in `raw_source_sha256` is `null`, `raw_hash_state` is `PENDING_LIVE_ADAPTER_FETCH`, and all 25 included records are `HOLD_RAW_SOURCE_HASH_PENDING`. A `--ready-only` query returns `NO_READY_COMPARABLES`.

The only promotion path is `hydrate_corpus.py`: it delegates HTTPS fetch, allowlisted-host authentication, content-type verification and raw-byte SHA-256 to the existing code-owned source adapters. A source becomes `VERIFIED_LIVE_ADAPTER` only when the adapter's live normalized observation set exactly matches the retained claims.

## Source families

- MWRD Legistar: 15 adopted 2026 award actions, including September 3 files `26-0580`, `26-0581`, and `26-0582`.
- Coral Gables Legistar: files `26-1459`, `26-1372`, `26-1191`, and `25-9436`.
- City of Coweta: April 22, 2026 Police Communications Radio Tower bid tabulation. Six bids are included. Second Sight Systems is excluded because the official PDF marks its packet rejected for labeling.

Coweta source: `https://www.cityofcoweta-ok.gov/DocumentCenter/View/2084/260427-Bid-Tab-PDF?bidId=`

## Exact comparable dimensions

Each record preserves buyer/source, official URI, opportunity/file ID, vendor, integer minor-unit amount, currency, basis, unit, term, event date, price kind, extraction state, source disposition, promotion state and claim SHA-256. Corpus v1 retains `USD`, `CONTRACT_TOTAL`, `unit=null`, and `term_months=null`; it performs no FX, inflation, scope, unit, term or buyer-budget conversion. `AWARD`, `BID`, `OPTION`, `RENEWAL` and amendment source classes remain distinct.

## Component-addressed carrier

`manifest.json` binds split `sources_*.json`, `records_*.json`, and `exclusions_*.json` by canonical SHA-256 and exact count. `assemble_corpus.py` verifies those commitments before invoking `validate_corpus.py`. `query_corpus.py` is read-only. `hydrate_corpus.py` is the sole live-adapter promotion bridge.

Validate:

```bash
python revenue/procurement_award_price_intelligence/comparable_corpus_20260916/assemble_corpus.py
python -m unittest -v revenue.procurement_award_price_intelligence.comparable_corpus_20260916.test_corpus
python -O -m unittest -v revenue.procurement_award_price_intelligence.comparable_corpus_20260916.test_corpus
```

Expected snapshot summary:

```text
VALID records=25 sources=20 buyers={'City of Coweta': 6, 'Coral Gables': 4, 'MWRD': 15} readiness={'HOLD_RAW_SOURCE_HASH_PENDING': 25}
```

A custody-requiring query:

```bash
python revenue/procurement_award_price_intelligence/comparable_corpus_20260916/query_corpus.py --buyer MWRD --price-kind AWARD --ready-only
```

returns `NO_READY_COMPARABLES` until live hydration succeeds.

Live hydration, from an environment with access to the allowlisted buyer hosts:

```bash
python -m revenue.procurement_award_price_intelligence.comparable_corpus_20260916.hydrate_corpus --out-corpus /tmp/corpus-hydrated.json --out-report /tmp/corpus-hydration-report.json
```

Hydration emits a separate corpus/report; it does not mutate buyer systems or the checked-in snapshot.

## Authority ceiling

All authority fields are hard-false. This corpus does not authorize or establish a TJLabs quote, bid, submission, buyer/partner contact, price commitment, buyer budget, undercut recommendation, award, payment, cash receipt or booked revenue. It is internal market-evidence infrastructure only.
