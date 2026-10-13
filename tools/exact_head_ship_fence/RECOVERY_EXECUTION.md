# D4M8 recovery execution — September 19, 2026

Operation: `exact-head-ship-fence-delivery-d4m8-20260919`. Existing demand #15676 and carrier #15731. ZZ-KESTREL-D4M8 / GPT-6 Astra Pro owns this regression completion; retained source and review contributors keep their original credit.

## Source and execution

Donor: `0900f7c40284d7576b016cbafb541d5ec06edb0d`. All eight executable/test files were hydrated through native GitHub reads and matched to the donor Git blob identities before execution. The README was not needed for execution and was not represented as hydrated. Runtime: Python 3.13.5, GCC 14.2.0, ephemeral Linux cloud container; no owner-PC execution or new runner.

The unchanged original two-module suite ran 24 tests normally and 24 under `python -O`, all passing. The added thirteen-method recovery panel initially produced eleven passes, one failure and one error: the public review guard visited an oversized array before its existing limit and compared a non-string head before core type validation. The correction captures/reuses the existing core array, SHA and name validators before review comparisons/case normalization. The core source, verdict policy and original tests remain unchanged.

Actual post-correction commands:

```sh
python -m unittest -v tools.exact_head_ship_fence.test_fence tools.exact_head_ship_fence.test_hardening tools.exact_head_ship_fence.test_recovery
python -O -m unittest -v tools.exact_head_ship_fence.test_fence tools.exact_head_ship_fence.test_hardening tools.exact_head_ship_fence.test_recovery
```

Both ran **37 tests, zero failures/errors/skips**. New coverage also retains optional-positive-review STOP behavior, exact 64-review acceptance, schema array caps, bounded canonical input and input preservation.

Executed changed-file identities:

| File | Git blob | SHA-256 |
|---|---|---|
| `fence.py` | `336bdec681ce59c0f5e85d98690d04d2e9c54093` | `2f41ed824f4341b100b27416e5960a1f7d9d960af419d8d25f5304fcb0a178be` |
| `test_recovery.py` | `f87e8c5e497561a0ee0b1c83f5734eca338c0626` | `3c5b5d8cefa3a3129513f35b044cb466004d69a8c2a1d2c65469962551dd80f4` |

This records component execution, not hosted CI, current-main composition, a canonical swarm-review packet or merge readiness. The forthcoming operator rehearsal remains a separate deliverable. The offline tool consumes retained snapshots and never queries or mutates GitHub; its READY verdict does not replace `host/swarm_review.py` or actual provider execution.
