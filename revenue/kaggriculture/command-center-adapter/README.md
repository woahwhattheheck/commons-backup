# TITAN command-center adapter

Dependency-free Python 3 adapter for source, session, VM, artifact, and operation observations. `adapter.json` is the native command center's publication input, with a top-level `sessions` array. The JSON/JSONL interface also retains source and operation observations. Native consumer pin: `54bd539954d67ed82288e0404411c86f6e2fbe7d`, branch `codex/command-center-20260907`; import `integrations.command_center.core.CommandCenter` and schema `integrations/command_center/equipment.py`.

Run from this directory:

```sh
python adapter.py inventory > fleet-observations.jsonl
python adapter.py local-vm --vm-id YOUR_EXISTING_VM_ID > vm-observation.json
python adapter.py snapshot --input fleet-observations.jsonl --as-of 2026-09-07T21:00:00Z
python native_export.py
python -m unittest discover -s . -p 'test_adapter.py' -v
python -m unittest test_native_export -v
python native_compatibility.py --native-directory /path/to/pinned-source/integrations/command_center
```

The Python import interface is `make_record(kind, subject_id, data, observed_at=..., source=..., provider=...)`, `snapshot(records, as_of=..., max_age_seconds=1800)`, and `measure_vm(vm_id, directory='.')`. Load `adapter.py` with `importlib.util.spec_from_file_location` when importing from outside this directory. Schema identifier: `titan.command-center-adapter.v1`.

Each record retains source provenance, the observation timestamp, local recording timestamp, and explicit provider status/event/completion timestamps. Missing facts stay null. Reconciliation uses observation time; delayed old records do not override newer observations. Equal-time conflicts remain ambiguous, and all distinct observations stay in the output. Reingestion does not refresh the evidence timestamp. Freshness describes the observation, not provider liveness.

Operation data accepts `expected_parts` (array or null), `acknowledgments` (`part_id`, `status`), and `reported_status`. Acknowledgment coverage is independent of completion. `provider_completion` describes an explicit terminal provider response with a receipt for the same operation. A board report remains available as `reported_status`; a partial or complete dispatch acknowledgment does not imply provider completion. An outcome may be known while its completion time remains unknown.

The saved catalog contains exact source/thread/session references from the T14 starting board and T08 pins. It does not re-query providers or renew those references' freshness. `local-vm` measures the current Python environment and local filesystem; network reachability remains unknown until supplied as a separate measured observation. This adapter has no lifecycle, spend, credential, shell-control, or game execution API.

`native_export.build_adapter(catalog, vm_observation, generated_at=...)` preserves `gpt-titan-vm` and `claude-titan-vm` IDs, with separate T11/T14 sessions. Only T14 receives the measurement bound to its actual runtime. CPU/RAM session fields describe the host-visible reading; the resource record separately retains cgroup limits. Unknown model/GPU/provider-state fields stay null, and regeneration preserves the original measurement time.

`native_compatibility.py` verifies exact native Git blobs and exercises the actual session parser and merge using temporary SQLite state. Its six checks cover schema acceptance, newer adapter versus older local telemetry, converse precedence, null hardware observations, and unknown timestamps. The pinned consumer selects newer adapter telemetry and retains local notes. The timestamped witness is in `native-compatibility.json`. These checks make zero provider calls and do not repeat the native application suite.

Original adapter code; no third-party runtime dependencies or vendored policy source.

The additive `work_items` export uses `titan.work-items.v1`. Its source catalog is
`work-records.json`: T01–T15 plus the existing GPT/Claude producers and shared
Gemini requests. `work_export.build_work_items(catalog)` returns detached records;
`native_export.build_adapter(..., work_catalog=...)` includes them in `adapter.json`.
Regeneration reads the saved catalog without renewing activity or hardware dates.

Each work item carries `id`, `lane`, `objective`, `owner`, `session_id`,
`session_ref`, `workspace`, `latest_activity_at`, `latest_activity_source`,
`latest_activity_kind`, `activity_summary`, `next_action`, `next_action_source`,
`consumer`, and source/PR/artifact link arrays. `observed_at` is the catalog read
time. `latest_activity_at` dates the sourced execution, publication or handoff;
`activity_freshness(item, as_of=...)` uses that date, never the fetch time.
Unknown timestamps and provider session IDs stay null. A coordination-thread
reference is labeled as such and is not presented as a provider session URL.

Independent `landed`, `selected`, and `hosted` objects have `state`,
`observed_at`, `completed_at`, and `source_ref`. A Slack publication report dates
the status observation; an exact GitHub merge response can also supply completion
time. Owner-reported Gemini completion is separate from a direct provider receipt.
The existing `gpt-t11-vm` identity now describes T15; hardware timestamps remain
unchanged. Gemini adds work records only, with no additional hardware session.

New focused verification only:

```sh
python -m unittest test_work_export -v
```

`work_export.native_source_check(native_directory, document)` checks exact native
core blob `b8a4479fb42c180f95d41cc41f8fff71acbc36a3` from main checkpoint
`2bcdd15bd1822eecb694bebe9a830ee5b3fb4a50`. The saved `work-validation.json`
records actual payload persistence and failed-fetch retention through that native
consumer. Native work presentation and whole-operation ingestion remain with its
builder; the pinned consumer currently retains work items in `sources[].data`.
No native files, existing adapter suites, simulation panels or provider calls are
part of these new compatibility checks.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
