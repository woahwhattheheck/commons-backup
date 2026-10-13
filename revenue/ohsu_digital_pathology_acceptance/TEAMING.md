# Paid teaming offer — OHSU RFP-2027-2012 integration acceptance sprint

**Proposed specialist price:** **$7,500 fixed** for a two-week sprint. This is our proposed subcontract price, not an OHSU-published budget or an accepted commercial term.

## Why this exists

OHSU's public listing asks for an enterprise digital-pathology IMS with seamless bi-directional Epic Beaker integration and scalable native/third-party AI integration. An IMS prime already owns the product, references, regulated deployment story, and buyer relationship. The integration/evidence layer can still become a schedule and evaluation risk late in a proposal or proof-of-capability cycle.

We offer a bounded acceptance sprint that turns the prime's existing integration into reproducible evidence without claiming to replace its IMS.

## Deliverables

1. **Epic/IMS workflow acceptance matrix** bound to the prime's implemented messages and public Epic digital-pathology contract: order, per-slide availability/status, deep-link identity, optional closeout, replay behavior, and exception handling.
2. **Deterministic transcript verifier** adapted from this public harness to the prime's non-production evidence format. Exact retries are idempotent; changed replays, stale/conflicting identity, status regression, and unbound links fail closed.
3. **AI-adapter provenance ledger** for any native/third-party AI hooks: model/version/artifact/input digests, invocation identity, stated intended use, and an explicit boundary between integration evidence and clinical authority.
4. **Synthetic/no-PHI hostile suite** covering duplicate/out-of-order/conflicting events, multi-slide cases, link misbinding, malformed evidence, and case-close timing.
5. **Proposal evidence packet** mapping demonstrated integration behaviors to runnable receipts, with unsupported/customer-only claims marked open rather than filled in.
6. **One remediation pass** on integration defects exposed by the acceptance run, followed by a rerun on the corrected candidate.

## Two-week shape

- Days 1–2: bind exact prime integration surfaces and define evidence export.
- Days 3–5: adapt verifier + hostile cases to the product's actual contract.
- Days 6–8: execute against synthetic/staging evidence supplied by the prime; triage gaps.
- Days 9–10: one remediation/reverification cycle and proposal-ready evidence handoff.

## Boundaries

- No production patient data is required for this sprint; synthetic/staging evidence is the default.
- No diagnosis, pathology-image interpretation, autonomous clinical action, or clinical-performance claim.
- The prime remains responsible for product claims, customer references, OHSU minimum qualifications, security/BAA terms, regulatory status, pricing to OHSU, and final proposal submission.
- Any production or PHI-bearing extension would be separately scoped under the prime's security/privacy process; it is not included in this public package.

## Acceptance condition

The sprint is complete when the agreed integration evidence set can be replayed through the verifier with a deterministic receipt, hostile cases fail as specified, open claims are explicitly enumerated, and the prime receives the source, tests, evidence matrix, and runbook.
