# Public-Sector Integration Workshare Pack

Operation: `PUBLIC-SECTOR-WORKSHARE-CAPTURE-20260913`
Recovery builder/finalizer: **Zeta-Five / GPT-5.6 Sol**
Commercial state: **PROPOSED_NOT_ACCEPTED**

This package turns Commons issue #14283 into a reusable, bounded subcontract offer for public-sector modernization primes. It does **not** posture TokenJunkieLabs as the enterprise platform prime. The pack sells proof-heavy engineering work that can sit beside a prime-owned platform implementation: migration reconciliation, interface conformance/replay, UAT evidence, and cutover/delta receipts.

## Why this recovery exists

Two #14283 opportunities already have merged qualification carriers and are preserved rather than reminted:

- Oregon ODA `S-DASOBO-00017788`: PR #13907, merge `8ffd13dd910589aa7ff7e56862b1740f07efea5e`.
- NYSED RFP #144: PR #13547, merge `4178bc0daf9d6fa11fabf818d96062dc0915447d`.

The still-missing work was the reusable commercial pack plus thin overlays for the Illinois CDB/DoIT modernization and North Carolina DHHS/DHB CLMS pursuits. Those are the two live overlays in this directory.

## Offer shapes

The pack carries two explicit **commercial hypotheses**, not accepted business:

- **$25,000 fixed / 2–4 week pilot** — one bounded migration or integration evidence seam, synthetic/non-production proof, acceptance matrix, and reproducible handoff.
- **$125,000 fixed / 8–12 week implementation workshare** — migration evidence, up to eight interface conformance families, UAT evidence, and one cutover rehearsal/reconciliation workstream.

Both remain `PROPOSED_NOT_ACCEPTED` until a counterparty explicitly accepts a scoped offer. No award, receivable, recognized revenue, payment, or buyer budget is asserted by these bytes.

## Modules

`pack.json` defines four reusable modules with exact inputs, outputs, acceptance tests, and exclusions:

1. `MIGRATION_EVIDENCE`
2. `INTEGRATION_CONFORMANCE`
3. `UAT_ACCEPTANCE_EVIDENCE`
4. `CUTOVER_REPLAY`

The pack deliberately leaves platform licensing, prime solution architecture, regulatory/security certifications, buyer sign-off, and production deployment authority with the prime/buyer unless separately evidenced and contracted.

## Live opportunity overlays

### Illinois DoIT + CDB — `27-448DOIT-ADMIN-B-52519`

Primary source: https://cdb.illinois.gov/procurement/camp-rfp.html

The official CDB notice describes a statewide cloud construction-project-management modernization with full lifecycle project/procurement/contract/invoice/document workflows, legacy migration, SAP ERP integration, CEI/SOS integration, and future interface needs. The pack therefore positions TJLabs only for **legacy migration reconciliation + SAP/interface contract verification + deterministic UAT/cutover evidence**. The System Implementor/platform prime retains the platform, SAP solution, security/compliance and full-program obligations.

The CDB notice points bidders to BidBuy under the exact solicitation ID and describes the System Implementor as the prime. `buyer_budget_usd` remains `null`; no unsupported budget is invented.

#### Illinois source update — 2026-10-04

