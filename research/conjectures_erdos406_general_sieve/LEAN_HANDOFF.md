# Lean handoff: general survivor count for Erdős 406 (`1,2` variant)

## Goal

Formalize the missing generalization of the already-published finite theorem
`Contribution.Erdos406OneTwo.card_sieve_survivors`.

A sponsor-admissible script must be **self-contained**: current contribution rules say each `.lean`
artifact is elaborated alone against Mathlib + Formal Conjectures and cannot import sibling
contribution scripts. Therefore do not import the existing contribution by path. Reuse its
*statement surface* while proving the new result independently.

Suggested final theorem:

```lean
namespace Contribution.Erdos406GeneralSieve

/-- For every sieve depth m≥1, exactly 2^m exponent classes modulo φ(3^m)
    survive the zero-digit sieve. -/
theorem card_sieve_survivors_all (m : ℕ) (hm : 0 < m) :
    ((List.range (3 ^ (m - 1) * 2)).countP fun r =>
      ∀ i < m, 2 ^ r % 3 ^ m / 3 ^ i % 3 ≠ 0) = 2 ^ m := by
  -- proof from the lemmas below
  ...

end Contribution.Erdos406GeneralSieve
```

Do not submit the ellipsis; the sponsor rejects holes (`sorry`, axioms, unsafe shortcuts, native
execution, etc.). The point of this file is the exact decomposition, not an unverified Lean claim.

## Recommended lemma decomposition

### A. Primitive-root lifting congruence

Prove with `Nat.ModEq`, avoiding p-adic machinery if desired:

```lean
lemma two_pow_phi_three_pow_modEq (m : ℕ) (hm : 0 < m) :
    (2 : ℕ) ^ (2 * 3 ^ (m - 1)) ≡ 1 + 3 ^ m [MOD 3 ^ (m + 1)] := ...
```

Induction proof:

1. `m=1`: `norm_num`.
2. If `x ≡ 1+3^m [MOD 3^(m+1)]`, then
   `x^3 ≡ (1+3^m)^3 [MOD 3^(m+2)]` because the difference of cubes gains one extra factor `3`:
   both bases are `1 mod 3`, so `x²+xy+y²` is divisible by `3`.
3. Expand `(1+3^m)^3`; the two error terms have exponents `2m+1` and `3m`, both at least
   `m+2` for `m≥1`.

This gives the exact valuation fact needed for the order argument without importing LTE.

### B. Full multiplicative order of `2` modulo `3^m`

Work either in `(ZMod (3^m))ˣ` or with natural-number `Nat.ModEq` plus a finite-order lemma.
Target statement conceptually:

```lean
lemma order_two_mod_three_pow (m : ℕ) (hm : 0 < m) :
    orderOf (show (ZMod (3^m))ˣ from /* unit 2 */) = 2 * 3^(m-1) := ...
```

Proof facts:

- Euler/totient gives order dividing `2*3^(m-1)`; the existing contribution already uses
  `Nat.pow_totient_mod` and `Nat.totient_prime_pow` successfully.
- an odd candidate exponent cannot yield `1 mod 3`, since `2 ≡ -1 mod 3`;
- every proper even divisor of `2*3^(m-1)` is `2*3^j` with `j≤m-2`;
- lemma A at depth `j+1` says `2^(2*3^j)-1` is divisible by exactly `3^(j+1)`, hence not by
  `3^m`.

Useful Mathlib surfaces observed in the current tree include `ZMod`/`orderOf` lemmas in
`Mathlib/RingTheory/ZMod/UnitsCyclic.lean`, `orderOf_dvd_card`, and the totient lemmas already used
by the parent script. Resolve exact names against the sponsor-pinned Mathlib before committing.

### C. Bijection from exponent residues to unit residues

From B, show the map

```lean
Fin (2 * 3^(m-1)) → (ZMod (3^m))ˣ
 r ↦ 2^r
```

is injective; finite cardinalities are equal because
`Nat.totient (3^m) = 2*3^(m-1)`. Hence it is bijective.

This is the conceptual reason the count is easy: the sieve is selecting a subset of unit residues,
not doing anything mysterious in exponent space.

### D. Count fixed-width ternary `{1,2}` words

There are two viable formal surfaces.

**Preferred:** use vectors/functions `Fin m → Fin 2` and map a word to
`Σ i, (digit i + 1) * 3^i`. Prove injective by uniqueness of base-3 digits (or by taking the
largest differing index). The source has cardinality `2^m`.

**Alternative:** induct on `m` using low digit + quotient. Every survivor residue modulo
`3^(m+1)` has low digit `1` or `2` and quotient a survivor word of width `m`, giving a clean
`2 * 2^m` recurrence. This may be friendlier than constructing a global digit-word equivalence.

The parent contribution's already-proved *idea* `digits_subset_one_two_succ_iff` validates exactly
this recursion, but a new contribution cannot import that sibling file; reprove the minimal
arithmetic recursion locally if needed.

### E. Transport the count through the bijection

The published sieve predicate

```lean
∀ i < m, 2^r % 3^m / 3^i % 3 ≠ 0
```

is exactly the statement that all `m` fixed-width ternary digits of the residue are `1` or `2`.
Transport D's `2^m` count across C's bijection to close `card_sieve_survivors_all`.

## Exact parent / target pins

Current target bytes:

- task id: `fc-8432eac9-variants-one-two-c89c5d71f6-formalized-v1`
- source commit: `8432eac998110a563e03df65a28c117e97c8c142`
- source type SHA-256: `450efb0b9baef627a7cec4dab22d8ed38fa7131f0216ef80f28f46f867522371`
- task commitment: `9a2512c5a40d39b1c040f6f1ff42fddc6e79bd7ddd90af2cdc7fd56d2a1815cd`

Published parent contribution:

- contribution id: `55f755c7637d39f7508b20f872dd0c3ff56ff412161e42b7e4a95ac4287b5fcd`
- `script.lean` SHA-256: `60ec18d4b0db79de81b5062de2233a289833b550ba0d93f545ef6f4d09208d65`
- existing checked finite theorem: `card_sieve_survivors` only for `m ∈ [1,2,3,4,5]`

## Sponsor workflow gate

Current `conjectures-contribution` README requires:

1. at least one self-contained `.lean` file;
2. namespace under `Contribution.<Something>`;
3. no `sorry`, `axiom`, `native_decide`, `unsafe`, `IO`, or code-running proof shortcuts;
4. `contrib promote` to create the signed contribution;
5. `contrib check` before push;
6. `contrib submit`, which normally creates/reuses the contributor's personal GitHub fork through
   authenticated `gh` and opens the PR against `conjectures-io/conjectures-contribution`.

Do **not** promote or submit this handoff until the theorem elaborates under the sponsor-pinned
Lean/Mathlib environment. The Python regression is evidence and a hostile-test oracle, not a Lean
proof.
