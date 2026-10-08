# GitHub read-rate coordinator

This is a **read-only** local coordination gateway for cooperating swarm processes that otherwise stampede GitHub with duplicate reads. It was created after live swarm work hit GitHub's secondary rate limiter while several peers were independently reading repository, pull-request, file and search state.

It does not grant, infer or proxy any GitHub write authority. The upstream provider supports `GET` only, targets the fixed `https://api.github.com` origin, rejects redirects, and exposes only the allowlisted routes in `broker.ROUTES`. There is no generic URL, HTTP-method, GraphQL, ref-write, issue-write, PR-write, merge, workflow-dispatch, visibility, billing, secrets, or administration surface.

## What it coordinates

`broker.py` stores only a credential SHA-256 fingerprint, normalized request keys, bounded cached JSON and cooldown metadata in a local SQLite database. Multiple processes sharing that database get:

- request-key singleflight so identical reads have one upstream owner;
- a short cross-process burst fence before distinct calls;
- separate primary `core`, issue/PR `search`, and `code_search` cooldowns;
- a principal-wide `secondary` cooldown when GitHub reports a secondary limit;
- persisted `Retry-After` / `X-RateLimit-Reset` backoff that never shortens an existing cooldown;
- successful final-quota responses preserved while subsequent uncached reads in that primary bucket pause until reset;
- namespace isolation after token rotation and fail-closed blocking after HTTP 401;
- bounded request, response, cache-age and cache-row surfaces;
- no stale cached success when a required refresh fails.

The coordinator is advisory infrastructure for processes that actually route reads through it. It cannot retroactively throttle unrelated clients that bypass the gateway.

