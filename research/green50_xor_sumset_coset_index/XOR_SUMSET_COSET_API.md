# Finite XOR sumset and affine-coset index

This package supplies exact repeated-sumset growth, ordered representation fibers, affine-coset containment and single-deletion sensitivity for fourteen specified subsets of F₂⁶. Its input is the full set

    A = {2,3,5,7,11,13,17,19,23,29,31,37,41}

and each set obtained by deleting exactly one label. Integer labels encode six binary coordinates; addition is bitwise XOR. Lengths 0 through 10 are retained. No other generator subset or ambient dimension was classified.

The complete result contains 9,856 coefficient cells and 39 distinct support profiles. For the full A, the first four positive sumset sizes are 13,42,62,64. Its 137,858,491,849 ordered ten-tuples are represented by 64 target fibers, without enumerating those tuples. The saved reader retains 105 complete responses and 23 inverse rank matches.

## Qualified problem and finite limitation

Ben Green's [100 Open Problems](https://people.maths.ox.ac.uk/greenbj/papers/open-problems.pdf#problem.50), Problem 50 on printed page 25, asks whether a density-α subset A of F₂ⁿ has a coset of dimension at least n−O(log(1/α)) inside 10A. The additive notation on printed page 2 defines A+B through all pairs. Thus repeated choices in the ten summands are allowed, equal output values count once in the sumset, and a coset can be translated away from zero. The implied constant is absolute. The retained author text is a statement/notation source; no proof or current frontier survey was reviewed.

The separately read [FormalConjectures statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/GreensOpenProblems/50.lean) explicitly defines repeated tenfold addition, a nonempty finite A, α=|A|/2ⁿ and an absolute C>0. The complete returned text has 2,375 bytes and local Git blob 7d36420dc80baba588a325f8cb0ae7f6c1889a52. The request used the repository default ref; no immutable source commit was supplied. Its research-open annotation and local sorry are recorded as observed metadata, not an independently verified global status or proof.

The earlier Muse semantic audit of the meaning of 10 • A is an accepted separate result. No Lean instance, elaboration, audit or disproof investigation was repeated here. The current source itself states the intended iterated-sumset convention.

Dimension six also imposes an elementary limitation on this consumer. For any nonempty A⊂F₂⁶, fix a₀∈A and let W=span(A+a₀). Choose a basis of W from A+a₀; it has at most six elements. A vector of W uses s≤6 basis differences and can therefore be written as s elements of A plus one further a₀ when s is odd. This is an even number s+(s mod 2)≤6 of terms. Pairs a₀+a₀=0 pad it to ten terms. Conversely, every ten-term sum lies in W because ten copies of a₀ cancel. Hence 10A=W in this ambient dimension.

That argument is a simple finite-dimensional observation, not a new general Bogolyubov theorem. The useful computations here are the exact earlier growth stages, ordered-fiber multiplicities and navigation, and the specified deletion effects. A fixed six-dimensional result does not provide an absolute dimension-loss bound as n varies.

## Input lineage and preserved calculations

