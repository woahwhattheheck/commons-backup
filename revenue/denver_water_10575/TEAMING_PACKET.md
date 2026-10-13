# Denver Water 10575 — specialist teaming packet (internal draft)

This is a bounded technical workstream that a qualified prime could insert into a broader Customer Care agent-assist implementation **only if the controlling solicitation permits subcontract/team delivery**. It is not a proposal, commitment, buyer communication or representation of past performance.

## Proposed specialist outcome

Build independent evidence that an internal AI Agent Assistant behaves correctly at the seams where enterprise integrations and generative behavior are hardest to trust:

1. **Retrieval and citation fidelity**
   - source allowlist derived from prime/buyer-approved knowledge systems;
   - exact source/version identity in test evidence;
   - citation-to-claim checks and unsupported-answer detection;
   - stale-content and cross-account contamination tests.

2. **Customer/account context isolation**
   - opaque synthetic identities and tenant/account boundaries in preproduction;
   - negative tests proving one interaction cannot inherit another customer's context;
   - explicit redaction assertions for logs and evaluation artifacts.

3. **Human-reviewed write-back authority**
   - draft-only state until an explicit human approval event is bound to the exact proposed mutation;
   - replay/idempotency keys, changed-payload conflict rejection and generation fencing;
   - unknown provider outcome is a hold/reconciliation state, never assumed success;
   - audit receipt binds proposed mutation, approver evidence, execution request and returned outcome without persisting raw secrets.

4. **Genesys / CC&B / SharePoint integration QA**
   - contract tests against prime-provided adapters and schemas;
   - read-only vs write-capable path separation;
   - timeout/retry/duplicate/out-of-order event hostiles;
   - schema drift and unavailable-source behavior;
   - preproduction acceptance evidence only unless the prime/buyer separately authorizes production access.

5. **Regression and release evidence**
   - deterministic golden-task suite covering source-grounded answers, account context, policy boundaries and handoff;
   - adversarial/hallucination probes with explicit unsupported-answer handling;
   - exact model/config/source/adapter version binding per run;
   - release receipt reports observed pass/fail evidence, never a blanket safety/certification claim.

6. **Governance / audit support**
   - map actual buyer requirements to exact tests and artifacts after the controlling package is recovered;
   - retention-minimized evidence manifest;
   - accessibility/security/privacy controls are verified only where the prime supplies authoritative design/evidence; no certification is inferred by this workstream.

## Inputs required from a prime before scope can become proposal-ready

- complete current solicitation + addenda/Q&A;
- intended legal/prime/subcontract role and buyer-permitted teaming structure;
- exact Genesys, CC&B, SharePoint and other interface boundaries;
- data classification and approved synthetic/preproduction test strategy;
- model/provider/runtime choice and deployment boundary;
- prime-owned security/privacy/accessibility/records architecture;
- explicit release/write-back human authority workflow;
- acceptance criteria, environments, schedule, support boundary and artifacts expected by Denver Water.

## Explicit exclusions

No claim here supplies enterprise platform licensing, Genesys/CC&B OEM status, public-utility implementation references, professional/cyber insurance, legal representations, production credentials, production customer data, managed operations, buyer contact, pricing, signature, contract acceptance or revenue recognition.
