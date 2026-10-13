# Quiet-carrier deadline sweep

Deterministic implementation of reset-wave order `QUIET-CARRIER-DEADLINE-SWEEP-20260916`.

It screens Sep 1–15 merged HOLD carriers for deadlines Sep 23–Oct 15, then excludes any current post-Sep16 owner, SENT, DNR, expired deadline, or out-of-window carrier. Remaining rows are ordered by recoverable public-source posture, number of owner-only facts, deadline, known value path, and stable ID. This is an **actionability ordering**, not external-send authority.

Current Sep 17 census ranks IMPO MTP 2055 first and Snohomish RFP-26-0791BC second. USAC IT-26-139 is excluded because a live Sol-17 recovery owner exists; TTUHSC, WRI Open Timber, and Alcorn RFP 5588 are outside the reset-wave deadline window.

Every report and every ranked row carries `external_action_authorized=false`.

Run:

```bash
python -m revenue.quiet_carrier_deadline_sweep.sweep revenue/quiet_carrier_deadline_sweep/candidates.json --markdown
python -m unittest -v revenue.quiet_carrier_deadline_sweep.tests.test_sweep
python -O -m unittest -v revenue.quiet_carrier_deadline_sweep.tests.test_sweep
```

No dedicated workflow is added: Commons is already at the 67/67 active-workflow budget.
