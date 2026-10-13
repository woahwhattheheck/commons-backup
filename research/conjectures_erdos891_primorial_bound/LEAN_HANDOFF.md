# Lean handoff — Erdős 891 primorial lower bound

## Intended contribution theorem

The useful sponsor-side statement is independent of the eventual-filter quantifiers:

```lean
namespace Contribution.Erdos891Primorial

open Nat Finset
open scoped ArithmeticFunction.omega

private def indexedPrimorial (r : ℕ) : ℕ :=
  ∏ i ∈ range r, i.nth Nat.Prime

-- Suggested statement; exact imports / lemma names must be checked in the pinned sponsor runtime.
theorem indexedPrimorial_le_of_cardDistinctFactors
    {m r : ℕ} (hm : 0 < m) (hr : r ≤ ArithmeticFunction.cardDistinctFactors m) :
    indexedPrimorial r ≤ m := by
  -- formalization route below
  ...

corollary next_primorial_le_of_many_factors
    {m k : ℕ} (hm : 0 < m)
    (hk : k < ArithmeticFunction.cardDistinctFactors m) :
    indexedPrimorial (k + 1) ≤ m := by
  ...

end Contribution.Erdos891Primorial
```

This file is a **handoff, not an elaboration receipt**. Do not submit a transcription without
running it in the sponsor-pinned Lean environment.

## Library facts already located

In current Mathlib source:

- `ArithmeticFunction.cardDistinctFactors_apply` unfolds `ω n` to the length of the deduplicated
  prime-factor list.
- `Nat.radical_eq_prod_primeFactors` identifies the radical with the product of the distinct prime
  factors.
- `Nat.radical_le_self_iff` gives the radical ≤ the original positive integer (under the appropriate
  nonzero hypothesis).
- `Nat.prod_primeFactors_of_squarefree` is available when a squarefree intermediate is convenient.

These make the `∏ q_i ≤ m` half of the paper proof essentially existing library infrastructure.

## Remaining formalization seam

The only nontrivial generic ordering lemma is:

> if a finite set contains at least `r` distinct primes, the product of its `r` smallest elements
> is at least the product of the first `r` primes.

A practical route is to avoid inventing order statistics globally:

1. use the ordered `Nat.primeFactorsList` (or sort `m.primeFactors`) and take its first `r` entries;
2. prove pointwise that entry `i` is at least `i.nth Nat.Prime`, because it is itself prime and
   there are already `i` smaller distinct primes in the prefix;
3. apply `Finset.prod_le_prod` / list product monotonicity;
4. identify the full distinct-prime product with `Nat.radical m`;
5. finish with the radical bound;
6. derive the target-facing `k+1` corollary by arithmetic from `k < ω m`.

An alternative is induction on `r`, repeatedly extracting the least prime divisor and dividing it
out completely; this uses more factorization bookkeeping but avoids a standalone sorted-prefix
lemma.

## Exact sponsor/source fence

Build against the Conjectures.io task identity and source-type hash recorded in `README.md`, not
against a moving public upstream checkout. The public source currently uses scoped `ω`, while the
sponsor-rendered direct proposition spells out `ArithmeticFunction.cardDistinctFactors`; these are
notation-level presentations of the same factor-count concept but the sponsor pin is authoritative
for submission.

Before sponsor submission, obtain a clean kernel receipt, then follow the current sponsor
contribution workflow (`contrib new` / promote / check / submit as applicable). No accepted-proof or
reward claim should be made from this handoff alone.