The labels are copied literally from the first thirteen prime entries in [#31789](https://github.com/woahwhattheheck/commons/pull/31789), merge 8f7f9ec9393a19d18789d72b23882f7f4657c5b7, path research/erdos1094_binomial_valuation_index/input256.json, blob 522485b25d27bf7c37b0042dea6339fd4dea15d8. Primality is unused; no factor, valuation or sieve calculation is replayed.

The affine catalogue is a premise from [#31804](https://github.com/woahwhattheheck/commons/pull/31804), merge 3e92840c95275caa40ac87076a6ee43c0164a559, under research/green40_binary_linear_cover_index/. Its manifest blob is 7c324f454164cfe02e04bfcd0e765067bf69f3cf and its complete original snapshot identity is b02175aa336d299c1c147dd50633a6238aa08fb6. This input copies only each code's ID, basis and dimension, and each coset's representative and complete vector list. It preserves all 2,825 subspaces and 26,387 distinct affine cosets. No RREF generation, subspace enumeration, coset generation, Hamming-weight table, covering radius or earlier query is repeated.

A coset ID is the position in the flattened retained code/coset order. Its vector order is the inherited catalogue order; it is not asserted to be numerical order. Tuple symbols and sumset values use increasing numerical order. Every point/coset is labelled; no quotient by coordinate transformations is taken.

All new input bytes were banked before the source ran. The new full input has 2,687,475 bytes and blob 25c2ba3f857f4bbc2644803bd420b14bfb6f3370. Its array-encoded catalogue shards reproduce that exact object.

## Exact construction

For a fixed variant B and target x, let C_k(x) count ordered k-tuples from B with XOR x. Repetitions are allowed. The declared empty-tuple convention is C₀(0)=1 and C₀(x)=0 for x≠0. The recurrence is

    C_(k+1)(x) = Σ_(a∈B) C_k(x XOR a).

It partitions tuples by the final symbol. The source fills all 64 target cells at each length, using BigInt counts. The support kB is exactly the set of x with C_k(x)>0; ordered multiplicities are not the cardinality of kB.

Each inherited coset is converted once to a 64-bit membership mask by reading its saved vectors. This is a new storage representation, not coset generation. A support profile is cached by its entire membership mask. A coset mask M lies in support mask S precisely when M AND S=M. The profile retains every matching coset ID, grouped by dimension, and the complete maximum-dimension list. Identical support profiles can be shared across lengths or variants even though their representation counts differ.

The fourteen variants remain separate inputs. Their counts are not added to claim a count of distinct tuples across variants, since the variant families overlap.

| Variant | Size of 1B | Size of 2B | Size of 3B | Size of 4B | Size of 10B | Largest coset dimension in 10B | C₁₀(0) |
|---|---:|---:|---:|---:|---:|---:|---:|
| full | 13 | 42 | 62 | 64 | 64 | 6 | 2623553533 |
| without_2 | 12 | 30 | 32 | 32 | 32 | 5 | 1970525952 |
| without_3 | 12 | 39 | 60 | 64 | 64 | 6 | 1160278272 |
| without_5 | 12 | 39 | 60 | 64 | 64 | 6 | 1145390592 |
| without_7 | 12 | 41 | 62 | 64 | 64 | 6 | 1145390592 |
| without_11 | 12 | 41 | 62 | 64 | 64 | 6 | 1143566592 |
| without_13 | 12 | 39 | 60 | 64 | 64 | 6 | 1160278272 |
| without_17 | 12 | 41 | 62 | 64 | 64 | 6 | 1143566592 |
| without_19 | 12 | 41 | 62 | 64 | 64 | 6 | 1145390592 |
| without_23 | 12 | 39 | 60 | 64 | 64 | 6 | 1160278272 |
| without_29 | 12 | 41 | 62 | 64 | 64 | 6 | 1145390592 |
| without_31 | 12 | 41 | 62 | 64 | 64 | 6 | 1143566592 |
| without_37 | 12 | 37 | 58 | 64 | 64 | 6 | 1298806272 |
| without_41 | 12 | 37 | 58 | 64 | 64 | 6 | 1298806272 |

For the full A, the largest coset dimensions at lengths 0 through 4 are 0,2,4,5,6. The numbers of maximum-dimensional cosets at lengths 1,2,3,4 are respectively 19,15,31,1.

Removing label 2 removes the only label whose least significant bit is zero. In the resulting variant, every odd-length sum has least significant bit one and every even-length sum has that bit zero. The stored length-three support is the entire odd-encoding affine hyperplane, and the length-four support is the entire even-encoding linear hyperplane; they alternate through length ten. This is parity of the integer encoding's lowest coordinate, not parity of Hamming weight. At length ten there are 1,970,525,952 tuples with target zero and none with target one. The full variant has 2,623,553,533 and 1,795,030,682 tuples at those targets.

| Once-only construction work | Value |
|---|---:|
| Coefficient cells | 9,856 |
| XOR-convolution additions | 108,160 |
| Saved coset-vector insertions into masks | 180,800 |
| Support-cell reads | 9,856 |
| Distinct support profiles / cache hits | 39 / 115 |
| Coset containment checks | 1,029,093 |
| Matching coset-ID insertions | 187,138 |
| Old subspace/coset/covering work | 0 |
| Primality or old arithmetic work | 0 |

The source bounds dimension by six, length by ten, variants by the supplied maximum 32, catalogue size by 30,000 and support profiles by 400. The actual input contains 14 variants and 39 profiles. It consumes a trusted complete catalogue; validating hostile replacements or proving catalogue completeness again is outside this interface.

## Saved reader and ordering

~~~javascript
const fs = require('fs');
const {loadInput, loadData} = require('./load_saved_index.cjs');
const {openIndex} = require('./xor_sumset_coset_index.cjs');
const read = p => JSON.parse(fs.readFileSync(p,'utf8'));
const input = loadInput(read('input_manifest.json'),read);
const saved = loadData(read('sumset_manifest.json'),read);
const api = openIndex(saved,input);
const count = api.prefixCount('full',10,0,[2,3,5]);
const last = api.tupleSelect('full',10,0,'727397',[2,3,5]);
const inverse = api.tupleRank('full',10,0,last.tuple,[2,3,5]);
~~~

This is a CommonJS reuse example. The actual source and reader were loaded unchanged in V8; no native executor or Node CLI was used.

| Method | Meaning |
|---|---|
| compile(input) | Once-only convolution and new containment profiles. |
| openIndex(saved,input) | Structural opening of the trusted complete saved objects. |
| summary(), profiles() | Retained family and support-profile metadata. |
| growth(name) | Every saved length's support, mass and coset counts for one variant. |
| sumset(name,k) | Distinct output values, total ordered tuples and maximum coset dimension. |
| prefixCount(name,k,x,prefix) | Exact number of ordered completions to target x. |
| tupleSelect(name,k,x,rank,prefix) | Zero-based lexicographic tuple and every branch decision. |
| tupleRank(name,k,x,tuple,prefix) | Inverse rank, or null if the tuple has the wrong XOR. |
| tuplePage(name,k,x,start,limit,prefix) | At most 50 consecutive tuples and next rank. |
| sumsetSelect(name,k,rank), sumsetRank(name,k,x) | Numerical navigation of distinct target values. |
| cosetPage(name,k,dimension,start,limit) | At most 1,000 matching inherited cosets of one dimension. |
| coset(name,k,id) | Complete coset/basis and containment, with a first missing vector on failure. |
| deletionImpact(k,x) | All fourteen saved counts/support dimensions at one target and length. |
| work() | Fresh reader operation counters. |

Variant names are full and without_<label>. Lengths and six-bit targets are exact bounded Numbers. Tuple ranks accept nonnegative BigInt, decimal strings or safe integer Numbers. Prefix symbols must belong to the selected variant and the prefix must not exceed the requested length. A full ranked tuple must extend that prefix. Invalid inputs or a rank outside a nonempty fiber raise an error; an absent target has count zero and its rank-zero page is empty.

If a prefix XOR is s and t positions remain, its completion count is C_t(x XOR s). Select branches through allowed symbols in ascending order and subtracts these saved suffix counts. Rank adds earlier branch counts. No suffix convolution is performed by these queries. Repeated symbols remain separate tuple positions; permutations normally have different ranks.

A coset query obtains its first absent vector by scanning the inherited vector list against the saved support mask. This is reported as new query work. It neither generates the coset nor repeats the constructor's classification of every coset.

## Actual first reader

All 105 responses were banked immediately, before later queries. The 23 inverse matches comprise fourteen median tuples with target zero, six first/middle/last sumset targets, and three last tuples with prescribed prefixes. The complete growth table for every variant, all 39 profile summaries and all six requested maximum-coset lists are retained.

The prefix [2,3,5] leaves 727,398 full-variant length-ten completions to zero and 1,385,539 to one. Prefix [37,41] leaves 8,891,568 completions to target 63. The last ranked completion of each family was selected and ranked back.

The actual containment failures use the whole ambient coset: it has missing vector zero at full-variant length one and missing vector one at without_2 length ten. The latter variant's length-three maximum coset is translated away from zero, illustrating why affine cosets and linear subspaces are separate objects. The empty tuple at length zero was selected and ranked under the explicit API convention.

| Fresh reader work | Value |
|---|---:|
| Saved coefficient reads | 2,075 |
| Prefix XOR operations | 24 |
| Branch candidates / rank additions | 1,102 / 888 |
| Selected tuples | 22 |
| Coset-record / coset-vector reads | 76 / 183 |
| Sumset support lookups | 12 |
| Deletion-profile rows | 42 |
| New convolutions, support compilations or coset masks | 0 |
| Old catalogue generation | 0 |

The construction and reader both completed without an exception or lost response. These counters describe actual work, not a timing benchmark; uncalled error branches have source inspection only.

## Complete files and structural reopening

The original new snapshot has 1,623,313 bytes and blob c0bcd29576a3cce2a3ee64e8c572fa6db733c891. sumset_manifest.json retains all coefficients, masks, provenance and counters, with profiles supplied by three complete shards. input_manifest.json preserves the full source projection except its catalogue, whose three shards use rows [id,code_id,dimension,representative,vertices].

The loader reassembles the original property order and shapes. Compact serialization with a final newline matched both complete original input and snapshot strings exactly. This is byte identity only: no convolution, mask generation, containment classification or reader response was recomputed.

| Shard | Start | Rows | Bytes | Blob |
|---|---:|---:|---:|---|
| input_cosets_00.json | 0 | 15043 | 479956 | f1280fac5d288ee0783c985e94e05f3c71311f74 |
| input_cosets_01.json | 15043 | 10507 | 479951 | 6d6986a6eff970e7343be04c5b68fbfc7f2ba791 |
| input_cosets_02.json | 25550 | 837 | 47814 | 6d220a7cb73396fe52851befd2e63ec7d6e10c79 |
| support_profiles_00.json | 0 | 14 | 444826 | aca431c9090d2ec573776f043eea35b4bc69b23e |
| support_profiles_01.json | 14 | 21 | 425176 | 9e1a9a634381bc2a9c171159d83a64fd27ba9aa7 |
| support_profiles_02.json | 35 | 4 | 164405 | c64540bfcc8498256d1813f9dd71197bc0aaecb4 |

Other immutable identities:
- Constructor/reader source: 41b83f17abb20c80ed9a9982e28e236f9d5a470c, 9,526 bytes.
- Structural loader: 31dad818ddcadc80ced52d934ad0eefa3fb629cf, 786 bytes.
- Input manifest: a4abc176571f5ac3aeac7613c9d275cacf267d4c, 229,104 bytes.
- Result manifest: 2a6074200844f20e1cb3e55c7b854ea909dd443c, 589,461 bytes.
- Complete 105-query output: 69562d8b149e18f02362ae201cbb208e208e4370, 187,292 bytes.

The exact finite families and their saved queries provide no uniform bound as n grows, new proof of Green's conjecture, novelty, external acceptance, sponsor submission or prize claim.
