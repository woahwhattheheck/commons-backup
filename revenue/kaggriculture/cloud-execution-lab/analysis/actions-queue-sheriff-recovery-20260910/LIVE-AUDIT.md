# TITAN V3 Actions queue audit — 2026-09-10

## Live observations

- Successive repository reads reported **1,406**, **1,421**, then **1,433** queued workflow runs.
- Only **14 pull requests** were open during the audit.
- GitHub reported **20 in-progress** runs while the queued population continued growing.
- Page 10 of the queued-run listing (roughly rows 901–1,000, newest-first) still contained PR-triggered runs created at **2026-09-09 22:15:29 UTC** whose PR association was already empty.
- The V3 one-tree materialization run **34516594783** (head `0e7ea5f2bd78040dfc38758d08b149f392c1fb3b`) was created at **2026-09-10 18:48:34 UTC** and remained queued through the final read around 19:18 UTC.
- One newly opened TITAN PR head spawned nine visible workflows immediately: eight generic checks plus its dedicated panel. This is queue amplification, not gameplay evidence.

## Diagnosis

The binding constraint is repository-wide experiment throughput. Old PR checks are not being retired quickly enough, while broad path filters make unrelated validation workflows join nearly every `cloud-execution-lab` PR. This delays the one-tree publication build and every score-bearing panel. In that state, adding more candidate heuristics increases evidence latency faster than it increases reliable information.

## Repair packet

`titan-v3-actions-queue-sheriff.patch` adds or changes five repository paths:

1. `.github/scripts/queue_sheriff.py` — a stdlib-only, deterministic, fail-closed classifier and cancellation client.
2. `.github/scripts/test_queue_sheriff.py` — 22 predecessor-killing contracts.
3. `.github/workflows/actions-queue-sheriff.yml` — trusted-default-branch execution, manual dry-run/apply dispatch, and automatic closed-PR retirement.
4. `.github/workflows/titan-selected-projection.yml` — removes the catch-all `cloud-execution-lab/**` trigger, retains the exact files its sparse checkout consumes (including the frozen archive), and makes new revisions supersede old runs.
5. `.github/workflows/path-manifest.yml` — adds PR/ref concurrency so stale revisions cannot stack indefinitely.

The sheriff never cancels in-progress runs. It retains current open-PR heads, manual/repository dispatches, live singleton branch pushes, explicit run IDs, and protected workflow/branch globs. It cancels only queued checks tied to closed/missing PRs, superseded open-PR heads, old queued runs on deleted branches, or older duplicate branch pushes.

Every complete mutation plan is written before the first cancellation. GitHub HTTP 409 races are recorded as benign `already_terminal` outcomes; all other API errors fail closed with an updated receipt. Cancellation requests are paced at 0.5 seconds each to avoid turning a large cleanup into secondary-rate-limit churn.

## Recurrence prevention

Once landed, every `pull_request_target: closed` event runs the sheriff from the trusted default branch with:

- `apply=true`
- `stale_minutes=0`
- `max_cancel=1000`
- protected workflow globs `*one-tree*`, `*publication*`, `*release*`
- protected branches `main`, `release/*`

The global sheriff concurrency permits one active and one latest pending audit. A later close event can replace an obsolete pending audit, while the running cleanup completes uninterrupted. Each pass audits the whole visible queued population, so no per-PR untrusted input is required.

## Recommended first manual dispatch after landing

Use audit-only mode first:

- `apply=false`
- `stale_minutes=30`
- `max_cancel=1000`
- `protect_run_ids=34516594783`
- default protected workflow globs (`*one-tree*`, `*publication*`, `*release*`)

Inspect the JSON decision counts, then dispatch `apply=true` with the same protections. GitHub exposes at most 1,000 results for a filtered workflow-run query; when `api_search_truncated=true`, repeat after the first pass.

## Local proof

- Python: 3.13.5
- `python -B -m unittest -v test_queue_sheriff.py`: **22/22 PASS**
- `python -m py_compile queue_sheriff.py test_queue_sheriff.py`: **PASS**
- Workflow YAML parse: **PASS**
- Synthetic repository `git apply --check`: **PASS**
- Synthetic repository `git apply`: **PASS**
- Applied-tree tests, compile, YAML parse, and `git diff --check`: **PASS**

## Landing options

- `titan-v3-actions-queue-sheriff.patch` is the complete five-path change.
- `titan-v3-actions-queue-sheriff-core.patch` adds only the sheriff script, contracts, and workflow; use it when the two existing workflow files have moved.
- `titan-v3-actions-amplification-fixes.patch` contains only the projection-trigger/concurrency and path-manifest concurrency changes.

All three patch forms passed independent synthetic `git apply --check` and apply validation.

No canonical TITAN runtime, config, archive, pointer, provider, Kaggle submission, or gameplay policy is changed by this packet.
