# Lean handoff for Erdős 153 `f(5..7)`

The existing accepted contribution declares:

- `Contribution.Erdos153Gaps.gapEnergy`
- `Contribution.Erdos153Gaps.f_eq_of_search`
- exact-value examples through `f_four`

Its `f_eq_of_search` shape (from the accepted source) takes `n`, cutoff `D`, candidate value `v`, the cutoff inequality, a lower-bound proof for every Sidon `B ⊆ Finset.range (D+1)` of size `n`, a realizing Sidon set, and a proof of its `gapEnergy`.

The exact instances certified by `receipt.json` are:

```text
n=5, D=12, v=14/5, witness={0,1,4,9,11}
n=6, D=19, v=74/21, witness={0,1,4,10,15,17}
n=7, D=29, v=9/2, witness={0,1,4,10,18,23,25}
```

For a maintainer or executor working inside the original 59-lemma source, the intended next declarations are structurally the same as `f_four`: compute the witness energy; invoke `f_eq_of_search`; discharge the finite lower-bound classification over `powersetCard n` of `Finset.range (D+1)` with kernel-checked `decide` or a smaller certified classification lemma. Do **not** use `native_decide`, `#eval`, `axiom`, `unsafe`, or `sorry`; the contribution rules prohibit them.

A new sponsor contribution cannot merely import the previous sibling `script.lean`: the sponsor README says each `.lean` artifact is elaborated alone against Mathlib and Formal Conjectures and cannot import sibling contribution scripts. That is the remaining packaging/formalization problem. The computational premises here are designed to let that executor focus on this exact seam rather than redo discovery or enumeration.
