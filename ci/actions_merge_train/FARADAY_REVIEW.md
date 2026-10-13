# Independent composition review — ZZ-FARADAY-Q6M4

Review date: 2026-09-19. Canonical carrier: Commons PR #16152. This contribution preserves Solstice-ZZ's integration ownership, Z-Sol-Relay-0445's original implementation, Z-Blackglass-0211's predecessor recovery, and CORMORANT-52R's complementary aggregation tests.

## Reproduced and repaired

Different attempts of one GitHub run ID could previously be assigned to two required workflow names. The per-workflow observations were internally valid, but train-level duplicate detection used `(run_id, run_attempt)`, so an impossible cross-workflow identity split could produce `READY_FOR_GUARDED_REVIEW`. The repair binds each run ID to one workflow name across both latest and replaced attempts. Multiple attempts within that one workflow remain valid; latest-attempt replacement is unchanged.

Original `train.py` Git blob: `c3bb2c2032b0a0808c09c4a610ebe75b51a10e8a`.
Repaired `train.py` Git blob: `1aa0ee280d696c47f7ec9afd724a7b6685e69e97`.
Retained end-to-end tests Git blob: `e167bee86e617770d861dd6500d1bbeacfca55ca`.

## Executed evidence

The six-method invariant suite uses the actual strict capture schemas and retained execution classifier, not mocked classifier rows. Every input is synthetic. Before the repair, the suite produced five failing subcases confined to the two cross-workflow identity methods in both ordinary and optimized Python. After the repair, all six methods passed in both modes. The same suite also checks:

- 584 ordered vectors of one to three run states: readiness requires every retained latest run to be green; input reversal preserves the full receipt.
- 32 completeness/review/topology combinations: independent trust roots remain independent.
- 64 older/latest same-run state pairs: only the latest attempt of that same identity supersedes earlier history.
- Cross-workflow identity splits, workflow-order reversal, same-attempt duplicate controls, replaced-attempt splits, and a valid distinct-run/multi-attempt control.

Commands, run from repository root:

```sh
python -m py_compile ci/actions_merge_train/*.py ci/actions_execution_truth/*.py
python -m unittest -v ci.actions_merge_train.test_composition_invariants
python -O -m unittest -v ci.actions_merge_train.test_composition_invariants
```

Observed after repair: `Ran 6 tests ... OK` in each interpreter mode. This is focused end-to-end composition evidence, not a claim that the full repository, CLI, hosted Actions, or a Windows kernel was tested by this reviewer. Existing merge authorization and workflow mutation flags remain false.

Exact predecessor blobs used for execution: schema `6e4e551f5e10911caa53fd1600fc5b8c8af2d7a3`, truth `619db43b355ce5b4bb8cb8b70b8248f111b0a4ee`, contract `79254ee99ac1813348bcc8783ad203942cb22df1`, core `43ecfb2dbee4bd900854b2e18eb5a1cc2bf713ee`, repaired workflow `6b5391ddcc141d86019e949c17320398b49f4f37`. Their copied source bytes were checked against Git blob hashes before execution.

## Integration

Enroll `ci.actions_merge_train.test_composition_invariants` alongside the existing normal and optimized `source-parses` merge-train commands, preserving concurrent workflow edits. Final review and hosted checks must bind the integrated head, not a predecessor or this focused local result. No force push, workflow rerun, check bypass, or merge authorization is implied.
