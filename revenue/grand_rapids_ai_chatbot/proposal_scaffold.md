# Grand Rapids 920-45-269 — proposal-production scaffold

**Status:** HOLD until the controlling MITN packet/addenda are acquired and the executable preflight returns `READY`.

This is a source-bound production carrier, not a submitted proposal and not a representation that Token Junkie Labs satisfies packet-only bidder gates.

## 1. Executive outcome

Position the system around resident service navigation rather than unconstrained chat: answer from City-approved sources with exact source/version lineage; abstain or route when evidence is stale, conflicting, missing, or high-risk; correlate duplicate cross-channel requests into one canonical case; preserve deterministic evidence for answer, route, rule, model, and external-effect reconciliation.

**Packet insertion needed:** exact stated objectives, scope language, term, evaluation weights, and mandatory response format.

## 2. Resident experience and City authority boundary

- Informational/service-navigation answers only from approved knowledge sources.
- City-defined queue/routing ownership for unresolved requests.
- Emergency, legal, permit/benefit eligibility, enforcement, and other high-risk determinations never become autonomous answer authority.
- Production writes require an explicitly approved connector contract and human release semantics.
- Accessibility, language, channel, privacy, retention, and records requirements remain packet-required until sourced.

## 3. Technical architecture narrative

1. **Knowledge snapshot:** approved source IDs + versions + freshness policy.
2. **Decision layer:** answer / hold / escalate with reason codes and source lineage.
3. **Routing layer:** City-owned intent-to-queue rules; no hidden fallback queue.
4. **Cross-channel identity:** stable canonical request key so retries/duplicates do not create duplicate logical effects.
5. **Connector boundary:** idempotency key, pre-effect validation, post-timeout reconciliation, explicit unknown-effect quarantine.
6. **Evidence receipt:** case ID, disposition, source/version, rule/model version, route, external-effect status, replay signature.

**Packet insertion needed:** required hosting, vendor platform constraints, named City systems/APIs, SSO/IAM, observability, DR/BCP, cyber controls, data residency, retention, records, and SLA requirements.

## 4. Acceptance/UAT

Use City-approved synthetic/redacted fixtures. The included `acceptance.py` validates the invariants but does not invent City gold data. Replace the sample fixture with the City's approved intents, sources, routes, and hostile cases.

Required categories:
- fresh approved answer + exact source/version citation;
- conflicting, stale, and missing source => HOLD/ESCALATE;
- emergency/legal/eligibility/enforcement/high-risk => no autonomous ANSWER;
- route must match City gold queue;
- cross-channel duplicates => one canonical case and at most one logical effect;
- timeout-after-commit => reconciled `APPLIED` or `NOT_APPLIED`, never silent unknown;
- replay => stable evidence signature.

## 5. Implementation and transition

Proposed phases must be re-cut against the RFP schedule after packet acquisition:
- source/routing inventory and City-owned policy freeze;
- synthetic/redacted UAT and hostile fixture;
- limited approved channel pilot;
- measured expansion to packet-authorized channels/integrations;
- operations, change control, monitoring, source freshness, model/rule versioning, incident handling, and knowledge-owner workflow.

Do **not** use the old exploratory `$32k / $210k / $96k` fit ladder as bid pricing. The packet pricing form and owner commercial approval control.

## 6. Qualifications / administrative response

HOLD until packet and owner evidence establish: eligibility, VSS/MITN state, EBO applicability/forms, certifications, insurance, reference requirements, personnel/resumes, subcontracting rules, legal exceptions, conflicts, attestations, and signature authority.

## 7. Submission release

Run:

```bash
python revenue/grand_rapids_ai_chatbot/preflight.py \
  revenue/grand_rapids_ai_chatbot/submission_state.json
```

Only `READY` permits a human owner to consider the separately authorized portal/signature step. `READY` itself does not submit anything and makes no award/payment claim.
