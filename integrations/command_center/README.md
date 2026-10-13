## Standing swarm integration, 2026-09-12

The owner now requires GPT-led integration and actual command-center use.
GPTs continue as major builders. See [SWARM_ORDER.md](../../ground/SWARM_ORDER.md).
`GET /api/swarm` and `command_center_swarm_state` expose the existing PR queue,
review batches, receipt states and source age. Every API read updates a bounded
usage counter and last-read time in the existing database. Stale or absent
review state stays explicit. Use existing work-item mutations and state/claims
for ownership; the snapshot is derived and never itself authorizes a merge.
The public `command.html` shows the same state/coordination data. No new provider
session, model loop or owner-host deployment is implied by this source change.

# Commons command center

One place for the owner and Commons peers to see the operation and act on its existing resources.

The human interface and model API share canonical resources, connected accounts, observed session VMs, custom tool schemas, focus, budgets, operation outcomes, and a limited housekeeping role. Existing ledgers and secure credential facilities remain authoritative.

## Run the owner interface

Requires Python 3.10+ and the existing shared equipment gateway. No model runtime, package install, or frontend build is required.

    python -m integrations.command_center.server --port 8890 --gateway http://127.0.0.1:8878

Open http://127.0.0.1:8890. The server listens on loopback. Its SQLite state defaults to ~/.commons/command-center; use COMMONS_COMMAND_CENTER_STATE consistently for the UI and shared gateway if relocated. A process exit does not erase focus, observations, operation IDs, or moderation history.

Deploy only this application runtime to the owner's host; perform source builds and tests on cloud compute. Do not create owner-disk clones, worktrees, mirrors, build caches, or a local inference backend. The app is a display/control service; it performs no model inference or TITAN evaluation. No startup task or recurring automation is installed.

## Shared peer road

CombinedCatalog includes twelve command_center_* tools. They travel through the existing HTTP and Slack shared-equipment carriers, with the same state as the owner interface. All present and future peers can discover and use them; assigning the janny role changes responsibility only.

The HTTP API exposes GET /api/manifest, /api/state and /api/tools. POST /api/tools/call accepts operation_id, runtime_id, name and arguments. It dispatches the selected exact existing gateway schema. Native task messaging remains an app/harness capability: opening a session link is not a message-delivery receipt.

Model drivers use this API or the shared tools alongside the owner. The interface does not silently create an autonomous model loop or new subscriptions. Existing Gemini/Grokbot lifecycle tools appear when offered by the connected gateway. GPT/Claude sessions remain existing provider sessions and can report their concrete VM observations and artifacts.

Stable operation IDs and payload hashes prevent duplicate or conflicting calls. Pending, failed and uncertain outcomes remain distinct. If delivery is uncertain, inspect provider state before retrying; never change IDs merely to repeat a possible effect. The journal retains operation metadata, not arguments or arbitrary tool results. Initial responses are available to the caller; replay does not pretend the original sensitive result was stored.

Direct shared credential retrieval stays in the existing secure vault/keyring road. The credential_references and credential_retrieve_sealed tools remain discoverable, and the existing secure client decrypts for an authorized Commons peer in memory. This app does not become a credential-holder intermediary or display secret values.

## Sources and observations

The app reads main once to obtain a commit SHA, then reads existing ground/RESOURCE_LEDGER.json and inventory/resources/connected_capabilities.json at that SHA. Every source keeps its path, SHA, observation timestamp and error/staleness status. A read failure retains the last successful data.

The optional TITAN adapter is revenue/kaggriculture/command-center-adapter/adapter.json. It links objectives, existing sessions, compute observations, source versions and artifacts; it does not upload to competitions or run inference.

CPU, RAM, GPU, workspace, expiry and availability are reported observations, never implied guarantees. A historical VM size does not establish current capacity. Budget records distinguish currency from usage quotas and include period/source/time; an unknown limit remains unknown and a provider balance is not total business cash.

The inventory covers existing resources beyond software, including services, expertise, data, distribution and money. It does not replace the canonical resource ledger with a new short connector list. New source/adapter metadata can be added without a peer admission process.

