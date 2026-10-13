# Exact finite deletions from a periodic additive basis

This API gives an exact all-target representation index after deleting finitely many individual integers from an identified periodic order-two basis. It saves affine formulas by residue and quotient interval, all missing targets, the conductor, and enough deletion data to select and rank ordered representation pairs at very large queried targets.

The actual source basis is B = A + 13 N₀, with A = {0,1,2,4,5,7}. Exactly two summands are used, equal summands are permitted, and zero is initially an ordinary member. Removing one actual integer is different from removing its entire residue class.

## Statement, attribution and accepted input

The complete read of FormalConjectures/ErdosProblems/330.lean has content blob 638e0d045f2161db15c6f33fd4dbbeea6f17a6ff. It defines exact h-fold representability, deletion of a single element, and minimality as failure of the asymptotic-basis property after every such deletion. Its question asks for positive upper density of the basis and of each resulting unrepresentable set; it does not require density limits to exist. The source annotates the existence assertion as True / research solved, while its local proof is a placeholder. Its linked external Lean proof was not opened.

The already-read author paper by Sergei V. Konyagin and Vsevolod F. Lev, [The Erdős–Turán problem in infinite groups](https://math.haifa.ac.il/seva/Papers/ErTur.pdf), supplies the ordinary order-two convention: cover every ambient element, count ordered representations, and permit equal summands. This older source supplies conventions, not a current-status assessment of Erdős 330.

The arithmetic premise comes from [Commons #31581](https://github.com/woahwhattheheck/commons/pull/31581), head 7d111484c6e74b62b53fa4eddf73b7820691f147, merge d168aa451f315080230cc565b45de6bb89601eff. Its complete saved reader is research/ppl050_cyclic_two_sum_bases/saved_reader_queries.json, blob 2c99da26691f98c317171119b41c544a20d75c0e. Query 9 is the accepted profile for mask 183:

- Residues A: [0,1,2,4,5,7].
- Ordered residue coefficients R: [1,3,3,2,3,4,4,4,3,4,1,2,2].
- Carry coefficients C: [0,1,0,0,0,0,0,0,0,0,0,0,0].

The complete original construction identity is ba08e0d7ecb2d8702397a9101b341c9314aa4981. Its existing 169 ordered base-pair records were filtered by mask 183 to copy the 36 selected records, including their existing residues, carries and IDs. No pair sums, carry profiles, subset classification, basis proof or old reader query was recomputed. These identified records are input premises.

Minimality of A as a cyclic basis does not imply minimality of its periodic natural-number lift. The argument below shows that every finite deletion from this lift remains an asymptotic order-two basis. This package therefore does not construct the minimal basis required in Erdős 330 or re-prove its annotated result.

## The new deletion set

The input deletes 62 distinct elements of B:

1. Every residue a in A at quotients 0 through 7: 48 elements.
2. Quotient 8 with residues {0,4,7}; quotient 9 with {1,5}; quotient 10 with {2,7}; quotient 11 with {0}: eight elements.
3. For i = 0,...,5, the element 13·(10^80+i)+A[i]: six distant elements.

These are actual element deletions. The infinitely many other members in each residue class remain. Input blob bfd1979dc78571e8ea3fdaec78c9b15eb235a6d7 preserves all exact values, accepted coefficients/pairs and its original provenance fields. The full carrier path and immutable #31581 identities above were supplied subsequently from retained publication metadata; the executed input was not changed.

## Event formula and completeness

Write n = m q + r, with m=13, q≥0 and 0≤r<m. The inherited periodic count is

    R_B(n) = R_r (q+1) - C_r.

For finite D, inclusion–exclusion on the two ordered summand roles gives

    R_(B\D)(n)
      = R_B(n)
        - 2 * #{d in D : n-d in B}
        + #{(d,e) in D×D : d+e=n}.

A deleted d=m u+s contributes to the middle count precisely when (r-s mod m) belongs to A and q≥u+[r<s]. It causes a permanent intercept change of −2 at that threshold.

For each unordered deletion pair i≤j, the compiler records target d_i+d_j with ordered weight one when i=j and two otherwise. Its impulse adds that weight at its quotient and subtracts it at the next quotient. This restores the double-subtracted pairs with both entries deleted. A repeated summand is one ordered pair, not two.

Sorting and aggregating events gives intervals on which the answer is R_r·q+intercept. Adjacent equal-intercept intervals are coalesced. The first starts at q=0 and the last is unbounded, so all nonnegative targets are covered by the saved formulas without scanning up to distant holes. Every slope is positive. Solving each affine formula for zero inside its own interval gives the complete missing-target set. The compiler also rejects a negative count at an interval's first quotient; counts increase within that interval.

The inherited inequalities R_r≥1 and 0≤C_r≤R_r imply R_B(mq+r)≥q. Deleting |D| elements removes at most 2|D| ordered pairs at any target, and the intersection correction is nonnegative. Thus q≥2|D|+1 guarantees coverage. For this input every n≥13·125=1,625 is covered regardless of hole positions. Distant events affect counts and navigation but cannot create distant gaps. This is a bound for the declared periodic family, not the minimal-basis construction in the general question.

The source has natural density 6/13, unchanged by finitely many deletions. Its two-sum complement after deletion is finite and has density zero. This is distinct from the question's positive upper-density deletion effect.

## Actual construction

The compiler ran once from source blob b09c5294ee613fb5b04b2c1af9d04342b6fc8252, preserved verbatim as original_construction_source.cjs. Its complete index is blob fb0cb36e811a3d53ec992cb2d69d03432cc71b5e, 307,424 UTF-8 bytes.

| Quantity | Exact result |
| --- | ---: |
| Deleted elements | 62 |
| Threshold records | 372 |
| New unordered deletion-pair records | 1,953 |
| Their total ordered weight | 3,844 |
| Impulse updates | 3,906 |
| Aggregate event rows | 494 |
| Complete affine intervals | 363 |
| Missing targets | 219 |
| First represented target | 210 |
| Largest missing target | 246 |
| Conductor | 247 |

Production performed 806 new threshold-membership checks and the stated deletion-pair arithmetic. It did not enumerate target integers or recompute inherited pair sums/profiles. All threshold, pair, event, interval and gap rows are complete in finite_deletions_index.json.

The first represented target is 210=105+105. Target 247 has two ordered representations and one unordered representation. There are 28 represented targets at most 246 and 782 at most 1,000. The bound 1,625 is conservative; the exact saved conductor is 247.

## Reader correction and continuation

The first fresh reader retained seven complete responses. Its eighth request, coverageSelect("0"), raised TypeError: Cannot mix BigInt and other types, use explicit conversions. The midpoint expression used >>1, mixing a BigInt with a Number.

The one-character correction changes this reader expression to >>1n. The construction function is unchanged. The recommended module periodic_deletions.cjs has blob ca204dbb6be080937c45f2e9ff77aa3cc25f4099. The original executed module remains archived to bind the actual construction bytes; it is not the recommended reader entry point.

The complete first-session records, failed request, error and counters were banked in blob d110965325bd405c657db77e399251368b1cadd2. A new reader opened the existing index and continued from the failed request. It did not rerun the compiler or the seven completed responses. The final reader retains all 46 successful responses: seven original plus 39 continuation responses, with both source identities and the error boundary. Its blob is 8343db17b20dfc1d7b3ef35a85368b06194321d4, 103,843 bytes.

Nine ordered-pair select/rank pairs and two coverage select/rank pairs match in retained responses. All 219 gaps are exported in one complete page. Other actual results include:

| Query | Exact saved result |
| --- | --- |
| Ordered representation mass on [0,246] | 72 |
| Unordered representation mass on [0,246] | 39 |
| Ordered representation mass on [0,1000] | 62,335 |
| Unordered representation mass on [0,1000] | 31,256 |
| Diagonal representations on [0,1000] | 177 |
| Target 1,625 | 106 ordered / 53 unordered representations |
| Covered-target rank 10^1000 | Target 10^1000+219 |

Explanations include twice the first distant deleted element and the sum of two distinct distant deleted elements. They retain active threshold indices and pair-repair weights, distinguishing a diagonal repair of one from an off-diagonal repair of two. Pair navigation also operates at target 10^1000+330; the saved mass query covers that target and the following 1,000. A queried pair containing a deleted element returns nonmembership.

First-session work includes seven successful responses and the failed eighth request, with 25 segment-search steps. Continuation work records 39 queries, 49 segment-search steps, 1,089 mass interval scans, 149 gap-search steps, 756 saved-pair scans, 928 deleted-quotient scans, 707 excluded split positions, 99 pair-selection steps, 99 pair-rank steps and 1,116 threshold explanation scans. It creates zero new events or intervals and recomputes no inherited pairs or profiles. Structural reopening does not audit the accepted premise or replay the compiler.

## Reusable API

buildIndex(input) accepts the modulus, sorted source residues, positive ordered coefficients, carry coefficients, inherited ordered base-pair records and deleted nonnegative integers. It requires modulus 2–64, at most 128 distinct holes, and every hole in the declared periodic source. The profile/pair mathematical relationship is a supplied premise; the implementation validates domain and shape without recomputing that established relationship. Larger unexercised branches were source-inspected only.

Each accepted pair object carries id, a, b, residue and carry. Source IDs determine branch order. The actual input also preserves inherited support masks.

openIndex(saved) accepts the full object or JSON text:

| Method | Operation |
| --- | --- |
| summary() | Exact event sizes, gaps, conductor, density and construction work |
| point(n) | Ordered, diagonal and unordered counts, with the selected affine interval |
| explain(n) | Baseline, active deleted-element indices and full pair correction |
| representationMass(lo,hi) | Inclusive sum of ordered/diagonal/unordered counts |
| coverageCount(bound) | Distinct represented targets in [0,bound], plus gap count |
| coverageSelect(rank) | Zero-based numerical selection of represented targets |
| coverageRank(n) | Inverse numerical rank, or null at a gap |
| gapPage(offset,limit) | Up to 256 entries of the complete finite gap list |
| residue(r) | All intervals for a residue and its inherited slope |
| pairBranches(n) | Saved pair branches, quotient ranges and excluded positions |
| pairSelect(n,rank) | One ordered representation avoiding every hole |
| pairRank(x,y) | Inverse ordered-pair rank, or nonmembership |
| work() | Reader counters without incrementing query count |

For an ordered residue pair (a,b), its saved carry gives the quotient-split total Q. Old representations have first quotient u in [0,Q]. A deletion in residue a excludes its quotient; a deletion in residue b excludes Q minus its quotient. The reader merges these finite excluded positions and skips them without enumerating the potentially enormous interval.

Pair order is the retained ordered residue-pair order, then increasing first quotient within its branch. It is not global numerical first-summand order. Coverage order is increasing numerical target order. Unordered counts include the surviving diagonal once and equal (ordered+diagonal)/2; pair navigation itself remains ordered.

Integer arguments accept nonnegative safe integer numbers, BigInts, or canonical decimal strings of at most 2,000 digits. Reversed mass intervals fail. Pair ranks must belong to the fiber. Coverage selection is unbounded because the positive-slope premise proves eventual coverage. Gap pages remain bounded by the finite saved list.

A saved-data consumer uses the corrected entry point:

~~~javascript
const fs = require('node:fs');
const {openIndex} = require('./periodic_deletions.cjs');
const api = openIndex(fs.readFileSync('./finite_deletions_index.json', 'utf8'));
const p = api.point('247');
const selected = api.pairSelect('247', '0');
const inverse = api.pairRank(...selected.pair);
const gaps = api.gapPage(0, 256);
const huge = api.coverageSelect('1' + '0'.repeat(1000));
~~~

This example describes the implemented interface. The actual 46 successful responses and failed-reader boundary are saved separately. One documentation-authoring script failed to parse before any provider call; it caused no numerical rerun or publication mutation. No test suite, original basis computation, external proof audit, sponsor contact or prize submission was undertaken.
