# UIOWA-058 — Secure-development guidance discussion pack

> Fictional facilitation material. Assess the usability of guidance and support systems, not individual engineers.

## Guidance usability snapshot

| Guidance | Topic | Status | Primary evidence state |
|---|---|---|---|
| GUIDE-INPUT-01 | input_handling | current | USABLE_GUIDANCE_EVIDENCED |
| GUIDE-AUTHZ-01 | authorization_design | current | USABLE_GUIDANCE_EVIDENCED |
| GUIDE-ERROR-01 | error_handling | current | USABLE_GUIDANCE_EVIDENCED |
| GUIDE-INPUT-OLD | input_handling | superseded | SUPERSEDED_NOT_CURRENT_SUPPORT |
| GUIDE-AUTHZ-PARTIAL | authorization_design | current | PARTIAL_GUIDANCE_EVIDENCE |
| GUIDE-ERROR-UNKNOWN | error_handling | unknown | GUIDANCE_STATUS_UNKNOWN |

## Discussion exercises

### EX-INPUT-01 — Student import gains a new partner-supplied CSV field

**Topic:** input_handling

**Scenario:** A fictional ESS import receives a new optional field from an external partner. Sample files vary in encoding, field length, and row shape. The team must decide how the boundary should behave before release.

**Practice goal:** Use reusable input-boundary guidance to define accepted structure, bounds, failure behavior, and support diagnostics.

**Unsafe shortcut to discuss:** Accept any row that can be parsed and rely on downstream code to cope with unexpected structure.

**Discussion questions**
- Where would you look for the current pattern?
- What should be explicitly accepted or rejected?
- What evidence would show the behavior was tested?
- When would specialist input be useful?

**Reasoning anchors (facilitator prompts, not employee scoring keys)**
- define expected structure and bounds
- predictable rejection path
- separate user-facing error from diagnostics
- prefer current guidance over superseded note

**Evidence to request**
- current validation guidance
- representative schema/contract
- boundary-condition tests
- review or design record

**When specialist help should become an option:** The parser or trust boundary is novel, or the team cannot determine which malformed cases must be rejected.
**Referenced guidance:** GUIDE-INPUT-01, GUIDE-INPUT-OLD
**Current usable guidance evidenced in this synthetic packet:** GUIDE-INPUT-01
**Non-current/unknown-status references:** GUIDE-INPUT-OLD — do not treat these as current support.

### EX-AUTHZ-02 — Research administrator can act for several projects

**Topic:** authorization_design

**Scenario:** A fictional RIS feature adds delegated administration. A signed-in administrator may update some research projects but not others, and a shared API serves several project types.

**Practice goal:** Separate authentication from authorization and make the requested action/resource relationship explicit.

**Unsafe shortcut to discuss:** Treat possession of a broad administrator role as sufficient for every project resource.

**Discussion questions**
- Which facts should the authorization decision depend on?
- Where is the reusable authorization pattern?
- How would you test cross-project boundaries?
- What ambiguity should trigger IAM/security consultation?

**Reasoning anchors (facilitator prompts, not employee scoring keys)**
- caller plus action plus target resource
- resource-scoped policy
- deny when required evidence is absent
- test permitted and non-permitted project boundaries

**Evidence to request**
- role/resource decision model
- authorization tests
- delegation design record
- specialist consultation route

**When specialist help should become an option:** Delegation crosses organizational or policy domains, or existing role semantics do not express resource ownership clearly.
**Referenced guidance:** GUIDE-AUTHZ-01, GUIDE-AUTHZ-PARTIAL
**Current usable guidance evidenced in this synthetic packet:** GUIDE-AUTHZ-01
**Guidance-system evidence gaps**
- GUIDE-AUTHZ-PARTIAL: owner role not supplied
- GUIDE-AUTHZ-PARTIAL: no decision/application triggers supplied
- GUIDE-AUTHZ-PARTIAL: specialist route or trigger is missing/unknown

### EX-ERROR-03 — Identity synchronization fails on an external dependency

**Topic:** error_handling

**Scenario:** A fictional IAM synchronization job receives an unexpected dependency response. Operators need enough detail to investigate, while end users should receive a stable supportable message.

**Practice goal:** Apply reusable error-handling guidance that preserves diagnostics without exposing unnecessary internal detail.

**Unsafe shortcut to discuss:** Return raw dependency exceptions directly to the caller so support has maximum detail.

**Discussion questions**
- What belongs in the user-facing response versus operational evidence?
- How should a support engineer correlate the two?
- Where is current guidance located?
- When should reliability/security specialists join the design?

**Reasoning anchors (facilitator prompts, not employee scoring keys)**
- stable user-safe category
- correlation identifier
- diagnostic detail retained in controlled evidence
- known owner and specialist route

**Evidence to request**
- error-handling pattern
- sample user-safe response
- access-controlled diagnostic example
- correlation/runbook evidence

**When specialist help should become an option:** The team is unsure whether diagnostic content crosses a sensitive-data boundary or how failures propagate across services.
**Referenced guidance:** GUIDE-ERROR-01, GUIDE-ERROR-UNKNOWN
**Current usable guidance evidenced in this synthetic packet:** GUIDE-ERROR-01
**Non-current/unknown-status references:** GUIDE-ERROR-UNKNOWN — do not treat these as current support.
**Guidance-system evidence gaps**
- GUIDE-ERROR-UNKNOWN: no discoverable location supplied
- GUIDE-ERROR-UNKNOWN: specialist route or trigger is missing/unknown

## Facilitation boundary

Use participant reasoning to discover whether guidance is findable, applicable, reusable, owned, and backed by accessible specialist help. Do not grade individuals, demand one implementation pattern, or treat a written document as proof of routine practice. Follow up with artifacts from real work before forming a finding.