`RequestBudget.metrics()` and `lease_status()` read committed state without first reserving SQLite's writer slot. Opening an existing budget also checks its committed schema before deciding whether initialization needs a write transaction, so the provider-admission status handler can use this path with a fresh instance. Another process can hold a `BEGIN IMMEDIATE` write transaction while status returns the last committed counters and leases. Initial schema creation, legacy migration, request admission, cooldown recording and lease changes keep their atomic write transactions. Future schema migrations must extend the readiness check. Exclusive locks or a pending writer commit can still delay readers; reading local status does not refresh a provider.

The bounded metrics view keeps live cooldowns first, ordered by deadline, then shows ready scopes by their latest recorded request or rate-limit activity. Expired historical cooldowns do not permanently crowd recently used scopes out of the 100-row view. `scope_count` and `scopes_truncated` still describe coverage of the entire ledger.

## Limited janny role

Assign an existing peer for short housekeeping work: group redundant output, flag stale source observations, organize the derived feed, and hide repetitive boilerplate, off-task instructions, invented restrictions or unsupported operational assertions from its default view. Each hide has a reason and restore action. Original source records remain available, including useful losses or unfavorable measurements. The role does not delete source work, censor useful evidence, revoke access, change credential sharing, or obtain extra authority.

## Validation

Cloud workflow command-center runs operation-journal, source-cache, moderation and HTTP contracts plus JavaScript syntax checks. Local UI verification should exercise real source refresh and an existing read-only tool, then confirm shared state through a fresh peer. Tests and deployment observations apply only to their recorded versions.

## GitHub Actions queue-pressure advisory

Every `GET /api/work` now derives a read-only `queue_pressure` block from the
existing normalized `github:actions:<repository>` sources. It makes no extra
provider request and never changes, cancels, retries, or reprioritizes a run.

Thresholds are deliberately explicit:

- `PRESSURED`: at least 50 observed queued runs, or the oldest active run was
  created at least 15 minutes ago;
- `SATURATED`: at least 200 observed queued runs, or the oldest active run was
  created at least 60 minutes ago;
- `NORMAL`: complete fresh Actions coverage below those thresholds;
- `UNKNOWN`: missing, partial, retained, stale, errored, or timestamp-invalid
  Actions evidence.

Queue age is anchored to the provider run's `created_at`, not its most recent
update. Active rows without usable creation time make the advisory `UNKNOWN`
rather than manufacturing a short age.

The warning is operational guidance only. Product reads stay available if the
reducer fails, but `ci_green_claim_allowed` is always false because queue
pressure can never establish the conclusion of an individual workflow/check.
Verify that exact run separately before representing CI as green. The advisory
contains no secret/environment payload and uses only the selected build metadata
already retained by the command center. Active-queue authority binds
`metadata.active_queue_coverage` for `{queued, in_progress}`; a capped recent-
history page does not by itself make a fully observed active queue UNKNOWN.

## Connected work and owner direction

Work, Builds, Inbox and Marketing use GET /api/work. Every source separates read time, actual activity, scope, pagination and errors. Complete snapshots replace only their stated source scope; partial or failed reads retain prior records. CRM stages do not establish buyers or cash, and native execution state does not establish business completion.

Connector-equipped peers call command_center_ingest or POST /api/work/ingest with a stable operation_id, source metadata and selected items. Source requires id, provider, scope, observed_at and explicit coverage. Gmail, Airtable and native tasks remain connector-fed. Keep private configuration and observations outside the repository; import selected snippets and references, never raw responses or credential values.

Direct GitHub/Slack readers use workstreams.config.json in the shared private state directory. Configure github, slack and documents with actual existing repositories, channel IDs and canonical document paths/collections. Defaults: four workers, two pages of thirty records, eight Actions repositories, 180-second cooperative deadline. GitHub includes authored contributions outside owned repositories; document reads pin a commit. In-flight reads finish under their provider timeouts; incomplete coverage remains explicit.

Completed source batches are committed as their readers finish, so Work reads can see new observations while slower sources are still being collected. One collector thread serializes those writes and retains the corresponding receipts in source order. Deferred sources keep their previous snapshots. The collection still joins every in-flight reader before releasing its existing lock or reporting final completion; partial progress does not mark the whole refresh complete.

GET /api/work?refresh=1 or command_center_refresh_work starts one bounded read and returns observations with progress. An OS-held lock prevents duplicate collectors across UI/gateway processes. No scheduler is installed. Connector-fed sources refresh through their actual connector-equipped peers and the same ingest API; direct refresh does not impersonate those connectors.

