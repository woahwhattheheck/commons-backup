# Review-draft assembly index

> REVIEW DRAFT ONLY. This folder is an internal assembly of prepared components. It is not a University of Iowa submission, not Clark's Consulting's bid, not an assertion of qualifications or insurance, and not an invoice, payment, or schedule. Missing financial and qualification attachments remain missing.

Solicitation: `18649`  
Bidder: Token Junkie Labs (subcontract workshare; prime not asserted)  
Assembly status: **REVIEW_DRAFT_SUBMISSION_INCOMPLETE**  
Rendered: `proposal.pdf` (7 pages), `proposal.docx`, `proposal.html`

## Commercial facts consumed (UIOWA-132)

- RFQ `18649`, currency `USD`
- TJLabs subcontract workshare $24,000 base + $4,000 option (not the prime bid fee)
- Split 40/40/20 = $9,600 / $9,600 / $4,800
- Principal = prime, specialist = subcontract
- Deadline currentness: **CURRENTNESS_HOLD** (RFQ print 2026-09-22 15:00 America/Chicago; overlay 2026-09-29 15:00 America/Chicago)

## Documents

| # | Section | File | PDF page | Content |
|---|---|---|---|---|
| 1 | Cover letter | `documents/01-cover-letter.md` | 4 | SUPPLIED |
| 2 | Commercial terms | `documents/02-commercial-terms.md` | 5 | SUPPLIED |
| 3 | Methodology | `documents/03-methodology.md` | 6 | SUPPLIED |
| 4 | Exceptions and Attribute 15 | `documents/04-exceptions-and-attribute-15.md` | 7 | SUPPLIED |

## Attachment index

`UNKNOWN` = no file supplied, so nothing could be measured. Not zero.

| ID | Title | Category | Required | Status | File | Bytes | SHA256 | Index page |
|---|---|---|---|---|---|---|---|---|
| ATT-PROP-01 | Detailed proposal (Attribute 9) | proposal | yes | **SUPPLIED** | `attachments/A01-detailed-proposal-attribute-9.md` | 363 | `2c21315194dbf15c` | 2 |
| ATT-FIN-01 | Audited financial statements, preceding two years (Attribute 19) | financial | yes | **PLACEHOLDER-NOT SUPPLIED** | _(placeholder)_ | UNKNOWN | UNKNOWN | 2 |
| ATT-FIN-02 | Annual reports, preceding two years (Attribute 19) | financial | yes | **PLACEHOLDER-NOT SUPPLIED** | _(placeholder)_ | UNKNOWN | UNKNOWN | 2 |
| ATT-QUAL-01 | Key personnel resumes (Attribute 10/11) | qualification | yes | **PLACEHOLDER-NOT SUPPLIED** | _(placeholder)_ | UNKNOWN | UNKNOWN | 2 |
| ATT-QUAL-02 | References / comparable engagements | qualification | yes | **PLACEHOLDER-NOT SUPPLIED** | _(placeholder)_ | UNKNOWN | UNKNOWN | 2 |
| ATT-FEE-01 | Prime all-inclusive Fee for Services (Attribute 9 / Bid Line 1) | financial | yes | **PLACEHOLDER-NOT SUPPLIED** | _(placeholder)_ | UNKNOWN | UNKNOWN | 2 |

## Completeness

**SUBMISSION_INCOMPLETE**

- Required attachments declared: 6
- Present: 1
- Not supplied: `ATT-FIN-01`, `ATT-FIN-02`, `ATT-QUAL-01`, `ATT-QUAL-02`, `ATT-FEE-01`

> Counts describe declared-vs-present documents in this pack only. This is not a readiness score and not University completeness.

## Cross-references

- `S-COVER` -> `S-COMMERCIAL` (section) **RESOLVED**
- `S-COVER` -> `ATT-PROP-01` (attachment) **RESOLVED**
- `S-COVER` -> `ATT-FEE-01` (attachment) **RESOLVED**
- `S-COMMERCIAL` -> `ATT-FEE-01` (attachment) **RESOLVED**
- `S-METHOD` -> `ATT-PROP-01` (attachment) **RESOLVED**
- `S-METHOD` -> `S-APPENDIX-C` (unknown) **UNRESOLVED**
- `S-METHOD` -> `ATT-QUAL-01` (attachment) **RESOLVED**
- `S-METHOD` -> `ATT-QUAL-02` (attachment) **RESOLVED**
- `S-METHOD` -> `ATT-FIN-01` (attachment) **RESOLVED**
- `S-METHOD` -> `ATT-FIN-02` (attachment) **RESOLVED**

## Assembler issues

- **WARN** `ATTACHMENT_NOT_SUPPLIED` required attachment ATT-FIN-01 (Audited financial statements, preceding two years (Attribute 19)) has no file; emitted as a placeholder
- **WARN** `ATTACHMENT_NOT_SUPPLIED` required attachment ATT-FIN-02 (Annual reports, preceding two years (Attribute 19)) has no file; emitted as a placeholder
- **WARN** `ATTACHMENT_NOT_SUPPLIED` required attachment ATT-QUAL-01 (Key personnel resumes (Attribute 10/11)) has no file; emitted as a placeholder
- **WARN** `ATTACHMENT_NOT_SUPPLIED` required attachment ATT-QUAL-02 (References / comparable engagements) has no file; emitted as a placeholder
- **WARN** `ATTACHMENT_NOT_SUPPLIED` required attachment ATT-FEE-01 (Prime all-inclusive Fee for Services (Attribute 9 / Bid Line 1)) has no file; emitted as a placeholder
- **INFO** `COMMERCIAL_FACTS_CONSUMED` consumed UIOWA-132 commercial-facts from pinned-local; $24000 is TJLabs subcontract workshare, not the prime bid fee
- **WARN** `DEADLINE_CURRENTNESS_HOLD` RFQ print 2026-09-22 15:00 America/Chicago vs workshare overlay 2026-09-29 15:00 America/Chicago; official refresh unconfirmed
- **WARN** `PRIME_FEE_NOT_SUPPLIED` $24000 workshare is not the Attribute 9 / Bid Line 1 all-inclusive prime fee
- **WARN** `XREF_UNRESOLVED` section S-METHOD references 'S-APPENDIX-C', which is not a section or an attachment
