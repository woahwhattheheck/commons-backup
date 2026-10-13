# Erdős 406 (`1,2` digits): general survivor-count reduction

This directory advances the **existing published sieve contribution** for the Conjectures.io target
`Erdos406.erdos_406.variants.one_two`.

It does **not** claim to solve Erdős 406. It isolates and proves on paper the all-depth counting
fact that the published contribution explicitly left as an observed pattern, and supplies an exact,
dependency-free finite regression plus a Lean formalization handoff.

## Exact target and parent contribution

Current target (read 2026-09-18):

- target: `Erdos406.erdos_406.variants.one_two`
- Lean type: `IsGreatest {n | n.isPowerOfTwo ∧ Nat.digits 3 n ⊆ [1, 2]} (2 ^ 15)`
- task id: `fc-8432eac9-variants-one-two-c89c5d71f6-formalized-v1`
- Formal Conjectures source commit: `8432eac998110a563e03df65a28c117e97c8c142`
- source type SHA-256: `450efb0b9baef627a7cec4dab22d8ed38fa7131f0216ef80f28f46f867522371`
- task commitment advertised by the canonical page:
  `9a2512c5a40d39b1c040f6f1ff42fddc6e79bd7ddd90af2cdc7fd56d2a1815cd`

The published parent contribution is
`55f755c7637d39f7508b20f872dd0c3ff56ff412161e42b7e4a95ac4287b5fcd`, titled
**“Erdős 406 (digits 1,2 only): positional bridge for Nat.digits, decidable reformulation,
3^m exponent sieve”**. Its `script.lean` SHA-256 is
`60ec18d4b0db79de81b5062de2233a289833b550ba0d93f545ef6f4d09208d65`.

That contribution proves the digit bridge and sieve engine, and checks only the finite statement
that, for `1 ≤ m ≤ 5`, exactly `2^m` exponent classes survive at modulus `3^m`. Its own prose
explicitly says the general `2^m` count is expected from `2` being a primitive root modulo `3^m`
but is **not proved there**. This carrier owns only that missing general counting structure.

## The all-`m` theorem

For `m ≥ 1`, put

```
q_m = 3^m
T_m = 2 * 3^(m-1) = φ(3^m).
```

For an exponent residue `0 ≤ r < T_m`, call `r` a *survivor* when every one of the first `m`
base-3 digits of `2^r mod 3^m` is nonzero. Equivalently, in the exact syntax of the published
sieve:

```
∀ i < m, 2^r % 3^m / 3^i % 3 ≠ 0.
```

Then

> **General survivor-count theorem.** For every `m ≥ 1`, exactly `2^m` residues
> `r ∈ {0, …, T_m-1}` survive.

This is a counting theorem about the sieve. It does not remove the surviving exponent classes and
therefore does not settle the original greatest-power conjecture.

## Proof

The proof has two independent ingredients.

### 1. `2` generates all units modulo `3^m`

First establish the stronger lifting congruence

```
2^(2*3^(m-1)) ≡ 1 + 3^m  (mod 3^(m+1))                    (★)
```

for every `m ≥ 1`.

The base case is `2^2 = 4 = 1 + 3 (mod 9)`. For the induction step write
`x = 2^(2*3^(m-1))`. The new exponent is three times the old one, so we need `x^3`.
If `x ≡ 1+3^m (mod 3^(m+1))`, then

```
x^3 - (1+3^m)^3
  = (x-(1+3^m)) * (x^2 + x(1+3^m) + (1+3^m)^2).
```

The first factor is divisible by `3^(m+1)` and the second is divisible by `3` because both
`x` and `1+3^m` are `1 mod 3`. Hence the difference is divisible by `3^(m+2)`. Meanwhile

```
(1+3^m)^3
 = 1 + 3^(m+1) + 3^(2m+1) + 3^(3m)
 ≡ 1 + 3^(m+1)  (mod 3^(m+2)),
```

since `m ≥ 1`. This proves (★) by induction.

Consequences of (★):

- `2^T_m ≡ 1 (mod 3^m)`, so the order of `2` modulo `3^m` divides `T_m`.
- More sharply, `3^m` divides `2^T_m-1` but `3^(m+1)` does not.
- Every proper even divisor of `T_m=2*3^(m-1)` has the form `2*3^j` with `j≤m-2`; applying
  (★) at depth `j+1` shows its power of `2` is **not** `1 mod 3^m`.
- Every odd exponent is `2 mod 3`, not `1 mod 3`.

Thus the multiplicative order of `2` modulo `3^m` is exactly `T_m`. Therefore

```
r ↦ 2^r mod 3^m,     0 ≤ r < T_m,
```

is a bijection from exponent residues onto the `T_m` unit residues modulo `3^m`.

### 2. The surviving unit residues are exactly `{1,2}`-words

Every residue `a` with `0 ≤ a < 3^m` has a unique fixed-width base-3 expansion

```
a = d_0 + d_1*3 + ... + d_(m-1)*3^(m-1),   d_i ∈ {0,1,2}.
```

The sieve condition is exactly `d_i ≠ 0` for every `i<m`; hence each `d_i` is independently
`1` or `2`. There are exactly `2^m` such words. Their least-significant digit is nonzero, so
none is divisible by `3`; all are units. By the bijection from step 1, each such residue has
exactly one exponent residue `r mod T_m`, and no other `r` survives.

Therefore the survivor count is exactly `2^m` for every `m≥1`.

## Exact executable regression

`sieve_count.py` independently verifies, for every `1 ≤ m ≤ 12`, all of the finite objects used
above:

1. the `T_m` powers `2^r mod 3^m` are pairwise distinct and equal the complete unit set;
2. the survivor image is exactly the set of fixed-width ternary words over `{1,2}`;
3. the survivor count is exactly `2^m`;
4. the lifting congruence (★) holds modulo `3^(m+1)`;
5. `v_3(2^T_m - 1)=m` as a redundant arithmetic control.

Across depths `m=1..12`, this traverses `531,440` exponent residues. At the largest depth,
`m=12`, it checks a period of `354,294` unit residues modulo `531,441` and exactly `4,096`
survivors.

Canonical receipt payload SHA-256:

```
532378d44f1725f21dce894c17f7e82fc823dd986059e6476b74ecbf19d2698a
```

Pretty-printed `receipt.json` file SHA-256:

```
510a1ec6e55da14d8a581c410586a774691cc992195077332f39626818dfe20f
```

Validation performed before publication:

```text
python -m unittest -v test_sieve_count.py       -> 9/9 PASS
python -O -m unittest -v test_sieve_count.py    -> 9/9 PASS
python -m py_compile sieve_count.py test_sieve_count.py -> PASS
python sieve_count.py --max-m 12 --pretty       -> receipt reproduced
```

## Evidence ceiling

- The all-`m` survivor-count argument above is an ordinary mathematical proof, but **not yet a
  Lean kernel receipt** in this environment.
- The executable regression is exact finite evidence only; it is not a proof by testing.
- This result strengthens the published sieve bookkeeping. It does **not** show that every
  exponent `k≥16` is eliminated by the sieve; the surviving classes still contain the open
  mathematical problem.
- No Conjectures.io solve, accepted contribution, bounty, payment, or revenue is claimed by this
  carrier.

See `LEAN_HANDOFF.md` for the minimal self-contained formalization plan and exact sponsor rules.