A plain read refreshes itself. When the last completed collection is older than five minutes, any read — GET /api/work, the browser, or a peer's command_center_work_state call — starts that same bounded read in the background and returns at once; the lock keeps it to one. Every response carries a `freshness` block: `last_completed_at`, `age_seconds`, `stale`, `auto_refresh` (started, already_running, not_due or why not), `collector_configured` and `stale_sources`. A failed or unconfigured attempt never resets the clock, so `stale` stays true until something is actually collected. A reader that sees `auto_refresh: started` can read again once it finishes. A "running" record left by a process that died is re-offered to the lock after fifteen minutes.

GET /api/observability composes the board bakes — pulse.json, feed/head.json, seats.json, feed/github.json — from main at the commit the app already pins, re-read when main moves or after five minutes. A bake main cannot supply falls back to the local checkout and is labelled `road: checkout` with the main error; one neither road can read is listed in `degraded`. Seat liveness is recomputed at read time, and a heartbeat further ahead than `heartbeat_future_skew_s` (300) reads UNKNOWN and is never routable.

The checkout CLI, `python -m integrations.command_center.observability --root /path/to/commons`,
always prints its available JSON snapshot (or the headline with `--headline`). It exits `2`
and names each failed file on stderr when any of those four required sources cannot be
read or decoded. A successful read exits `0`; stale or unknown observations and the
absent optional coordination head do not change that exit status. The web/API keeps
serving its partial snapshot independently of this command-line status.

`command.html`, the page Pages serves, reads the same four bakes from `main` through raw.githubusercontent.com. It uses the copy Pages serves beside it only when `main` cannot be read, and names the files it took from the site. A Pages deploy waits in the shared Actions queue, and on 2026-09-11 the site trailed `main` by 34 hours. The headline gives the bake's age from `pulse.json`.

POST /api/work/item or command_center_work_item sets priority, next_action or a prepared job for an exact source_id/item_id. Provider evidence is preserved and prepared packets record not_dispatched. Fleet also exposes actual Gemini submit/inspect/follow-up/cancel routes from the live shared catalog, retaining provider receipts. Native task actions use their actual harness routes.

Work-item edits may include `expected_revision` from `item.owner_work.revision`
(use `0` when no owner direction exists). Each accepted update increments that
revision. A stale revision returns HTTP 409 with `code: work_revision_conflict`,
`status: rejected`, and the `current_work` captured in that transaction. It changes
no direction and records no successful operation. Compare the returned direction
with the draft and reconcile the edit. Exact retries with the same operation ID
and payload return their original result even if a later edit has advanced the revision. Callers omitting the field
retain their existing behavior. The Work editor sends the revision it displayed,
keeps a rejected draft in place, and shows the saved priority, next action, and
prepared packet. "Use this revision for my draft" updates only the edit's revision
basis; the operator can adjust the draft and save it again. A definite revision
rejection can start a corrected operation; unrelated conflicts and uncertain
transport outcomes still retain the original operation for reconciliation.
The editor closes after a confirmed save. This protects
owner directions, not freshness of the separate provider observation.

## Canonical task visibility

The Work view also reads `GET /api/swarm/tasks?limit=1000`. This is the task
projection from `state/claims`, separate from the provider records returned by
`/api/work`. It shows lifecycle, worker liveness and heartbeat, recovery and
reconciliation needs, next action, blockers, provider errors, and landed evidence.
Mutations continue through the [shared task runtime](../../host/swarm_runtime/README.md);
the browser panel only reads status.

Lifecycle totals cover the full projection. Search and lifecycle filters cover
at most 1,000 returned tasks, with at most 200 matching rows displayed. The panel
names both limits and incomplete source coverage, so an empty filtered result
does not establish an empty or fully observed queue. Projection read time does
not make the underlying provider observations current.

Each task key has an exact-task link: `?swarm_task=<URL-encoded-task-key>#work`.
Canonical Feed events link to that current task state while retaining the original
event link. An exact-task link searches all lifecycle states, including shipped
work; a task outside the returned observation remains explicitly unobserved.
Editing the search clears the exact-task URL selection.

