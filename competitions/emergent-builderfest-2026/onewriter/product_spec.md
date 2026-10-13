# OneWriter product specification

Status: `SOURCE_CONTRACT / DRAFT_NOT_SUBMITTED`

## User problem

A multi-agent or multi-operator team can have several workers independently notice the same valuable target. A task assignment does not prevent a race: one worker can choose a sales alias while another chooses a founder or partner alias and both can send. OneWriter is the narrow control plane that prevents that class of duplicate external touch.

## Identity model

A writer lane is identified by:

`organization × domain × purpose × opportunity`

`route` is normalized **lease metadata**, not a collision-key field. A live lease therefore blocks another claim for the same organization/opportunity even when the second worker proposes a different email alias, form, DM route, or other contact path.

A provider `SENT` or `BOUNCE` outcome must match the route selected by the current live lease. A genuine human reopen may subsequently permit a new lease with a deliberately selected different route, but that human evidence authorizes **one bounded lease attempt only**. If the human-authorized lease expires unused, the lane returns to the exact prior fence and cannot use ordinary stale recovery; another human event is required before another post-fence action can be leased.

## Primary users

1. **Worker** — proposes a target/route and requests a writer lease.
2. **Coordinator** — sees contested lanes, selected routes, stale leases, hard DNRs, dead routes, and holds.
3. **Evidence reviewer** — inspects transition receipts and retained outcome identifiers.
4. **Business owner** — sees aggregate measured outcomes without exposing private buyer content.

## Screens

### Claim desk
Fields: organization, domain, proposed route, purpose, opportunity, actor/worker id, lease duration (30–1800 seconds), reason.

Before submission, show both the normalized organization-lane identity and the proposed normalized route. Make clear that changing the route does not bypass an existing writer lease.

Typed decisions: `GRANTED`, `DENIED_ACTIVE_LEASE`, `GRANTED_STALE_RECOVERY`, `DENIED_HARD_DNR`, `DENIED_DEAD_ROUTE`, `DENIED_HOLD`, `GRANTED_AFTER_HUMAN_EVENT`.

Never render a Send button.

### Live lanes
Show normalized organization/domain/purpose/opportunity, state, holder, selected route, lease expiry, last transition, receipt digest, and next admissible action. Filters: active, stale/recoverable, DNR, dead route, human reopen, hold.

A normal expired lease is recoverable. A lease created from `HUMAN_EVENT_REOPEN` is different: it carries the prior fence as provenance and automatically returns to that fence when it expires unused.

### Outcome recorder
For a currently leased lane only:
- provider SENT receipt id + the exact leased route;
- provider BOUNCE receipt id + the exact leased route.

Reject the outcome if its normalized route does not equal the route selected by the current lease.

For a fenced lane: retained HUMAN_EVENT evidence id. For a non-leased lane: manual HOLD reason.

The UI must say that SENT means provider acceptance of the outgoing action, not human interest; BOUNCE means route failure, not buyer rejection; route failure does not silently authorize a fallback alias; HUMAN_EVENT requires retained human evidence; and recording an outcome never creates payment, contract, or revenue truth.

### Receipt inspector
Immutable chronological receipts include event id and exact UTC timestamp, actor, collision key, normalized event route, current lane route, prior state, decision, new state, whether an expired human-reopen lease was re-fenced, the canonical normalized accepted-event object, its SHA-256, receipt SHA-256, and `external_send_authorized=false`. The accepted-event object binds the authority-bearing cause: identity, route, actor, kind/time, lease duration, provider receipt, human evidence id, and reason. Allow JSON copy/export.

### Impact dashboard
Compute only from retained receipts: claim attempts/grants, collisions prevented, duplicate touches prevented, stale recoveries, provider sends, dead routes, human reopens, lease latency/duration, and current hard fences. Show **Synthetic Demo** whenever demo data is selected. Show **Measured Business Use** only for a separate real-use workspace.

## Retained identifier contract

Event ids, `provider_receipt`, and `human_evidence_id` are opaque workspace identifiers, not notes. All three use one exact admission contract: **trimmed nonempty text, 1–240 characters, no ASCII control characters, no Unicode category-C codepoints, no non-category-C Default_Ignorable codepoints, and at least one visible base codepoint outside Unicode C/M/Z categories**. Reject whitespace-only, padded, overlong, control/format/private/unassigned, grapheme-joiner, Hangul-filler, variation-selector, other Default_Ignorable-bearing, or combining-mark-only values rather than silently normalizing them. Ordinary combining marks remain admissible when attached to a visible base.

All admitted event/provider/human identifiers share **one workspace uniqueness namespace**. An identifier first used as a provider receipt cannot later masquerade as human evidence; human evidence cannot be recycled as provider evidence; and neither may collide with an event id.

## State transitions

