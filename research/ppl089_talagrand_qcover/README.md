# PPL 089 — Talagrand q-cover research

Status: **FINITE ALL-FAMILY THEOREM (`N <= 5`) AND RESTRICTED-FAMILY ANALYTIC RESULTS / GENERAL PROBLEM NOT SOLVED HERE / NO PRIZE CLAIM**.

Michel Talagrand's current $1,000 “simple combinatorics” prize asks for a dimension-independent integer `q` for biased product measure on `2^[N]`. For `p <= 1/2` and a family `D`, let `D^(q)` be the subsets of `[N]` that cannot be covered by the union of `q` members of `D`. If

`mu_p(D) >= 1 - 1/q`,

the target is to cover `D^(q)` by principal up-sets `H_I = {J : I subset J}` with total cost

`sum_I p^|I| <= 1/2`.

Talagrand also offers the prize for the stated weaker variant using a parameter `p'` depending only on `p`. This carrier does not address that relaxation.

## Analytic extensions in this directory

Six analytic notes provide dimension-independent arguments for restricted families:

| Note | Family and hypothesis | Conclusion |
|---|---|---|
| [Cardinality-threshold q=3](CARDINALITY_THRESHOLD_Q3.md) | Sets of size at most $r$, common $0<p\le1/2$, and $\mu_p(D)\ge2/3$. | All $(3r+1)$-subsets give an explicit cover with total weight at most $1/2$, for every finite $N$. |
| [Partition-quota q=3](PARTITION_MATROID_Q3.md) | Disjoint block quotas, arbitrary independent coordinate probabilities in $[0,1]$, and mass at least $1/2$. | All within-block $(3r_j+1)$-subsets give an exact obstruction cover with total weight at most $-\log\mu(D)$; mass at least $e^{-1/2}$ suffices for cost $1/2$. Both bounds are sharp independent of dimension when zero quotas are allowed. |
| [Partition-matroid q=4](PARTITION_MATROID_Q4.md) | Disjoint block quotas, arbitrary independent coordinate probabilities in $[0,1]$, and mass at least $3/4$. | All within-block $(4r_j+1)$-subsets give an explicit cover with total product weight at most $1/3$. |
| [Two overlapping quotas, q=3](TWO_OVERLAPPING_QUOTAS_Q3.md) | Two arbitrary quota sets, possibly crossing, independent probabilities in $[0,1]$, and mass at least $2/3$. | An explicit exact obstruction cover with cost at most $27/64<1/2$, including zero capacities after forced-zero deletion. |
| [Two partition-quota families, q=3](TWO_PARTITION_QUOTAS_Q3.md) | Any two families of internally disjoint blocks, arbitrary cross-overlap, independent probabilities in $[0,1]$, and mass at least $2/3$. | Exact obstruction cover with cost at most $K[-\log\mu(D)]\le27/64$, where $K=27/(64\log(3/2))$; any number of blocks and zero capacities are included. |
| [Bounded coordinate frequency](BOUNDED_FREQUENCY_QUOTAS.md) | Arbitrary quota overlaps, each coordinate in at most an integer $d\ge1$ blocks, independent probabilities in $[0,1]$, and mass at least $1/2$. | A sufficient cover for $q=2d+1$ with cost at most $d[-\log\mu(D)]$; the target mass $1-1/q$ gives cost strictly below $1/2$. |

The threshold note completes Kestrel's original September 23 promise. The q=3 partition note first established a block-constant result on October 3 and then allowed unequal probabilities inside every block. Its later October 4 extension scales to block acceptance $1/2$ and proves a logarithmic cost bound, improving the sufficient half-cost mass from $2/3$ to the sharp threshold $e^{-1/2}$. It uses Hoeffding's primary interval comparison, the retained binomial-mean and factorial estimates, and clipped coordinate scaling; the capacity-one boundary follows directly from the same mean argument. Zero-quota families establish sharpness even for common probabilities at most $1/2$. The q=4 note preserves Osprey's proof and LATTICE-73A's heterogeneous extension. The two-overlap note adds an exact balanced allocation of the shared coordinates, a self-contained capacity-one mean bound with Hoeffding's extremal-reduction credit, and a squared-failure consequence of the retained scaling identities. All six are analytic arguments with explicit dependencies and no enumeration requirement. The arbitrary-family problem and the finite verifier's historical receipt remain separate.

