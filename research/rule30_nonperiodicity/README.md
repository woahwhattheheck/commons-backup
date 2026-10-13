# Rule 30 nonperiodicity — period-two frontier

Operation: `RULE30-NONPERIODIC-FIRSTPROOF-CAIRNZ-20260917`  
Issue: #15314  
State: **RIGOROUS_PARTIAL / PRIZE THEOREM OPEN**

This carrier attacks Wolfram Rule 30 Prize Problem 1 without treating finite computation as an infinite proof. The target is the center column produced from the lone-seed initial condition. A complete proof that the center trace is not eventually periodic would qualify for the advertised $10,000 prize subject to the sponsor's review process; this carrier does **not** make that claim.

## What changed

A September 8, 2026 preprint by David L. Condrey proves the entire eventual-period-one case for every nonzero finite Rule 30 configuration and explicitly identifies eventual period two as the next unresolved case. This carrier starts there rather than duplicating that result.

The new executable piece is an exact bounded fiber engine for the two alternating traces `0101...` and `1010...`.

For support radius `w` and one of the two phases:

1. choose the `w` positive-side bits `x_1,...,x_w`;
2. Rule 30 left permutivity forces `x_-1,...,x_-w` one cell at a time if the center is to match the alternating trace through time `w`;
3. therefore every radius-`w` row that could remain alternating is among exactly `2^w` candidates for that phase, not `2^(2w+1)` arbitrary rows;
4. evolve each forced candidate exactly until its first mismatch.

`bounded_receipt.json` exhausts both phases for every radius `1..14`: **65,532 exact candidates** total. Every one escapes the alternating trace. The largest bounded horizon found is time index `19` (phase 0, radius 14). This proves the bounded statement for radius at most 14; it does not prove that an arbitrary finite configuration cannot alternate forever. The receipt is deterministically reproducible from `period2_fiber.py`.

## Exact reduction from eventual period two

A nonconstant binary sequence of period two is alternating. If a finite Rule 30 configuration `x` has an eventually period-two center trace beginning at time `T`, then `F^T(x)` is still finitely supported and has a **purely alternating** center trace from its time zero. Therefore it is sufficient to prove that neither alternating trace fiber contains a finite configuration.

That is the infinite target of this lane.

## First forced identities

Write

- `c_t = F^t(x)_0`,
- `l_t = F^t(x)_-1`,
- `r_t = F^t(x)_1`.

Rule 30 is

`c_(t+1) = l_t XOR (c_t OR r_t)`.

Under `c_(t+1) = 1 XOR c_t`, inversion gives

`l_t = c_(t+1) XOR (c_t OR r_t)`.

Hence:

- when `c_t=1`, `l_t=1`;
- when `c_t=0`, `l_t=NOT r_t`.

Pushing the same relation one cell farther left gives, at the same time `t`:

- if `c_t=0`, then `x_-2^t = x_1^t`;
- if `c_t=1`, then `x_-2^t = NOT(x_1^t OR x_2^t)`.

For the initial row this yields the tested depth-two completion formulas:

- phase `0`: `L1 = NOT R1`, `L2 = R1`;
- phase `1`: `L1 = 1`, `L2 = NOT(R1 OR R2)`.

These identities are exact but do not yet close period two.

## Run

```bash
python research/rule30_nonperiodicity/period2_fiber.py --max-radius 14 --output /tmp/rule30-period2.json
python test_rule30_period2_frontier.py
```

The unit test includes a second, dictionary-based Rule 30 oracle and checks the optimized integer-bitset engine against it; it also re-exhausts the exact small-radius frontier.

## Next theorem target

The missing inference is structural: show that for every eventually-zero positive right half, the unique alternating-trace left completion contains infinitely many ones (or derive an equivalent obstruction). A proof of that statement for both phases would exclude eventual period two for every nonzero finite Rule 30 orbit. Higher nonconstant periods would still remain before the full prize theorem.

No Wolfram submission, prize award, payment, receivable, or revenue event is represented here.
