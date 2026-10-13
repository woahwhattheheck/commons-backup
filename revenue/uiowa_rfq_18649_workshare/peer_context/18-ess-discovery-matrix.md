# UIOWA-018 — ESS discovery and evidence matrix

**Operation:** `uiowa-018-kestrel-ess18-20260919`  
**Status:** Proposed interview instrument; no University interviews conducted.  
**Companions:** [peer pack](18-ess-peer-pack.md) · [source register](18-ess-source-register.md)

## Use at preparation and discovery

Choose questions after confirming actual service boundaries and participant responsibilities. Roles below are suggestions, not named people or committed assignments. Several roles may participate in one session; do not convert rows into appointments or assume one interview per person. Ask for deidentified metadata or examples sufficient to establish the practice, not student records, credentials or unrestricted production exports.

Each source reference supplies **peer context only**. The question and requested evidence are analyst proposals. Record any local response with a new local evidence ID, exact version/locator, service and period; never overwrite a peer source entry with a local finding. A source can motivate a question without demonstrating that a peer performs the proposed practice.

## Question matrix

| ID / topic | Peer context | Question | Proposed roles | Evidence request | Interpretation limit |
|---|---|---|---|---|---|
| ESS18-Q01 / Service boundary | ESS18-S01, ESS18-S06 | Which student journey and applications are actually inside ESS, and which are inherited dependencies? | ESS service lead; functional process owner | Current service map and one deidentified end-to-end journey | A peer module list cannot establish the Iowa inventory. |
| ESS18-Q02 / Decision rights | ESS18-S02, ESS18-S03 | For a term-specific rule change, who owns the policy decision, configuration edit, code change and business verification? | Registrar or relevant functional owner; application lead | One completed change with role-specific decisions and evidence locators | A published role chart does not establish that the roles were exercised. |
| ESS18-Q03 / Shared records | ESS18-S01, ESS18-S05 | Where does the selected journey share records with another administrative service, and who reconciles changes? | Application and integration owners; data steward role | Field-level dependency description and redacted reconciliation example | Shared technology does not prove synchronized data or shared functional ownership. |
| ESS18-Q04 / Calendar provenance | ESS18-S08 | Which authoritative calendar/version and process deadlines inform this service's change planning? | Functional process owner; release coordinator | Calendar version, applicable deadline and one decision referencing it | A calendar listing alone is not a release restriction. |
| ESS18-Q05 / Change classes | ESS18-S02, ESS18-S07 | Are business configuration, software releases and infrastructure maintenance treated differently when student impact differs? | Functional administrator; development and operations leads | Two comparable changes with rationale and impact descriptions | Different paths may be appropriate; uniformity is not the required outcome. |
| ESS18-Q06 / Deferral | ESS18-S07, ESS18-S08 | When a change date moves, who rechecks business timing, consumer readiness and communications? | Change coordinator; functional and downstream owners | Original and revised plan, decision, notice and readiness check | A deferral date is a plan; ask for an executed example before concluding repeatability. |
| ESS18-Q07 / Exceptions | ESS18-S07 | How is an urgent repair handled during a locally sensitive period without importing an assumed blanket freeze? | Service and incident leads; accountable functional owner | Redacted exception rationale, decisions and verification; or an explicit no-sample response | An exception is not automatically a defect, and no sample is not proof that exceptions are uncontrolled. |
| ESS18-Q08 / Stakeholder coverage | ESS18-S03 | How are affected units represented, including disagreement and a request that was not accepted? | Functional representatives; service/product owner | One request-to-disposition record including a dissent or rejected option | A committee listing is not proof of coverage, agreement or closure. |
| ESS18-Q09 / Communication continuity | ESS18-S04 | How does time-sensitive information reach affected units when a standing forum is canceled or an attendee is absent? | Liaison or communications role; operations lead | Redacted alternate communication path and one acknowledgement or follow-up example | A canceled meeting does not by itself establish a communication failure. |
| ESS18-Q10 / Roadmap truth | ESS18-S09 | How do recipients distinguish a tentative roadmap update from a committed or completed change? | Product/service owner; communications role | A dated announcement linked to its decision and subsequent status | A presentation or agenda is not evidence that a capability shipped. |
| ESS18-Q11 / Test environment fit | ESS18-S05, ESS18-S06 | How is a representative student journey tested against relevant interface and environment versions? | Test/development lead; integration owner | Environment/version map and redacted test execution for the sampled change | An available environment or written test plan does not establish executed coverage. |
| ESS18-Q12 / Consumer impact | ESS18-S07 | Which consumers are affected when an API or background interface is unavailable even if a portal is reachable? | Integration and service owners; downstream process representative | Dependency list and business-impact check for a planned or actual interruption | Screen availability does not demonstrate whole-journey availability. |
| ESS18-Q13 / Data reconciliation | ESS18-S01, ESS18-S07 | After interruption or replay, how are missing, delayed or duplicate business updates detected and resolved? | Application/integration owners; functional verifier | Deidentified reconciliation totals, exception disposition and verification locator | Do not infer data correctness from a completed technical restart. |
| ESS18-Q14 / Recovery demonstrated | ESS18-S06, ESS18-S07 | What evidence distinguishes a written recovery plan from a demonstrated restoration of the sampled service? | Operations lead; application and functional verification roles | Plan/version plus one redacted exercise or incident execution record | Exercise and production evidence remain separate; a plan is not a completed recovery. |
| ESS18-Q15 / Timing definitions | ESS18-S07 | What do detection, restoration and business-verification times mean, and which intervals or observations are missing? | Operations/measurement owner; functional owner | Timestamp definitions, timezone, denominator/period and missing-data note | A planned duration is neither an observed duration nor a peer performance target. |
| ESS18-Q16 / Functional outcome | ESS18-S02, ESS18-S06 | Who verifies that the intended student business outcome is correct, rather than only that software is running? | Functional verifier; application owner | Deidentified transaction-result or configuration-verification example linked to the change | Technical completion alone does not establish functional acceptance. |
| ESS18-Q17 / Manual equivalence | ESS18-S03 | Where does a deliberate manual or shared-service practice achieve the required outcome, and what evidence supports it? | Practitioner; service owner | One repeatable example, exception handling and effort/context note | Automation is not a maturity score; compare outcomes and evidence. |
| ESS18-Q18 / Coverage and disagreement | ESS18-S03, ESS18-S04 | Which services, roles or periods are not represented, and what would resolve any conflicting account? | Assessment lead; relevant practitioner and functional owner | Sample coverage statement, competing locators and bounded follow-up request | Do not generalize a convenience sample or convert absent evidence into a low rating. |

