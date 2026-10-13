# Finite coset-packing polynomials

Complete subgroup/coset construction and saved disjoint-family navigation for a finite group of order at most twelve.

The actual input is the **dihedral group of order 12**, with six rotations. Its sixteen subgroups produce 74 distinct left cosets. Exact sparse polynomials for all 4,096 available-element subsets retain **99,178 coefficients**, counting **697,975 disjoint families** and **27,613 full covers** without enumerating those families individually.

Families are unlabelled sets of disjoint coset sets. The same subgroup may contribute different cosets, and uncovered group elements are permitted. All 158 realized full-group index profiles satisfy Sun's stated gcd condition where it applies (at least two cosets); this is a finite-instance observation, not a general proof.

[COSET_PACKING_API.md](COSET_PACKING_API.md) gives the subgroup/packing arguments, exact interface, source qualification, counts, assembly instructions and complete identities.

| File | Contents |
| --- | --- |
| [coset_packing_index.cjs](coset_packing_index.cjs) | Bounded constructor and separate saved-data reader. |
| [dihedral12_coset_packings.json](dihedral12_coset_packings.json) | Group, all candidates/subgroups/cosets, full profiles, shard manifest and 28 queries. |
| [polynomials_0000_1023.json](polynomials_0000_1023.json) | Available masks 0–1023. |
| [polynomials_1024_2047.json](polynomials_1024_2047.json) | Available masks 1024–2047. |
| [polynomials_2048_3071.json](polynomials_2048_3071.json) | Available masks 2048–3071. |
| [polynomials_3072_4095.json](polynomials_3072_4095.json) | Available masks 3072–4095. |

Saved count/rank/select, prefix, cover and page queries consume these exact coefficients without subgroup or polynomial reconstruction. Six index-six cosets give 955 covers; the rotation-element subset has 143 packings and twelve covers under the original group's coset convention.

[Zhu's 2008 paper](https://arxiv.org/abs/0807.2207) supplies the precise conjecture and dated k=3,4 theorem. No arbitrary-group resolution, current frontier, novelty or reward claim is made.
