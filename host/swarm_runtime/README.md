# Commons task runtime

Canonical work is stored on the existing `state/claims` branch in
`holdings/swarm-runtime.json`. It contains source events, consumption cursors,
provider facts, worker activity and operation IDs. The projector derives task
state at read time, so clock-relative ages do not create commits. GitHub
task custody is mirrored into existing `holdings/*.json` records in the same
atomic commit, so old claim readers and the runtime share custody.

The lifecycle is `OPEN → ACTIVE → SHIPPED`, with `BLOCKED`, `SUPERSEDED` and
`ABANDONED` as exceptional terminals. Direct work remains possible. Automatic
dispatch selects canonical open or recoverable work and adds no review stage.

## Use the shared service

Set `COMMONS_SWARM_URL` to the existing command-center base URL and
`COMMONS_SEAT` to the worker name. The CLI also accepts `--url` and `--worker`.
Global options precede the command:

```bash
python host/swarmctl.py status
python host/swarmctl.py status --state ACTIVE --owner MY_SEAT --limit 20
python host/swarmctl.py status --task github:woahwhattheheck/commons:issue:177
python host/swarmctl.py status --task github:woahwhattheheck/commons:issue:177 --context
python host/swarmctl.py sync --max-calls 4
python host/swarmctl.py take github:woahwhattheheck/commons:issue:177 --operation-id take-177-01 --data /tmp/worker.json
python host/swarmctl.py heartbeat --feed-cursor '2026-09-26T12:00:00Z|exact-event-id'
python host/swarmctl.py release github:woahwhattheheck/commons:issue:177 --operation-id release-177-01 --expected-started-at '2026-09-26T12:00:00Z'
python host/swarmctl.py ship github:woahwhattheheck/commons:issue:177 --operation-id ship-177-01
python host/swarmctl.py block github:woahwhattheheck/commons:issue:177 --operation-id block-177-01 --blocker 'Exact provider error' --next-action 'Exact action needed'
python host/swarmctl.py next --operation-id next-02
```

Use real task IDs and consumed cursors. `open` adds a task without taking it;
`abandon` closes unfinished work explicitly. `heartbeat` can omit the task only
when that worker owns exactly one active task. `ship` records a shipment claim;
provider reconciliation supplies the actual merged SHA. It does not merge code.
`release` returns the specified unfinished ACTIVE task to OPEN and releases its
matching legacy holding without marking completion or taking another task. Copy
the task's exact `started_at` from `status` into `--expected-started-at` (or
`expected_started_at` in `--data`/the shared API), and retain it with the same
operation ID for retries. A changed claim generation, another current worker, or
a task that is no longer ACTIVE returns an explicit rejected outcome; it cannot
release newer work. Run `next` separately when ready to take another task.
After a terminal outcome or a collision, the same transaction attempts to take
the next compatible task. The response includes its bounded context bundle.
Status accepts repeated `--state`, exact `--task`/`--owner`, and `--after` with
the returned `next_cursor`. `total` counts all canonical tasks; `matched` counts
the selected filter before pagination. These reads do not refresh providers.
Add `--context` with `--task` to inspect the existing handoff bundle without
acquiring work. The optional `context` result includes up to eight recent
matching retained events, exact source IDs, next action, blocker and known
code/artifact references. It is `null` when the selected task is absent from the
filtered page. The same option is available as `context: true` with `task` in
the shared status tool/POST payload, or `context=1&task=...` on the GET endpoint.
The bundle is bounded retained evidence; the surrounding coverage and provider
observation times still describe any missing or stale source history.
Provider-confirmed shipments also appear once in the existing command-center
feed, even when the worker never wrote a final receipt.

Workers with a saved `holdings/swarm-runtime.json` from `state/claims` can use
the same status filters and pagination without a Git clone or provider request:

```bash
python host/swarmctl.py status --ledger /tmp/swarm-runtime.json --state OPEN --limit 20
python host/swarmctl.py --output /tmp/task-context.json status --ledger /tmp/swarm-runtime.json --task github:woahwhattheheck/commons:issue:177 --context
```

`--ledger` selects the saved input even when `COMMONS_SWARM_URL` is configured.
The result reports `authority=retained_ledger`, its exact `source_ledger_sha256`,
and no live claims tip. Ages are recomputed at read time; original provider
observation times and source coverage remain visible. The reader does not
refresh sources or acquire work. Fetch newer ledger bytes to refresh this view;
combining `--ledger` with `--fresh` returns an error. `--output`, `--task`,
`--owner`, repeated `--state`, and the returned `--after` cursor work normally.

