# Component maintenance interview and decision instrument

**Fictional preparation instrument. No University findings, vendor recommendations or authorization to act.**

## Purpose and participants

Establish how a team identifies its software components, knows when support changes, handles advisories and exceptions, and coordinates maintenance across inherited services. Invite roles through the engagement's already authorized coordination process, not through this tool. Useful perspectives are application maintenance, platform/shared-service operations, security triage and service ownership. Record role titles rather than personal identifiers unless the engagement explicitly requires named accountability.

Begin with: “We are examining how component maintenance decisions are supported and handed off. A missing record is a question to resolve, not a finding about the team's competence. We will distinguish what a document says from what has been demonstrated.”

Use a single recent component change as a walkthrough, then one open advisory or exception, then one inherited/shared dependency. Ask for artifacts that already exist; do not request credentials, live probing, exploit reproduction, production dumps or broad access.

## Inventory and scope

Ask the maintainer to show the inventory entry that identifies the component, exact version, service scope and observation date. What creates that record, and what event makes it stale? How are transitive or inherited components represented? Which inventory is authoritative when build metadata, an application register and platform records disagree?

For an ESS/RIS shared component, ask whether there is one maintenance decision with several affected consumers or separate decisions with distinct versions and owners. Do not merge two components merely because their names match. Preserve distinct version/service evidence until the responsible roles confirm the relationship.

Record component ID, version as supplied, service IDs, inventory locator and date, known coverage limitations and the role responsible for resolving discrepancies. “No component listed” is an inventory coverage question; it is not evidence that the service has no dependencies.

## Support status and planning horizon

Ask for the dated support statement relevant to the exact version and deployment arrangement. Who determines whether ordinary, extended, contractual or inherited support applies? Does the end date include the last supported day? What has changed since the statement was observed? Is the date a vendor lifecycle date, a contractual entitlement or a local maintenance target?

Record the declared state separately from the evidence age. When there is a supported label with no horizon, ask what future event would trigger a maintenance decision. When an old record says unsupported, ask whether a replacement, extension or version change occurred; do not treat the old statement as proof of current state.

Before a real assessment, agree the evidence-age and planning-horizon conventions with the engagement owner. The fixture's 120 and 90 days are demonstration settings, not a prescribed service-level agreement. A date conflict becomes a named reconciliation action with both source references retained.

## Advisory intake, applicability and reported exposure

Choose a supplied advisory record and trace it from intake to disposition. What established that the advisory applies to this component/version? What evidence addresses the actual service context? Who can distinguish an affected component from observed exposure? How are a not-affected statement, a not-observed result and unknown exposure kept separate?

Ask for the intake date, applicability reference, exposure-context reference, responsible role, due date and current disposition. Do not ask the interview participant to demonstrate exploitation. When the record says resolved, identify the dated closure evidence, its scope and what was actually verified. A closure ticket title alone is not the same thing as a verified change.

For an accepted-risk disposition, ask who owns the recorded exception, when it expires, what it covers and what re-review event applies. An exception can change the workflow disposition without making the reported exposure disappear. Expired exceptions, missing owners and unsupported closure claims remain visible follow-up questions.

## Ownership and inherited services

Ask the service owner to describe who makes the maintenance decision, who executes the change, who verifies its outcome and who accepts any exception. These can be different roles. Which team is expected to act when an inherited component crosses its support horizon? Where is that handoff recorded?

For a shared component, walk one change through every listed consumer. What compatibility checks, change windows, rollback preparation and communication are required? Which effort is performed once for the shared component and which is genuinely consumer-specific? Record uncertainty rather than multiplying a single estimate by the number of services.

The instrument's component-level row is a coordination aid, not permission to erase separate work. When real consumers require distinct changes, model distinct components/versions or explain the component-level estimate's scope. Do not let the convenient aggregation hide necessary consumer work.

## Maintenance cadence and effort

Ask what triggers review: a calendar date, a release, a support announcement, an advisory or an inherited-service change. Show a completed example and the record of its next review. Who notices an overdue item when the original maintainer is absent?

For each proposed change, capture low/high person-day bounds, the assumptions behind the bounds, included coordination and testing, excluded work, and the role qualified to revise the estimate. Unknown is an acceptable answer. A known 9–16 day subtotal plus one unknown item is not a complete 9–16 day programme estimate and cannot establish a delivery date or fixed price.

## Decision record

Use the workbook's Decisions tab or copy this record into the engagement's existing tracker. Do not create a competing board.

| Field | Record |
|---|---|
| Component and version | Exact supplied identifier and version; do not normalize silently |
| Service scope | All affected consumers, plus any coverage uncertainty |
| Question or practice gap | Missing evidence, conflicting records, unclear handoff, or planning need |
| Proposed decision | Investigate, Plan, Defer or No change; preparation only |
| Evidence | Locator/ID, observed date, what it supports, and remaining limits |
| Owner role | Role responsible for obtaining evidence or proposing a change |
| Effort | Low/high person-days or UNKNOWN; included/excluded work |
| Review trigger | Proposed date/event and rationale; not a newly scheduled meeting |
| Acceptance authority | Existing authorized role/process; UNKNOWN when not established |
| Disposition rationale | Why this next action fits the evidence; what would change the decision |

Close with: “Here is what the records support, here is what remains unknown, and here are the decisions we are proposing for the existing owner process. Have we mistaken a planning assumption for an established fact, or combined services that should remain separate?”

## Follow-through without premature findings

After the interview, preserve the original supplied input and record any corrections as a new version. Re-run the assessor into a new directory and verify the complete bundle. Review the readable summary alongside the source register; do not promote unsupported claims because the output looks polished.

Every follow-up should name the question, the evidence needed, the role responsible and the next decision. Missing evidence can warrant a request or a maintenance planning action; it does not by itself establish a control failure. Unresolved conflict should stay unresolved in any report or presentation until there is a documented basis to resolve it.

This module's priorities are workflow cues. Before including a recommendation in an engagement report, connect the component evidence to the report's approved observation/recommendation IDs and preserve the original scope, dates, unknown effort and limitations. Do not translate priority 1 into “critical vulnerability,” supported into “secure,” or documented closure into independently authenticated closure.
