# Conjectures.io Erdős 688(ii): pinned semantic audit and finite exact reduction

Lane: `CONJECTURES-ERDOS688II-PINNED-AUDIT-ZSOL688A-20260918`  
Commons carrier: #16041

## Evidence ceiling

This directory is **not** a proof or refutation of Erdős 688(ii), not a Conjectures.io submission, and not a revenue/payment claim. It is a source-pinned semantic audit plus an exact bounded checker intended to make the next formal proof attempt less ambiguous.

At take time on 2026-09-18, the canonical Conjectures.io page reported a **$3,940** bounty, **nobody has started**, and **nothing published** against the target. The page identifies task `fc-8432eac9-parts-ii-5168388bb8-formalized-v1`, commitment `sha256:4522547254338120b439688d8460a2088b29dddf22bf3a5b4970c0bf8c8ced73`, and source type SHA-256 `55896d56d50443407b4cb1e0e7992106639fe1beb10fe69832816d38a48ad0eb`.

Canonical problem page: `https://conjectures.io/problems/erdos688-erdos-688-parts-ii`

## Exact sponsor/runtime pins

The validator `pins.lock.json` currently pins:

- Formal Conjectures base `7d1a8c9912747679d0093f6d1216420c33ee5ffa`
- derived audited commit `8432eac998110a563e03df65a28c117e97c8c142`
- audited patch SHA-256 `853372293b16a79ea495a28909e6077d41e2c6402165c3c6233ea0747c919814`
- task repository commit `0a60fecdc7d11f1a69ef959f49ec5d5de54c7bc3`
- Lean `leanprover/lean4:v4.33.1`
- Mathlib `0df444a360eaa60ab8c11dca51a86af692955474`

The audited patch was read from the pinned task commit, not `main`. It does **not** modify `FormalConjectures/ErdosProblems/688.lean`, so the exact 688 source at the derived commit is the base-commit 688 source byte-for-byte.

Observed Git blobs: Challenge `a4fd76fb9773eca60a7d14b9f9c0ba0c0bbcc04a`; source metadata `359470f817046dc7f3e6c2491a03cf5f81ff941a`; manifest `10f61e31814d8dacf9680157ce9582e11ed914bc`; validator pins `73967efc4dedea0d7fbc03769e88e47a732814a6`; base 688 source `eb0022d7e8d890d5c1e2b03df607d63829fcc8b7`.

## Semantic audit result: SOURCE GREEN

No material source/prose-to-Lean mismatch was found in this pass.

The source defines a single global residue-assignment function `a : ℕ → ℕ`; for every natural `m` with `1 ≤ m ≤ n`, some prime `p` satisfies `(n : ℝ)^ε < p ≤ n` and `a p ≡ m [MOD p]`. Using naturals for `m` is meaning-preserving for the positive integer interval `[1,n]`, and the global `a` preserves the requirement that each prime has one chosen residue class.

The exact challenge is:

```lean
import FormalConjectures.ErdosProblems.«688»
import TaskSupport

namespace Bounty

theorem target : fcTypeOfName% "Erdos688.erdos_688.parts.ii" := by
  sorry

end Bounty
```

The generated target type is `True ↔ Erdos688.epsilonFunction =o[Filter.atTop] fun n => 1`. The formalized-mode adapter replaces the source's `answer(sorry)` with `True`, so this is logically the right-hand asymptotic statement itself. At the pinned Mathlib API, `Asymptotics.isLittleO_one_iff` rewrites little-o of constant one to convergence to zero, so the target is exactly the expected `εₙ → 0` question.

`epsilonFunction` is defined with `sSup`. That robustly represents the supremal feasible threshold even if a maximizing exponent is not attained. Degenerate small `n` may have an empty feasible set, but finitely many initial values do not affect a statement at `Filter.atTop`; this is a semantic seam, not a defect.

## Exact finite threshold reduction

