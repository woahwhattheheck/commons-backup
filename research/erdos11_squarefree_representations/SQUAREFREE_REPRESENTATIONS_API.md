# Complete squarefree-plus-power representations in a finite odd interval

This module constructs and saves a finite representation index for odd integers n. For each retained n it records every exponent l≥0 for which the positive remainder n−2^l is squarefree. Rejected candidates retain a prime-square divisor; accepted candidates use the declared completeness of the supplied prime basis and the saved segmented calculation.

The actual interval contains the 4,096 odd integers from **134,217,729 = 2²⁷+1** through **134,225,919 = 2²⁷+8191**. There are **91,257 representations**. The minimum count is **15**, attained only at **134,222,629**; **34 integers admit all 28 exponents** from 0 through 27. The saved reader made 34 queries without repeating the square-divisor construction.

## Sources and limits

The complete [FormalConjectures statement of Erdős 11](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/11.lean) was read at Git blob `585fa1676048dfa69ad4111dc40ea8644121756d` (2,679 bytes). Its main statement has odd n>1 and natural exponents l, hence includes l=0. Its general question remains annotated research open with a local placeholder. The same file separately annotates the finite existence range n<2⁵⁰ as solved, also with a local placeholder. We did not inspect an external proof or repeat that verification.

Consequently this package is **not a new existence range**. It adds all-representation counts, rank/select, conditional navigation and explicit rejection witnesses for its specified window. It neither proves the infinite statement nor extends the already recorded finite existence result.

