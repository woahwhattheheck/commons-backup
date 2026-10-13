# Erdős 789: universal two-element separating subset

This is a bounded first-piece carrier for the Conjectures.io target
`Erdos789.erdos_789.variants.sq`. It does **not** prove the requested
asymptotic `h(n) = Θ(√n)`.

## Exact source / task pin

Canonical target observed 2026-09-18:

- problem: `erdos-789-variants-sq`
- target: `fcTypeOfName% "Erdos789.erdos_789.variants.sq"`
- source repository commit: `8432eac998110a563e03df65a28c117e97c8c142`
- source type SHA-256: `5f0475c69d1d1d8fe299a0db410a528e1ee8017f96eaf19609441e9bc257c04d`
- task id: `fc-8432eac9-variants-sq-e605ce6bf4-formalized-v1`
- task commitment: `sha256:e946ba46e17c8446833271e9ea81f341e79ce8493d19af039ebe01e69f713b73`
- sponsor task `Challenge.lean` Git blob: `77c49405c0dfdba7663167e8b032332e3f23c90e`

The source definition is:

`IsSubsetSumSeparatingCard n m` iff every `n`-element finite set `A ⊂ ℤ`
contains a finite `B ⊆ A` with `m ≤ |B|` such that equal sums of two
nonempty *subsets* of `B` have equal cardinality.

## New lemma

For every `n ≥ 3`,

`Erdos789.IsSubsetSumSeparatingCard n 2`.

Proof: let `A` have `n ≥ 3` distinct integers. At most one member of `A`
is zero, so `A` contains two distinct nonzero elements `a,b`. Put
`B={a,b}`. Its nonempty subsets are `{a}`, `{b}`, and `{a,b}`. The two
singletons have the same cardinality. If a singleton sum equalled the
two-element sum, then either `a=a+b` or `b=a+b`, forcing `b=0` or `a=0`,
contradicting the choice of `a,b`. Therefore equal nonempty subset sums
inside `B` always have equal cardinality.

This is a genuine universal structural lemma, but it is only a constant
lower bound and therefore does not close the asymptotic target.

## Exact small-n controls

The same argument plus explicit obstructions gives:

- `h(1)=1`;
- `h(2)=1`, with upper witness `A={0,1}`;
- `h(3)=2`, with upper witness `A={1,2,3}` since `1+2=3`;
- `h(4)=2`, with upper witness `A={-1,0,1,2}`. Every subset of size at
  least three either contains `0` (so adjoining `0` preserves a sum while
  changing cardinality) or is `{-1,1,2}`, where `-1+2=1`.

The executable verifier checks the separating predicate exactly on finite
sets, validates those upper witnesses, and regression-tests the canonical
two-nonzero construction over every `A ⊆ [-6,6]` of sizes 3 through 8.
The committed JSON receipt is deterministic.

## Run

```bash
cd research/conjectures_erdos789_two_element
python -m py_compile erdos789_two_element.py test_erdos789_two_element.py
python -m unittest -v test_erdos789_two_element.py
python -O -m unittest -v test_erdos789_two_element.py
python erdos789_two_element.py
```

## Evidence ceiling

`Contribution.lean` is a sponsor-shaped handoff draft, **UNEXECUTED** in
this runtime. Do not represent it as kernel-checked, sponsor accepted, a
solution of Erdős 789, or earned revenue until a sponsor-pinned Lean
environment elaborates it and the current contribution/submission flow
accepts it.

## Connected runtime triple constructor

[Exact separating triples](EXACT_TRIPLE_API.md) documents a dependency-free,
JSON-safe `BigInt` API in [separating_triple.cjs](separating_triple.cjs).
It constructs a triple with at most ten candidate checks and returns explicit
subset-sum collisions when none exists. The mathematical criterion and
five-nonzero guarantee are credited to the July 28, 2026 report linked in the guide.
[Construction outputs](construction_results.json) retain the API's actual calls
on that report's two finite input sets. This adds executable capability while
preserving the original contribution and its evidence ceiling.
