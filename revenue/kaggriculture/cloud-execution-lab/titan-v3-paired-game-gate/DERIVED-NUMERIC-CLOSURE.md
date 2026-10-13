# Derived numeric closure

Operation: `titan-v3-paired-game-derived-numeric-closure-20260909-sol-cipher-02`

Repair land: composed onto current `main` after PR #11627
(`5363b18101d9eaece372557ab9d587aed6da3507`) which already owns snapshot
binding, scalar integer-to-float overflow, `Game.margin` finite-check, paired
delta finite-check, and `statistics.fmean` overflow. This successor does not
rewrite those controls.

## Remaining coverage

PR #11621 stacked on #11597 at `3816ed79509f3fe529834008acfb765fc1ec8f43`,
where `Game.margin` was still unchecked subtraction. Individually finite
terminal scores could still produce non-finite derived evidence:

1. `1e308 - (-1e308)` overflows a game margin;
2. candidate `1e308` minus baseline `-1e308` overflows own/rival delta;
3. finite `+1e308` and `-1e308` game margins overflow margin delta;
4. two finite `1e308` cell deltas overflow `statistics.fmean` at a seat pair
   (same primitive as opponent, seat, and aggregate summaries);
5. an even-cardinality median can become `inf` from finite inputs.

On that predecessor these paths could exit 1 without a machine report. On
current `main` after #11627 the first four already fail closed; this land
adds analyze-level labeled margin checks and W/T/L derived from those
checked margins, normalizes median overflow to `GateError`, and ships the
four CLI regressions plus the even-cardinality median helper.

## Repair

- finite-check baseline and candidate margins at the analyze cell boundary
  (`own - rival`) with exact `baseline_margin` / `candidate_margin` labels;
- keep `Game.margin` finite-check for every other consumer;
- finite-check own, rival, and margin deltas at each cell;
- derive W/T/L from the checked margins;
- normalize mean and median overflow/non-finite results to `GateError`;
- preserve exact pair/opponent/seat/aggregate labels in the error.

No clipping, saturation, alternate arithmetic, score semantic change, policy
relaxation, controller/runtime/archive/default mutation, game execution, or
provider spend is introduced. Extreme evidence is rejected as `INVALID`.

## Verification contract

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
  python3 -m unittest -v \
  test_validation.py test_policy_cli.py test_numeric_closure.py \
  test_derived_numeric_closure.py

Expected: 34 tests, OK

python3 -m compileall -q .
Expected: PASS
```

Each derived-numeric test invokes the real CLI and requires exit 2 plus a
persisted, machine-readable `INVALID` report.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
