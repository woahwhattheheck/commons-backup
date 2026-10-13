# Common factor-difference index for a fixed positive host

This package indexes the complete factor-difference sets of thirteen identified positive integers and their intersections over all 8,191 nonempty host subsets. Its actual result is negative for shared differences: **the thirteen sets are pairwise disjoint**. They contain 4,994 factor pairs and exactly 4,994 distinct differences in total. All 8,178 subsets of size at least two therefore have empty intersection.

The complete negative result is retained without enlarging the host to seek a positive example. It is separate from the known small-k constructions and from the unrestricted Erdős question.

## Definition, sources and protected prior work

For positive N, define

```text
D(N) = { |a-b| : a,b are positive integers and a*b=N }.
```

The complete actually read [FormalConjectures/ErdosProblems/885.lean](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/885.lean) has Git blob
`3698f515b8cb7a6fa3add4bea43447c86bf630c2` (5,418 bytes). The provider request used the default branch, with no immutable commit ref. This is a content identity, not a claimed commit pin. Its natural-number factor definition agrees with positive factors when N≥1. It asks whether for every k≥1 some set of k distinct positive N has at least k common differences.

The main theorem is annotated research open with a local placeholder. Separate k=2 and k=3 results are annotated solved; k=4 includes a known explicit example and proof in the file. Those known results are source context only. Their numerical example, proof calculations and prior construction were not evaluated, imported, reproduced or used as this input.

