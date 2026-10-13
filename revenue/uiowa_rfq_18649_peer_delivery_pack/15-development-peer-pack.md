# 15 — Higher-education software delivery peer pack

Solicitation 18649, work order UIOWA-015. Practice cards drawn from
**official, published** peer-university sources, each cited to a URL and a
retrieval date.

**Nothing in this pack is a statement about the University of Iowa.** No peer
is ranked, scored, or described as a leader; the cards record what these
organizations publish, not how well they do it.

> Original collection: OP5-KELVIN, 2026-09-19. Source-context integration: ZZ-TRACEFORGE, GPT-6 Astra Pro, 2026-09-19. The UC PDF was text-read and visually checked; Northeastern rechecks returned HTTP 502, so its prior draft-source observation remains explicitly attributed, not freshly verified. These are peer policy reference cards, not University of Iowa findings or proof of implementation.

## The distinction this pack turns on

A policy document states what is **required**. It is not evidence that
anything is **done**. Every card below records which of the two its source
is. The tool preserves that classification; it does not independently verify the source or interpret arbitrary claims.

| | |
| --- | ---: |
| Sources checked | 6 |
| Sources carrying cards | 5 |
| Practice cards | 13 |
| Cards from PUBLISHED_POLICY | 13 |

**No card in this pack rests on reported implementation.** The selected policy
clauses describe expectations, not observed performance. Uncollected evidence
remains unknown; this is not an exhaustive search of institutional practice.

## Something worth noticing across the published wording

Of the 13 cards, 1 state the practice as **advisory** (`should`,
`encouraged`) rather than mandatory, and one peer publishes an explicit
fallback for when peer review is not feasible. A pack that reported these as
requirements would overstate what peers actually commit to. The tooling
refuses universal labels when structured scope cases are present. CONDITIONAL
cards carry the source's classification or applicability limits; isolated wording
does not override the document context. DRAFT_INTENT remains separate from adoption.

## Practice cards

### PC-001 — code_review (Dakota State University)

| Field | Value |
| --- | --- |
| Organization | Dakota State University |
| Document | Software Development Lifecycle (Policy 14.10) |
| Owning unit | Information Technology Services |
| Document date | originally issued 2026-02-07; adopted 2026-02-09 (separate fields on the page) |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **ADVISORY** (on the wording "are encouraged") |
| Source | https://dsu.edu/policy/software-development-lifecycle.html |
| Retrieved | 2026-09-19 |
| Interpretation state | **ADVISORY** |
| Source locator | Policy 14.10, III.6.5.9 |
| Applicability | DSU development within the policy scope; preserve its tailoring and approved-exception context. TDX is DSU-specific, not an Iowa tool requirement. |
| Source scope | DSU ITS development and coordinated departmental development. Section III.6 permits lifecycle tailoring; approved exceptions follow the policy process. Tool names are local examples, not purchasing recommendations. |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> Peer code reviews are encouraged for significant changes. If it is not feasible based on the skillsets available within the team, development managers can approve based on documentation review.

**What it says.** Peer review is encouraged rather than required, and an explicit documented fallback exists when the team lacks a second qualified reviewer.

**Why it transfers.** A multiple-application organization will have teams too small for independent review of some work. This card shows one peer's published handling of that: a named fallback with an approver, rather than silence.

**Transferable assessment questions**

- For a change nobody else on the team can review, what happens? Is there a written fallback, or does it go out unreviewed?
- Who approves in that case, by role, and is the approval recorded anywhere?
- Can you show me a recent change that took the fallback path?

### PC-002 — change_control (Dakota State University)

| Field | Value |
| --- | --- |
| Organization | Dakota State University |
| Document | Software Development Lifecycle (Policy 14.10) |
| Owning unit | Information Technology Services |
| Document date | originally issued 2026-02-07; adopted 2026-02-09 (separate fields on the page) |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **MANDATORY** (on the wording "is required") |
| Source | https://dsu.edu/policy/software-development-lifecycle.html |
| Retrieved | 2026-09-19 |
| Interpretation state | **MANDATORY** |
| Source locator | Policy 14.10, III.6.7.1 |
| Applicability | DSU development within the policy scope; preserve its tailoring and approved-exception context. TDX is DSU-specific, not an Iowa tool requirement. |
| Source scope | DSU ITS development and coordinated departmental development. Section III.6 permits lifecycle tailoring; approved exceptions follow the policy process. Tool names are local examples, not purchasing recommendations. |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> An approved TDX Change request is required for any production deployment. That request shall include a description of the change, UAT results, the deployment plan, rollback procedures, and the scheduled change window.

