# UIOWA-024 — Editable coverage matrix

**Blank working template.** Copy this document into the approved engagement workspace before entering real data. The public example repository is not a destination for real participant identities, private notes or University artifacts. Every blank/`UNKNOWN` cell is unresolved; none means zero, absence, success or permission.

Use the [sampling field guide](24-sampling-plan.md) for interpretation and [the complete fictional example](worked-selection.md) for a filled version. Markdown tables are deliberately editable without a runtime or spreadsheet dependency. Add rows; retain stable IDs and a short change note rather than silently replacing earlier records.

## A. Frame and round identity

| Field | Working value |
| --- | --- |
| Plan ID / version | `TO_COMPLETE` |
| Author / reviewer roles | `TO_COMPLETE` |
| Planning state | `PROPOSED_NOT_SCHEDULED` |
| Scope interpretation approved by / source | `UNKNOWN` |
| Groups included | `ESS; RIS; IAM` — confirm boundaries |
| Frame locator / version / obtained time | `UNKNOWN` |
| Who nominated the initial roster | `UNKNOWN` |
| Known omissions / concentrated nomination route | `UNKNOWN` |
| Intended event window | `UNKNOWN` |
| Actual available window by source | `UNKNOWN` |
| Evidence freeze date | `NOT_AGREED` |
| Target per group | `6–8 distinct participants`, pending scope confirmation |
| Session capacity / duration / assessor assumptions | `TO_COMPLETE` |
| Availability check source and time | `NOT_CHECKED` |
| Previous version / reason for change | `NONE_RECORDED` |

A planning state must never be changed to scheduled merely because a bundle was selected. Any real calendar action has a separate availability check and authorization path.

## B. Required perspectives and contexts

Replace provisional labels with the group's documented requirements. A label is a requested dimension, not a finding. Record the source for each set and why a dimension matters. Do not omit a difficult dimension merely to improve the coverage count.

| Group | Required role perspectives | Required stacks/data paths | Required delivery patterns | Requirement source and limits |
| --- | --- | --- | --- | --- |
| ESS | `service_owner; implementation; verification; operations; consumer_support; security_identity` — confirm | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` |
| RIS | `service_owner; implementation; verification; operations; consumer_support; security_identity` — confirm | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` |
| IAM | `service_owner; implementation; verification; operations; consumer_support; security_identity` — confirm | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` |

`UNKNOWN` means the required set is not established. An empty set requires an explicit scope decision and rationale; it must not silently convert a coverage calculation to “complete.” Role titles alone do not demonstrate the relevant perspective.

## C. Pseudonymous participant frame

Use one global person ID. The same person may appear in several group rows, but do not invent a new identity for that person in each group. A person can attend repeated bundles without increasing a group's distinct count.

| Person ID | Group | Proposed role perspective | Relevant stack/context | Delivery pattern | Basis and nomination route | Availability / participation state | Limitation or alternate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `PENDING_ESS_01` | ESS | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `NOT_CHECKED` | `UNKNOWN` |
| `PENDING_RIS_01` | RIS | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `NOT_CHECKED` | `UNKNOWN` |
| `PENDING_IAM_01` | IAM | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `NOT_CHECKED` | `UNKNOWN` |

Replace placeholder IDs before counting. Distinguish `PROPOSED`, `NOT_CHECKED`, `DECLINED`, `UNAVAILABLE`, `CONFIRMED_FOR_SEPARATE_INVITATION`, and `PARTICIPATED` in actual records; a combined cell can record a proposed role and unchecked availability separately. Only actual attendance supports a participated count. Confirmed availability is not permission to publish a name.

## D. Proposed session bundles and actual attendance

| Bundle ID | Group | Relative phase | Duration assumption | Proposed person IDs | Planned topic keys | Actual attended IDs / source | Actual topics / notes source | State / unresolved conflict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ESS-B01` | ESS | `TO_AGREE` | `TO_AGREE` | `TO_COMPLETE` | `software; security; deployment; ai` — refine | `NOT_OCCURRED` | `NOT_OCCURRED` | `PROPOSED_NOT_SCHEDULED` |
| `RIS-B01` | RIS | `TO_AGREE` | `TO_AGREE` | `TO_COMPLETE` | `software; security; deployment; ai` — refine | `NOT_OCCURRED` | `NOT_OCCURRED` | `PROPOSED_NOT_SCHEDULED` |
| `IAM-B01` | IAM | `TO_AGREE` | `TO_AGREE` | `TO_COMPLETE` | `software; security; deployment; ai` — refine | `NOT_OCCURRED` | `NOT_OCCURRED` | `PROPOSED_NOT_SCHEDULED` |

Do not infer exact start times from a relative phase. Shared people require a separate conflict/availability check before an invitation. “All four topic keys on the agenda” is not “all four areas assessed.”

