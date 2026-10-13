# Exact full-support receipt-table solver

This optional, standard-library component solves the complete supplied finite
matrix, rather than restricting mixtures to two alternative plans. It does not
construct a controller, price receipts, infer rival probabilities, or change a
selected policy. T15's original solver, selector and frozen evaluations remain
unchanged. Runtime plan selection and independent consumer inspection are
separate components owned by PRISM and TRIAD respectively.

## Callable

```python
from full_support import solve_full_table, verify_certificate

# Algebraic discriminator, not an observed game payoff table.
deltas = [[0, 0, 0], [5, -2, -2], [-2, 5, -2], [-2, -2, 5]]
result = solve_full_table(deltas, max_pivots=128, max_bits=512)
assert verify_certificate(deltas, result)["valid"]
# result["weights"] == ["0", "1/3", "1/3", "1/3"]
# result["value"] == result["upper_bound"] == "1/3"
```

Rows are one zero-delta baseline followed by up to eight complete alternatives;
columns are 1..32 complete, correlated rival streams. Each entry is the change
in **own-minus-rival cash relative to the same baseline under the same stream**.
Original row and column positions are retained, including all zero weights.
Integer, fraction-string and `Fraction` inputs are exact. Finite floats are
interpreted as their decimal string, not their binary expansion. Invalid shapes,
a nonzero baseline, nonfinite values or oversized inputs raise `ValueError`.

The caller establishes feasibility of **every constituent plan**, consistent
fixed order positions, dated stock/cash/worker commitments, and scenario
provenance before using a mixture. A feasible average cannot repair an infeasible
constituent. This solver only sees a matrix; it does not establish any of those
physical or observation-time facts. It also does not reconcile submitted sales
with fills or revalidate future commitments.

## Results and independent bounds

`weights` and `column_expectations` contain exact rational strings. `value` is
the minimum included-column expectation for that row mixture. `dual_weights`
are a normalized nonnegative **adversarial certificate**, not fitted or calibrated
scenario probabilities. `row_expectations_under_dual` and their maximum
`upper_bound` prove an upper bound on the best mixture over the entire supplied
row family. `gap = upper_bound - value`. Equal lower and upper bounds prove the
finite-table optimum without rerunning the optimizer.

Other fields are `status`, `exact`, `arithmetic_exact`, `support`, `pivots`,
`max_pivots`, `max_bits`, `pure_minima`, `alpha=0`, `probabilities=None`,
`table_sha256`, `scope` and `certificate_valid`. The hash is SHA-256 of compact
ASCII JSON of the matrix after each entry is converted to a canonical rational
string: `json.dumps(rows_as_strings, separators=(',', ':'))`.

`verify_certificate(deltas, result)` independently recomputes the two bounds,
normalization, dimensions, hash and expectation arrays using only rational
arithmetic. It returns `valid`, `optimal` and exact bound strings, or a failure
reason. It does not run simplex. For independently supplied provider results,
check that the certificate is valid before consumption; do not trust the
provider's `certificate_valid` Boolean alone.

`status='optimal'` denotes completed optimization. `exact=True` requires that
status and an exactly closed bound gap. An exact-zero optimum deliberately
returns the original baseline, not an arbitrary alternative tied with it.
`pivot_limit` and `bit_limit` return baseline weights and a valid upper-bound
witness, with `exact=False`; an unfinished positive mixture is never emitted.
Occasionally that baseline and an elementary upper bound already prove a zero
optimum even though optimization stopped: the verifier can then report
`optimal=True` while the provider's completion status remains a limit. Preserve
both facts; the output is still the unchanged baseline.

## Computation bounds

The exact simplex implementation solves the positive-shifted packing linear
program `max sum(y)` subject to `(D + shift) y <= 1, y >= 0`. A feasible slack
basis avoids a phase-I solve. Bland entering/leaving ordering resolves
algebraic degeneracy deterministically. The objective slack coefficients yield
the row mixture; the normalized primal variables yield the column witness.
The zero-baseline row ensures a nonnegative achievable original value.

At most 128 pivots and a 512-bit rational-component threshold are used by
default. Caller options allow 0..4096 pivots and 16..4096 bits. Input sizes are
checked, and the tableau threshold is checked before another pivot. These are
arithmetic-work controls, **not a hard wall-clock timeout or whole-agent runtime
guarantee**. A finishing pivot and certificate arithmetic can exceed the
threshold; they remain exact. Imports, receipt construction, selectors and
other agent work are outside the timings below.

## Executed validation

`test_full_support.py` contains 21 passing standard-library regression methods:
three- and eight-alternative support, zero-tie preservation, fractions, repeated
and permuted rows/columns, certificate tampering, both computation limits,
canonical hashes, nonmutation and CLI execution. Eighty generated matrices are
included in these methods.

`validate.py` executes another deterministic algebraic corpus with every shape
from 2..9 rows by 1..32 columns: 256 inputs. On the retained run, all 256 exact
certificates close; SciPy 1.17.0 HiGHS independently agrees on all values
(maximum absolute difference 5.329070518200751e-15). The new solver also agrees
on all 256 restricted projections with the actual existing T15 solver blob
`3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3`. This is new-core compatibility testing,
not a rerun of T15's gameplay proof. SciPy is only an optional validation oracle.

On Python 3.13.5 the 256 in-process solver-plus-certificate calls had median
1.5394 ms, p95 8.3046 ms and maximum 16.7529 ms, with at most 29 pivots. The
three-support algebraic example attains 1/3 while every two-alternative
restriction attains zero. The eight-alternative example requires all eight and
attains 1/8. These are mathematical discriminators, **not game-strength results**.

The two small strawberry tables in the tests are explicitly transcribed from
T15's published README at `4d97474b0188b0373be1b52b610c0114ceb033c8`: the original
two-stream table returns 1/5 and the added adverse column restores the baseline.
This component does not claim to have re-executed their official engine traces.
There are zero new engine transitions, full games, gameplay seeds or selection
changes in this delivery. No broader-support improvement on reached game
observations is established here. An expectation over included streams is not
a per-game guarantee, and omitted streams can change the optimum.

`VALIDATION.json` retains source identities, complete witness results, all 256
exact values and corpus fingerprints. The runnable validation command produces
all input matrices and full certificates, not just the summary.

## Reproduce

From the repository root:

```sh
python -m unittest discover -s revenue/kaggriculture/cloud-full-support -p 'test_*.py'
python revenue/kaggriculture/cloud-full-support/full_support.py input-matrix.json
python revenue/kaggriculture/cloud-full-support/validate.py \
  --with-scipy \
  --reference-solver revenue/kaggriculture/cloud-market-game-theory/solver.py \
  --output /tmp/poly-full-validation-new.json
```

Omit `--with-scipy` for standard-library-only execution; the result then records
zero independent-LP comparisons. Omit `--reference-solver` to test only the
full-support core. Reference source identities are read from actual bytes,
never assumed from a path. The validation output must be a new filename so
retained inputs or prior runs are not overwritten. The core CLI also accepts
`{"deltas": [...]}` and an optional `--output` result path.

Apache-2.0. See `NOTICE.md` for the interface and validation references.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