## Three fictional rehearsal cases

These are invented teaching cases. They are not descriptions of Michigan, Minnesota, Berkeley or Iowa, and their identifiers must not enter a client evidence register as observations.

### SYN-ESS18-A — configuration and release are different changes

A fictional registration service has a functional request to change a seat limit for the next term. The team also plans an unrelated software deployment. The supplied packet contains an approved limit change and a successful technical deployment log, but no record that the revised limit was checked in the student journey.

**Expected reasoning:** Separate the two changes. The log supports the stated deployment event, not the correctness of the seat limit. Request the configuration version, accountable functional role and relevant result check. Do not call the entire service immature or infer that a software rollback is needed. Use Q02, Q05 and Q16.

### SYN-ESS18-B — a deferred window needs another impact check

A fictional team moves a maintenance window by one week. The original impact analysis cites a business calendar version; the revised notice has a new date but no recorded reassessment. A practitioner says reassessment happened in a call, and the record has not yet been located.

**Expected reasoning:** Retain the practitioner statement and the missing locator. Ask for the call decision or another contemporaneous record and confirm which calendar generation applied. Do not assert that the check did not happen, that the new date was unsafe, or that all academic-period changes should be prohibited. Use Q04, Q06 and Q18.

### SYN-ESS18-C — a restored portal is not a reconciled process

A fictional portal responds after a restart. The packet separately records queued integration work, but supplies neither final processing totals nor a business verification result. A recovery procedure is present; no exercise or incident execution record for this version is included.

**Expected reasoning:** Distinguish portal reachability, integration completion, data reconciliation and demonstrated recovery. Request evidence for the unobserved steps. Do not invent duplicate records, data loss, a recovery duration or a completed restore test. Use Q12–Q15.

## Disposition vocabulary for this instrument

Use `CONTEXT_ONLY` for every peer entry. For locally gathered material, describe a statement as `STATED_PRACTICE`, a written plan as `DOCUMENTED_INTENT`, and an executed sample as `OBSERVED_EXAMPLE` only when its actual source supports that label. `UNRESOLVED` retains disagreement or missing evidence. `NOT_APPLICABLE` needs a recorded local reason; it is not a substitute for an unanswered question.

