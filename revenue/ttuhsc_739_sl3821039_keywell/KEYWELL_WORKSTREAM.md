# Partner-ready workstream — AI workflow evaluation & pilot verification

**Target prime:** Keywell AI, only if Keywell confirms it is eligible and actively pursuing TTUHSC RFP 739-SL3821039.  
**Potential subcontractor:** TJLabs.  
**Commercial basis:** paid, bounded technical work package; fee/rate and contracting terms to be agreed with the prime before production work begins.  
**Current status:** internal response-ready draft; no teaming relationship or award is implied.

## Why this workstream exists

TTUHSC's RFP puts most evaluation weight on service specifications and asks for durable AI adoption across academic, administrative, clinical, and research operations. A prime can cover enterprise strategy, healthcare/public-sector governance, organizational change, training, procurement, and institutional compliance while using TJLabs for a narrow evidence-producing layer: **prove selected AI workflows behave correctly under normal and hostile operational conditions before they are called pilot-ready or production-ready.**

## Proposed TJLabs scope

For each workflow selected by the prime and TTUHSC, TJLabs would build an acceptance pack around the approved workflow contract:

1. **Workflow contract** — named inputs, allowed data classes, expected outputs/actions, human-approval points, prohibited actions, stop conditions, owners, and success metrics.
2. **Known-answer replay fixtures** — synthetic or properly sanitized examples with expected outcomes and exact provenance.
3. **Failure injection** — missing, stale, contradictory, malformed, duplicate, retry, timeout, partial-tool, permission-denied, and unavailable-dependency cases.
4. **Decision/action receipts** — deterministic evidence tying each attempted decision/action to input version, policy/control version, tool/model/config version, human approval where required, outcome, and stop/rollback state.
5. **Regression gate** — rerunnable checks that prevent a changed model, prompt, policy, integration, or tool schema from silently invalidating prior acceptance evidence.
6. **Pilot-verification report** — pass/fail matrix, unresolved failure modes, operational handoff boundaries, measured KPI deltas, and a concrete `KEEP / CHANGE / STOP` recommendation.

## Inputs required from the prime / TTUHSC

The workstream does not begin from private production data by default. The prime supplies or brokers:

- one approved workflow definition and business owner;
- the authoritative policy/process documents that constrain it;
- the approved environment and access path;
- the allowed data classification and de-identification/sanitization rules;
- any existing prototype/API/tool contract to test;
- human approval/escalation roles;
- baseline KPI definitions and measurement window;
- security/privacy owner and incident/escalation path.

Until those exist, the harness remains on synthetic/sanitized fixtures and cannot be represented as clinical, FERPA, HIPAA, or production validation.

## Outputs

A completed work package produces:

- workflow acceptance contract;
- replay fixture manifest and provenance;
- failure-mode matrix;
- deterministic runner/specification and rerun instructions;
- control/approval/stop-path evidence;
- regression baseline and change-detection criteria;
- ROI/adoption measurement sheet with raw metric definitions;
- final pilot-readiness report with unresolved blockers and owners.

The prime receives all deliverables needed to integrate the evidence into its broader TTUHSC transformation, governance, change-management, training, and knowledge-transfer deliverables.

## Binary acceptance criteria

A work package is accepted only when all of the following are true for the agreed fixture set:

- every valid fixture reaches the expected disposition or an explicitly approved variance;
- every invalid/unsafe fixture stops with a machine-readable reason and owner;
- no injected duplicate/retry creates a duplicate external state change;
- every action requiring human approval proves that approval occurred before the action;
- every decision/action receipt resolves to the exact input/control/model/tool/config versions used;
- rollback/reset behavior is demonstrated for every agreed reversible side effect;
- the same frozen fixture set can be rerun after a change and produces an explicit regression diff;
- KPI measurements are calculated from observed timestamps/counts/cost inputs rather than invented baselines;
- unresolved exceptions are enumerated, owned, and excluded from any `pilot-ready` claim.

## Explicit exclusions

Unless separately contracted and supported by prime/owner facts, TJLabs does **not** claim to provide:

- prime-contractor responsibility or proposal submission;
- healthcare/legal/compliance certification or legal advice;
- TTUHSC institutional policy approval;
- VetHUB plan ownership;
- TX-RAMP, insurance, franchise-tax, or bidder certifications;
- three qualifying client references on behalf of the prime;
- clinical decision authority or autonomous patient-care actions;
- production deployment into TTUHSC systems without an approved environment/access path;
- use of TTUHSC data to train any vendor model;
- unlimited support outside the agreed work package.

## Commercial handoff

If Keywell confirms pursuit and wants this workstream, the next document is a **priced subcontract milestone schedule**, not more free exploratory production work. Pricing must be agreed by the authorized prime and TJLabs and should map directly to selected workflows, fixture volume, integration complexity, evidence requirements, security constraints, and schedule. No dollar amount is asserted in this package.