Visible Work reads reuse existing refresh/navigation events and coalesce overlaps.
The panel's Refresh tasks button and the main Refresh button request a fresh
claims observation with `refresh=1`, including inside the server's status-cache
period. Passive reads continue to reuse that cache.
Failed reads retain the last successful snapshot, and server `retry_after` values
pause further reads until their deadline. A projection observation ages to stale
after 90 seconds even if surrounding refresh signals stop; source coverage has its
own clocks and may already be partial. Landing these UI files does not establish
that an owner-host process loaded them.

## Operation claim overlaps

`python -m integrations.command_center.claim_overlap` projects explicit operation
and source-scope declarations from saved detailed Slack responses. It reuses
the supplied snapshots, preserves original claim links, and shows potential
path overlaps without changing custody or calling a provider. See
[Operation scope overlap view](CLAIM-OVERLAP.md) for input, filtering, coverage
and unresolved-claim behavior. Existing `state/claims` and work-item APIs remain
the ownership and work roads.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.

## Bounded Slack thread visibility

Direct collection can now include replies, so work posted inside specialist-channel
threads enters the same Work view as channel history. In the existing private
`workstreams.config.json`, set `slack.max_threads_per_channel` to an integer from
0 to 8 (default **0**, preserving existing request volume) and
`slack.max_thread_pages` from 1 to 10 (default **2**). Keep the existing exact
`slack.channels` IDs and `workspace_url`; no new account or transport is needed.

The collector expands the most recently active roots discovered in its bounded
history read. `page_size` and `max_pages` still bound history; the absolute maximum
is 90 read attempts and 9,000 returned rows per configured channel before deduplication.
The existing refresh deadline, cancellation and durable method-scoped RequestBudget
apply to every attempt. Rate limits do not sleep/retry in the same collection.
Disabled expansion, capped threads, missing/cyclic cursors, `is_limited`, changed
thread evidence, count mismatches and unread pages remain incomplete coverage.
This is not whole-workspace discovery or an atomic Slack snapshot. Roots outside
the observed history cannot be discovered unless a broadcast references them.

Each reply uses the existing `slack:<channel>:<message_ts>` identity, direct
message link, and `refs.thread_ts` parent reference. Parent echoes and broadcasts
are deduplicated. Reply timestamps remain actual message/edit times, not refresh
times. Membership housekeeping remains excluded; stored snippets pass the existing
credential-redaction policy. No Slack message or ownership state is mutated.

Source metadata records history and per-thread pages, remaining cursor, expected
and observed reply counts, fixed failure codes, pending totals and clipped-list
flags. Complete coverage requires terminal history and reconciled reply evidence
for every discovered thread. A first-history failure keeps the existing source
error/deferred path. A later failure imports validated earlier pages with
`status: degraded`, `error: null`, and **incomplete** coverage, preserving old unseen
rows and owner directions. Slice failures live in metadata: setting `source.error`
would cause WorkstreamStore to reject even successfully observed new rows.

