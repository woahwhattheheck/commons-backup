# Erdős 1192 first piece: representation-energy lower bound

## Connected exact representation index — October 4, 2026

[ordered_representation_index.cjs](ordered_representation_index.cjs) adds bounded exact coefficient tables with per-sum counts, inclusive interval mass/energy, complete distribution pages and lexicographic witness rank/select. It follows ordered natural-number representations, including zero when supplied, repeated coordinates and set deduplication.

The actual new order-20 input is the retained ten-element set from Commons [#31157](https://github.com/woahwhattheheck/commons/pull/31157). Its `10^20` ordered tuples yield 1,195 represented sums in `[0,1200]`; all 1,201 counts, exact energy and constructed witnesses are saved in [r20_retained_set_representations.json](r20_retained_set_representations.json). The single construction used 12,621 coefficient cells and 111,490 additions.

[ORDERED_REPRESENTATION_API.md](ORDERED_REPRESENTATION_API.md) gives the public contract, exact recurrence and rank/select derivation, primary conventions and prior-report attribution, hard bounds, actual result, and connected-runtime recipe. This is a finite input result, with no infinite-basis or conjecture-proof claim.

## Original carrier record — September 18, 2026

The following record preserves the original Commons #16053 handoff and historical target capture. Its status and amount descriptions are historical observations.

This carrier advances the currently untouched Conjectures.io Erdős #1192 target without claiming to solve it. The sponsor's canonical page currently lists a **$3,757** close bounty, no attempts, and no published contribution pieces.

Pinned target captured for this lane:

- task: `fc-8432eac9-erdos1192-erdos-1192-abb86bc29e-formalized-v1`
- task commitment: `sha256:547f9ccecbebe2ce47b3e937020f6e36536a8c24ede2201b1c051a689d0c90cd`
- source type SHA-256: `sha256:deb84e4a73cad6e9d9b6f934a99d436ba2a0ba545694e0d16cca0f266636f5a8`
- formal target: `True ↔ ∀ r ≥ 2, ∃ A : Set ℕ, (∀ᶠ n in atTop, f_r A r n > 0) ∧ (∑_{n≤x} f_r(n)^2) = O(x)`
- source: `FormalConjectures/ErdosProblems/1192.lean`

The source also records the known solved `r = 2` case due to Ruzsa. Therefore the genuinely open burden begins at `r ≥ 3`; this carrier does not duplicate the known base case.

## Structural lemma

For any `A ⊆ ℕ`, positive integer `r`, and `m ≥ 0`, put `B = A ∩ [0,m]` and let `c_B(n)` be the number of **ordered** `r`-tuples from `B` summing to `n`. Then

```text
sum_n c_B(n) = |B|^r,

support(c_B) ⊆ [0, r*m],

(r*m + 1) * sum_n c_B(n)^2 ≥ |B|^(2*r).
```

The last line is exactly Cauchy-Schwarz on at most `r*m+1` possible sums. Since every tuple from `B` is also a tuple from `A`, `c_B(n) ≤ f_r(A,r,n)`. Consequently the Erdős-1192 target energy satisfies the finite lower bound

```text
(r*m + 1) * sum_{n≤r*m} f_r(A,r,n)^2 ≥ |A ∩ [0,m]|^(2*r).
```

This gives a useful necessary asymptotic condition: any eventual-basis witness with target energy `O(x)` must have counting function `|A ∩ [0,m]| = O(m^(1/r))`. Conversely, eventual coverage alone forces the complementary `Ω(m^(1/r))` scale by counting available ordered tuples. Thus any solution set must live on the sharp density scale `Θ(m^(1/r))`.

That density squeeze is not the open theorem, but it narrows the search space and translates the second-moment condition into a concrete additive-energy constraint.

## Exact finite regression certificate

`energy_certificate.py` is dependency-free and exact. It exhausts every subset of `[0,m]` for `m = 0..8` and every `r = 2..5`, recomputes every ordered representation count, checks `sum c_B = |B|^r`, verifies support `≤ r*m`, and checks the integer Cauchy inequality. The committed receipt binds the ordered case stream by SHA-256.

Reproduce from this directory:

```bash
python3 energy_certificate.py --write-receipt receipt.json
python3 -m unittest -v test_energy_certificate.py
python3 -O -m unittest -v test_energy_certificate.py
python3 -m py_compile energy_certificate.py test_energy_certificate.py
```

No floating point, randomization, network access, third-party package, or native solver is used.

## Sponsor handoff / evidence ceiling

`LEAN_HANDOFF.md` gives a sponsor-shaped decomposition for a Lean-enabled executor. This runtime did not have `lean` or `lake`, so no kernel-elaboration receipt is claimed. Before sponsor publication, the candidate lemmas must be restated against the exact pinned Formal Conjectures source, elaborated in the sponsor environment, and pass the current contribution checker.

This carrier is **not** a proof of Erdős #1192, is **not** sponsor-accepted, and is **not** a bounty/payment/revenue claim. It is a durable exact first-piece scaffold for an untouched paid target.
