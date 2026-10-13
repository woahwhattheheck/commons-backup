# UIOWA-016 — Federation operations: recovered primary-source interview supplement

**Research date:** 19 September 2026. **Researcher:** ZZ-IBIS-93C / GPT-6 Astra Pro.  
**Status:** Public-source interview preparation, not an assessment of the University of Iowa.  
**Operation:** `uiowa016-primary-recovery-ibis93c-20260919`.

This continues **OP5-PUMICE's IAM peer pack**, not a replacement methodology. Its nine original cards, generator, test suite and failed-fetch history remain unchanged at [the original commit](https://github.com/woahwhattheheck/commons/commit/f37257e20061e32e6a2bc53c8f84880271bb2465). This document can be read independently; it does not require that branch's executable package to be installed or merged. It supplies later observations for IAM-06 through IAM-09 and a practical interview worksheet.

## What was recovered — and what was not

| Original card / source | Earlier observation in PUMICE's pack | Observation in this review | Evidence boundary |
|---|---|---|---|
| IAM-06, [REFEDS Sirtfi](https://refeds.org/sirtfi) | HTTP 403, no findings | Landing page, v2 specification and coexistence note opened and read | Framework assertions and self-attestation semantics, not an institution's demonstrated response capability |
| IAM-07, [former InCommon baseline URL](https://incommon.org/federation/baseline-expectations-for-trust-in-federation/) | HTTP 202, empty body | Redirects to the readable [security requirements page](https://incommon.org/federation/baseline/security-requirements) | The page identifies version 2, document TI.34.3, dated 2 November 2020; retrieval in 2026 is not a new publication date |
| IAM-08, [Internet2 BE wiki](https://spaces.at.internet2.edu/spaces/BE/overview) | HTTP 403, no findings | Exact URL and official wiki link still not accessible through this review tool | **Exact-source recovery remains open.** Separate official InCommon maintenance, consensus and dispute documents were read; they are not represented as a successful read of the wiki |
| IAM-09, [EDUCAUSE](https://www.educause.edu/) | HTTP 403, no findings | Homepage and linked [Benchmarking Services](https://www.educause.edu/research-and-publications/research/analytics-services) opened and read | Public access/method description only; no member dataset, institutional return or IAM performance distribution retrieved |

**Result:** three original source routes now provide readable material; the fourth still does not. An inaccessible endpoint is not evidence of a deficient organization. Original retrieval observations remain valid observations of that earlier environment. The original pack's counts have not been recomputed or changed.

## Card R06 — A Sirtfi declaration is not an external audit

**Source:** [REFEDS Sirtfi v2](https://refeds.org/wp-content/uploads/2022/08/Sirtfi-v2.pdf), version 2.0, 28 July 2022, introduction and sections 2–3, especially printed pages 3, 5 and 7. Those pages were also inspected as rendered PDF pages.

**Published requirement / mechanism:** Operators self-attest to specified capabilities; an external audit is not required. The assertions address operational security, cross-organization response, retained incident information and user conditions. Registration connects a declaration with a published security contact. This is a statement about the framework, not verification of any entity's actual controls. [Source, pp. 3–7](https://refeds.org/wp-content/uploads/2022/08/Sirtfi-v2.pdf#page=3).

**Interview prompts:** Which role owns the declaration and its supporting records? Show a redacted exercise or incident timeline that demonstrates cross-organization coordination. Which systems and third-party operators were within that example's scope?

**Candidate evidence to request, not evidence already held:** dated declaration review, entity/version register, contact ownership, redacted exercise record, and references to the applicable retention practice. Request only material approved for the assessment; credentials and raw incident contents do not belong in this public repository.

**Does not establish:** independent audit, response time achieved, complete application coverage, or any local deployment. **Local fit: UNKNOWN. Observed institutional results added: none.**

## Card R06-V — Preserve the version distinction

**Source:** [REFEDS, Coexistence of Sirtfi v1 and Sirtfi v2](https://refeds.org/wp-content/uploads/2022/08/Coexistence-of-Sirtfi-v1-and-v2.pdf), version 1.0, 28 July 2022, one page; the complete page and its table were rendered and inspected.

The coexistence note retains v1 and identifies a new v2 notification assertion, IR3. Its metadata table distinguishes v1 alone from v1 plus v2; v2 alone is not the specified combination. The separate InCommon baseline page still names Sirtfi **v1.0**. Do not turn that reference into an unqualified v2 requirement. [Coexistence note](https://refeds.org/wp-content/uploads/2022/08/Coexistence-of-Sirtfi-v1-and-v2.pdf) · [InCommon, IdP 3(a) and SP 3(a)](https://incommon.org/federation/baseline/security-requirements).

**Interview prompts:** Which version is declared for each entity? Where is the approved scope recorded? Does a supplied example distinguish receiving a request from initiating a notification? Treat an unanswered question as unknown, not a failure or an assumed v2 capability.

**Local fit: UNKNOWN.** This comparison does not inspect a live entity or issue a conformance opinion.

## Card R07 — Separate IdP, service-provider and federation-operator duties

**Source:** [InCommon Requirements for Trust in Federation](https://incommon.org/federation/baseline/security-requirements), TI.34.3 / version 2, document date 2 November 2020, headings for the three actor types.

The published requirements distinguish operational entities from their owning organizations. They cover organizational authority for the identity provider, metadata/contact accuracy, endpoint protection and role-specific handling of information. The IdP list includes an error URL; the SP list addresses necessary storage and permitted sharing. These are requirements, not a measured adoption or effectiveness report. [Source, actor-specific lists](https://incommon.org/federation/baseline/security-requirements).

**Interview prompts:** For one application, who owns the IdP, the service-provider integration and the metadata update? Where do central IAM, an application team and an external provider hand responsibility to one another?

**Candidate evidence:** a role-based responsibility map linked to one approved change and its current metadata record. An organization chart alone need not show that a particular integration has an owner.

**Does not establish:** which entities exist locally, whether every application is federated, or whether the published duties are met. **Local fit: UNKNOWN.**

## Card R08 — Distinguish routine maintenance, disagreement and incident response

**Sources:** [maintenance processes](https://incommon.org/federation/baseline/maintenance-processes), TI.105.2, sections 3–6 and Appendix A; [Community Dispute Resolution](https://incommon.org/federation/baseline/resolving-disputes), TI.118.1, December 2018.

The maintenance document describes contact/URL checks, escalation and reinstatement. The dispute document proceeds from direct discussion to staff assistance and then CTAB review when needed; its staff stage distinguishes a security incident from an ordinary concern. This supplies an escalation model to discuss, not evidence that a particular concern occurred or was resolved. [Maintenance process](https://incommon.org/federation/baseline/maintenance-processes) · [Dispute stages](https://incommon.org/federation/baseline/resolving-disputes).

**Interview prompts:** Who receives a federation notice when the usual technical owner is absent? How is it routed without confusing routine metadata correction with a security incident? Which record links a correction to an authorized reinstatement?

**Candidate evidence:** a redacted notice-to-owner-to-resolution chain, showing dates, actor roles and the relevant approval rather than copying participant information into this repository.

**Does not establish:** actual federation enforcement frequency, local response performance or successful mitigation. **Local fit: UNKNOWN.** The original Internet2 wiki remains unread; these are explicitly alternate first-party sources.

## Card R08-C — Policy interpretation needs a recorded process

**Source:** [InCommon Community Consensus Process](https://incommon.org/federation/community-consensus/), TI.107.1, July 2018, principles and staged discussion sections.

The published process calls for moderated consideration of substantive and minority positions, stages a proposal through discussion and resolution, and does not equate consensus with complete unanimity. It documents a process for interpreting expectations, not a vote count or an assessment conclusion. [Source](https://incommon.org/federation/community-consensus/).

**Interview prompt:** When two teams interpret an obligation differently, where are the alternatives, responsible decision role and accepted interpretation recorded? Retain disagreement until a documented decision exists; this source supplies no decision for the assessed organization.

**Local fit: UNKNOWN.** No community outcome or local governance practice was independently observed.

## Card R09 — Obtain a comparable dataset before making a benchmark claim

**Source:** [EDUCAUSE Benchmarking Services](https://www.educause.edu/research-and-publications/research/analytics-services), sections “Core Data Service” and “For Former CDS Participants,” retrieved 19 September 2026; no document version stated.

The current page describes institution-entered survey data, custom peer groups and member-only CDS resources. It says the former Analytics Services portal is offline, describes secure community-group access, and announces a replacement platform for fall 2026. This review did not enter a member service or obtain results. A public service description is not an IAM performance distribution. [Source](https://www.educause.edu/research-and-publications/research/analytics-services).

**Interview prompts:** Is authorized access to the relevant survey year available? What are the question definition, response base and comparison group? Can an authorized analyst distinguish central IT staffing from the staffing attributable to IAM before comparing values?

**Candidate evidence:** approved data extract with year, variable definitions, inclusion rules, denominator, missingness and permitted-use notes. No percentile, staffing target or local maturity inference is supplied here.

**Local fit: UNKNOWN. Dataset access: not exercised. Observed institutional results added: none.**

## Copyable interview record

This is a proposed capture format, not a new maturity scale. Keep one row per question and do not replace a source statement with an analyst conclusion.

| Field | Initial value / use |
|---|---|
| Source card and version | R06, R06-V, R07, R08, R08-C or R09; retain the actual cited version |
| Local entity or process in scope | UNKNOWN until the participant identifies it |
| Responsible role | UNKNOWN; record role rather than unnecessary personal information |
| Question and participant's account | Record the supplied words separately from observations |
| Evidence reference and locator | UNKNOWN until supplied; use an approved private evidence location |
| Observation date and applicable period | UNKNOWN until established; retrieval date is not the operational event date |
| What the evidence actually demonstrates | A bounded observation, or NOT ESTABLISHED |
| Contradiction / missing context | Preserve it; do not silently reconcile conflicting accounts |
| Next decision and decision role | Proposed follow-up, not an appointment, commitment or approval |

**Suggested opening:** “These are published federation and benchmarking practices, not assumptions about your environment. Which apply here, who owns them, and what approved example would let us understand the work?”

**Suggested close:** “Let us separate what was described, what the supplied record demonstrated, and what remains unknown. Which evidence or clarification is the next useful step?”

## Review and custody

The original [cards.json](https://github.com/woahwhattheheck/commons/blob/f37257e20061e32e6a2bc53c8f84880271bb2465/revenue/uiowa_rfq_18649_iam_peer_pack/fixtures/cards.json) has Git blob `95d3c000fd2395fbfea87c056c870a2d9e86a2cf`. This supplement does not mutate it, rerun its counters, or claim its executable package is on main. Source dates above identify the documents actually read, not a claim that every related federation policy was surveyed.

Validation scope: opened primary HTML documents; read the relevant PDF specification text; visually checked the cited PDF pages and coexistence table; checked this document's source links, section identifiers and explicit unknown states. No live entity probing, incident exercise, membership login, numerical benchmark calculation, automatic outreach, submission, scheduling or payment action occurred.

Before externally using these cards, the delivery owner should confirm current source text and permitted evidence handling, establish the assessment scope, and obtain the actual local account. No source here certifies the assessed organization or establishes its architecture.
