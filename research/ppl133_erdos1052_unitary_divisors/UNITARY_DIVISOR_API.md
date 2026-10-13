# Exact unitary-divisor navigation from retained prime powers

This module constructs and reopens a bounded index for the unitary divisors of an identified positive integer. It provides exact counts and sums in inclusive intervals, zero-based numerical rank and selection, divisor/complement witnesses, and consecutive pages. Two sorted half-subset tables support these operations without storing the full family of cross products.

The completed consumer is the factorization of **89!** obtained from an accepted prime list. Its 24 prime-power blocks give **16,777,216 unitary divisors**, of which **16,777,215 are proper**. The two stored halves have 4,096 rows each. A fresh reader found **5,472,372 proper unitary divisors in [10^30,10^60]**, retained their exact sum through row-cutoff certificates, and navigated a selected divisor, its complement and two consecutive pages.

These are finite arithmetic and navigation results. The original question asks whether there are only finitely many unitary perfect numbers. The index does not answer that question or search for an extension of the known list.

## 1. Sources, conventions and input custody

Subbarao and Warren, [*Unitary Perfect Numbers*, Canadian Mathematical Bulletin 9(2) (1966), 147–153](https://doi.org/10.4153/CMB-1966-018-4), define a unitary divisor d of a positive integer N by

\[
d\mid N,\qquad \gcd(d,N/d)=1.
\]

For the prime factorization \(N=\prod_{i=0}^{k-1}p_i^{a_i}\), their introduction gives

\[
\sigma^*(N)=\prod_{i=0}^{k-1}(1+p_i^{a_i}).
\]

The number is unitary perfect exactly when \(\sigma^*(N)=2N\). The all-divisor family includes 1 and N; the proper family excludes N. This agrees with the [FormalConjectures statement of Erdős 1052](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/1052.lean), which sums positive unitary divisors in the half-open integer range [1,N). The inspected formal file has Git blob `708d86e978936cf3253062c53fef885be8cdfe13`. Its global finiteness declaration is tagged research open; that tag is source-limited metadata. Separate example and parity declarations, external proof links and local proof placeholders were not treated as a proof of global finiteness.

The 1966 paper proves finiteness under a fixed 2-adic exponent and, separately, a fixed number of distinct prime factors. Neither statement establishes global finiteness. Its historical list is not used as a current completeness claim. No known unitary-perfect-number example or linked Lean proof was executed or replayed.

### Accepted prime premise

The new factorial input consumes this already retained Commons source:

| Field | Identity |
| --- | --- |
| Prior carrier | Commons #31426 |
| Repository | `woahwhattheheck/commons` |
| Path | `research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json` |
| Merge | `8bcf059ef0fda877c0975f7a89a2ae565e71a3b8` |
| Git blob | `7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd` |
| Field | `.snapshot.basis.primes` |
| Accepted complete basis | 1,900 primes through the basis limit 16,384 |
| Selected input | Indices 0–23, the 24 primes through 89 |
| Next retained prime | 97 at index 24 |

The selected list is

```text
2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37,
41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89
```

The supplied `prime_basis` declares completeness through 89 and identifies this source and field. Primality and completeness are premises inherited from that identified source. The present operation performs no sieve, primality test, earlier row calculation or earlier local-rule calculation. A source identifier is provenance text, not automatic authentication of an external object.

### Factorial composition

For each supplied prime \(p\le89\), the helper computes

\[
v_p(89!)=\sum_{j\ge1}\left\lfloor\frac{89}{p^j}\right\rfloor.
\]

Every multiple of \(p^j\) contributes one additional factor p, so the sum is its exact factorial valuation when the prime list is complete. All powers, quotients and exponents from these **34 divisions** are retained. The constructor then forms the new whole prime-power blocks; no separate multiplication of 1 through 89 was performed.

| Prime | Exponent | Whole block |
| ---: | ---: | ---: |
| 2 | 85 | 38685626227668133590597632 |
| 3 | 42 | 109418989131512359209 |
| 5 | 20 | 95367431640625 |
| 7 | 13 | 96889010407 |
| 11 | 8 | 214358881 |
| 13 | 6 | 4826809 |
| 17 | 5 | 1419857 |
| 19 | 4 | 130321 |
| 23 | 3 | 12167 |
| 29 | 3 | 24389 |
| 31 | 2 | 961 |
| 37 | 2 | 1369 |
| 41 | 2 | 1681 |
| 43 | 2 | 1849 |
| 47 | 1 | 47 |
| 53 | 1 | 53 |
| 59 | 1 | 59 |
| 61 | 1 | 61 |
| 67 | 1 | 67 |
| 71 | 1 | 71 |
| 73 | 1 | 73 |
| 79 | 1 | 79 |
| 83 | 1 | 83 |
| 89 | 1 | 89 |

The resulting 137-digit N is

```text
16507955160908461081216919262453619309839666236496541854913520707833171034378509739399912570787600662729080382999756800000000000000000000
```

The factorial input is a new composition from the accepted prime premise. It is not a new primality result.

## 2. Exact subset-product model

For each distinct prime, a unitary divisor must contain either its entire power \(p_i^{a_i}\) or none of that prime. A partial exponent would leave p dividing both d and N/d. Conversely, selecting whole powers of distinct primes makes the two complementary products coprime. Unique prime factorization gives a bijection between subsets of the k blocks and unitary divisors.

Consequently,

\[
\#U(N)=2^k,\qquad
\sum_{d\in U(N)}d=\prod_i(1+p_i^{a_i}).
\]

Independent blocks must have distinct prime bases and positive exponents. Splitting one prime power into several independent blocks changes the family. The constructor rejects duplicate prime bases; callers must supply a genuine consolidated factorization.

For \(N=1\), the factor list is empty. There is one empty subset, giving the single all-family divisor 1 and \(\sigma^*(1)=1\). The full and empty selections coincide. Removing N once gives no proper unitary divisors, and 1 is not unitary perfect. This endpoint is covered by the contract and was source-inspected, not added as another executed consumer.

### Two half tables

Factors are sorted by prime. The canonical split puts the first \(\lfloor k/2\rfloor\) factors on the left and the rest on the right. Each half begins with the empty product 1. Inserting a new block w doubles the table by retaining each old product v and adjoining vw with the corresponding bit set.

Let the sorted half products be

\[
L_0<\cdots<L_{u-1},\qquad R_0<\cdots<R_{v-1}.
\]

A complete divisor has the unique form \(L_iR_j\). The index stores every half product, its local subset mask, and prefix sums

\[
P_R(c)=\sum_{j=0}^{c-1}R_j,\quad P_R(0)=0,
\]

with analogous left prefix sums. It does not store the \(uv=2^k\) complete products. Construction uses \(u+v-2\) subset-product multiplications, sorting and \(u+v\) prefix additions. For 24 factors, \(u=v=4096\), yielding 8,190 subset-product multiplications.

The construction also retains successive factor products, successive factors in the product for \(\sigma^*\), the exact floor square root and aggregate identities

\[
L_{u-1}R_{v-1}=N,\qquad P_L(u)P_R(v)=\sigma^*(N).
\]

## 3. Prefix and inclusive-interval certificates

For an integer bound x, define

\[
c_i(x)=\#\{j:L_iR_j\le x\}.
\]

Then the all-family prefix count and sum are

\[
C(x)=\sum_i c_i(x),\qquad
S(x)=\sum_i L_iP_R(c_i(x)).
\]

As i increases, \(L_i\) increases, so the cutoff \(c_i(x)\) can only decrease. One right pointer therefore traverses the sorted right table while the left table is scanned. The number of product comparisons is on the scale of \(u+v\), rather than uv. Sum queries add one weighted right-prefix sum per nonempty left row.

An optional frontier records **every** \(c_i(x)\), including zero entries after the scan ends. Its entries always describe the all-divisor grid. For a proper-family query, the full divisor N is subtracted from the count and sum exactly when \(x\ge N\); the frontier itself is not rewritten to hide that exclusion. Returned fields explicitly include the all-family count and sum and any excluded full value.

For an inclusive interval [a,b],

\[
\#(U(N)\cap[a,b])=C(b)-C(a-1),
\]
\[
\sum_{d\in U(N)\cap[a,b]}d=S(b)-S(a-1).
\]

The proper-family version applies the same difference after the explicit full-divisor exclusions. Public bounds are nonnegative. An interval starting at zero internally uses the empty prefix at -1; its receipt may therefore contain that internal negative bound even though public inputs do not accept negative integers.

## 4. Numerical rank, selection and complements

Ranks refer to ordinary increasing divisor value, starting at zero. They do not refer to subset-mask order. Since N is the last all-family divisor, every proper divisor has the same rank in both families.

The complement map \(d\mapsto N/d\) reverses this order. For \(N>1\), it has no fixed point among unitary divisors: if \(d=N/d\), then unitary coprimality gives \(\gcd(d,d)=d=1\), forcing N=1. This argument remains valid when N itself is a square. It does not rely on an assumption that N is nonsquare.

Writing the full sorted list as \(d_0,\ldots,d_{T-1}\), where \(T=2^k\), gives

\[
d_{T-1-r}=N/d_r,
\]

and exactly \(T/2\) unitary divisors lie at or below \(\lfloor\sqrt N\rfloor\).

### Selection

A lower-half selection searches the ordinary integer interval \([1,\lfloor\sqrt N\rfloor]\) for the least x satisfying \(C(x)>r\). Binary search is exact because C is nondecreasing and jumps by one at each distinct unitary divisor. Every midpoint and count is retained in the selection trace.

An upper-half selection reflects the rank, selects the lower divisor and divides N by it. The first and last divisors have direct endpoint cases. The N=1 case is handled before any nontrivial reflection. Bounded caches retain counts at visited thresholds and values at selected ranks; an already cached reflected rank avoids another bisection.

The integer square root is computed during construction using exact integer Newton iteration and checked by

\[
s^2\le N<(s+1)^2.
\]

The saved reader checks these two products but does not repeat the Newton iteration.

### Membership and rank

A rank query first checks divisibility, then computes \(\gcd(d,N/d)\). It returns one of:

- `not_divisor`, with the remainder;
- `not_unitary`, with quotient and nontrivial gcd;
- `not_proper`, when d=N and the proper family was requested;
- `found`, with rank \(C(d-1)\), quotient, subset and complement masks, selected factor indices and corresponding half-row products.

For a found value, the implementation reconstructs its whole-block mask and checks the corresponding retained pair product. These targeted checks do not establish every saved mask-to-product identity independently.

### Consecutive pages

A page selects its starting value and seeds a min-heap with the first eligible product in each left row. Each row is the increasing stream

\[
L_iR_0,L_iR_1,\ldots,L_iR_{v-1}.
\]

The heap repeatedly returns its smallest product and advances only that row. Unique subset products make these the successive numerical divisors. Every returned record contains the rank, value, quotient, masks and row witnesses.

When another divisor remains, the heap minimum is cached under the next page's start rank. A following page can reuse that selected value. **The heap itself is rebuilt for each page**; the API does not serialize or preserve a live heap between page calls.

Memory for the two half tables is \(O(2^{\lceil k/2\rceil})\). A lower-half selection uses \(O(\log N)\) threshold queries, each with \(O(u+v)\) comparison-scale work. Page seeding scans the two tables and inserts at most u streams; subsequent outputs cost logarithmic heap work per divisor. These statements count arithmetic operations and comparisons, not constant-time bit operations on unbounded integers. The explicit digit caps bound the supported arithmetic.

## 5. Public API

The file is dependency-free CommonJS and has no I/O. Its four exports are:

| Export | Purpose |
| --- | --- |
| `factorialPrimePowerInput(options)` | Compose an identified factorial's prime-power input and complete valuation records. |
| `createUnitaryDivisorIndex(options)` | Construct both half tables from distinct identified prime powers. |
| `openRetainedUnitaryDivisorIndex(snapshot)` | Restore a saved index with the checks listed below. |
| `UNITARY_DIVISOR_LIMITS` | The fixed supported bounds. |

### Direct saved-data use in connected JavaScript

The host supplies the already fetched complete module text as `sourceText` and JSON text as `dataText`. No filesystem, package installation or native process is required.

```javascript
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);

const saved = JSON.parse(dataText);
const index = loaded.exports.openRetainedUnitaryDivisorIndex(saved.snapshot);

const result = index.interval(
  "1000000000000000000000000000000",
  "1000000000000000000000000000000000000000000000000000000000000",
  { kind: "proper", include_frontiers: true }
);
// result.count === "5472372"
// result.sum is the exact inclusive-interval sum recorded below.
```

This is a usage example of the retained consumer, not an additional execution in the publication record. New readers should open `saved.snapshot`; they do not need to reconstruct the factorial or half tables.

For a different, separately identified input:

```javascript
const prepared = loaded.exports.factorialPrimePowerInput({
  n: newFactorialBound,
  source_id: newInputSourceId,
  prime_basis: identifiedPrimeBasis
});
const fresh = loaded.exports.createUnitaryDivisorIndex(prepared);
```

The placeholder values must satisfy the contract. Alternatively, supply constructor options `{source_id, prime_basis, factors}` directly, with factors of shape `{prime, exponent}`. The factorial helper's output already has those fields.

### Index methods

`kind` is `"proper"` by default; `"all"` is the only other accepted value.

| Method | Result and boundary |
| --- | --- |
| `summary()` | Copy of scalar totals, factor rows, half sizes, finite perfectness classification and rank convention. |
| `count({kind})` | Exact family size as a decimal string. |
| `prefix(bound,{kind,include_frontier})` | Count and sum through the inclusive bound, with optional complete row cutoffs. |
| `interval(lo,hi,{kind,include_frontiers})` | Inclusive count and sum plus lower/upper prefix receipts; requires lo≤hi. |
| `rank(value,{kind})` | Membership status and, when admitted, its zero-based numerical rank and witnesses. |
| `select(rank,{kind})` | One divisor with quotient, masks, row identities and selection trace. |
| `page(startRank,{kind,limit})` | Consecutive records and `next_rank` or null. Start equal to count returns an empty terminal page; greater starts fail. |
| `snapshot()` | Complete JSON-safe mathematical tables and arithmetic records. |
| `work()` | Current operation counters and cache sizes. |

The frontier flags default to false and must be Boolean. Page size defaults to 128. The mathematical state is fixed after construction or restoration; caches and work counters change with queries. Returned data are copies. Invalid inputs throw a synchronous `RangeError`; an unsuccessful query may have advanced diagnostic counters before the error, without changing the mathematical state.

### Integer and provenance contracts

New mathematical inputs accept a safe integer Number, a BigInt, or a canonical unsigned decimal string. Decimal strings have no sign, redundant leading zeros, exponent notation or fractional part. Positive values are required for prime bases, divisors and exponents where applicable. Exponents themselves are Number safe integers in the listed range. Public interval and prefix bounds may be zero.

Saved mathematical integers use canonical decimal strings; the signed excess has a separate signed-decimal field. Subset masks use canonical lowercase hexadecimal without a `0x` prefix. Indices, finite array lengths, exponent values, page limits and diagnostic counters use Numbers. A source ID is a nonempty string with the listed length cap.

A prime basis has shape

```javascript
{
  source_id: "identified source and field",
  complete_through: "89",
  primes: ["2", "3", /* identified remaining primes */ "89"]
}
```

This illustrates the shape only; omitting actual primes would violate the intended completeness premise. The implementation requires a strictly increasing list within the declared bound, factor-prime membership in that list and distinct factor bases. These structural conditions do not prove that the entries are primes or that the list is complete.

The factorial helper requires declared coverage through its requested bound and uses the supplied primes at most that bound. The constructor sorts factors by prime, so masks and `selected_factor_indices` always refer to that canonical order.

| Limit | Value |
| --- | ---: |
| Prime-power factors | 28 |
| Rows per half | 16,384 |
| Positive exponent | 4,096 |
| Factorial helper bound | 4,096 |
| Rows in the supplied prime basis | 4,096 |
| N, factor powers and public integer value digits | 256 |
| Saved sums and bounded arithmetic-result digits | 272 |
| Divisors per page | 128 |
| Source ID characters | 2,048 |
| Selected-rank cache entries | 128 |
| Threshold-count cache entries | 512 |

The factorial bound is an individual input cap, not a promise that every factorial through 4,096 fits the factor-count and digit caps. All applicable limits must hold. Caches are bounded by insertion order with replacement; they are not described as least-recently-used caches.

## 6. What the saved reader checks

The saved reader is designed to consume established arithmetic while exposing exactly what it validates. It checks:

- Schema, canonical bounded values, source-ID shape, sorted distinct factor bases and membership in the supplied basis.
- The canonical split, half lengths, complete unique local-mask coverage and strict row-product order.
- The empty/full mask endpoints and all prefix-sum equalities, not just total sums.
- Counts \(2^k\) and \(2^k-1\), proper-sum subtraction and the perfectness/excess fields.
- Increasing saved factor-product and sigma-product prefixes with the stated initial and final values.
- Both exact square-root inequalities and their recorded products.
- The two aggregate products \(L_{\max}R_{\max}=N\) and \(P_L(u)P_R(v)=\sigma^*(N)\).

It **does not** regenerate individual prime powers, every mask-to-product identity, successive multiplicative prefix identities, factorial valuations or either subset-product table. It does not authenticate an external source ID or establish basis primality/completeness. Those remain identified input premises; a malformed table can satisfy some structural identities, so successful restoration is not an independent proof of its entire provenance.

For this actual saved input, opening checked 8,192 half rows, 8,192 mask entries and **8,192 prefix-sum equalities**, plus two square-root products and two aggregate products. It used zero prime-power, factor-product, sigma-product or subset-product construction operations, zero sort comparisons and zero Newton iterations. It was not a zero-arithmetic load.

The complete published snapshot retains the constructor's rows and arithmetic, so a consumer can reuse them with this boundary explicit.

## 7. Actual finite results

The single factorial preparation and constructor ran on October 4, 2026, starting at 19:56:18.748 UTC. The fresh saved reader ran at 19:57:28.737 UTC. The executed source was unchanged across both contexts.

### Scalar results

| Quantity | Value |
| --- | ---: |
| Distinct prime-power blocks | 24 |
| Half rows | 4,096 + 4,096 |
| All unitary divisors | 16,777,216 |
| Proper unitary divisors | 16,777,215 |
| All unitary divisors through floor√N | 8,388,608 |
| Proper divisors in [10^30,10^60] | 5,472,372 |
| Finite unitary-perfect classification | false; the unitary sum is below 2N |

Exact floor square root:

```text
128483287477042947436606854413089420338280480054241478815100633956558
```

Exact \(\sigma^*(N)\):

```text
19256106605113740790495052819822491330635219614463622248429407133487537287541234748328541432563527343191546902853949973818507264000000000
```

Exact sum of proper unitary divisors, \(\sigma^*(N)-N\):

```text
2748151444205279709278133557368872020795553377967080393515886425654366253162725008928628861775926680462466519854193173818507264000000000
```

Exact excess \(\sigma^*(N)-2N\):

```text
-13759803716703181371938785705084747289044112858529461461397634282178804781215784730471283709011673982266613863145563626181492736000000000
```

Thus the new finite input is unitary deficient. This classification is not a statement about finiteness of the perfect numbers.

### Prefix and interval receipts

The sum of the 8,388,608 unitary divisors at or below floor√N is

```text
17140347372833574140030669685401004029498067450830373998519351292164219131
```

The inclusive [10^30,10^60] proper-family sum is

```text
125096473838759904348068399635264963909595967607889450685508347008
```

Its lower prefix at \(10^{30}-1\) has count 473,255 and sum

```text
28604739858123535175188037706552923
```

Its upper prefix at \(10^{60}\) has count 5,945,627 and sum

```text
125096473838759904348068399635293568649454091143064638723214899931
```

All three complete 4,096-entry row-cutoff vectors are saved. These records express the exact threshold partitions without listing every complete divisor in the interval.

### Selected ranks, pages and membership distinctions

At proper-family rank **4,194,304**, the selected value D is

```text
351770075062745950390997393945891004366379731996639232
```

Its complement \(Q=N/D\) is

```text
46928253228941953724112445227835248330483661825591971974194272473640346527099609375
```

The D subset mask is `36ce21` and its complement is `c931de`. Its selected factor indices are [0,5,9,10,11,14,15,17,18,20,21]. Its half-row witnesses are left row 1,116 with product

```text
5991431174191720340496422160952639501631488
```

and right row 1,460 with product 58,712,194,939. All **226** lower-half bisection records are retained. The last two threshold records distinguish D−1, with count 4,194,304, from D, with count 4,194,305.

Two pages contain every rank from **4,194,304 through 4,194,335**, with all 32 values, quotients, masks and half-row witnesses. The second page starts from the value cached at the end of the first page; it rebuilds its heap. The final saved page value is

```text
351841598054836212730384375903823845462512969970703125
```

The selection at rank **12,582,911** uses complement reflection to the already cached rank 4,194,304 and returns Q with no further bisection.

The additional rank calls retain distinct membership outcomes:

| Input | Proper-family result |
| --- | --- |
| D above | Found at rank 4,194,304, gcd 1. |
| 2 | Not unitary: it divides N, but gcd(2,N/2)=2. |
| Entire block \(2^{85}\) | Found at rank 232,241, mask 1, gcd 1. |
| N | Not proper: the all-family full divisor is excluded. |

The divisor 2 and the whole block \(2^{85}\) demonstrate the actual whole-prime-power boundary on this input. No separate small example or known perfect number was computed.

### Operation accounting

The factorial helper made 34 valuation divisions. The constructor recorded:

| Work | Count |
| --- | ---: |
| Prime-power multiplications | 69 |
| Factor-product multiplications | 24 |
| Sigma-product multiplications | 24 |
| Half-subset product multiplications | 8,190 |
| Half-sort comparisons | 87,219 |
| Half-prefix additions | 8,192 |
| Newton square-root iterations | 8 |
| Square-root bound products | 2 |
| Aggregate products | 2 |
| Complete divisor families enumerated | 0 |

The fresh reader made exactly 12 public calls: two counts, one prefix, one interval, two selections, two pages and four rank queries. After restoration, its query counters include:

| Work | Count |
| --- | ---: |
| Threshold scans | 230 |
| Left rows visited by those scans | 457,411 |
| Threshold product comparisons | 1,399,261 |
| Threshold weighted-sum products | 5,769 |
| Bisection steps | 226 |
| Threshold-cache hits | 1 |
| Selection-cache hits | 3 |
| Heap-seed comparisons | 11,956 |
| Heap-seed products | 7,394 |
| Heap comparisons | 12,061 |
| Heap pushes | 7,426 |
| Heap pops | 32 |
| Heap-advance products | 32 |

Membership operations and the complete before/after counters are also retained. `returned_divisors=34` counts two select outputs and 32 page outputs; it is not a count of unique values or of every kind of returned witness. Rank receipts are separate.

The reader made zero new prime powers, half-subset products, factor/sigma constructions, sorts, sieves or primality tests. It did not enumerate all 16,777,216 cross products. Recorded elapsed times were 0 ms for preparation at the timer's resolution, 47 ms for construction, 75 ms for opening and 187 ms for the 12 calls. These are single observations, not statistical benchmarks or general performance guarantees.

## 8. Retained artifact and execution boundary

| File | Role |
| --- | --- |
| `unitary_divisor_index.cjs` | Public constructor, factorial composer and saved reader. |
| `UNITARY_DIVISOR_API.md` | This derivation, contract, source scope and actual results. |
| `factorial89_unitary_divisor_index.json` | Complete input, factorization, half tables, prefix sums, arithmetic, query records and work accounting. |
| `README.md` | Entry point and saved-data usage. |

The executed module has Git blob **64494e6fb71b877d50ef63d2c14abc8412e20f57** and 27,928 UTF-8 bytes. The complete JSON has Git blob **3cad8b2aaa202bf868dc490692410092989871ec** and 953,407 UTF-8 bytes. The JSON is one complete file; no half table, cutoff vector, bisection trace or page record was omitted.

Top-level JSON fields are:

```text
schema
source_identity
source_provenance
factorial_request
factorial_input
constructor_execution
snapshot
retained_consumer
execution_boundary
```

The directly loadable object is `snapshot`. Each half stores `factor_start`, `factor_count`, every `[product_decimal, local_mask_hex]` row, and the prefix-sum array including its leading zero. `retained_consumer.queries` stores every actual request and result in order. The work objects distinguish initial construction, saved opening and subsequent queries.

One input composition, one constructor and one fresh saved open were executed. Other factor sets, N=1, maximum caps, alternate source bases and the remaining rejection branches were inspected in source only. The source remained unchanged throughout the actual runs. This artifact supplies a reusable finite index and its exact consumer data; it makes no global finiteness, known-number-list extension, novelty or external-frontier claim.
