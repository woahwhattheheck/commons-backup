# TDEM-RFP-1548 / Euna Grants workshare — reviewer acceptance checklist

This checklist reviews the proposed TJLabs evidence/acceptance workshare. It does not create external-send, bid, contractual, security-certification, grant-decision, production, payment, or revenue authority.

## A. Opportunity and relationship gate

- [ ] Controlling TDEM RFP/addenda/clarifications are retained before discovered requirements are called authoritative.
- [ ] Solicitation id is confirmed as `TDEM-RFP-1548`.
- [ ] Current response deadline is re-read from buyer-controlled evidence.
- [ ] Mandatory conference/pre-bid obligations are verified by the qualified prime.
- [ ] VetHUB/subcontracting obligations are verified and owned by the prime.
- [ ] Euna has actually confirmed pursuit/interest before relationship language is used.
- [ ] Current Muse single-writer decision selects one sender, recipient, offer and purpose.
- [ ] Immediate Slack and Gmail recensus is clean before any send.
- [ ] `$45,000 fixed / 20 business days` remains proposed, not accepted.
- [ ] No statement implies Euna has an unverified backlog, staffing shortage, customer commitment, budget, award, or need for TJLabs.

## B. Prime authority / qualification boundary

- [ ] Official RFP/addenda interpretation remains with the prime.
- [ ] Bidder eligibility/corporate representations remain with the prime.
- [ ] Platform ownership/licensing remains with the prime.
- [ ] References/past performance remain with the prime.
- [ ] Security/certification representations remain with the prime/provider.
- [ ] FEMA/state integration commercial relationships remain with the prime/provider.
- [ ] Customer pricing/support/SLA/training remain with the prime.
- [ ] VetHUB/subcontract plan remains with the prime.
- [ ] Proposal forms/signatures/submission remain with the prime.
- [ ] Production access/go-live remains with the prime/TDEM.

## C. Scope freeze

- [ ] One implementation id.
- [ ] One approved source export family.
- [ ] One approved target evidence/import family.
- [ ] Closed program family/set.
- [ ] Closed award/subaward/subrecipient population.
- [ ] Closed reimbursement/disaster-cost population.
- [ ] Closed FEMA/federal interface set.
- [ ] Closed state/ERP interface set.
- [ ] Closed acceptance/reporting/audit requirement set.
- [ ] One cutover rehearsal generation.
- [ ] Named acceptance decision owner.
- [ ] Explicit data-handling/redaction/environment constraints.

## D. Evidence custody

- [ ] Every material artifact has a stable evidence reference.
- [ ] Retained bytes have digests.
- [ ] Owner-supplied generation/provenance is recorded separately from byte custody.
- [ ] Screenshots/filenames/operator statements are not overclaimed.
- [ ] Discovery summaries are labeled non-controlling.
- [ ] Missing/contradictory evidence produces HOLD.
- [ ] Owner assertions are labeled and not upgraded to provider truth.

## E. Source profile

- [ ] Program population is explicit.
- [ ] Award/subaward population is explicit.
- [ ] Subrecipient population/relationships are explicit.
- [ ] Reimbursement/request population is explicit.
- [ ] Stable identifiers/candidate keys are documented.
- [ ] Required-field completeness is measured where meaningful.
- [ ] Duplicate/orphan/unmapped populations are measured.
- [ ] Status vocabularies are inventoried.
- [ ] Fiscal/date/time conventions are inventoried.
- [ ] Amount precision/currency conventions are inventoried.
- [ ] Document/attachment classes are inventoried without unnecessary sensitive content.

## F. Migration reconciliation

For each admitted rule:

- [ ] stable rule id;
- [ ] explicit expected behavior;
- [ ] source evidence refs;
- [ ] target evidence refs;
- [ ] owner-approved mapping where semantics change;
- [ ] terminal result is `PASS_WITH_EVIDENCE`, `FAIL_WITH_EVIDENCE`, `HOLD_MISSING_OWNER_EVIDENCE`, or `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`;
- [ ] sampling rule was frozen before interpretation where used;
- [ ] passing samples are not generalized beyond their scope;
- [ ] every FAIL/HOLD links to an exception.

## G. Identity and lifecycle traceability

- [ ] Program identity mapped.
- [ ] Award identity mapped.
- [ ] Subaward identity mapped where applicable.
- [ ] Subrecipient identity mapped.
- [ ] Project/mission identity mapped where applicable.
- [ ] Reimbursement identity mapped.
- [ ] Amendment/version history mapped.
- [ ] Application/review/award status mappings owner-approved.
- [ ] Monitoring/reporting/closeout mappings owner-approved.
- [ ] Similar labels are not assumed semantically equivalent.

## H. Financial/reimbursement evidence

- [ ] Authorized/award/amended amount semantics explicit.
- [ ] Requested reimbursement semantics explicit.
- [ ] Approved reimbursement semantics explicit.
- [ ] Paid/disbursed claims use provider/accounting evidence appropriate to that claim.
- [ ] Match/share categories explicit where in scope.
- [ ] Cost categories explicit where in scope.
- [ ] Fund/program/project allocations explicit where in scope.
- [ ] Fiscal-period semantics explicit.
- [ ] Precision/rounding explicit.
- [ ] Reversal/adjustment semantics explicit.
- [ ] Cumulative vs incremental amounts explicit.
- [ ] TJLabs does not authorize payment or certify allowability.