**What it says.** A production deployment requires an approved change request carrying five named contents, including acceptance results and a rollback procedure.

**Why it transfers.** The list of required contents is the useful part: it is a concrete checklist an assessment can compare a real change record against, rather than asking whether change control 'exists'.

**Transferable assessment questions**

- Pull the last production deployment record. Which of these five does it actually contain: change description, acceptance results, deployment plan, rollback procedure, change window?
- Is a rollback procedure recorded for changes that cannot be rolled back, and what is written there instead?
- Are emergency deployments held to the same record, or a different one?

### PC-003 — testing (Dakota State University)

| Field | Value |
| --- | --- |
| Organization | Dakota State University |
| Document | Software Development Lifecycle (Policy 14.10) |
| Owning unit | Information Technology Services |
| Document date | originally issued 2026-02-07; adopted 2026-02-09 (separate fields on the page) |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **MANDATORY** (on the wording "No code will be moved to production without") |
| Source | https://dsu.edu/policy/software-development-lifecycle.html |
| Retrieved | 2026-09-19 |
| Interpretation state | **MANDATORY** |
| Source locator | Policy 14.10, III.6.6.6 |
| Applicability | DSU development within the policy scope; preserve its tailoring and approved-exception context. TDX is DSU-specific, not an Iowa tool requirement. |
| Source scope | DSU ITS development and coordinated departmental development. Section III.6 permits lifecycle tailoring; approved exceptions follow the policy process. Tool names are local examples, not purchasing recommendations. |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> No code will be moved to production without UAT approvals stored in TDX tickets or projects.

**What it says.** User acceptance approval is a precondition for production, and it must be stored in a named system.

**Why it transfers.** It names where the approval lives. An assessment can ask for the locator rather than accepting that acceptance 'happens'.

**Transferable assessment questions**

- Where is user acceptance recorded, and can you open one for a recent change?
- Who gives that approval, by role?
- Are maintenance changes held to the same rule as project work?

### PC-004 — testing (University of Kansas)

| Field | Value |
| --- | --- |
| Organization | University of Kansas |
| Document | Systems Development Life Cycle (SDLC) Standard |
| Owning unit | University of Kansas Information Technology |
| Document date | effective 2009-12-01; last updated 2025-10-09 |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **CONDITIONAL** (on the wording "should conduct") |
| Source | https://services.ku.edu/TDClient/818/Portal/KB/Article/21410/Systems-Development-Life-Cycle-SDLC-Standard |
| Retrieved | 2026-09-19 |
| Interpretation state | **CONDITIONAL** |
| Source locator | Statement of Policy, global subtask rule + Testing Phase, independent QA subtask |
| Applicability | The isolated should wording is subject to the preceding Level 1 data rule. |
| Source scope | Applies to development for KU. Global phase-subtask rule makes the listed subtasks mandatory for Level 1 data and otherwise recommended. The required phases and exemption process are separate from individual subtask wording. |
| Scope case | KU Level 1 data involved: **MANDATORY** |
| Scope case | Otherwise, within required SDLC phases: **ADVISORY** |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> Representatives separate from the development group should conduct internal Quality Assurance (QA) testing

**What it says.** Independent QA is a scoped expectation; the global subtask rule changes its force for Level 1 data.

**Why it transfers.** Ask which classifications and project conditions affect the practice; do not transplant KU classifications or apply an isolated sentence universally.

**Transferable assessment questions**

- Take the last change that shipped: who wrote it, and who tested it? Can you show me where that is recorded?
- Who tests a change before it ships, and are they the same people who wrote it?
- If testing is done by the author, is that recorded as such anywhere?
- Does independence differ between applications, and what drives that?
- For that example, which data classification and documented exception, if any, determined the expectation?

