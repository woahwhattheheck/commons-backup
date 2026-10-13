# Exact one-element extensions of a finite B3 set

This module compiles every obstruction to appending one integer larger than the maximum of a supplied finite B3 set. It retains an equal-sum witness for every rejected value and supports exact counting, ranking, selection and paging of the admissible complement. It treats the seed's B3 property as an identified mathematical premise.

The actual input is the previously established set
\[
B=\{1,13,32,66,169,174,396,416,756,858,915,1016,1044\}.
\]
For this seed the first admissible append is **2197**. Every integer from 1045 through 2196 is forbidden. There are 253 admissible integers at most 3130, and every integer at least 3131 is admissible. Each is a separate one-element extension of B. These statements do not say that several admissible append values can be added simultaneously.

## Sources and conventions

A B3 set has unique sums of exactly three elements when representations are identified as multisets. A summand may occur more than once; different permutations are the same representation. The current [FormalConjectures statement of Erdős 41](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/41.lean) makes this convention explicit with multisets.

[Nathanson and O'Bryant, “The Fourth Positive Element in the Greedy Bh-Set,” Journal of Integer Sequences 27 (2024), Article 24.7.3](https://cs.uwaterloo.ca/journals/JIS/VOL27/OBryant2/obryant4.html), define the classical greedy sequence from the nonnegative seed {0}, appending the least larger integer that preserves the property. Here “first admissible append” refers to the supplied thirteen-element seed. The value 2197 is not presented as a newly discovered term of that canonical zero-seeded sequence or as an extremal record.

The seed retains the Bose–Chowla construction and affine-lift attribution of Commons #31278 and #31280, as carried by #31427. The existing field, primitive element, degree-three argument and affine optimization were not rerun. [Nathanson's 2022 account](https://www.theoryofnumbers.com/melnathanson/pdfs/nath2022-198.pdf) supplies the prior Bose–Chowla context.

Erdős 41 asks whether every infinite B3 subset A of the natural numbers satisfies
\[
\liminf_{N\to\infty}\frac{|A\cap\{1,\ldots,N\}|}{N^{1/3}}=0.
\]
The inspected formal source labels that assertion research open and contains a local placeholder, not an inspected proof. Its pairwise variant is a separate statement. This finite extension index neither establishes the liminf assertion nor supplies an infinite density construction or a current exhaustive literature survey.

## Exact input lineage

The seed is copied from:

- repository: woahwhattheheck/commons;
- commit: 32ff6fc62fc7f43f5b424b0d0c78b5d7e7a1618c;
- file: research/ppl009_erdos241_b3/prime13_saved_triple_decoding.json;
- blob: 43aa8d6f6599221292acba0e57b488642c4c3598;
- member: opened_summary.positive_values;
- original construction blob: 2b77e0e8dc97c5107ab5a4e5cca162a92c12de38;
- original affine-lift blob: 0c31cc4c2e3e2639bb204f4b97095132134932e6.

Both predecessors explicitly avoided complete triple enumeration. No complete pair/triple sum table existed in those retained data. The 91 pair rows and 455 triple rows below are therefore newly formed production inputs to this obstruction computation. They are not a repeated B3 uniqueness check. The constructor never compares the old triples for collisions.

The complete decoded FormalConjectures text was read once from its current contents route. Its independently computed Git-blob content identity is 2a1bd1f521325e36aaaf50a3a3feffc9c426aaf6 (2256 UTF-8 bytes). The provider supplied no immutable commit or blob pin for that read; this is a content identity, not an invented repository revision.

## Why the two obstruction families are complete

Let B be any nonempty finite B3 set of integers, let m=min B and M=max B, and consider x>M. Write kB for sums of exactly k elements of B with repetitions allowed; 0B={0}. The exact forbidden set is
\[
F=\left((3B-2B)\ \cup\
\{z\in\mathbb Z:2z\in3B-B\}\right)\cap(M,\infty).
\]

Consider a collision between two three-term multisets in B union {x}. Let r and s be their numbers of x terms, with r>=s. If r=s, cancellation leaves equal-length old sums. Such old sums are unique: pad both sides with copies of one fixed element of B to obtain equal old triple sums, use the supplied B3 property, and cancel the common padding. Thus a genuine new collision requires r>s.

After cancelling s copies of x,
\[
(r-s)x\in(3-s)B-(3-r)B.
\]
There are only the following cases:

| New-copy multiplicities (r,s) | Consequence |
| --- | --- |
| (1,0) | x lies in 3B−2B |
| (2,0) | 2x lies in 3B−B |
| (2,1) | x lies in 2B−B, already contained in 3B−2B by adding the same fixed old element to both sums |
| r=3 | x is the average of 3−s old elements, so x<=M, contrary to the append domain |

Conversely, each value from the first family gives x+b1+b2=b3+b4+b5, and each integral value from the second gives 2x+b1=b2+b3+b4. They are genuine different multisets because x is outside B. Odd values of the second numerator are discarded: only integer x are candidates.

The first family's maximum is 3M−2m. The second is at most (3M−m)/2, which is no larger because M>=m. Hence
\[
x>3M-2m \quad\Longrightarrow\quad B\cup\{x\}\text{ is B3}.
\]
The singleton case also obeys this formula: both obstruction families lie at or below M, so every larger append is admissible. Empty B is excluded because its maximum is undefined. The implementation accepts nonnegative seeds; the argument itself does not require nonnegativity.

This is a finite, conditional extension argument. It does not re-establish the premise that B is B3.

## Public CommonJS API

The source has no dependencies, file I/O, networking or process calls. It runs in an ordinary CommonJS host or a connected JavaScript isolate.

~~~js
const { compileAppendIndex, openAppendIndex, LIMITS } =
  require("./b3_append_index.cjs");

// For a genuinely new, already established B3 seed:
const snapshot = compileAppendIndex(values, {
  premise_id: "identifier for the supplied finite B3 premise"
});

// For the published actual result, use the saved snapshot:
const api = openAppendIndex(savedRecord.snapshot);
api.classify("2196");
api.appendCertificate("2197");
api.countThrough("3130");
api.page("0", 64);
api.select("10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000");
~~~

The example's saved record is thirteen_seed_extensions.json. Reading it is the caller's responsibility. Do not call the constructor merely to reopen the published result.

### Constructor contract

compileAppendIndex(values, {premise_id}) requires a strictly increasing, nonempty array of nonnegative exact integers. Inputs may be safe JavaScript integers, BigInts or canonical unsigned decimal strings. Repeated input values are rejected rather than interpreted as multiset multiplicities. The premise identifier is retained provenance text; it does not authenticate a mathematical assertion.

The constructor forms unordered pairs i<=j and triples i<=j<=k in lexicographic index order, records their sums, and processes:

1. every triple-row minus pair-row;
2. every triple-row minus seed element, retaining half only if the numerator is even.

For each triple it visits the first family before the second. Only candidates above M are recorded. Each distinct forbidden value keeps the first witness encountered and counts all accepted candidate occurrences in both families. Thus multiplicities count generating pairs of rows, not distinct forbidden integers, ordered triple permutations or unique reduced collision identities.

The constructor sorts the distinct forbidden values, stores the finite gaps between M+1 and the final obstruction, and records the infinite tail beginning one above that obstruction. If there are no obstructions, the tail starts at M+1. The entire result is returned as a JSON-compatible snapshot. Numeric values and arbitrary counts/ranks use decimal strings; small bounded row indices and candidate multiplicities are Numbers.

### Saved reader methods

| Method | Result |
| --- | --- |
| summary() | Seed, sizes, finite gap count, tail and first admissible append |
| classify(value) | ALLOWED with rank, FORBIDDEN with full displayed collision, or OUTSIDE_APPEND_DOMAIN |
| countThrough(value) | Number of admissible appends in (M,value], zero when value<=M |
| rank(value) | Zero-based numerical rank for a member, null otherwise; also insertion rank |
| select(rank) | The admissible integer at any supported nonnegative rank |
| page(start,count=32) | A page in increasing numerical order; the family has an infinite tail |
| forbiddenPage(start=0,count=32) | Explicit saved equal-sum witnesses in increasing forbidden-value order |
| sourceRows("pairs" or "triples",start=0,count=32) | Saved new sum-table rows with their original index references |
| appendCertificate(value) | The enlarged one-element set and conditional B3 conclusion, or NOT_APPENDED with its obstruction |
| stats() | Reader work counters, without incrementing the query counter |
| snapshot() | An outward copy of the saved record, without incrementing the query counter |

Pages use zero-based start positions. Admissible ranks are zero-based and refer to ordinary integer order. countThrough uses an inclusive upper endpoint. Each appended set includes the old seed and one chosen value; no operation certifies a batch of several allowed values together.

The append certificate's triple count is the combinatorial value C(n+3,3) for the enlarged (n+1)-element set, not a second enumeration of its triples. In particular, the thirteen-element input yields fourteen elements and 560 unordered triples with repetitions after one accepted append.

All returned arrays and records are outward copies or newly allocated output. The reader holds a private deep copy of its input. A caller cannot change later query results by modifying a returned summary or snapshot.

### Reader validation boundary

openAppendIndex performs bounded structural checks: schema, canonical integer forms, seed order, pair/triple dimensions and indices, ordered forbidden values, witness references, positive multiplicity totals, ordered gap endpoints, rank-prefix/length relations, tail endpoint and saved partition size.

It does **not** regenerate sums, enumerate candidate differences, prove old B3 uniqueness, recompute the safe bound formula, or independently authenticate the completeness or arithmetic of imported tables. In particular, dimensions alone do not prove that all unordered index tuples or forbidden values are present. Its gap-size relation is a structural consistency check, not an independent proof that the gaps are exactly the forbidden complement. Saved witness rendering copies the saved common sum and carries arithmetic_rechecked:false.

Correct mathematical answers require an authentic constructor output with the stated B3 premise. This is explicit provenance, not a general-purpose verifier for arbitrary claimed snapshots.

## Exact navigation without scanning to a large target

Let the sorted forbidden values be f0,...,f(F−1). For y>M,
\[
A(y)=y-M-\#\{i:f_i\le y\}.
\]
Binary search gives the final count. For an admissible y, its rank is A(y)−1. A nonmember's insertion position is the number of admissible values below it.

Finite allowed gaps retain their starting rank and length. Selection finds the gap containing the requested rank by binary search. If T is the tail start and C is the finite allowed count, rank r>=C selects T+r−C directly. Thus neither a target with hundreds of digits nor a rank of that size requires generation of preceding integers.

Here F=1833, M=1044, T=3131 and C=253. Consequently A(y)=y−2877 once y>=3131, and select(r)=r+2878 for r>=253. The actual query at rank 10^100 returns 10^100+2878.

## Complete actual result

The single new construction produced:

| Quantity | Actual value |
| --- | ---: |
| Seed size | 13 |
| New unordered pair rows | 91 |
| New unordered triple rows | 455 |
| First-family candidates | 41,405 |
| First-family hits above M | 10,939 |
| Second-family candidates | 5,915 |
| Odd second numerators discarded | 2,820 |
| Integral second candidates at or below M | 2,854 |
| Second-family hits above M | 241 |
| Total retained candidate hits | 11,180 |
| Distinct forbidden values | 1,833 |
| Repeated hits after first insertion | 9,347 |
| Finite admissible gaps | 134 |
| Admissible values through 3130 | 253 |
| First admissible value | 2197 |
| Infinite admissible tail starts | 3131 |

For this input all 1833 first witnesses use the one-new family; the second family adds multiplicities but no additional forbidden integer. Both families remain necessary in the generic derivation and implementation. The general two-new-first-witness branch was source-inspected, not exercised by this consumer.

Examples from the actual saved reader are:
\[
1045+13+32=1+174+915=1090,
\]
\[
2196+1+32=169+1016+1044=2229,
\]
and
\[
3130+1+1=1044+1044+1044=3132.
\]
These are explicit rejection witnesses. The intervening forbidden integers have their own retained row references and counts; no reader needs to reconstruct the candidate loop to obtain them.

The conditional first extension is
\[
\{1,13,32,66,169,174,396,416,756,858,915,1016,1044,2197\}.
\]
The word “first” is exact for this fixed seed and the append-only order. It is not a minimum possible endpoint over all fourteen-element B3 sets.

## Once-only execution and saved-data use

The frozen executed source is blob 9348d6e9e955522536bb3ad520849ff68d385f15, 12728 UTF-8 bytes. It was checkpointed before computation. The complete initial constructor packet was then saved as blob 7d7f0c8f62342190ccf52b1658bb0330ccdcac2b, 263348 bytes.

A fresh module context loaded that snapshot and made **22 actual queries**. The retained results include:

- all 253 finite admissible values through four pages, plus eight values from the infinite tail;
- classifications at 1045, 2196, 3130 and 3131;
- ranks of 2197 and the rejected endpoint 3130;
- counts through 2196, 3130 and 10^100;
- a B3 append certificate at 2197;
- the large-rank selection and its separate one-element append certificate;
- six displayed forbidden-page rows and ten saved sum-table rows.

There were 262 selected values, ten rendered witness rows and 1985 binary comparisons. The reader structurally inspected 91 pair rows, 455 triple rows, 1833 forbidden rows and 134 gap rows. It formed zero sum rows and replayed zero candidate pairs, old B3 checks or field operations.

The measured constructor time was 10 ms and reader opening time 4 ms in this one connected V8 observation. These are not benchmarks. General larger inputs, singleton inputs, malformed inputs and unused error branches were source-inspected only. No test suite, synthetic input or prior computation was run.

thirteen_seed_extensions.json retains the full snapshot and every query output. Its compact JSON is 273512 UTF-8 bytes, blob 1d2710d39c548add71f38ce76c68d90ed117237a. The accepted input lineage remains embedded. No truncated example stands in for missing data.

## Hard bounds and costs

The implementation limits a seed to 24 elements, nonnegative integer inputs/ranks to 1024 decimal digits, candidate pairs to 1,000,000, forbidden rows to 200,000, JSON snapshots to 12,000,000 characters and pages to 64 records. A constructor rejects before sum formation if the largest triple sum exceeds the integer-digit limit. Query arithmetic may return a decimal with one additional digit at the input limit; a later input still obeys its documented 1024-digit cap. Such boundary cases were not exercised here.

For n seed elements there are P=n(n+1)/2 pairs, T=n(n+1)(n+2)/6 triples and T(P+n) candidate operations. Sorting the distinct forbidden values costs O(F log F) comparisons. The snapshot stores O(P+T+F) records, including finite gaps. A saved count/rank/classification query uses O(log F) binary comparisons; a selection uses O(log G) comparisons for G finite gaps, or direct tail arithmetic. BigInt arithmetic cost depends on operand length and is not constant in the digit size.

These finite computational limits are unrelated to the domain of the infinite conjecture. The artifact supplies an exact reusable finite extension index, with prior mathematical attribution and explicit imported-premise boundaries; it asserts no new density theorem, global extremal value, novelty, prize or sponsor submission.
