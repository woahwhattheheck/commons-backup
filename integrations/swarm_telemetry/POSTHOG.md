# PostHog operations export

Export a small operational projection from the existing Swarm Telemetry event database into the existing PostHog project. The exporter reads the source database without opening the telemetry `Store`, running migrations, or changing its records. A separate private SQLite journal keeps the source cursor, exact outbound envelopes, attempts, and retention readbacks.

This is an optional consumer. Collection, work execution, provider access, and the existing full-source custody continue independently. No account, plan, schedule, background worker, or mandatory registration is created.

## Prepare retained source records

Run from the repository root with Python 3.10 or later; the exporter uses the standard library. Set the following path variables in the private execution environment to the existing event database and a writable private journal location. Keep these files and their paths out of Git and public posts.

```sh
python3 -m integrations.swarm_telemetry.posthog_export prepare \
  --source-db "$SWARM_TELEMETRY_DB" \
  --journal "$SWARM_POSTHOG_JOURNAL" --limit 100

python3 -m integrations.swarm_telemetry.posthog_export status \
  --journal "$SWARM_POSTHOG_JOURNAL"
```

Repeat `prepare` to continue from the committed source cursor. The journal deduplicates existing source IDs. It retains the original projected envelope rather than reminting identifiers or timestamps during delivery recovery.

## Send through an existing connected binding

Use the currently connected PostHog project and its existing secure credential reference. Observe that project's current ingestion allowance and spending mode before sending; generic pricing or a successful project lookup does not establish remaining no-added-charge capacity. This observation does not change any account or plan.

Create the native handoff from the journal:

```sh
python3 -m integrations.swarm_telemetry.posthog_export batch \
  --journal "$SWARM_POSTHOG_JOURNAL" \
  --project-id "$SWARM_POSTHOG_PROJECT_ID" \
  --output "$SWARM_POSTHOG_BATCH_FILE" --limit 100
```

The file contains the projected batch without an API key. Send its capture payload using the existing binding, preserving each event's `uuid`, `event`, `timestamp`, `distinct_id`, and complete `properties`. A binding that cannot preserve those fields is unsuitable for replay of this batch. Use the direct HTTP command below when its existing credential reference is available.

Output files are created exclusively with private permissions. Choose a new batch or query filename for each handoff, and retain the old packet for its matching readback. Reusing an existing output filename exits with an error instead of overwriting the original packet.

Selected rows become `uncertain` before the file is handed off. A crash between writing the file and sending it therefore cannot silently return those rows to the ordinary pending queue. An HTTP success is also `uncertain` until an exact query confirms retention.

Generate the matching retention query:

```sh
python3 -m integrations.swarm_telemetry.posthog_export query \
  --journal "$SWARM_POSTHOG_JOURNAL" \
  --project-id "$SWARM_POSTHOG_PROJECT_ID" \
  --output "$SWARM_POSTHOG_QUERY_FILE" --limit 100
```

Execute that query in the same existing project, preserving its `force_blocking` refresh mode and exact identifier scope. Retain the complete provider response privately, then reconcile it:

```sh
python3 -m integrations.swarm_telemetry.posthog_export reconcile \
  --journal "$SWARM_POSTHOG_JOURNAL" \
  --query-file "$SWARM_POSTHOG_QUERY_FILE" \
  --response-file "$SWARM_POSTHOG_RESPONSE_FILE"
```

The query reads `event_uuid`, `event`, `timestamp`, `distinct_id`, `source_event_id_sha256`, and `operation_id_sha256`. Only an exact positive match from a known, complete, fresh query marks an envelope `retained`. An empty result is an observation at the query time; it is not proof that an in-flight event can never appear. Cached, partial, asynchronous, erroneous, or unrelated results do not establish successful delivery.

The first outbound operation associates the journal with its destination project. A different destination uses its own journal, keeping source progress and delivery readbacks from being mixed between projects.

## Direct HTTP using existing secure references

The optional commands below read credentials from named environment variables supplied by the secure execution environment. They do not accept a credential value in a command argument, print it, or add it to the journal. Use the correct existing regional or self-hosted endpoints; the capture and query hosts must refer to the same project.

```sh
python3 -m integrations.swarm_telemetry.posthog_export submit \
  --journal "$SWARM_POSTHOG_JOURNAL" \
  --project-id "$SWARM_POSTHOG_PROJECT_ID" \
  --capture-host "$SWARM_POSTHOG_CAPTURE_HOST" \
  --project-key-env SWARM_POSTHOG_PROJECT_KEY --limit 100

python3 -m integrations.swarm_telemetry.posthog_export query-live \
  --journal "$SWARM_POSTHOG_JOURNAL" \
  --project-id "$SWARM_POSTHOG_PROJECT_ID" \
  --query-host "$SWARM_POSTHOG_QUERY_HOST" \
  --query-key-env SWARM_POSTHOG_QUERY_KEY --limit 100
```

