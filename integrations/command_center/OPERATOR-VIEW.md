# Offline operator view

Read an existing decision snapshot without opening a dashboard, importing the server, starting collectors, or reading provider accounts. This is a CLI over the existing `commons-deathstar-decisions/v2` result, not another store or decision engine.

From the repository root, using Python 3.10 or later:

```sh
python integrations/command_center/operator_view.py decisions.json
python integrations/command_center/operator_view.py decisions.json --mode blocked --details
python integrations/command_center/operator_view.py decisions.json --mode working --query worker-name
python integrations/command_center/operator_view.py decisions.json --mode merged --limit 10
python integrations/command_center/operator_view.py decisions.json --mode all --operation exact-operation-id --details
python integrations/command_center/operator_view.py decisions.json --mode all --offset 10 --limit 10
python integrations/command_center/operator_view.py decisions.json --mode all --format json
```

The input may be a saved `/api/decisions` response, an existing `/api/summary` response containing a full `decisions` object, or stdin (`-`). A summary containing only the `/api/decisions` link is not a snapshot and is rejected; the reader never follows that link.

## Acquire a current snapshot

The current `/api/decisions` endpoint reads the existing shared work snapshot and coordination cache without starting provider reads or refreshes. Obtain the response from an already-running, authorized cloud command center; do not start a server or collectors just to use this reader. Acquisition is still a separate HTTP request to that service, not an offline action. The CLI itself only consumes the supplied bytes. Other endpoints, including `/api/work`, can refresh providers and are not interchangeable with this cache-only export.

A cache-only request does not make old observations fresh. The endpoint reports unknown operator control when its coordination cache is unavailable or stale. Refresh through the established observability workflow when actual new observations are needed; this CLI does not initiate that workflow.

## Find the next action

`attention` is the default. It includes rows waiting on us, rows with a supplied exception, stalled rows, explicitly blocked agents, and held publications. `blocked` includes only explicit blocked-agent or held-publication evidence. `working` means an agent is **reported active**; its heartbeat age remains visible and the CLI does not verify live execution. `merged` means the supplied row reports at least one merged PR, not that all work landed, a deployment happened, or money was paid. `all` preserves the supplied order of every returned row.

`--operation` is an exact identifier match. `--query` is a case-insensitive substring search over the operation, owner, agents, next action and retained records. These options combine with the mode. `--details` adds source freshness/coverage/cooldown, stage evidence and observation timestamps, and retained record URLs. It does not fetch a URL or a longer transcript.

The text view is intentionally small: operation, state, owner, observed merges, waiting party, next action and workers. Unknown next actions stay unknown. Terminal control characters in source text are made inert. JSON output returns the selected original rows without display rewriting, alongside selection counts, operator control, control-source metadata, projection cache metadata and collection scope.

## Read the limits before acting

The existing producer returns at most 50 active rows. Filtering and pagination operate **only on those saved rows**. The header reports the saved count, reported active count, unavailable active rows, matching rows, remaining page count and upstream omitted exceptions. An empty selection is not evidence that the fleet has no such work. Terminal operations excluded by the upstream producer cannot be recovered by `--mode all`.

The snapshot generation time is not a worker heartbeat or provider observation time. Control freshness and projection cache hit/age/TTL are explicitly labeled **at snapshot**: they describe the saved producer observation, not current live status. Projection cache age is not provider freshness. Stage observation timestamps remain separate from the snapshot generation time. Older inputs without this metadata show unknown rather than invented timestamps. Future or unavailable generation times are labeled rather than converted into fresh evidence. Unknown operator control is not changed to RUN.

The v2 decision contract has no dedicated billed-cost or exact-source-ref fields. They remain unknown rather than being derived from token counts, request counts, advertised amounts, PR counts or titles. Retained record URLs and source identifiers are still available in `--details`; `--format json` preserves the producer's money fields and other row data. This is not a billing or settlement calculator.

## Errors and side effects

The program reads at most 8 MiB from the selected file or stdin and writes only stdout/stderr. It uses the Python standard library; no repository module, subprocess, network client, scheduler, database or collector is imported. The source file is never modified. A shell redirect is the caller's action, not an overwrite feature in this program.

Unreadable input, malformed UTF-8/JSON, duplicate JSON members, non-finite numbers, an unsupported schema, a false `ok`, invalid row collections or duplicate operation identifiers produce a clear diagnostic and exit 2. Successful rendering, including an explicitly empty selection, exits 0. Page limits are 1–50 and offsets are nonnegative. Unknown schema versions are rejected rather than silently reinterpreted.

The decision reducer, collector, server, existing browser table, payment classification and ownership semantics are not replaced by this reader.
