# SCDHHS Medicaid Clinical Data Exchange — 5400030026

Operation key: `SCDHHS-MCDE-5400030026-QUALIFICATION-MATRIX-20260913`

This package is an **internal, fail-closed evidence qualification control** for
the South Carolina Department of Health and Human Services Medicaid Clinical
Data Exchange (MCDE) solicitation. It does not contact the buyer, submit an
offer, set price, make a certification, sign a contract, authorize spend,
deploy anything, recognize payment, or recognize revenue.

## Retained source snapshot, not live-current authority

The repository trust root was transcribed from official State of South Carolina
sources on 2026-09-13:

* SC Business Opportunities listing:
  `https://scbo.sc.gov/online-edition?c=7-2026-08-29`
* SCEIS solicitation attachment index:
  `https://apps.sceis.sc.gov/SCSolicitationWeb/contractSearch.do?solicitnumber=5400030026`

At capture time the official index showed 33 solicitation attachments and a due
date of 2026-10-15 11:00 ET. `Amendment 1.pdf`, posted 2026-09-11 10:18:53 ET,
was the controlling complete replacement document; Amendment 1 directs
prospective offerors to discard the original solicitation and use the replacement
when preparing bids.

**Important authority boundary:** the compiler is offline. A caller can replay an
old observation, so equality with `source_contract.json` proves only
`source_snapshot_match=true`. It does **not** prove that the State has not posted
Amendment 2, changed the deadline, or otherwise changed the live buyer corpus.
The receipt therefore hardcodes:

* `source_current=false`;
* `live_source_review_required=true`; and
* `deadline_status="NOT_EVALUATED"`.

A source mismatch still fails closed as `HOLD_SOURCE_SNAPSHOT_MISMATCH`, but a
perfect match can only reach an evidence-ready state. Before any external bid or
current-readiness conclusion, an independent operator must reacquire the live
State source and confirm the current generation/deadline. No caller-supplied
JSON can promote this carrier to live-current authority.

Negative conclusions are equally snapshot-relative. Missing retained Amendment-1
evidence emits `SNAPSHOT_MANDATORY_EVIDENCE_GAP`, never a current `NO_GO`;
proposal-readiness evidence gaps emit `SNAPSHOT_PROPOSAL_EVIDENCE_GAP`. A later
buyer amendment could relax or replace retained requirements, so only a trusted
live-source review may make a current bid/no-bid conclusion.

No buyer file bytes were persisted in this repository, so
`buyer_bytes_captured=false` and `buyer_file_sha256=null`; the package never
invents a buyer-file digest.

## Mandatory §5.2 evidence gate

Against the retained Amendment 1 snapshot, the repository-owned minimums are:

1. at least 36 months of offeror experience as prime contractor and at least
   three distinct federal/state/local/private healthcare entities where the
   offeror was prime contractor and a proposed solution of similar size and
   scope is/was implemented;
2. at least 36 months of real-time ADT solution experience, including at least
   24 months in healthcare; and
3. at least one successful prior ADT implementation for a health plan/system
   with at least 1,000,000 lives.

The compiler requires evidence references for the duration claims, every
qualifying healthcare entity, and the million-lives implementation. A candidate
packet cannot lower repository thresholds.

A candidate that clears the offeror-specific minimums and readiness evidence is
**not** labeled State-qualified. The strongest offline prime result is
`PRIME_EVIDENCE_READY_FOR_LIVE_SOURCE_REVIEW`; `prime_qualification_candidate`
remains false until a separate live-source / procurement review exists.

## Teaming route

Amendment 1 §5.2 allows an offeror to explain relationships to key personnel,
predecessor businesses, or subcontractors whose qualifications it wants
considered. This package deliberately does not interpret that as permission to
erase the offeror-specific prime-history minimum.