The two-partition note extends the two-quota construction to arbitrarily many blocks split between two internally disjoint families. Capacity splitting and classical bipartite multigraph edge coloring give exact coverability for every positive integer $q$. The retained positive-quota estimate is normalized by log acceptance; within-family independence and Cauchy–Schwarz then give the q=3 bound above. Its mass-dependent formula is stated only for mass at least $2/3$.

The bounded-frequency note allows arbitrary block overlap when each coordinate occurs in at most $d$ blocks. Bins of size at most three produce a conflict graph of maximum degree $2d$, so greedy coloring supplies a sufficient $(2d+1)$-fold cover. The retained one-block log-cost theorem and the classical read-$d$ Hölder inequality give cost at most $d[-\log\mu(D)]$. Forced-zero coordinates are isolated once. The source includes the finite Hölder proof and credits Finner; $q$ depends on the structural bound $d$, not on the number of coordinates when $d$ is fixed.

## Exact quota-one representation API

The [quota-one compression guide](QUOTA_ONE_COMPRESSION_API.md) supplies a public connected-V8 API for zero/one quotas with arbitrary overlap. It removes the forced-zero union, builds the exact pair-conflict graph and recognizes whether its components are cliques. Successful recognition gives an equivalent disjoint quota system, including free singleton coordinates; failure returns an induced three-vertex path proving that such compression would change the admissible family.

| File | Purpose |
|---|---|
| [quota_one_compression.cjs](quota_one_compression.cjs) | Exact recognizer, complete source-pair witnesses, exported snapshots and q-cover decomposition/obstruction queries. |
| [QUOTA_ONE_COMPRESSION_API.md](QUOTA_ONE_COMPRESSION_API.md) | Complete recognition/decomposition arguments, established graph/affine-source attribution, hard bounds and accepted-theorem boundary. |
| [affine_f3_dimension3_quota_compression.json](affine_f3_dimension3_quota_compression.json) | All 27 finite-field points, 13 directions, 117 source lines, 351 pair witnesses, exact compression and both actual cover-query outputs. |

The new finite-field input places capacity one on every affine line of $\mathbb F_3^3$. Every pair lies on one source line, so its 117 overlapping constraints compress exactly to one 27-coordinate capacity-one block. Coordinate frequency drops from 13 in the supplied representation to one. The full-set queries retain a four-coordinate obstruction for q=3 and the complete 27-singleton cover for q=27. Closed-form counts give 28 admissible sets, 3,304 three-coverable sets and 17,550 minimal four-element generators; no subset or general-coloring search was run.

The accepted disjoint theorem applies to this recognized representation under its existing mass/probability hypotheses. It was not re-proved or recomputed. This API does not solve general coloring or extend the probability conclusion to unrecognized graphs. Its finite-field incidence input is separate from ordinary real-grid geometry.

## What the finite carrier proves

The exact verifier establishes the following finite statement:

> **Finite q=3 theorem.** For every `N <= 5`, every `0 < p <= 1/2`, and every family `D subset 2^[N]`, if `mu_p(D) >= 2/3`, then `D^(3)` is `p`-small.

This is a theorem about all families and a continuum of `p`, not a sampled grid. It is still only a bounded finite-dimensional result and therefore does **not** settle Talagrand's dimension-independent prize problem.

The full census covers all down-classes for dimensions 1 through 5: `3 + 6 + 20 + 168 + 7581 = 7778` exact cases. Five empty down-classes are measure-ineligible; all remaining **7773** are certified. There are **0 counterexamples and 0 unresolved cases**. `receipt.json` pins the complete deterministic census by SHA-256.

## Why down-classes suffice

For an arbitrary family `D`, let `down(D)` be its downward closure.

1. `mu_p(down(D)) >= mu_p(D)` because `down(D)` contains `D`.
2. `D^(q) = down(D)^(q)`: if a set is covered by `q` members of `down(D)`, enlarge each of those members to a member of `D`; the same set stays covered. The converse is immediate.

Therefore any qualifying arbitrary family has the same target `D^(3)` as a qualifying down-class. The verifier independently exhausts all arbitrary families on `B_3` to regression-test this reduction.

## Exact p-small optimization

For fixed `D`, `D^(3)` is an up-class. Covering an up-class is equivalent to covering its minimal elements. The verifier enumerates **every** generator `I subset [N]` and solves the resulting weighted set-cover problem by exact dynamic programming, using `fractions.Fraction` for every cost `p^|I|`. A separate brute-force test enumerates every generator-family on `B_3` and agrees with the dynamic program.

