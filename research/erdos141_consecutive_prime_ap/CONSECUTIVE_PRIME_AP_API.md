# Saved arithmetic progressions of consecutive primes

This finite API indexes consecutive blocks of an identified global-prime prefix, separating arithmetic progressions from non-progressions. A block of length at least three is an AP exactly when every internal saved prime gap is equal. Rejected blocks carry the first adjacent pair of unequal gaps as a concise witness.

## Sources and conventions

The fully read [FormalConjectures Erdős 141 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/141.lean) has 3,717 bytes and Git blob `4fdbda793cc1b21d094cfabca98d9b83441547cd`. Its predicate requires a set of k consecutive global primes that also forms an arithmetic progression. Its main every-k≥3 question, eleven-prime case, and infinite-three/general infinitude variants are annotated research open, with local placeholders. The first-cases declaration for k≤10 is annotated research solved, also with a local placeholder. The file also contains elementary three-prime examples; these were not executed or used as a verification target. Source annotations are recorded without a current literature or proof audit.

H. Dubner, T. Forbes, N. Lygeros, M. Mizony, H. Nelson and P. Zimmermann, *Ten consecutive primes in arithmetic progression*, Mathematics of Computation 71 (2002), 1323–1328, supplies historical primary context. Its [author-hosted paper](https://lygeros.org/wp-content/uploads/2019/12/S0025-5718-01-01374-6.pdf), introduction on page 1323, expressly distinguishes requiring AP terms to be prime and requiring the intervening integers to be composite. Only this convention passage was consumed; no numerical construction, table, record, proof, or source implementation was imported or checked.

An equally spaced subsequence obtained by skipping primes is not an eligible consecutive-prime block. Here global consecutiveness comes from the identified saved input premise. Index i is zero-based, with prime[0]=2. Positive gaps imply a positive AP step. The API deliberately restricts all counted blocks to length at least three, so empty, singleton and two-term conventions do not create additional records.

The bounded exact-number Slack and code checks found no current carrier. The exact PR query hit a GitHub secondary-rate-limit 403 and remains held without retry or alternate acquisition. PR-search coverage was incomplete and was disclosed in the activity message; no global absence of previous work is asserted.

## Input and new work boundary

This consumer uses only `.primes` and `.gaps` from the complete #31726 index:

| Field | Identity |
| --- | --- |
| Path | `research/erdos238_consecutive_prime_blocks/prime_prefix1900_blocks.json` |
| Immutable head | `629b9622fbe94022c6bc3094bf7b0f3521f630a3` |
| Complete input artifact blob | `0224dfb74525d7d18b6e5aba20f01e1784a0c8f2` |
| Supplied host | 1,900 primes, 2 through 16,381 |
| Supplied raw edges | 1,899 consecutive gaps |

All gap values are copied literally. There is no new gap subtraction, sieve, primality test, old threshold-union calculation, or normalized-gap ordering. The ultimate accepted prime list remains the #31426 premise documented in #31726. The current constructor checks increasing labels and saved endpoint alignment but does not independently prove primality, consecutiveness or inherited subtraction correctness.

The module bounds input to 3–4,096 increasing supplied primes at most 10,000,000, with exactly one positive saved gap per adjacent pair, also at most 10,000,000. The complete input, source and results are retained before publication.

## Equal-gap run index

Partition the edge sequence into maximal intervals of equal gap. A run with edges a,…,b describes the vertex interval a,…,b+1. Consecutive runs share one vertex, but a block with at least two edges can lie in at most one run. Thus AP blocks of length at least three are exactly the subintervals of these run vertex intervals.

For each possible block start i, the saved start record gives its edge-run identifier, step, and final AP endpoint e(i). A block [i,j] is an AP if and only if j≤e(i). If j>e(i), the first unequal adjacent gap pair is at edges e(i)−1 and e(i). Both edges are internal to the rejected block. This witness uses the saved run boundary and two saved gap values, with no new equality scan at query time.

The constructor also stores complete base prefixes for AP and non-AP blocks and a length histogram of AP blocks. A run with L vertices contributes L−k+1 blocks at each length 3≤k≤L. Its first and final vertex may be shared with another run; no length-three block is double-counted.

For a query window and length bounds a≤length≤b, each start i has allowed final indices in an interval. AP queries intersect

```text
[i+a−1, i+b−1] ∩ [first_window,last_window] ∩ (−∞,e(i)].
```

Non-AP queries use the same length/window restrictions and intersect with [e(i)+1,∞). An optional AP step filter can discard a start row. The row count is the interval length, or zero. Cumulative row counts give exact lexicographic order by (first index,last index). Selection binary-searches these prefixes and offsets inside one row; rank uses the corresponding row and final-index offset.

The complement family is relative to all in-host consecutive blocks satisfying the same index and length restrictions, with length at least three. Step restrictions are available only for the AP family, since a non-AP block has no common step.

Reopening validates structural dimensions, full edge-run coverage and start-to-run links. It does not replay all equal-gap comparisons, regenerate runs or serve as an independent hostile-input proof checker. The stored data are a trusted compiled index under the identified input premise.

## Reader contract

```javascript
const {openIndex} = require("./consecutive_prime_ap.cjs");
const saved = require("./prime_prefix1900_ap_index.json");
const api = openIndex(saved);
api.query({op:"family",condition:{kind:"ap",min_length:3}});
api.query({op:"family",condition:{kind:"non_ap",min_length:11,max_length:11}});
```

The constructor is `compile(input)`; saved consumers use `openIndex` and never invoke the constructor. Both the saved input and returned query objects are copied.

Conditions support `kind:"ap"` (default) or `"non_ap"`; inclusive `first_index` and `last_index`; integer prime cutoff `x`; `min_length` and `max_length`, both at least three; and AP-only `min_step` and `max_step`. Defaults cover the full host, all lengths at least three and every positive saved step. Indices are bounded by the retained host, x lies in 0…10⁹, and step bounds lie in 1…10⁷. Counts fit safe integers for the constructor's maximum 4,096 vertices.

A cutoff below the first prime or a reversed index condition gives an empty family. A reversed length or step interval is invalid. Up to 32 normalized conditions are cached; each new condition scans saved start records and constructs conditional ranges and prefixes. This is explicitly fresh reader arithmetic. Prime-cutoff binary search occurs before cache lookup and is counted even on a cache hit.

| Operation | Returned information |
| --- | --- |
| `summary` | Host sizes, run count, AP/non-AP totals, AP length histogram and constructor work |
| `family` | Normalized condition, exact count and longest admitted block |
| `condition_rows` | All conditional endpoint ranges and cumulative counts |
| `select` | Zero-based ranked block, AP status and first unequal-gap witness when applicable |
| `rank` | Conditional membership and zero-based rank for a supplied block |
| `page` | Up to 512 ranked blocks, with total and next offset |
| `classify` | AP status of any in-host block of length at least three |
| `run` | One saved maximal run and its complete literal gap records |
| `runs` | Saved maximal runs meeting a supplied minimum vertex length |
| `conditions` | All cached condition summaries |

`classify` concerns the AP property independently of a condition. Use `rank` for membership in a filtered family. A successful classification does not claim the block is maximal; the saved run supplies that separate information. “Non-AP” is a finite block property, not a conjecture counterexample.

The input host ends at 16,381. Queries with a larger x still concern only this host. No later prime, later AP, new search frontier, eleven-prime resolution, global infinitude, historical record improvement or prize eligibility is inferred.

## Actual finite result

The new comparison pass made exactly 1,898 adjacent gap comparisons. It formed 1,798 maximal equal-gap runs and 1,898 start records. No gap was subtracted.

| Family in the retained prefix | Count |
| --- | ---: |
| All consecutive blocks of length at least three | 1,802,151 |
| AP blocks | 113 |
| Non-AP blocks | 1,802,038 |
| AP triples | 101 |
| AP quadruples | 12 |
| AP blocks of length five or greater | 0 |
| AP blocks with common step six | 101 |
| AP blocks with every prime at most 1,000 | 16 |
| Eleven-prime windows | 1,890 |
| Non-AP eleven-prime windows | 1,890 |

The largest AP length in this identified finite host is four. Every one of its twelve maximal four-prime runs has step six; this is an observed finite output, not a general statement about consecutive-prime quadruples.

The twelve four-prime runs have first indices 53, 270, 463, 681, 708, 820, 828, 1509, 1593, 1725, 1841 and 1852. The reader exported all 113 AP blocks and all 1,890 non-AP eleven-prime windows. Every rejected window includes its first unequal-gap witness. These windows lie wholly inside the retained prefix; their rejection does not address eleven-prime progressions elsewhere.

## Actual saved queries and source-boundary correction

The complete saved packet has **43 outputs** and **nine exact inverse-rank matches**. It contains all AP blocks, all eleven-prime rejection witnesses, two full run records, the length-three/four/eleven counts, the complete cutoff-1,000 conditional ranges, all 101 step-six AP blocks, an empty-cutoff answer and two explicit block classifications.

| Family | Rank | Selected indices |
| --- | ---: | --- |
| All AP blocks | 0 | [1,3] |
| All AP blocks | 56 | [821,823] |
| All AP blocks | 112 | [1883,1885] |
| All non-AP blocks | 0 | [0,2] |
| All non-AP blocks | 901,019 | [556,616] |
| All non-AP blocks | 1,802,037 | [1897,1899] |
| Non-AP eleven-prime windows | 945 | [945,955] |
| AP blocks with primes at most 1,000 | 15 | [163,165] |
| Non-AP eleven-prime windows inside indices 300…600 | 145 | [445,455] |

The first constructor and 39-output reader used source `7c900597518109554e860927d696b286765c7ed9`. Static interface review then found that a returned normalized non-AP condition included neutral step bounds that the input boundary would reject if resubmitted. No failed query was performed. The final source `5ce47a110bec7002f127f8b769dba3a9aed68a8a` accepts exactly these neutral defaults for non-AP queries while continuing to reject actual step restrictions. Its constructor is unchanged.

A fresh reader opened the existing data under that final source and performed four **new** queries on the previously unqueried index subwindow 300 through 600, with length exactly eleven. That family has 291 blocks. A selection and inverse rank reused the returned normalized condition successfully; rank 145 gives indices 445 through 455, primes 3,137 through 3,221, with unequal gaps 26 and 4 at edges 445 and 446. The final packet preserves both source identities, both work ledgers, all prior responses, and all four continuation responses. No constructor, old query, gap equality comparison or classification table was replayed.

The initial reader created nine conditions, scanned 13,454 saved start rows and evaluated the same number of endpoint-range counts. It performed 55 prime-cutoff comparisons, 23,064 selection steps, eight rank lookups and 2,114 saved-boundary classifications, returning 1,895 unequal-gap witnesses and six literal run-gap records. It had 23 condition-cache hits.

The final-source continuation created one condition, scanned 301 saved start rows, performed 301 range-count evaluations, eight selection steps, one rank lookup and one classification/witness. It had two condition-cache hits. Both phases report zero new gap subtraction, new gap equality comparisons, run reconstruction, sieving, primality work, old threshold merges and old normalized ordering.

Each response was individually banked before the next query. No output was lost, and neither reader phase threw an exception. The source correction is retained as a bounded API-input change rather than concealed as if the final source had produced all earlier outputs.

## Complete files and identities

| Artifact | Git blob |
| --- | --- |
| Frozen identified input | `1dc4831c65f9248d79572d52bcfff5ade73ae92d` |
| Originally executed constructor/reader | `7c900597518109554e860927d696b286765c7ed9` |
| Final published module | `5ce47a110bec7002f127f8b769dba3a9aed68a8a` |
| Complete run/start index | `442d4726b90825e378b8f20155500361027d4c45` |
| Complete 43-output reader packet | `df3e81a945ebdb86d4f533601a17d8490d11f89b` |

The package publishes `consecutive_prime_ap.cjs`, `prime_prefix1900_ap_index.json`, `saved_reader_queries.json`, this guide and `README.md`. The result is exact finite navigation of supplied data, with old source premises and new work separated. It is not a new prime search or a verification of the historical ten-prime construction.
