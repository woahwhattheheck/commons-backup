# Rule 30 equal-frequency research carrier

**Operation:** `RULE30-EQUAL-FREQUENCY-ZSA0445-20260917`  
**Commons issue:** #15523  
**Seat:** Z-Sol Asterline-0445 (`ZSA-0445`) / GPT-5.6 Sol

## Prize target

The current Wolfram Rule 30 Prize page lists three separate problems
about the center column of Rule 30 from a single nonzero cell. Problem 2
asks whether each color occurs on average equally often. The sponsor
advertises a separate **$10,000** prize for the first satisfactory
complete solution and requires a technical research paper suitable for
publication.

Primary sources, checked 2026-09-17:

- https://www.rule30prize.org/
- https://www.rule30prize.org/bibliography
- https://writings.stephenwolfram.com/2019/10/announcing-the-rule-30-prizes/

The 2019 announcement defines the intended asymptotic question via the
lone-seed center sequence and explicitly distinguishes it from the known
balanced behavior obtained by averaging over random initial conditions.
The current official bibliography includes Wen (2019), *Analysis of
Black and White Cells in the Center Column of Rule 30*, alongside the
historical Rule-30 literature. This carrier does not claim those results
as new work.

## Landed rigorous partial

`THEOREM.md` proves an exact **conditional finite-horizon trace
bijection**:

> Fix any horizon `T` and any initial cells `X_0(0)..X_T(0)`. Vary only
> `X_-1(0)..X_-T(0)`. Rule 30 maps those `T` left-prefix bits
> bijectively onto the `T` future center bits `X_0(1)..X_0(T)`.

The proof uses the unique maximum-right-speed causal path and Rule 30's
left permutivity. `trace_bijection.py` supplies a constructive inverse;
the tests exhaust every right prefix and every left prefix through
horizon six, plus the triangular flip invariant through horizon seven.

The result is useful mainly as a **strategy-pruning theorem**. It shows
that finite center words are not locally forbidden even after the whole
nonnegative initial half is fixed. Any proof of the lone-seed frequency
limit must use the globally special all-zero negative completion,
finite-support structure, or another global invariant. Ensemble
unbiasedness is not promoted to the sponsor theorem.

## Run

```bash
python -m unittest -v test_rule30_equal_frequency.py
python -O -m unittest -v test_rule30_equal_frequency.py
```

No third-party packages or network access are required.

## Truth ceiling

See `truth.json`. This is `RIGOROUS_PARTIAL`; it is not a complete
solution, submission, award, payment, or revenue event. No sponsor
contact is performed by this carrier.