| From | Event | Guard | To | Decision |
|---|---|---|---|---|
| CLEAR | CLAIM(route R) | valid lease | LEASED(R) | GRANTED |
| ordinary LEASED(R1) | CLAIM(route R2) | before expiry, including R1 != R2 | LEASED(R1) | DENIED_ACTIVE_LEASE |
| ordinary LEASED | CLAIM(route R2) | at/after expiry | LEASED(R2) | GRANTED_STALE_RECOVERY |
| LEASED(R) | SENT(route R) | actor=current holder; live lease; admitted unique provider receipt | HARD_DNR | RECORDED_SENT |
| LEASED(R) | SENT/BOUNCE(route != R) | any | unchanged | REJECT / contract error |
| LEASED(R) | BOUNCE(route R) | actor=current holder; live lease; admitted unique provider receipt | DEAD_ROUTE | RECORDED_DEAD_ROUTE |
| HARD_DNR | CLAIM(any route) | always | HARD_DNR | DENIED_HARD_DNR |
| DEAD_ROUTE | CLAIM(any route) | always | DEAD_ROUTE | DENIED_DEAD_ROUTE |
| HOLD | CLAIM(any route) | always | HOLD | DENIED_HOLD |
| HARD_DNR/DEAD_ROUTE/HOLD | HUMAN_EVENT | distinct admitted retained human evidence | HUMAN_EVENT_REOPEN | REOPENED_HUMAN_EVENT |
| HUMAN_EVENT_REOPEN | CLAIM(route R2) | valid lease | LEASED(R2, prior fence retained) | GRANTED_AFTER_HUMAN_EVENT |
| human-reopen LEASED | any later event at/after expiry | one-shot lease expired unused | restore exact prior HARD_DNR/DEAD_ROUTE/HOLD before evaluating event | no stale recovery |
| non-LEASED | HOLD | evidence gap | HOLD | RECORDED_HOLD |

`HOLD` may not silently revoke a live lease. An expired human-authorized lease is not a new source of outreach authority: expiry restores the pre-reopen fence and consumes that human event's one-shot authorization.

## Acceptance criteria

The app is acceptable for business-use rehearsal only if:
1. simultaneous clients racing the same organization lane cannot both receive a live lease;
2. simultaneous claims using **different routes** for that same lane still collide;
3. server/database time, not browser time, controls expiry;
4. lease acquisition is atomic at the persistence layer;
5. collision identity normalization is consistent server-side;
6. route normalization is consistent server-side but route is not used to split the writer lane;
7. provider outcomes verify current holder, live lease, matching leased route, and admitted evidence id;
8. provider SENT creates a hard fence;
9. provider BOUNCE is route failure, never human rejection, and does not auto-authorize fallback outreach;
10. event/provider/human identifiers reject whitespace-only, padded, overlong, ASCII-control, Unicode category-C, non-category-C Default_Ignorable, and combining-mark-only values while admitting ordinary combining Unicode attached to a visible base;
11. human reopen requires a nonempty unique admitted evidence id;
12. after genuine reopen, exactly one bounded lease may select a new route; if it expires unused, the lane returns to its exact prior fence and ordinary stale recovery is forbidden;
13. event ids, provider receipts, and human evidence ids share one workspace uniqueness namespace, including cross-type reuse rejection;
14. all transitions produce immutable receipts with prior/new state, route evidence, and a digest-bound canonical accepted event so changing evidence, lease duration, reason, identity, route, actor, kind, or time changes the receipt;
15. UI cannot perform external sends;
16. demo data is visibly synthetic;
17. dashboard metrics derive from stored receipts, not typed totals;
18. exported authority booleans remain false;
19. concurrent browser tabs are covered by an actual race integration test, not sequential clicks.

## Concurrency implementation requirement

Do not implement "check then insert" in two application calls.

Preferred persistence pattern:
- `lanes` keyed by the organization-lane collision key;
- columns include normalized org/domain/purpose/opportunity plus `leased_route`, holder, lease expiry, state, version, `reopen_from_state`, and `reopen_from_route`;
- atomic transaction / CAS grants an ordinary lease only if row is absent/CLEAR or an ordinary lease is expired; `HUMAN_EVENT_REOPEN` grants one lease while retaining its prior-fence provenance;
- an expired human-reopen lease is atomically restored to its prior fence before any later transition and is not eligible for generic stale recovery;
- the claim writes the selected normalized route in the same transaction;
- provider outcome transaction compares holder and `leased_route` and validates the evidence id before mutation;
- one workspace identifier registry / unique index prevents event/provider/human cross-type reuse after admission;
- transition receipt with canonical accepted-event digest is inserted atomically with state mutation.

For PostgreSQL/Supabase, use a transactional RPC, row lock, or conditional `UPDATE ... WHERE` with unique constraints. Other persistence layers must provide equivalent atomicity.

## Domain normalization

Treat domain as an organization-level routing domain, not a URL origin: parse URL-like input server-side, reject embedded credentials and explicit ports, normalize host case, strip `www.`, path/query/fragment and trailing dot, and canonicalize Unicode hostnames with IDNA. Equivalent host spellings must not split a lane.

## Privacy and authority boundary

Public demo uses synthetic organizations and `.invalid` domains. Real business-use evidence may retain internal receipt identifiers and aggregate counts, but public contest materials must not expose private buyer content without separate clearance. This source contract grants no authority for external send, provider/payment mutation, contract/signature, contest submission, or cash/revenue claims.