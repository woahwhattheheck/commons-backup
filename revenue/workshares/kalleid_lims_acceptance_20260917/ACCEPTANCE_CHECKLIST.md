# Kalleid LIMS workshare — reviewer acceptance checklist

This checklist is an owner-review aid for the proposed Kalleid workshare. It does not create external-send, contractual, quality-release, payment, or revenue authority.

## Commercial / relationship gate

- [ ] A current Muse single-writer decision selects exactly one sender, route, offer, and purpose.
- [ ] Last-inch Slack/provider relationship recensus shows no competing writer, prior send, DNR, bounce/dead-route, or human reply that changes posture.
- [ ] The counterparty has actually expressed interest or asked for scope before any acceptance/contract language is used.
- [ ] `$18,000 fixed` is still explicitly a proposal, not represented as agreed.
- [ ] No statement implies Kalleid has an unverified backlog, defect, staffing shortage, customer, budget, or active project.

## Scope freeze

- [ ] One implementation/project id is recorded.
- [ ] One bounded migration slice is named.
- [ ] Admitted source export/evidence family is named.
- [ ] Admitted target export/read-only evidence family is named.
- [ ] Closed interface set is enumerated.
- [ ] Closed requirement/UAT/validation set is enumerated.
- [ ] Final acceptance decision owner is named by Kalleid/customer.
- [ ] Data handling / redaction / environment constraints are explicit.

## Evidence custody

- [ ] Every material source artifact has a stable evidence reference.
- [ ] Bytes under TJLabs custody have digests recorded.
- [ ] Screenshots/filenames/operator statements are not treated as stronger evidence than they are.
- [ ] Missing/contradictory evidence produces HOLD, never inferred PASS.
- [ ] Sampling rules are documented before sampled field-level checks are interpreted.

## Migration reconciliation

- [ ] Expected population/count rules are defined where meaningful.
- [ ] Identifier preservation/remapping rules are explicit.
- [ ] Required-field completeness rules are explicit.
- [ ] Duplicate/orphan/unmapped-object rules are explicit.
- [ ] Every agreed rule has `PASS`, `HOLD`, or `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`.
- [ ] Every result links to supporting evidence and exception ids where applicable.

## Interface replay / idempotency

- [ ] Each admitted interface scenario has a successful-path replay or owner-supplied equivalent evidence.
- [ ] Retry/duplicate behavior is tested where the interface contract permits retry.
- [ ] Correlation identity or owner-approved equivalent is traceable.
- [ ] Agreed negative/rejection cases are evidenced.
- [ ] Payload/semantic reconciliation depth is stated rather than implied.
- [ ] No destructive production replay occurred under this workshare.

## Exception / HOLD ledger

For every finding:

- [ ] stable exception id;
- [ ] requirement/test/interface/migration reference;
- [ ] evidence references;
- [ ] observed vs expected result;
- [ ] owner-approved severity/disposition;
- [ ] next owner/action;
- [ ] closure-evidence requirement;
- [ ] one of `OPEN`, `HOLD`, `RETEST_READY`, `CLOSED_WITH_EVIDENCE`.

No item disappears because a deadline arrives.

## Final reviewer pack

- [ ] Frozen-scope manifest is present.
- [ ] Evidence/digest inventory is present.
- [ ] Requirements-to-evidence matrix is complete.
- [ ] Migration reconciliation results are present.
- [ ] Interface replay results are present.
- [ ] Exception/HOLD ledger is present.
- [ ] Retest/closure evidence is linked.
- [ ] Residual HOLDs are visible.
- [ ] Reviewer handoff separates proven facts, owner assertions, and unresolved items.
- [ ] Final language does not claim TJLabs is Kalleid/customer's regulatory, quality, production-release, procurement, or contractual authority.

## Delivery-complete decision

Delivery may be marked complete only when the bounded evidence product is complete and traceable. Delivery-complete does **not** require pretending owner-controlled HOLDs are resolved. If owner-controlled evidence or decisions remain missing, the pack must state those blockers explicitly.

## Authority readback

Before any repository or Slack closeout calls this lane commercially successful, verify:

- `proposal_accepted = false` unless counterparty evidence proves otherwise;
- `contract_exists = false` unless executed-contract evidence proves otherwise;
- `work_authorized = false` unless customer/counterparty authorization proves otherwise;
- `payment_received = false` unless provider payment evidence proves otherwise;
- `booked_revenue = false` and `recognized_revenue = false` unless accounting evidence and policy independently support them.
