# Complete finite coset packings

This package compiles the subgroups and distinct left cosets of a supplied finite group, then counts every disjoint coset family inside every available-element subset. Sparse multivariate coefficients retain the number of cosets of each subgroup index. A separate reader provides exact counts, profile pages, rank/select, partial-decision counts and cover navigation without rebuilding the group, its subgroups, its cosets or the polynomial recurrence.

The one actual input is the **dihedral group of order 12**, with rotation order six. Here “D12” always means order 12, not the alternative convention of a dihedral group with twelve rotations.

The resulting finite index has **16 subgroups, 74 distinct left cosets, 4,096 available masks and 99,178 coefficient cells**. It counts **697,975 disjoint families**, including **27,613 covers** of the full group, without enumerating those individual families.

## Source conventions and limits

[Wan-Jie Zhu, *On Sun’s Conjecture concerning Disjoint Cosets*, International Journal of Modern Mathematics 3 (2008), no. 2, 197–206](https://arxiv.org/abs/0807.2207), with [author text](https://arxiv.org/pdf/0807.2207), states Sun's conjecture for an arbitrary group G: if k>1 left cosets a_i G_i are pairwise disjoint and all subgroup indices are finite, some pair i<j should satisfy

~~~text
gcd([G:G_i],[G:G_j]) >= k.
~~~

No finite-group, abelian, normality, distinct-subgroup or covering assumption is imposed. Different disjoint cosets of the same subgroup are allowed. Zhu's Theorem 1.1 establishes k=3 and k=4; these are dated 2008 partial results, not an exhaustive current-frontier claim. Only definitions and theorem statements were used, not a proof audit.

The original catalogue's linked Sun survey returned one timeout and was left unavailable. The independent Zhu paper supplied the needed source conventions; the failed survey was not retried or fetched through another route.

A family in this API is an unlabelled collection of distinct coset **sets**. Different representatives of one coset do not create new objects, and permuting a family does not create a new family. An empty family and singleton families are retained for the polynomial interface. The source inequality is marked not applicable to those k=0 and k=1 cases.

This finite group is one instance of a much broader conjecture. None of its 158 realized full-group index signatures violates the stated inequality for k>=2. That finite classification does not prove the arbitrary-group assertion, establish a new theorem or claim priority.

## Explicit new group input

Elements are pairs (a,b), with 0<=a<6 and b in {0,1}, encoded as 2*a+b. The multiplication law is

~~~text
(a,b)(c,d) = (a + (-1)^b*c mod 6, b XOR d).
~~~

The identity is label 0. This standard semidirect-product description gives rotations and reflections, and the input declares it directly:

~~~json
{"group":{"dihedral_rotation":6}}
~~~

The complete twelve-by-twelve Cayley table is materialized once and retained. Before subgroup enumeration the constructor checks its identity, two-sided inverses and associativity. These checks concern the new actual finite table; no previous group artifact or coset computation is consumed.

The actual work includes 144 materialized products, 24 identity checks, 78 inverse candidates and 1,728 associativity checks. The inverse array and full table are saved alongside the subgroup and coset records.

## Complete subgroup and coset catalog

Every subgroup contains the identity. The constructor therefore considers all 2,048 masks containing that element. For each candidate it tests closure under table multiplication. A nonempty finite subset containing the identity and closed under multiplication is a subgroup: powers of each element repeat, supplying its inverse within the subset. This proves that the test is sufficient as well as necessary.

Every rejected candidate retains its first explicit escape witness (a,b,a*b), with a and b in the candidate and a*b outside it. The output contains all 2,048 candidate records, not merely the sixteen accepted masks. Accepted records retain their element lists, orders and indices.

For each subgroup H and every a in G, form aH={a*h:h in H}. The complete translate-mask array is saved per subgroup. Equal coset sets are deduplicated, with the smallest representative retained. A coset set cannot belong to two different subgroups: choosing any a in the set C recovers the subgroup as a^-1*C. Thus deduplicating by element mask preserves subgroup identity, rather than conflating distinct mathematical objects.

This produces 74 distinct left cosets with indices

~~~text
[1,2,3,4,6,12].
~~~

The subgroup phase used 21,032 product checks, stopping at the first escape for a rejected mask. The translate phase used 720 product lookups. The saved catalog contains provenance for every coset and every translate; the reader does not regenerate them.

## Packing polynomials

Let S be a subset of available group elements. All subgroup indices remain indices in the **original group G**, even when S is a proper subset. Let z_j mark a chosen coset whose subgroup has index j. Define P_S as the sum of the corresponding monomials over all disjoint coset families contained in S.

The empty family contributes one. With v the least available element:

~~~text
P_empty = 1

P_S = P_(S without v)
      + sum over cosets C containing v and contained in S
          z_index(C) * P_(S without C).
~~~

The first case leaves v uncovered. In every other family there is exactly one chosen coset containing v because the cosets are disjoint. Removing that coset gives the corresponding smaller packing. These cases are mutually exclusive and exhaustive, establishing the recurrence without requiring a cover.

Every recursive available mask is numerically smaller, so a bottom-up pass suffices. Multiplying by z_j increments one index multiplicity. Different families contributing the same monomial are added into its exact BigInt coefficient. This indexes all families without listing them individually.

For this order-12 input, signatures are six-component vectors in the index order [1,2,3,4,6,12]. Counts are encoded as base-13 digits, with index 1 in the least significant position. Every multiplicity is at most twelve, so no carries conflate signatures. Stored rows are sorted by this numeric signature code.

The compiler retains every nonzero coefficient for all 4,096 masks. Its 99,178 cells arise through 329,673 coefficient contributions and 65,520 considered coset branches. The constructor's observed 166 ms is one connected-runtime observation, not a benchmark or comparative performance result.

### From signatures to the source condition

If a signature has multiplicities c_j, its number of cosets is k=sum c_j and its number of covered elements is sum c_j*(12/j). Disjointness makes that coverage exact.

The maximum pairwise index gcd is determined solely by the signature. Distinct occurring indices may form a pair; an equal-index pair is available only if its multiplicity is at least two. The output records this maximum and one attaining index pair. For k>=2, this determines whether Sun's stated inequality holds for every family represented by that signature. For k<2 it returns null, not an artificial successful pair.

No signature with a positive coefficient in this instance violates the inequality. This is a consequence of the complete finite signature census, not a proof for other groups or a replay of Zhu's theorem.

## Actual finite counts

| Number of cosets | Disjoint families |
| --- | ---: |
| 0 | 1 |
| 1 | 74 |
| 2 | 1,584 |
| 3 | 14,914 |
| 4 | 69,775 |
| 5 | 170,567 |
| 6 | 221,223 |
| 7 | 152,200 |
| 8 | 55,656 |
| 9 | 10,827 |
| 10 | 1,099 |
| 11 | 54 |
| 12 | 1 |
| **Total** | **697,975** |

The exact counts by covered-element number 0 through 12 are

~~~text
[1,12,108,644,3039,11004,31880,72216,127578,
 168904,159456,95520,27613].
~~~

Thus 27,613 families cover the full group. A cover is just a packing with no uncovered element; the general census does not impose this constraint.

The signature [0,0,0,0,6,0] has six index-six cosets and exactly **955** families. Each covers the group because the cosets have size two. Its maximum pairwise gcd equals k=6. The signature [0,2,0,0,0,0] has exactly **three** two-coset covers of index two.

The available mask 1365 contains precisely the six rotation elements (even labels). It has 143 contained coset packings and twelve covers of that available set. These are still cosets and indices of the original twelve-element group; the API does not silently recompute the subgroup lattice of the six-element available set.

## Navigation order and proof

For a fixed signature, inspect the least available element. Order the uncovered branch first, then permitted cosets containing that element in increasing coset-mask order. Recursively apply the same order to the remainder.

Each branch's size is a saved smaller-mask coefficient, using the unchanged signature for an uncovered point or decrementing the chosen coset's index multiplicity. Selection subtracts preceding branch counts; ranking sums them. A selected family returns the actual coset records, uncovered elements and its complete decision trace.

A partial prefix is a sequence of these decisions: null means leave the current least available element uncovered; an integer coset mask means choose that coset. The explicit uncovered decisions matter. A list of already chosen cosets alone need not describe a contiguous prefix of this order.

Aggregate ordering sorts signature codes first, followed by the fixed-signature order. Cover-only aggregate ordering filters signatures by exact coverage while retaining their relative order. These are interface choices, not group-isomorphism quotients or labelled-family counts.

### Retained selections and prefix

The aggregate middle packing has rank 348987. Its signature is [0,0,0,0,3,3], with six cosets covering nine elements. Its within-signature rank is 9870, and its coset masks are

~~~text
[6,24,32,576,256,1024].
~~~

Labels [0,7,11] remain uncovered. These masks are in canonical decision order, which is not simply increasing numeric order.

Its first three decisions are [null,6,24]. They leave 130 completions, beginning at within-signature rank 9790. The complete selected family ranks back to 9870 using saved branch coefficients.

The middle cover has aggregate cover rank 13806. Its signature is [0,0,0,0,4,4], its within-signature rank is 633, and the selected coset masks are

~~~text
[1,2,260,72,2064,32,128,1536].
~~~

All twelve elements are covered. First and last packings, first and last covers, both ends of the 955 six-pair covers, the final cover page, and the empty available set are also retained as reader outputs.

## Public API

The dependency-free CommonJS module exports `VERSION`, `compileCosetPackings`, and `openCosetPackings`.

A constructor accepts either `group.dihedral_rotation` in 2–6, or an explicit `group.table` of order 1–12 with a declared `group.identity`. For an explicit table it verifies the same group axioms before compilation. Non-groups are rejected. These generic input branches were source-inspected; only the declared rotation-order-six consumer was executed.

The default coefficient-cell budget is 1,000,000, configurable up to 1,500,000. The contribution-visit budget defaults to 10,000,000, configurable up to 20,000,000. An exceeded budget throws without returning a partial snapshot. These bounds prevent uncontrolled enumeration; they are not a mathematical threshold in Sun's question.

Integer masks, table entries, signature digits and page offsets use exact safe Numbers. Coefficients and ranks use BigInt and canonical decimal strings; numeric rank inputs must be safe integers. Decimal inputs have a 100-digit cap. Snapshot opening has a 24,000,000-character cap.

### Opening the published coefficient shards

The complete initial snapshot was banked before any query. Its unchanged polynomial array is published in four contiguous shards so every file can be read back in full. The core record contains all other snapshot fields and a manifest binding each shard's interval and Git identity.

~~~js
const {openCosetPackings} = require("./coset_packing_index.cjs");
const record = require("./dihedral12_coset_packings.json");
const shards = [
  require("./polynomials_0000_1023.json"),
  require("./polynomials_1024_2047.json"),
  require("./polynomials_2048_3071.json"),
  require("./polynomials_3072_4095.json")
];

const polynomials = [];
for (const shard of shards) {
  if (shard.start !== polynomials.length ||
      shard.rows.length !== shard.end_exclusive - shard.start) {
    throw new Error("incomplete or misordered coefficient shards");
  }
  polynomials.push(...shard.rows);
}
if (polynomials.length !== 4096) throw new Error("missing masks");

const index = openCosetPackings({...record.snapshot, polynomials});
index.totalCount(4095);
index.totalCount(4095, true);
index.count(4095, [0,0,0,0,6,0]);
~~~

This concatenates saved records; it performs no polynomial recurrence. The actual fresh reader used this assembly before its 28 queries.

| Method | Result |
| --- | --- |
| `summary()` | Saved group and full-family census. |
| `subgroupPage(start,limit)` | Complete subgroup records and translate references. |
| `cosetPage(start,limit)` | Distinct left cosets and subgroup provenance. |
| `candidatePage(start,limit)` | Identity-containing subgroup candidates and escape witnesses. |
| `profilePage(available,start,limit)` | Exact coefficient profiles for an available mask. |
| `count(available,signature)` | Number of packings with the requested index multiplicities. |
| `totalCount(available,covers=false)` | All families, optionally covering the available set. |
| `select(available,signature,rank)` | One fixed-signature packing with branch trace. |
| `selectAll(available,rank,covers=false)` | Aggregate signature-then-packing selection. |
| `prefix(available,signature,decisions)` | Completions and first rank of a decision prefix. |
| `rank(available,cosetMasks)` | Fixed-signature rank of a supplied disjoint coset family. |
| `pageAll(available,start,limit,covers=false)` | Up to 32 aggregate selections. |
| `statistics()` | Reader work and zero-recomputation counters. |

Subgroup, coset, candidate and profile pages accept 1–64 records. Empty end pages are allowed; selection outside a family throws. Missing signatures count as zero. A supplied family for ranking must consist of distinct, disjoint, catalogued cosets contained in the available set. Its array order is immaterial: ranking constructs the canonical decision order and derives its signature.

## Reader validation and actual work

The reader copies the supplied snapshot and validates shapes, table bounds, subgroup-mask/index relationships, all 2,048 identity-containing candidate references and all 2,032 saved escape witnesses. It checks coset-mask/provenance/translate references, polynomial row ordering, positive coefficients, signature coverage bounds and the empty-family coefficient.

It does not recheck all group axioms, retest subgroup closure, recompute translates or redo the polynomial recurrence. It does not independently authenticate an arbitrarily edited group, accepted-subgroup list, coefficient value or summary. Those claims remain bound to the identified constructor output and argument. Comparing a saved escape with the saved Cayley table is a structural witness check, not a subgroup search.

The fresh reader made **28 queries**, exporting all sixteen subgroups, all 74 cosets and all 158 full-group profiles, plus selections, ranks, prefixes, cover counts, subset counts and sample rejected-subgroup records.

It opened 99,178 coefficients and checked 2,032 saved escapes. Its query counters record 344 coefficient lookups, 229 navigation branches, 1,404 profile evaluations and 1,784 aggregate coefficient visits. Opening also checks per-cell signature support. Query profile decoding, gcd arithmetic and aggregation are actual work; zero reconstruction counters do not imply that reading is computation-free.

The reader performed zero group-product reconstruction, subgroup-closure replay, coset-translate replay or polynomial recurrence. It enumerated only the requested output families; the constructor's complete 697,975-family count came from coefficients.

## Durable identities

| Artifact | Bytes | Git blob |
| --- | ---: | --- |
| Frozen source | 19,134 | `c2dad75eaebaf56b0e960c2174e9d05e3c6c04fb` |
| Standalone exact input | 591 | `87e7ec7d78c7eb8903f01d6aac241abc8febe01d` |
| Complete pre-reader snapshot | 1,531,248 | `878a2d23d9bb5f019295da5b4d2b5933cf880157` |
| Core, manifest and 28 queries | 235,317 | `f3a2130732132b23ff0ad4d9fac3b60946a8ea7f` |
| Polynomial masks 0–1023 | 214,268 | `41d6ed2ac08ba2618aa80a85d5ece7b40e0d6ce4` |
| Polynomial masks 1024–2047 | 327,269 | `ff4dee30bdbfc0108941d99a016ae6118bd0ba29` |
| Polynomial masks 2048–3071 | 327,269 | `4f63b1f2ae23cf0b2f6027d83671cddb00a34194` |
| Polynomial masks 3072–4095 | 491,384 | `62e7d271d47559166477e5764ced25016417751d` |

Source and input were checkpointed before the one bounded calculation; its entire result was banked immediately. Sharding changed only storage organization. All source, guide, core and shard texts are published with full readbacks. No old finite group, external proof, accepted computation or source example was rerun; no sponsor contact or submission occurred.
