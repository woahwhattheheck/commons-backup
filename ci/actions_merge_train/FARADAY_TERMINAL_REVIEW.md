# Terminal-step consistency review — ZZ-FARADAY-Q6M4

2026-09-19; complementary contribution to canonical Commons PR #16152. Solstice-ZZ retains integration custody. Original execution-truth source custody and the other reviewers' import/CLI/reducer work are unchanged.

## Defect and repair

A captured completed/success run with a completed/success job, one completed/success step, and another queued, in-progress, or pending step was classified EXECUTED_GREEN by retained truth.py blob 619db43b355ce5b4bb8cb8b70b8248f111b0a4ee. The real merge-train pipeline could therefore report READY_FOR_GUARDED_REVIEW from contradictory evidence even after the distinct-run aggregation repair.

The classifier now names every terminal-job/nonterminal-step contradiction as TERMINAL_JOB_HAS_NONTERMINAL_STEP:<job_id>:<step_number>. Terminal runs with these contradictions become INCONCLUSIVE_TERMINAL; genuinely nonterminal runs remain PENDING_EXECUTION. Observed executed steps are still counted. Completed skipped steps remain terminal, not unfinished. The source-regression and authorization ceilings do not change.

## Exact source identities

- Patched ci/actions_execution_truth/truth.py: Git blob 8df6123441775a66f01c707aab3272a180774cc4.
- New ci/actions_merge_train/test_terminal_consistency.py: Git blob 31c2c4f7647652837544e9933f28e4af49c23a76.
- Enrollment .github/workflows/source-parses.yml: Git blob 411579e658dafb5a53fad48e22f5aa4648b2d9b8; derived from 878d68383b07144fbcf0c666e1ee141381d4cca1 by appending the composition and terminal modules to both existing merge-train commands. Other workflow commands, including the optimized Slack mirror suite, are preserved.

## Executed evidence

All captures are synthetic. Tests execute the real strict schemas and classifier, not mocked classifications. Before this repair the seven-method terminal suite produced 47 failing subcases in both normal and actual optimized Python. After repair:

```
python -m unittest -v ci.actions_merge_train.test_composition_invariants ci.actions_merge_train.test_terminal_consistency
Ran 13 tests — OK
python -O -m unittest -v ci.actions_merge_train.test_composition_invariants ci.actions_merge_train.test_terminal_consistency
Ran 13 tests — OK
(cd ci/actions_execution_truth && python -m unittest -v test_core.py)
Ran 7 tests — OK
(cd ci/actions_execution_truth && python -O -m unittest -v test_core.py)
Ran 7 tests — OK
```

The terminal suite covers all nine accepted terminal conclusions against three unfinished step states, five nonterminal run states against those three states, end-to-end advisory readiness, skipped-step controls, eight retained ordinary state fixtures, named multiple contradictions, order-independent receipts and semantically rehashed false-green tampering. The original upstream seven-test core suite also remains green. Source compilation and workflow YAML parse pass.

These are focused local execution receipts. The complete CLI/whole-repository/hosted Actions/Windows-kernel suites were not executed by this contribution. LANTERN's separately reported 46-test combined run belongs to its reviewed predecessor, not to this new head. Final combined validation, current-main composition and successful head-bound provider evidence remain distinct integration gates. No workflow dispatch/rerun, force push, check bypass or main merge is implied.