### PC-005 — documentation (University of Kansas)

| Field | Value |
| --- | --- |
| Organization | University of Kansas |
| Document | Systems Development Life Cycle (SDLC) Standard |
| Owning unit | University of Kansas Information Technology |
| Document date | effective 2009-12-01; last updated 2025-10-09 |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **CONDITIONAL** (on the wording "should detail") |
| Source | https://services.ku.edu/TDClient/818/Portal/KB/Article/21410/Systems-Development-Life-Cycle-SDLC-Standard |
| Retrieved | 2026-09-19 |
| Interpretation state | **CONDITIONAL** |
| Source locator | Statement of Policy, global subtask rule + Testing Phase, requirements-linked test documentation subtask |
| Applicability | The isolated should wording is subject to the preceding Level 1 data rule. |
| Source scope | Applies to development for KU. Global phase-subtask rule makes the listed subtasks mandatory for Level 1 data and otherwise recommended. The required phases and exemption process are separate from individual subtask wording. |
| Scope case | KU Level 1 data involved: **MANDATORY** |
| Scope case | Otherwise, within required SDLC phases: **ADVISORY** |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> Documentation during testing should detail and match testing criteria to specific requirements.

**What it says.** Requirement-to-test documentation has different force under the global Level 1 data rule.

**Why it transfers.** Ask which classifications and project conditions affect the practice; do not transplant KU classifications or apply an isolated sentence universally.

**Transferable assessment questions**

- For a recent change, can you show which test covers which stated requirement?
- If a requirement changed mid-delivery, was the test updated, and how would you know?
- Is that link recorded anywhere, or reconstructed from memory?
- For that example, which data classification and documented exception, if any, determined the expectation?

### PC-006 — code_review (University of Minnesota)

| Field | Value |
| --- | --- |
| Organization | University of Minnesota |
| Document | Software Development Standard (appendix to the information security policy) |
| Owning unit | Office of Institutional Compliance |
| Document date | published July 2019 |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **CONDITIONAL** (on the wording "Document the peer review") |
| Source | https://policy.umn.edu/it/securedata-appsd |
| Retrieved | 2026-09-19 |
| Interpretation state | **CONDITIONAL** |
| Source locator | Software Development Standard, SD.B.06, High/Medium/Low columns |
| Applicability | Use the table columns and locally established classification; no general claim about non-overridable exceptions. |
| Source scope | Read each SD.x.nn row with its High/Medium/Low columns. A row label alone does not establish a universal requirement; classification and other applicable requirements must be resolved locally. |
| Scope case | High: **MANDATORY** |
| Scope case | Medium: **ADVISORY** |
| Scope case | Low (Optional in source): **UNKNOWN** |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> Document the peer review of the design and the approval to move to the next phase

**What it says.** Design-review recording is Required for High, Recommended for Medium and Optional for Low.

**Why it transfers.** It separates 'a review happened' from 'the review and its outcome are recorded'. An assessment can ask for the record.

**Transferable assessment questions**

- Where is a design review recorded, and can you open a recent one?
- Does the record show the decision to proceed, or only that a meeting occurred?
- Which changes are large enough to get a design review at all?
- Can you show how the system classification and any applicable exception were determined for that record?

### PC-007 — environments (University of Minnesota)

| Field | Value |
| --- | --- |
| Organization | University of Minnesota |
| Document | Software Development Standard (appendix to the information security policy) |
| Owning unit | Office of Institutional Compliance |
| Document date | published July 2019 |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **CONDITIONAL** (on the wording "Prevent") |
| Source | https://policy.umn.edu/it/securedata-appsd |
| Retrieved | 2026-09-19 |
| Interpretation state | **CONDITIONAL** |
| Source locator | Software Development Standard, SD.C.02, High/Medium/Low columns |
| Applicability | Use the table columns and locally established classification; no general claim about non-overridable exceptions. |
| Source scope | Read each SD.x.nn row with its High/Medium/Low columns. A row label alone does not establish a universal requirement; classification and other applicable requirements must be resolved locally. |
| Scope case | High: **MANDATORY** |
| Scope case | Medium: **MANDATORY** |
| Scope case | Low: **ADVISORY** |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> Prevent private-highly restricted and/or private-restricted data from appearing in non-production environments unless the environment meets the same requirements as the production environment