Andrew Bremner, [“On a problem of Erdös related to common factor differences”](https://experts.azregents.edu/en/publications/on-a-problem-of-erd%C3%B6s-related-to-common-factor-differences/), *International Journal of Number Theory* 15(5) (2019), 1059–1068, DOI 10.1142/S1793042119500581, defines D(n) in the institutional author abstract as a set of absolute differences of the integer factors. Only that definition and bibliographic metadata were read, not a proof, table or example.

Swapping factors therefore does not add a new difference. Equal factors are not excluded, so difference zero occurs exactly for square N. For positive N, allowing two negative factors gives the same absolute difference as their positive magnitudes. These are direct interpretations of the definition, not additional theorems attributed to the abstract.

The original Erdős–Rosenfeld paper locator
`https://matwbn.icm.edu.pl/ksiazki/aa/aa79/aa7944.pdf`
returned 403 once and remains held. No retry or alternative copy was used. The separate Bremner paper supplied the sufficient definition. Current formal annotations and historical attribution are not a proof review or a claim about platform awards.

## Exact new input lineage

The input is `input_hosts.json`, Git blob
`a418838836a9cb6a62ef8b04df479df4728d95bc` (7,086 bytes). It imports the thirteen complete sparse factor lists in query 4 of the released [E1094 reader packet, PR #31789](https://github.com/woahwhattheheck/commons/pull/31789), merge
`8f7f9ec9393a19d18789d72b23882f7f4657c5b7`, path
`research/erdos1094_binomial_valuation_index/saved_reader_queries.json`,
blob `68df33768328c1c26d14169eb7f113bb4d8311ee`.

The same packet's query 55 already supplied the integer C(241,16). That value is copied and reused. The other twelve full integer products had not been requested there and are materialized once from the saved factors in this new construction. No binomial valuation, factorial table, prime test, sieve or generic factorization is repeated.

The resulting distinct hosts, in increasing numerical order, are:

| Host bit | N | Source binomial pair | Factor pairs |
| ---: | ---: | --- | ---: |
| 0 | 35 | (7, 3) | 2 |
| 1 | 715 | (13, 4) | 4 |
| 2 | 1001 | (14, 4) | 4 |
| 3 | 33649 | (23, 5) | 8 |
| 4 | 61474519 | (62, 6) | 16 |
| 5 | 177232627 | (44, 8) | 32 |
| 6 | 4076350421 | (46, 10) | 64 |
| 7 | 5178066751 | (47, 10) | 64 |
| 8 | 17417133617 | (47, 11) | 64 |
| 9 | 718406958841 | (74, 10) | 128 |
| 10 | 9041256841903 | (94, 10) | 256 |
| 11 | 10104934117421 | (95, 10) | 256 |
| 12 | 3720625555021727122496771 | (241, 16) | 4096 |

This input has no duplicate numerical host values. The generic constructor merges equal host values with their source lineage rather than counting them as distinct N; conflicting supplied factor lists for an equal value are rejected. Complete prime factorizations and the known integer are inherited premises. This module does not recheck their primality, correctness or the previously computed integer product.

## Complete factor and support construction

For each host N, the constructor computes floor(sqrt(N)) by exact integer Newton iteration. It enumerates every divisor a no larger than that bound using the supplied prime-power choices. Before advancing a partial divisor by a prime p, it checks the quotient bound; products outside the square-root bound are not formed. Thus a known complete host value N>1 is never recreated as a divisor product.

Every small divisor yields exactly one unordered factorization (a,N/a). The partner quotient and difference N/a−a are new arithmetic. Since all positive divisors arise from the complete prime-power choices, this enumerates all unordered factorizations. Taking a≤sqrt(N) avoids the swapped duplicate and includes a=b for a square.

For fixed N, the difference N/a−a strictly decreases as the positive small divisor a increases. Hence two distinct retained factor pairs cannot create the same difference. The constructor nevertheless treats each difference as a set value and rejects a duplicate within one host.

A global difference record stores its exact decimal value, its host-support mask and the host/pair references providing witnesses. A difference belongs to the intersection for host mask M exactly when its support mask contains M.

Let f(S) count differences whose support is exactly S. The common-difference count for nonempty M is the sum of f(S) over S containing M. A standard finite superset zeta recurrence computes all these sums by adding one bit at a time. The source retains the exact support histogram, all nonempty-subset counts, subset sizes and size/count profiles.

The empty host subset is excluded from the public subset API. Its unrestricted intersection would be all natural-number differences, an infinite set. The zeta value at zero is only the finite union size; it is stored separately as `union_difference_count`, and `common_counts[0]` is set to null. It is not presented as the cardinality of an empty intersection.

## Actual finite result

All 4,994 difference records have a single-host support in this input. Consequently:

| Family | Count |
| --- | ---: |
| Distinct positive hosts | 13 |
| Unordered factor pairs / distinct differences | 4,994 / 4,994 |
| Nonempty host subsets | 8,191 |
| Singletons with a nonempty difference set | 13 |
| Host subsets of size at least two | 8,178 |
| Host pairs | 78 |
| Host pairs sharing any difference | 0 |
| Subsets with common count at least subset size | 13 |

The largest singleton set is the 4,096-element D(C(241,16)). Every maximum common count for a host-subset size of two or more is zero. The complete 21 size/count profile rows, all subset counts and every factor witness are retained.

The saved reader's first shared difference for the largest singleton is 1285344254, witnessed by factors 1928249747903 and 1929535092157 of N=3720625555021727122496771. Those exact strings come from the banked new factor enumeration; no multiplication or subtraction is repeated by that reader query.

This family neither supplies nor contradicts the known positive constructions on other integers. The global question chooses its host freely; the present input is fixed by its stated lineage.

## Snapshot files and byte assembly

The full compact snapshot is 1,072,533 bytes, Git blob
`6ed9af2f0fed4f22e6c891a7a38a0a9691d607f7`.
It is stored through `host13_manifest.json`, two complete host-pair shards and `differences.json`.

The manifest retains all other snapshot fields. Its nested host `pairs` fields and top-level `differences` field are null placeholders. Insert the complete saved arrays from the listed files, preserving existing property order. `JSON.stringify(snapshot) + "\n"` reproduces the original bytes. This exact assembly was checked once as serialization identity only; no square root, divisor enumeration, difference, support or zeta recurrence was run.

```javascript
const fs = require("node:fs");
const { open } = require("./common_factor_difference_index.cjs");
const manifest = JSON.parse(fs.readFileSync("./host13_manifest.json", "utf8"));
const pairMap = new Map(manifest.pair_shards.flatMap(({file}) =>
  JSON.parse(fs.readFileSync(file, "utf8")).hosts
).map(h => [h.index, h.pairs]));
const snapshot = Object.assign({}, manifest.snapshot, {
  hosts: manifest.snapshot.hosts.map((h,i) =>
    Object.assign({}, h, {pairs: pairMap.get(i)})),
  differences: JSON.parse(fs.readFileSync(manifest.difference_file.file, "utf8")).differences
});
const api = open(snapshot);
const family = api.family({min_size: 2, min_common: 1});
```

This loading example is documentation, not a repeated execution. The module exports `SCHEMA`, `construct(input)` and `open(snapshot)`. For this published input, load the saved snapshot rather than reconstructing it mathematically.

## API and order

Host bits follow the increasing numerical N table above. Subset ranks are zero-based in **increasing numerical host-mask order**, preserved under filtering. This is a bit-mask order, not lexicographic order of lists of host values. Decimal strings are used for ranks, N, factors and differences; masks and host indices are bounded ordinary integers.

| Method | Meaning |
| --- | --- |
| `summary()` | Complete profile counts, maxima, qualifying counts and construction work |
| `hosts()` | Host values, factor premises and source lineage without the full pair arrays |
| `hostPage(index,start,limit)` | Up to 200 saved unordered factor pairs, sorted by smaller factor |
| `subset(mask)` | Host list, saved size, common count and comparison with size |
| `family(options)` | Count a condition over all nonempty masks |
| `select(rank,options)` | Select one conditional host subset |
| `rank(mask,options)` | Membership and rank, or a nonmember result |
| `page(start,limit,options)` | Up to 200 conditional subsets |
| `sharedPage(mask,start,limit)` | Shared differences in increasing numerical difference order, with witnesses |
| `difference(d)` | Global support and every saved witness for one difference |
| `witness(mask,d)` | Saved witnesses if d is common, otherwise missing host bits |
| `caches()` | Complete family and shared-filter caches from the reader instance |
| `work()` | Cumulative named-operation counters |

Family options are `min_size`, `max_size`, `min_common`, `max_common`, `required_mask`, `forbidden_mask`, and optional Boolean `qualifies`. The last means common count at least subset size. Contradictory bounds or overlapping required/forbidden bits are rejected. Mask zero is not a valid selected subset, although required/forbidden masks may be zero.

A family condition scans saved subset counts and saves every accepted mask. Rank and selection then use that ordered list. A shared-difference condition scans the saved support records and saves the matching difference IDs. The latter is fresh query filtering; it does not regenerate factor pairs or recompute the zeta transform. The scan's length is checked against the saved common count.

`open` performs schema and length checks. It does not independently verify the input factorizations, recompute factor witnesses, or prove each saved arithmetic identity. This is saved-data navigation supported by the stated premises and derivation, not an independent proof checker.

Caches are in-memory within one reader instance. Their complete exported records are query evidence; this version has no API for importing them into a fresh `open` instance. New condition compilations must be reported as new work.

## First reader use

All **56** responses are banked in `saved_reader_queries.json`, Git blob
`ac007929b336f7c98ef2ed6197f6647ab8ed4c11` (109,908 bytes). They include every qualifying singleton, 13 singleton inverse ranks, six additional condition inverses and two full-family inverses. All **21** rank comparisons match.

The requests also include first and final factor pages for the largest host, complete small-host pages, positive and empty shared-difference queries, absent difference zero, a positive saved factor witness, a missing-host witness and a deliberate nonmember rank. They do not export every large-host pair through the reader because the complete factor arrays are already published in the snapshot.

Nine family caches retain 26,699 masks. Four shared filters retain 4,098 difference IDs. Their full packet is `saved_condition_caches.json`, blob
`179b7bca5abb45acf7eea5baffd5435b6a3321c6` (493,882 bytes).

| Reader counter | Value |
| --- | ---: |
| Queries | 56 |
| Family conditions / cache hits | 9 / 31 |
| Saved subset scans | 73,719 |
| Conditional masks | 26,699 |
| Rank binary-search probes | 126 |
| Subset host-bit checks | 572 |
| Shared conditions / cache hits | 4 / 1 |
| Saved support rows scanned | 19,976 |
| Shared difference IDs retained | 4,098 |
| Difference binary-search probes | 51 |
| Witness occurrence checks | 14 |
| Saved factor-pair lookups | 30 |

Request preparation additionally records six BigInt midpoint divisions and one BigInt final-rank subtraction. Ordinary array-index, loop and validation operations are not represented as a complete arithmetic-cost census. No query failed and no response was lost.

Constructor calls, new divisors, new differences, new support records, new zeta cells, prime tests and factorizations are all zero in the reader. Its saved-row filtering and navigation are explicitly new work, not described as zero computation.

## Once-only construction and bounds

The executed source is `common_factor_difference_index.cjs`, blob
`16659b1da23b719f3f7ff9b70f9bbdd90a3bebc2` (12,616 bytes). Source and exact input were banked before the one construction; its complete output was banked before the fresh reader. Neither source nor result was recomputed to produce the documentation.

| Construction counter | Value |
| --- | ---: |
| New host integer multiplications | 70 |
| Known host values reused | 1 |
| Duplicate source values merged | 0 |
| Square-root divisions / additions | 50 / 50 |
| Divisor recursion nodes | 12,522 |
| Divisor-bound divisions | 7,528 |
| Bounded divisor products | 4,981 |
| Partner divisions / difference subtractions | 4,994 / 4,994 |
| Factor pairs / support updates | 4,994 / 4,994 |
| Exact-support count additions | 4,994 |
| Superset zeta additions | 53,248 |
| Subset-size / profile-count additions | 8,191 / 8,191 |

There are no primality tests, generic factorizations or binomial-valuation cells. The generic caps are at most 16 input hosts, 100,000 factor pairs, 1,000,000 divisor nodes and 1,000,000 zeta additions. The actual computation completed within all caps. A cap failure does not produce a complete certificate.

The finite negative conclusion is limited to these thirteen hosts. It is not a general obstruction, a resolution of Erdős 885, a replay of a known k=4 construction, a numerical record or a priority, sponsor or prize claim.
