# Numeric-closure repair

Operation: `titan-v3-paired-game-numeric-closure-20260909-sol-cipher-01`

Base: PR #11530 head `22e764944d246fce5555f8ae09c7f14345179219`.

## Predecessor failures

The original gate correctly rejected explicit `NaN` and `Infinity`, but two
classes of syntactically valid JSON escaped the promised exit contract:

1. an integer score too large for `float(value)` raised an uncaught
   `OverflowError`;
2. individually finite terminal scores could produce an infinite margin,
   own/rival delta, margin delta, median, pair mean, stratum mean, or aggregate
   mean. The report serializer then raised `ValueError` and wrote no machine
   receipt.

Both paths exited 1 rather than the documented exit 2 / `INVALID` result.

## Repair

- scalar conversion overflow is normalized to `GateError`;
- oversized JSON integer/parser failures are normalized to `GateError`;
- every margin and paired delta is finite-checked immediately;
- median, pair, opponent, seat, and aggregate means are finite-checked before
  policy evaluation;
- overflow inside `statistics.fmean` is reported as invalid evidence rather than
  escaping the CLI.

No score clipping, saturation, alternate arithmetic, policy relaxation, or
runtime/controller change is introduced. Extreme evidence is rejected rather
than silently transformed.

## Verification

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
  python3 -m unittest -v \
  test_validation.py test_policy_cli.py test_numeric_closure.py

Ran 26 tests
OK

python3 -m compileall -q .
PASS
```

The three new CLI regressions assert both exit 2 and a persisted `INVALID` JSON
report for oversized integer conversion, finite-endpoint subtraction overflow,
and finite-cell-delta mean overflow. The original 23 tests remain unchanged and
pass.

## Scope

This repair is limited to numeric closure in the paired-game evidence gate. It
does not claim gameplay strength and intentionally does not duplicate the
separately owned artifact-binding, single-read/TOCTOU, or no-clobber repair.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