## I. FEMA/federal integration seam

- [ ] Owner-approved interface contract/expected behavior retained.
- [ ] Program/award/project/subrecipient identifiers mapped as applicable.
- [ ] Amount/status mappings explicit.
- [ ] Correlation identity traceable.
- [ ] Happy-path evidence present or HOLD.
- [ ] Duplicate/idempotency evidence present or HOLD.
- [ ] Retry behavior present or HOLD.
- [ ] Invalid/rejected cases present or HOLD.
- [ ] Partial-batch behavior present or HOLD where applicable.
- [ ] No production federal credential/portal mutation occurred.

## J. State / ERP integration seam

- [ ] Fund/program/cost-center/account mappings owner-approved.
- [ ] Vendor/subrecipient identity mapping owner-approved.
- [ ] Reimbursement/payment-request identity traceable.
- [ ] Invoice/payment/status semantics explicit where applicable.
- [ ] Fiscal-period/amount precision explicit.
- [ ] Transaction correlation traceable.
- [ ] Duplicate/retry behavior tested or HOLD.
- [ ] Reversal/adjustment behavior tested or HOLD where applicable.
- [ ] Reject/error behavior tested or HOLD.
- [ ] No production financial posting occurred under this workshare.

## K. Award / subrecipient lifecycle evidence

- [ ] Application/review lineage traceable.
- [ ] Award/amendment lineage traceable.
- [ ] Deliverable/report references traceable where in scope.
- [ ] Monitoring/exception references traceable where in scope.
- [ ] Reimbursement lineage traceable.
- [ ] Closeout evidence references traceable.
- [ ] Activity/audit evidence class explicit.
- [ ] TJLabs does not decide eligibility, award, risk acceptance, findings, or closeout authority.

## L. Exception / HOLD ledger

Every finding includes:

- [ ] stable exception id;
- [ ] rule/requirement/interface/migration ref;
- [ ] evidence refs;
- [ ] observed result;
- [ ] expected result;
- [ ] evidence class;
- [ ] owner-approved severity/disposition;
- [ ] next owner/action;
- [ ] closure evidence requirement;
- [ ] state `OPEN`, `HOLD`, `RETEST_READY`, or `CLOSED_WITH_EVIDENCE`.

No exception disappears because a deadline arrives.

## M. Cutover rehearsal

- [ ] Exact source generation frozen.
- [ ] Target/configuration generation frozen or owner-attested with evidence class explicit.
- [ ] Mapping/transformation generation frozen.
- [ ] Preflight gates enumerated.
- [ ] Migration reconciliation attached.
- [ ] Integration acceptance results attached.
- [ ] Financial/reimbursement reconciliation attached.
- [ ] Unresolved exceptions visible.
- [ ] Rollback prerequisites come from prime/platform owner.
- [ ] TJLabs final posture is readiness/HOLD, not independent `PRODUCTION_GO`.

## N. Audit / security evidence

- [ ] Identity/access evidence owner/provider sourced.
- [ ] Administrative/audit-log evidence owner/provider sourced.
- [ ] Encryption/transport evidence owner/provider sourced.
- [ ] Environment separation evidence owner/provider sourced.
- [ ] Backup/DR evidence owner/provider sourced.
- [ ] Retention/export evidence owner/provider sourced.
- [ ] Hosting/data-region evidence owner/provider sourced.
- [ ] Change/release evidence owner/provider sourced.
- [ ] Integration credential boundary explicit.
- [ ] Certification gaps remain HOLDs.
- [ ] TJLabs does not self-certify security/compliance frameworks.

## O. Final reviewer pack

- [ ] Frozen scope/input manifest.
- [ ] Evidence/digest inventory.
- [ ] Source profile.
- [ ] Migration acceptance matrix/results.
- [ ] FEMA/federal integration results.
- [ ] State/ERP integration results.
- [ ] Reimbursement/disaster-cost reconciliation.
- [ ] Award/subrecipient lifecycle traceability.
- [ ] Exception/HOLD ledger.
- [ ] Cutover rehearsal/readiness evidence.
- [ ] Audit/security evidence matrix.
- [ ] Retest/closure evidence.
- [ ] Residual HOLD list.
- [ ] Reviewer handoff separates proven facts, owner assertions, and unresolved items.

## P. Commercial authority readback

Before any closeout calls the lane commercially successful, verify:

- `prime_pursuit = UNKNOWN` unless Euna/prime evidence proves otherwise;
- `counterparty_interest = UNKNOWN` unless a human reply proves otherwise;
- `proposal_accepted = false` unless counterparty evidence proves otherwise;
- `contract_exists = false` unless executed-contract evidence proves otherwise;
- `work_authorized = false` unless authorization evidence proves otherwise;
- `invoice_exists = false` unless invoice evidence proves otherwise;
- `receivable_exists = false` unless accounting/contract evidence proves otherwise;
- `payment_received = false` unless provider payment evidence proves otherwise;
- `booked_revenue = false` and `recognized_revenue = false` unless accounting evidence/policy independently support them.

Repository merge, email send, positive reply, proposal discussion, bid submission, contract, work authorization and payment are distinct states.