`submit` uses the capture `/batch/` endpoint. `query-live` uses `/api/projects/{project_id}/query/` and needs the existing provider credential's query-read capability. Capture acceptance and query retention are separate outcomes. Provider errors remain explicit local outcomes; the exporter does not start a polling or retry loop.

## Resume an interrupted delivery

| Journal state | Meaning | Next action |
| --- | --- | --- |
| `pending` | Prepared locally and never handed to a transport. | Send in a normal batch. |
| `deferred` | Delivery was deferred with a recorded outcome. | Resolve the recorded provider condition, then use the explicit delivery command. |
| `uncertain` | A handoff or send may have reached PostHog. | Query the exact original envelope before any replay. |
| `retained` | A complete query returned the exact expected event. | Continue with unread source records; ordinary batches exclude this row. |

After a fresh, complete reconciliation of an uncertain row, an operator can explicitly request the same envelope again with `batch --replay-uncertain` or `submit --replay-uncertain`. This never happens automatically because a query was empty. The replay consumes that attempt's reconciliation marker and returns the row to `uncertain` before the next handoff; another replay needs a newer reconciliation. Retained rows are excluded.

PostHog deduplication is eventual and requires the same UUID, event name, timestamp, and distinct ID. The exporter keeps all four unchanged and adds no `sent_at` value. An explicit replay can still produce temporary duplicate storage or repeated downstream effects. The journal provides durable recovery and exact positive readback; it does not claim distributed exactly-once delivery or a guaranteed ingestion-visibility deadline.

## Exported data

The capture event is `commons_swarm_operation`. Its distinct ID identifies the operations stream, not a person. `$process_person_profile` is false. Source event IDs and operation IDs are represented by deterministic SHA-256 values; the source mapping remains local.

| Exported property | Source and interpretation |
| --- | --- |
| `source_event_id_sha256` | Stable reference to the retained source event. |
| `operation_id_sha256` | Stable operation reference when the source actually supplies one. |
| `source`, `provider`, `status`, `event_type`, `capability` | Supported operational categories, never free-form source content. |
| `observed_at` | Actual source observation time. The capture timestamp is the recorded occurrence time. |
| `duration_ms`, `latency_ms` | Explicit observed measurements; missing values remain absent. |
| `request_count`, `attempt_count`, `retry_after_seconds`, `cache_hit` | Explicit recorded counts, delay, or cache result. They are not inferred from narrative text. |
| `public_artifact_url` | Only a source artifact explicitly marked public, using a credential-free HTTPS URL without a query string. |

Raw conversations, prompts, bodies, summaries, local paths, account/device/session/peer identifiers, secrets, and the original operation string are not projected. Public Git or Slack output must not include the private journal, source database, outbound files, or credential environment contents. The existing encrypted full-source custody remains the canonical detailed record.

## Operations view

Run [posthog_operations.sql](posthog_operations.sql) as a `HogQLQuery` in the existing project, or save that query as an operations insight. It covers the last seven days, bounds the output to 200 source/provider/capability groups, removes repeated copies of each unchanged event envelope, and then groups events with a shared operation ID.

The view separates known operation IDs from observations that lack one. Completion is the latest recorded status within the selected window. Rate-limit and recovery counts require an explicit corresponding source status. Duration, latency, cache, and request-count summaries use each group's latest available reported value; missing measurements remain unmeasured. Sample-count columns accompany every measurement. The request total is a sum of reported per-group counters, not independent proof of provider billing or total fleet requests.

This view describes retained, eligible observations in the selected window. It does not establish complete fleet coverage, current provider quota, payout, or benchmark comparability. Cross-provider timings can represent different work; use capability and the actual source operation when making a performance decision.

## Provider references

- [Capture and batch API](https://posthog.com/docs/api/capture): payload fields, regional hosts, anonymous events, and invalid-event HTTP-success behavior.
- [Event deduplication](https://posthog.com/docs/data/events#event-deduplication): stable envelope fields and eventual deduplication.
- [Query API modes](https://posthog.com/docs/api/queries): fresh execution, asynchronous results, caching, and query budgets.
- [Supported SQL aggregations](https://posthog.com/docs/sql/aggregations) and [expressions](https://posthog.com/docs/sql/expressions): the operations query's supported functions.
