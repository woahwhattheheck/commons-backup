# Results and non-claims

## Executed locally

Command:

```bash
python3 -m unittest -v test_semantic_safety.py test_builder.py
```

Result: **20 tests passed** in **0.034 seconds** in the session cloud container.
A subsequent full rerun after eliminating the tar extraction warning also passed
20/20 in 0.030 seconds.

Additional command:

```bash
python3 -m compileall -q .
```

The source modules and tests compile successfully.

## What the tests establish

- A saturated 10-slot market queue is returned by object identity and its tenth
  inherited order survives.
- A safe land hypothesis appends after inherited orders only when a free slot
  exists; it never prepends or duplicates `BUY_LAND`.
- Dumper classification does not edit SELLs; E11 is the sole sell-deferral owner.
- E11 aggregates actual future per-step absorption. A non-tick current step can
  still see future shop ticks, and a current shop tick is not multiplied by the
  entire horizon.
- Fractional or negative absorption fails closed.
- Terminal decisions preserve the selected action.
- Under low crop-service demand, E20 preserves every queue index and drops all
  HIREs beyond the remaining allowance, not just the final one.
- Disabled flags return the exact original action object.
- The builder rejects noncanonical hashes by default, rejects traversal members,
  removes partial output after failure, inserts exactly one hook before pending
  accounting, compiles touched files, and writes an output hash manifest.

## Not executed

- No full game.
- No 4×192 development matrix.
- No holdout.
- No hosted Kaggle run or submission.
- No export replacement.
- No claim that E11, O01, E20, or SHOP improves win rate or cash.

The unit result authorizes a bounded E11-only gameplay experiment; it does not
authorize promotion.
