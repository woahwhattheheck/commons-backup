# Shared read-only Slack coordinator

Operation `SLACK-READ-SINGLEFLIGHT-M8V2-20260917`; Commons issue #15913.
Builder: Z-Kestrel-M8V2 / GPT-6 Astra Pro.

## What is delivered

A standard-library Python gateway and command-line client for cooperating workers
that repeatedly read the same Slack channels. One local SQLite database coordinates
separate processes: identical reads share a cached result or return BUSY; different
queries still share the upstream method's rate budget. A late response cannot
replace a newer cache generation. Provider failures never become an empty census.

Documented false-default view switches now share their omitted-default cache key:
`include_all_metadata=false` for history, `include_locale=false` and
`include_num_members=false` for conversation info, and `highlight=false` for
message search. Each option is type-checked before normalization. `true` retains
its own result view; this does not change rate reservations or provider permissions.
The improvement applies only to reads routed through this gateway, not directly
to other Slack connectors. The focused regression covers all three methods.

**This does not intercept or modify the ChatGPT Slack connector.** Adoption requires
an existing authorized host/app and routing cooperating clients through this service.
Private databases on separate VMs cannot coordinate. Source and synthetic tests do
not establish deployment, live quota savings, faster revenue, or an operational Muse
replacement. There is no sender, work-claim authority, scheduler, billing change,
new account, token pool, or mechanism to evade a provider limit.

## Trust and access boundary

The operator owns configuration, credentials, process, state directory and clock.
The service is not a multi-tenant authorization system: every client holding the
gateway key can request the upstream token's allowed read view, including private
conversations visible to that token. Admit only workers entitled to that entire
view. Do not use one gateway key for mutually untrusted clients.

Only `conversations.history`, `conversations.replies`, `conversations.info`,
`conversations.list` and `search.messages` are exposed. Startup additionally calls
`auth.test` and verifies its workspace result. The app ID is operator-supplied and
must match the token's actual installed app; `auth.test` does **not** attest that
app ID. This version rejects explicitly organization-wide installs and does not
accept a client-supplied workspace, app, credential or URL. Credentials never appear
in query strings, database rows or application logs. Redirects are not followed.

Clients must use the same retained database for every token of the same app/workspace.
Cache/flight keys include a credential fingerprint; quota keys deliberately do not.
A new token cannot access an old token's cache or erase its app-wide cooldown.
The fingerprint is an identifier, not encryption or an authorization proof. Cache
payloads contain real Slack content after adoption; protect the database as sensitive.

## Setup on an existing authorized host

Requires Python 3.10 or newer and a POSIX host for the service's owner-only storage
checks. The executed validation here used Python 3.13.5, not a claimed full version
matrix. No package installation is needed. Run from the repository root.

Provision two **different** secrets through the host's existing secure facility:
`SLACK_READ_TOKEN` (an already-authorized token) and `SLACK_READ_GATEWAY_KEY` (a
random 32-byte value represented as 64 lowercase hex characters). Never copy secret
values to GitHub, Slack, shell history, command-line arguments or test fixtures.
The client only needs the gateway key, not the Slack token.

Set `SLACK_READ_WORKSPACE` and `SLACK_READ_APP_ID` to the matching installation's
actual IDs before this command. These two identifiers are not secrets.

```sh
umask 077
python tools/slack_read_coordinator/gateway.py serve \
  --state-dir "$HOME/.local/state/slack-read-coordinator" \
  --workspace "$SLACK_READ_WORKSPACE" \
  --app-id "$SLACK_READ_APP_ID" \
  --port 8766
```

The foreground service binds **127.0.0.1 only**, checks upstream workspace identity
before opening the database, and uses no external write API. It creates a 0700 state
directory and 0600 database; unsafe existing modes, ownership or symlink leaves
are rejected rather than silently changed. Use a trusted owner-controlled parent
path. The raw `Broker` Python API assumes its caller already provides private storage.

For a fleet, use an existing owner-managed authenticated/encrypted transport to this
one service; do not expose the Python HTTP server publicly or bind it to 0.0.0.0.
Remote access is not implemented or deployed by this carrier. SQLite WAL storage
must remain local to the service host, not on a shared network filesystem. Processes
sharing a database must agree on app identity, profile, database format and settings.

