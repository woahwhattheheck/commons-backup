# Exact trigger-repair patch receipts

Two reviewable patches are included:

- `exact-main-trigger-repair.patch` — five current-default-branch workflows:
  SaleReady, Reply Conversion, Project Profitability, Receivable Aging, and
  Client Growth.
- `incidentdesk-pr165-trigger-repair.patch` — the exact IncidentDesk PR #165
  branch workflow.

Each patch adds only:

```yaml
push:
  branches: [main]
```

It retains every existing path filter, pull-request trigger, job, matrix,
permission, timeout, and command. ReviewPulse is intentionally absent because
its exact workflow is PR-only and therefore was collateral damage, not a trigger
amplifier.

Validation performed:

- source blob SHA pinned for every fetched workflow;
- `git apply --check` PASS against exact fetched bytes;
- real `git apply` PASS;
- transformed bytes equal the tested rewriter output;
- post-apply rewriter `--check` reports zero remaining changes.

The IncidentDesk patch belongs on the current PR #165 branch before landing,
not blindly on unrelated `main` state.