Background `sync` reconciles source events and provider outcomes without taking
new work or renewing a worker's heartbeat. When an active task becomes terminal,
its response may include one advisory `candidates` entry per eligible worker:
`{"worker": "SEAT", "after_task_key": "completed-key", "task": {"task_key": "candidate-key", "...": "bounded context"}}`.
The batch prepares its task rows and current seat census once, using the same
read clock for every worker. An empty batch skips that preparation entirely.
Each task is suggested at most once within that response. Later workers use the
remaining compatible tasks in the existing recovery/priority order; a worker
gets no suggestion if that batch has exhausted its eligible work. The candidate
retains its current task state and ownership; it is not an assignment or
delivery, and another caller may still claim it. The compatibility `assignments`
field remains empty. Actual dispatch and direct `take`/`next`/terminal operations
still acquire the next claim
atomically after fresh reconciliation. Repeated sync alone cannot keep an idle
worker live or reserve work ahead of its execution callback.

After a configured collector cycle completes, the existing ingestion hook also
requests historical provider reconciliation with a maximum of four reads. The
shared provider cache, pacing, retry budget and ingestion lock still apply; a
busy hook leaves the work for a later cycle or explicit sync. Ordinary ingestion
and passive board sync continue to request zero provider reads. No new timer or
worker dispatch is created. `swarm-last-sync.json` includes `provider_calls` for
the completed hook alongside its existing publication/error receipt.

Meaningful claims transactions also publish `holdings/swarm-status.json` beside
the ledger. This bounded read model comes from the same Python projector and
includes the exact ledger's SHA-256 and projection time. It is suitable for a
static operator view; custody decisions still go through the runtime. Merely
aging a lease does not write another snapshot or commit.
The static task panel reads that one bounded branch snapshot through the raw
content CDN and shares its cache across tabs. It does not spend a GitHub REST
request resolving the branch for each reader. The displayed observation time
and ledger digest identify the received snapshot; they do not invent a commit
pin or claim that a cached projection includes newer work.

The existing `POST /api/tools/call` submit path accepts optional top-level
`swarm: {"task_key": "github:owner/repo:issue:177", "worker": "SEAT"}`
metadata for `gemini_submit` and `grokbot_submit`. Omit `task_key` to select next
work. The worker must match the actual submitted peer/seat; `feed_cursor` and
`base_sha` may accompany it. Dispatch uses existing seat liveness and capabilities;
selecting a peer does not renew its heartbeat or advertise new roads. The same
operation journal reserves delivery before taking work, requires published
canonical custody, and adds bounded context to the existing prompt. Collision
routing replaces the original objective with the selected task. Its `swarm`
receipt records the selected key and claim tip. Retried claims and existing
task/worker deliveries return their receipts without another provider launch.

Confirmed worker exits are matched to the dispatch's exact provider request/run
handle in the existing operation journal. Compact observations remain in the
existing command-center feed, including completions that arrive before the
submission receipt. An observer stopping, timing out or losing its connection is
not proof that the remote worker stopped. Worker completion is also not proof
that a task shipped: bounded reconciliation of that exact task checks provider
facts before the next assignment. It reuses the same provider cache and cooldowns.
An unfinished confirmed exit releases only its matching claim generation. A
currently live, available execution road receives another eligible task through
the same dispatch path. The planned child operation survives interruption;
replay reuses its receipt. Failed or cancelled execution, an unconfigured worker,
and provider cooldowns defer continuation without a retry loop. Existing provider
callbacks and event reads drive this path; no additional poller is installed.

`--data` reads JSON metadata. For example, a worker that has actually discovered
these roads can supply:

```json
{"seat":{"roads":["github-git-data","slack"],"model":"actual-model","harness":"actual-harness"},"required_capabilities":["github-publish"],"base_sha":"actual-base-sha"}
```

Reuse the exact `operation_id` and payload after interruption. Reusing an ID with
different content is an error. CLI-generated IDs are printed on stderr; heartbeat
and next defaults include the current minute, so retain an explicit ID for retries
across minute boundaries. Read `published` before treating custody as acquired.
Persisted operation receipts keep known assignment, outcome, error, and request
evidence. Their context references exact event IDs in the retained journal instead
of repeating event bodies; `UNKNOWN` placeholders are omitted. Immediate
and retried operations still return full current context. Context without backing
journal events remains inline, and structured no-assignment results stay intact.

Treat event IDs as opaque references. New operation events use
`swarm-operation-v2:` followed by the full SHA-256 of the exact operation ID's
UTF-8 bytes and the event's role suffix. This keeps caller IDs containing colons
distinct from implicit OPEN, recovery and next-task events. Existing journal
IDs and stored operation receipts remain unchanged; retries keep the original
operation identity and do not emit replacement events.