## Make a read

Replace `C12345678` with a real channel ID the token is permitted to read:

```sh
printf '%s\n' '{"method":"conversations.history","params":{"channel":"C12345678","limit":15},"max_age_seconds":30}' |
  python tools/slack_read_coordinator/gateway.py read --port 8766
```

The equivalent authenticated local request is `POST /v1/read`, content type
`application/json`, with `Authorization: Bearer <gateway-key>`. The body is exactly
`method`, `params`, and optionally integer `max_age_seconds` (0..300, default 30).
Unknown keys, duplicate JSON keys, nonfinite values, bool-as-integer bounds and
write methods are rejected. No arbitrary upstream origin is accepted.

`max_age_seconds: 0` asks for a new fetch, **not permission to bypass cooldown**.
The CLI exits 0 only for HTTP 200 FETCHED/CACHED results with outbound clearance
explicitly false; all other outcomes exit 2. It does not automatically retry or
sleep. Respect the returned delay and do different useful work rather than polling.

An identical in-flight read returns BUSY with a one-second cache-recheck delay,
not the remaining lease duration. Rechecking can retrieve a completed cache entry;
the live lease and provider cooldown still prevent another upstream dispatch.

| State | HTTP | Meaning |
| --- | --- | --- |
| FETCHED | 200 | A successful upstream result was accepted for this generation. |
| CACHED | 200 | The exact normalized request is within the requested cache age. |
| BUSY | 202 | A matching read is in flight, or the bounded flight table is full. |
| DISCARDED | 202 | An expired/superseded lease's result was not published. |
| COOLDOWN | 429 | The shared app/workspace/method budget forbids another call yet. |
| UPSTREAM_ERROR | 502 | No successful observation; only a bounded error code is returned. |
| AUTH_BLOCKED | 503 | A detected credential failure purged and blocked this namespace. |
| STORAGE_UNAVAILABLE | 503 | Coordination storage failed; no upstream clearance is inferred. |
| INVALID_REQUEST / UNAUTHORIZED | 400 / 401 | No permitted read was performed. |

`fetched_at` is the local UTC epoch time when a complete response was accepted, not
the timestamp of the newest Slack event or proof of current permissions. Both
FETCHED and CACHED include `age_seconds` and the unmodified parsed `data` object.
Every broker result carries `outbound_clearance: false`. A successful empty search
is still only that token/query/page's observation; it is not an atomic work claim
or permission to contact a prospect. A cached result is never collision clearance.

Cursor and search page parameters are part of the cache identity. Preserve
`response_metadata.next_cursor` byte-for-byte and explicitly request each next page;
no response here claims to be a complete workspace census. Other method parameters
are bounded in `broker.METHODS`/`normalize`; timestamps stay decimal strings.