**What it says.** The equivalent-controls condition for restricted data is Required for High/Medium and Recommended for Low.

**Why it transfers.** It states the condition under which the rule bends, which is the part an assessment can actually check.

**Transferable assessment questions**

- What data is in your test environments today, and how do you know?
- If production data is used for testing, what makes that environment equivalent?
- Who decides, by role, and is that decision recorded?
- Can you show how the system classification and any applicable exception were determined for that record?

### PC-008 — testing (University of Minnesota)

| Field | Value |
| --- | --- |
| Organization | University of Minnesota |
| Document | Software Development Standard (appendix to the information security policy) |
| Owning unit | Office of Institutional Compliance |
| Document date | published July 2019 |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **CONDITIONAL** (on the wording "Prohibit deployment") |
| Source | https://policy.umn.edu/it/securedata-appsd |
| Retrieved | 2026-09-19 |
| Interpretation state | **CONDITIONAL** |
| Source locator | Software Development Standard, SD.E.03, High/Medium/Low columns |
| Applicability | Use the table columns and locally established classification; no general claim about non-overridable exceptions. |
| Source scope | Read each SD.x.nn row with its High/Medium/Low columns. A row label alone does not establish a universal requirement; classification and other applicable requirements must be resolved locally. |
| Scope case | High: **MANDATORY** |
| Scope case | Medium: **MANDATORY** |
| Scope case | Low: **ADVISORY** |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> Prohibit deployment when software does not pass security requirements in the testing phase

**What it says.** The deployment prohibition is Required for High/Medium and Recommended for Low. This row alone does not establish that exceptions cannot exist.

**Why it transfers.** Distinguish the stated expectation, applicable classification, decision record and actual enforcement; ask rather than assume whether an exception process applies.

**Transferable assessment questions**

- Has a deployment ever gone ahead with a known failing security requirement? What happened?
- Who can waive that, by role, and where is a waiver recorded?
- Is the gate enforced by a person or by the pipeline?
- Can you show how the system classification and any applicable exception were determined for that record?

### PC-009 — documentation (Northeastern University)

| Field | Value |
| --- | --- |
| Organization | Northeastern University |
| Document | Systems and Software Development Life Cycle Standard |
| Owning unit | Office of Information Security |
| Document date | Initial Draft version 0.1, dated 2025-10-16 |
| Document status | **DRAFT** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **MANDATORY** (on the wording "must be developed and updated") |
| Source | https://security.its.northeastern.edu/systems-and-software-development-life-cycle-standard/ |
| Retrieved | 2026-09-19 |
| Interpretation state | **DRAFT_INTENT** |
| Source locator | SDLC standard, documentation requirement (original extraction) |
| Applicability | Draft intent only; current content not reverified because the official endpoint returned HTTP 502. |
| Source scope | Intended requirements in the originally retrieved draft, not evidence of an adopted current obligation. Re-open the official source before external reliance. |
| Recheck | 2026-09-19; FETCH_UNAVAILABLE; Two direct rechecks returned HTTP 502. Retain OP5-KELVIN original retrieval and DRAFT status; current source content and supersession were not independently resolved. |

> Documentation, to include security considerations, must be developed and updated during all phases from Initiation through Maintenance.

**What it says.** Documentation is a continuing obligation across the whole lifecycle, including maintenance, not a delivery artifact.

**Why it transfers.** Most documentation questions stop at delivery. The maintenance clause is the one that separates current documentation from documentation that was accurate once.

**Transferable assessment questions**

- When was the documentation for a given application last updated, and what triggered it?
- Does a maintenance change update the documentation, and can you show one that did?
- Who would notice if it went stale?

*This document identifies itself as a draft. It shows an intended
requirement, not a settled one.*

### PC-010 — environments (Northeastern University)

