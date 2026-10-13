# ROADEF rank-traversal restart-budget follow-up

Source/evidence only. **No solver run, contest submission, promotion, provider action, account mutation, or spend is performed by this package.** The existing submission hold remains authoritative.

The released `cloud-rank-traversal` scheduler uses one `FLEET_RANK1_PASSES` counter for both (a) no-gain rank probes that advance the finite rank sweep and (b) accepted moves that reset selection to rank 1. The Sep 8 review observed useful A04/A14 improvements while both arms exhausted the default 16-pass cap with hundreds of seconds still available. Accepted resets therefore spend the same scarce budget that is supposed to expose deeper coordinates.

This follow-up makes the accounting explicit and bounded:

- `FLEET_RANK1_PASSES` becomes the budget of **non-accepting rank probes** while rank traversal is enabled. The legacy non-traversal branch still uses it as the original total pass cap.
- New `FLEET_RANK1_RESTARTS` is the budget of accepted rank-1 resets; it defaults to the configured pass budget and is capped at 128.
- Every traversal iteration consumes exactly one of those two finite budgets. Therefore scheduler iterations are bounded by `pass_budget + restart_budget` (maximum 256) in addition to the unchanged global `finished()` wall-clock/signal guard.
- Accepted moves still reset ordering to rank 1. No-gain probes still advance one rank and an unchanged-state sweep still stops at `configured_sweep_exhaustion`.
- Hitting the accepted-reset cap stops with `restart_budget`. Diagnostics/PRISM report include `no_gain_passes`, `restart_limit`, and `restarts`.
- Candidate generation, `move()`/`moveTogether()`, ECMP, segment limits, transition budgets, sorted six-decimal acceptance, solution checkpointing, ordinary search, natural-exhaustion gate, signal handling and total `SEDGE_SECONDS` envelope are not changed by the generator.

`build_restart_budget.py` accepts **only** the released `cloud-rank-traversal/main.cpp` bytes (50,431 bytes; SHA-256 `d85ee6187607b1e04c9d77073d42e3eba699fe42309ee3f3324f25528a8f945e`). It then writes a candidate source, unified diff and JSON receipt. Exact-anchor checks fail closed if the source is not the reviewed scheduler.

Generate locally without networking, compilation or execution:

```sh
python3 -B build_restart_budget.py ../cloud-rank-traversal/main.cpp \
  --output restart-budget-main.cpp \
  --patch restart-budget.patch \
  --receipt SOURCE-RECEIPT.generated.json
python3 -B -m unittest -v test_restart_budget.py
```

The deterministic tests cover the starvation case (eight accepted resets still leave all 16 no-gain ranks available), reset-storm boundedness, the 256-iteration hard cap, scheduler-only anchor transformation and fail-closed base identity. They do **not** claim performance improvement; a future owner may run the generated candidate under the already-established ROADEF evaluator only after fresh resource/ownership checks. Submission remains on hold.
