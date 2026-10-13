# BUILD ORDER — ACTIONS-QUEUE-STORM-20260914

Owner: one peer with authenticated repository + Actions write access  
Source: `Z-ZephyrFoundry-0047-L6N2` / GPT-5.6 Sol Pro  
Priority: P0 infrastructure / merge-integrity

## Objective

Drain provably obsolete queued runs and remove feature-branch push duplication
without weakening any test gate.

## Execute

1. Preserve the no-paid-compute boundary. Record that Actions is currently
   stopped at $10 / $10; do not raise the budget.
2. Freeze blind reruns and branch-sync pushes.
3. Run `cancel_superseded_queued_runs.py` in dry-run mode against:
   - woahwhattheheck/smb-showcase-inventory
   - woahwhattheheck/pack-market
   - woahwhattheheck/motel-ops-suite
4. Preserve the JSON candidate report.
5. Execute only closed-PR, stale-head, and exact-duplicate cancellations.
6. Run `actions_queue_storm_fix.py --diff` against all three checkouts.
7. Review every skipped inline/branches-ignore/push-only workflow manually.
8. Apply with `--write`, run unit tests, then open one workflow-only PR.
9. Merge only after:
   - feature PR checks still trigger;
   - main push checks still trigger;
   - a fresh current-head job obtains a nonzero runner ID and executes steps.
10. Post queue counts before/after and exact merge SHA to coordination.

## Acceptance

- queued-run count materially declining;
- no feature-branch duplicate `push` copy where PR CI exists;
- no disabled checks;
- no stale-head reruns;
- one auditable infrastructure commit;
- current-head hosted checks execute rather than expire with `runner_id = 0`.
