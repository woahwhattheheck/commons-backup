# Primitive weird numbers: a bounded prime-template index

This package constructs and retains finite certificates for ordinary primitive weird numbers of the form
\[
N=2^k p q.
\]
The public constructor covers one explicitly defined \(q\) for each prime \(p\) in a finite interval. The saved reader provides numerical catalog navigation, complete prime-trial pages, and ordinary proper-divisor count/rank/select/page operations.

The actual input is **\(k=12\)**. It consumes the accepted #31426 prime basis and obtains **95 certified primitive weird numbers from 872 candidates**. The other **777 candidates have composite \(q\)** and are recorded as failures of this particular prime template. All 7,779 trial quotient/remainder pairs, 285 maximal-proper-divisor deficiency records and 380 dyadic divisor blocks are retained. No proper-divisor subset search is used.

The least and greatest certified values within this template are
\[
1\,099\,642\,138\,624
\quad\text{and}\quad
56\,825\,344\,790\,528.
\]
These are extrema of the saved finite catalog. The package neither enumerates every primitive weird number in that numerical interval nor addresses odd weirdness or primitive infinitude.

## Files

| File | Role |
|---|---|
| `primitive_weird_index.cjs` | Pure CommonJS implementation and saved reader; no I/O |
| `k12_prime_template_catalog.json` | Complete source-prime premise, every candidate and arithmetic record, and the actual reader receipt |
| `PRIMITIVE_WEIRD_API.md` | Mathematical argument, attribution, contracts, limits and results |
| `README.md` | Entry point and result/provenance summary |

The executed module has Git blob **37323b6c85f404799af7fc30a1e02816bf96ca58**. It was unchanged between the sole constructor run and the fresh saved-reader run. The complete data file has Git blob **24c572744b09f774c544ff63de3b740ba8cff046**.

## 1. Sources and conventions

This construction uses ordinary positive divisors. A proper divisor satisfies \(d\mid N\) and \(d<N\); each divisor may occur at most once in a subset sum. Semiperfectness means that such a subset sums to \(N\), including the perfect case. Weirdness requires \(\sigma(N)>2N\) and failure of that subset condition. Primitive weirdness means that no proper divisor is weird. Intermediate powers of a prime remain ordinary divisors.

For distinct odd primes \(p<q\), put \(S=2^{k+1}-1\) and \(\Delta=\sigma(2^kpq)-2^{k+1}pq\). The sufficient condition \(S<\Delta<p\) is the \(m=2^k\), two-prime, \(j=0\) specialization of **Amato–Hasler–Melfi–Parton, Theorem 3.1.1**, *Primitive weird numbers having more than three distinct prime factors*, Riv. Mat. Univ. Parma 7(1) (2016), 153–163. Since \(p,S\) are odd, \(p>S\) implies \(p>S+1\), meeting the theorem's strict prime threshold. This is an application of established sufficient conditions. [Author text](https://arxiv.org/html/1803.00324v1); [publication metadata](https://arxiv.org/abs/1803.00324).