## Rate limits and deployment

Use one shared `--url` deployment for the fleet. The command-center adapter uses
its existing state directory, provider request budget and collected work snapshot.
Provider refresh adds a process-shared file lock, durable response cache, 60-second
mutable-response TTL, immutable merge and full-commit comparison caching,
paginated timeline progress and bounded task rotation. Comparisons retain only
complete ancestry evidence between two full 40- or 64-character commit hashes;
existing retained comparisons qualify without another provider read. Branch
references keep their 60-second TTL. When a full artifact or PR head SHA equals
the resolved target head, reconciliation uses that branch observation directly.
The evidence cites the branch endpoint and records `target_head_identity` as its
proof method. Differing heads use the pinned comparison lookup, and a changed
target commit selects a new comparison. Symbolic or abbreviated comparisons,
incomplete responses and provider errors retain their existing expiry/retry behavior.
Cache reads use the existing task-key index for only the
requested facts, with at most 500 SQL parameters per batch; a small refresh does
not scan the entire retained cache. A persistent shared client budget permits a burst of four
requests and replenishes one request every three seconds; cache hits are free.
An exhausted shared bucket defers further requests while the rest of the bounded
task window still reconciles reusable cached responses.
These are conservative client settings, not a claim about the provider's quota.
`COMMONS_SWARM_GITHUB_INTERVAL_S` (1–3600) and `COMMONS_SWARM_GITHUB_BURST` (1–20)
configure this policy on the shared service. Provider Retry-After/reset cooldowns
remain authoritative. Saturated callers receive a positive-jitter retry boundary.
Rate-limit deferrals carry retry information; refresh does
not sleep while holding a worker. CLI `--max-calls` accepts 0–20, default 4.

Request continuation stops before the first task that receives no request
because the call or shared pacing budget is spent. A partially served task keeps
its endpoint progress and rotates so other tasks get a turn. Cached responses
still reconcile through the bounded scan after that point. Zero-request refreshes
rotate a separate cache cursor; they do not move request continuation, and paced
positive refreshes do not reset their sweep. Coverage reports these as
`next_after_task_key` and `cache_next_after_task_key`, respectively.
With provider refresh enabled, `sync --max-calls 0` still reconciles reusable
cached responses and reports cache misses without making provider requests.
`sync --cached` disables that refresh path entirely.

Canonical Git pushes also honor an already configured publication capacity in
the same state directory's existing `request-budget.sqlite3`. The store acquires
and renews its publication lease immediately before pushing and releases it on
exit. A capacity or cooldown deferral retains the unpublished proposal and retry
boundary. This does not configure capacity or turn a task claim into publication
permission; unconfigured direct Git roads retain their existing behavior.

Provider refresh and ingestion locks work on Windows and Unix using the same
one-byte `msvcrt` / `flock` pattern as the command center. They release when a
process exits; lock contention and an unavailable lock are reported separately.

`sync --max-calls 0` reconciles reusable provider-cache evidence without making
new provider requests. Cache misses stay deferred; a zero request budget does
not skip retained merge or artifact evidence.

`sync --cached` ingests existing evidence without provider refresh. `status` and
heartbeat do not refresh GitHub REST data. Dispatch and terminal operations may
refresh exact candidate identifiers within a four-call budget; canonical claims
still use git. `status --fresh` refreshes the claims branch, not providers.
Every fresh store read checks the remote claims tip. When that commit is
unchanged, it reuses the isolated cached snapshot without rereading Git objects
or rewriting the cache file after this process has read its Git objects once.
A disk cache alone does not satisfy that first fresh read. A changed tip reloads
the ledger and its holdings; an unavailable remote remains an error, and
mutations keep their fresh-tip check.
`sync --work-snapshot`, `--facts` and `--events` accept saved JSON inputs.

The existing `commons-board` ingest job runs `sync --cached --max-calls 0` after
its feed, seat and GitHub bakes. It uses the job's existing Git write credentials
to reconcile `state/claims`, independently of the command-center host, without
another provider poll. A failed or unpublished sync emits a workflow warning;
the next existing ingest retries without invalidating already-durable intake.

Without `--url`, the CLI uses git and defaults its provider cache to
`swarm-cache` in Git's common directory, shared by linked worktrees;
`--state-dir` overrides that path. Separate VMs with separate
state directories **do not share a global provider budget**. Pointing every worker
at its own local cache defeats fleet request coalescing.

