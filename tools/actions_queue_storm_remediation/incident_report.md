# GitHub Actions queue-storm incident report

## Executive finding

The screenshot labeled “Fix this” showed red GitHub notification emails across
Pack Market, Motel Ops, and SMB Showcase Inventory. Direct job inspection found
the same pre-execution signature in every visible entry:

- hosted label: `ubuntu-latest`;
- `runner_id: 0`;
- blank runner name;
- `steps: []`;
- one matrix leg eventually labeled failure and another cancelled.

Therefore the red emails were **not source-test verdicts**. They were jobs that
never acquired a runner.

The fleet coordination thread later supplied the missing account-level cause:
GitHub Actions budget was **$10 / $10 exhausted with “Stop usage” enabled** at
2026-09-14 00:39:13 EDT (message TS `1789360753.758319`). This is the primary
execution block. The queue storm and duplicate feature-branch `push` triggers
amplify the incident and will recreate pressure after reset unless repaired.

## Exact sampled runs

| Repository | Workflow | Run ID | Head | Result |
|---|---|---:|---|---|
| pack-market | SaleReady | 34800018325 | 7477bc613efa3271157687949cc86cf80846403f | no runner, no steps |
| pack-market | SaleReady on main | 34799422682 | dae5d282… | no runner, no steps |
| pack-market | Merchant Inventory on main | 34799422668 | main head | no runner, no steps |
| motel-ops-suite | IncidentDesk CI | 34799940233 | 9895ca360692aeda74c9437df9f08ad8022cc17c | no runner, no steps |
| smb-showcase-inventory | Reply Conversion Desk v2 | 34800335706 | affected head | no runner, no steps |
| smb-showcase-inventory | Project profitability review | 34799676014 | 56dfd7de54a590304b7013f083703f57b89dedd4 | no runner, no steps |
| smb-showcase-inventory | Receivable aging review | 34799675823 | 56dfd7de54a590304b7013f083703f57b89dedd4 | no runner, no steps |
| smb-showcase-inventory | Client growth review | 34799676011 | 56dfd7de54a590304b7013f083703f57b89dedd4 | no runner, no steps |
| motel-ops-suite | reviewpulse-ci | 34799637567 | da87c425dfb37e1262747bd6c8f6fca542891c43 | no runner, no steps |

GitHub’s public status API reported all systems operational and no unresolved
incident during the investigation. The GitHub App connection cannot read owner
billing/entitlement settings, so a billing restriction is not directly ruled
out. However, the owner-scoped backlog is independently sufficient to explain
starvation.

## Queue census

Initial census at approximately 05:03 UTC on 2026-09-14:

- SMB Showcase Inventory: **739 queued workflow runs**
- Pack Market: **30 queued workflow runs**
- Motel Ops Suite: **31 queued workflow runs**
- Total across those three: **800 queued runs**

Fresh census at approximately 05:09 UTC:

- SMB Showcase Inventory: **742 queued workflow runs**
- Pack Market: **29 queued workflow runs**
- Motel Ops Suite: **31 queued workflow runs**
- Total across those three: **802 queued runs**

The queue was still growing overall while the account-level stop remained
active.

A workflow run can contain multiple jobs. Several sampled workflows use
two-version matrices, so queued job demand exceeded queued-run count.

## Trigger amplification

Representative workflows such as SaleReady, IncidentDesk, and Project
Profitability had both:

```yaml
on:
  push:
    paths: [...]
  pull_request:
    paths: [...]
```

with no `push.branches` restriction. A feature branch sync from a rapidly
advancing `main` can therefore trigger many path-scoped push workflows for files
imported by that sync, while the PR event also runs CI. This is why an
intermediate Custom Order Desk branch head launched unrelated product workflows
even though the final PR diff did not contain those product paths.

ReviewPulse was PR-only and still starved, demonstrating shared queue impact
rather than a ReviewPulse trigger defect.

## Required remediation order

1. Preserve the standing no-paid-compute boundary; do not raise the Actions
   budget merely to clear this incident.
2. Pause new queue-generating pushes and blind reruns.
3. Cancel queued runs tied to closed PRs, stale PR heads, and exact duplicates.
4. Constrain duplicate product `push` gates to `main`; keep PR gates intact.
5. Add per-PR/per-branch concurrency cancellation in a separately reviewed
   change where product semantics permit it.
6. After entitlement reset—or explicit activation of an already reviewed free-CI
   pilot—rerun only current exact heads.
7. Treat a check as source evidence only after it acquires a runner and executes
   steps.

## Non-remedies

- Do not disable required checks.
- Do not call empty-step jobs green.
- Do not merge because a red run is “only infrastructure” unless local evidence
  and the repository’s merge policy independently authorize it.
- Do not rerun all failed historical heads.
- Do not introduce an owner-PC self-hosted runner merely to hide the queue.