Likewise, arbitrary strings such as `"Qualified Prime"` or a caller-supplied
reference label cannot prove another company actually cleared §5.2. The
`subcontractor_to_qualified_prime` route therefore remains
`TEAMING_DISCOVERY` even when a prospective prime is named and review references
exist. The receipt may mark `teaming_evidence_candidate=true` to show that an
internal partner-review packet is assembled, but it always includes
`QUALIFIED_PRIME_REVIEW_REQUIRED`; it never emits a team-ready or bid-ready
state without separate trusted prime review authority.

This leaves the commercially sensible lane intact: TJLabs can prepare to serve
as a bounded specialist subcontractor to a genuinely qualified prime, while the
carrier refuses to manufacture that prime qualification itself.

## §5.5 subcontractor identification

For subcontracting above 10% of cost, involving government information, or
otherwise critical to performance, the retained Amendment 1 snapshot requires
identification including business name, address, phone, taxpayer identification
number, point of contact, and work to perform.

A bare `identification_complete=true` has **no authority**. For a triggered
subcontractor, the packet must include:

* business name and scope;
* business address;
* phone;
* point of contact;
* one or more identification evidence references; and
* a private taxpayer-ID evidence reference plus lowercase SHA-256 digest.

Raw taxpayer IDs are not emitted into the receipt. The digest/reference pair is
intended to bind an owner-held private artifact without publishing the TIN. If
the required subcontractor control tuple is incomplete, the result holds with
`SUBCONTRACTOR_IDENTIFICATION_INCOMPLETE`. Even when every privacy-safe evidence
component is assembled, the offline carrier still emits
`SUBCONTRACTOR_IDENTIFICATION_REVIEW_REQUIRED`: caller-authored evidence cannot
self-certify that the private identity packet is truthful or complete. A
separate trusted procurement review must clear that external readiness gate.

Separately, when the packet asks the State to consider a subcontractor's
qualifications, nonempty `qualification_evidence_refs` require
`relationship_explained=true`, matching the §5.2 relationship requirement.

## Readiness gates

The compiler separately holds for proposal-readiness evidence derived from the
retained Amendment 1 snapshot:

* proposed Project Manager: 36 months MCDE, including 24 months healthcare;
* HIPAA compliance and ATTM 005 Business Associate Agreement readiness;
* encryption in transit and at rest for government data / PHI;
* NIST SP 800-53 Rev. 5, NIST SP 800-53B, NIST SP 800-171 Rev. 3,
  FIPS 140 as amended, CMS ARC-AMPE, SSA security requirements, and SCDIS-200.

Every security/readiness control requires both an explicit boolean and evidence
references. These are evidence-readiness controls, not certifications.

## Evaluation leverage

The retained Amendment 1 snapshot allocates 1,000 evaluation points: 700
technical, 200 price, and 100 demonstration. Qualification/source review is only
the first gate. If a genuinely qualified prime is secured, specialist effort
should concentrate on implementation/go-live, interoperability, data quality,
reporting, governance, security evidence, and demo reliability rather than
pretending to supply the prime's past-performance history.

## Usage and receipt semantics

```python
from revenue.scdhhs_mcde_5400030026 import compile_qualification

receipt = compile_qualification(packet, source_observation=retained_snapshot_capture)
```

`source_observation` is intentionally separate from candidate evidence, but it
is still caller-supplied and therefore **not live-current authority**. It is used
only to detect whether supplied bytes match the retained repository snapshot.

The deterministic receipt binds:

* repository source-contract SHA-256;
* exact source-observation SHA-256;
* exact candidate-packet SHA-256; and
* the compiled result SHA-256.

`verify_receipt(...)` recompiles and byte-compares canonical JSON. It verifies
integrity of this offline evidence packet, not live State currentness.

## Current TJLabs disposition

This package contains **no fabricated TokenJunkieLabs experience,
certification, customer, healthcare, ADT, security, or million-lives evidence**.
Until owner-held evidence proves the offeror-specific §5.2 minimums and a
separate live-source review confirms the current solicitation generation, do not
label TJLabs prime-qualified or bid-ready. Existing partner outreach remains a
potential path to a qualified prime with TJLabs in a bounded specialist role;
this carrier does not duplicate outreach or manufacture the partner's
qualification.
