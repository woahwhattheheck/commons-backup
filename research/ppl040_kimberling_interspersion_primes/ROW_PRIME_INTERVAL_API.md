# Kimberling's interspersion: exact finite row-prime intervals

This module classifies every value in a bounded column interval of one row of Kimberling's triangular-number array. It retains a complete small-prime basis, all local column residue rules, and a least-prime-divisor/quotient witness for every composite. A saved index supports rightward extension and exact finite count/rank/select operations.

The actual consumer uses row **493**, columns **10,001 through 22,000**. It found **1,124 primes and 10,876 composites**. The first 10,000 columns were compiled once; a fresh saved-state consumer appended the next 2,000 columns without rebuilding the prime basis or local rules. Both complete snapshots are supplied.

## 1. Source and mathematical question

[Clark Kimberling's author page](https://faculty.evansville.edu/ck6/integer/unsolved.html), section 15, asks whether every row of a particular displayed natural-number array contains infinitely many primes. It does not ask this about arbitrary interspersions. His comments in [OEIS A185787](https://oeis.org/A185787) give the array formula
\[
T(r,c)=r+\frac{(r+c-2)(r+c-1)}2,\qquad r,c\ge1.
\]
The row and column indices are one-based. A185787 itself is a derived column-sum sequence; the array formula is in its COMMENTS, so its listed sequence terms must not be relabelled as array rows.

Kimberling's March 2012 notes credit Charles Greathouse and Pedja Terzic for the conditional Hardy–Littlewood/Bunyakovsky discussion. Those observations and the polynomial description retain their original attribution. The present work makes no unconditional assertion of infinitely many primes in a row and no claim of a current exhaustive literature frontier. It supplies an exact finite sieve and reusable saved data.

Row 493 was selected using only the retained point-count scalar from Commons #31400, whose complete Cartesian-distance data has Git blob `75dad6ddfd00a0efb2c80bddb12eb4e13405d216`. No earlier geometric calculation was repeated, and that scalar carries no asserted implication about the prime distribution in this row. No source-authored prime example or earlier row enumeration was used as a runtime input.

## 2. Exact local divisor rules

Fix a row \(r\), and write
\[
s=r+c-2,\qquad T=r+\frac{s(s+1)}2.
\]
The elementary identity
\[
8T=(2s+1)^2+8r-1
\]
converts divisibility by an odd prime \(p\) into a square-root problem:
\[
p\mid T(r,c)
\quad\Longleftrightarrow\quad
(2s+1)^2\equiv D_r\pmod p,
\qquad D_r=1-8r.
\]
Both 2 and 8 are invertible modulo an odd prime. If \(u^2\equiv D_r\pmod p\), the corresponding column class is
\[
c\equiv (u-1)2^{-1}-r+2\pmod p.
\]

There are three cases.

- If \(D_r\equiv0\pmod p\), the only square root is zero, producing one column class.
- If \(D_r\) is a nonzero quadratic residue, its two roots \(u,-u\) produce two distinct classes.
- If it is a quadratic nonresidue, there are no classes.

These are complete lists: a degree-two polynomial over a field has at most two roots, and the displayed roots attain the possible counts. The map from roots to column classes is invertible. Each rule therefore covers every divisibility hit, not a sample of hits.

Period \(p\) is valid for odd \(p\), since
\[
T(r,c+p)-T(r,c)=ps+\frac{p(p+1)}2
\]
is divisible by \(p\). The rule's representatives lie in \(\{0,\ldots,p-1\}\), but the actual column interval remains a range of positive ordinary integers.

### Prime 2

The odd-prime identity cannot be inverted modulo 2. Instead,
\[
\frac{(s+4)(s+5)-s(s+1)}2=4s+10
\]
is even, so the parity pattern has period four. The triangular terms for \(s\bmod4=0,1,2,3\) have parities \(0,1,1,0\). Combining these with \(r\bmod2\) gives exactly two allowed column residues modulo four.

For the actual row \(r=493\), divisibility by 2 occurs at
\[
c\equiv2,3\pmod4.
\]
The complete saved rule table also includes the discriminant-zero case \(p=3943\), with the single column class \(c\equiv1480\pmod{3943}\). This is an actual retained local rule, not a general infinitude result.

### Modular square-root computation

The modular square-root problem and its algorithms are classical; see Menezes, van Oorschot and Vanstone, [*Handbook of Applied Cryptography*, chapter 3](https://cacr.uwaterloo.ca/hac/about/chap3.pdf), §3.5.1, Algorithms 3.34 and 3.36 on printed page 100. Their general algorithm's stated inputs are an odd prime and a nonzero residue candidate. This implementation handles zero and prime 2 separately. It uses deterministic bounded nonresidue search, so the handbook's randomized expected-time statement is not transferred to it.

Here is the invariant for the order-reduction routine actually used. For a nonzero quadratic residue \(a\), write \(p-1=2^e q\), with \(q\) odd, and choose a quadratic nonresidue \(z\). Initialize
\[
C=z^q,\qquad x=a^{(q+1)/2},\qquad t=a^q,\qquad m=e.
\]
Then \(C\) has exact order \(2^m\), \(t\) has order dividing \(2^{m-1}\), and
\[
x^2=at\quad\text{in }\mathbb F_p.
\]
The order claims follow from Euler's criterion.

If \(t\ne1\), let \(i\) be the smallest positive integer with \(t^{2^i}=1\). Thus \(i<m\). Put
\[
b=C^{\,2^{m-i-1}},\quad
x'=xb,\quad C'=b^2,\quad t'=tb^2,\quad m'=i.
\]
The new \(C'\) has order \(2^i\). Both \(t\) and \(b^2\) have \(2^{i-1}\)-st power \(-1\), so their product has order dividing \(2^{i-1}\). Also \(x'^2=at'\). The same invariant holds with strictly smaller \(m\); eventually \(t=1\), giving \(x^2=a\). When \(p\equiv3\pmod4\), the routine uses the standard shortcut \(x=a^{(p+1)/4}\).

The implementation searches successive integers starting at 2 for a nonresidue. Existence follows because an odd prime field has nonzero nonsquares. The explicit prime cap makes this a bounded deterministic computation; no general polynomial-time assertion about that search is made.

## 3. Why the finite classification is exact

### Complete prime basis

The constructor builds all primes through a caller-specified limit \(B\), together with a least-factor array for every integer from zero through \(B\). It processes integers increasingly. An unmarked integer is prime; starting from its square, its multiples receive it as a factor if they have not already been marked.

Every composite integer has a prime divisor no larger than its square root. That divisor is processed before the composite, so every composite through \(B\) is marked. The first marking comes from its least prime factor. This is the ordinary sieve of Eratosthenes, with the complete factor array retained rather than only a prime list.

### Complete interval sieve

The constructor requires
\[
B\ge\left\lfloor\sqrt{\max_{c\in[L,U]}T(r,c)}\right\rfloor.
\]
The row values increase strictly because
\[
T(r,c+1)-T(r,c)=r+c-1>0.
\]
The maximum is therefore the last value, and the coverage test is exact.

For each basis prime, the algorithm visits every hit of every retained column residue within the requested interval. It processes primes increasingly and records a factor only when a value has not already received one. If a hit has value exactly \(p\), it remains prime: divisibility by itself is not a compositeness witness.

Now let a row value \(v\ge2\) be composite. Its least prime divisor is at most \(\sqrt v\), hence lies in the complete basis. Its local rule reaches that column. The first prime that marks it is its least prime divisor, and its stored quotient \(v/p\) is an exact integer greater than one. Conversely, a recorded proper divisor proves that its value is composite.

Every unmarked value at least two is therefore prime. The value one is classified separately as `UNIT`. These statements prove finite exactness under the recorded basis coverage; they do not require a probabilistic primality test.

The quotient in a composite record is not asserted to be prime. A least-divisor/quotient witness is not generally a full factorization.

### Saved rightward extension

An appended interval begins at the next column. Its first value is obtained from the retained last value by the same first-difference formula; later new values use successive increments. The prime basis and all local residue rules depend only on the fixed row and basis limit, so they remain valid.

Before appending, the API checks the new maximum against the value and basis-coverage limits. It then sieves only the new columns. Existing records, basis factors, prime rules and earlier segment records are retained; prime indices for the new segment are shifted and appended. No existing column is reclassified.

This argument consumes the mathematical correctness of the saved source. Structural loading by itself does not prove that an arbitrary supplied state satisfies those premises.

## 4. Actual row-493 result

| Quantity | Initial segment | Saved-rule append | Final interval |
| --- | ---: | ---: | ---: |
| Columns | 10,001–20,000 | 20,001–22,000 | 10,001–22,000 |
| Number of columns | 10,000 | 2,000 | 12,000 |
| Primes | 953 | 171 | 1,124 |
| Composites | 9,047 | 1,829 | 10,876 |
| Units | 0 | 0 | 0 |
| First value | 55,046,771 | 209,971,771 | 55,046,771 |
| Last value | 209,951,279 | 252,934,279 | 252,934,279 |

The final maximum has floor square root 15,903, within the chosen basis limit 16,384. The basis contains 1,900 primes and the full 16,385-entry factor array, including entries for zero and one.

All 1,900 local rules are retained. Their method cases are:

| Case | Number of rules |
| --- | ---: |
| Prime 2, period four | 1 |
| Nonresidue, no hit classes | 954 |
| Nonzero root using order reduction | 453 |
| Nonzero root using \(p\equiv3\pmod4\) shortcut | 491 |
| Discriminant zero | 1 |

Together they supply 1,891 column residue progressions. Both snapshots retain every row value and classification, all prime record indices, all composite least-divisor/quotient witnesses, and a complete per-rule hit/assignment table for each executed segment.

The first prime column in the retained final interval is 10,004; the last is 21,996. These are endpoints within the stated interval, not the first and last primes of the infinite row.

### Saved-reader consumer

A third fresh module context opened the final snapshot and made six public queries:

| Operation | Actual result |
| --- | --- |
| Count through column 21,000 | 1,045 primes within retained columns 10,001–21,000 |
| Select zero-based prime rank 562 | Column 15,872, value 133,882,559 |
| Rank that column | 562 |
| Prime page beginning at rank 953 | First sixteen primes in the appended segment |
| Record at column 22,000 | \(252,934,279=13\cdot19,456,483\), least divisor 13 |
| Classification page at columns 20,001–20,008 | All eight complete records retained |

The sixteen prime columns are
\[
20004,20005,20025,20080,20092,20093,20100,20116,
20145,20149,20161,20165,20168,20169,20176,20192.
\]
The corresponding values and all source references are in the final data file. The first appended column has the retained witness
\[
T(493,20001)=209,971,771=107\cdot1,962,353,
\]
with 107 its least prime divisor.

Every count and rank is relative to the retained finite interval. In particular, the count through column 21,000 does not include the uncomputed columns 1 through 10,000.

## 5. Public interface

The dependency-free CommonJS module exports:

- `compileInterspersionRowPrimeIndex(request)`;
- `openRetainedInterspersionRowPrimeIndex(snapshot)`;
- the frozen `INTERSPERSION_ROW_LIMITS` object.

A compile request has `source_id`, `row`, `first_column`, `last_column` and `prime_basis_limit`. Row and column inputs accept positive BigInts, safe integer Numbers, or canonical positive decimal strings. Leading zeros, signs and fractions are not accepted in strings. The basis limit is a bounded Number integer.

The constructor returns `{status: "COMPLETE", index}` or a `CAP_STOP` record with its reason and a null index. Invalid integer formats, invalid parameter types and reversed intervals raise a TypeError.

| Index method | Contract |
| --- | --- |
| `summary()` | Source IDs, finite interval, basis size, segment count and classification totals |
| `selectPrime(rank)` | Prime at a zero-based rank in the retained interval |
| `rankPrime(column)` | Rank of a retained prime column, or its nonprime record |
| `countPrimesThrough(column)` | Inclusive count clipped to the retained interval |
| `pagePrimes(startRank, limit)` | Bounded prime page in increasing column order |
| `recordAtColumn(column)` | Exact PRIME, COMPOSITE or UNIT record for one retained column |
| `pageRecords(startColumn, limit)` | Consecutive complete classification records |
| `localRule(prime)` | Copied local rule for a Number integer in the retained prime basis |
| `appendThrough(lastColumn, {source_id})` | New immutable index extending strictly to the right |
| `snapshot()` | Complete JSON-compatible state |
| `work()` | Copied construction, reuse, structural-read and query counters |

Prime selection returns `FOUND` or `OUT_OF_RANGE`. A rank request outside the saved interval returns `OUTSIDE_RETAINED_INTERVAL`; a retained composite or unit returns `NOT_PRIME` with its record. Record pages require their starting column to be inside the saved interval. Prime pages can start beyond the final rank and then return an empty page. Both page types expose the next cursor and whether more records remain.

The prime order is ordinary increasing column order. Since row values increase, it is also increasing value order. It is not a rank among all primes of the row. Query column and rank inputs are nonnegative exact integers under the query digit cap, so column zero simply lies before the retained interval.

Decoded row, column and value fields are decimal strings. Counts, local primes, record indices and found ranks are bounded Number integers. The compact saved records use exact Number integers within the value cap; all remain exactly representable.

All returned records are copied or freshly constructed. Parent and appended indices expose no mutable references to the basis or row records. A source ID is caller-supplied lineage metadata, not source authentication.

### Open the complete delivered state

```js
const {
  openRetainedInterspersionRowPrimeIndex
} = require("./interspersion_row_prime_index.cjs");
const saved = require("./row493_columns10001_22000.json");

const index = openRetainedInterspersionRowPrimeIndex(saved.snapshot);
index.countPrimesThrough("21000");
index.selectPrime("562");
index.pagePrimes("953", 16);
index.recordAtColumn("22000");
```

The earlier complete snapshot is in `row493_columns10001_20000.json` at the same `snapshot` field. The actual append opened that state and called `appendThrough("22000", {source_id: ...})`. Repeating that call is unnecessary to consume the delivered final file.

The module can also be evaluated with a fresh CommonJS `module.exports` object in the connected V8 runtime. That is the route used here. The file-loading example above describes normal CommonJS use, not an executed native-process step.

## 6. Saved records and trust boundary

The index schema is `commons.kimberling15.row_prime_index/v1`. It retains:

- the row, source IDs and inclusive interval;
- the complete prime list and `least_factor_by_integer` array through the basis limit;
- one local rule per basis prime, including its period, complete residue list, discriminant, Euler value, square root and method fields;
- every column record and every prime record index;
- the summary and every segment's complete rule-usage table.

A compact column record has five fields:
`[column, value, least_prime_divisor_or_zero, quotient_or_zero, rule_index_or_minus_one]`.
An unmarked value at least two is prime. Value one is a unit. A composite has a positive least divisor, its exact quotient, and a rule index. A segment's rule-usage row is
`[rule_index, hits, new_composite_assignments, basis_prime_self_hits]`.
The record order supplies complete column coverage, and the rule order matches the increasing prime basis.

The loader checks bounds, integer formats and structural references. It checks the complete factor-array shape, prime/factor references, local-rule case shapes, consecutive columns, increasing saved values, record tags and prime-index agreement, classification counts, contiguous segment coverage, and full rule-usage tables. It also checks that the stored floor-square-root bounds the saved maximum and lies within the basis limit.

It does not rebuild the prime sieve, test the primality of the supplied prime list, recompute row formulas, verify modular roots or hit classes, divide every saved value again, or independently prove that every recorded divisor is least. Some summary endpoint checks establish membership and identity, not every possible extremality relationship. Those mathematical facts are supplied by the actual constructor and its retained provenance.

The file identities bind the actual source and prior snapshot used by the recorded append. Loading unrelated or modified caller data does not make it a mathematical certificate merely because its structure is accepted.

## 7. Arithmetic and resource bounds

| Resource | Public bound |
| --- | ---: |
| Prime-basis limit | 65,536 |
| Maximum row value | 4,294,967,296 |
| Total columns, including appends | 20,000 |
| Total saved segments | 16 |
| Decimal digits in row/column construction inputs | 16 |
| Decimal digits in query inputs | 1,000 |
| Page size | 128 |
| Source-ID characters | 512 |

The constructor computes the maximum requested row value with BigInt before converting bounded values to Number. New row values use exact first differences. Every modular factor is below its prime, so modular products are below \(65,536^2=2^{32}\), and all stored values and quotient calculations stay within exact integer range. The square-root floor starts with a floating estimate and adjusts it using exact integer-square comparisons; no rounded square-root result is accepted without those comparisons.

The cap checks occur before basis construction for a new compile and before any new segment sieve for an append. A stop may identify total column count, segment count, value cap or insufficient basis coverage. The current basis is not silently enlarged. A stopped request does not prove that its omitted values are composite or prime.

The initial construction used 28,733 basis-mark visits, built 1,900 local rules, made 5,316 modular-power calls and 81,801 calls to the modular-multiplication helper, and evaluated 10,000 new column values. Its 20,525 progression hits assigned 9,047 composite witnesses; the other 11,478 hits already had a smaller divisor.

The append reused all 16,385 basis entries, 1,900 rules and 10,000 prior column records. It made no basis builds, modular powers or modular-multiplication-helper calls. Its 4,136 hits over only 2,000 new columns assigned 1,829 new composite witnesses and skipped 2,307 hits with an earlier divisor. Complete per-rule counters are retained for both segments.

Observed elapsed times were 16 ms for initial compilation, 20 ms to open the initial snapshot, and 4 ms for the append. Opening the final snapshot took 18 ms. The six saved queries recorded 0 ms at Date.now's millisecond resolution; that is not zero execution time. These are individual observations, not statistical benchmarks or a comparison with another sieve.

The final reader structurally read 16,385 basis entries, 1,900 prime references, 1,900 rules, 12,000 column records and 3,800 segment-rule rows. Its six queries used 20 binary-search steps and returned 27 decoded records. It performed no row sieve, root search, modular power or prime-basis reconstruction. Structural counting and square-bound comparisons remain real reader work.

## 8. Execution scope

The recorded execution is exactly one initial compile, one fresh saved-state append over a disjoint new column interval, and one fresh final reader with six queries. All nonzero-root methods, the discriminant-zero rule and the period-four rule occurred in the actual row's basis.

The value-one case, basis-prime self-hit exception, empty-prime intervals, cap stops, malformed-input refusals, outside-interval and out-of-range returns, page exhaustion, the `localRule` accessor, and further append requests were source-inspected where not exercised here. No synthetic suite or prior source example was run.

The implementation file is the exact source used for all three recorded contexts. No post-consumer source change is incorporated into these execution claims. The complete finite evidence and reusable interface do not settle the infinite-row prime question.