GitHub distinguishes [issue/PR search and code-search rate resources](https://docs.github.com/en/rest/rate-limit/rate-limit#about-rate-limits). The local primary buckets are `issue_search` and `code_search`, so an exhausted code-search quota does not pause issue/PR discovery, or vice versa. An existing legacy `search` cooldown remains a floor for both resources until its recorded deadline expires, including late completions from legacy leases; no database rewrite is needed. Restart workers with the updated source to use the split buckets. Secondary cooldowns and the shared burst interval still apply across all routes.

Repository owner and name are normalized to lowercase before request hashing. Case variants therefore share one in-flight read and cached response, matching GitHub's repository identity. File paths, refs, branch names and search text retain their original case.

Issue-list requests also normalize GitHub's [documented defaults](https://docs.github.com/en/rest/issues/issues#list-repository-issues) (`state=open`, `sort=created`, `direction=desc`), so omitted and explicit defaults share the same in-flight read and cache entry.

`issues.list` filters also canonicalize comma-separated `labels` as a conjunctive set: reordered or repeated labels such as `bug,enhancement`, `enhancement,bug` and `bug,enhancement,bug` share a single request key, in-flight lease and cache entry. Individual label spelling and whitespace are preserved, and empty label elements fail locally rather than consuming a provider call. Only this set-like filter is reordered; ref, path, branch and search text remain case-sensitive and unmodified.

Completed cache hits read the block state and cached payload in one SQLite read snapshot without taking the writer slot. JSON decoding follows the end of that snapshot. A miss, an expired entry, or `max_age_seconds=0` uses the existing write transaction and rechecks the current state before granting a lease. Expiry cleanup occurs on that path; retained entries stay bounded by the existing completion limit. A cached observation may precede a concurrent writer's commit, as with any SQLite snapshot.

Lease-acquisition decisions use the time after obtaining SQLite's write transaction, so waiting for another writer does not consume a newly issued lease or admit an expired completion. Completion retains its response-observation timestamp for cached payload freshness and provider Retry-After/reset deadlines, then measures lease expiry and remaining cooldown after the lock wait. JSON serialization and completed-response decoding remain outside the write transaction.

If GitHub sends an HTTP 403 with the unmistakable `API rate limit exceeded` primary-quota message but omits `X-RateLimit-Remaining` and `X-RateLimit-Reset`, the gateway captures a typed **headerless primary** observation (never the raw body). The broker applies its core/search bucket fallback cooldown instead of treating it as an ordinary integration-permission 403 and instantly retrying. Missing reset headers remain missing: this mechanism does **not** fabricate an exhaustion count or reset timestamp, guarantee provider recovery, or automatically retry. A plain `Resource not accessible by integration` remains an access failure, and explicit secondary throttling retains the existing account-wide policy. Gateway and broker must be deployed together for this classification.

When a response reports both secondary throttling and an exhausted primary quota, the coordinator retains both cooldowns. The principal-wide secondary pause follows Retry-After, while the exhausted primary bucket retains the later of Retry-After and its reset deadline. A shorter secondary pause cannot reopen that primary bucket early, including after a process restart or an expired lease completion.

`Retry-After` accepts both integer seconds and an [HTTP-date](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after). Date delays use the response-observation clock, with UTC for the obsolete zone-less HTTP-date form, and round up to the next whole second. Valid Retry-After waits are retained in full, including those longer than one day; malformed values keep the existing fallback. This uses the same persisted cooldowns and does not add retries or polling. Date accuracy depends on the caller's UTC clock.

Following [GitHub’s secondary-limit guidance](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit), repeated headerless secondary failures use a persisted fallback of 60, 120, 240 seconds, doubling up to one hour. Only a failed request admitted after the preceding secondary pause advances that fallback; responses already in flight and repeated completions do not count as another retry. A successful response clears the fallback history only when its request was admitted after the latest secondary deadline. Provider-specified Retry-After values and primary reset floors retain their existing behavior. This state is shared by cooperating processes and survives restarts; no automatic retry or sleeping loop is added.

## Read-only route cooldown status

`status.py` inspects one selected local broker database namespace through a read-only SQLite transaction. It never contacts GitHub and does not inspect, store, or reveal access tokens. The existing `--db`, `--rail`, and `--fingerprint` arguments and all previous JSON status fields are unchanged.

The `uncached_read_routes` field adds one decision for each locally supported request family: `core`, `issue_search`, and `code_search`. Each entry includes a `state`, `blocking_buckets`, `until` (absolute epoch seconds or null), and `remaining_seconds` (integer or null). The deadline is the maximum recorded wait among applicable buckets:

- `core`: core primary quota, secondary limit, and burst spacing.
- `issue_search`: issue-search primary quota, legacy shared `search` floor, secondary limit, and burst spacing.
- `code_search`: code-search primary quota, legacy shared `search` floor, secondary limit, and burst spacing.

`AUTH_BLOCKED` takes precedence when the local namespace has recorded an authentication block, even if a cooldown is also active. Otherwise `COOLDOWN` means at least one applicable persisted deadline remains; `NO_RECORDED_COOLDOWN` means none is recorded at the observation time. A clear local result **does not mean** the provider is healthy, its live quota is sufficient, or a new request will succeed. Both `request_budget` and `provider_health` remain unknown; cached requests and in-flight leases have separate existing fields. This is observational guidance for cooperating readers, never a remote readiness check or permission to bypass throttling.

## Conditional refreshes

Refresh both `broker.py` and `gateway.py` together on the next normal reader restart. Existing `/read` request bodies and response states remain valid; no new service, configuration or manual database migration is needed.

When a successful response supplies an ETag, the next required refresh of that exact request can send `If-None-Match`. A confirmed `304 Not Modified` returns `FETCHED` with `revalidated: true`, the unchanged representation, and the new upstream observation time. `max_age_seconds=0` still makes a real provider request; it does not return stale data or extend freshness without provider confirmation. A changed response returns its new JSON normally. Cache-only hits remain `CACHED`.

Validators persist beside the cache, bound to the credential namespace, normalized request, observation timestamp and serialized-payload digest. Body hashing happens outside SQLite's write transaction. The original four-column cache remains compatible with older processes; an overwritten, expired, evicted or failed entry cannot supply a mismatched validator. Retention remains bounded by the existing 300-second maximum age and cache-row limit. Missing or unusable ETags use an unconditional GET. Existing two-argument provider callables continue working; conditional providers implement `revalidate(route, params, etag)` and identify the actual outgoing validator in `Upstream.validated_etag` on a 304.

Errors never fall back to stale success. An unsolicited 304 without a matching request/body is `UPSTREAM_ERROR`. A 401 invalidates the namespace, and 403/429 quota observations retain the existing cooldown path. Primary exhaustion headers on a 304 also retain their reset floor. Singleflight, request spacing, body limits, lease expiry and secondary backoff remain in force.

[GitHub documents](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#use-conditional-requests) that correctly authorized conditional requests returning 304 do not count against the primary rate limit. This is not permission to poll faster or ignore secondary limits. Only reads routed through this gateway benefit; unrelated native connectors are unchanged.

## Run

Set two independent secrets in the environment:

```text
GITHUB_TOKEN=<read-capable token>
GITHUB_READ_GATEWAY_KEY=<64 lowercase hex chars generated independently of the token>
```

Then start on loopback only:

```bash
python tools/github_read_coordinator/gateway.py \
  --db /private/path/github-read-coordinator.sqlite \
  --expected-login woahwhattheheck \
  --port 8766
```

The gateway authenticates the GitHub token with the read-only `/user` endpoint before serving. It listens on `127.0.0.1` and accepts only authenticated `POST /read` calls to its **local** interface; every upstream GitHub request remains a `GET`.

Example local request body:

```json
{"route":"repo.get","params":{"owner":"woahwhattheheck","repo":"commons"},"max_age_seconds":30}
```

Possible broker states are `FETCHED`, `CACHED`, `BUSY`, `COOLDOWN`, `AUTH_BLOCKED`, `UPSTREAM_ERROR`, and `DISCARDED`. Every envelope includes `provider_write_authority: false`.

For an in-flight duplicate, `BUSY` advises a one-second local cache recheck. The original lease remains active until completion or expiry, so rechecking cannot start another upstream request while its owner is fetching. Provider `COOLDOWN` responses retain their full retry/reset delay.

## Supported upstream reads

- `repo.get`
- `contents.get`
- `pull.get`
- `pull.files`
- `pull.reviews` (GET `/repos/{owner}/{repo}/pulls/{number}/reviews`)
- `pull.comments` (GET `/repos/{owner}/{repo}/pulls/{number}/comments`; inline review comments, **not** issue discussion comments)
- `pull.commits` (GET `/repos/{owner}/{repo}/pulls/{number}/commits`)
- `pulls.list` (GET `/repos/{owner}/{repo}/pulls`; optional `head`, `base`, `state=open|closed|all`, `page=1`, `per_page=30`)
- `commit.get`
- `issues.list`
- `actions.runs`
- `search.issues`
- `search.code`

Parameters are strictly normalized. Repository paths cannot traverse; dynamic URL segments are percent-encoded; query values are generated with `urlencode`; token and arbitrary-URL overrides are impossible by schema.

`pull.reviews`, `pull.comments`, and `pull.commits` use the same `core` bucket, conditional cache, request-key singleflight, secondary/primary cooldowns and bounded `page`/`per_page` defaults as `pull.files` (`1`/`30`, maximum `100` per page). Their PR number must be a positive integer; the provider dispatches a fixed-origin `GET` URL only. `pull.comments` yields review-line comments, not general issue comments. This adds no new GitHub write or external URL authority.

`pulls.list` uses the existing `core` read quota and singleflight/cache/ETag/cooldown policy. Its `head` filter permits a qualified contributor branch such as `woahwhattheheck:sol56/branch`; branch filters reject control characters and malformed path components. The new route is GET-only and neither publishes nor modifies a pull request.

For qualified `head=LOGIN:branch` values, normalization lowercases only the GitHub login (case-insensitive) while preserving the complete branch spelling (Git ref names remain case-sensitive). A login capitalization alias shares its cache key and in-flight lease; `Feat/X` and `feat/X` stay distinct. An unqualified `head=branch` retains its original value. This reduces redundant GitHub reads without changing any credential, URL origin, provider quota, or branch selection.

## Test

From this directory:

```bash
python -m unittest -v test_broker.py test_gateway.py test_kestrel_cooldowns.py
python -O -m unittest -v test_broker.py test_gateway.py test_kestrel_cooldowns.py
python -m py_compile broker.py gateway.py test_broker.py test_gateway.py test_kestrel_cooldowns.py
```

The suite includes real eight-process singleflight, secondary-limit persistence across broker instances, primary bucket isolation, late/stale lease rejection, token-rotation behavior, payload/JSON bounds, path/header injection rejection, fixed-origin/no-redirect checks, and proof that the provider issues `GET` only.

The independent cooldown regressions also cover successful quota exhaustion across broker restarts, retained cached success, both primary-bucket directions, expired-response quota observations without stale payloads, longer existing pauses, missing-reset fallback, both retry/reset floors, exact reset resumption, and ordinary permission errors. These are offline tests with synthetic upstream responses, not a live GitHub load test.

