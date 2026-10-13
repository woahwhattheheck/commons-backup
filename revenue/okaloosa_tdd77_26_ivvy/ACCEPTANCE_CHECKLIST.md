# Okaloosa TDD 77-26 / iVvy workshare — reviewer acceptance checklist

This checklist reviews the proposed TJLabs specialist workshare. It does not create bid, external-send, contractual, security-certification, production, payment, or revenue authority.

## A. Current opportunity / relationship gate

- [ ] The controlling current RFP/addenda are retained by the qualified prime before any requirement is represented as authoritative.
- [ ] RFP identifier is confirmed as `TDD 77-26`.
- [ ] Current response deadline is re-read from the buyer-controlled source.
- [ ] iVvy has actually confirmed pursuit/interest before language implies a relationship.
- [ ] A current Muse single-writer decision selects exactly one sender, recipient, offer and purpose.
- [ ] Immediate pre-send Slack census shows no competing writer, send, DNR, route failure or human reply.
- [ ] Immediate pre-send Gmail census shows no competing send, reply, DSN/bounce or relationship event.
- [ ] `$35,000 fixed / 15 business days` remains explicitly proposed, not accepted.
- [ ] No statement implies iVvy has a backlog, staffing shortage, customer commitment, budget, award or obligation to use TJLabs.

## B. Prime / platform qualification boundary

The prime owns these questions. TJLabs may record evidence; it may not self-certify them.

- [ ] SaaS ownership/operation requirement verified against controlling buyer text.
- [ ] Multi-venue functional requirements verified.
- [ ] References/past performance verified by the prime.
- [ ] Required security/certification language verified by the prime.
- [ ] PCI/payment obligations verified by the prime/provider.
- [ ] Insurance/bond/form requirements verified by the prime.
- [ ] Support/SLA/maintenance obligations verified by the prime.
- [ ] Proposal pricing/term structure owned by the prime.
- [ ] Submission/signatory authority remains with the prime.

Any unresolved item is a qualification HOLD, not a TJLabs compliance claim.

## C. Scope freeze

- [ ] One implementation/project id is recorded.
- [ ] One approved legacy export family is recorded.
- [ ] One approved target evidence/import family is recorded.
- [ ] Historical migration population is bounded.
- [ ] Workday contract/evidence boundary is enumerated.
- [ ] DocuSign contract/evidence boundary is enumerated.
- [ ] Bluepay/payment contract/evidence boundary is enumerated or buyer-controlled replacement is documented.
- [ ] UAT/acceptance requirements are closed and versioned.
- [ ] Cutover rehearsal generation is identified.
- [ ] Acceptance decision owner is named by the prime/customer.
- [ ] Data-handling/redaction/environment constraints are explicit.

## D. Source evidence custody

- [ ] Every material source artifact has a stable evidence reference.
- [ ] Bytes in TJLabs custody have recorded digests.
- [ ] Export generation/time supplied by owner is recorded separately from byte digest.
- [ ] File names/screenshots/operator descriptions are not treated as stronger evidence than they are.
- [ ] Missing/contradictory evidence produces HOLD.
- [ ] No external URL alone is treated as retained controlling buyer content.
- [ ] Discovery summaries are distinguished from buyer-controlled requirements.

## E. Historical migration profile

- [ ] Population/object classes are enumerated.
- [ ] Stable identifiers/candidate business keys are documented.
- [ ] Required-field completeness is measured where meaningful.
- [ ] Relationship/cardinality observations are documented.
- [ ] Duplicate/orphan/unmapped populations are measured.
- [ ] Time-zone/date conventions are documented where present.
- [ ] Currency/numeric precision conventions are documented where present.
- [ ] Attachment/document classes are inventoried without unnecessary sensitive content.
- [ ] Source evidence gaps are explicit.

## F. Migration reconciliation

For every admitted rule:

- [ ] rule id is stable;
- [ ] expected behavior is explicit;
- [ ] source evidence refs are present;
- [ ] target evidence refs are present;
- [ ] result is one of `PASS_WITH_EVIDENCE`, `FAIL_WITH_EVIDENCE`, `HOLD_MISSING_OWNER_EVIDENCE`, `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`;
- [ ] sampling rule, if any, was frozen before interpretation;
- [ ] a passing sample does not silently prove an unsampled population;
- [ ] identifier remapping is explicitly owner-approved when used;
- [ ] duplicate/orphan exceptions remain visible;
- [ ] every result is traceable to evidence.

## G. Workday acceptance seam

