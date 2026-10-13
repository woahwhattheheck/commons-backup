# Rigorous partial results — Rule 30 Prize Problem 3

Operation: `RULE30-LINEAR-LOWERBOUND-ZRH1546-20260917`

This note records what is actually proved in this carrier. It does **not** prove
the Rule 30 prize theorem.

## Lemma 1 — the published prose and displayed predicate are not equivalent

Let `T(n)` be the running time of an exact predictor.

Three asymptotic statements must remain distinct: (A) no exact predictor has
`T(n)=o(n)`; (B) every exact predictor has `T(n)=Omega(n)`; (C) no exact
predictor has finite `limsup T(n)/n`, equivalently no exact `O(n)` predictor.
Neither (A) nor (C) is synonymous with (B).

The displayed formal predicate instead rules out an exact machine satisfying

`limsup_{n -> infinity} T(n)/n < infinity`.

For nonnegative runtimes, finite limsup implies an eventual constant upper bound
`T(n) <= C n`, i.e. an `O(n)`-type upper bound. Hence the displayed predicate
rules out both sublinear and ordinary linear-time exact predictors.

Two separators make the distinctions explicit.

* Let `S(n)=n` on powers of two and `floor(sqrt(n))` otherwise. Then `S`
  is not `o(n)` because its ratio has limsup 1, but it is not `Omega(n)`
  because its ratio tends to zero along non-powers. Thus (A) does not imply (B).
* Let `Q(n)=n^2` on powers of two and `floor(sqrt(n))` otherwise. Then
  `Q` is not `O(n)` but also not `Omega(n)`. Thus the per-machine
  properties behind (B) and (C) differ. Conversely `T(n)=n` is
  `Omega(n)` and `O(n)`.

Therefore every result must name A, B, or C explicitly; the generic phrase
“linear lower bound” is insufficient here.

`asymptotic.py` makes this distinction executable for exact power/log families
and includes a non-smooth O(n), non-o(n) witness to prevent accidental
finite-sample smoothing from replacing asymptotic reasoning.

## Lemma 2 — causal-cone size alone cannot prove the desired lower bound

A radius-one elementary cellular automaton has a width `2n+1` backward cone for
the time-n center cell. That does **not** imply that evaluating the center bit
requires work proportional to the cone.

Rule 150 is an exact counterexample. Over `F_2`, encode a row as a Laurent
polynomial. From a lone seed,

`P_n(x) = (x^-1 + 1 + x)^n`.

Write the binary expansion `n = sum_{k in S} 2^k`. Frobenius in characteristic
two gives

`(x^-1 + 1 + x)^(2^k) = x^(-2^k) + 1 + x^(2^k)`,

so

`P_n(x) = product_{k in S} (x^(-2^k) + 1 + x^(2^k))`.

The constant term is obtained by choosing the `1` from every factor. There is no
second way to obtain exponent zero: if a nonempty signed sum of distinct powers
of two were zero, the largest selected power would exceed the sum of all
smaller selected powers. Thus the constant coefficient is exactly one for every
n.

So Rule 150 has the same linearly widening geometric cone, yet its lone-seed
center column is identically black and is computable without evolving the cone.
Any valid Rule 30 lower bound must use structure specific to the center-bit
function, not cone area/width by itself.

`rule30.py` independently simulates elementary rules and checks this closed form
for bounded horizons as a falsifier. The proof above, not the finite check, is
the result.

## Lemma 3 — eventual periodicity gives an O(log n) binary-input predictor

Suppose a binary sequence has a finite prefix of length `N` and thereafter a
period `p`. Both `N` and `p` are constants of the machine.

On binary input `n`, one left-to-right scan can maintain `n mod p` in a
finite-state residue register. A finite-state comparison with the fixed
threshold `N` selects either the prefix table or the periodic table. The scan
takes `Theta(log n)` input-symbol steps.

Therefore, if the Rule 30 center column were eventually periodic, an exact
`O(log n)` predictor would exist in the binary-input Turing-machine model
described by the sponsor. Any genuine lower bound excluding `o(n)` predictors
would consequently imply nonperiodicity. This is a conditional implication,
not a proof that Rule 30 is nonperiodic.

`eventually_periodic_predictor` is a constructive executable model of this
reduction.

## Model boundary

The sponsor explicitly describes putting the **digits of n** on a Turing-machine
tape. The input length is therefore `Theta(log n)`. Reading every digit costs
only `Theta(log n)`, matching the sponsor's own observation. Input-reading
arguments alone cannot bridge the gap to an `Omega(n)` lower bound.

General prediction hardness for arbitrary cellular-automaton initial conditions,
P-completeness of other automata, chaos, statistical randomness, and Rule 30
inversion hardness do not automatically imply a lower bound for this *fixed
lone-seed one-bit function*. Any imported complexity result must provide an
explicit reduction to this exact function.

## What remains open

The hard step remains untouched by these model-cleanup lemmas: prove one
explicitly named target A, B, or C above, or exhibit a correct algorithm that
refutes the corresponding target. The three statements are not interchangeable.

No finite timing curve, symbolic-expression growth plot, causal-cone count, or
generic CA hardness statement is promoted to that conclusion here.