[Granville's author publication page for 1998](https://dms.umontreal.ca/~andrew/1998.php) identifies Andrew Granville and K. Soundararajan, *A binary additive problem of Erdös and the order of 2 mod p²*, Ramanujan Journal 2 (1998), 283–298, and its squarefree-plus-power-of-two question. The directly accessed author PDF yielded unusably garbled text. That exact route remains held; no alternate copy, screenshot or retry was used. Detailed exponent and remainder conventions are therefore bound to the fully read formal statement and the explicitly stated API model, not to an unread PDF passage.

A positive integer is squarefree when no prime square divides it. Thus 1 is squarefree and 0 is not. This API always requires n−2^l≥1. Distinct exponents identify distinct representations of a fixed n, and l=0 contributes the power 1. The source's separate variants involving two powers or integers not divisible by four are outside this API.

The formal annotations are source metadata, not a fresh proof or exhaustive current-status assessment. No sponsor contact, submission, reward assertion, novelty claim or global non-Wieferich consequence is made.

## Identified input premise

| Item | Exact identity |
| --- | --- |
| Prior carrier | Commons #31426 |
| Repository | `woahwhattheheck/commons` |
| Path | `research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json` |
| Immutable merge | `8bcf059ef0fda877c0975f7a89a2ae565e71a3b8` |
| Full source blob | `7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd` |
| Full source size | 971,078 bytes |
| Consumed fields | `.snapshot.basis.primes` and `.snapshot.basis.limit` |
| Prime count / completeness limit | 1,900 / 16,384 |
| New frozen input blob | `2d00def8848abe904e1c005ff3538e41d3a1bb76` |

One full immutable fetch matched both the provider SHA and an independently computed Git blob identity. Only the listed prime basis and bound are input. The old least-factor array is not used, and neither its construction nor the original triangular-row arithmetic is repeated.

Primality and completeness through the declared bound are accepted premises. The generic source checks increasing order, numerical bounds and sufficient coverage, but does not perform a sieve to prove the supplied list is prime and complete. The guarantee for saved squarefree records is conditional on that identified input premise.

The maximum remainder is 134,225,918, below 16,384². If a prime square divides any positive remainder q in the covered union, that prime is at most √q and is therefore present in the supplied complete basis.

## Construction

For each power 2^l below the final n, form the inclusive candidate interval

```text
[max(1,start−2^l), end−2^l].
```

These intervals contain every positive remainder produced by the retained odd n. They also contain some unused integers; the package explicitly classifies the complete union of integer intervals. Adjacent or overlapping intervals are merged before square-divisor marking, so a covered integer receives one saved obstruction entry even if several representations use it.

The actual 28 source intervals merge to 15 intervals:

| Low | High |
| ---: | ---: |
| 1 | 8,191 |
| 67,108,865 | 67,117,055 |
| 100,663,297 | 100,671,487 |
| 117,440,513 | 117,448,703 |
| 125,829,121 | 125,837,311 |
| 130,023,425 | 130,031,615 |
| 132,120,577 | 132,128,767 |
| 133,169,153 | 133,177,343 |
| 133,693,441 | 133,701,631 |
| 133,955,585 | 133,963,775 |
| 134,086,657 | 134,094,847 |
| 134,152,193 | 134,160,383 |
| 134,184,961 | 134,193,151 |
| 134,201,345 | 134,209,535 |
| 134,209,537 | 134,225,918 |

There are 131,056 saved integer positions. In particular, 134,209,536 lies in a gap and is not classified by this snapshot.

The constructor squares the supplied primes in increasing order until passing the largest remainder. The 1,393 relevant prime squares are retained; the counter includes one additional stopping-square multiplication. In each merged interval it visits multiples of each relevant p². A previously unmarked position receives p as its least prime-square obstruction. Later visits leave that first witness unchanged.

A zero saved obstruction denotes squarefree. This is justified because every possible prime-square divisor is within the supplied completeness bound and was visited. It is not a claim that absence from an arbitrary short list proves squarefreeness.

After this segmented calculation, each retained odd n reads its candidate remainders from the saved intervals. Its row stores an exponent bitmask and the number of accepted exponents. A prefix array stores cumulative representation counts. Histograms by representation count and counts by exponent are retained.

The constructor uses ordinary safe integers under explicit bounds: odd start at least 3; 1–8,192 odd values; final value at most 2³¹−1; supplied basis limit at most 1,000,000; at most 600,000 merged integer positions. The actual operation is well inside these limits. No unbounded prime search or factorization is hidden in the constructor.

## Saved data and reader guarantees

The complete snapshot contains:

- the exact prime-basis premise, input range and provenance;
- all power labels and relevant prime-square records;
- all 15 merged intervals and every obstruction entry;
- all 4,096 exponent-mask/count rows;
- all 4,097 representation prefixes;
- the full count histogram and counts for all 28 exponents;
- constructor counters.

Opening the snapshot validates schema and bounded dimensions, odd range metadata, power labels, mask ranges, prefix increments, total count, segment ranges and lengths, and obstruction references to saved prime-square records. It copies the snapshot and builds saved lookups.

It does **not** rerun marking, recompute prime squares, recount every bitmask, repeat the original prime-basis sieve or independently certify every saved arithmetic identity. Those identities remain bound to the retained once-only construction. Reopening is structural checking, not an independent replay of its proof.

A requested rejected remainder additionally checks its saved divisibility and supplies the exact quotient. A requested complete number record checks consistency between the saved accepted mask and each candidate's saved remainder status. Those are counted fresh query operations.

## Order, conditions and multiplicities

Numbers are ordered by increasing n. Representation pairs are ordered first by n, then by increasing exponent l. A representation is the pair (n,l); its squarefree remainder is determined by subtraction.

Conditions select **numbers**, using any combination of:

- minimum and maximum total representation count;
- exponents required to be available for that number;
- exponents required to be unavailable.

After selecting numbers, pair navigation includes **all** of each selected number's representations. For example, requiring exponents 0 and 27 does not restrict pair selection to those two exponents. It selects numbers admitting both and then retains all their pairs.

Each new normalized condition scans the saved row masks and counts, storing selected row indices and cumulative pair counts. Up to 24 conditions are cached. Duplicate exponent entries collapse; an exponent both required and excluded yields an empty family. Exported conditions are complete reader records, not extra inputs automatically loaded by `openIndex`.

Zero-based rank/select uses the saved indices and prefixes. No representation can occur twice for the same (n,l), and no symmetry quotient is imposed. Integer interval queries select the retained odd numbers lying between their inclusive endpoints.

## API

The dependency-free CommonJS module has no I/O and exports:

| Export | Purpose |
| --- | --- |
| `compile(input)` | Execute one finite segmented construction and return the serializable snapshot |
| `openIndex(snapshot)` | Open saved data and return `query` and `stats` |

Construction input has this shape:

```javascript
{
  start: 134217729,
  count: 4096,
  basis: { limit: 16384, primes: identifiedPrimeList },
  provenance: identifiedSource
}
```

A number filter is:

```javascript
{
  min_count: 0,       // defaults to 0
  max_count: 28,      // defaults to the snapshot's exponent count
  required: [0, 27],  // exponent indices, not prime indices
  excluded: []
}
```

| Operation | Fields | Result |
| --- | --- | --- |
| `summary` | none | Range, histogram, exponent totals, segments and constructor counters |
| `value` | value | Saved squarefree status, explicit obstruction, or outside-union disposition |
| `number` | n; optional details | Accepted exponent list; optionally every positive candidate certificate |
| `pair` | n, exponent | One accepted representation or rejection witness |
| `family` | optional filter | Number count and all-pair count |
| `selectNumber` | rank; optional filter, details | Number at the zero-based conditioned rank |
| `rankNumber` | n; optional filter | Number rank or outside-filter disposition |
| `page` | optional start, limit≤1000, filter | Consecutive number records |
| `selectPair` | rank; optional filter | Representation at the zero-based conditioned pair rank |
| `rankPair` | n, exponent; optional filter | Pair rank, rejected candidate or outside-filter disposition |
| `range` | lower, upper; optional filter | Number and pair counts in an inclusive integer interval |
| `conditions` | none | All complete currently cached condition records |

Ranks and numerical fields are safe integer numbers, not decimal strings. Input n must be a retained odd value. Exponents must be among the snapshot's power labels. `value` accepts positive integers up to the largest possible remainder; being in that numerical range does not imply membership in the saved interval union. It does not silently factor an outside-union input.

Selecting outside a family's bounds throws. A page may begin at the family end and may request zero records. Default page length is 20. Unknown operations and filter keys throw. The public query wrapper returns copied JSON-compatible records.

### Example using the saved artifacts

```javascript
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);
const reader = loaded.exports.openIndex(JSON.parse(indexText));

const rare = reader.query({
  op: "selectNumber",
  rank: 0,
  filter: { min_count: 15, max_count: 15 },
  details: true
});
const chosen = reader.query({ op: "selectPair", rank: 45628 });
const inverse = reader.query({
  op: "rankPair", n: chosen.n, exponent: chosen.exponent
});
```

This consumes saved certificates. It does not run `compile`.

## Actual finite results

All 4,096 numbers admit between 15 and 28 representations. The complete histogram is:

| Representations | Number of n |
| ---: | ---: |
| 15 | 1 |
| 16 | 2 |
| 17 | 10 |
| 18 | 91 |
| 19 | 289 |
| 20 | 611 |
| 21 | 805 |
| 22 | 711 |
| 23 | 343 |
| 24 | 298 |
| 25 | 425 |
| 26 | 326 |
| 27 | 150 |
| 28 | 34 |

The unique minimum is n=134,222,629, with accepted exponents

```text
[1,3,5,6,7,9,12,13,15,16,17,18,19,21,24].
```

Its complete 28-candidate reader output includes all 13 rejected exponents. For example:

| Exponent | Remainder | Least prime-square obstruction | Quotient |
| ---: | ---: | ---: | ---: |
| 0 | 134,222,628 | 2²=4 | 33,555,657 |
| 4 | 134,222,613 | 7²=49 | 2,739,237 |
| 10 | 134,221,605 | 19²=361 | 371,805 |
| 23 | 125,834,021 | 311²=96,721 | 1,301 |
| 27 | 4,901 | 13²=169 | 29 |

These rows are examples from the complete saved query, not the entire rejection list.

The reader exported all 104 numbers having at most 18 representations and all 34 numbers having 28. It also recorded:

| Condition / range | Numbers | Representation pairs |
| --- | ---: | ---: |
| All retained numbers | 4,096 | 91,257 |
| At most 18 representations | 104 | 1,855 |
| Exactly 28 representations | 34 | 952 |
| Exponents 0 and 27 both available | 1,316 | 30,724 |
| Exponent 0 unavailable | 2,439 | 53,168 |
| Exponent 0 both required and excluded | 0 | 0 |
| First 100 retained odd numbers | 100 | 2,241 |
| First 100, with exponents 0 and 27 available | 32 | 769 |

Global pair selection witnesses:

| Rank | n | Exponent | Remainder |
| ---: | ---: | ---: | ---: |
| 0 | 134,217,729 | 1 | 134,217,727 |
| 12,345 | 134,218,837 | 11 | 134,216,789 |
| 45,628 | 134,221,825 | 25 | 100,667,393 |
| 91,256 | 134,225,919 | 27 | 8,191 |

All four were returned to their original pair ranks. The unique minimum number also passed its conditioned number-rank comparison. The sixth comparison was conditioned pair rank 15,362, selecting n=134,221,827 and exponent 2 under the requirement that exponents 0 and 27 both be available. This illustrates that number conditions do not narrow the later pair set to the required exponents.

A direct saved-value query confirms the endpoint convention for 1. Queries for 4, 9 and 49 return their explicit prime-square obstructions. The query at 134,209,536 reports outside the saved remainder union and makes no squarefreeness inference.

## Actual work and retained-output custody

Source and input were frozen and banked before the one constructor execution. Its complete data were banked before the first reader. Each reader response was individually banked, and the aggregate packet includes all 34 requests and responses, six inverse-rank results and final counters. There were no failures, missing ephemeral outputs or corrective reruns.

| Constructor counter | Count |
| --- | ---: |
| Prime-square products, including stopping sentinel | 1,394 |
| Initial candidate intervals | 28 |
| Merged integer positions | 131,056 |
| Prime-square multiple visits | 59,242 |
| First obstruction assignments | 51,392 |
| Representation candidate lookups | 114,688 |
| Segment-search steps | 413,696 |
| Accepted pairs | 91,257 |
| Prefix additions | 4,096 |
| Old basis constructions / primality tests | 0 / 0 |

| Reader counter | Count |
| --- | ---: |
| Public queries | 34 |
| Number rows loaded | 4,096 |
| Obstruction positions loaded | 131,056 |
| Condition row scans | 28,672 |
| Conditions created / cache hits | 7 / 17 |
| Rank-search steps | 178 |
| Exponent-bit visits | 4,113 |
| Segment-search steps | 371 |
| Saved-square lookups | 26 |
| Witness divisions / remainder checks | 26 / 26 |
| Returned representation records | 10 |
| Returned number records | 142 |
| Sieve visits / prime-square products | 0 / 0 |
| Old basis construction / primality tests | 0 / 0 |

Counters report named algorithm operations, not every allocation, addition, serialization step or elapsed duration. No timing or asymptotic improvement claim is made.

## Files and immutable identities

| File | Purpose | Git blob |
| --- | --- | --- |
| `squarefree_representations.cjs` | Constructor and saved reader | `f2758c887c58c7183623074d8c882ac389d21f4c` |
| `odd_window_2pow27_index.json` | Complete snapshot | `5233867b10bad17b0997e514e682ad913bb4cbc7` |
| `saved_reader_queries.json` | All 34 queries and work records | `fc59b8f91017973da3c21eed49c2d8e0efc482f9` |
| `SQUAREFREE_REPRESENTATIONS_API.md` | This guide | Bound by publication receipt |
| `README.md` | Entry point | Bound by publication receipt |

The index is 384,042 bytes and the reader packet is 130,052 bytes, both compact JSON with one terminal newline. Git identities bind bytes; correctness still depends on the stated input premises and mathematics.

This finite all-representation and rejection interface adds navigation for the declared window. It does not provide a new existence verification range or a solution to the infinite question.
