# Swarm Product-Lane Collision Preflight v2

Deterministic supplied-evidence compiler for **product/revenue-lane ownership collision review before a fleet TAKE**. It does not query GitHub or Slack and it never grants TAKE, outbound, merge, payment, or revenue authority.

## Why v2 exists

The unmerged v1 donor chain correctly tightened provider/family coverage and same-hit reconciliation, but two independent exact-head reviews found remaining false-authority classes:

1. `candidate.created_at` was caller-authored yet the product described it as an anti-race intent epoch. Backdating that value could make a pre-intent census look post-intent.
2. semantic vocabulary used the same grammar as provider queries, so caller-declared terms such as `repo:irrelevant/empty` or `in:empty-channel` could themselves become GitHub/Slack scope operators while still satisfying an “exact term” check.

v2 closes both classes without inventing an authentication root.

## Truth-narrowed chronology contract

There is intentionally **no candidate creation/intent timestamp** in the v2 input schema. The deterministic compiler has no authenticated provider adapter and therefore cannot establish a trustworthy candidate-intent epoch.

`evaluation_time` is retained only as a caller-declared self-consistency coordinate for supplied search freshness and impossible-future checks. It is emitted as:

- `timeAuthority=CALLER_DECLARED_SELF_CONSISTENCY_ONLY`
- `candidateEpochAuthority=ABSENT_NOT_ESTABLISHED`
- `antiRaceChronologyEstablished=false`
- `providerOriginAuthenticated=false`
- `currentOwnerEstablished=false`
- `takeAuthorized=false`

A clean census returns `CENSUS_CLEAR_CALLER_TIME_UNVERIFIED`, not an anti-race or TAKE authorization. Seats must still re-run live provider/owner checks immediately before a durable TAKE.

Because this is a **pre-TAKE** compiler, any materially-same durable `TAKE`/`CLAIM` found in the supplied census is a `COLLISION`; there is no caller-mintable “later than my intent” exception.

## Provider / semantic-family contract

The code-owned provider universe is exactly:

- `GITHUB_ISSUES`
- `GITHUB_PRS`
- `GITHUB_CODE`
- `SLACK`

Every candidate signature token must anchor exactly one declared semantic family, and every declared synonym term must have one exact search row for every required provider. Missing, non-complete, stale, future, contradictory, or root-mismatched evidence fails closed.

Semantic terms use a deliberately separate grammar from provider search syntax. They may contain lowercase letters, digits, `.`, `_`, and interior `-`; they **cannot** contain `:`, `/`, whitespace, quotes, parentheses, or a leading minus. `and`, `or`, and `not` are reserved. This mechanically prevents a declared term from becoming `repo:`, `org:`, `in:`, `after:`, or analogous provider scope/filter syntax.

Each search `query` must equal exactly one declared semantic term. Combined-AND queries and appended provider qualifiers are rejected.

## Provider-evidence consistency

Each search row is retained-root-bound to its exact provider, family, query, observation time, state, and hits. That retained root is explicitly **integrity-only**; it is not provider authentication.

A `hit_id` is reconciled globally before durable/semantic filtering. If the same id appears with changed URL, creation time, kind, claim state, operation, owner, semantic signature, or evidence digest, status is `UNKNOWN_HOLD`. Identical repeated evidence is allowed and aggregates its evidence origins.

Only GitHub issue/PR or Slack-message evidence explicitly marked `TAKE` or `CLAIM` establishes a collision. Chatter can remain in the census but does not establish ownership.

## Result states

- `COLLISION` — at least one materially-same durable TAKE/CLAIM is present in the supplied census.
- `CENSUS_CLEAR_CALLER_TIME_UNVERIFIED` — the full declared provider/family/term census is internally complete/fresh and contains no durable materially-same carrier, **without** trusted candidate epoch/provider/current-owner authority.
- `UNKNOWN_HOLD` — supplied evidence cannot safely establish either result.

## Bundle and verifier

Compilation emits create-exclusive-compatible leaves:

- `packet.json`
- `review.md`
- `collisions.csv`
- `receipt.json`

The receipt binds the exact other three output leaves. `verify_bundle()` recompiles the semantic result and requires exact bytes for all four leaves.

## Authority ceiling

No provider/network access, Muse election, Slack/Gmail/customer contact, TAKE mutation, merge mutation, contract, payment, savings, revenue, legal, compliance, or procurement authority is created here. Positive output is a supplied-evidence census statement only.
