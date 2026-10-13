# Numerical interval rank/select from retained residue rules

`residue_interval_index.cjs` supplies an ordinary numerical index for the complement of finitely many forbidden congruence classes inside an inclusive integer interval. It exports `compileResidueInterval`, `createIntegerGapIndex`, and `limits`. Both operations run in connected V8 or a CommonJS host, use exact `BigInt` arithmetic, and have no imports or I/O.

The [retained full-period CRT API](CONNECTED_CRT_INDEX.md) addresses admissible tuples in mixed-radix order. The new API answers which admissible integers occur first, in the middle, or at a specified numerical rank in a requested interval. It builds the forbidden hits and the gaps between them, without constructing the full CRT period or visiting every interval integer.

## Actual retained-input result

The [complete dataset](residue_interval_45773612811_45775397187.json) applies the [118 retained rules](prime_block_252_1024.json) for primes \(251<p\le1024\) to

\[
L=45{,}773{,}612{,}811,\qquad
U=45{,}775{,}397{,}187.
\]

Both endpoints are retained values from [Commons #31166](https://github.com/woahwhattheheck/commons/pull/31166). Their earlier digit conditions choose this consumer's interval only; no implication for the squarefreeness of \(n^4+2\) is asserted.

| Quantity | Actual value |
| --- | ---: |
| Requested integers, endpoints included | 1,784,377 |
| Retained prime rules | 118 |
| Rules with a forbidden class | 40 |
| Forbidden congruence classes | 100 |
| Emitted class/value incidences | 816 |
| Distinct excluded integers | 816 |
| Integers hit by multiple classes | 0 |
| Candidates avoiding these rules | 1,783,561 |
| Maximal nonempty candidate gaps | 817 |

Every excluded integer has an explicit proper square-divisor witness in the dataset. Every maximal gap is retained, including its endpoints, size, first rank and last rank. This gives a lossless description of all candidates without writing out more than a million individual values.

For example, the first excluded value has the recorded identity

\[
45{,}773{,}613{,}042^4+2
=563^2\cdot13849815431065203246076830169504175042.
\]

The recorded prime square is \(316{,}969\), and the cofactor exceeds one. This is the first matching retained class, with no least-divisor claim. The same exact product check was performed for all 816 new witness records.

The candidates avoid precisely the supplied prime-square rules. Primes at most 251 and primes greater than 1024 can still supply square divisors. These counts do not certify squarefree values or establish an unbounded conclusion.

## Why the congruence compiler is complete

For a forbidden residue \(r\) modulo a positive integer \(m\), let residues be normalized into \([0,m)\). The first hit at or above \(L\) is

\[
f=L+\bigl((r-(L\bmod m))\bmod m\bigr).
\]

It satisfies \(f\equiv r\pmod m\) and \(L\le f<L+m\). Consequently every hit of this class inside \([L,U]\) is exactly one of

\[
f,\ f+m,\ \ldots,\ f+(h-1)m,
\qquad
h=
\begin{cases}
0,&f>U,\\
1+\lfloor(U-f)/m\rfloor,&f\le U.
\end{cases}
\]

The compiler computes this count for every forbidden class before emitting any hits. It rejects a request whose total incidence count exceeds the requested budget. Once admitted, it emits the finite progressions, sorts by integer value and class index, and groups equal values.

The resulting excluded set is exactly the union of the supplied congruences on the requested interval. A value that belongs to several classes is excluded once and retains every matching class index. This argument needs no coprimality condition. The compiler works with overlapping, repeated or noncoprime moduli, as well as the prime squares used here.

The incidence budget includes duplicates across classes. It cannot be weakened to the distinct-exclusion count before the hits are grouped. Within one rule, duplicate forbidden residues are rejected as an input error; the same congruence in separate rules is accepted and contributes separate provenance references.

## Numerical rank, selection and range counts

Let the sorted distinct excluded values be \(e_0<\cdots<e_{E-1}\). The gap index consumes that increasing list and creates each maximal nonempty part of its complement in \([L,U]\). Its constructor checks the partition identity

\[
\sum_{\text{gaps }[a,b]}(b-a+1)+E=U-L+1.
\]

For a candidate \(n\), its zero-based numerical rank is

\[
\operatorname{rank}(n)
=n-L-\#\{e_i:e_i<n\}.
\]

The same expression gives the number of candidates below an excluded value, without assigning that value a rank. A binary search in the exclusion list supplies the count.

Each gap stores its cumulative first rank. If a gap starts at \(a\), has length \(\ell\), and has first rank \(q\), it contains exactly ranks \(q,\ldots,q+\ell-1\). Selection finds the containing gap by binary search and returns

\[
\operatorname{select}(k)=a+(k-q).
\]

A range query clips its requested interval to the indexed interval, subtracts the number of excluded points within that intersection, and returns the exact candidate count. Its endpoints are inclusive.

Constructing the gap index uses a linear pass through the excluded list. Selection uses a binary search over the gaps; location and range queries use binary searches over the excluded values. Gap pages only materialize their requested records. Arithmetic cost also depends on integer length, bounded as described below.

## Compiler contract

Call:

```javascript
const compiled = compileResidueInterval({
  from,
  through,
  rules,
  max_hits: 100000
});
```

The endpoints are required and satisfy `from <= through`. Signed integers are supported. Each rule is an object with a positive `modulus` and an array `bad_residues` containing distinct residues from zero through modulus minus one. Additional fields such as the retained prime `p` and lift provenance are ignored. The retained `prime_block.records` array can be passed directly.

Integer inputs accept BigInts, safe integer Numbers, or canonical decimal strings. Canonical strings allow zero or a nonzero integer with an optional minus sign. Leading zeroes, a plus sign, whitespace, exponent notation, fractions and the string `"-0"` are rejected; numeric negative zero becomes zero. Integer results use decimal strings.

The compiler returns schema `commons.residue_interval_compilation/v1` with:

- exact requested, incidence, excluded and candidate counts;
- every class's source rule/residue indices, modulus, residue, hit count, first hit and last hit;
- every distinct excluded value with all matching class indices;
- overlap counts and the actual bounded work counters.

A class with no hit has null first/last fields and a zero count. Class indices follow input rule order, then the original residue order. Residues need not be sorted. No rule is silently combined with another, and the compiler does not inspect polynomial roots or prove primality.

An empty rule list, or rules with empty forbidden lists, excludes nothing. Modulus one is permitted: its forbidden residue zero covers the whole interval, subject to the incidence budget. These are general congruence semantics, separate from the retained prime-square source.

## Saved-gap index contract

Call `createIntegerGapIndex({from, through, excluded_values})`. The exclusion list must be strictly increasing, distinct and contained in the interval. It is copied into internal exact integers. The constructor checks ordering and endpoints; it does not recompute residue rules or certify that a caller's exclusion list is complete for a polynomial.

| Method | Result |
| --- | --- |
| `describe()` | Inclusive endpoints, exact counts, gap count, ordinary numerical order and zero-based rank metadata. |
| `select(rank)` | The candidate at that rank, its containing gap and offset within the gap. |
| `locate(value)` | `INDEXED` with its rank; `EXCLUDED` with its exclusion index; or `OUTSIDE`. Every result includes the number of indexed candidates below the supplied value. |
| `range({from, through})` | The clipped inclusive interval and exact requested, excluded and candidate counts. A disjoint query returns a null clipped interval and zero counts. |
| `gaps({start_index, limit})` | A bounded page of complete gap records with the next start index, or null when pagination reaches the end. |

The index can be empty when every interval integer is excluded. In that case there are no gaps, every selection rank is invalid, and range/location counts remain defined. With no exclusions the interval itself is the one gap.

For `locate`, values below the indexed interval have zero candidates below them; values above it have the total candidate count. The method does not normalize values modulo a period.

Each thrown validation error is an `Error` with a stable `code` field. Codes identify malformed input, reversed intervals, invalid moduli or residues, duplicate local residues, exceeded bounds, invalid ranks, or unordered/out-of-range exclusions. A rejected compiler request does not return a partial index.

## Hard bounds

| Bound | Maximum |
| --- | ---: |
| Decimal digits in an endpoint, modulus, residue or location/range integer | 256 |
| Decimal digits in a selection rank | 257 |
| Rules per compilation | 256 |
| Total forbidden classes | 4,096 |
| Emitted congruence incidences | 100,000 |
| Excluded integers supplied to a gap index | 100,000 |
| Gap records per page | 1,000 |

Ranks allow 257 digits because an interval between signed 256-digit endpoints can have a 257-digit size. Counts and rank arithmetic remain BigInt; array indices are bounded Numbers.

The optional `max_hits` is an integer from zero through 100,000, with 100,000 as the default. Validation and class counting occur before the incidence-budget decision. The budget bounds emitted records, not elapsed time. A large interval with few forbidden hits is supported; a small interval with many repeated forbidden rules can exhaust the budget.

Compiler storage is proportional to the class and hit counts. It sorts the emitted hits using the runtime's array sort. The recorded comparison count describes this actual V8 execution; it is not a portable benchmark or fixed sort guarantee.

## Consume the saved result in a fresh runtime

Read the complete module and dataset texts through the connected repository reader. The following uses the saved exclusions directly:

```javascript
const moduleBox = {exports: {}};
new Function("module", "exports", completeSource)(
  moduleBox,
  moduleBox.exports
);
const saved = JSON.parse(completeDataText);
const index = moduleBox.exports.createIntegerGapIndex(
  saved.persisted_gap_input
);
const middle = index.select("891780");
const firstRange = index.range({
  from: "45773612811",
  through: "45773712810"
});
text({middle, firstRange});
```

An ordinary CommonJS host can import the same exports with `require("./residue_interval_index.cjs")`.

For a new interval, pass the saved rules into `compileResidueInterval`, then serialize its endpoints and sorted `excluded_records.map(row => row.value)`. Those values are sufficient to recreate numerical navigation. Retain the full compilation as well when class provenance matters.

## Recorded consumer and work

The compiler ran once on the specified retained inputs. It used 40 starting-modulus reductions, 100 residue alignments, 100 progression-length divisions, 816 emitted incidences and 6,677 sort comparisons. It scanned zero interval integers and built no CRT period. The compiler-plus-witness observation took 11 ms in this runtime; this single timing is not a comparative performance claim.

The 816 witness constructions each evaluated \(n^4+2\), divided by the selected retained \(p^2\), and checked an exact product identity with a cofactor greater than one. They did not refactor the quartic values or reconstruct the old prime/root/lift computations.

The gap-index input was serialized as 11,490 characters. A fresh V8 isolate constructed one index from that saved text, without rerunning the compiler. The actual consumer made one description call, three selections, two locations, one range query and seven gap-page calls of at most 128 records. All 817 returned gaps are present in the dataset.

| Numerical query | Actual result |
| --- | --- |
| Select rank 0 | 45,773,612,811 |
| Select rank 891,780 | 45,774,505,000 |
| Select rank 1,783,560 | 45,775,397,187 |
| Locate 45,773,613,042 | Excluded; 231 candidates lie below it |
| Locate 45,774,504,999 | Indexed at rank 891,779 |
| Count candidates in [45,773,612,811, 45,773,712,810] | 99,956 of 100,000 integers; 44 exclusions |

The first maximal gap is \([45{,}773{,}612{,}811,45{,}773{,}613{,}041]\), with 231 candidates. The last is \([45{,}775{,}394{,}259,45{,}775{,}397{,}187]\), with 2,929. The complete intervening gaps and all their rank boundaries are retained.

## Sources and scope

The local rules come from [Commons #31121](https://github.com/woahwhattheheck/commons/pull/31121), whose prime-block blob is `31170471fd5958acdcf7f954ccccdfae4e2b0e0f`. The local arithmetic and Hensel-lifting attribution remain with that construction and its [accepted source contribution](https://github.com/conjectures-io/conjectures-contribution/tree/main/contributions/erdos-978-parts-iii/9a9241fd706f8b096cd34d40d7d6ba62d230f954361dd8d648e3fb21591f0d0b). The contribution identifier and script blob `8c2962f14f9dfce9ee59b00479d891800f6a7666` are bound in the new dataset. No accepted proof or root/lift computation was replayed.

[Commons #16072](https://github.com/woahwhattheheck/commons/pull/16072) supplied the earlier finite CRT composition. The [July 28, 2026 working report](https://erdosproblemaday.com/report/978), attributed to Patrick White, already reports overlapping local root and lift calculations. This delivery preserves that credit and makes no new local-discovery, computation-range or mathematical-priority claim.

The endpoint dataset's exact blob is `36354d1c19cf5156679e65cedf0c0b73ff59d679`. It is consumed through its two retained values, with no digit search replay. Full path, merge and JSON-pointer provenance for both input datasets appears in the new data file.

The deliverable is a finite congruence compiler, a reusable numerical navigation API and their complete new consumer records. The general API preserves overlaps even though this particular interval has none. A surviving integer can still fail another prime-square rule. No infinite squarefree-value statement, large-prime tail estimate, external frontier advance, formal elaboration or sponsor submission is established here.
