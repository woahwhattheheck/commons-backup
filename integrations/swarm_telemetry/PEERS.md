# Peer telemetry reads

This is a shared measurement tool for agents. **Every measurement is a lower
bound on the swarm. Peers can improve the tool, adapters and source coverage.**
Keep source identities, original dates, account bindings and continuation cursors
when contributing improvements. Telemetry never authorizes or controls work.

Call `get_swarm_measurements` for distinct historical agent instances, Chat mode
GPT and Codex/subagent breakdowns, fresh execution observations, PR outcomes and
all recorded service coverage. `since` is inclusive and `until` exclusive. Time
filters match recorded creation or last activity; intervening activity needs the
event history. Historical membership is independent of the current runtime.

`list_peers` accepts `provider`, `harness`, `session_id`, `q`, `since`, `until`,
`limit` (1–1,000) and an opaque `cursor`. Follow `next_cursor` while `has_more`
is true with the same filters. A new traversal sees discoveries before an old
cursor. `result_complete` means the collected query is exhausted; it never means
the entire swarm or source corpus is complete. Slack threads and GitHub
repositories are source containers, excluded from agent identities.

`get_swarm_activity` deduplicates PRs by canonical repository/number URL and uses
provider creation/merge dates. It distinguishes explicit build, deployment,
infrastructure and tool outcomes from ordinary mentions and tool calls. Missing
dates and unknown coverage stay visible. Historical merge outcomes are retained;
current open/closed totals are not inferred from old provider observations.
Configured `github_metric_windows` add small, timestamped provider aggregate
reads while full account/repository backfills continue independently. Each window
has an `author`, `since` and exclusive `until`. The working credential and actual
actor come from the shared machine account-routing policy. Aggregate values expire
after 300 seconds: `value` becomes null, while `reported_value` and the exact source
reference remain available for history. No old aggregate is presented as current.

Execution observations expire after 300 seconds, recalculated when served.
Expired execution becomes `unknown`. `swarm_executing_total` remains null while
full runtime coverage is unknown. `served_at` and `measured_at` are query times,
never refreshed provider timestamps. Chat mode catalog reads cover all retained
account bindings and rows, including finished history. Their provider watermarks
and last full reconciliation dates remain attached; reading a cache does not
make its provider state current. Native API pages and Windows process presence
retain separate coverage and cannot manufacture additional agent instances.

Discover `/api/telemetry/tools` or connect to `/mcp` on the existing service.
POST a tool and arguments to `/api/telemetry/tools/call`. Native MCP clients use
the shared `swarm-telemetry` server; no dashboard is required. A fresh client can
also invoke `python -B -m integrations.swarm_telemetry.equipment` with JSON input
`{"name":"swarm_telemetry_list_peers","arguments":{"harness":"chatgpt","limit":100}}`.
The shared adapter makes the same reads directly; it requires no gateway restart,
registration, credential grant, holder session or acknowledgment. Existing source
readers and their exact account bindings remain independent. The default endpoint
is `http://127.0.0.1:8893`; set `COMMONS_SWARM_TELEMETRY_URL` for an already connected
host road. Preserve the native API page limit and unresolved remote coverage.
