# Exact divisor-factorial series enclosures

This package indexes the positive-index real series
\[
\alpha_k=\sum_{n\ge1}\frac{\sigma_k(n)}{n!},\qquad
\sigma_k(n)=\sum_{\substack{d\ge1\\d\mid n}}d^k.
\]
Each ordinary positive divisor occurs once. Both 1 and n are included; when n=1 they are one divisor. The actual new input is k=5, cutoff N=128. All numeric certificate operations use integers and exact rational fractions.

The saved enclosure certifies 204 decimal fractional digits of this series. It begins **143.81196393273824608939064809196105382067726047655918**. This is a truncated prefix, not rounded decimal output. The same enclosure does not certify the next decimal place: its endpoint floors differ at scale 10^205. That is a limitation of this particular enclosure, not a claim about the existence of a decimal expansion or its true digits. No irrationality conclusion follows.

## Source and indexing boundaries

Kyle Pratt, *The irrationality of a divisor function series of Erdős and Kac*, arXiv:2209.11124v1, submitted 22 September 2022, supplies the positive-index series and divisor-power convention in the directly read [author abstract](https://arxiv.org/abs/2209.11124). Only the abstract and metadata were consumed for this dependency; no proof, numerical table or previous example was reviewed or recomputed.

The separately fully read [FormalConjectures Erdős 252 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/252.lean) had observed blob ed8605f7345d21159db997cc5099606f9c80d5e9, 3953 UTF-8 bytes. The native request was the contents endpoint for that path without an explicit ref. This is an observed file identity, not an invented commit pin. Its main and k>=5 irrationality assertions carry research-open annotations and local placeholders; smaller k cases and conditional statements have separate solved annotations and local placeholders. These tags are not proof audits. The formal definition uses a Nat-index sum. This API does **not** assert an unchecked equality between that definition and the positive-index series: no value of sigma_k(0) or zero-th summand is imported.

The series and historical attribution precede this implementation. This package supplies a finite exact numerical certificate and saved navigation. It does not settle the k=5 irrationality question, improve an irrationality theorem, assert a current literature census, or claim an award or mathematical priority.

## Files and input

| File | Role |
|---|---|
| factorial_series_enclosures.cjs | CommonJS constructor and saved reader |
| FACTORIAL_SERIES_ENCLOSURES_API.md | This contract, derivation, actual input and limitations |
| k5_cutoff128_index.json | Complete powers, divisor fibers, factorials, partial sums and enclosures |
| saved_reader_queries.json | All 34 actual query requests and complete responses, with reader counters |
| README.md | Entry point and finite scope |

Declared production input: k=5, N=128. There is no inherited numerical input, prime basis, least-factor table, factorial table or divisor computation. The new source and input were banked as Git blobs before the one constructor call:

- Source: 1a726e8d7a8218bd3971abed3bba9c2ad698f15a, 8812 bytes.
- Input: 8302870928b122ad2f234f16999beba7a4d7a931, 312 bytes.
- Complete output: 9f72f44c3df1c0e14f7210e08e53e6f2fa7890df, 177200 bytes.
- Complete reader packet: b2d8157d67789f66952547e0836cd2246e70e8ef, 155269 bytes.

The generic constructor rejects k outside 1..12 and N outside 1..512. This consumer was fixed at 128 before execution and was not expanded. The query precision ceiling is 512 fractional digits in bases 2..36. Input decimal integer strings are capped at 10000 characters; row pages contain at most 64 rows.

## Exact construction and tail proof

For d=1,...,N+2 the constructor retains d^k once. For each d<=N it visits every positive multiple n<=N, records d in that row's divisor fiber, and adds d^k. Thus all ordinary divisors and no others are present, without factoring n or testing primality. Factorials are retained from 0! through (N+1)!; the final value is a tail-bound sentinel.

If A_n/n! is the partial sum through n, then
\[
A_0=0,\qquad A_n=nA_{n-1}+\sigma_k(n).
\]
Every row stores this unreduced numerator and factorial as well as its reduced lower endpoint. Reduction uses an integer gcd; there is no conversion to a floating approximation.

For a positive integer m, there are at most m positive divisors, each at most m. Hence
\[
\sigma_k(m)\le m^{k+1},\quad t_m=\frac{m^{k+1}}{m!},\quad
\frac{t_{m+1}}{t_m}=\frac{(m+1)^k}{m^{k+1}}
=\frac1m\left(1+\frac1m\right)^k.
\]
The last expression decreases with positive m: both positive factors decrease. For the tail after n set
\[
B=(n+1)^{k+1},\quad C=(n+2)^k,\quad \rho_n=C/B.
\]
When C<B, every successive tail ratio is at most rho_n, so the convergent geometric majorant gives
\[
0<\alpha_k-\frac{A_n}{n!}
\le \frac{t_{n+1}}{1-\rho_n}
=\frac{B^2}{(n+1)!\,(B-C)}.
\]
The saved certificate uses the conservative closed interval [lower, lower+tail]. The tail includes n+1 and all following terms. This argument also establishes convergence for the positive-index series at every supported k; no irrationality inference is involved.

If C>=B, the row retains its exact partial sum and ratio but stores null for tail and upper, with reason geometric_ratio_not_below_one. It does not claim divergence or manufacture a bound. For this actual input only n=1,2 are unavailable; n=3,...,128 give 126 enclosure rows.

## Actual construction and precision results

The one construction performed:

| Operation | Count |
|---|---:|
| d^k evaluations, including two sentinels | 130 |
| Divisor visits and sigma additions | 645 each |
| Factorial multiplications | 129 |
| Partial-numerator recurrence steps | 128 |
| Available tail rows | 126 |
| Unavailable tail rows | 2 |

All 128 divisor fibers, every partial numerator and all factorials from 0! through 129! are retained. No missing layer needs regeneration.

The saved reader's precision searches give:

| Truncation n | Base | Largest certified places within requested cap | Requested cap | Cap reached |
|---:|---:|---:|---:|---|
| 16 | 10 | 5 | 50 | no |
| 32 | 10 | 26 | 100 | no |
| 64 | 10 | 79 | 200 | no |
| 128 | 10 | 204 | 512 | no |
| 128 | 16 | 170 | 512 | no |
| 128 | 2 | 512 | 512 | yes |

“Largest” here is relative to the saved enclosure and requested cap. The binary result does not establish the maximum beyond 512. For each radix base b and number of places D, the reader compares the exact integers floor(L b^D) and floor(U b^D). Equality certifies floor(alpha_k b^D); inequality returns undecided. The property is monotone as D decreases, which supports the bounded binary search used by precision. It is truncation, never rounding to nearest.

The complete certified decimal prefix at 204 fractional places is:

```
143.811963932738246089390648091961053820677260476559189328353333770067919541089397448478650619185174413971850377051919936841094858406257341556611806836713613459437562601552020897291835966200605090178188710010
```

The packet also retains the exact rational endpoints and every precision probe, including the failure at 205 places. Separate digits requests certify 0,10,50,100,200 decimal places; the 300-place decimal request is undecided. Base-16 at 128 places, base-36 at 100 places and base-2 at 512 places certify. A digits request at truncation n=2 returns unavailable.

## Saved-reader API

Load the module with require and parse the saved JSON, then call openIndex(saved). Calling openIndex does not construct divisor fibers, powers, factorials, partial sums or tail enclosures. It clones and checks shapes, integer encodings, row labels and positive rational denominators. It trusts the identified saved certificate and its production derivation; these structural checks are not an independent proof replay or a verifier for adversarially fabricated data.

The reader exposes query(request) and work(). Default n is N where specified.

| Operation | Fields and result |
|---|---|
| summary | k, N, final interval and saved construction counters |
| term | n; complete row plus its divisor/power fiber and unreduced term fraction |
| interval | optional n; exact lower, upper, ratio, tail and availability |
| page | from, limit<=64; complete consecutive row records and next position |
| digits | base, places, optional n; scaled endpoint floors and certified prefix or undecided/unavailable |
| precision | base, cap, optional n; bounded maximum certified places and all probe evidence |
| compare | signed decimal numerator, positive decimal denominator, optional n; exact above/below/undecided relation to that rational threshold |

Example consumer syntax, shown for users and not another execution here:

```javascript
const { openIndex } = require('./factorial_series_enclosures.cjs');
const fs = require('node:fs');
const saved = JSON.parse(fs.readFileSync('k5_cutoff128_index.json', 'utf8'));
const reader = openIndex(saved);
reader.query({op:'digits', base:10, places:100});
reader.query({op:'term', n:128});
reader.query({op:'compare', numerator:'144', denominator:'1'});
```

All large integers and rational components are decimal strings. Numeric row labels, bases and digit counts are bounded safe integers. The output alphabet for bases above 10 is 0..9 followed by lowercase a..z. Repeated saved responses are cloned so callers cannot mutate the retained index.

For compare, an interval strictly above the threshold returns above and one strictly below returns below; otherwise it returns undecided. In particular a threshold equal to the saved lower endpoint returns undecided under this conservative closed-interval rule, even though the positive tail independently implies strictness. The API does not silently strengthen its stated comparison contract.

## Actual first saved-reader use and custody

All 34 requests and complete responses were stored individually before the next query. The completed packet was then banked. There was no failed query, lost output or continuation repair.

The actual consumer read five complete term fibers (n=1,2,6,64,128), seven interval rows, first and last eight-row pages, ten radix requests, six precision searches and three exact threshold comparisons, plus the summary. The first two threshold comparisons use the two adjacent rational bounds of the certified 204-place decimal cell and return above and below; equality with the saved lower endpoint returns undecided.

Fresh query arithmetic is explicit:

| Reader work | Count |
|---|---:|
| Queries | 34 |
| Saved-row reads | 47 |
| New radix-scale powers | 53 |
| Scale-cache hits | 11 |
| Exact floor divisions | 128 |
| Threshold cross-products | 12 |
| Precision probes | 55 |
| Constructor steps | 0 |

The nonzero powers and arithmetic above belong to fresh reader queries. They are not portrayed as zero-cost lookup. No divisor, factorial, partial-sum recurrence or tail construction was replayed. The first reader consumed the complete banked construction, rather than checking a second independently recomputed copy.

## Delivery and limits

The five files form one complete finite package. Full content identity and native publication metadata establish custody; they do not establish runtime deployment, external acceptance or formal verification. Source and data are public reviewable bytes, with saved outputs documenting the actual consumer.

Ownership checks were bounded exact-number Slack, all-state PR and code queries, all returning empty before the activity. This is coordination evidence, not a global uniqueness or exclusivity claim. The selected series input is independent of earlier divisor and factorial deliveries.

The enclosure can settle a requested prefix only when its saved endpoints agree at that scale. It does not determine every digit, identify the best possible majorant, or certify irrationality. The whole infinite series appears only through the proved positive-tail enclosure; the package does not promote finite precision into an infinite arithmetic conclusion.