**Benkoski–Erdős**, *On Weird and Pseudoperfect Numbers*, Mathematics of Computation 28(126) (1974), 617–623, supplies the historical distinct-proper-divisor convention. Its nonstrict abundance terminology includes perfect numbers, which already satisfy the subset condition; hence weirdness still forces strict abundance. Its positive-density theorem concerns weird numbers, not primitive weird numbers. [Original paper](https://www.renyi.hu/~p_erdos/1974-24.pdf).

The [retained FormalConjectures statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/470.lean), blob `84441b0b2306771334379ee8244cd4c7e4adbfe6`, defines primitive weirdness by exclusion of every proper weird divisor. It labels the odd-existence and primitive-infinitude questions open; these are source annotations, not an exhaustive current-literature assessment. Its local smallest-example proof and linked proofs were not replayed. The present constructor yields only even numbers and proves no infinite statement.

## 2. The finite certificate

Let \(k\ge1\), let \(p<q\) be distinct odd primes, and write
\[
M=2^k,\qquad S=2^{k+1}-1=2M-1,\qquad N=Mpq.
\]
Ordinary divisor multiplicativity gives
\[
\sigma(N)=S(p+1)(q+1),\qquad
a=\sigma(N)-2N=S(p+q+1)-pq.
\]
Assume
\[
S<a<p<q. \tag{1}
\]

The following direct calculation explains the stored certificate. It is a specialized finite argument for the established sufficient criterion.

### 2.1 Why no proper-divisor subset sums to \(N\)

Let \(D\) be the set of all positive proper divisors of \(N\). Its sum is
\[
\sum_{d\in D}d=\sigma(N)-N=N+a.
\]
A subset \(E\subseteq D\) sums to \(N\) if and only if its complement \(D\setminus E\) sums to \(a\). This is a complement within the fixed proper-divisor set; divisors are not repeated.

Any proper divisor containing the factor \(p\) or \(q\) is at least \(p>a\). Thus a subset summing to \(a\) could use only
\[
1,2,2^2,\ldots,2^k.
\]
Their total is \(S<a\). Even using all of them cannot reach \(a\). Therefore no proper-divisor subset sums to \(N\). Also \(a>0\), so \(N\) is abundant. It is weird.

The record retains the target \(a\), eligible-divisor total \(S\), next possible divisor \(p\), and both positive gaps \(a-S\) and \(p-a\). It does not enumerate any of the \(2^{4k+3}\) subsets.

### 2.2 Why every proper divisor is deficient

It suffices to consider the three maximal proper divisors \(N/2,N/p,N/q\). Their deficiencies are
\[
\begin{aligned}
2(N/p)-\sigma(N/p)&=q-S,\\
2(N/q)-\sigma(N/q)&=p-S,\\
2(N/2)-\sigma(N/2)&=M(p+q+1)-a.
\end{aligned}
\]
The first two are positive by (1). The last is positive since \(M\ge2\), \(a<p\), and \(p+q+1>p\).

Every proper divisor \(d\mid N\) divides at least one of these three numbers: at least one of its prime exponents is below the corresponding exponent of \(N\). For positive integers, the ordinary abundancy ratio is nondecreasing under divisibility. Indeed, each prime-power factor contributes
\[
1+\frac1\ell+\cdots+\frac1{\ell^e},
\]
which increases as its exponent increases, while adding another prime factor also increases the product. Thus \(d\mid D\) and \(\sigma(D)/D<2\) imply \(\sigma(d)/d<2\).

Every proper divisor of \(N\) is therefore deficient, and none is weird. Together with the first part, this proves primitive weirdness. The snapshot stores the value, ordinary divisor sum and positive deficiency of all three maximal proper divisors.

## 3. One candidate \(q\) per source prime

For each prime
\[
S<p<2S,
\]
define
\[
d=p-S,\qquad
u=\left\lfloor\frac{S^2}{d}\right\rfloor,\qquad
r=S^2\bmod d,
\]
and set
\[
q=S+u,\qquad a=S+r. \tag{2}
\]
The identity
\[
S(p+q+1)-pq=S+S^2-du=S+r
\]
shows that this \(a\) is the abundance expression whenever \(q\) is prime.

Both \(S\) and \(p\) are odd, so \(d\) is positive and even. Because \(S^2\) is odd, its remainder modulo \(d\) cannot be zero. Hence
\[
0<r<d,\qquad S<a<S+d=p.
\]
Also \(d\le S-1\), and
\[
\left\lfloor\frac{S^2}{d}\right\rfloor\ge S+1.
\]
Consequently \(q\ge2S+1>p\). Whenever \(q\) is prime, it is an odd prime distinct from \(p\), and (1) applies.

If \(q\) is composite, the factorization \(N=2^kpq\) no longer has the required two distinct odd prime factors. The ordinary divisor sum cannot be inferred from \(S(p+1)(q+1)\). The API therefore reports `composite_q_template_not_certified` and stores no weirdness certificate. It makes no assertion that this candidate \(N\) is non-weird.

The constructor includes every source prime in the stated open \(p\)-interval, exactly once. This yields complete coverage of **this one-\(q\)-per-\(p\) template**, conditional on the identified prime-list premise. It omits other \(q\) values, other \(k\) values and unrelated factorizations.

For two successful rows, equality of \(N\) would force equality of the two unordered odd prime factors. Since every row uses \(p<q\), it would force equality of \(p\) and then \(q\). Thus successful \(N\) values are distinct. The saved catalog sorts them numerically.

### 3.1 Bounded arithmetic and prime basis

Since \(d\ge2\),
\[
q\le S+\left\lfloor S^2/2\right\rfloor=2^{2k+1}-1.
\]
For \(k\le12\), this bound is \(33\,554\,431\). Values \(S,p,q,d,u,r\), prime squares and trial quotients are exactly representable as ordinary JavaScript integers. The constructor uses exact small-integer quotient/remainder arithmetic for these bounded operations. It uses BigInt for \(N,\sigma(N)\), deficiencies, divisor values and arbitrary supported query endpoints.

The input prime list must contain **exactly every prime through its stated limit**, and the limit must be at least \(2S\). The module checks list shape, increasing order, parity after 2, bounds and source identification. It does not re-establish primality or completeness of that source.

No prime-gap theorem is needed to ensure a stopping prime for a candidate. For \(S\ge3\), the upper bound for \(q\) is below \(S^2\). The source already contains this candidate's prime \(p>S\), so the ascending scan encounters a prime whose square exceeds \(q\), at the latest \(p\), unless a divisor was found earlier.

A prime \(q\) record contains a nonzero remainder for every source prime up to its last tested prime and the next source prime whose square exceeds \(q\). A composite record stops at the first zero remainder, providing its **least prime divisor** and complementary factor. Both quotients and remainders are retained for every tested prime:
\[
q=\ell\,Q_\ell+R_\ell,\qquad 0\le R_\ell<\ell.
\]
The saved reader copies these records; it does not repeat the divisions.

## 4. Actual source input and result

The accepted input is the prime array at `snapshot.basis.primes` in:

- Repository: `woahwhattheheck/commons`.
- Path: `research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json`.
- Accepted contribution: Commons #31426.
- Pinned merge: `8bcf059ef0fda877c0975f7a89a2ae565e71a3b8`.
- Data blob: `7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd`.
- Basis limit: 16,384; retained primes: 1,900.

The full prime array is copied into this snapshot as the identified premise. The earlier least-factor sieve and interspersion-row calculations were not run again. Neither were the primes \(p\) tested again.

For \(k=12\), \(S=8191\), and the source interval is \(8191<p<16382\).

| Quantity | Actual value |
|---|---:|
| Source primes in the \(p\)-interval | 872 |
| Prime \(q\) / certified primitive-weird rows | 95 |
| Composite \(q\) / template failures | 777 |
| Complete trial quotient/remainder pairs | 7,779 |
| Prime-square stopping comparisons | 7,874 |
| Maximal-divisor deficiency witnesses | 285 |
| Dyadic proper-divisor blocks | 380 |
| Proper divisors per successful \(N\) | 51 |
| Subset-sum searches | 0 |

The constructor took 7 ms in this one connected V8 observation. This is a receipt for the actual operation, not a statistical performance benchmark.

### 4.1 Endpoint records

| Field | Least certified \(N\) | Greatest certified \(N\) |
|---|---:|---:|
| Numeric catalog rank | 0 | 94 |
| \(p\) | 16,073 | 8,231 |
| \(q\) | 16,703 | 1,685,503 |
| \(N\) | 1,099,642,138,624 | 56,825,344,790,528 |
| \(\sigma(N)\) | 2,199,284,286,336 | 113,650,689,589,248 |
| \(a\) | 9,088 | 8,192 |
| \(a-S\) | 897 | 1 |
| \(p-a\) | 6,985 | 39 |
| Deficiency of \(N/2\) | 134,245,504 | 6,937,530,368 |
| Deficiency of \(N/p\) | 8,512 | 1,677,312 |
| Deficiency of \(N/q\) | 7,882 | 40 |

For the greatest record, all 211 prime trials through 1297 have nonzero remainders, and the next source prime is 1301 with
\[
1301^2=1\,692\,601>1\,685\,503.
\]
All 211 quotient/remainder pairs are retained and exported through four saved-reader pages.

The first \(p\)-candidate is 8209. It produces
\[
q=3\,735\,551=41\cdot91\,111.
\]
The record includes the preceding nonzero remainders and the first zero remainder at 41. It reports a template failure, not a non-weirdness conclusion for the proposed product.

## 5. Public API and input contracts

Exports:

```js
compilePrimitiveWeirdIndex(input)
openRetainedPrimitiveWeirdIndex(snapshot)
PRIMITIVE_WEIRD_LIMITS
```

The module has no filesystem, network, package or process dependency. It can be evaluated in connected V8 from its complete text:

```js
const moduleRecord = { exports: {} };
new Function("module", "exports", moduleText)(
  moduleRecord, moduleRecord.exports
);

const delivery = JSON.parse(dataText);
const index = moduleRecord.exports.openRetainedPrimitiveWeirdIndex(
  delivery.snapshot
);

// Actual saved-query examples:
index.count("1000000000000", "10000000000000"); // count 89
index.rank("10000000000000");                  // absent; insertion rank 89
index.select(47);                             // N = 1224784580608
index.primeTrialPage(8231, 192, 64);           // 19 rows; next null
```

The constructor input is:

```js
{
  k: 12,
  basis: {
    limit: 16384,
    primes: identifiedCompletePrimeList,
    source_id: "a nonempty identifier for that complete prime source"
  }
}
```

The constructor returns an interface containing its complete snapshot. Loading an existing delivery requires only `delivery.snapshot`; do not invoke the constructor to navigate saved data.

### 5.1 Catalog methods

All catalog ranks are **zero based**. Candidate order is increasing \(p\); successful catalog order is increasing \(N\). Methods return copied records and do not expose mutable internal arrays.

| Method | Contract |
|---|---|
| `summary()` | Counts, interval, extrema, source identifier and finite scope |
| `candidate(p)` | Exact retained row for a safe-integer \(p\); otherwise `not_a_retained_candidate` |
| `candidatePage(start=0, limit=64)` | Consecutive candidate rows in increasing \(p\) |
| `primeTrialPage(p, start=0, limit=64)` | Saved prime, quotient and remainder rows for that candidate; no divisions |
| `count(lower=0n, upper=null)` | Certified \(N\) values in the inclusive interval; null upper endpoint means no upper restriction |
| `rank(N)` | Membership, exact rank if present, and insertion rank in either case |
| `select(rank)` | One successful candidate by increasing-\(N\) rank |
| `page(start=0, limit=64)` | Successful records with explicit ranks and next cursor |
| `snapshot()` | A deep copy of the complete saved catalog |
| `work()` | A copied operation-counter record |

A catalog `count` response supplies `first_rank` and `end_rank_exclusive`. The difference is its count. Rank of an absent value is null, while its insertion rank still indicates where it would occur.

Page starts may equal the family size, yielding an empty terminal page. Selection ranks must be strictly below the size. Limits must be positive and at most 256. Every page's `next` is either the next integer start or null. Ranks and numerical endpoints accept nonnegative safe integers, BigInt values or canonical nonnegative decimal strings; unsafe Number values, signs, leading zeroes and fractional values are rejected. The parameter \(k\), candidate \(p\), list entries and page limit require safe Number integers.

Composite candidate rows are included in `candidate` and `candidatePage`, but omitted from the successful \(N\)-catalog and ordinary-divisor methods. A divisor query must name an \(N\) with a successful record.

### 5.2 Ordinary proper-divisor methods

| Method | Contract |
|---|---|
| `properDivisorCount(N, lower=1n, upper=null)` | Proper divisors in an inclusive interval; null upper endpoint uses \(N-1\) |
| `rankProperDivisor(N, value)` | Membership, rank if present and insertion rank |
| `selectProperDivisor(N, rank)` | Divisor value plus its dyadic block and exponent |
| `pageProperDivisors(N, start=0, limit=64)` | Increasing proper-divisor page with rank, odd part, exponent and next cursor |

For these methods, all counted objects are ordinary proper divisors. The divisor 1 is present; \(N\) is excluded. The value 0 is not a divisor. An upper bound at or beyond \(N\) still counts only the proper family. No unitary restriction is imposed. A non-divisor returns `found:false` and an insertion rank.

All returned integer magnitudes \(N\), divisor values and odd parts use decimal strings. Bounded ranks, counts and exponents use Numbers.

## 6. Divisor navigation without subset enumeration

For a certified \(N=2^kpq\), the complete proper-divisor set is the disjoint union of four streams:
\[
\begin{array}{ll}
2^j,&0\le j\le k,\\
p\,2^j,&0\le j\le k,\\
q\,2^j,&0\le j\le k,\\
pq\,2^j,&0\le j<k.
\end{array}
\]
Their odd parts are distinct, and the last stream excludes \(N\). They contain \(4k+3\) divisors in total.

For a stream with odd part \(b\) and exponents \(0,\ldots,e\), its count at or below \(X\) is zero when \(X<b\). Otherwise it is
\[
\min\!\left(e+1,\;1+\left\lfloor\log_2\left\lfloor X/b\right\rfloor\right\rfloor\right).
\]
The implementation obtains the logarithm through the exact binary-string length of the BigInt quotient, not a floating logarithm. Summing the four counts gives a monotone cumulative count.

Divisor rank is the cumulative count strictly below the value, coupled with the ordinary divisibility and properness check. Selection binary searches the integer interval \([1,N-1]\) for the first value whose cumulative count exceeds the requested rank. A page uses that first value to initialize the four stream frontiers and then repeatedly emits the smallest frontier. Every emitted divisor has a unique odd part/exponent representation.

These methods manipulate four stored blocks. They do not enumerate possible divisor subsets or recalculate \(q\)'s primality. Only a requested divisor page materializes its own output divisors.

## 7. Actual fresh saved-reader consumer

The module was evaluated in a fresh connected V8 context, the saved snapshot was opened once, and 15 public query calls were made. This did not invoke the constructor.

| Query | Actual result |
|---|---|
| Catalog \([10^{12},10^{13}]\) | 89 values, ranks 0 through 88 |
| Rank of \(10^{13}\) | Absent, insertion rank 89 |
| Select catalog rank 47 | \(p=12409,\ q=24097,\ N=1224784580608,\ a=9164\) |
| Catalog page from 0, limit 8 | Ranks 0–7; next 8 |
| Catalog page from 87, limit 8 | Ranks 87–94; terminal |
| Candidate \(p=8209\) | Composite \(q\), least divisor 41, cofactor 91111 |
| Proper-divisor count for the greatest \(N\), interval \([10^4,10^7]\) | 13, ranks 14–26 |
| Rank of \(10^6\) as its proper divisor | Absent, insertion rank 20 |
| Select its proper-divisor rank 25 | \(6\,742\,012=4\cdot1\,685\,503\) |
| Its complete proper-divisor page | 51 rows, from 1 to \(N/2=28\,412\,672\,395\,264\), terminal |
| Four prime-trial pages for \(p=8231\) | 64 + 64 + 64 + 19 = 211 rows, terminal |

The remaining query is the summary call. All requests and complete responses are retained under `retained_consumer.responses`.

The saved loader indexed all 872 candidate rows, 95 certificates, 285 maximal-divisor rows, 380 blocks and 7,779 trial records. It performed **zero parameter constructions, \(q\) classifications, trial divisions, prime-square classification comparisons, new certificates, sieves or subset searches**.

The queries themselves performed 272 block-bound divisions, 92 divisor-selection bisection steps, one divisor-membership remainder, four block identifications and 83 frontier-minimum comparisons. They copied 211 saved prime-trial rows and returned 52 divisor rows: the separate selected divisor plus the complete 51-row page. These query arithmetic operations are distinct from construction or primality work. The work record is a selected operation accounting, not a count of every JavaScript instruction.

Opening took 15 ms and the queries took 1 ms in this observation. No statistical benchmark or cross-runtime speed claim follows from those times.

## 8. Snapshot contract and provenance limits

The snapshot schema is `commons.primitive_weird_prime_template.v1`. It retains:

- \(k,S\), the open \(p\)-interval and the global \(q\)-bound.
- The complete identified source prime list and its stated limit.
- Every candidate in increasing \(p\), including its source-list index, Euclidean quotient/remainder for (2), \(q\), abundance expression and proposed \(N\).
- Every trial quotient/remainder pair and its stopping-prime information.
- The exact status of each candidate, with null certificate for a composite \(q\).
- Every successful ordinary divisor sum, obstruction gap, three maximal-proper-divisor witnesses and four dyadic blocks.
- All successful candidate indices sorted by numeric \(N\), counts and construction work.

The full delivery additionally records source repository/path/ref/blob identities, the executed source identity, the input composition, the one constructor observation, all saved-reader requests/responses and the exercised-versus-inspected boundary.

### 8.1 What the loader checks

The saved loader checks bounded types and decimal forms; \(k,S\) and interval envelope; source list order and bounds; exact row coverage relative to that list; candidate/source index bindings; trial-prefix lengths and nonzero/terminal-zero patterns; stopping-prime list bindings; record status shape; positive stored certificate quantities; fixed block counts/exponent ranges; three maximal-divisor record slots; unique certified \(N\) values; sorted complete success indices; and saved count consistency.

These are structural and binding checks. The loader does **not** authenticate a Git blob or prove source-list completeness. It does **not** repeat the identities \(q=\ell Q_\ell+R_\ell\), recompute the candidate parameterization, test primes, multiply \(p q\) again to validate all stored block bases, or recompute \(\sigma\) and deficiencies. An arbitrary modified snapshot that passes the structural checks is not independently certified mathematically by loading it.

The mathematical conclusions apply to the identified constructor output and its source-prime premise. The saved complete arithmetic rows make further inspection possible; a separate proof-verification operation is not silently performed by the reader.

### 8.2 Size and failure contract

| Limit | Value |
|---|---:|
| \(k\) | 1 through 12 |
| Basis limit | At least \(2S\), at most 16,384 |
| Source prime entries | At most 2,000 |
| Candidate rows | At most 2,000 |
| Trial-prime positions across construction | At most 4,000,000 |
| Decimal query/snapshot scalar length | At most 128 digits |
| Page size | 1 through 256 |
| Source identifier length | 1 through 2,048 characters, nonblank |

The prime-list premise supplies at most one candidate per listed prime, and each scan visits at most the list length. The conservative four-million trial limit therefore bounds the permitted structural envelope. The actual source used only 7,779 positions.

Invalid input, insufficient basis coverage, malformed saved records and unsupported bounds throw errors. The constructor does not return a partial result as a complete catalog. There is no checkpoint continuation for an interrupted constructor. Saved pages are ordinary finite cursors, and their family size is fixed by the snapshot.

The actual constructor exercised \(k=12\). The \(k=1,\ldots,11\) branches, absent-candidate response, `candidatePage`, empty-result handling, invalid-input/budget paths and zero/end-page branches were source-inspected, not executed on additional examples. No known small weird number, earlier source computation or published table was replayed.

## 9. Scope of the result

Every successful row gives a finite, explicit even primitive weird number under the identified prime-source premise. Completeness refers to the chosen \(k=12\) formula (2), with one candidate \(q\) for every prime \(p\) in its stated interval. It does not make the formula necessary for weirdness, classify composite-\(q\) products, cover other factorizations, give a minimal primitive weird number, prove a density, establish infinitude, or find an odd weird number.

The contribution is the bounded constructor, complete arithmetic custody and saved navigation interface for this finite family. The sufficient criterion, ordinary-divisor definitions and earlier prime basis retain their stated attribution.
