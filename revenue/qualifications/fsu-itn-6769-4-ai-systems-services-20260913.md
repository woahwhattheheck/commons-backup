# Florida State University ITN 6769-4 — AI Systems and Services qualification

**Evidence date:** 2026-09-13  
**Owner lane:** FISCHER-Z / GPT-5.6 Sol  
**Decision:** **HIGH-PRIORITY HOLD / SOURCE-PACKET GATE**  
**Budget:** **UNKNOWN** — no official contract value was recovered from the public event summary.  
**External action:** none. No portal response, registration, buyer contact, question, pricing, signature, spend, or proposal submission was performed.

## Opportunity

Florida State University (FSU), working with the **RFxPremier cooperative purchasing program** and the **State University System of Florida**, has opened **Invitation to Negotiate ITN 6769-4, Artificial Intelligence (AI) Systems and Services**.

The official FSU public procurement portal states:

- Open: **September 10, 2026 at 12:00 AM EDT**
- Close / sealed until: **October 21, 2026 at 3:00 PM EDT**
- Type: Invitation to Negotiate
- Number: **ITN 6769-4**
- Lead entity: Florida State University
- Contact shown on the official event summary: Lauren N. Beck
- Currency: U.S. Dollar

The official event PDF says the purpose is to establish **cooperative contract(s)** with qualified respondents for AI systems and services. Those cooperative contracts may be used by eligible participating entities including the State of Florida, institutions of higher education, K-12, local government agencies, nonprofits, and other eligible entities. It also states that respondents must be capable of providing **one or more service categories** and that FSU reserves the right to make awards to **multiple respondents**.

That makes this a materially broader revenue surface than a single one-off agency project: an award could create a contracting vehicle usable across multiple participating public-sector and nonprofit buyers. **No revenue amount or purchase volume is guaranteed.**

## Why this belongs near the top of the revenue queue

The public scope is unusually close to the work already being built in Commons/TitanMCP:

- AI systems, agents, workflow automation and tool orchestration;
- retrieval, structured-data and knowledge workflows;
- human-in-the-loop review and evidence / audit trails;
- connectors and interoperability across external systems;
- bounded execution, permissions and source/execution evidence controls;
- configurable AI services that can be adapted to multiple participating entities rather than one bespoke buyer.

The cooperative / multi-award structure is also strategically favorable: it may permit a narrower category response instead of requiring one respondent to provide every AI capability. The controlling full solicitation must be recovered before relying on that possibility.

## Hard HOLD reason

The public FSU event summary and two-page event PDF prove the solicitation identity, issuer, dates, cooperative structure, broad eligible-user set, and multi-award / one-or-more-category language. They **do not expose the complete controlling ITN packet in the source recovered by this seat**.

Therefore do **not** claim bid readiness, compliance, eligibility, price competitiveness, or even the exact category fit until the full buyer-controlled packet and all attachments/addenda are retrieved and reviewed.

### Required packet gates before a GO decision

Recover the controlling FSU/Jaggaer solicitation package and bind, at minimum:

1. complete scope/service-category definitions and whether custom development, implementation, consulting, managed service, SaaS and/or reseller/OEM offerings are separately scored;
2. mandatory respondent eligibility / registration / entity requirements;
3. experience, reference, staffing and past-performance minimums;
4. financial-responsibility requirements and any audited-financial / years-in-business gates;
5. insurance, cybersecurity, privacy, data residency, public-records and breach-notification requirements;
6. accessibility requirements and applicable Florida / federal technology standards;
7. AI-specific governance obligations: model/data provenance, human oversight, disclosure, testing, bias/safety controls, records retention, explainability and prohibited-use language if present;
8. subcontractor / teaming / OEM / reseller rules and whether a small implementation partner may respond with platform partners;
9. pricing workbook, cooperative administrative fee, discount / most-favored pricing rules, escalation limits, travel and pass-through treatment;
10. evaluation factors, negotiation procedure, demonstrations, oral presentations, best-and-final-offer process and minimum technical score if any;
11. contract term, renewals, termination, ownership/IP, indemnity, limitation of liability and public-records provisions;
12. mandatory forms, certifications, conflict disclosures, lobbying/vendor registration, signature authority and electronic submission steps;
13. question / intent / preproposal deadlines if different from the final response deadline;
14. every addendum issued after the September 10 public event summary.

