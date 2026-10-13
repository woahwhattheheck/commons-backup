# Sources

This lane targets the current Conjectures.io Erdős 412 task and packages the elementary strict-growth fact for the sum-of-divisors orbit into a reusable Lean lemma.

- Problem page: https://conjectures.io/problems/erdos412-erdos-412
- Pinned task repository: https://github.com/conjectures-io/conjectures-tasks/tree/main/pool/tier-1/erdos-412-formalized
- Formal source module: https://github.com/google-deepmind/formal-conjectures/blob/8432eac998110a563e03df65a28c117e97c8c142/FormalConjectures/ErdosProblems/412.lean
- Mathlib arithmetic-function implementation used for the handoff: https://github.com/leanprover-community/mathlib4/blob/94ef6b89544e58e90f119da869f3fb48d1da0f4c/Mathlib/NumberTheory/ArithmeticFunction/Misc.lean

Mathematical argument: for `n ≥ 2`, both `1` and `n` are distinct divisors of `n`. Therefore `σ(n)`, the sum of all positive divisors, is at least `1 + n`, hence strictly larger than `n`. Iterating preserves the `≥ 2` domain and makes every orbit strictly increasing. This does not resolve the conjecture that every two such orbits intersect.
