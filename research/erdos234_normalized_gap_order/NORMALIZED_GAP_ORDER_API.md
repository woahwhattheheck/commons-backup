# Exact finite normalized prime-gap ordering and empirical counts

This package indexes the 1,897 prime-gap records with zero-based indices n=2,…,1898 from an identified consecutive list of 1,900 primes. Its normalized value is

```text
g(n) / ln(n), where g(n) = prime[n+1] − prime[n].
```

The denominator is the logarithm of the **index**, not of the prime. The construction orders these values exactly through integer-power comparisons, retains every adjacent order certificate, and identifies equal values. It computes no logarithm approximations.

The saved reader provides exact empirical counts at thresholds of the form a/(d ln b), ranks, selections, ties and restricted families. Optional rational enclosures of selected values are fresh reader calculations with complete finite series and tail records.

The actual input has **1,888 distinct normalized values**, including **nine ties of size two**. Its minimum is **2/ln(1896)**, from primes 16,361 and 16,363. Its maximum is **34/ln(216)**, from primes 1,327 and 1,361. This maximum differs from the largest raw gap, 44.

## Sources and mathematical scope

The complete [FormalConjectures statement of Erdős 234](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/234.lean) was read at blob `cac644f9ba9d9f752db9225cd432717f4b5211f4` (1,179 bytes). It asks whether, for every nonnegative c, the set of natural indices with primeGap(n)/log(n)<c has a density given by a continuous function of c. The declaration is annotated research open and has a local placeholder. No external proof or current literature survey was performed.

Its definition dependency, `FormalConjecturesForMathlib/NumberTheory/PrimeGap.lean`, was read at commit `89294ea02bd7cd678d59984add52cb4baef3dbf4`, blob `81fa618bd2241aadd88666383c9f53139455ded3`. It defines primeGap(n) using consecutive `Nat.nth Nat.Prime` values. The finite API explicitly uses the retained array's zero-based indexing, prime[0]=2, and omits indices 0 and 1 so all logarithms used for comparison are positive.

