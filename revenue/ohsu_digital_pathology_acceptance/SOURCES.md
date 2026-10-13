# Source ledger and claim ceilings

Checked 2026-09-13.

## Buyer source

- OHSU Procurement, Current bids: https://www.ohsu.edu/procurement/bids
  - `RFP-2027-2012` — **Digital Pathology Image Management System**
  - public listing issue date: 2026-09-11
  - public listing proposal due date: 2026-10-11
  - public listing says OHSU Health seeks an enterprise IMS with seamless bi-directional Epic Beaker integration and scalable integration with native and third-party AI/image-analysis applications.
  - **Ceiling:** the listing instructs bidders to read and confirm minimum requirements in the RFP document. This repository does not assert that TokenJunkieLabs independently satisfies those prime-bid minimums.

## Integration contract sources

- Epic Digital Pathology playbook: https://fhir.epic.com/Documentation?docId=chlistingrequest&section=EmbeddedchlistingrequestLaunch_eligibility
  - Beaker sends slide-order information with `OML^O21`.
  - the IMS sends `SSU^U03` per individual slide when image/status information is available.
  - Epic documents optional `ORU^R01` case-finish synchronization.
  - Epic recommends case/slide deep links and binding identifiers to the selected case/slide.
- Epic ancillary-system documentation: https://open.epic.com/Ancillary/Results
  - documents the digital-pathology integration between Beaker and a third-party image-management system using lab order/result interfaces.

## Explicit non-claims

This lane provides no evidence of: OHSU bidder qualification; production Epic connectivity; PHI processing; clinical diagnostic performance; FDA clearance; medical-device status; pathology image interpretation; customer references; vendor partnership; OHSU submission; contract award; payment; or revenue received.