## E. Coverage status at each snapshot

Use two snapshots where necessary: **proposed design coverage** and **observed participation coverage**. Do not combine them. A proposed candidate can make the design look covered while actual attendance remains unknown.

| Snapshot / group | Distinct people in group | Target status | Role perspectives represented / missing | Stacks represented / missing | Patterns represented / missing | Planned topics / actually discussed | Limitation / next decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `PROPOSED / ESS` | `NOT_CALCULATED` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN / NOT_OCCURRED` | `TO_COMPLETE` |
| `PROPOSED / RIS` | `NOT_CALCULATED` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN / NOT_OCCURRED` | `TO_COMPLETE` |
| `PROPOSED / IAM` | `NOT_CALCULATED` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN / NOT_OCCURRED` | `TO_COMPLETE` |
| `PARTICIPATED / ESS` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `NOT_APPLICABLE / UNKNOWN` | `No attendance evidence supplied` |
| `PARTICIPATED / RIS` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `NOT_APPLICABLE / UNKNOWN` | `No attendance evidence supplied` |
| `PARTICIPATED / IAM` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `UNKNOWN` | `NOT_APPLICABLE / UNKNOWN` | `No attendance evidence supplied` |

| Whole-round count | Value / basis |
| --- | --- |
| Distinct people across all groups | `UNKNOWN` — union of stable IDs, not a sum of group counts |
| Distinct person-group pairs | `UNKNOWN` |
| Session appearances | `UNKNOWN` — sum of attendance or proposed IDs, consistently labeled |
| Repeated people / groups involved | `UNKNOWN` |
| Session time / assessor-hours / participant-hours | `UNKNOWN` — state duration assumptions and excluded work |
| Weekly bundle limit and exceedances | `UNKNOWN` |

## F. Artifact requests and reviewed support

Do not paste restricted source text here. Reference the approved retained source location and version. Group/topic tags are routing labels, not an automatic assertion of evidence sufficiency.

| Request ID | Group / topic | Question / contrasting case sought | Nominated route | Source locator / version | Event window / export coverage | Access and review state | Supported proposition / limit | Conflict or follow-up ID |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ESS-A01` | ESS / `TO_SET` | `TO_COMPLETE` | `UNKNOWN` | `NOT_RECEIVED` | `UNKNOWN` | `NOT_REQUESTED` | `UNRESOLVED` | `TO_SET` |
| `RIS-A01` | RIS / `TO_SET` | `TO_COMPLETE` | `UNKNOWN` | `NOT_RECEIVED` | `UNKNOWN` | `NOT_REQUESTED` | `UNRESOLVED` | `TO_SET` |
| `IAM-A01` | IAM / `TO_SET` | `TO_COMPLETE` | `UNKNOWN` | `NOT_RECEIVED` | `UNKNOWN` | `NOT_REQUESTED` | `UNRESOLVED` | `TO_SET` |

Suggested review states are `NOT_REQUESTED`, `REQUESTED_UNAVAILABLE`, `RECEIVED_NOT_REVIEWED`, `IN_WINDOW_READ`, `PARTIAL_WINDOW`, `OUTSIDE_WINDOW`, and `CONFLICT_OPEN`. Use an accompanying note where more than one condition applies; a primary state is not a reason to erase a second limitation. `IN_WINDOW_READ` means only that the designated fictional or real record was read in the declared scope, not that the practice is good, the export is complete, or its source has been authenticated.

## G. Targeted expansion and disagreement log

| Follow-up ID | Trigger and affected proposition | Missing perspective/source/window | Retained conflicting references | Proposed next step / role | Capacity or access dependency | Decision / rationale / result reference |
| --- | --- | --- | --- | --- | --- | --- |
| `FU-01` | `TO_COMPLETE` | `UNKNOWN` | `NONE_RECORDED` | `PROPOSED_NOT_DISPATCHED` | `UNKNOWN` | `OPEN` |

Close an item only with a recorded disposition: `ANSWERED_WITH_REFERENCE`, `SCOPE_NARROWED`, `UNAVAILABLE_WITH_LIMIT`, or `CARRYOVER`. These are worksheet dispositions, not workflow automation. A different investigator's account may sharpen a disagreement rather than resolve it; keep both.

## H. Version-change and reporting handoff

| Revision | Change and source | Changed selection / support | Counts before → after | Statements needing recheck | Reviewer / decision |
| --- | --- | --- | --- | --- | --- |
| `v1` | `Initial proposed frame` | `TO_COMPLETE` | `NOT_CALCULATED` | `All` | `PENDING` |

Before handing off, verify every non-unknown count against stable IDs, every represented dimension against its stated basis, and every used proposition against retained evidence and its window. Carry missing requirements, nonresponse, repeated-person involvement and unresolved conflicts into the report. Do not replace unknown entries with zeros just to make a table total.