These are capture labels, **not a new maturity scale**. A supported strength or gap requires synthesis under the engagement's selected assessment method. Retain the limits of the sample and any contradictory evidence with the eventual finding. A repeated, demonstrated practice can be strong without matching a peer's organizational structure or technology.

## Machine-readable interview records

This fenced JSON is an editable interchange representation of the matrix, not executable code or a compiler authority bundle. `null` means that this pack contains no Iowa observation, not a negative result. Consumer adapters must preserve that distinction and the peer-context classification.

```json
{
  "schema": "uiowa-018-discovery-context/v1",
  "classification": "PUBLIC_PEER_CONTEXT_NOT_IOWA_EVIDENCE",
  "operation": "uiowa-018-kestrel-ess18-20260919",
  "questions": [
    {
      "id": "ESS18-Q01",
      "theme": "Service boundary",
      "peer_context_sources": [
        "ESS18-S01",
        "ESS18-S06"
      ],
      "question": "Which student journey and applications are actually inside ESS, and which are inherited dependencies?",
      "proposed_roles": "ESS service lead; functional process owner",
      "evidence_request": "Current service map and one deidentified end-to-end journey",
      "interpretation_limit": "A peer module list cannot establish the Iowa inventory.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q02",
      "theme": "Decision rights",
      "peer_context_sources": [
        "ESS18-S02",
        "ESS18-S03"
      ],
      "question": "For a term-specific rule change, who owns the policy decision, configuration edit, code change and business verification?",
      "proposed_roles": "Registrar or relevant functional owner; application lead",
      "evidence_request": "One completed change with role-specific decisions and evidence locators",
      "interpretation_limit": "A published role chart does not establish that the roles were exercised.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q03",
      "theme": "Shared records",
      "peer_context_sources": [
        "ESS18-S01",
        "ESS18-S05"
      ],
      "question": "Where does the selected journey share records with another administrative service, and who reconciles changes?",
      "proposed_roles": "Application and integration owners; data steward role",
      "evidence_request": "Field-level dependency description and redacted reconciliation example",
      "interpretation_limit": "Shared technology does not prove synchronized data or shared functional ownership.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q04",
      "theme": "Calendar provenance",
      "peer_context_sources": [
        "ESS18-S08"
      ],
      "question": "Which authoritative calendar/version and process deadlines inform this service's change planning?",
      "proposed_roles": "Functional process owner; release coordinator",
      "evidence_request": "Calendar version, applicable deadline and one decision referencing it",
      "interpretation_limit": "A calendar listing alone is not a release restriction.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q05",
      "theme": "Change classes",
      "peer_context_sources": [
        "ESS18-S02",
        "ESS18-S07"
      ],
      "question": "Are business configuration, software releases and infrastructure maintenance treated differently when student impact differs?",
      "proposed_roles": "Functional administrator; development and operations leads",
      "evidence_request": "Two comparable changes with rationale and impact descriptions",
      "interpretation_limit": "Different paths may be appropriate; uniformity is not the required outcome.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q06",
      "theme": "Deferral",
      "peer_context_sources": [
        "ESS18-S07",
        "ESS18-S08"
      ],
      "question": "When a change date moves, who rechecks business timing, consumer readiness and communications?",
      "proposed_roles": "Change coordinator; functional and downstream owners",
      "evidence_request": "Original and revised plan, decision, notice and readiness check",
      "interpretation_limit": "A deferral date is a plan; ask for an executed example before concluding repeatability.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q07",
      "theme": "Exceptions",
      "peer_context_sources": [
        "ESS18-S07"
      ],
      "question": "How is an urgent repair handled during a locally sensitive period without importing an assumed blanket freeze?",
      "proposed_roles": "Service and incident leads; accountable functional owner",
      "evidence_request": "Redacted exception rationale, decisions and verification; or an explicit no-sample response",
      "interpretation_limit": "An exception is not automatically a defect, and no sample is not proof that exceptions are uncontrolled.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q08",
      "theme": "Stakeholder coverage",
      "peer_context_sources": [
        "ESS18-S03"
      ],
      "question": "How are affected units represented, including disagreement and a request that was not accepted?",
      "proposed_roles": "Functional representatives; service/product owner",
      "evidence_request": "One request-to-disposition record including a dissent or rejected option",
      "interpretation_limit": "A committee listing is not proof of coverage, agreement or closure.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q09",
      "theme": "Communication continuity",
      "peer_context_sources": [
        "ESS18-S04"
      ],
      "question": "How does time-sensitive information reach affected units when a standing forum is canceled or an attendee is absent?",
      "proposed_roles": "Liaison or communications role; operations lead",
      "evidence_request": "Redacted alternate communication path and one acknowledgement or follow-up example",
      "interpretation_limit": "A canceled meeting does not by itself establish a communication failure.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q10",
      "theme": "Roadmap truth",
      "peer_context_sources": [
        "ESS18-S09"
      ],
      "question": "How do recipients distinguish a tentative roadmap update from a committed or completed change?",
      "proposed_roles": "Product/service owner; communications role",
      "evidence_request": "A dated announcement linked to its decision and subsequent status",
      "interpretation_limit": "A presentation or agenda is not evidence that a capability shipped.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q11",
      "theme": "Test environment fit",
      "peer_context_sources": [
        "ESS18-S05",
        "ESS18-S06"
      ],
      "question": "How is a representative student journey tested against relevant interface and environment versions?",
      "proposed_roles": "Test/development lead; integration owner",
      "evidence_request": "Environment/version map and redacted test execution for the sampled change",
      "interpretation_limit": "An available environment or written test plan does not establish executed coverage.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q12",
      "theme": "Consumer impact",
      "peer_context_sources": [
        "ESS18-S07"
      ],
      "question": "Which consumers are affected when an API or background interface is unavailable even if a portal is reachable?",
      "proposed_roles": "Integration and service owners; downstream process representative",
      "evidence_request": "Dependency list and business-impact check for a planned or actual interruption",
      "interpretation_limit": "Screen availability does not demonstrate whole-journey availability.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q13",
      "theme": "Data reconciliation",
      "peer_context_sources": [
        "ESS18-S01",
        "ESS18-S07"
      ],
      "question": "After interruption or replay, how are missing, delayed or duplicate business updates detected and resolved?",
      "proposed_roles": "Application/integration owners; functional verifier",
      "evidence_request": "Deidentified reconciliation totals, exception disposition and verification locator",
      "interpretation_limit": "Do not infer data correctness from a completed technical restart.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q14",
      "theme": "Recovery demonstrated",
      "peer_context_sources": [
        "ESS18-S06",
        "ESS18-S07"
      ],
      "question": "What evidence distinguishes a written recovery plan from a demonstrated restoration of the sampled service?",
      "proposed_roles": "Operations lead; application and functional verification roles",
      "evidence_request": "Plan/version plus one redacted exercise or incident execution record",
      "interpretation_limit": "Exercise and production evidence remain separate; a plan is not a completed recovery.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q15",
      "theme": "Timing definitions",
      "peer_context_sources": [
        "ESS18-S07"
      ],
      "question": "What do detection, restoration and business-verification times mean, and which intervals or observations are missing?",
      "proposed_roles": "Operations/measurement owner; functional owner",
      "evidence_request": "Timestamp definitions, timezone, denominator/period and missing-data note",
      "interpretation_limit": "A planned duration is neither an observed duration nor a peer performance target.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q16",
      "theme": "Functional outcome",
      "peer_context_sources": [
        "ESS18-S02",
        "ESS18-S06"
      ],
      "question": "Who verifies that the intended student business outcome is correct, rather than only that software is running?",
      "proposed_roles": "Functional verifier; application owner",
      "evidence_request": "Deidentified transaction-result or configuration-verification example linked to the change",
      "interpretation_limit": "Technical completion alone does not establish functional acceptance.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q17",
      "theme": "Manual equivalence",
      "peer_context_sources": [
        "ESS18-S03"
      ],
      "question": "Where does a deliberate manual or shared-service practice achieve the required outcome, and what evidence supports it?",
      "proposed_roles": "Practitioner; service owner",
      "evidence_request": "One repeatable example, exception handling and effort/context note",
      "interpretation_limit": "Automation is not a maturity score; compare outcomes and evidence.",
      "iowa_observation": null
    },
    {
      "id": "ESS18-Q18",
      "theme": "Coverage and disagreement",
      "peer_context_sources": [
        "ESS18-S03",
        "ESS18-S04"
      ],
      "question": "Which services, roles or periods are not represented, and what would resolve any conflicting account?",
      "proposed_roles": "Assessment lead; relevant practitioner and functional owner",
      "evidence_request": "Sample coverage statement, competing locators and bounded follow-up request",
      "interpretation_limit": "Do not generalize a convenience sample or convert absent evidence into a low rating.",
      "iowa_observation": null
    }
  ]
}
```
