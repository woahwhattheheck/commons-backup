# Erdős 686 / variant “four”: length-5 reduction

This directory is a bounded, non-duplicative continuation of the three published
Conjectures.io pieces for `erdos-686-variants-four`. Those published pieces
already cover:

- `k = 2`: impossibility;
- `k = 3`: reduction to a cubic curve (plus the excluded overlap point);
- `k = 4`: impossibility.

This carrier starts at **`k = 5`**. It does not restate those lemmas.

## Exact reduction

Let

```text
P(x) = (x+1)(x+2)(x+3)(x+4)(x+5)
Q(t) = t^5 - 5t^3 + 4t.
```

Pairing factors around the center gives, over the integers,

```text
P(x)
= (x+3)((x+3)^2-1)((x+3)^2-4)
= Q(x+3).
```

Therefore the `k = 5` window equation

```text
P(m) = 4 P(n)
```

is **equivalent** to

```text
Q(m+3) = 4 Q(n+3).
```

The sponsor-side disjointness condition becomes `m >= n + 5`.

`P` is strictly increasing on nonnegative integers. Moreover

```text
P(2n+10) > 2^5 P(n) > 4 P(n),
```

because for every `i=1,...,5`, `2n+10+i > 2(n+i)`. Hence, for each fixed
`n`, an eligible `m` exists iff binary search finds it in the exhaustive integer
bracket `[n+5, 2n+10]`.

## Reproducible finite evidence

`erdos686_len5.py --limit 1000000` checks every `n` from 0 through 1,000,000
using exact Python integers. The committed receipt records:

- 1,000,001 values of `n`;
- 18,530,416 exact product comparisons;
- 0 eligible `k=5` witnesses;
- candidate-stream SHA-256
  `2ea1db918c0bc48835e03c98c67696d14d7af04e691ef3fe097a960d8a2afc68`;
- committed receipt SHA-256
  `71080b8d3cfb26097fd6127545fc93948e72fedf01e9b0f171d18173e0e2b8bc`.

The test suite cross-checks the binary-search result against brute force on a
smaller window and verifies the centered polynomial identity and the exhaustive
upper bracket.

## Connected inverse and new interval — October 4, 2026

[window_five_inverse.cjs](window_five_inverse.cjs) adds an exact fifth-root certificate,
a general five-window product locator, a ratio-four point classifier, and bounded
scans with complete compact records. The new bound
`(m+2)^5 < P(m) < (m+3)^5` leaves only the candidate
`m=floor((4P(n))^(1/5))-2`; exact equality and `m>=n+5` are still required.

One connected-runtime scan classified every new `n=1,000,001..1,010,000`.
All 10,000 candidates were disjoint and had positive product differences, with
zero equalities. It used 70,000 integer Newton iterations and 10,000 candidate
comparisons. Every new root/candidate and signed difference is retained in
[inverse_interval_1000001_1010000.json](inverse_interval_1000001_1010000.json).

[WINDOW_FIVE_INVERSE_API.md](WINDOW_FIVE_INVERSE_API.md) supplies the inverse and
integer-root derivations, exact API/record contract, source attribution, hard
bounds, full interval result and connected-runtime recipe. Published finiteness
is credited to Beukers, Shorey and Tijdeman; it supplies no usable cutoff in the
consulted statement. The original finite prefix was not rerun. Combining its
existing record with this new interval gives recorded negative coverage through
`n=1,010,000`, without a global length-five or arbitrary-length claim.

## Sponsor pins observed on 2026-09-18

Canonical page:
`https://conjectures.io/problems/erdos686-erdos-686-variants-four`

- observed closing bounty: **$3,324**;
- current page: 3 pieces / 8 lemmas;
- task id:
  `fc-8432eac9-variants-four-ae7cfb4a62-formalized-v1`;
- task commitment:
  `sha256:7ad397738b5b17c97fcc7e3a12b068f4ffe90614a06e7f802e79f9637cedf575`;
- source type SHA-256:
  `sha256:ba400ba0844a1182de84df5aa217255c4343091b3aec968e35793bb0e75e8db2`.

The sponsor contribution index blob read for deconfliction was
`dfe24f693a84ee556a6ebe1c9df505abf177232e`; the published script blob that
contains the k=2/k=3/k=4 window lemmas was
`2c6d213eac932c3103351908077e1f94cb384281`.

## Evidence ceiling

This is a reusable exact algebraic reduction plus finite negative evidence.
It **does not** prove the full Erdős 686/four conjecture, and it does not prove
the `k=5` case beyond the stated finite range. `candidate.lean` is a
sponsor-shaped handoff and must not be represented as verified until it is
elaborated in the sponsor-pinned Lean environment. No bounty, payment, or
sponsor acceptance is implied by this Commons artifact.