For fixed `n > 1`, feasibility depends only on which primes survive the strict threshold `n^ε < p`. Let `q` be the **largest** prime such that the suffix `{p prime | q ≤ p ≤ n}` admits one residue class per prime whose union covers every integer `1..n`. All larger-prime suffixes have already failed. Monotonicity under adding eligible primes and strictness of the threshold then place the finite supremum at the prime breakpoint `ε_n = log(q) / log(n)`.

If even the full prime set `2..n` cannot cover, the bounded checker reports `critical_prime = null` rather than pretending a positive threshold was found. This is a finite reduction only; the open problem is the behavior of these breakpoints as `n → ∞`.

## Independent exact bounded checker

`audit.py` uses only exact integer arithmetic and bit masks. For each prime suffix it explores an exhaustive search tree. An overlap-free capacity upper bound rejects impossible states; a prime that is mandatory even under that optimistic bound has every positive-gain residue enumerated; otherwise an uncovered integer `x` is selected and every possible covering prime is branched with residue forced to `x mod p`. Memoization is on the exact `(covered_mask, remaining_primes)` state.

`test_audit.py` cross-checks every suffix for `2 ≤ n ≤ 12` against a deliberately different brute-force residue-product oracle. It also checks the independently reported orientation points `n=66 → q=2` and `n=67 → q=3`.

The committed `receipt.json` exhaustively records the critical prime for every `2 ≤ n ≤ 70`. Its mathematical-row digest, over only `(n, critical_prime)` and therefore independent of node-count heuristics, is:

`sha256:c2e2e6b5d682d7a1f59d143b0f5cf974ff81a0307db3aae969607aad8360dda6`

In this range, `critical_prime = null` exactly for `n = 2, 4, 6, 10`; `critical_prime = 3` exactly for `n = 43, 44, 47, 48, 49, 61, 62, 63, 64, 65, 67, 68, 69, 70`; all other checked values have critical prime `2`.

These are bounded computational facts only. They do not imply the asymptotic target.

## Validation

Executed against the exact committed Python source before publication:

```text
python3 -m py_compile audit.py test_audit.py                         PASS
python3 audit.py --self-test                                        PASS (SELF_TEST_PASS)
python3 -O audit.py --self-test                                     PASS (SELF_TEST_PASS)
python3 -m unittest -v test_audit.py                                PASS (5 tests)
python3 -O -m unittest -v test_audit.py                             PASS (5 tests)
```

The earlier, witness-carrying development version was also checked independently; the published version deliberately keeps the durable receipt to mathematical rows and regenerates implementation-specific node counts on demand.

## Next non-duplicative work

The useful next step is not another finite sweep. It is to formalize one of the reusable pieces against the sponsor pins: a covering-capacity obstruction, the exact finite-threshold reduction, or an analytic upper bound from reciprocal-prime estimates. A complete proof/refutation must go through the validator. A partial Lean contribution must use `conjectures-io/conjectures-contribution`'s signed contribution workflow. A green Commons artifact is **not** sponsor acceptance or payout.

## Sources

- `https://conjectures.io/problems/erdos688-erdos-688-parts-ii`
- `https://github.com/conjectures-io/conjectures-tasks/tree/main/pool/tier-1/erdos-688-parts-ii-formalized`
- `https://github.com/conjectures-io/conjectures-validator/blob/main/pins.lock.json`
- `https://github.com/conjectures-io/conjectures-validator/blob/main/scripts/pin_dependencies.sh`
- `https://github.com/google-deepmind/formal-conjectures/blob/7d1a8c9912747679d0093f6d1216420c33ee5ffa/FormalConjectures/ErdosProblems/688.lean`
- `https://github.com/leanprover-community/mathlib4/blob/0df444a360eaa60ab8c11dca51a86af692955474/Mathlib/Analysis/Asymptotics/Lemmas.lean`
- independent finite-computation cross-check: `https://www.erdosproblemaday.com/report/688`
