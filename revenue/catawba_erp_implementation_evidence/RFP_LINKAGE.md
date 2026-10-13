# Catawba County RFP 27-1004 — specialist evidence linkage

## Controlling public sources

- [County bid notices](https://catawbacountync.gov/county-services/purchasing/bid-notices/) — the authoritative posting route confirmed by A2 Q10/Q95.
- [Base RFP](https://catawbacountync.gov/site/assets/files/2340/final_rfp_-_erp_software_and_implementation_services.pdf), issued 2026-08-31.
- [Addendum No. 1](https://catawbacountync.gov/site/assets/files/2340/addendum_no_1_-_amended_bid_schedule_9_15_2026.pdf), issued 2026-09-15.
- [Addendum No. 2](https://catawbacountync.gov/site/assets/files/2340/addendum_no_2_-_questions_and_answers_rfp_27-1004.pdf), issued 2026-09-25; 34 pages, 171 questions.

All four responses were captured as HTTP 200 on 2026-10-04. The [dated source packet](../rfp_addenda_delta/packets/catawba_erp_27_1004_20261004/README.md) contains exact byte identities, original analysis and the actual addenda-checker receipt. County source bytes and extracted text remain intermediate. Attachments A-D were not acquired, so this is not complete solicitation custody or a workbook response.

Addendum No. 1 controls the schedule, reaffirmed by A2 Q11/Q152: written questions were due **2026-09-21 17:00 ET**; County responses were due 2026-09-25 17:00 ET; sealed proposals are due **2026-10-21 15:00 ET** (`2026-10-21T19:00:00Z`); shortlisted demonstrations/interviews are anticipated in the first two weeks of December. A2 Q3 anticipates award in early 2027; Q4 leaves implementation timing to the proposed approach. These dates grant no contact or submission authority.

## Why this is partner-first

The minimum criterion remains **three implementations of the proposed software for organizations of similar size and complexity within the previous five years** (RFP p17, section 5.1.1). A2 Q25/Q69 allow proposed publisher and implementation-partner experience to be presented with clear attribution and a demonstrated comparable context. They do not qualify this workstream or supply missing references; the completed-versus-started-installation question is not separately answered.

A2 Q7-Q9 require a seamless integrated solution with one primary implementor accountable for the whole scope; standalone HCM proposals are not accepted. Q35 explains the named-subcontractor disclosure/approval route under section 7.10. Q129 expresses no preference between an integrator and the primary software company performing implementation. The existing pursuit owner retains team selection and responsibility allocation. Q118 bars Plante Moran from bidding.

The United States data-center/storage minimum remains (RFP p17). A2 Q119 points back to that page; this packet does not invent an additional offshore-personnel rule.

Catawba has used Oracle PeopleSoft for Financials, Supply Chain Management and HCM for more than 25 years and seeks a modern cloud ERP plus implementation partner (RFP p6). The County calls for project/change management, training, knowledge transfer, technical guidance, data migration, integrations and post-go-live support.

## Addendum 2 implications for this workstream

| Topic | Current source and implication |
| --- | --- |
| Proposal validity | Q23, p6 changes 90 days to **120 days** after the due date. This does not accept or reprice the internal specialist offer. |
| Migration | Q20, p5 gives three years across PeopleSoft HR/Finance/Budget and 500-600 GB. Q90-Q91, p18 and Q134, pp24-25 require an object-specific calendar/status interpretation; no universal extra year is assumed. |
| Source documents | Q149, p27 includes in-window source documents (120,000 financial and 84,000 HR); Q150 requires the existing account structure. Q13/Q144/Q155 exclude existing Laserfiche migration and clarify that ERP replacement of Laserfiche is not expected. |
| Integrations | Q71, p15 assumes initial-go-live integrations while allowing phasing discussion. Preserve the separate API/third-party charge statements in Q14/Q43/Q159 until responsibilities are assigned per interface. |
| Response files | Q24/Q36/Q164/Q165 clarify the physical proposal, USB PDF plus native A-D workbooks, and the Excel Questionnaire as the hosting-form location. Q29/Q76-Q79/Q165 preserve the 20-page Executive Summary cap with stated appendices excluded. |
| Core scope and pricing | Q133/Q139/Q143/Q156/Q163 clarify required-area pricing, native learning functionality, workforce scheduling and grouped modification disclosures. Actual workbook rows still need binding; the synthetic pack does not satisfy them. |
| Insurance and agreements | Q33/Q94 specify minimum insurance lines including E&O. Q31 retains uncapped breach-remediation exposure. Q34/Q39/Q64 permit disclosed exceptions for County consideration; Attachment F is acknowledged, not signed, with the proposal. No proposed exception is accepted here. |
| Hosting and commercial terms | Q151 makes the stated 99.99% uptime a requested SLA disclosure, not a proposal-disqualifying pass/fail gate. Q37 requests at least a five-year term, renewal capability and annual uplift caps; this workstream supplies no hosting or subscription commitment. |

SSO remains a source-scope issue: Q15, p4 affirmatively answers a compound cloud identity/hosting question, while Q62, p14 says SSO is not needed at that time in the timekeeping question sequence. Preserve both answers for the security owner; do not infer a blanket exemption or claim compliance with every referenced framework. [source-review.json](../rfp_addenda_delta/packets/catawba_erp_27_1004_20261004/source-review.json) also retains the ambiguous Q158 timing answer and all five unresolved interpretation points.

## Scored-round linkage

| County round-two category | Weight | Workstream contribution | Boundary |
| --- | ---: | --- | --- |
| Functionality, including integrations with County systems | 30% | interface replay/idempotency evidence; requirement-linked UAT hashes | no ERP module/functionality claim |
| Technical and support | 20% | deterministic migration/replay evidence and recovery cases | no hosting/SLA/security-certification claim |
| Implementation approach, staffing, division of responsibility | 20% | bounded workshare, acceptance criteria, exception/cutover gate | prime owns overall implementation/staffing |
| Cost | 15% | fixed $32k specialist tranche + optional $8k shortlist support | does not fill County pricing forms |
| Vendor experience/stability | 15% | no borrowed credentials | prime retains qualifying installs/references |

The weights are from RFP section 5.1.2, p17. A2 Q27/Q83 clarify that Round 3 is scored independently, without carrying or combining Round 2 scores. This package is supporting evidence for a qualified prime, not a row-level response to Attachment C and not a County proposal.

Original pursuit/product credit remains Z-CinderAtlas-0558-N7Q4 under [#14809](https://github.com/woahwhattheheck/commons/pull/14809); accepted repair/main-integration credit remains Z-PalladiumHelix-0820-N4V7. `OFFER.md`, implementation source, synthetic fixture and accepted proof remain intact. The original README outbound guard and all authority limits continue to apply.
