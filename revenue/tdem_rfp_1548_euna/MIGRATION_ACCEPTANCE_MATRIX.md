# TDEM-RFP-1548 — migration / integration acceptance matrix

This matrix is a reusable reviewer skeleton for the proposed TJLabs workshare. It is not populated with TDEM production data and does not imply Euna/TDEM acceptance.

## Result vocabulary

Every executable row terminates in exactly one of:

- `PASS_WITH_EVIDENCE`
- `FAIL_WITH_EVIDENCE`
- `HOLD_MISSING_OWNER_EVIDENCE`
- `NOT_TESTABLE_FROM_SUPPLIED_EVIDENCE`

Every result must carry evidence references. Owner assertions are marked separately from retained/provider evidence.

## Evidence classes

| Code | Meaning |
|---|---|
| `BYTE_CUSTODY` | TJLabs retained the exact bytes and digest |
| `OWNER_EXPORT` | Owner supplied an export/artifact; custody and provenance recorded separately |
| `PROVIDER_RECEIPT` | Provider-generated immutable/authoritative receipt supplied or observed |
| `OWNER_ASSERTION` | Named owner statement; never silently upgraded |
| `PUBLIC_FIRST_PARTY` | Public platform/vendor material, useful for capability context only |
| `DISCOVERY_NONCONTROLLING` | Procurement discovery source, not controlling buyer text |

## A. Source population

| Rule family | Required evidence | Acceptance question | Default failure/HOLD |
|---|---|---|---|
| source generation | owner export + generation metadata | Is one exact source generation frozen? | ambiguous/multiple generations |
| artifact custody | inventory + digests where retained | Can every material artifact be identified? | missing artifact reference |
| program population | source counts / object ids | Is admitted program population explicit? | unknown/incomplete population |
| award population | source counts / award ids | Is admitted award population explicit? | unknown/unbounded population |
| subaward/subrecipient | source relationships | Are admitted relationships enumerable? | orphan/unknown relationship |
| reimbursements | request ids + amounts/status | Is admitted reimbursement population explicit? | missing request identity |
| documents | document reference inventory | Are admitted document classes accounted for? | missing/unmapped refs |

## B. Identity preservation

| Rule | Source | Target | Required evidence | Result |
|---|---|---|---|---|
| program id | legacy program key | target program key | mapping + before/after export | pending |
| award id | legacy award key | target award key | mapping + before/after export | pending |
| subaward id | legacy subaward key | target subaward key | mapping + before/after export | pending |
| subrecipient id | legacy party key | target party key | mapping + collision report | pending |
| project/mission id | legacy project key | target project key | mapping where in scope | pending |
| reimbursement id | request/payment reference | target request key | mapping + status evidence | pending |
| amendment/version | source version key | target history/version | before/after history evidence | pending |

No identifier remap may be interpreted as preservation unless the remap is explicitly owner-approved and traceable.

## C. Relationship preservation

Test admitted relationships such as:

- program → funding source;
- program → award;
- award → subaward;
- award/subaward → subrecipient;
- award → amendment/version;
- award/project → reimbursement request;
- reimbursement request → supporting-document refs;
- reimbursement request → approved/payment refs where owner/provider evidence exists;
- award → monitoring/reporting/closeout records.

Each relationship rule must identify expected cardinality and orphan behavior. Aggregate counts alone do not prove relationship preservation.

## D. Lifecycle mapping

For each owner-approved lifecycle state:

| Source state | Target state | Semantic owner | Evidence | Result |
|---|---|---|---|---|
| pending | pending | prime/customer | mapping spec | pending |

Populate one row per admitted source state. Similar names do not establish equivalence; the semantic owner approves mappings.

Required families may include application, review, award, amendment, monitoring, reimbursement, reporting and closeout.

## E. Financial / reimbursement reconciliation

At the agreed evidence depth, reconcile:

- authorized amount;
- award amount;
- amended amount;
- requested reimbursement;
- approved reimbursement;
- payment/disbursement reference supplied by provider/owner where available;
- match/share amount/category;
- cost category;
- program/fund/project allocation;
- fiscal period;
- amount precision/rounding;
- reversal/credit/adjustment semantics;
- cumulative vs incremental values.

A request marked approved does not prove payment. A payment claim requires provider/accounting evidence appropriate to that claim.

## F. FEMA / federal integration seam

For each admitted exchange:

| Scenario | Input evidence | Expected behavior | Output/provider evidence | Result |
|---|---|---|---|---|
| canonical happy path | fixture/export | owner-approved mapping | supplied output/receipt | pending |
| duplicate | duplicate fixture | owner-approved idempotency | output/receipt | pending |
| retry | retry fixture | owner-approved retry semantics | output/receipt | pending |
| invalid identifier | negative fixture | reject/HOLD per contract | output/receipt | pending |
| invalid amount/state | negative fixture | reject/HOLD per contract | output/receipt | pending |
| partial batch | batch fixture | owner-approved partial behavior | output/receipt | pending |

No production federal credential or portal mutation is required or authorized by this matrix.

## G. State / ERP seam

Enumerate owner-approved mappings for:

- fund/program/cost-center/account;
- vendor/subrecipient identity;
- obligation/encumbrance references if applicable;
- reimbursement/payment request identity;
- invoice/payment/status semantics if applicable;
- fiscal periods;
- amount precision;
- reversal/adjustment semantics;
- transaction correlation;
- duplicate/retry handling;
- failed/rejected record handling.

For every scenario retain source evidence, expected behavior, observed output/evidence and terminal result.

## H. Document / attachment migration

Where admitted:

- source document reference exists;
- target document reference exists;
- document type/class maps correctly;
- relationship to program/award/request is preserved;
- byte equality is checked only where both exact byte sets are legitimately available;
- redaction/data-handling rules are preserved;
- inaccessible or restricted documents remain explicit HOLDs.

## I. Audit / activity evidence

Acceptance evidence may check that owner/provider-supplied logs can demonstrate the agreed activity families, such as:

- authentication/session events;
- administrative/configuration changes;
- program/award object changes;
- reimbursement/status changes;
- integration activity/errors;
- document actions;
- user/role changes.

This matrix checks supplied evidence. It does not certify the platform or establish compliance with an external framework.

## J. Cutover rehearsal

Record:

- exact source generation;
- exact mapping/transformation generation;
- exact target/configuration generation supplied by owner;
- preflight outcomes;
- migration start/end checkpoints;
- row/object reconciliation summary;
- interface smoke/acceptance summary;
- financial/reimbursement reconciliation summary;
- unresolved exceptions;
- rollback prerequisites supplied by prime/platform;
- owner readiness decision.

Allowed TJLabs terminal posture: `READY_FOR_OWNER_REVIEW` or `HOLD`. `PRODUCTION_GO` remains owner authority.

## K. Exception row schema

Each exception must carry:

```text
exception_id
rule_id
object_or_population_ref
evidence_refs
observed
expected
evidence_class
severity_or_disposition_owner
next_owner
next_action
closure_evidence_required
state = OPEN | HOLD | RETEST_READY | CLOSED_WITH_EVIDENCE
```

No deadline or narrative closeout removes an unresolved exception.

## L. Delivery-complete matrix gate

The matrix is delivery-complete when:

- all admitted rules have terminal evidence states;
- every FAIL/HOLD is represented in the exception ledger;
- every material conclusion has evidence refs;
- owner assertions remain labeled;
- provider/payment claims use provider/accounting evidence appropriate to the claim;
- source/target generations are explicit;
- integration contracts are owner-approved;
- residual HOLDs are visible;
- commercial/external/production authority remains unchanged.