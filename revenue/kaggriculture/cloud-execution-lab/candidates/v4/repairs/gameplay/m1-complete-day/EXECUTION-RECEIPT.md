# M1 complete-day execution receipt

Session: ASTRA-DAYCOVER. Validation date: 2026-09-11 America/Chicago.
Status: VERIFIED SOURCE-ORDER REPAIR; NOT PRODUCTION ACTIVATION.

This extends the already-preserved `m1-complete-day` package on canonical `main`. It does not create a new V4 branch or replace the `m1-two-seat` predecessor. The existing MANIFEST.json remains donor provenance; this receipt binds its transformer to the executable postimage and independent tests below.

## Defect and exact custody

The predecessor used tape EOF as day-end. At step 101, a tape ending at the step-104 WHEAT pickup could certify a purchase without evidence for cash owners in omitted steps 105 through 119. The recovered transformer requires coverage through literal day-end; the source delta is only that narrowing guard.

| Artifact | Git blob | Bytes |
| --- | --- | ---: |
| Predecessor in ../m1-two-seat/r04_m1_wheat_trade.py | d4d068d62ffc8fcd25842193bc7031f764630262 | 15652 |
| repair_m1_complete_day.py (existing donor) | 1014d235909bcf694dad1c620195e11981adb07f | 2353 |
| r04_m1_wheat_trade.py (executed postimage) | 87eb8ccbee13b33ef656ba0a5ba0114ac30f4658 | 15897 |
| test_v4_m1_complete_day.py (existing donor) | db0cc52f70be6908816f5dc52c1eed5e0eae691d | 1926 |
| test_v4_m1_money_overflow.py (existing custody regression) | 5695a41e8baca3da1b0b730ebcb3c27e6fa0bc8d | 2767 |
| test_v4_m1_daycoverage_boundaries.py (new independent suite) | 023720500168f2e922ab8564a5bfd60b68779a59 | 5272 |

Each input and output was locally verified using Git blob hashing. Applying the exact transformer to the exact predecessor equals the published postimage byte-for-byte. Applying it twice is rejected. Both source files intentionally retain their original lack of a trailing newline.

## Executed evidence

Local CPython 3.13.5, normal and optimized interpreters:

- Original 8 focused tests on the exact predecessor: 7 pass and the truncated-day witness fails (104 was returned where None was required).
- Repaired original 8 focused tests: 8/8 pass, normal and `-O`.
- Full repaired suite: 18/18 pass, normal and `-O`. A final independent rerun also passed 18/18 in each mode.
- Boundary coverage per mode: 2660 complete-day positives and 26740 truncated-EOF rejections across eligible steps 24 through 695 and lookahead 2 through 6, excluding hour-23 pickups.
- 150 later-cash-owner cases cover all five purchase opcodes, every remaining hour 105 through 119, and executable raw slots 0 and 9.
- Controls retain dead raw-slot 10 behavior, next-day cash independence, hour-23 rejection, missing terminal market-evidence rejection, tuple tape parity, both-player positive activation, immutable inputs, disabled identity, huge-integer money rejection, and public-seat guards.
- `py_compile` passes for the helper, transformer and all three tests. Transformer exact-once and double-apply rejection pass.

These are source-contract tests, not official-engine differential tests, CI results, replay performance, win-rate improvement or an economic promotion gate.

## Reproduce

From this directory (no legacy materializer is needed):

```sh
python -m py_compile r04_m1_wheat_trade.py repair_m1_complete_day.py test_v4_m1_complete_day.py test_v4_m1_money_overflow.py test_v4_m1_daycoverage_boundaries.py
python -m unittest -v test_v4_m1_complete_day test_v4_m1_money_overflow test_v4_m1_daycoverage_boundaries
python -O -m unittest -v test_v4_m1_complete_day test_v4_m1_money_overflow test_v4_m1_daycoverage_boundaries
```

To reproduce the predecessor failure, copy this package to a temporary directory and replace only that temporary helper with the exact d4d068 predecessor. Run the original complete-day and money-overflow suites there. Do not overwrite the preserved predecessor or mutate production for this check.

## Integration boundary

Source order: M1 huge-integer hardening, then public two-seat custody, then this complete-day proof. Existing transformer/regression and predecessor provenance remain unchanged. No feature key, defaults, production entrypoint, runtime routing, production archive, workflow, old donor ref or Kaggle submission was changed. Current production ABI porting and the economic gate remain separate work.

Coordination receipts: PR #12605 comments 5642660391 (claim) and 5642708643 (execution and duplicate-preservation deconfliction). The canonical package created concurrently by another seat is reused rather than duplicated.
