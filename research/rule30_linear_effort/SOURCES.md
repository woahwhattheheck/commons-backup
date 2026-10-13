# Source snapshot and literature boundary

Snapshot date: 2026-09-17.

## First-party prize sources

1. Wolfram Rule 30 Prizes — https://rule30prize.org/
   * still lists Problem 3 as: whether computing the nth center-column cell
     requires at least O(n) computational effort;
   * requires definite, precise arguments and a technical research paper
     suitable for publication;
   * prize result/acceptance/payment are separate later states.

2. Stephen Wolfram, *Announcing the Rule 30 Prizes* (2019) —
   https://writings.stephenwolfram.com/2019/10/announcing-the-rule-30-prizes/
   * describes direct evolution as O(n^2) individual cell updates;
   * asks whether the nth center value can be obtained in less than O(n) work;
   * uses Rule 150 as the shortcut comparison;
   * proposes a Turing-machine model with the digits of n on the tape;
   * explicitly notes that reading all input digits costs only O(log n);
   * separately displays the finite-limsup-over-n predicate recorded in
     `THEOREM.md`.

3. Official bibliography — https://rule30prize.org/bibliography/
   The current list is primarily Rule-30 structure/randomness literature. This
   carrier does not treat presence on that bibliography as a prediction lower
   bound.

## Complexity-literature boundary

There are cellular automata for which *general prediction from variable initial
data* is P-complete, and there is broad literature on computational
irreducibility. Those results concern a different input problem from the
specific map

`binary n -> Rule30(lone_seed, time=n, center)`.

A reduction is required before they can say anything decisive about this prize
target. In particular:

* arbitrary-initial-state prediction hardness is not automatically fixed-seed
  index-prediction hardness;
* inversion hardness is not center-bit prediction hardness;
* chaotic/statistical behavior is not a time lower bound;
* a widening dependency cone is not a time lower bound (Rule 150 supplies an
  exact counterexample).

This distinction is a guardrail against importing a celebrated but inapplicable
complexity theorem as a prize proof.
