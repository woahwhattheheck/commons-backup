# UIOWA-020 — Primary framework crosswalk adaptation memo

**Prepared:** 2026-09-19  
**Scope:** University of Iowa RFQ 18649 preparation asset  
**Status:** Proposed analyst method; not a University finding, certification, compliance opinion, or maturity determination

## Purpose

This package maps selected concepts from current primary NIST publications to the RFQ's four assessment areas:

1. software development;
2. security;
3. deployment and operations; and
4. AI readiness.

The companion `20-framework-crosswalk.csv` is intentionally structured to keep three things separate:

- **source concept** — what the cited NIST publication actually describes;
- **proposed assessment use** — how an assessor could use that concept to frame discovery, evidence requests, or analysis; and
- **adaptation limit** — what the source does **not** establish and what the engagement must not infer from the mapping.

This distinction is essential. A useful crosswalk is a research and assessment aid; it is not evidence that a practice exists at the University, not a NIST endorsement of the engagement method, and not an empirical maturity benchmark.

## Source set and version treatment

### NIST SSDF

The secure-development baseline is **NIST SP 800-218, SSDF Version 1.1**, final February 2022:

https://csrc.nist.gov/pubs/sp/800/218/final

SSDF presents high-level secure software development practices that can be integrated into an organization's SDLC. The crosswalk uses exact practice/task identifiers such as `PO.1`, `PO.3.3`, `PO.4.1`, `PW.2.1`, and `PW.6.1-PW.6.2` so later assessment notes can point back to the source without claiming that NIST supplied a local maturity score.

A revision, **SP 800-218 Rev. 1 / SSDF Version 1.2**, was issued as an **Initial Public Draft** on December 17, 2025:

https://csrc.nist.gov/pubs/sp/800/218/r1/ipd

The draft is a horizon-scan source only in this package. It should not be treated as final NIST practice or used to score an organization. Its status should be checked again at engagement kickoff.

**NIST SP 800-218A**, final July 2024, is a community profile for generative-AI and dual-use foundation-model development:

https://csrc.nist.gov/pubs/sp/800/218/a/final

It is therefore conditional. It becomes relevant when discovery establishes that an assessed team develops or materially modifies models in its scope. It should not be generalized to ordinary third-party AI feature usage or to all software development.

### NIST Cybersecurity Framework 2.0

The cybersecurity baseline is **NIST CSF 2.0, NIST CSWP 29**, final February 2024:

https://www.nist.gov/publications/nist-cybersecurity-framework-csf-20

CSF 2.0 supplies a common taxonomy of cybersecurity outcomes. The crosswalk uses exact Core identifiers including `GV.RM`, `GV.RR`, `PR.AA`, `PR.DS`, `PR.IR`, `DE.CM`, `DE.AE`, `RS.MA`, `RS.AN`, `RS.CO`, `RS.MI`, `RC.RP`, `RC.CO`, and `ID.IM`.

The Core is non-prescriptive: it describes cybersecurity outcomes rather than mandating one implementation. This package therefore uses the CSF to organize questions and evidence, not to infer tooling, architecture, certification, or a numeric maturity score.

NIST's **SP 1347, NIST CSF 2.0: Informative References Quick-Start Guide**, final August 2026, is included as a methodology supplement:

https://www.nist.gov/publications/nist-cybersecurity-framework-20-informative-references-quick-start-guide

Its relevance here is methodological: informative references and crosswalks can make relationships between source material and CSF outcomes explicit. The existence of that NIST method does not make this TJLabs crosswalk an official NIST informative reference or an endorsed equivalence.

### NIST AI RMF 1.0

The AI-risk baseline is **NIST AI 100-1, Artificial Intelligence Risk Management Framework 1.0**, published January 2023:

https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10

The maintained NIST AIRC Core representation is:

https://airc.nist.gov/airmf-resources/airmf/5-sec-core/

The AI RMF Core is organized into **GOVERN, MAP, MEASURE, and MANAGE** functions with categories and subcategories. The crosswalk uses exact identifiers such as `GOVERN 1.5-GOVERN 1.7`, `MAP 1.1`, `MEASURE 2.1`, and `MANAGE 1.1`.

NIST currently states that AI RMF 1.0 is being updated. The present package therefore freezes its references to published 1.0 identifiers and records the revision-in-progress caveat. Before an actual assessment starts, the team should check whether a revised final framework has been published and record any deliberate version transition.

**NIST AI 600-1, Generative Artificial Intelligence Profile**, final July 2024, is also conditional:

https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence

It should be used only when discovery confirms a generative-AI use case. The RFQ's AI-readiness scope is not itself evidence that ESS, RIS, IAM, or any other University service deploys generative AI.

## How to use the crosswalk

### 1. Use a framework row to generate a probe, not a conclusion

A framework reference can justify asking a focused question or requesting a specific class of evidence. For example:

- `SSDF PO.4.1` can prompt discovery of release/security-check criteria and exception handling.
- `CSF PR.AA` can prompt identity-lifecycle, authentication, authorization, and federation questions.
- `CSF DE.CM` can prompt questions about monitoring coverage and alert routing.
- `AI RMF MEASURE 2.4` can prompt discovery of production monitoring for an in-scope AI system.

None of those references establishes what Iowa currently does. The local conclusion must come from engagement evidence.

### 2. Separate intended practice from observed practice

A policy, procedure, architecture diagram, or governance charter primarily demonstrates **design or intent**. Stronger claims about operating practice should be corroborated through appropriate evidence such as:

