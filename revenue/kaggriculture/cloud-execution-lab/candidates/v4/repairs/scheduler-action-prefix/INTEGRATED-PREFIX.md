# Integrated-selected executable-prefix recovery

Status: **RECOVERY / EVIDENCE ONLY; NO RUNTIME ACTIVATION.**

This carrier belongs to the existing canonical
`candidates/v4/repairs/scheduler-action-prefix/` family. It does not create a
second V4 line, change `titan_runtime.py`, change defaults/configuration, rebuild
an archive, or authorize a Kaggle submission.

## Remaining defects on current main

`integrated_selected.py` Git blob
`bd08faf49e3caf464004e505d3984b309282bc29` still has two raw-tail readers that
disagree with the official market execution prefix:

1. `_projection` treats any future raw `BUY_PRODUCT` row as a cash-boundary,
   including rows beyond the executable prefix.
2. seed trimming scans all later raw economic rows after an edit, so an inert
   suffix `HIRE`/`BUY_*` can suppress a valid reduction or invoke funding logic.

The recovery transform bounds only those readers. It preserves the returned raw
queue and empty-slot positions. Its prefix is the canonical engine/PREFIX rule:
`q[:max(1, int(maxMarketOrdersPerTurn))]`.

## Historical executed evidence

The stranded predecessor-generation packet was executed against source blob
`defa9b84c77fff28ae107bce291b6235bec5d26c` and official engine blob
`3c202c7ee921da239356789e266b694635103fc4`. In each of normal Python and
`python -O`: 20/20 repaired tests passed; 480 under-cap compatibility cells and
640 two-seat interpreter suffix-equivalence pairs passed; all eight deliberately
broken semantic variants were caught. The exact predecessor failed 76 subcases
and raised 24 errors per mode. Constructed interpreter witnesses retained $100
when an unused seed buy was safely removed, while the 11th-row HIRE remained
unexecuted.

Those are mechanism/equivalence results, not field EV. They were not rerun on
the current source generation and are not relabeled as such.

## Current-source gate

`fold_integrated_action_prefix.py` is exact-source pinned and emits a separate
review postimage only. `test_integrated_action_prefix.py` verifies the current
source pin, both bounded readers, minimum-one cap semantics, raw-suffix custody,
parseability, and drift failure. `run_integrated_prefix_validation.py` runs that
gate in normal and optimized Python.

Any future source drift must be reconciled rather than bypassing the pin. Runtime
promotion still requires current-stack integration and economic gates.
