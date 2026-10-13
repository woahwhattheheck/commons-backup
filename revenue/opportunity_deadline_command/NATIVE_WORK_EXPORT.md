# Native Work export for deadline review

This exporter turns the existing deadline engine's result into selected metadata for `WorkstreamStore`. It creates a local JSON payload; it does not ingest into a running command center, call providers, schedule work, send messages, or change a calendar.

Lineage: [Commons #13799](https://github.com/woahwhattheheck/commons/issues/13799), original product/engine **Z-CobaltForge / ZCF-C8V4**; retained exporter and usage-note donor **Z-Lantern-915-L8Q2**, originally handed to **Z-Cairn-0915-S8R2** for recovery. The whole-product recovery later landed through [#14885](https://github.com/woahwhattheheck/commons/pull/14885), finalized by **Z-RheniumCauseway-1000-Q4M8**. The exporter is recovered from commit `70b31a59de52db9cd6f7270415cb9a0fedf1581a` and uses the current engine and native store.

## Prepare a saved snapshot

Run from the Commons checkout root. The examples below use relative input and fresh local output/state paths beneath that root. Save the existing input and policy JSON blocks in [README.md](README.md) unchanged as `opportunities.json` and `policy.json`, or use your own retained records following that contract. The README example is illustrative supplied data, not verified buyer evidence. Its September 13 source capture is stale under its seven-day policy when evaluated on October 3, 2026; the unchanged example therefore produces `SOURCE_RECOVERY_REQUIRED` at that time. Do not relabel old capture times as fresh evidence.

```sh
python -m revenue.opportunity_deadline_command.work_snapshot \
  --input opportunities.json \
  --policy policy.json \
  --portfolio-ref public-pursuits \
  --snapshot-out deadline-work.json
```

The command reads bounded ordinary UTF-8 files, samples process UTC, compiles the current engine, and creates one new output file. It refuses overwrite; the output parent must already exist. Success prints `operation_id` and exits `0`; an input/output contract error prints an error to stderr and exits `2`. There is no caller-supplied evaluation-time option.

Keep `deadline-work.json` unchanged after an uncertain ingest result. Delivering that same payload again is a retry. Recompiling creates a newly evaluated observation and may change its operation identity, classification, and freshness budget.

## Local ingest, retry, and owner direction

The following is a local operator workflow using a new SQLite state directory. It does not use the running application's state directory or HTTP endpoint. The required runtime files are:

- `revenue/opportunity_deadline_command/{__init__.py,engine.py,work_snapshot.py}`
- `integrations/command_center/{__init__.py,schema.py,workstreams.py}`

These imports use Python's standard library, including SQLite. No command-center server, collectors, catalog, or provider configuration is needed. The repository's `revenue` and `integrations` parent directories work as namespace packages when the checkout root is on the import path.

After exporting the unchanged README sample, run this from the same working directory. Choose a new state-directory name for a separate demonstration; `mkdir` below deliberately refuses an existing directory.

```sh
python - <<'PY'
import json
import time
from pathlib import Path

from integrations.command_center.workstreams import WorkstreamStore
from revenue.opportunity_deadline_command.engine import read_bounded_json
from revenue.opportunity_deadline_command.work_snapshot import build_work_snapshot

snapshot = json.loads(Path("deadline-work.json").read_text(encoding="utf-8"))
raw_input = read_bounded_json("opportunities.json")
policy = read_bounded_json("policy.json")
portfolio_ref = snapshot["source"]["scope"]["portfolio_ref"]
source_id = snapshot["source"]["id"]

state_dir = Path("local-deadline-state")
state_dir.mkdir()
store = WorkstreamStore(state_dir)
print("ingest", json.dumps(store.ingest(snapshot), sort_keys=True))
print("retry", json.dumps(store.ingest(snapshot), sort_keys=True))

item = next(row for row in store.state()["items"]
            if row["source_id"] == source_id)
revision = (item["owner_work"] or {}).get("revision", 0)
direction = store.update_work({
    "operation_id": "owner-direction:" + snapshot["operation_id"],
    "source_id": source_id,
    "item_id": item["id"],
    "expected_revision": revision,
    "priority": "urgent",
    "next_action": "Review retained source evidence with the pursuit owner.",
})
print("owner direction", json.dumps(direction, sort_keys=True))

empty_selection = {**raw_input, "opportunities": []}
time.sleep(1)
partial = build_work_snapshot(empty_selection, policy, portfolio_ref=portfolio_ref)
print("empty partial refresh", json.dumps(store.ingest(partial), sort_keys=True))
print("retained items", json.dumps(store.state()["items"], sort_keys=True))

time.sleep(1)
reinclude = build_work_snapshot(raw_input, policy, portfolio_ref=portfolio_ref)
print("reinclude", json.dumps(store.ingest(reinclude), sort_keys=True))
print("current state", json.dumps(store.state(), sort_keys=True))
PY
```

The one-second pauses let separate refreshes use a later process-clock second. Recompiling identical inputs during the same second can reproduce the same payload and operation ID; that is an identical observation, not a forced new refresh.

The retained README sample was exercised locally at `2026-10-03T10:08:45Z`. It produced `SOURCE_RECOVERY_REQUIRED` with `STALE_OFFICIAL_SOURCE`, preserving the original September 13 capture. Initial ingest received one row; unchanged retry returned `replayed: true`; native counts were `work_items: 0` and `control_rows: 1`. Owner direction at revision `1` survived an empty partial refresh (`received: 0`, `removed: 0`, `retained: 1`), reinclude (`received: 1`, `changed: 1`, `removed: 0`), and reopen. Ordinary commands exited `0`. Reusing the export filename exited `2` and preserved its existing bytes. This records a local workflow, not live ingestion or deployment.

Reopening the same local directory through `WorkstreamStore(state_dir).state()` reads its retained state. For later owner edits, read `owner_work.revision`, send it as `expected_revision`, and use a new operation ID. A stale revision raises `WorkRevisionConflict` with the saved direction in `.work`; compare before editing again. An identical operation retry returns its original result even if later work has advanced. Reusing an operation ID with different content is rejected.

## Partial coverage, freshness, and authority

Source identity is `opportunity-deadlines:<portfolio-ref>`. Keep that reference stable for the same selection scope; use a distinct source ID for a different scope. All snapshots declare `coverage.complete: false`. Omitted records remain retained with their earlier item metadata; a new source-level observation does not re-evaluate those omitted records. Inspect each item's `metadata.evaluated_at` and source coverage when interpreting freshness.

`observed_at` means queue computation, not buyer-source capture or human activity. The original controlling-source capture remains in item metadata. The freshness budget is at most 300 seconds and can become shorter before a known classification boundary. The native store marks age stale when it exceeds that budget. A new computation cannot refresh stale underlying source evidence.

The exporter preserves engine classifications. A fresh, complete, otherwise actionable record with no declared deadlines remains `SOURCE_RECOVERY_REQUIRED` with `NO_DECLARED_DEADLINE`, `due_at: null`, and `needs_attention: true`. It requests recovery of the missing date and infers no closed window. `EXPIRED` requires declared deadlines with none still in the future after the source-quality checks. Explicit owner `NO_BID` and route `HOLD`/`UNKNOWN` retain their earlier dispositions. Terminal states receive `needs_attention: false` under the retained mapping. To correct a previously imported undated row, export and ingest a new snapshot; retrying its older saved payload replays that earlier observation.

Records are selected metadata, with `control: true`, `countable: false`, and no proposed provider actions. Source refreshes update imported metadata without replacing separately saved owner direction. The native store applies its own metadata bounds and credential redaction/refusal; engine acceptance alone does not bypass those checks. Keep opaque identifiers and review text free of credentials.

An existing authorized collector can later deliver a saved payload through the existing native ingest route. That is a separate action from this local workflow. Authority labels and hashes remain upstream declarations, not authenticated buyer facts. No contact, registration, submission, signature, spending, payment, award, or revenue authority is created.
