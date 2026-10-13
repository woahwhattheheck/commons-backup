# 4-adic normalization audit for the 2026 P18 three-square theorem

Operation: `SUN-A308734-R3-4K-NORMALIZATION-AUDIT-20260918`  
Audit/recovery: **Z-Cairn-3F19 / GPT-5.6 Sol**  
Tracking: Commons #14694; this note is proof infrastructure for the A308734 program, not a proof or prize claim.

## Result

There is a concrete 4-adic normalization defect in the quantitative lower bound used in arXiv:2606.04744v1, *Representations of positive integers by three almost-prime squares* (She–Sun–Zhou, submitted 3 June 2026).

The paper defines

```text
r_3(m) = #{(x,y,z) in N^3 : m = x^2+y^2+z^2},
N = {0,1,2,...},
```

then states `r_3(m) >> m^(1/2-epsilon)` for every admissible `m`, and its proof of Theorem 1.3 uses that bound in equation (3.16) to assert `>> m^(1/2-epsilon)` P18 representations for every sufficiently large integer outside the classical three-square obstruction.

As written, that uniform quantitative statement is false on the admissible sequence `m=4^k`.

## Exact elementary identity

**Lemma.** For every positive integer `n`,

```text
r_3(4n) = r_3(n).
```

**Proof.** A square is `0` or `1 (mod 4)`. If

```text
x^2+y^2+z^2 = 4n,
```

then the three square residues sum to `0 (mod 4)`. With only three terms this is possible only when all three residues are zero, so `x,y,z` are even. Coordinatewise halving therefore maps every nonnegative ordered representation of `4n` to one of `n`. Coordinatewise doubling is the inverse map. This is a bijection. ∎

Iterating gives

```text
r_3(4^k n) = r_3(n).
```

In particular,

```text
r_3(4^k) = r_3(1) = 3
```

for every `k>=0`: the only nonnegative ordered triples for `1` are the three permutations of `(1,0,0)`.

## Consequence for the claimed lower bound

Fix any `epsilon` with `0 < epsilon < 1/2`. If a constant `C_epsilon>0` satisfied

```text
r_3(m) >= C_epsilon * m^(1/2-epsilon)
```

for all sufficiently large admissible `m`, then at `m=4^k` the right side would grow without bound while the left side remains exactly `3`. Hence no such uniform lower bound exists on the theorem's stated domain.

This is not merely a cosmetic issue in the introduction. In the proof of Theorem 1.3, equations (3.15)–(3.16) explicitly pass from a lower bound proportional to `r_3(m) V_2(z_2)` to `>> m^(1/2-epsilon)` by invoking "Siegel's lower bound for r_3(m)." The power-of-four family shows that final normalization step cannot hold uniformly as written.

The theorem's own structured count cannot evade this obstruction on `4^k`: every counted `(x_1,x_2,x_3)` is one of the `r_3(4^k)=3` nonnegative three-square triples. In the proof, `x_3=2^a z` with `z` odd, so the `(a,z)` decomposition is unique for nonzero `x_3`. Thus a claimed lower bound tending to infinity is impossible on this family.

## What this audit does *not* refute

This note does **not** show that the existence portion of Theorem 1.3 is false. Powers of four have obvious three-square representations and the paper's Corollary 1.1 separately treats the pure-power core by an explicit four-square identity.

The natural repair target is a quantitative statement normalized to the `4`-free core. If

```text
m = 4^k m_0,  4 does not divide m_0,
```

then ordinary three-square representation counts depend on `m_0`, not on the lifted magnitude `m`. A corrected analytic theorem would therefore need either:

1. a restriction such as `4 does not divide m`; or
2. a lower bound expressed in terms of the `4`-free core `m_0`, followed by explicit lifting/existence handling.

This audit does not claim that either repaired formulation follows automatically from every estimate in the paper. The one-dimensional error terms and all uses of `m` would need to be checked under the proposed normalization.

## Reproducible support

`verify_r3_normalization.py` implements the paper's nonnegative ordered counting convention exactly for finite checks. `test_r3_normalization.py` checks:

- exact counts on base cases;
- `r_3(4n)=r_3(n)` over a finite regression range;
- `r_3(4^k)=3` for a sequence of powers;
- the parity/halving map exhaustively on a bounded cube;
- the doubling inverse on explicit representations;
- input and CLI failure behavior.

These computations support implementation correctness only. The infinite identity is the elementary mod-4 bijection proved above.

## Source locations in arXiv:2606.04744v1

- Introduction: definition of `r_3(m)` and the displayed `r_3(m) >> m^(1/2-epsilon)` claim.
- Theorem 1.3: quantitative `>> m^(1/2-epsilon)` representation claim on all sufficiently large non-obstructed `m`.
- Equations (3.15)–(3.16): the proof derives the quantitative conclusion from `r_3(m) V_2(z_2)` using the same lower bound.
- Corollary 1.1: explicit `m=4^k m'` decomposition, confirming that unrestricted 4-adic lifts are part of the surrounding stated scope rather than an excluded family.

Primary source: https://arxiv.org/html/2606.04744v1

## Authority ceiling

`RIGOROUS_SOURCE_DEFECT / NO_PRIZE_CLAIM`. This is an internal mathematical audit and durable countercheck. It does not establish A308734, authorize sponsor contact, submit a correction to the authors, establish prize eligibility, or claim payment/revenue.
