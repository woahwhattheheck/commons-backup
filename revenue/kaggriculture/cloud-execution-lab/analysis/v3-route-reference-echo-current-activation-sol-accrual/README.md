# TITAN V3 route-reference echo — exact-current activation closure

Operation: `titan-v3-route-reference-echo-current-activation-20260910-01`

This lane consumes the independently reviewed source/state theorem from the
closed, unmerged SOL-ACCRUAL packet in
`../v3-route-reference-echo-sol-accrual/`. It does not replace or broaden that
theorem. The predecessor established that current `FrozenSelected` can place an
inherited future route `SELL` into the optimizer reference, checkpoint the
selected **total** into `self.planned`, then add the unchanged inherited route
quantity again when the step becomes due. The guarded consumer stores only the
scheduler-owned excess above that fixed route floor.

The missing evidence was natural activation on the exact current package and
score/action consequences. This successor supplies that closure without
changing canonical runtime or release bytes.

## Exact current base

- current-main ancestor: `21011846096daad1dd487df0efedf209303c1cb5`
- canonical archive SHA-256:
  `5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1`
- canonical source-manifest SHA-256:
  `3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469`
- canonical `main.py` blob: `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`
- canonical `scheduler.py` blob: `a483b24dd72b580d7d8811636b54d2d44f391575`
- canonical `frozen_selected.py` blob:
  `fc7baf5c179818a55037f6a61d92984d81d1a21c`
- official evaluator blob: `077feb2208b6e0c1727835eb4f8089709bf67f3b`
- official engine `kaggriculture.py` blob:
  `3c202c7ee921da239356789e266b694635103fc4`

The source candidate and normalization implementation are reused at their
reviewed Git blobs. The first recovery commit adds those exact blobs on top of
current main; this directory adds evidence transport and classification only.

## Evidence path

`instrumented_candidate.py` delegates the complete action to the reviewed
candidate. After the action returns, it exposes an optional, JSON-bounded hook
only when the normalization receipt says `changed=true`, `status=NORMALIZED`,
and removed quantity is positive. Duplicate receipts are suppressed per game.
The hook cannot mutate the returned action.

`materialize_evaluator.py` applies seven exact-cardinality patches to the pinned
offline evaluator. It records, for the tested actor only:

1. every returned action's SHA-256 in order;
2. a rolling ordered action digest; and
3. the optional normalization receipt beside the same pre-interpreter step.

Actions are handed to the official interpreter unchanged. The source evaluator
is re-hashed before patching and checked again afterward.

`run_current_panel.sh` verifies source blobs and the canonical archive pointer,
runs predecessor and successor contracts, requires the canonical archive to
rebuild byte-current, materializes the evidence evaluator, then evaluates
control and repair on the same 8 seeds, both seats, against public Arlene and
frozen V1: 32 cells per arm, 64 official-interpreter games total, plus the
existing deterministic first-cell recheck.

`analyze_panel.py` rejects incomplete or mismatched schedules, malformed or
out-of-order receipts, control-side evidence, action-count drift, and any score
change without a returned-action divergence. It reports natural activation,
first action-divergence steps, own/rival/margin deltas, W/T/L transitions,
opponent-by-seat strata, and descriptive cell/seed sign summaries.

## Verdicts

- `NO_NATURAL_ACTIVATION`: no affirmative normalization receipt.
- `STATE_ONLY_ACTIVATION`: normalization fired but returned actions stayed equal.
- `ADVANCE`: natural and action activation, positive mean own and margin deltas,
  no new losses or lost wins, and no negative opponent-by-seat mean own delta.
- `REGRESSION`: negative aggregate/stratum economics or adverse W/T/L movement.
- `MIXED_MORE_EVIDENCE`: action-active but not cleanly directional.

The classifier never authorizes promotion. Any useful result remains a
candidate for one-tree integration and a fresh integrated-control panel.

## Scope lock

No canonical gameplay file, config, archive, pointer, source manifest, provider,
Kaggle submission, or hosted leaderboard state is modified. No claim is made
for the active own-value, continuation-haircut, intent-priority, multi-product,
cash-reserve, or cashflow-atlas lanes.
