# OCS2026.01 official-source checkpoint — October 4, 2026

## Disposition

**Official text located and read; raw-source binding and supplier qualification remain incomplete.** This checkpoint corrects the existing carrier's source interpretation. It does not represent a new buyer instruction issued on the observation date or a complete comparison against an earlier RFQ: the retained September 18 ledger contains secondary observations, not an earlier official PDF generation.

The original carrier and accepted engineering proof remain usable reference assets. The present workshare follows the source rows below. An internal capability inventory is not evidence that its listed software is a purchased RFQ deliverable.

## Official sources and coverage

- **Board:** [DoIT SLCGP program page](https://www.doit.nm.gov/programs/cybersecurity/state-and-local-cybersecurity-grant-program-slcgp), RFQ section. It links the two documents below.
- **Base:** [Official RFQ](https://www.doit.nm.gov/assets/docs/RFQ-Third-Party-Risk-Management-Project.pdf).
- **Q&A:** [Official October 2 answers](https://www.doit.nm.gov/assets/docs/RFQ-Third-Party-Risk-Management-Project-Questions-and-Answers-2026-10-02.pdf).

Read coverage: all 83 rendered board lines; all 369 rendered RFQ lines across 12 PDF pages; all 268 rendered Q&A lines across two PDF pages, including all 26 numbered answers and matching questions. Page references below are physical PDF pages, starting at 1. Raw bodies, byte sizes, SHA-256 identities and visual layout were not acquired or reviewed. Rendered text coverage does not fill those gaps. The title exposed for the Q&A mentions a spreadsheet; the linked object is served as a PDF.

## RFQ reading

| ID | Locator | Source reading |
| --- | --- | --- |
| B1 | §§3,5; pp. 1–4 | Six outputs: current-state and gap reports, standards recommendations, model ordinances, model clauses, final report. |
| B2 | §4; p. 3 | Quotes over $60,000 require current SWPA/GSA/NASPO awardee status. The threshold is not the budget. |
| B3 | §6; pp. 4–5 | Summary, plan/KPIs, key-person credentials, samples, at least three comparable form references, federal forms A and cost form B. |
| B4 | §6g / Attachment B; pp. 4–5, 11–12 | Time-and-materials, not-to-exceed total and completion guaranty; supplier bears underestimated effort. |
| B5 | §7; p. 5 | Evaluation: technical 30%, approach 30%, cost 20%, past performance 10%, compliance 10%. |
| B6 | §§8,10; pp. 5–6 | October 16, 2026 response date; no printed clock time/timezone. Six months from effective date. |
| B7 | §3c; p. 2 | NIST 800-53 Rev. 5 Moderate, 800-161 and applicable guidance. |

## Q&A reading

| ID | Locator | Source reading |
| --- | --- | --- |
| W1 | Q16; p. 2 | Recommend tool characteristics; specific tool selection/procurement is outside the RFQ. |
| W2 | Q3,12; p. 1 | Contractor drafts model ordinance language; State/counsel retains formal legal review, refinement, validation and adoption. |
| W3 | Q1,5,6,9; p. 1 / Q20; p. 2 | Entity scope, assessment depth, baselines and engagement answers deferred through October 7; other deadlines unchanged. |
| W4 | Q4; p. 1 / Q21,22; p. 2 | Official pricing form B; scope changes require formal modification; hours reallocation needs OCS approval. |
| W5 | Q23,24; p. 2 | Relevant prime/personnel experience may be documented; no additional specified personnel minima. |
| W6 | Q8,11,13; p. 1 | Consolidated analysis with profiles; configurable ordinance and clauses. |
| W7 | Q14; p. 1 | Offshoring/data-residency provisions. This answer does not establish a blanket US-only condition. |

W7's final sentence is an interpretation limit, not an additional buyer condition. The board's local-entity program-participation requirements must not be relabeled as supplier qualification.

## Application to this carrier

The existing `tprm.py`, CLI, qualification logic and examples remain unchanged. Workshare wording now separates the original engineering inventory from a proposed RFQ contribution. It avoids treating the original mirror-driven software plan or an unevidenced counsel assumption as an established buyer requirement.

The `packet.status=VERIFIED` path requires an exact digest. Neither this note nor its observation JSON is a replacement qualification input. The retained `PUBLIC_SOURCE_LEDGER.json` and `examples/qualification_public_only.json` remain the historical generation. No new gate execution or readiness output is claimed. Missing supplier evidence remains missing; no budget, quote, staffing, certification, signature or submission authority is supplied.

## Next source and owner work

Complete the remaining source binding and inspect subsequent answers when available. Then map actual supplier evidence and the proposed contribution to the controlling generation. Keep unresolved scope explicit when estimating effort. The official source's threshold, published date and State role allocation do not grant supplier eligibility or authorization to contact, price, sign or submit.

Original custody: [#15842](https://github.com/woahwhattheheck/commons/issues/15842), accepted [#15867](https://github.com/woahwhattheheck/commons/pull/15867), ZZ-KESTREL-M8D3 recovery and ZZ-IBIS-93C-R3 repair/review. The separate [#30624](https://github.com/woahwhattheheck/commons/pull/30624) workflow update remains outside this document change.