The [official BidBuy notice](https://www.bidbuy.illinois.gov/bso/external/bidDetail.sda?docId=27-448DOIT-ADMIN-B-52519) displays an October 28, 2026 opening at 14:00; the header does not identify its timezone. `OPEN` is Bid Type, not a separate acceptance-status finding.

The notice lists twelve files and two amendment entries. September 9 amendment 1 records a corrected traceability-matrix bid number and a question date added to RFP C.10. September 18 amendment 2 adds `IL CDB Pre-Submission Conference.zip` for slides, attendance and recording. The latter postdates the overlay's September 16 capture.

The board reports BEP/VBP goals of 7%/1%, with no small-business set-aside. Required uploads include disclosure, signed offer, technical response, pricing, utilization plans and C2D answers. Pricing must also populate the Items tab from Attachment B's Total Price Summary, B20; pricing-file classification and specified missing uploads carry disqualification/nonresponsiveness warnings.

Coverage is all 81 rendered notice lines. Attachment contents, file bytes/hashes, full amendment effects, C.10's actual date and deadline timezone remain unverified; no anonymous attachment links were exposed. This is a notice-level addition, not complete solicitation custody.

The September 16 machine overlay remains a historical snapshot; this documentation does not refresh its source timestamp or clear its unresolved-timezone HOLD. Preserve the original ZSQY-A4C7 scouting, all #14283/#14882 implementation and recovery credits, partner-first posture, unknown buyer budget, proposed prices and existing contact boundaries. The next source task is controlling RFP/attachment custody and reconciliation of these notice instructions. No contact, registration, submission, signature, pricing commitment or eligibility is authorized. Machine inputs, validator and accepted historical execution are unchanged; no native run occurred.

### North Carolina DHHS / DHB — `30-2025-037-DHB`

Primary source: https://evp.nc.gov/solicitations/details/?id=5d9802e7-e99b-f111-8077-001dd80bcb64

The current eVP notice describes a comprehensive cloud CLMS for Medicaid-related contracts with implementation, data migration, workflow automation, vendor-performance monitoring, Office 365/SharePoint/Adobe/DocuSign interoperability, optional ServiceNow/NCFS integration, training/support, and State privacy/security/enterprise-architecture obligations. The RFP package also includes an Attachment Z Subcontractor Identification Form, so the overlay preserves a subcontract path without claiming that TJLabs satisfies the prime's CLMS SaaS or Medicaid past-performance gates.

The workshare wedge is **contract-corpus migration verification + integration conformance/replay + deterministic UAT/cutover evidence**. Buyer budget remains unknown here.

## Duplicate-contact prevention

The repository does not store a send route for either live overlay. Outbound execution is a separate provider action. `validate_pack.py::collision_key()` provides a deterministic opportunity × target company × route identity. Immediately before a real send, the executor should use the current fleet process the owner specified: fresh Slack relationship/claim census, fresh mailbox/thread census, Muse single-writer selection for that exact tuple, then a second fresh census immediately before the provider mutation. An ambiguous provider result becomes `DNR_RECONCILE_NEVER_RESEND`.

That process is **coordination only**, not authentication or a permission system. It creates no Commons credentials and grants no buyer authority.

## Validation

Run from this directory:

```bash
python -m py_compile validate_pack.py test_validate_pack.py
python -m unittest -v test_validate_pack.py
python -O -m unittest -v test_validate_pack.py
python validate_pack.py
```

The validator rejects commercial-truth drift, prime-readiness drift, outbound/submission assertions, boolean/int aliases, unknown module/offer references, duplicate JSON keys, broken existing-qualification references, and coordination semantics that claim to create security authority.

## Authority ceiling

No buyer/prime contact is performed by these files. No bid or portal submission, account creation, signature, teaming commitment, OEM/certification/security-clearance/public-sector-past-performance claim, buyer acceptance, award, payment, recognized revenue, spend, or production deployment is asserted. External contact, when separately executed, must use literal provider receipts and preserve the exact payment/acceptance state.


## Authority-bound single-writer lease

Duplicate-contact coordination now keys one outbound route by stable `opportunity_id × organization_id × route_id`, rather than display-company or address spelling. Display aliases remain audit text and do not create a second coordination identity.

A target-review packet requires two independently retained objects:

- target authority binds the opportunity, stable organization and route IDs, display labels, generation, capture time and source reference;
- single-writer lease receipt binds that same opportunity/organization/route identity to an arbiter, positive generation, bounded status, acquisition/expiry times and durable receipt reference.

Both objects are checked against independently supplied SHA-256 roots before use. Only an `ACQUIRED`, unexpired lease can clear the lease control at the packet's review time. Relationship/provider-history observations and the opportunity deadline are also re-evaluated for that review rather than inherited from an older packet. A source whose deadline timezone is unresolved remains `HOLD`.

`READY_FOR_OWNER_TRANSPORT_REVIEW` is a coordination result only. The emitted packet keeps `external_send_authorized`, `submission_authorized`, and `payment_authorized` false.
