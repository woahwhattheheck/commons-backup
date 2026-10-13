# UIOWA-047 interview and evidence guide

Use these prompts to populate the catalog and to understand maintenance practice. They are assessment prompts, not statements about current University practice.

## Purpose and ownership

- What specific behavior or integration is this test dataset intended to exercise?
- Which role is accountable for keeping it useful when requirements or interfaces change?
- Who can decide that the fixture should be retired rather than refreshed?
- If ownership has changed, what record shows the handoff?

Evidence examples: fixture catalog entry, team ownership map, maintenance ticket, repository history, service documentation.

## Refresh and versioning

- What event or cadence triggers refresh?
- When was the fixture last refreshed, and what changed in that refresh?
- Which API/schema/event/model version does it target?
- How do maintainers notice that a current interface has moved beyond the fixture version?
- Can a previous fixture version be recovered when investigating an old test result?

Evidence examples: commit/tag history, refresh job record, schema/version file, release notes, change ticket.

## Boundary cases and representativeness

- Which business-critical or integration boundary cases must this fixture represent?
- Why were those cases chosen?
- What known behaviors are intentionally not represented?
- Has a recent defect or change exposed a missing case?
- Does a passing test establish only fixture behavior, or is it being interpreted more broadly?

Evidence examples: acceptance criteria, defect history, test specifications, contract tests, business-rule documentation.

## Cleanup and retention

- Is the fixture persistent, recreated per run, or temporary?
- What happens when it becomes obsolete?
- What evidence demonstrates cleanup or retirement?
- How long are fixture versions retained and why?
- If data is production-derived, what approved handling/minimization controls apply?

Evidence examples: cleanup logs, lifecycle job, retention configuration, handling reference, decommission ticket.

## Maintenance effort

- How many hours or roles are normally required for a meaningful refresh?
- Which upstream teams or interfaces create dependencies?
- What work is deferred when fixture maintenance competes with delivery?
- Would a smaller generated fixture, shared builder, or contract-level fixture reduce effort without losing needed boundary coverage?

Do not convert effort estimates into a product recommendation. Record assumptions and dependencies.

## Finding discipline

Use the evaluator state as a starting point:

- **EVIDENCED:** corroborate the record before describing a strength.
- **OBSERVED_GAP:** the supplied evidence conflicts with the team's own documented expectation; validate context and impact before making a recommendation.
- **UNKNOWN:** request follow-up evidence or report the uncertainty. Do not lower a score merely because evidence is missing.

A report finding should retain the chain:

**catalog field / artifact → service context → observed evidence → limitation → finding → practical improvement option**
