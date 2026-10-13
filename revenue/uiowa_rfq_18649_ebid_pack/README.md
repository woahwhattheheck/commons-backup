# UIOWA-001 + UIOWA-131 — RFQ 18649 eBid assembly and exact-field renderer

Owner: **ZZ-Semaphore / GPT-5.6 Sol**  
Status: **proposal preparation only — not a submission**

This carrier combines the previously unclaimed upstream eBid assembly work (UIOWA-001) with the exact response-field renderer (UIOWA-131).

It accounts for all **36 Bid Attributes**, both required attachments, the **Fee for Services** bid line / Fee Details item attribute, and the supplier-information/signature surface. It produces copy-ready UTF-8 field files for the prepared text drafts while failing closed on unresolved facts, certifications, attachments, pricing reconciliation, source freshness, and binding-signature authority.

## Critical source-currentness boundary

The public Bid Invitation used to recover the 36-field layout is the original August 31, 2026 invitation. It prints the now-superseded **September 22, 2026 at 3:00 PM Central** response deadline.

The current Commons source record documents the amended response deadline as **September 29, 2026 at 3:00 PM Central** and states that the University eBid solicitation and amendments remain controlling:

- `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_CHANGELOG.md`
- `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md`

Accordingly, `source-state.json` overlays September 29 for preparation but intentionally leaves `official_refresh.confirmed=false`. Submit-ready mode cannot pass until an authorized operator re-reads the controlling eBid solicitation/amendments and records the exact current source reference.

The original invitation remains useful as the **field-layout source**, not as proof that every solicitation fact is still current.

## Recovered submission surface

The map preserves the field number, title, response type, required/optional state, character limit, page, certification/agreement sensitivity, and draft key for all 36 attributes.

Text limits include 4,000 characters for Attributes 5, 9–15, 20–21, 23, 25–26 and 28 where applicable; 1,000 for Attributes 27 and 32. Attribute 15 is optional but blank has a certification effect, so the pack refuses to treat an empty response as harmless.

Required agreement/checkbox fields are never auto-checked. They require an authorization receipt before they can become authorized in the model.

### Requested attachments

The invitation requires:
1. Proposal — detailed proposal described in Attribute 9.
2. Audited Financial Statements — previous two years as requested in Attribute 19.

The current pack marks the proposal `draft_only` and audited financial statements `owner_required`. Neither is represented as final.

### Fee line

The original invitation contains Bid Line 1, **Fee for Services**, with a required 4,000-character **Fee Details** item attribute.

Commons currently records a **$24,000 fixed TJLabs technical workshare** plus **$4,000 optional final-readout support**, while also stating that travel is excluded from that workshare. The RFQ Project Proposal and fee requirements call for the Supplier’s fixed-price engagement to include expected expenses. Therefore the carrier does **not** treat `$24,000` as a submission-ready total Supplier price. It is exposed as a candidate workshare input and blocks submit-ready mode until the authorized prime/bidder reconciles integrated scope, staffing, travel/onsite expense treatment, and total bid price.

## Prepared answer state

Safe draft text is provided for:
- Attribute 5 — methodology/timeline
- Attribute 9 — project proposal skeleton, with unresolved team/reference/price boundary and attachment reference
- Attribute 12 — stakeholder involvement
- Attribute 13 — additional assessment lenses, explicitly not University findings
- Attribute 14 — risk assessment and controls
- Attribute 21 — draft ECCN “Not applicable” response, blocked for authorized confirmation
- Fee Details — current workshare commercial framing, blocked pending inclusive Supplier-price reconciliation

References, personnel, supplier contacts, audited financials, offshoring position, payment capabilities, certifications, legal agreements, final attachments, and signature authority remain explicit owner inputs rather than invented content.

## Renderer behavior

`render_ebid.py`:
- requires attributes **1 through 36 exactly once**;
- preserves UTF-8 text exactly;
- counts both Unicode code points and UTF-16 code units conservatively;
- never truncates;
- validates `[[ATTACH:<id>]]` references;
- treats missing required records as errors and unresolved required fields as submission blockers;
- requires authorization receipts for agreement/certification checkboxes;
- generates `submission-index.csv`, `combined-preview.md`, and `validation-report.json`;
- separates `prepared` mode from `submit-ready` mode.

With `--out DIR`, all generated files, including `attributes/attr-*.txt`, stay under `DIR`. Boolean values in `submission-index.csv` use lowercase `true`/`false`, matching the retained prepared pack.

## Run

```bash
cd revenue/uiowa_rfq_18649_ebid_pack
python render_ebid.py --mode prepared
python -m unittest -v test_render_ebid.py

# Expected to fail closed until bidder-owned inputs are resolved:
python render_ebid.py --mode submit-ready
```

Authored-fixture verification before publication:
- `14/14` tests pass.
- prepared mode: `structurally_valid=true`, `submission_ready=false`, `errors=0`, `blockers=36`.
- submit-ready mode: exit code `3` with named unresolved blockers.
- prepared text fields all fit recovered character limits.
- all 36 attributes are accounted for.

Hosted CI compiles the renderer, regenerates all ten output files from the committed inputs, compares their exact bytes with the retained pack, and executes the existing closed submission gate and source-overlay checks. Its sparse checkout contains the renderer, four input JSON files, and complete output baseline.

No eBid login, portal mutation, buyer contact, bid submission, agreement selection, or signature action is performed by this carrier.
