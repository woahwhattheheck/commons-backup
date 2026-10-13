# A mean-preserving quintic body-diagonal edge lift

`p5_body_diagonal_lift.py` extends the [quartic construction](P4_BODY_DIAGONAL_LIFT.md)
to degree five. It accepts **any eighteen** interior quartic Bernstein divergence
coefficients on the body diagonal `(0,0,0)`–`(1,1,1)` and returns a continuous
piecewise-quintic vector field on `[0,2] × [0,1]²` with those traces. Every other
edge divergence and both target endpoints remain zero; every cell has zero mean;
the field has zero patch boundary trace.

This completes degrees four and five for this single local edge class in #14999.
It does not complete the other classes, the full boundary census or global theorem.
The positive-x neighbor is fixed and must fit in the domain. No sponsor/prize action
or theorem-wide certification is implied.

## Run or reuse

```sh
python research/ridgway_freudenthal/p5_body_diagonal_lift.py \
  --trace 1 -2 3 -4 5 -6 7 -8 9 -10 11 -12 13 -14 15 -16 17 -18 \
  --output /tmp/quintic-body-diagonal-velocity.json
```

Python 3.10+, standard library only. Output must be a new file. Omit `--trace` for
the reusable operator alone; programmatic callers can cache `construct()` and use
`apply(operator, trace)` for each target. Integers and exact rational strings are
accepted; floats and booleans are not accepted by `apply`.

Targets are cell-major in the unchanged six-cell Kuhn order, then high-endpoint
power `j=1,2,3`. They are coefficients of the degree-four edge modes with endpoint
powers `(4-j,j)`, not point values. The exact cell and barycentric index accompanies
each coordinate in the output. `nodes_times_five` records five times each shared
reference Bernstein node; velocity values are quintic Bernstein coefficients.
The sparse basis uses `[vector_coefficient_row, target_column, rational_value]`.
Omitted boundary coefficients are zero.

## Construction and source compatibility

The existing exact protected-map elimination is reused. Its geometry helper now
takes a degree argument, with degree four retained as the default. There are 64
interior scalar nodes and 192 vector unknowns for the raw quintic field. The
114 protected edge rows have rank 60; adjoining the eighteen target rows gives
rank 78. Exact elimination constructs `R` with `P R=0` and `T R=I_18`, checking
all columns. Shared physical Bernstein keys enforce continuity, while omitted
cube-face keys enforce zero boundary trace as in the quartic derivation.

Thus every possible eighteen-coordinate vector has a local protected realization.
In particular the endpoint-zero trace of any global quintic divergence is covered;
there is no additional source compatibility relation to assume for this class.

The raw field is extended by zero to the adjacent cube. Degree-four divergence
has 35 Bernstein coefficients of equal mean weight `1/35`, so its twelve cell
means are calculated exactly. Their sum is zero because the field has zero
boundary trace. The unchanged quartic mean-repair operator produces the desired
correction in degree four. Embed that correction in the quintic space using

```
c^5_alpha = sum_i (alpha_i / 5) c^4_(alpha-e_i),    |alpha|=5.
```

This is the Bernstein degree-elevation identity and represents the **same
polynomial field**. It follows by multiplying each degree-four Bernstein term by
`sum_i lambda_i=1` and collecting degree-five terms. The code checks that elevation
gives the same coefficient whenever two cells share a node. Consequently it retains
continuity, zero boundary trace, edge invisibility and the correction's cell means.
Subtracting the elevated correction from the raw field yields the requested map.

The final combined 432×18 matrix has 1,763 nonzero rational entries. Construction
checks all 264 edge rows and all twelve cell-mean rows on every target column before
publishing output. These are identities of the returned combined polynomial field,
not floating-point rank evidence or assumptions about separately assembled pieces.

## Bound and exact execution

The largest squared row norm of the combined coefficient matrix is `276/1225`.
The quartic guide's Bernstein/Jensen/Cauchy–Schwarz argument applies with derivative
factor five. With patch volume two, three vector components, four barycentric
terms, and `sum_i |grad(lambda_i)|²=6`, it gives

```
|L_5 y|_H1² <= 2 * 3 * 25 * 6 * 4 * (276/1225) ||y||_2²
            = (39744/49) ||y||_2².
```

This is a conservative reference-patch bound in trace-coefficient norm. It is not
the external manuscript's optimized pressure-L2 constant. Translating and scaling
the field as `v_h(x)=h L_5 y((x-a)/h)` preserves divergence traces and scales the
squared seminorm by `h³`. Other patch orientations, neighbor selection, all-edge
assembly and the remaining source-envelope census are not implemented here.

The command above ran on Python 3.12.14/Linux with exit 0 and printed
`CONSTRUCTED: target dimension 18, 432 unknowns, 1763 nonzero coefficients`.
No new test framework, fixtures, workflow, third-party dependency or benchmark
campaign was added. The existing Kuhn geometry, protected-map solver and local
mean-repair operator retain their attribution. Background target/protection
formulation: Alfyorov, September 2, 2026, sections 3–4/Table 1,
https://doi.org/10.21203/rs.3.rs-10887173/v1. This independently reconstructed map
does not replay or certify that manuscript's entire finite certificate package.
