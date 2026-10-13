# Cyclic affine incidence index

This package classifies and navigates the affine cyclic symmetries of one identified order-13 Singer plane. It consumes the saved difference set modulo 183; it does not reconstruct the field, prove the difference-set premise again, or identify this family with the full collineation group. The complete finite result is three multipliers and 549 affine maps.

## Source and scope

Gordon, Mills and Welch, *Some New Difference Sets*, Canadian Journal of Mathematics 14 (1962), 614–625, DOI [10.4153/CJM-1962-052-2](https://doi.org/10.4153/CJM-1962-052-2), define affine equivalence of cyclic difference sets by E=a+tD with gcd(t,v)=1; a slide has t=1, and t is a multiplier when E=D. The successfully read [publisher extract](https://www.cambridge.org/core/journals/canadian-journal-of-mathematics/article/some-new-difference-sets/9C377AE31ED76315C26280B65F0C9F30) supplies this definition. With u=t and c=−a, the convention here is uD=D+c. The incidence-map formulas below are this implementation's elementary specialization, not a quoted theorem from that extract. Cambridge's 2018 online date is not the paper's original publication year.

The accepted plane uses the classical Singer construction. Its prior source attribution and full field/difference certificate remain in #31474. The present input is a literal retained transfer through #31568; only the modulus and difference-set list are newly consumed. No old field cycle, triple-sum table, difference proof, incidence graph or C4 repair is recomputed.

The complete read of [FormalConjectures 723](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/723.lean), content blob `bb3216448586aaf61f8bedf61f0b20a674ff5e66` (2,421 bytes), marks the main prime-power question and order-12 existence question research open. It separately marks prime-power existence, the order-at-most-11 case and Bruck–Ryser as solved; their local proofs remain placeholders. This differs from the older intake's solved/False description. No linked proof was opened, no new global status survey was made, and this finite index resolves none of those questions.

## Exact input lineage

| Item | Identified value |
|---|---|
| Accepted source | [Commons #31474](https://github.com/woahwhattheheck/commons/pull/31474) |
| Original data path | `research/ppl088_erdos30_singer_plane/prime13_singer_plane.json` |
| Original data blob | `5561a91eddf8cfd7911641702b60cd51e308078d` |
| Original commit | `8a113ba792d9a9d674a5d8b0af7f78c079f846c7` |
| Retained transfer | #31568 input blob `f936595b3f047286fa6aa3fa8695c8b8aac3e301` |
| New input blob | `268fea103c62ccd16dc1036253d086c55d06b447` |
| New executed source | `e5cb3a38c8fe6163146184c4b9f9da832c686a2b` (7926 bytes) |
| Complete new snapshot | `563ce3b8a929f20204b451d1c6a73336ab32ed4a` (423123 bytes) |
| Complete saved reader | `c874205317e37bcbc1479d453b3e0b1477eb8a5f` (43693 bytes) |

The input is m=183 and D=[4,7,32,50,52,61,85,91,101,108,122,123,127,135]. Its inherited premise is that each nonzero residue has exactly one ordered difference between members of D, giving the accepted projective plane on translated blocks. This compiler does not check that premise. Its set-map classification itself needs only the literal finite subset; interpreting the result as plane collineations additionally uses the identified premise.

## Labels and affine maps

Points x and lines l are distinct types even when their numeric labels coincide. Labels run from 0 to 182. Incidence means x−l belongs to D modulo 183. A flag is represented by [l,j], where 0≤j<14 and its point is l+D[j] modulo 183.

For a unit u and slide c satisfying uD=D+c, an affine element (u,t,c) acts by

- point x ↦ ux+t;
- line l ↦ ul+t+c;
- flag [l,j] ↦ [ul+t+c,j′], where D[j′]=uD[j]−c modulo 183.

Indeed u(l+D)+t=ul+t+c+D. This also explains the sign of c in the line action. Within the actual input all three slides happen to be zero; the implementation retains the general slide term.

For g=(u,t,c_u) and h=(v,s,c_v), `compose(g,h)` means g after h. Its unit is uv, translation is us+t and slide is u c_v+c_u, modulo m. The inverse has unit u⁻¹, translation −u⁻¹t and slide −u⁻¹c_u. The snapshot stores the small multiplier product and inverse tables; a reader computes translation arithmetic from those tables.

## Complete finite classification

To find every slide for a unit u, note that uD[0]−c must be some anchor d in D. Therefore c=uD[0]−d ranges over exactly 14 candidates and covers all possible slides. Each candidate stores either its first missing image or acceptance. Since u is a unit, 14 included images are distinct and establish equality of the two sets. Nonunits are separately excluded with their gcd.

The generic constructor requires a trivial translation stabilizer and checks that exactly one slide occurs for u=1. For this planar difference-set premise, that property also follows because D+a=D for nonzero a would supply |D| ordered differences equal to a, contrary to the unique-difference premise. Consequently each multiplier has a unique slide. Closure and inverses then follow by composing the set equalities; the compiler retains its multiplier table.

| Multiplier u | Slide c |
|---:|---:|
| 1 | 0 |
| 13 | 0 |
| 169 | 0 |

There are 120 units, 1,680 candidate slides, 3,525 image-membership checks and 9 multiplier product entries. The 549 affine elements are indexed by `id = multiplier_index · 183 + t`, with multipliers sorted by u. The identity is id 0. There are 200,934 point/line fixedness checks; this counter excludes the separate small difference-permutation scan.

| Fixed points | Fixed lines | Fixed flags | Elements |
|---:|---:|---:|---:|
| 183 | 183 | 2562 | 1 |
| 0 | 0 | 0 | 426 |
| 3 | 3 | 6 | 122 |

Translations act transitively on points and separately on lines. On flags, the difference coordinate changes by d↦ud−c while translations permit any line coordinate. Thus flag orbits correspond exactly to the recorded orbits in D. For any source and target flags in the same difference orbit, every multiplier sending the source difference to the target determines exactly one translation; no multiplier does so across different orbits.

| Orbit | Difference residues | Flags | Stabilizer size per flag |
|---:|---|---:|---:|
| 0 | 4, 52, 127 | 549 | 1 |
| 1 | 7, 85, 91 | 549 | 1 |
| 2 | 32, 50, 101 | 549 | 1 |
| 3 | 61 | 183 | 3 |
| 4 | 108, 123, 135 | 549 | 1 |
| 5 | 122 | 183 | 3 |

The fixed flag count of an element is its number of fixed lines times the number of fixed difference coordinates. The 2,562 flags are represented by the incidence coordinates, not by conflating point and line labels. These are labelled-object counts. No quotient by arbitrary graph isomorphism is taken.

## Module contract

`cyclic_affine_incidence.cjs` exports `buildIndex(input)` and `openIndex(snapshot)`. The generic constructor accepts modulus 3 through 1,000 and a sorted list of 2 through 64 distinct residues in range. It rejects a nontrivial translation stabilizer. It does not test primality, difference-set parameters or plane axioms. The actual input is fixed above.

`openIndex` performs format and basic shape checks and returns `{query, stats}`. It trusts the supplied snapshot's mathematical certificate; it is not a hostile-input validator or independent proof checker. Query results are outward copies. Preserve the snapshot unchanged after opening. Numeric labels and ranks are safe integers within the supplied finite ranges.

| Operation | Request fields | Result |
|---|---|---|
| `summary` | none | Counts, fixed signatures and flag orbits |
| `screen` | `u` | Saved nonunit gcd or all slide witnesses |
| `multiplier` | `index` | u, c and difference-index permutation |
| `element` | `id` | Translation and saved fixed-object records |
| `compose` | `left`, `right` | ID of left after right |
| `inverse` | `id` | Inverse ID |
| `power` | `id`, `exponent` | Nonnegative power by table-based repeated squaring |
| `action` | `id`, `type`, `label` | Point/line integer or full flag image object |
| `fixed` | `id` | Fixed point/line lists, difference indices and flag count |
| `orbit` | `difference_index` | Saved flag-orbit description |
| `flagSelect` | `orbit`, `rank` | Flag in line-major, then ascending difference-index order |
| `flagRank` | `line`, `difference_index` | Orbit and rank in that ordering |
| `transporter` | `type`, `from`, `to` | All element IDs sending the source object to the target |
| `condition` | up to 8 `constraints` | All element IDs meeting every action constraint |
| `bucket` | `index` | Complete IDs with one fixed-object signature |

Types are `point`, `line` or `flag`. Action flag labels and transporter flag endpoints are arrays `[line,difference_index]`. A flag `condition` uses that array for `from`, but `to` is the exact action output object `{line,difference_index,point}`; point/line constraints use integer endpoints. Conditions compare complete action outputs. Power exponents are canonical nonnegative decimal strings of at most 2,048 digits. They are never converted to JavaScript Number.

## Saved reader evidence

A separate reader opened the banked snapshot after construction and produced 53 complete responses. Each response was retained and blob-banked before the next query; the aggregate file is complete. No reader or construction error occurred.

- Element 184 raised to 10^1000 returns element 184, using 4,484 table-based power products in the actual reader.
- The inverse of 184 is 380; the subsequent composition returns identity 0.
- Point 0 to point 182 has transporters [182,365,548]; line 182 to line 0 has [1,196,535].
- Flag [0,0] to [182,12] has the single transporter 548. Flag [0,5] to [182,5] has three transporters. Flag [0,0] to [0,5] has none.
- Fixing point 0 leaves [0,183,366]; fixing both points 0 and 1 leaves only identity.
- The last flag in each of all six orbits was selected and then ranked; all six inverse comparisons match the saved responses.

The reader records 1,098 element scans, 15 multiplier scans, 14,577 table lookups, 1,109 affine evaluations and 4,484 power products. These are fresh query operations, not zero-work claims. The compiler's gcd, candidate, image, multiplier-table and fixed-object construction is not repeated. Group-element IDs and orbit ranks are their declared finite orderings, not geometric canonical forms.

## Using the saved index

```javascript
const fs = require('fs');
const { openIndex } = require('./cyclic_affine_incidence.cjs');
const snapshot = JSON.parse(fs.readFileSync('order13_affine_index.json', 'utf8'));
const reader = openIndex(snapshot);
reader.query({ op: 'transporter', type: 'flag', from: [0, 0], to: [182, 12] });
reader.query({ op: 'power', id: 184, exponent: '1' + '0'.repeat(1000) });
```

This is a usage example, not an additional executed consumer. The saved reader is the evidence for the actual queries.

## Practical limits

The certificate exhausts a deliberately restricted family for one fixed labelled plane. It does not assert that all collineations have affine cyclic form, classify all projective planes, determine order-12 existence, prove the prime-power conjecture or establish mathematical novelty. Source attribution, inherited mathematical premises, newly compiled data and fresh query arithmetic remain separate. No sponsor contact or submission was made.