- sampled tickets, approvals, reviews, changes, builds, releases, or incidents;
- tool or system records;
- test/evaluation outputs;
- monitoring or trend records;
- interviews with multiple roles; and
- where appropriate, repeatable observation across a defined period.

The assessor should record evidence type, date or period, population/sample, and limitations. A framework citation must not substitute for that evidence record.

### 3. Keep maturity criteria engagement-specific and explicit

The source publications in this package provide practices, outcomes, actions, risk-management structure, and vocabulary. This package does **not** claim that they supply a validated ordinal maturity instrument for this engagement.

If the proposal or later assessment uses labels such as "initial," "managed," "defined," or numerical levels, those labels and their decision rules must be defined separately. The method should show:

- what evidence qualifies for each level;
- how conflicting evidence is handled;
- whether results describe design, implementation, consistency, measurement, or improvement;
- how assessor calibration works; and
- what uncertainty remains.

Do not rename a NIST construct into a maturity level without explaining the adaptation. In particular, do not present CSF implementation concepts or AI RMF actions as an empirical peer percentile.

### 4. Preserve service context

ESS, RIS, and IAM are different service contexts. A framework reference may be relevant across all three while producing different evidence questions.

Examples:

- `PR.AA` is directly relevant to IAM but also matters to ESS and RIS application access.
- `PW.6` may be relevant where a team controls software build processes but less directly applicable to purchased services with different responsibility boundaries.
- AI RMF rows apply only to systems and workflows that meet the engagement's defined AI population.

Applicability should therefore be recorded per assessed service rather than assumed globally.

### 5. Treat conditional profiles as conditional

Two sources in the register are deliberately marked supplemental:

- NIST AI 600-1 for generative-AI use cases; and
- NIST SP 800-218A for generative-AI and dual-use foundation-model development.

Discovery should first establish the actual technology and responsibility boundary. The presence of an AI-readiness workstream is not enough to activate every AI-specific profile.

## Suggested evidence pattern by assessment area

| Assessment area | Framework anchors | Useful evidence classes | Primary caution |
| --- | --- | --- | --- |
| Software development | SSDF PO/PW tasks | SDLC standards, backlog/acceptance criteria, reviews, tests, build records, toolchain outputs | A documented process is not proof of consistent execution |
| Security | CSF GV/PR/DE/RS/RC plus SSDF | risk decisions, access records, monitoring coverage, incidents, control exceptions, sampled system evidence | Do not turn outcome categories into a compliance certification |
| Deployment and operations | CSF PR.IR/DE/RS/RC/ID.IM plus SSDF pipeline/build tasks | deployment history, observability, incident timelines, recovery tests, post-incident actions | Metrics require period, scope, denominator, and local context |
| AI readiness | AI RMF GOVERN/MAP/MEASURE/MANAGE; conditional AI 600-1 and 800-218A | AI inventory, use-case records, governance, evaluation, production monitoring, risk treatment, disable/fallback evidence | Define the AI population before assessing it; framework actions are not a checklist |

## Interview and discovery examples

These questions are proposed engagement prompts, not NIST quotations.

### Software development

- Where are security requirements for a change recorded, and what evidence shows they were considered before release?
- Which checks can block a build or release, who can approve an exception, and where is that exception recorded?
- Show a recent design or code review in which a security-relevant issue changed the implementation.
- Which build and delivery artifacts are retained, and can they reconstruct why a particular version reached an environment?

### Security

- Who owns cybersecurity risk decisions for this service, and where are acceptance or treatment decisions recorded?
- How are identities created, changed, disabled, privileged, and periodically reviewed across the service boundary?
- Which assets and events are monitored, where are known coverage gaps recorded, and how does an alert become an incident?
- Show a recent incident from detection through mitigation and improvement, including what changed afterward.

### Deployment and operations

- What conditions must be satisfied before a release is promoted, and what evidence remains after promotion?
- Which signals establish that a service is healthy, degraded, or unavailable, and who owns those signals?
- How are rollback, restoration, and recovery procedures exercised rather than only documented?
- How are post-incident actions prioritized, assigned, and verified closed?

### AI readiness

- What AI-enabled systems or development workflows are in scope, and how is that inventory maintained?
- For one in-scope use case, what intended purpose, affected users, assumptions, limitations, and risk tolerance are documented?
- What evaluation occurs before deployment, which risks cannot currently be measured, and who reviews the results?
- What is monitored after deployment, and who can pause, override, disable, or retire the AI-enabled capability?

## What this package must not be used to claim

The crosswalk does **not** establish that:

- the University currently follows any mapped NIST practice or outcome;
- a public policy proves actual ESS, RIS, or IAM implementation;
- any service is compliant, certified, secure, mature, immature, or benchmarked at a peer percentile;
- the RFQ requires NIST certification;
- a NIST framework prescribes a product, vendor, architecture, or procurement choice;
- a conditional GenAI profile applies without evidence of a relevant use case; or
- a superseded or draft publication is a final requirement.

## Handoff rule

At the start of a real engagement, record a **version-freeze date** for every framework used. Re-check the SSDF 1.2 draft/final status and the AI RMF revision status. If a source has changed, preserve the proposal-era register and document the reason for any transition rather than silently replacing identifiers.

For every finding, keep the chain visible:

**framework reference → proposed discovery question → actual evidence → finding → recommendation**

The framework reference is the start of that chain, never the substitute for the evidence in the middle.
