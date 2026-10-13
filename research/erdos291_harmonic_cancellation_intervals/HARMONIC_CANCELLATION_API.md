# Finite harmonic-denominator cancellation intervals

This index represents every positive integer n through **10^80** using a complete partition into **1,589 intervals**, each with a constant set of cancellation witnesses among the seven supplied odd primes **3, 5, 7, 11, 13, 17, 19**. It does not enumerate the integers, construct enormous harmonic numerators or least common multiples, or claim to classify cancellation at unlisted primes.

The number with at least one selected-prime cancellation witness is
`50499451073774740305783837728113361536301219700112965548252753979282108037745695`.
The remaining
`49500548926225259694216162271886638463698780299887034451747246020717891962254305`
have no witness from this palette and remain **unresolved for other primes**. These two counts sum to 10^80. They are finite-window counts, not densities or estimates of a limiting frequency.

## Definitions and source attribution

Write H_n = Σ_{j=1}^n 1/j = c_n/d_n in lowest terms, D_n = lcm(1,…,n), and q_n = D_n/d_n. Peter Shiu, *The denominators of harmonic numbers*, [arXiv:1607.02863v2](https://arxiv.org/html/1607.02863v2), revised 30 July 2024 (original 2016), uses these definitions. For an **odd** prime p, he defines E_p by 1<m<p and p dividing the reduced numerator c_m. His Theorem 2 states that p divides q_n exactly when m·p^a ≤ n < (m+1)·p^a for some m∈E_p and a≥1. The introduction also treats the absence of 2-cancellation separately.

This is a directly read theorem statement and definition, not a proof audit. No numerical table or example was imported. The fixed seven-prime specialization and saved interval-navigation implementation are this package's construction, not an attributed new theorem of Shiu. The odd-prime restriction is retained.

The complete [FormalConjectures Erdős 291 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/291.lean) was independently read via the contents API without an explicit ref. The observed UTF-8 identity is `0a4dfff252bc2c4f87424531474f87c23132884d` (4,741 bytes). It uses L_n=D_n and the unreduced integer a_n = L_n H_n. Since d_n divides L_n and gcd(c_n,d_n)=1, elementary reduction gives gcd(a_n,L_n)=L_n/d_n=q_n. Thus this guide's cancellation witnesses refer to exactly that gcd. Shiu's c_n must not be confused with the unreduced a_n.

That formal source separately annotates the infinitely-many-coprime-n question, Shiu's order-of-growth heuristic and density-zero question as research open; it annotates the complementary infinitude, leading-digit criterion and a conditional Wu–Yan assertion as solved, with local placeholders. The file was read for statement and annotation custody, not to execute its examples or verify proof claims. No current exhaustive literature assessment is inferred. This finite index establishes neither infinitude nor any asymptotic heuristic and makes no prize or priority claim.

The domain here is n≥1. No n=0 harmonic, logarithm or LCM convention is imported.

## Exact new input and inherited premise

The supplied prime values are copied literally from indices 1 through 7 of the zero-based `primes` array in the released [#31726](https://github.com/woahwhattheheck/commons/pull/31726) input:
- Immutable merge: `e04374c3650c68ff5ed22c8997f6805eb5b31c85`.
- Path: `research/erdos238_consecutive_prime_blocks/prime_prefix1900_blocks.json`.
- Git blob: `0224dfb74525d7d18b6e5aba20f01e1784a0c8f2`.
- The full accepted array has 1,900 primes from 2 through 16,381; only the seven indicated values are consumed here.

Their primality is an identified input premise. No old sieve, least-factor data, consecutive-gap computation, order statistic or proof is replayed. No standalone primality test is run; modular inversion still performs its stated gcd/unit checks as part of this new calculation.

The new input was frozen before production as 1089 bytes with blob `0baf7cf5b15b09d2bbb4518dc2963d6f7c0e9075`:
```json
{
  "primes": [
    3,
    5,
    7,
    11,
    13,
    17,
    19
  ],
  "upper": "100000000000000000000000000000000000000000000000000000000000000000000000000000000",
  "limits": {
    "max_primes": 16,
    "max_prime": 97,
    "max_decimal_exponent": 200,
    "max_intervals": 20000,
    "max_events": 40002
  },
  "provenance": {
    "prime_input": {
      "pr": 31726,
      "merge": "e04374c3650c68ff5ed22c8997f6805eb5b31c85",
      "path": "research/erdos238_consecutive_prime_blocks/prime_prefix1900_blocks.json",
      "blob": "0224dfb74525d7d18b6e5aba20f01e1784a0c8f2",
      "field": "primes",
      "zero_based_indices": [
        1,
        2,
        3,
        4,
        5,
        6,
        7
      ]
    },
    "formal_blob": "0a4dfff252bc2c4f87424531474f87c23132884d",
    "primary": "https://arxiv.org/html/1607.02863v2",
    "theorem": "Shiu Theorem 2, odd-prime leading-digit intervals, directly read statement; proof and numerical table not inspected.",
    "scope": "Positive finite n domain; selected-prime cancellation only; zero mask remains unresolved."
  }
}
```

## New modular tables

For each supplied odd prime p, the constructor computes every modular inverse of k=1,…,p−1 by the extended Euclidean algorithm. It retains the inverse, the exact integer multiple (k·inverse−1)/p and the running harmonic residue Σ_{j=1}^k j^−1 mod p.

Because k<p, the ordinary reduced denominator of H_k is a unit modulo p. Therefore a zero running residue is equivalent to p dividing its reduced numerator. This is the elementary bridge from the finite modular computation to Shiu's E_p definition.

The actual newly computed zero-digit sets are:
| p | E_p |
|---:|---|
| 3 | {2} |
| 5 | {4} |
| 7 | {6} |
| 11 | {3,7,10} |
| 13 | {12} |
| 17 | {16} |
| 19 | {18} |

All 68 inverse and running-residue rows are retained. These rows were computed once for this new consumer; no source table supplied them.

## Interval compilation and exact partition

For every m in the saved E_p and every exponent a≥1 whose interval can meet [1,U], U=10^80, the compiler creates
`[m·p^a, min(U,(m+1)·p^a−1)]`.
Every record retains p, the palette index, m, a, the exact power p^a, both inclusive endpoints and whether the upper endpoint was clipped. Exponent zero is excluded: the theorem requires p≤n and a≥1.

For each prime, the power table starts at 1 and includes the first power greater than U as a boundary sentinel. No logarithm or floating-point approximation selects exponents.

An interval adds its ID at its lower endpoint and removes it at upper endpoint plus one. Synthetic positions 1 and U+1 bound the domain. Equal positions are combined before the sweep. At each event, removals precede additions; the source requires at most one active interval for each prime. Every interval between consecutive event positions inherits the current mask and active interval IDs.

The output is a complete, disjoint partition of [1,U]. It consists of event cells, not a claim that adjacent equal masks were merged into maximal mask intervals. Retaining active interval IDs lets a later witness name its precise power/digit record. The mask groups store segment IDs in numeric order with complete length-prefix arrays. Mask 0 means no selected-prime witness, not gcd(a_n,L_n)=1.

Actual new construction:
| Operation or record | Count |
|---|---:|
| Modular inverses | 68 |
| Euclidean divisions | 252 |
| Harmonic residue updates | 68 |
| Power multiplications, including sentinels | 656 |
| Obstruction intervals | 795 |
| Interval endpoint updates | 1,590 |
| Distinct event positions | 1,590 |
| Event sort comparisons | 5,981 |
| Segments / group-prefix additions | 1,589 / 1,589 |
| Distinct observed masks | 58 |
| New prime sieve / standalone primality tests | 0 / 0 |
| Enumerated integers / full harmonic or LCM values | 0 / 0 |

The actual power-array lengths, including 1 and the sentinel, are 169, 116, 96, 78, 73, 67 and 64 in palette order. The compiler ran once. No cap failure or missing output occurred.

## Constructor bounds

`compile(input)` requires 1–16 distinct increasing odd prime premises, each at most 97, and a canonical decimal endpoint from 1 through 10^200. These checks occur before modular or interval construction. The explicit record caps are 20,000 intervals and 40,002 event positions. A composite premise exposing a nonunit during inversion throws. The constructor does not silently label a failed or capped prefix as a complete index.

All endpoint arithmetic is BigInt. Residues, masks and small Euclidean inputs fit the stated exact safe-integer limits. Each selected interval's width and every aggregate count are decimal BigInt strings. No approximate logarithmic endpoint arithmetic is used.

## Saved format and complete shards

The constructor's full serialized snapshot has blob `76c7ba573ab188594894e79442d1968100803110`, 1044937 bytes. For transport, its segment array is split into four complete shards. The manifest retains the full modular tables, all interval records, all events, mask-group prefix arrays, totals, provenance and work; only its snapshot `segments` field is null.

| Segment shard | IDs | Git blob |
|---|---|---|
| segments_00.json | 0–399 | dabc621276edc6b8f74b72af76f65cde112008bd |
| segments_01.json | 400–799 | e21dc08bedd98d89b6d44dc34d3571e6d33fd726 |
| segments_02.json | 800–1199 | f1fef05e8b6cd75a9b3fec7d7a1fce807abf3374 |
| segments_03.json | 1200–1588 | 62675269fe0173f966eedbaf7ad589c97284ab19 |

Concatenating those arrays and replacing the manifest's null field yields the exact complete original serialization. That assembly was compared byte-for-byte and independently blob-identified. It is not interval construction, arithmetic replay or a second theorem check.

```js
const fs = require("node:fs");
const { openIndex } = require("./harmonic_cancellation_intervals.cjs");
const read = name => JSON.parse(fs.readFileSync(name, "utf8"));
const manifest = read("snapshot_manifest.json");
const segments = manifest.segment_shards
  .flatMap(row => read(row.path).segments);
const snapshot = { ...manifest.snapshot, segments };
const reader = openIndex(snapshot);
reader.query({ op: "family", condition: { any: snapshot.primes } });
reader.query({ op: "witness", n: snapshot.upper });
```

Opening copies/parses saved records and checks the partition shape, continuity, segment IDs, lengths and endpoints. Those structural checks do not rederive modular inverses, powers, interval endpoints, events or group prefixes, and do not certify arbitrary untrusted mathematical premises.

## Saved reader operations

The reader uses increasing **numeric n order**, with zero-based ranks. This differs from coordinate or digit order. All public large n, rank and count fields are canonical nonnegative decimal strings; n itself must lie in [1,U].

Conditions have optional prime lists `require`, `forbid` and `any`. Every required prime must witness cancellation, no forbidden prime may do so, and at least one `any` prime must do so when that list is nonempty. An empty `any` list imposes no requirement. All entries must belong to the declared palette; duplicate entries and require/forbid overlap are rejected. Masks concern exactly this palette.

| Operation | Contract |
|---|---|
| summary | Domain, construction totals and work. |
| prime | Complete saved modular and power table for one palette prime. |
| interval, segment | Complete record by bounded saved ID. |
| group | Saved segment IDs and complete prefix array for one mask; absent masks return zero. |
| family | Exact count and number of matching segments for a condition. |
| select | Numeric zero-based rank to n, mask and prime witnesses. |
| rank | n to member status and numeric rank under the condition. |
| window | Exact inclusive count between two in-domain ordered endpoints. |
| page | Up to 128 consecutive selected n values, with next cursor. |
| classify | Saved segment/mask and selected-prime status for one n. |
| witness | Precise saved obstruction interval and modular residue, plus one fresh leading-digit quotient, for an active selected prime. |
| conditions | Summaries of all cached conditions. |

A fresh condition scans the saved segments and constructs only its conditional length-prefix array. At most 32 conditions are cached. Selection and rank use binary search; interval records and power tables are never rebuilt. A failed witness query reports absence of a selected-prime certificate and does not certify coprimality.

## Actual reader evidence

All **45 new reader responses** were banked individually and are retained in `saved_reader_queries.json`. They include:
- 12 full condition summaries, including each selected prime separately and the simultaneous-all-seven condition, which has zero members in this finite window;
- six exact select/rank inverse matches, at first, middle and last ranks of both the screened and unresolved families;
- six exact window counts and two twelve-value numeric pages;
- explicit cancellation witnesses and an unresolved witness response;
- selected complete saved prime, interval, segment and group records.

For [1,1000], the saved queries count 743 selected-prime cancellations and 257 unresolved values. For the inclusive final window [10^80−1000,10^80], all 1,001 values have a selected witness. These are queries on the one compiled index, not a direct verification of an earlier numerical frontier.

At n=10^80, the retained witness uses p=3, exponent 167 and leading digit 2. Its saved interval begins at
`95560746531118716018384891544079288513588277158888376726675291951451666121649174`
and is clipped at 10^80. The immediately preceding integer is the last unresolved value for this seven-prime palette; neither statement assigns it a full harmonic gcd.

The reader performed 19,068 saved-segment scans, 5,201 conditional prefix additions, 466 binary-search steps, 30 selected-offset calculations, six rank-offset calculations, six window subtractions, two witness quotients and four interval reads. It reports 12 conditions and 21 condition-cache hits. Modular inverses, harmonic residues, powers, intervals, events and base-partition construction all have fresh-reader count zero.

Query-input arithmetic is separately disclosed: the final-window lower endpoint uses one subtraction; the half-window lower endpoint uses one integer division; two middle ranks and two final ranks use two divisions and two subtractions of already saved family counts. No hidden harmonic or prime computation is involved.

## Limitations and identities

Finite-palette cancellation is a sufficient certificate of gcd(a_n,L_n)>1. Mask zero only excludes those seven primes. The compiler does not compute the full gcd, the exact reduced denominator, or its complete prime factorization at a queried n. It supplies no upper/lower density theorem or decision about infinitely many fully coprime harmonic denominators.

Production source: `150e266fb56214d7e3c755aec27201344cda4820` (11010 bytes).
Full snapshot before transport splitting: `76c7ba573ab188594894e79442d1968100803110`.
Complete reader responses: `110b3525b69106a257055a19593c25584a50c16f` (43526 bytes).

All new source, input, complete result, shard assembly and reader outputs were banked before guarded publication. The source statement, inherited prime premise, new finite computation and later query arithmetic are kept distinct.