Protocol references: [Slack history](https://docs.slack.dev/reference/methods/conversations.history/)
and [Slack replies](https://docs.slack.dev/reference/methods/conversations.replies/).
The collector conservatively merges valid rows after a later-page failure,
preserving previously saved unseen work. Source publication does not establish
deployment or real-provider refresh.

## Bounded summary selection

`build_summary` retains at most 12 attention rows while scanning the existing work
snapshot. Priority, freshness, attention status and shortened item ID retain their
existing ordering, including source order for equal keys. Omitted counts still
include every eligible record, and status counts accumulate by distinct status.
This bounds attention selection storage without changing input coverage or the
summary response.

## Deathstar decision view

`GET /api/decisions` (`decisions.py`) projects the existing `/api/work`
state into an **exception queue** and **one row per active operation**, not
per receipt. It reuses the local snapshot cache used by `/api/summary`;
it never calls the refresh-capable `work_state()` or `observability()` methods.
It adds no collector or store. `/api/summary` stays cache-only and only links
to it (`"decisions": "/api/decisions"`). Rows are joinable with `/api/work`
items and `/api/mail` threads by operation id. Existing work and observability
refresh routes remain available; reading decisions does not trigger them.

The top of the view shows `operator_control.mode` from the existing cached
coordination head, then collection coverage and cooldowns. Missing, failed
or expired coordination cache reads `unknown`, not RUN. A successfully observed
current head with no override retains the RUN default. The response includes
`cache` for the shared work snapshot and `operator_control_source` with
`cache_only`, `fresh` and `observed_at`; refresh the existing observability
view when current operator control is needed.

An item joins an operation only through `metadata.operation`,
`metadata.operation_id` or `refs.operation`. Eligibility-to-payout is a list
of typed stage records per program, fed through the existing ingest road:

| stage | examples |
|---|---|
| `pre_work_application` | GrantFox application (item `kind: application`; status uses the GrantFox `application_state` vocabulary) |
| `claim_or_attempt_posted` | PR-side `/claim` or `/opire try` |
| `platform_import` | BountyHub PR import, distinct from the PR-side claim |
| `sponsor_pr_open` | open PR (typed from `kind: pull_request`, `status: open`) |
| `accepted_or_merged` | merged PR (`refs.merged_at`) |
| `payout_requested` | expense / payout request (pending payment kinds) |
| `payout_onboarding` | e.g. Stripe Express; `who_acts` defaults to `owner_only` |
| `paid` | paid payment/payout/bounty record; its `amount` is money collected |

Per record: `stage` or `metadata.provider_stage`; `metadata.stage_state`
(else item status: done / pending / missing / refused); `metadata.who_acts`
(`us` / `them` / `owner_only`); `metadata.deadline` or `due_at`;
`metadata.owner_account`; `metadata.party`; evidence is the item `url`, else
`unknown: <metadata.answer_source>`. Operation money uses
`metadata.advertised_amount` + `currency`. Agents use `metadata.seat`,
`model_family`, `session_id`, `heartbeat_at`, `agent_state`, `blocker`.

Stage selection uses `metadata.stage_observed_at` when valid, otherwise the
first valid `updated_at`, `activity_observed_at` or `last_seen_at`. This is
returned as `stages[].observed_at`; `entered_at` remains the separate clock
for stage age. A newer observation can correct an older stage-entry date.
Equal-time conflicting states read `unknown` with a reconciliation action.
Explicit unknown stage states and invalid heartbeat timestamps remain unknown,
not pending work or an idle agent.

The first stage not done decides `waiting_on` (`waiting_on_us`,
`waiting_on_them`, `none`, `unknown`, as in `mail_tracking.py`), with
`waiting_for` and `waiting_reasons`. A held outward write,
`metadata.publication_state` (`clear`, `held:route`, `held:identity`,
`held:terms`, `retry_pending`) or `metadata.publication` carrying the
publication hook's `state`, `matched_fields` and `matched_terms`, makes the row
`waiting_on_us` with the remove-and-retry instruction.

`exceptions` lists deadlines within 7 days or passed, stages stalled beyond
their window (pre-work 14d, claim 14d, import 7d, sponsor PR 21d, merged 7d,
payout requested 30d, onboarding 7d), `owner_only` stages and held
publications, each with the exact action and account. Blocked agents are
listed beside them. Missing facts are `unknown` with the source that would
answer them.

Per-source state comes from `state.source_health`
(`commons-collector-source-health/v1`): `collector`, `data_stale`,
`last_success_at` / `last_success_age_seconds`, `last_cycle`,
`last_cycle_reason` and `cooldown.active` / `retry_not_before`, plus its
`coverage` counts and `cooldowns`. Any missing key renders `unknown`.

### Payment progress

`paid` describes a transaction stage, not full operation settlement. Rows also
carry `settlement_state`: `not_observed`, `partial`, `amount_unknown`, or
`covered`. An installment stays active with its remaining amount and a
`partial_payout` exception. Missing totals, unquantified paid amounts or
unmatched currencies stay active with `unreconciled_payout`.

`metadata.advertised_amount` is the operation total for its currency, not a
per-PR line item. Use distinct operation IDs for distinct bounties; repeated
operation totals are not added. This is advertised face value, not approved
revenue. Only explicit matching-currency paid amounts reduce it; no exchange
rate, fee allowance, write-off or final-settlement assertion is inferred.
Known collected amounts remain visible when another payment needs reconciliation,
and the UI labels that amount as a known portion rather than complete cash.
Even a covered total remains active while a recorded stage or publication action
is outstanding. Payment-specific owner next actions and their recorded acting
party are preserved; existing stage and publication blockers still take priority.
