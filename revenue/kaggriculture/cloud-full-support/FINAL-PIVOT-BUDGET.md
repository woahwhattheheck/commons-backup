# Final-pivot arithmetic-budget boundary

`full_support.py::_solve_normalized` previously checked the exact rational
simplex tableau before each pivot, but returned immediately when the last pivot
left no improving column. That last pivot can itself grow a numerator or
denominator beyond `max_bits`. The old result was a mathematically valid optimum,
but its `optimal` completion status violated the requested computation budget
and allowed downstream selectors to draw and persist a plan.

The runtime now applies the existing `too_big` predicate at that final optimum
exit. A breached final tableau returns `bit_limit`, the unchanged baseline row
mixture and the existing valid dual upper-bound witness. Sufficient and default
budgets retain the exact optimum. No pivot rule, cache key, certificate math,
receipt table, plan, scenario, random draw or policy default changes.

This is a between-tableau arithmetic-work boundary. It is not a wall-clock or
memory limit and does not prevent the final pivot's arithmetic from occurring.

## Discriminator

For the algebraic table:

```json
[[0, 0], [-95, 48], [497, -106]]
```

`max_bits=16` reaches a 17-bit final tableau after two pivots. The previous code
reported `optimal`, weights `[0, 603/746, 143/746]` and value `6893/373`. The
corrected code reports `bit_limit`, weights `[1, 0, 0]`, lower bound `0`, upper
bound `6893/373` and `exact=false`. With `max_bits=17`, the original optimum is
retained. A separate pure optimum after one final pivot exercises the same
boundary.

These are numerical fixtures, not game-derived receipts. The tests also execute
the unchanged T15 `WholePlanSelector` and PRISM weighted selector. Under the
corrected 16-bit result they preserve the complete supplied action with no draw;
with sufficient budget they draw once and persist the selected sale schedule.
This establishes consumer behavior, not game strength or physical plan
feasibility.

## Executed validation

Exact source identities:

- original core: Git blob `7f7e2e9d62a655e24219490e9c54ab23019f1520`, SHA-256 `91f2cbcf80e8b82a26a987654fef5df0036cd87271522d78b98df8fd9422b06f`;
- corrected core: Git blob `0a660f83cccacbfa809b129db4636651fdf39f6e`, SHA-256 `b08a373c4e5e87545e410880165f188c34e9fe5aff2be78a5cd6c96b6bb2ffae`;
- regression source: Git blob `83d67b30288fcfc6c05bb7d83a37683904ca8b3d`, SHA-256 `bdfd0e47852a5b9c2d34b2125de63e4a311259cbff0667896c43999978df2a5f`;
- T15 solver: blob `3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3`;
- T15 selector: blob `546b71188fd44dc47cac99623d1967bc81413da7`;
- PRISM weighted selector: blob `2c21f8975a64961aec0b94fc6ea930318fec111b`.

The corrected source passes **21/21 focused methods**. The exact previous source
fails **8/21** with zero errors. Coverage includes pure and mixed final exits,
initial/intermediate stops, exact pivot allowance, sufficient/default budgets,
cache separation and detached results, input validation/nonmutation, exact
bounds, CLI output, trace-hook restoration and real consumer fallback/persistence.

A separate deterministic compatibility run evaluates 72 algebraic tables across
222 old/new calls: 213 outputs are identical, and 9 differ only by the corrected
final `bit_limit` status/baseline behavior. All 72 default 512-bit results are
exactly equal. No LP oracle, engine transition, game, seed panel, network
submission or performance benchmark ran for this delivery.

Compact executed facts are retained in `FINAL-PIVOT-BUDGET-VALIDATION.json`.

## Reproduce

From repository root:

```sh
python -B revenue/kaggriculture/cloud-full-support/test_final_pivot_budget.py \
  --report /tmp/final-pivot-budget.json
```

The test loads source bytes directly, uses the existing repository-layout T15 and
PRISM consumers, and does not invoke a simulator or provider. For a negative
control, pass an unmodified copy of the original core through `--core`; eight
methods are expected to fail.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
