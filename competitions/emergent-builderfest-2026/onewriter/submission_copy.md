# Builder Fest submission copy — DRAFT_NOT_SUBMITTED

> **Do not submit this text as-is.** Replace bracketed evidence placeholders only with measured, retained business-use facts.

## Title

OneWriter — stop duplicate outreach before it hits a hot lead

## One-line description

An atomic coordination desk for multi-agent teams: one organization-lane writer gets the lease across aliases, duplicate claimants are stopped, provider outcomes stay route-truthful, and every transition is auditable.

## Problem

Our business uses multiple AI/operator sessions in parallel. Two workers can independently discover the same high-value lead, choose different contact aliases, and send seconds apart. A normal task board does not solve the race. Duplicate outreach looks like spam and can damage the opportunity.

## What OneWriter does

Every planned external touch is normalized into a writer-lane key: **organization × domain × purpose × opportunity**. The proposed route is separately normalized and bound to the lease. Changing `sales@...` to `founder@...` cannot bypass another worker's live lease.

OneWriter also keeps outcomes truthful:
- provider SENT must match the leased route and creates a hard do-not-repeat fence across the organization lane;
- a matching-route bounce is a dead route, not buyer rejection, and does not automatically open a fallback alias;
- stale leases can be recovered after expiry;
- only retained human evidence reopens a bounded next action;
- retained provider/human evidence ids must be exact trimmed nonempty 1–240 character values with no ASCII controls, Unicode category-C codepoints, or non-category-C Default_Ignorable codepoints, and must contain at least one visible base codepoint outside Unicode C/M/Z categories;
- the post-reopen claimant may deliberately select a new route;
- every transition produces an immutable receipt.

The app coordinates. It never sends the message itself.

## Real business use

`[REQUIRED BEFORE SUBMISSION: measured use window]`

`[REQUIRED: number of real workers/agents using the app]`

`[REQUIRED: cross-route and same-route collisions prevented, with denominator/population]`

`[OPTIONAL IF MEASURED: stale lanes recovered, route failures separated, time-to-lease]`

No synthetic-demo number belongs in this section.

## Why it can scale

The same single-writer race appears anywhere several people or agents can act on one external target: sales, partnerships, recruiting, vendor follow-up, support escalation, approvals, and account operations. Organization-scoped collision keys, route-bound leases, atomic acquisition, typed outcome states, and receipt logs are reusable workflow primitives rather than a one-off CRM feature.

## Emergent build

`[REQUIRED: describe the actual Emergent build choices used in the deployed app—database, atomic lease mechanism, cross-route race test, UI screens, deployment iteration, and any Emergent-native features. Do not invent.]`

## Demo flow

1. Alpha claims a synthetic hot lead through one alias.
2. Beta claims the same organization/opportunity through a different alias three seconds later.
3. One gets `GRANTED`; the other gets `DENIED_ACTIVE_LEASE` with the same collision key.
4. A provider outcome on the wrong route is rejected.
5. The winning writer records SENT on its leased route; the lane becomes `HARD_DNR`.
6. Another alias is blocked.
7. Retained human evidence reopens exactly one next action, which can choose a new route explicitly.
8. A second synthetic lane shows stale recovery and route failure becoming `DEAD_ROUTE`, not rejection.
9. The dashboard recomputes receipt-backed metrics live.

## Evidence / privacy

The public demo uses synthetic organizations and `.invalid` routes. Private buyer content is not exposed. Real-use contest claims must be aggregate and receipt-backed.

## Submission-state checklist

- [ ] working Emergent app deployed
- [ ] true cross-route concurrent race test passed
- [ ] used in the real business
- [ ] measured impact packet complete
- [ ] privacy review complete
- [ ] no other active team/participant submission conflicts
- [ ] final title/description checked
- [ ] submission action intentionally performed
- [ ] confirmation email received
- [ ] platform status reads Submitted

Until all boxes through actual submission are complete, state is `DRAFT_NOT_SUBMITTED`.