- [ ] Owner-approved Workday contract/expected behavior is retained.
- [ ] Account/cost-center/reference mapping evidence is defined where applicable.
- [ ] Amount/currency/tax precision is explicit where applicable.
- [ ] Status transitions are explicit.
- [ ] Duplicate/retry/idempotency behavior is tested or HOLD.
- [ ] Rejection/error cases are tested or HOLD.
- [ ] Correlation identity is traceable.
- [ ] Financial-output evidence reconciles to admitted source evidence at the agreed depth.
- [ ] No production Workday mutation occurred under the workshare.
- [ ] No accounting-treatment or financial-close conclusion is made by TJLabs.

## H. DocuSign acceptance seam

- [ ] Template/document identity is bound.
- [ ] Owner-approved signer-role mapping is bound.
- [ ] Envelope/request correlation identity is traceable.
- [ ] Expected state transitions are evidenced.
- [ ] Duplicate/retry behavior is tested or HOLD.
- [ ] Cancellation/void/error behavior is tested where in scope.
- [ ] Signed-document/evidence reference linkage is traceable where available.
- [ ] Technical delivery evidence is not represented as legal acceptance.
- [ ] TJLabs did not sign or select a legal signatory.

## I. Bluepay/payment acceptance seam

- [ ] Owner-approved payment contract/expected behavior is retained.
- [ ] Canonical payment/reference identity is explicit.
- [ ] Amount/currency minor-unit handling is explicit.
- [ ] Status/authorization/capture/refund mapping is explicit where in scope.
- [ ] Duplicate/retry/idempotency behavior is tested or HOLD.
- [ ] Provider rejection/error behavior is tested or HOLD.
- [ ] Booking/event/invoice evidence linkage is traceable.
- [ ] No secret or payment-card data is stored in durable test artifacts.
- [ ] Only approved sandbox/non-production actions or owner-supplied provider evidence were used.
- [ ] TJLabs did not move funds or claim PCI certification.

## J. Exception / HOLD ledger

Every finding includes:

- [ ] stable exception id;
- [ ] rule/requirement/interface/migration reference;
- [ ] evidence references;
- [ ] observed result;
- [ ] expected result;
- [ ] owner-approved severity/disposition;
- [ ] next owner/action;
- [ ] closure-evidence requirement;
- [ ] state: `OPEN`, `HOLD`, `RETEST_READY` or `CLOSED_WITH_EVIDENCE`.

No finding disappears because the bid or delivery deadline arrives.

## K. Cutover rehearsal

- [ ] Source generation is frozen.
- [ ] Target/configuration generation is frozen or owner-attested with evidence class clearly marked.
- [ ] Transformation/import version is identified.
- [ ] Preflight gates are enumerated.
- [ ] Reconciliation results are attached.
- [ ] Integration acceptance results are attached.
- [ ] Unresolved exceptions remain visible.
- [ ] Rollback/restore prerequisites come from the platform/prime owner.
- [ ] TJLabs status stops at evidence/readiness; it does not emit independent `PRODUCTION_GO`.

## L. Audit/security evidence

- [ ] Role/access evidence is owner/provider sourced.
- [ ] Audit/logging evidence is owner/provider sourced.
- [ ] Transport/security evidence is owner/provider sourced.
- [ ] Retention/export behavior is evidenced where in scope.
- [ ] Integration credential-handling boundary is documented.
- [ ] Backup/DR evidence comes from the owner/provider.
- [ ] Certification/control gaps remain HOLDs.
- [ ] TJLabs does not self-certify SOC 2, PCI DSS, privacy, legal or County compliance.

## M. Final reviewer pack

- [ ] Frozen scope/input manifest.
- [ ] Evidence/digest inventory.
- [ ] Source-profile summary.
- [ ] Migration reconciliation matrix/results.
- [ ] Workday acceptance evidence.
- [ ] DocuSign acceptance evidence.
- [ ] Payment acceptance evidence.
- [ ] Exception/HOLD ledger.
- [ ] Cutover rehearsal/readiness record.
- [ ] Technical audit/security evidence matrix.
- [ ] Retest/closure evidence.
- [ ] Residual HOLD list.
- [ ] Reviewer handoff separates proven facts, owner assertions and unresolved items.

## N. Authority readback

Before any closeout calls this commercially successful, verify:

- `prime_pursuit = UNKNOWN` unless iVvy/prime evidence proves otherwise;
- `counterparty_interest = UNKNOWN` unless a human reply proves otherwise;
- `proposal_accepted = false` unless counterparty evidence proves otherwise;
- `contract_exists = false` unless executed-contract evidence proves otherwise;
- `work_authorized = false` unless authorization evidence proves otherwise;
- `invoice_exists = false` unless invoice evidence proves otherwise;
- `receivable_exists = false` unless accounting/contract evidence proves otherwise;
- `payment_received = false` unless provider payment evidence proves otherwise;
- `booked_revenue = false` and `recognized_revenue = false` unless accounting evidence/policy independently support them.

Repository merge, email send, positive reply, proposal discussion and implementation readiness are all distinct states. None alone proves revenue.