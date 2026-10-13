# Data-handling interview and tabletop worksheet

**UIOWA-059 — preparation instrument; all worked cases below are fictional.**
Use organizational roles, category labels and controlled evidence locators. Do not
collect raw production data, personal identifiers, passwords or diagnostic dumps.
This is a practice assessment, not a formal compliance audit or employee rating.

## A lifecycle to walk, not a policy checklist

```text
Specific development/support need
  -> purpose + accountable role + classification decision
  -> category-by-category minimization
  -> source and separately inventoried copies
  -> destination/transfer review and operational use
  -> purpose-bound retention decision and review date
  -> disposal OR documented continuing need/exception
  -> same-copy verification after disposition
  -> reconcile derived copies, retained backups and unresolved scope
```

The evaluator does not perform any of these operations. A transfer produces its
own inventory row. A source's removal is not evidence about its children. A
procedure describes expected behavior; an observed record supports only what was
actually observed within its documented scope. Complete capture of every copy is
an interview question, not a property guaranteed by the submitted inventory.

## Facilitation setup

Choose one recent example for each relevant use case: production-derived test
data, diagnostic export, and shared troubleshooting material. Adapt the questions
to the actual team rather than requiring identical tooling. Record the collection
scope and the assessment instant. Ask a service steward, developer/support role,
and destination owner to explain the same copy's lifecycle; involve a records or
privacy specialist only for interpretation questions that require one.

| Interview field | Fill during the assessment |
|---|---|
| Group/service and selected example | UNKNOWN until supplied |
| Why this example represents ordinary work; exclusions | UNKNOWN |
| Accountable organizational role; destination role | UNKNOWN |
| Assessment instant and observed-record period | UNKNOWN |
| Inventory completeness basis and unexamined locations | UNKNOWN |
| Evidence locator; documented/observed basis | UNKNOWN |
| Contradictions and alternative explanations | UNKNOWN |
| Proposed follow-up, dependency, effort range and owner role | UNKNOWN |

## Reusable evidence worksheet

| Practice | Ask for a concrete walkthrough | Metadata/evidence request | Interpretation and next step |
|---|---|---|---|
| Purpose | What specific test/support question needed this copy? | Purpose, requester role, service and issue locator; no issue payload. | Missing purpose limits necessity/retention interpretation; clarify before judging minimization. |
| Classification | Who determined the categories and handling expectations? | Category labels, classification decision, date and accountable role. | A classification label or policy alone is not evidence that handling followed it. |
| Minimization | Which categories were excluded, transformed or retained, and why? | Decision record and scoped sample-review outcome, without values. | A noted omission is a specific evidence gap, not a claim that all exports are unsafe. |
| Transfer | Where did copies go, and which destination became responsible? | One copy ID per location; parent link, transfer review and recipient role. | Reconcile copied attachments and shared workspaces; do not infer they vanished with the source. |
| Retention | What ends the purpose, and when is continuing need reviewed? | Per-copy date, rationale, exception locator and dependency role. | No recorded date is UNKNOWN. Date reached triggers reconciliation, not an automatic breach finding. |
| Disposal | What disposition actually occurred for this copy? | Dated action record, scope/location and operator role; no deletion performed here. | A completed ticket or written procedure may be insufficient without its action scope. |
| Verification | What independently supports the recorded disposition and remaining scope? | Same-copy verification time/outcome, verifier role and excluded backups/copies. | Premature verification cannot substantiate later disposal. Keep partial scope and unresolved copies visible. |
| Ownership continuity | What happens when a contributor or maintainer leaves? | Accepted role responsibility and handoff record. | Evaluate continuity of the workflow, not a person's performance. |

## Worked synthetic tabletop

Run `example.json` through `cli.py`. The fixture has four separately tracked
copies and fifteen fully fictional supporting records. The record names are
locators for this exercise; there are no source documents or University records
behind them.

### ESS: source removed, support copy remains unresolved

`ess-source` represents a minimized test-data extract for a fictional registration
issue. The supplied observations support three base stages and a coherent disposal
on September 14, followed ten minutes later by same-copy verification.
`ess-copy` is a September 5 support handoff from that source. Its retention record
is merely documented; a minimization observation reports a gap. Ownership, its
own retention date, classification observation and transfer observation are absent.

Ask: Is this separately retained copy still required? Who accepted its lifecycle
responsibility? What evidence describes its categories and destination? Could a
purpose-bound continuing need explain separate retention? What is known about
other copies or backups? The tool highlights unresolved copy scope without
assuming the continuing copy is impermissible or deleted.

### RIS: a written expectation and conflicting accounts

`ris-export` represents diagnostic metadata for a fictional research-support
problem. Its purpose, owner and retention date are unrecorded. Classification is
UNKNOWN even though a written classification record exists. Two minimization
observations at the same time disagree.

Ask: Were the observers looking at the same copy and category set? What record
would resolve the disagreement? Does the written document apply to this workflow?
Which role can confirm purpose and review date? Record the disagreement rather
than choosing whichever account produces a stronger rating.

### IAM: verification happened before the recorded action

`iam-diagnostic` represents a fictional sign-in troubleshooting item with no token
or credential values. Base-stage observations are supplied. A September 15
verification precedes a September 16 disposal event. The September 18 review date
has passed at the selected assessment instant.

Ask: Was the verification for an earlier copy or earlier attempt? Is either time
wrong? Does another later record exist? Retain the inconsistent records while
reconciling them. The result is disposal-reported-but-unverified, not a fabricated
claim of completed deletion or failed compliance.

## Practical improvement options

These are discussion options, not prescribed findings. Estimate effort with the
team, avoiding product purchase recommendations or large-tooling assumptions.

| Option | Outcome to seek | Planning assumption | Dependencies and verification |
|---|---|---|---|
| Add accountable role, purpose and review date to the existing support handoff | A retained copy has a usable lifecycle decision, not an orphaned label. | 0.5–2 team-days once; recurring review effort locally estimated. | Source/destination roles, interpretation of existing retention expectations; inspect a later completed handoff. |
| Extend the current copy register with parent and location links | Source disposal no longer obscures separately retained copies. | 1–3 team-days for a bounded workflow; inventory size may change effort. | Destination visibility and transfer workflow; reconcile a sampled source with its destinations. |
| Add same-copy, post-action verification evidence to the existing disposition record | Distinguish performed action, checked result and remaining scope. | 0.5–2 team-days for a bounded workflow. | Operator/verifier roles and backup scope; rehearse a fictional case, then examine an authorized real record later. |
| Record contradictory observations and their resolution explicitly | A favorable account does not erase unresolved contrary evidence. | 0.5–1 team-day to adapt the assessment register. | Evidence IDs, timestamp scope and steward review; demonstrate retained history and a later resolution. |

## Recording findings and disagreement

Write: “In the selected supplied records, [specific observation] was supported by
[IDs/period/scope]; [missing or conflicting evidence] remains unresolved. The
potential operational consequence is [hypothesis with basis]. A proportionate
next step is [option], subject to [dependencies/effort assumptions].”

Do not write: “The University has no policy,” “All exports are unsafe,” “The team
is compliant,” or “Data was deleted” based only on this rehearsal or a metadata
label. Carry strengths as well as gaps, preserve disagreements, and link each
proposed improvement to the record that motivated it.