| Field | Value |
| --- | --- |
| Organization | Northeastern University |
| Document | Systems and Software Development Life Cycle Standard |
| Owning unit | Office of Information Security |
| Document date | Initial Draft version 0.1, dated 2025-10-16 |
| Document status | **DRAFT** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **MANDATORY** (on the wording "must be removed") |
| Source | https://security.its.northeastern.edu/systems-and-software-development-life-cycle-standard/ |
| Retrieved | 2026-09-19 |
| Interpretation state | **DRAFT_INTENT** |
| Source locator | SDLC standard, production transition requirement (original extraction) |
| Applicability | Draft intent only; current content not reverified because the official endpoint returned HTTP 502. |
| Source scope | Intended requirements in the originally retrieved draft, not evidence of an adopted current obligation. Re-open the official source before external reliance. |
| Recheck | 2026-09-19; FETCH_UNAVAILABLE; Two direct rechecks returned HTTP 502. Retain OP5-KELVIN original retrieval and DRAFT status; current source content and supersession were not independently resolved. |

> All tools, code, or access mechanisms used for development or testing of the system or software must be removed from the software that is being moved into a production environment.

**What it says.** Development and testing affordances must not travel into production with the code.

**Why it transfers.** Ask for concrete production-transition evidence. Similar themes in other sources are context, not independent proof of the same implemented practice.

**Transferable assessment questions**

- How do you know a test account or debug path did not ship with the last release?
- Is that checked by a person, by a tool, or not at all?
- Has one ever been found in production, and how?

*This document identifies itself as a draft. It shows an intended
requirement, not a settled one.*

### PC-011 — security_testing (University of California (systemwide))

| Field | Value |
| --- | --- |
| Organization | University of California (systemwide) |
| Document | Secure Software Development Standard |
| Owning unit | UCOP ITS Systemwide CISO Office |
| Document date | ITLC approval 2019-10-03 in revision history; running footer last updated 2019-08-21 |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **CONDITIONAL** (on the wording "Perform") |
| Source | https://security.ucop.edu/files/documents/policies/secure-software-development-standard.pdf |
| Retrieved | 2026-09-19 |
| Interpretation state | **CONDITIONAL** |
| Source locator | UC Secure Software Development Standard, section 4.1, printed page 5 |
| Applicability | Section 2 scope plus Protection Level 3+ or Availability Level 3+. |
| Source scope | Section 2: new UC network-accessible production software in the listed business, contractual, privacy or regulatory circumstances; qualified research/student exclusions. Existing PL3+ systems enter scope on high-risk assessment or substantive upgrade. Cards below retain their additional PL3+/AL3+ thresholds. |
| Scope case | In scope and PL3+ or AL3+: **MANDATORY** |
| Scope case | Outside that threshold: **UNKNOWN** |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> Perform code reviews to reduce cyber risk.

**What it says.** The scoped code-review requirements include security expertise and automated analysis.

**Why it transfers.** Use as an interview prompt, not an Iowa obligation or evidence that a peer implements the practice.

**Transferable assessment questions**

- Can you show the last applicable review record, its reviewers and the checks actually performed?
- Where does the record show disposition of issues and the criteria used to select this review depth?

### PC-012 — documentation (University of California (systemwide))

| Field | Value |
| --- | --- |
| Organization | University of California (systemwide) |
| Document | Secure Software Development Standard |
| Owning unit | UCOP ITS Systemwide CISO Office |
| Document date | ITLC approval 2019-10-03 in revision history; running footer last updated 2019-08-21 |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **CONDITIONAL** (on the wording "must") |
| Source | https://security.ucop.edu/files/documents/policies/secure-software-development-standard.pdf |
| Retrieved | 2026-09-19 |
| Interpretation state | **CONDITIONAL** |
| Source locator | UC Secure Software Development Standard, section 4.13, printed pages 8-9 |
| Applicability | Section 2 scope plus Protection Level 3+ or Availability Level 3+. |
| Source scope | Section 2: new UC network-accessible production software in the listed business, contractual, privacy or regulatory circumstances; qualified research/student exclusions. Existing PL3+ systems enter scope on high-risk assessment or substantive upgrade. Cards below retain their additional PL3+/AL3+ thresholds. |
| Scope case | In scope and PL3+ or AL3+: **MANDATORY** |
| Scope case | Outside that threshold: **UNKNOWN** |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> must create project documentation

