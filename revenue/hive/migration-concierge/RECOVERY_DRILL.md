# Run the Migration Desk recovery drill

This is a runnable, explicitly synthetic demonstration of the **existing**
Migration Desk and its backup companion. It is not another migration engine or
HTTP server. Run from the product directory with the canonical `intake.py`,
`migrate.py`, `desk.py` and `workspace_backup.py` present:

```sh
python3 recovery_drill.py /private/new-migration-drill
python3 desk.py --database /private/new-migration-drill/recovered/workspace.sqlite3 --assets /private/new-migration-drill/recovered/assets --port 8080
```

Choose a NEW directory. The first command finishes the drill and prints JSON with
`completed: true`, ten completed steps, relative output paths and `start_argv`
for the existing desk. The second command opens the normal local service; the
first does not start a server, browser, external account or background process.

## What to demonstrate

The drill imports two synthetic customers, two linked tasks and one binary file
through real CSV/mapping/plan/apply APIs. A second import replaces only the file.
It then backs up, verifies and restores the workspace, retries the second import
without duplication, rolls that import back to the original file, and marks the
second customer's task done in the recovered workspace. The original workspace
retains the replacement file and the open task, unchanged by the recovery work.

In the recovered desk, open **SYNTHETIC Client One** to download the original
binary attachment; open **SYNTHETIC Client Two** to see the completed task. Import
history has `synthetic-import-1: applied` and `synthetic-import-2: rolled_back`.
Normal edits and the existing workspace ZIP export remain usable. All names,
addresses, task text and file contents are expressly fictitious.

The new directory retains:

- `source-v1/`, `source-v2/`, `plan-v1.json`, `plan-v2.json`: exact original source
  versions and plans, so original operation retries remain demonstrable.
- `original.sqlite3`, `original-assets/`, `before-rollback.zip`: the unaffected
  original workspace and a recovery archive with five records, two runs, six
  journal entries and both attachment versions.
- `recovered/`, `daily-work-export/`, `DRILL.json`: the usable recovered desk,
  current-record data handoff and actual step/source-identity report.

The retained backup can also be restored into another NEW directory to recover
the pre-rollback state independently:

```sh
python3 workspace_backup.py restore /private/new-migration-drill/before-rollback.zip /private/another-recovered-desk
```

The restored active attachment is the replacement version in that second copy.
The first recovered desk and original workspace are not changed.

## Failure and scope

Existing output paths are rejected rather than overwritten. An interrupted drill
leaves `.DRILL_INCOMPLETE`; do not report it as a completed demonstration. Retry
into a new directory and retain existing work. The private, unencrypted backup,
resource limits and incomplete-restore behavior in `BACKUP.md` still apply.
Do not substitute actual customer data into this synthetic fixture generator.

`DRILL.json` records hashes of the actual source files used. It is a local run
report, not a signed certificate or proof of a customer migration. The completion
checks are explicit exceptions, not Python assertions disabled by optimization.
This command executes core/recovery APIs; `http_exercised_by_this_command` is false.

## Executed real-service integration

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_recovery_drill.py
```

Eight new methods passed in 1.447 seconds, with zero skips, in the Linux cloud
container using Python3.13.5. The suite starts RELAY's unchanged `desk.server_for`
on a temporary loopback port and exercises actual HTTP page/records/history,
original-file download, task edit, stale-save rejection, ZIP export and restart.
All servers and connections are closed by the tests. Source hash/report binding,
retained-source retry, another independent restore, no-overwrite behavior and the
actual CLI are covered. The previously accepted 21 recovery methods were not
rerun or counted as new tests. No native-browser, Windows, hosted-CI, live customer,
provider action, email, paid infrastructure or revenue result is claimed.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