After deploying these files, restart the existing command-center/shared-equipment
runtime so its tool inventory exposes `command_center_swarm_tasks` and the HTTP
surface exposes `POST /api/swarm/tasks`. Existing ingestion updates the projection
through the adapter; explicit `sync` requests bounded provider reconciliation.
No schedule or new worker launcher is installed. Worker `feed_cursor` records an
explicit consumed boundary; `dispatch_cursor` separately records which shared
projection supplied its context, without pretending the worker read every post.

## Native GitHub publication fallback

When using the local git path, `--no-push` returns a publication proposal. If
`COMMONS_SWARM_URL` is set, pass `--url ''` to select that local path:

```bash
python host/swarmctl.py --url '' --no-push --output /tmp/swarm-proposal.json take github:woahwhattheheck/commons:issue:177 --operation-id take-177-01
```

This is **not a claim**. Publish **every entry in `proposal.files`**, including
the ledger and holding mirrors, in one Git Data tree/commit whose parent is
`proposal.base_sha`. Advance `state/claims` without force. If its tip changed,
reload current state and rerun the operation; never publish an old computed
holding over a newer claim. Confirm publication before starting assigned work.
The store retries ref contention at most three times and preserves an unpublished
proposal on a push failure.

The ledger acknowledges the exact revision of each legacy holding it mirrors in
the same transaction. Replaying an operation does not ingest its own mirror as
new activity. A later direct claim change has different content and is still
ingested normally; historical events remain intact.

Terminal task history releases a matching legacy holding only when its dated
closure covers the holding's activity. A newer take or heartbeat is preserved,
even when the worker name matches; missing closure or holding dates leave custody
unchanged. Historical task completion cannot revoke a later direct claim.
Active projections also preserve later take and heartbeat times for the same
holder, so an older task cannot move a renewed claim's generation backward.
An explicit legacy release reopens its matching active task without declaring
completion. Its worker must match, and its dates must cover the current take;
stale releases cannot clear newer work. The next take creates fresh custody.
Sync rereads custody from the exact claims parent on every transaction attempt,
after collected events, so a release during collection cannot be overwritten.
A newer observed legacy claim can also transfer an active task from its former
owner. Its exact repository/key source, revision ID, take generation, heartbeat,
and lease must agree; an ordinary attempted take still collides with live custody.
Fresh seat activity on unrelated work cannot veto an already observed transfer.

## Facts and implementation

Missing values are `UNKNOWN`. Seat liveness is recomputed using `seat_census`
against the reader's clock: LIVE/QUIET retain custody; stale activity becomes
recoverable. Implausible future heartbeats do not renew leases. Provider
observations and actual provider activity have separate timestamps. A known
merged PR lacking a merge SHA remains undispatched pending reconciliation.
Provider observations are ordered by parsed time. A dated refresh can replace
undated baked facts; older or undated refreshes cannot erase a dated observation.
Confirmed merges and landed artifacts take precedence over observation age.
Collectors, sync batches, dispatch refreshes, and canonical-key aliases use the
same fact merge, so later stale inputs cannot erase immutable shipment evidence.
Heartbeat composition, creation-time dispatch order, recent shipments, and
bounded event context likewise compare parsed times. Timezone offsets and
fractional seconds do not reorder custody or displace newer context. Unknown
dates sort after known dates without changing recovery or priority precedence.
Incomplete source coverage stays visible; a newest Slack page is not a complete
work inventory. Publishing capability requires a discovered write road or write
primitive, with discovery, authentication, permission, policy and provider failures
reported distinctly.

Commons ingestion persists Git tree IDs and dirty-file content hashes as its
portable post boundary. Unchanged checkouts do not parse post bodies again;
changed Git paths and exact feed IDs select the next read. A feed gap or missing
prior tree widens to the available local corpus without hidden provider fetches.

| Module | Responsibility |
| --- | --- |
| `identity.py` | Deterministic issue, PR and owner-command keys |
| `sources.py` | Existing feed, work snapshot and legacy-holding ingestion with cursors |
| `projector.py` | Idempotent lifecycle, collisions, leases and provider reconciliation |
| `store.py` | Atomic claims-branch transaction and compatible holding mirrors |
| `providers.py` | Bounded GitHub refresh through existing collector and request budget |
| `routing.py` | Capability/liveness dispatch, bounded breadcrumbs and status |
| `runtime.py` | Operations, mechanical activity and immediate next-task selection |
| `integrations/command_center/swarm_tasks.py` | Existing service/tool adapter and ingestion hook |

Run the actual operation and inspect its output/exit status. This runtime adds no
test suite, hosted-CI prerequisite, review queue or approval queue.
