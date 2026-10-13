# Exeter RFP 2026-06 — Q&A review and workshare scope

Reviewed: 2026-10-04. Operation: `EXETER-QA-COVERAGE-20261004-7CA6`.

The [official Q&A](https://cityofexeter.ca.gov/wp-content/uploads/2026/09/questions-and-answers-rfp-no.-2026-06-1.pdf) was read through answers 1–38, across all 10 pages of extracted text. The table below completes the answer-coordinate coverage of the 20 selected rows in [the retained source review](captures/20261003/source-review.json). It records source context and qualifications; it does not classify every answer as a new obligation.

The retained Q&A copy is [captures/20261003/raw/qa.pdf](captures/20261003/raw/qa.pdf), Git blob `3e721a296ab32c3b1d5b91df9a3b46a3f6d26398`, SHA-256 `c83e7bfc77c9f5594381a67d61e8e7ca6271e24c0c21fffd80ab0500d3847cc5`, as captured by [#30973](https://github.com/woahwhattheheck/commons/pull/30973). Those are the existing capture identities, not a new byte comparison of the current web response.

## Answer coverage

| Answers | Location considered |
| --- | --- |
| Q1–4 | Existing primary-vendor, year-one-budget and price-horizon rows |
| Q5–6 | Context below |
| Q7 | Existing license-users row |
| Q8 | Context below |
| Q9 | Existing work-order-scope row |
| Q10–11 | Context below |
| Q12–15 | Existing experience, delivery-route, references and onsite rows |
| Q16 | Context below |
| Q17 | Existing history-depth row and qualification below |
| Q18–22 | Existing customization, counts, interface-gaps, implementation-plan and references rows |
| Q23–25 | Context below |
| Q26–27 | Existing concurrent-users row; Q26 qualification below |
| Q28 | Context below |
| Q29–33 | Existing source-data, conversion-owners, interface-gaps and payment/AMI rows |
| Q34 | Context below |
| Q35–36 | Existing optional-pricing and report-gaps rows |
| Q37 | Context below |
| Q38 | Existing price-horizon row and qualification below |

### Additional context and qualifications

| Coordinate | Compact source implication |
| --- | --- |
| Q5 | Two-year budgeting keeps separate fiscal-year appropriations. |
| Q6 | No vendor demos preceded the RFP. |
| Q8 | License-type count remains pending implementation. |
| Q10 | GoGov handles citizen requests; no dedicated work-order/asset system. |
| Q11 | Public Works has 12 field workers. |
| Q16 | Core administrative license estimate: 13. |
| Q23–25 | Priorities include usability, complete conversion, less manual work and comprehensive finance, purchasing, licensing, utility, HR/payroll and treasury functions. |
| Q28 | About 3,450 active utility accounts; service breakdown remains pending. |
| Q34 | SSO is preferred, with platforms, implementation needs and costs disclosed. Internal-network MFA is not anticipated; remote MFA remains conditional. |
| Q37 | Applicable governmental requirements need vendor-maintained updates. |
| Q17 | NewVision GFS 8.23 is named while version/hosting confirmation remains outstanding. |
| Q26 | The 13-user table distinguishes departments, roles and access types. |
| Q38 | User/account counts are expected to remain relatively stable. |

## Apply this to the existing acceptance packet

The engine's ten fixed mandatory UAT IDs are the minimum for the specialist evidence contract. They do not establish the full ERP's functional coverage. In particular, a passing GL or payroll evidence row cannot by itself establish budgeting behavior, business-license configuration, purchasing workflows, usability, training or regulatory maintenance.

For a separately authorized implementation, the prime and City must supply the applicable functional inventory and acceptance evidence. Treat fiscal-year budget separation, license-type configuration, department/role distinctions and unresolved service breakdowns as explicit planning inputs. Their presence in this note does not populate a packet, establish a configuration, or make an unknown input pass.

The Q34 statement is a source preference and qualification, not an implemented security policy or a result of the evidence engine. Q37 likewise requires a product/implementation response; the engine does not perform a legal-compliance certification.

## Remaining source boundary

Only the Q&A's extracted-text coverage is completed here. The original 26-page RFP scan has no usable text or page-image read in this review. BidNet's parallel distribution also remains uninspected. Consequently, the full functional requirement universe, RFP/Q&A reconciliation and visual source coverage remain incomplete.

The retained [source ledger](SOURCE_LEDGER.json) and [compiled generation](captures/20261003/new-generation.json) keep their existing incomplete-source state. This note does not refresh their observation time, extend a receipt, change a source pin or claim an engine run. The [City index](https://cityofexeter.ca.gov/bid-opportunities-and-requests-for-proposals/) still lists the October 2 proposal deadline; the package remains for internal disposition or separately authorized implementation work.

Lineage remains [#15896](https://github.com/woahwhattheheck/commons/issues/15896), [#15927](https://github.com/woahwhattheheck/commons/pull/15927) and [#30973](https://github.com/woahwhattheheck/commons/pull/30973). The existing source, recovery and commercial owners remain in place. Commercial state remains `PROPOSED_NOT_ACCEPTED`; the workshare terms remain as recorded in [WORKSHARE.md](WORKSHARE.md).