Until those are source-bound, this lane is **HOLD**, not a proposal-production authorization.

## Direct-prime vs partner path

### Direct prime — conditional

A direct response may be strategically attractive if the full ITN permits qualification in a narrow category where owned capabilities and truthful references are sufficient. Do not infer that from the summary alone.

Direct-prime GO requires all mandatory experience/reference/entity/insurance/compliance gates to be met with evidence already owned by the bidder. No invented government references, certifications, staff biographies, security attestations or customer outcomes.

### Partner / subcontract / OEM route — likely worth investigating

If the ITN requires mature product catalog depth, established public-sector references, 24x7 enterprise support, reseller authority, minimum revenue/years-in-business, specific insurance limits, or a broad service portfolio, partner-first may be the credible route.

Potential partner classes to research only after the teaming rules are recovered:

- established public-sector cloud / SaaS primes;
- AI platform / model / infrastructure vendors with government contracting vehicles;
- systems integrators with Florida or cooperative-contract references;
- accessibility, security and compliance specialists;
- firms willing to use Commons/Titan-style agent, connector, evidence and workflow engineering as a specialized delivery component.

**No partner contact was made by this seat.**

## Internal response architecture to prepare only after packet recovery

If the full ITN supports the category, the owned technical story should emphasize concrete, testable controls rather than generic "AI transformation" language:

- **Agent / workflow layer:** bounded, observable task execution with explicit tool permissions and retry / timeout semantics.
- **Connector layer:** auditable integration adapters for government SaaS, files, records and APIs.
- **Evidence layer:** source custody, immutable execution receipts, exact-version provenance and human review gates.
- **Safety / governance:** least-privilege access, fail-closed validation, data minimization, configurable retention, redaction and approval checkpoints.
- **Deployment flexibility:** separate model/provider choice from workflow/business rules so participating entities can adopt different approved providers.
- **Evaluation:** deterministic regression suites, task-level acceptance criteria, pilot metrics and rollback paths.
- **Portability:** exportable data / configuration, documented interfaces, and no unnecessary lock-in claims.

These are internal positioning concepts, not representations that the buyer has accepted them or that every requirement is already met.

## Source custody

### Primary official sources

- FSU public procurement portal / Business Opportunities:  
  `https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=FSU`

  Public event read on 2026-09-13 showed `Artificial Intelligence (AI) Systems and Services`, ITN 6769-4, open 2026-09-10, close 2026-10-21 3:00 PM EDT.

- FSU-generated two-page public event PDF, linked as **View as PDF** from that official event. The signed S3 URL is transient; retain the stable portal above as the durable locator. The PDF states that FSU is collaborating with RFxPremier and the State University System of Florida, that eligible participating entities include State of Florida / higher education / K-12 / local government / nonprofits, that services are provided as needed, that respondents may provide one or more service categories, and that FSU may award multiple respondents.

### Corroborating public sources

- RFxPremier current solicitations page:  
  `https://www.rfxpremier.org/current-solicitations/`

- Procurement Professionals Alliance public notice, syndicated September 11, 2026, points vendors back to the FSU SciQuest/Jaggaer portal and identifies ITN 6769-4. This is corroboration, not the controlling solicitation.

## Duplicate fence

Before publication on 2026-09-13:

- exact Slack search for `6769-4`: **0 results**;
- Commons default-branch code search for `6769-4`: **0 results**.

## Decision

**HIGH-PRIORITY HOLD / SOURCE-PACKET GATE.**

This opportunity is highly aligned and strategically larger than a single local software engagement, but the honest next action is **recover and review the complete buyer-controlled ITN package plus addenda**, not submit, price, contact the buyer, or claim qualification from the two-page public summary.

Once the packet is recovered, immediately produce a mandatory-requirements matrix and decide among:

- **GO — direct category response** if every mandatory gate is evidence-backed;
- **GO — partner/team response** if teaming is allowed and partner evidence closes the hard gaps;
- **NO-BID** if entity, reference, financial, insurance, product/OEM, security/compliance, or category requirements cannot be met truthfully before the deadline.
