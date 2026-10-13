# Results

Operation: `titan-v3-paired-game-intersection-closure-20260910-01`

Reviewed parent metric source: Git blob `288f35aa15b137c9bea67df5d3492abae1ce92f8` at `revenue/kaggriculture/cloud-execution-lab/titan-v3-paired-game-gate/metrics.py`.

## Predecessor-killing evidence

`PREDECESSOR-WITNESSES.json` contains three deterministic synthetic ledgers. They are arithmetic/evidence tests, not gameplay results. Each ledger satisfies the reviewed parent gate's published policy profile—nonnegative mean/median own cash, nonnegative global mean margin, sufficient positive own-cash cells and pairs, no result regression, and no negative opponent-only or seat-only own-cash stratum—so the parent profile returns `PROMOTE`.

The companion then independently rederives the score vectors and rejects:

1. **Opponent×seat own-cash mask:** one intersection is `-3` although every opponent marginal and every seat marginal is nonnegative.
2. **Opponent×seat margin mask:** one intersection is `-10` although global mean margin is positive and every own-cash robustness check passes.
3. **Negative paired margin:** seed 1 has two-seat mean margin `-10`, hidden by seed 2 at `+20`; every opponent×seat mean remains `+5`.

Observed verdicts are `PROMOTE → REJECT` in all three witnesses.

## Executed checks

Environment: CPython 3.13.5, Linux cloud container.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
  python3 -m unittest -v test_intersection_gate.py

Ran 22 tests in 3.945s
OK

python3 -m py_compile intersection_gate.py test_intersection_gate.py
PASS
```

Coverage includes the three predecessor witnesses, valid promotion, parent-verdict monotonicity, malformed parent checks, exact digest mismatch, missing/duplicate cells, contradictory deltas/results, NaN/Infinity/boolean numerics, finite-endpoint subtraction overflow, duplicate/unknown contract keys, missing and symlinked inputs, output/input alias protection, deterministic output, and stable CLI exit codes `0/2/3`.

## Example

The complete synthetic interface example under `example/` produces `PROMOTE` over an exact 2 opponents × 2 seeds × 2 seats grid. Its contract binds the included parent report's exact SHA-256. It proves the executable interface only.

## Non-claims

No official game, replay, evaluator, candidate policy, archive, release pointer, provider account, Kaggle submission, hosted score, or leaderboard rank was changed or measured by this work.