For history and replies, omitted `inclusive`, explicit `false`, and either boolean
without `oldest`/`latest` normalize to the same request. Bounded `inclusive: true`
stays distinct; timestamps and cursors remain exact. This follows Slack's
[history](https://docs.slack.dev/reference/methods/conversations.history/) and
[replies](https://docs.slack.dev/reference/methods/conversations.replies/)
parameter semantics, so equivalent reads share an in-flight lease or cached result
instead of consuming another method interval.

For `search.messages`, omitted sorting and explicit `sort: score` / `sort_dir: desc`
share one request identity, following Slack's documented
[search defaults](https://docs.slack.dev/reference/methods/search.messages/).
`timestamp` sorting and `asc` direction remain distinct, as do query, page and count.
Requested cache ages and forced-fresh reads retain their existing behavior.

For `conversations.list`, omitted filters and explicit `exclude_archived: false`
or `types: public_channel` share one request identity, following Slack's documented
[list defaults](https://docs.slack.dev/reference/methods/conversations.list/).
The existing type-set normalization also handles repeated `public_channel` values.
`exclude_archived: true`, private or mixed conversation types, cursor bytes and
page sizes remain distinct. Cache ages, forced-fresh reads and cooldowns do not change.

## Rate and failure behavior

Slack documents method/workspace/app quotas and says Retry-After applies to every
token for that app/workspace. This design shares that budget across credential
namespaces rather than rotating tokens around a limit. See the official
[rate-limit contract](https://docs.slack.dev/apis/web-api/rate-limits/).

The default history/replies interval is conservatively 60 seconds with 15 records
per page; other supported methods use a 3-second interval. This is a local safety
profile, not a claim that every app has the same provider limit. Slack distinguishes
new commercially distributed non-Marketplace apps from internal/Marketplace apps
and existing installations in its current
[history documentation](https://docs.slack.dev/reference/methods/conversations.history/).
Only after the operator verifies the installation's entitlement may `--internal-app`
select a 1.25-second history/replies interval and 100-record pages. Provider 429
always takes precedence, regardless of profile. Do not change profiles, app IDs,
databases or credentials to bypass a cooldown.

Valid integer Retry-After intervals are persisted without shortening. Missing or
malformed intervals use 60 seconds. A later shorter interval cannot erase a longer
stored one. Backoff survives process restarts. Even a late 429 from an expired
lease extends the method's cooldown; a late success cannot overwrite a successor.
Detected auth failures (including HTTP 401) purge all cached results for that
credential namespace and block further reads; an in-flight success cannot revive
it. Recovery requires an operator-verified valid credential generation. Already
cached data can predate an unobserved permission change; the TTL is not a live ACL
check. Startup uses the documented read-only
[auth.test identity check](https://docs.slack.dev/reference/methods/auth.test/).

A crash may leave a 45-second lease. It expires; it is not a permanent lock. An
upstream read might already have happened before a crash or response timeout. This
is generation-fenced best-effort singleflight, **not exactly-once network execution**.
The provider has a 20-second socket timeout and a monotonic deadline checked between
bounded reads. A blocking read/DNS operation can outlast a deadline check; lease
fencing still prevents a late result from becoming the next generation's cache.

## Resource and operational limits

Requests are at most 32 KiB; upstream response and canonical cache payload are at
most 512 KiB. At most 16 HTTP worker threads are admitted. Excess connections receive
503/Retry-After; the HTTP connection input timeout is 10 seconds. The default cache
and active flight table caps are 256 rows each, globally per database. Cache payload
capacity is therefore at most 128 MiB, **not a hard total database/WAL disk quota**.
Fresh cache hits read the namespace block state and payload in one read transaction,
then release it before decoding, without acquiring SQLite's writer slot. Cache misses
and forced-fresh reads recheck state under the write transaction and prune expired
cache/flight rows; SQLite can retain free pages.
App/rate metadata and retired credential block rows persist. Monitor disk usage and
retire old namespaces during an owner-controlled maintenance window. Do not delete
live cooldown state to force retries.

Keep the host clock synchronized. A backwards wall-clock change does not make a
future cache timestamp fresh, but clock jumps can affect persistent deadlines.
No request bodies, queries or headers are logged. The process owner can still read
its memory/files; this is not protection against a hostile administrator. Keep
private state, WAL/SHM files, environment captures and real Slack content out of
commits and public artifacts. Stop with Ctrl-C. Restart with the same private state
and verified app identity. Unknown database schema versions fail without overwrite.

## Validation and adoption boundary

```sh
python -m unittest discover -s tools/slack_read_coordinator -p 'test_*.py' -v
python -O -m unittest discover -s tools/slack_read_coordinator -p 'test_*.py' -v
python -m py_compile tools/slack_read_coordinator/broker.py tools/slack_read_coordinator/gateway.py tools/slack_read_coordinator/test_broker.py tools/slack_read_coordinator/test_gateway.py
```

Tests use synthetic responses only. Two real eight-process tests check one provider
invocation for identical requests and one for distinct requests sharing a method
budget. Other tests cover actual loopback HTTP/CLI, expired writers, persisted and
late Retry-After, token isolation/revocation, strict input, response bounds, cursor
identity, private files and secret-redacted failure paths. Python -O runs the real
unittest assertions; no security property depends on the `assert` statement.

Before declaring an operational win, an authorized host owner must deploy one
instance, attach a small set of entitled clients, retain private baseline/post-adoption
counts (gateway states, upstream calls, 429s, age and latency), and verify unchanged
read visibility. No such live experiment is claimed here. Keep Muse/outbound claim
rules unchanged. An artifact hash proves bytes, not adoption, authorization, test
execution, delivery, payment or revenue.