**What it says.** The documentation requirements cover security decisions, defects, testing and component state.

**Why it transfers.** Use as an interview prompt, not an Iowa obligation or evidence that a peer implements the practice.

**Transferable assessment questions**

- Can you show a recent project record linking a defect to its fix and verification?
- Who updates that record after maintenance, and how is current component state established?

### PC-013 — change_control (University of California (systemwide))

| Field | Value |
| --- | --- |
| Organization | University of California (systemwide) |
| Document | Secure Software Development Standard |
| Owning unit | UCOP ITS Systemwide CISO Office |
| Document date | ITLC approval 2019-10-03 in revision history; running footer last updated 2019-08-21 |
| Document status | **EFFECTIVE** |
| Source kind | **PUBLISHED_POLICY** — what this organization publishes as required or expected |
| Obligation | **CONDITIONAL** (on the wording "Use") |
| Source | https://security.ucop.edu/files/documents/policies/secure-software-development-standard.pdf |
| Retrieved | 2026-09-19 |
| Interpretation state | **CONDITIONAL** |
| Source locator | UC Secure Software Development Standard, section 4.14, printed page 9 |
| Applicability | Section 2 scope plus Protection Level 3+ or Availability Level 3+. |
| Source scope | Section 2: new UC network-accessible production software in the listed business, contractual, privacy or regulatory circumstances; qualified research/student exclusions. Existing PL3+ systems enter scope on high-risk assessment or substantive upgrade. Cards below retain their additional PL3+/AL3+ thresholds. |
| Scope case | In scope and PL3+ or AL3+: **MANDATORY** |
| Scope case | Outside that threshold: **UNKNOWN** |
| Recheck | 2026-09-19; READ; Official source text inspected for the cited clauses; this is not an implementation audit. |

> Use a software version control system or repository.

**What it says.** The scoped controls connect deployments and retrievable version labels to a repository.

**Why it transfers.** Use as an interview prompt, not an Iowa obligation or evidence that a peer implements the practice.

**Transferable assessment questions**

- Can you show the last deployed revision and retrieve its exact source version?
- What ties the test record to that revision when a deployment is rebuilt?

## Coverage

| Practice area | Cards |
| --- | --- |
| change_control | PC-002, PC-013 |
| code_review | PC-001, PC-006 |
| documentation | PC-005, PC-009, PC-012 |
| environments | PC-007, PC-010 |
| security_testing | PC-011 |
| testing | PC-003, PC-004, PC-008 |

An area with no card means no verified source was found for it in this
pass. It does not mean peers have no such practice.

## Sources checked that carry no card

| Source | Organization | Status | Why |
| --- | --- | --- | --- |
| SRC-RUTGERS-AR | Rutgers University | `VERIFIED_NO_RELEVANT_CONTENT` | No development-method practice card extracted from the inspected annual-review landing page. The linked PDF and underlying project records were not checked in this pass. Recorded as a collection limit, not as an absence of practice. |

These are recorded rather than dropped. A source that could not be read is
not the same as a source that says nothing, and neither is the same as an
organization that lacks the practice.

## Still UNKNOWN

- whether any of these published requirements is actually followed at the organization that published it — no source checked reports that these collected practices are consistently followed
- how lifecycle tailoring works in practice; DSU publishes a tailoring provision, but operating examples were not obtained
- whether the peers selected here are comparable in size, funding or application portfolio to a multiple-application central IT organization; no such comparison was made
- what the University of Iowa's own published expectations are — not collected, and deliberately not inferred from any peer

## How this pack was built

Original collection by OP5-KELVIN; source-context integration by ZZ-TRACEFORGE.
See original_observation and recheck fields for what each pass actually read.
Recheck current source wording and applicability before external reliance. `sources.json` and
`cards.json` are the data; `peerpack.py --check` enforces the citation rules
and this document is generated, not hand-written.