[NIST DLMF §4.6, equation 4.6.4](https://dlmf.nist.gov/4.6.E4) supplies the classical identity
```text
ln z = 2 [x + x³/3 + x⁵/5 + …],  x=(z−1)/(z+1).
```
For the positive real arguments used here, this is the natural logarithm. The displayed identity was directly read; the explicit truncation bound and finite integer-rounding implementation below are this package's derivation. No numerical table or earlier logarithm computation was replayed.

A finite empirical distribution is a step function and does not establish existence, continuity or a formula for a limiting density. This package's finite ordering and threshold counts make no new prime-gap bound, record, prize or global theorem claim.

## Input custody

The prime input is the already accepted basis from Commons #31426:

| Field | Identity |
| --- | --- |
| Repository | `woahwhattheheck/commons` |
| Source path | `research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json` |
| Immutable merge | `8bcf059ef0fda877c0975f7a89a2ae565e71a3b8` |
| Complete blob | `7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd` |
| Consumed field | `.snapshot.basis.primes` |
| List length | 1,900 |
| New input blob | `c8e31161f6d6f9abca21712b1d07da7e1af0dcef` |

The complete immutable source had already been recovered and byte-checked for #31720. This consumer uses that retained prime list without another provider fetch. It does not use the old least-factor array or rerun its sieve, primality work, squarefree calculations or original triangular-row computation. Consecutiveness, primality and completeness are identified input premises.

The constructor newly forms the 1,897 differences for indices 2 through 1898. It bounds the supplied list to 4–4,096 increasing integers at most 10,000,000 and requires every selected positive gap to be at most 512. These checks bound the interface; they are not primality tests.

## Exact order and ties

For i,j>1 and positive gaps gᵢ,gⱼ, positivity of logarithms gives

```text
gᵢ/ln i < gⱼ/ln j
  iff gᵢ ln j < gⱼ ln i
  iff j^gᵢ < i^gⱼ.
```

Equality is characterized by equality of those two positive integers. Thus exact integer powers suffice for sorting and identifying ties. The constructor caches powers by their base and exponent; a tie is ordered secondarily by increasing index n.

The snapshot retains the complete input-order records, sorted index order, tie groups, gap histogram, and one certificate for each adjacent sorted pair. Each certificate contains both indices, both integer powers, and their comparison result. The 1,896 comparisons cover the entire sorted order. They are saved evidence from this one construction, not independently recomputed on reopen.

The nine nontrivial tie groups are:

| First sorted rank | Indices |
| ---: | --- |
| 410 | 32, 1024 |
| 470 | 25, 625 |
| 683 | 121, 1331 |
| 831 | 9, 729 |
| 1014 | 6, 1296 |
| 1186 | 18, 324 |
| 1571 | 17, 289 |
| 1622 | 14, 196 |
| 1764 | 2, 8 |

Ranks are zero-based over records. Tied records remain distinct because their prime-gap indices are distinct; the group table separately identifies equal normalized values.

## Exact threshold counts

A threshold is represented by integer fields `{a,d,b}`, meaning **a/(d ln b)**. The field b is the argument of a natural logarithm, not a change of logarithm base. The default d is 1.

The supported bounds are 0≤a≤64, 1≤d≤16 and 2≤b≤1,000,000. Under the gap bound, comparison requires powers with exponent at most 8,192. For every retained record,

```text
g/ln n < a/(d ln b)  iff  b^(d·g) < n^a.
```

Equality and greater-than cases use the same exact integers. The case a=0 correctly has every normalized gap strictly above the threshold.

The reader binary-searches its conditioned saved order twice: once for the first value at least the threshold and once for the first value strictly greater. This produces separate counts below, equal and above. Every visited record, both integer powers and the comparison are retained in the query trace. Powers are cached within that query. No floating-point logarithm affects these answers.

The reported strict empirical fraction is below-count divided by the number of conditioned records. An empty family is explicitly marked `empty_family:true`; its conventional fraction field 0/1 is not asserted to be an empirical probability distribution on a nonempty sample.

Range queries use **[lower,upper)**. They compare the two symbolic thresholds by integer powers, then subtract their strict prefix counts. Conditions can restrict the index interval and the raw gap interval. They filter existing records; they do not generate another prime sequence.

This bounded symbolic threshold family is an interface choice. The API does not claim exact classification at every arbitrary real or rational threshold.

## Rational enclosures for selected values

The optional `approximate` query uses exact rational arithmetic. Write n=2ᵏz with 1≤z<2, and put x=(z−1)/(z+1), so 0≤x<1/3. The same series at x=1/3 supplies ln 2, and ln n=k ln 2+ln z.

For T=48 terms, the positive omitted tail satisfies

```text
0 ≤ remainder ≤ 2 x^(2T+1) / ((2T+1)(1−x²)).
```

This follows by replacing each omitted denominator by 2T+1 and summing the resulting geometric series. No truncation theorem is attributed to DLMF beyond its displayed infinite identity.

At scale S=2¹²⁸, the implementation floors each of the 48 scaled terms exactly. Their sum L is a lower bound. Let r count terms with a nonzero fractional remainder, and let t be the ceiling of the scaled tail bound. Then U=L+r+t is an upper bound. The certificate retains all term floors, r, the exact scaled-tail numerator and denominator, its ceiling, and L and U.

Combining the ln 2 and local certificates gives positive integers Lₙ,Uₙ with Lₙ≤S ln n≤Uₙ. Therefore

```text
gS/Uₙ ≤ g/ln n ≤ gS/Lₙ.
```

Both endpoints are returned as reduced rational pairs. These are outward enclosures, not rounded binary floating-point estimates. They play no role in the saved sort or exact threshold answers.

Series certificates are cached by their reduced x argument within the reader, and combined logarithm certificates by n. A new query may therefore perform new series arithmetic; such work is counted separately from construction. The actual four displayed-value queries used five distinct series arguments, 240 total terms, and the shared ln 2 certificate.

## API and saved-data contract

The dependency-free CommonJS module has no I/O. It exports `compile(input)` and `openIndex(snapshot)`.

Construction input:

```javascript
{
  primes: identifiedConsecutivePrimeList,
  first_index: 2,
  last_index: 1898,
  provenance: identifiedSource
}
```

The first index is at least 2, and the last is at most list.length−2. The generic bounds above apply before sorting. Input values are ordinary safe integer numbers.

The opened reader exposes `query(request)` and `stats()`. Query outputs are copied JSON-compatible records. Arbitrarily large exact powers and rational numerators/denominators are serialized as decimal strings.

| Operation | Fields | Result |
| --- | --- | --- |
| `summary` | none | Counts, ties, histogram, extrema and constructor work |
| `record` | n | One saved record, global rank and tie membership |
| `groups` | optional nontrivial | All groups, or only groups with more than one record |
| `adjacent` | optional start, limit≤2000 | Complete saved order certificates in the requested slice |
| `family` | optional filter | Conditioned record count |
| `select` | rank; optional filter | Record at a zero-based conditioned rank |
| `rank` | n; optional filter | Rank or outside-filter disposition |
| `page` | optional start, limit≤2000, filter | Consecutive saved records |
| `cdf` | threshold; optional filter | Strict-below, equality and above counts with all search comparisons |
| `range` | lower, upper thresholds; optional filter | Exact count in [lower,upper), with both prefix traces |
| `approximate` | n | Rational enclosure and complete fresh-or-cached series certificates |
| `conditions` | none | All currently cached conditioned index lists |

A filter accepts `first_index`, `last_index`, `min_gap` and `max_gap`. Defaults cover the entire saved input and gaps 1–512. Each new normalized condition scans all saved records once and preserves their exact sorted order. At most 16 conditions are cached. Exporting conditions does not make them inputs automatically reused by a new reader.

A page defaults to start 0 and limit 20; zero-length slices are allowed. Out-of-range selections throw. Unknown operations or filter keys throw.

### Open the published data

```javascript
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);
const reader = loaded.exports.openIndex(JSON.parse(indexText));

const answer = reader.query({
  op: "cdf", threshold: { a: 1, d: 1, b: 2 }
});
const tied = reader.query({ op: "select", rank: 410 });
const display = reader.query({ op: "approximate", n: tied.n });
```

Opening verifies bounded metadata, consecutive record indices, complete sorted-order coverage, complete group coverage, saved adjacency identities and comparison signs, and consistency of adjacency equality with group membership. It compares the stored integers but does not exponentiate them again. It does not subtract the prime gaps again, sort records, regenerate primes, or execute a logarithm series. Individual saved power identities and prime-source facts remain identified construction/input premises.

## Actual results

The one constructor retained all 1,897 records and all 1,896 adjacent certificates. The reader then made 36 queries; every response was individually banked and all are included in the aggregate packet. No reader call failed, no response was lost, and no source or calculation was rerun.

Exact global threshold results:

| Threshold c | Values <c | Values =c | Values >c |
| --- | ---: | ---: | ---: |
| 0 | 0 | 0 | 1,897 |
| 1/(2 ln 2) | 529 | 1 | 1,367 |
| 1/ln 2 | 1,229 | 1 | 667 |
| 2/ln 2 | 1,764 | 2 | 131 |
| 3/ln 2 | 1,872 | 0 | 25 |
| 8/ln 2 | 1,897 | 0 | 0 |
| 2/ln 32 | 410 | 2 | 1,485 |

The equal indices at the first three positive thresholds are respectively [16], [4], and [2,8]. Equality at 2/ln 32 is the group [32,1024]. The half-open interval [1/(2 ln 2),1/ln 2) contains 700 records.

Restricting to indices 1000–1898 gives 899 records; 606 are strictly below 1/ln 2 and none equals it. The raw-gap-two family contains 289 records, all exported. The raw-gap-at-least-20 family contains 138 records, with its first 20 exported.

Six selected records were returned to their original ranks: global ranks 0, 1896, 948, 410 and 411, plus rank 288 within the gap-two family. The two adjacent tied records at ranks 410 and 411 remain distinct records with equal normalized values.

The four rational-enclosure queries concern indices 1896, 216, 1828 and 32. Their complete large rational endpoints, term floors and tail bounds are in the saved packet. The minimum and maximum symbolic expressions stated above are exact; no decimal value is needed to establish them.

### Construction work

| Counter | Count |
| --- | ---: |
| New gap subtractions | 1,897 |
| Integer powers formed | 9,039 |
| Power-cache hits | 23,775 |
| Sort comparisons | 14,511 |
| Adjacent certificates | 1,896 |
| Logarithm series terms | 0 |
| Prime tests / old sieve work | 0 / 0 |

### Fresh reader work

| Counter | Count |
| --- | ---: |
| Public queries | 36 |
| Records loaded | 1,897 |
| Saved adjacent-integer comparisons | 1,896 |
| Condition row scans | 7,588 |
| Conditions created / cache hits | 4 / 24 |
| Threshold integer powers | 162 |
| Threshold power-cache hits | 270 |
| Threshold comparisons | 216 |
| Range-order powers | 2 |
| New series arguments / cache hits | 5 / 3 |
| Series terms and floor divisions | 240 / 240 |
| Series tail bounds | 5 |
| Combined logarithms retained | 4 |
| New gap subtractions / constructor-order powers / sorting | 0 / 0 / 0 |
| Prime tests / old sieve work | 0 / 0 |

Counters describe named operations, not constant-time bit costs or elapsed performance. The new threshold powers and series terms are real query arithmetic. “Saved reader” does not mean zero arithmetic.

## Files and immutable identities

| File | Purpose | Git blob |
| --- | --- | --- |
| `normalized_gap_order.cjs` | Constructor and reader | `f6c11685628cfbcd44ef6264ee05f253d91a80fd` |
| `prime_indices2_1898_index.json` | Complete order and certificates | `e51fb877c4b5474308e95443f9dc19e9b08fd92a` |
| `saved_reader_queries.json` | All 36 outputs and counters | `49c3feafdc4dfdcb0668670881ac7ab3714c36ec` |
| `NORMALIZED_GAP_ORDER_API.md` | This guide | Bound by publication receipt |
| `README.md` | Entry point | Bound by publication receipt |

The index is 444,734 bytes; the full reader packet is 93,959 bytes. Both use compact JSON with a terminal newline. Source and input were banked before construction; data were banked before opening the reader. Exact Git identities bind bytes, not external mathematical truth.

This is a finite empirical navigation capability, with explicit normalization, endpoint and threshold conventions. It does not settle the limiting-density or continuity question.
