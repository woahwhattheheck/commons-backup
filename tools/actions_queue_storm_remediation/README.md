# Actions Queue-Storm Remediation

Identity: `Z-ZephyrFoundry-0047-L6N2`  
Model: GPT-5.6 Sol Pro  
Prepared: 2026-09-14

## What this fixes

The observed GitHub emails were not test failures. The sampled jobs acquired no
runner (`runner_id = 0`) and executed zero steps. Fleet coordination then
confirmed the primary cause: Actions budget **$10 / $10 exhausted with “Stop
usage” enabled**. At the latest census, three private repositories alone
contained **802 queued workflow runs**:

- `woahwhattheheck/smb-showcase-inventory`: 742
- `woahwhattheheck/pack-market`: 29
- `woahwhattheheck/motel-ops-suite`: 31

Many product workflows declare both `push` and `pull_request`, but their `push`
trigger has no branch restriction. When a feature branch merges/rebases a
fast-moving `main`, every path imported by that sync can launch another workflow
copy in addition to PR CI. Matrix jobs multiply the pressure.

## Files

- `actions_queue_storm_fix.py` — scans workflow YAML and adds
  `branches: [main]` to unrestricted `push` triggers when the workflow also has
  `pull_request`. Defaults to read-only check mode.
- `github_workflow_fleet_audit.py` — GET-only GitHub Contents API auditor;
  enumerates every workflow, pins blob and byte hashes, classifies trigger
  semantics, and emits per-repository patches plus JSON receipts.
- `cancel_superseded_queued_runs.py` — cancels only queued runs proven obsolete
  by a closed PR, a moved PR head, or (opt-in) an exact duplicate. Defaults to
  dry-run.
- `test_actions_queue_storm_fix.py` — dependency-free workflow-rewriter tests.
- `test_cancel_superseded_queued_runs.py` — dependency-free cancellation
  classifier tests.
- `CURRENT_STATE.md` / `queue_snapshot.json` — current entitlement and queue
  receipts.
- `incident_report.md` — exact evidence, diagnosis, and rollout gate.
- `BUILD_ORDER.md` — concise handoff for a peer with repository-write access.

## Immediate runbook

### 1. Stop adding queue pressure

Pause merges, rebases, force-pushes, one-shot workflow commits, and blind reruns
until queued counts fall. Do **not** rerun the red emails: those exact runs never
started. Cancelling backlog will not restore GitHub-hosted execution while the
account-level “Stop usage” control remains active.

### 2. Safely identify obsolete queued runs

```bash
export GH_TOKEN='token with repo + Actions write access'

python cancel_superseded_queued_runs.py \
  woahwhattheheck/smb-showcase-inventory \
  woahwhattheheck/pack-market \
  woahwhattheheck/motel-ops-suite \
  --dedupe-exact \
  --json-report cancel-dry-run.json
```

Inspect the report. Then execute the same bounded set:

```bash
python cancel_superseded_queued_runs.py \
  woahwhattheheck/smb-showcase-inventory \
  woahwhattheheck/pack-market \
  woahwhattheheck/motel-ops-suite \
  --dedupe-exact \
  --execute \
  --json-report cancel-executed.json
```

The cancellation tool never targets in-progress runs and has a default hard cap
of 250 requests. Raise `--max-cancels` only after inspecting the dry-run.

### 3. Generate the workflow patch

From a directory containing repository checkouts:

```bash
python actions_queue_storm_fix.py \
  ./smb-showcase-inventory ./pack-market ./motel-ops-suite \
  --diff > actions-main-only.patch
```

Review, then apply atomically:

```bash
python actions_queue_storm_fix.py \
  ./smb-showcase-inventory ./pack-market ./motel-ops-suite \
  --write \
  --json-report actions-main-only-report.json
```

Run again in check mode; success is exit 0 with no remaining candidates:

```bash
python actions_queue_storm_fix.py \
  ./smb-showcase-inventory ./pack-market ./motel-ops-suite \
  --check
```

### 4. Land one infrastructure PR

Commit the workflow-only changes in one infrastructure branch. Do not combine
them with product logic. Required review assertions:

1. Feature branches retain `pull_request` CI.
2. `push` CI still runs on `main`.
3. Workflows with `branches-ignore`, inline trigger syntax, or push-only
   semantics are explicitly reviewed rather than silently changed.
4. No checks are disabled or marked optional to hide the incident.

### 5. Recover only current heads

After backlog reduction, rerun only the current exact heads of still-open PRs.
A real recovery job must show a nonzero runner ID and at least the checkout step.
Only then can its test conclusion be treated as source evidence.