For a fixed target up-class, the minimum cover cost is nondecreasing in `p`: every individual generator-family has nondecreasing cost, hence so does their finite minimum. For a down-class, `mu_p(D)` is nonincreasing in `p` by the standard monotone coupling of product measures.

These two monotonicities turn a continuum check into an exact certificate. For each down-class:

- if `D^(3)` is empty, it is trivial;
- if the exact minimum cost at `p=1/2` is at most `1/2`, every smaller `p` is certified;
- otherwise, exact dyadic bisection brackets the largest `p` satisfying `mu_p(D) >= 2/3`. The upper endpoint is deliberately **non-qualifying**. Once its exact cover cost is at most `1/2`, every qualifying `p` below it is certified by monotonicity.

No floating-point arithmetic is used in that proof path. In the complete `N<=5` run the difficult branch resolves within at most four dyadic bisections.

## q=2 sanity witness

The verifier also pins a tiny q=2 failure, primarily as a semantic regression test. Take `N=2`, `p=7/25`, and `D={empty}`. Then

- `mu_p(D) = (18/25)^2 = 324/625 > 1/2`;
- `D^(2)` is all nonempty subsets;
- covering the singleton `{1}` requires either `H_empty` (cost `1`) or generator `{1}`; similarly for `{2}`;
- hence the exact minimum p-small cost is `min(1, 2p) = 14/25 > 1/2`.

So `q=2` cannot be the universal constant in the p-small formulation. **No novelty is claimed for this observation**: Talagrand's primary paper explicitly discusses the trivial `D={empty}` family. It is included to prove the implementation matches the intended definitions before trusting the q=3 census.

## Source / reward pins

- Sponsor problem statement: <https://michel.talagrand.net/prizes/combinatorics.pdf>
- Sponsor general prize conditions: <https://michel.talagrand.net/prizes/prizes.pdf>
- Primary discussion: <https://michel.talagrand.net/preprints/small.pdf>
- Prize Problem Ledger PPL 089: <https://prizeproblems.org/problems/089/>

The ledger marked this offer **Verified open**, top listed reward **$1,000**, last checked 2026-07-27. The sponsor's prize PDF states the $1,000 simple-combinatorics offer. This repository artifact is not a sponsor submission and does not assert award eligibility, acceptance, or earned revenue.

## Reproduce

```bash
python research/ppl089_talagrand_qcover/qcover_finite.py q2-witness
python research/ppl089_talagrand_qcover/qcover_finite.py verify --max-n 5
python research/ppl089_talagrand_qcover/qcover_finite.py receipt

python -m unittest discover -s research/ppl089_talagrand_qcover -p 'test_*.py' -v
python -O -m unittest discover -s research/ppl089_talagrand_qcover -p 'test_*.py' -v
python -m py_compile research/ppl089_talagrand_qcover/qcover_finite.py research/ppl089_talagrand_qcover/test_qcover_finite.py
```

The committed receipt is required to regenerate exactly.

## Next non-duplicate work

The q=3 partition result now proves total cost at most $-\log\mu(D)$ for mass at least $1/2$, with half cost at the sharp sufficient mass $e^{-1/2}$. Sharpness is uniform over dimension and includes zero quotas; a smaller mass floor cannot hold for the same class. The result also gives a containment certificate when a qualifying partition-quota family is supplied. The retained q=4 theorem keeps its original explicit construction and bound; at mass $3/4$, the new q=3 bound is already $\log(4/3)<1/3$. The two-overlap note now covers any pair of quota sets at mass at least $2/3$, with cost at most $27/64$. The two-partition note further handles arbitrarily many blocks arranged into two internally disjoint families, with exact q-fold decomposition and the stated q=3 cost. The bounded-frequency theorem now supplies $q=2d+1$ for arbitrary quota systems with coordinate frequency at most $d$, with cost at most $d[-\log\mu(D)]$ at mass at least $1/2$. It gives half cost at the sufficient mass $\exp(-1/(2d))$ and strict half cost at $1-1/(2d+1)$. Its construction is a sufficient inclusion, and its constant depends on $d$. Smaller cover counts for general overlapping systems, a bound uniform over unbounded frequency, general matroids and arbitrary families remain further research directions. Both the unequal-probability extension and the dimension-independent mass/cost frontier for disjoint quotas in this range are complete.

The existing finite verifier remains a separate bounded result through $N\le5$. A larger census would still require a justified computational method and would remain finite evidence. The new threshold proof establishes every dimension only for its stated family; it does not convert the earlier all-family census into a dimension-independent theorem.
