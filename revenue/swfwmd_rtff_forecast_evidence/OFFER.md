# Proposed RTFF forecast-evidence workshare — SWFWMD RFP 26-4972

**State:** `PROPOSED_NOT_ACCEPTED`  
**Structure:** subcontract behind a qualified RTFF SaaS prime  
**Fixed fee:** **$18,000 / 10 business days** from prime-approved interfaces, fixtures, freshness limits, model artifacts, and demo scenarios.  
**Optional shortlist/demo support:** **$5,000 / up to 3 business days** after written activation.

## Deliverables
1. Input provenance ledger for scoped District/USGS/NOAA/operator feeds: observation time, fetch time, source identity, payload hash and freshness evidence.
2. Forecast-run manifest: exact model family/artifact hash, input identities, 72h+ horizon, interval, scenario hash, run times and output hash.
3. What-if scenario lineage for rainfall/structure-operation/temporary-pump cases without conflating scenarios with operational authorization.
4. Replay evidence showing whether identical approved inputs/model/scenario reproduce the same output hash; drift is explicit `review_required`.
5. Operational acceptance/demo packet covering stale/missing input fail-close, replay drift, scenario provenance and owner-review release gates.

## Acceptance
On mutually approved non-sensitive fixtures: all scoped inputs have stable identities and agreed freshness limits; run manifests bind exact inputs/model/scenario/output; identical replay either reproduces output or records a review exception; scenario provenance is preserved; and no artifact grants hydrologic-accuracy, emergency-action, production-release or District-submission authority.

## Prime-retained responsibilities
RTFF software/IP, StormWise/SWMM/HEC-RAS execution and scientific validity, model development/calibration, 24/7 SaaS, U.S. hosting, SOC 2/equivalent, public-entity references, SLA/support, pricing/licensing, District communications, proposal forms/signature, safety/operational decisions, production release, demonstrations and submission.

No award/payment/revenue is claimed until separately evidenced.
