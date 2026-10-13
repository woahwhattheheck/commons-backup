# Catalan translated-tail union

This package gives exact ordered navigation in the restricted family
`U(P) = {p + 1 + C_j : p in P, j >= 0}`,
where P is a subpalette of the supplied odd primes
`{3,5,7,11,13,17,19}`. The Fibonacci value is fixed at 1, with the two declared index aliases F1=F2=1. This is a subfamily of the prime–Fibonacci–Catalan representations in PPL013.

The constructor retains a complete collision prefix and proves that every later Catalan block is disjoint and numerically ordered. It supports arbitrary exact symbolic rank/select without expanding the selected Catalan number. Separate decimal queries use a bounded append-only Catalan cache and report their new recurrence work.

This is not a full PPL013 verifier. Absence from this family is not a counterexample to the conjecture, since other primes and Fibonacci values are excluded. No known verification interval, source example, prior Fibonacci recurrence, primality computation or old triangular collision construction was replayed.

## Attribution and exact input

The PPL013 card https://prizeproblems.org/problems/013/ links Zhi-Wei Sun, *Mixed sums of primes and other terms*, https://arxiv.org/abs/0901.3075 , v3 revised 29 January 2009. Conjecture 1.13 on printed pages 4–5 credits Qing-Hu Hou and Jiang Zeng with the January 2009 question: every integer n>4 is an odd prime plus a positive Fibonacci number plus a Catalan number. The target n is not restricted to odd.

The paper explicitly gives F1=F2=1 and defines
`C_j = binom(2j,j)/(j+1)`, j>=0. This yields C0=C1=1. The conjecture concerns existence of values; it does not prescribe counting multiplicities for equal-valued indices. Our API therefore reports both distinct value representations and separately declared index-labelled representations.

The seven prime constants are copied from the retained input of Commons #31958:
`research/ppl120_triangular_union/input.json`, blob
`f4d60a782b3d7ab8d6c6b456b22060e51cf4af3e`, at merge
`24f8a500dab33d636e2e4df644038f5063cec536`.
Only its double_triangular.offsets list is used as the prime premise. No old result or sequence was reconstructed. Primality is an input premise; the source checks an ascending odd palette, not primality.

Only the literal Fibonacci value 1 and indices {1,2} are used. No missing old Fibonacci prefix was reconstructed. Protected PPL072, PPL094 and PPL120 scopes remain separate. SOURCE_QUALIFICATION.md records the bounded source/current-carrier checks and held-route boundaries.

## Why a finite prefix suffices

Taking the ratio of successive Catalan binomial formulas gives
`C_(j+1) = 2*(2j+1)*C_j/(j+2)`.
The constructor uses exact integer division and records each numerator, denominator and resulting value.

Let offsets be a=p+1, and let D=max(a)-min(a). Here D=16.
For j>=1 the recurrence ratio is at least 2, so C_(j+1)>=2C_j.
Consequently the positive gaps grow strictly:
`C_(j+1)-C_j >= C_j > C_j-C_(j-1)`.
Once a gap is larger than D, every later gap is larger too.

Choose the first J>=1 with C_(J+1)-C_J>D and put K=J+1.
Every prefix target is at most C_J+max(a), while the first tail target is at least C_K+min(a). Their difference is strictly positive. The same inequality separates consecutive tail blocks. Thus all prefix targets precede every tail block, and the blocks
`{C_j+a : a selected}, j>=K`
are disjoint and ordered by j. Within a block, ascending selected offsets give numeric order. A subset of the prime palette can reuse the same J because its offset spread is no greater.

The duplicate Catalan value 1 has canonical index 0 with alias set {0,1}. The canonical prefix indices are therefore 0,2,...,J. Every target collision among these finite contributions is grouped before counting distinct integers.

## Actual once-only construction

The new construction calculated C0 through C5 and stopped at J=4, K=5:

| Quantity | Actual result |
| --- | ---: |
| Offset spread | 16 |
| New Catalan recurrence steps | 5 |
| Canonical prefix indices | 0,2,3,4 |
| Prime/value prefix contributions | 28 |
| Distinct prefix target integers | 23 |
| Index-labelled prefix representations | 70 |
| Prefix targets with more than one value representation | 5 |
| Largest prefix value multiplicity | 2 |
| Largest prefix target | 34 |
| Smallest first-tail target | 46 |
| Full-palette width of each tail block | 7 |

The complete certificate is `certificate.json`, 1,972 UTF-8 bytes, Git blob
`5a25a7b08e1211c61881fcf69569a57c58ae1425`.
It retains the input, offsets, spread, cutoff, all six Catalan values, all five recurrence steps, the canonical prefix indices, all prefix fibers, summary and work counters. Prefix fibers have shape `[decimalTarget, [[primeIndex,canonicalCatalanIndex],...]]`.

Each contribution at canonical Catalan index 0 has 2 Fibonacci aliases times 2 Catalan aliases, hence four index-labelled representations. Every other contribution has two Fibonacci aliases and one Catalan index. Contributions from different primes or Catalan values are distinct value representations even if their target sum agrees. Target-union counts collapse all such collisions and all index aliases.

These finite prefix counts are new input-specific outputs, not claims about the unrestricted conjecture or novelty.

## Exact numeric order without decimal expansion

For a selected prime mask, let h be its number of distinct prefix targets and m its number of selected offsets. If m=0 the union is empty.

For a zero-based rank r<h, select the r-th sorted prefix fiber.
For r>=h, use the exact quotient and remainder
`r-h = m*q + b`.
The answer is the symbolic integer
`C_(K+q) + selectedOffset[b]`.

This is an exact numeric-order selection because of the block separation proof. It is not merely ordering expression strings. The result is a structured expression with its exact Catalan index, offset, prime and aliases. Its `value` field is null until explicitly materialized. Selecting rank 10^100 does not compute or print that Catalan number.

Conversely, a selected tail contribution at index j>=K and offset position b has rank
`h + (j-K)*m + b`.
For prefix contributions the complete grouped fiber supplies the shared rank. In particular, Catalan indices 0 and 1 give the same target and union rank. Selecting a prefix collision returns a canonical contribution for inverse lookup together with every contributing value representation.

These formulas use BigInt ranks and indices. Arithmetic costs depend on integer digit lengths; no constant-time or performance claim is made.

## Decimal thresholds and cache work

The saved prefix contains C0 through C5. The reader's Catalan cache starts from these exact values and appends only missing successors. It never recalculates the constructor prefix or an already cached successor.

For an inclusive integer threshold X, binary search first counts admitted prefix targets. For the tail, locate the largest j whose smallest selected offset satisfies C_j+min(a)<=X. Every earlier tail block is fully admitted; the last block may be only partly admitted. Add its offsets individually. This handles equality at endpoints and the gaps between blocks.

Threshold queries extend the cache until one Catalan value brackets X above, then use binary search. Materialization extends only to the requested index. The configured materialization budget is a resource boundary: this actual reader used maxEvaluatedIndex=2048. Decimal requests that require a higher index raise an error; they do not prove nonmembership or return an approximate answer. A request that reaches the budget while extending may leave valid new cache entries, so callers preserving a failed operation should retain caches and work before closing it.

Symbolic rank/select has no such evaluation-index requirement. It can represent arbitrarily large nonnegative BigInt indices without claiming their decimal expansion was generated.

## API

```javascript
const fs = require("node:fs");
const {createReader} = require("./catalan_tail_union.cjs");
const saved = JSON.parse(fs.readFileSync("./certificate.json","utf8"));
const r = createReader(saved, {maxEvaluatedIndex:2048});
const symbolic = r.select(127, "1" + "0".repeat(100));
const a = symbolic.target.canonical;
const inverse = r.rankSymbolic(127, a.primeIndex, a.catalanIndex);
```

This is usage guidance, not an additional execution or replay. The bit positions of a mask correspond to the input prime list in ascending order; valid masks are integers 0..127. Query values accept BigInt, safe integer numbers or canonical signed decimal strings.

| Method | Meaning |
| --- | --- |
| summary() | Saved construction summary, cutoff and evaluation budget |
| condition(mask) | Selected primes/offsets, distinct prefix count, index multiplicity and tail width |
| prefix(mask) | All grouped prefix fibers, value/index multiplicities and aliases |
| select(mask,rank) | Exact numeric-order target as a decimal prefix value or symbolic tail expression |
| rankSymbolic(mask,primeIndex,j) | Shared union rank of a valid contribution, with complete prefix fiber if applicable |
| materialize(mask,rank) | Exact decimal selected target, subject to the evaluation budget |
| countLeq(mask,X) | Number of distinct represented integers <=X |
| countWindow(mask,L,R) | Inclusive count; reversed endpoints return zero |
| fiberValue(mask,n) | Complete prefix fiber or unique tail value representation; null for absent target |
| catalan(index) | Explicit decimal Catalan query, using the same cache and budget |
| work(), caches() | Current counters, all selected prefix conditions, full Catalan cache and extension records |

The valid-mask contract applies to all methods. The reversed-window shortcut returns zero before building a condition. Empty palettes have zero counts and no selectable ranks. Every nonempty palette has an infinite tail. Absent targets and resource-budget exceptions are separate outcomes.

The reader checks the schema tag and query contracts but trusts the identified certificate; it is not an adversarial mathematical verifier. Its source can construct other declared odd palettes within its stated bounds, but only this seven-prime instance was produced here.

## Actual reader evidence

The banked plan used masks 127,1,2,3,5,42,85,0. Their distinct prefix counts were respectively 23,4,4,8,7,11,14,0. Their index-labelled prefix multiplicities were 70,10,10,20,20,30,40,0.

All **231 responses** are retained in `saved_reader.json`, including **77 matching inverse ranks**, two matching canonical-index alias comparisons and eight complete palette conditions. The complete reader is 742,808 UTF-8 bytes, Git blob
`330e749030cab6ae8365cf50270de19871b89b43`.
No reader call failed or lost its response.

For every nonempty palette the actual plan included rank 10^100 and its symbolic inverse. Small ranks were also materialized and inverted by decimal fiber lookup. New decimal Catalan queries at indices 16,128,512,1000 and their threshold brackets extended the shared cache through index 1001, adding **996 new recurrence terms**. These are explicitly fresh query calculations, not zero-work reads.

| Threshold | Full palette distinct targets | Mask 42 distinct targets |
| --- | ---: | ---: |
| 10^100 | 1,199 | 515 |
| 10^400 | 4,692 | 2,012 |

Mask 42 selects primes 5,11,17. The empty palette returned zero at both thresholds. These counts cover only the fixed Fibonacci value and selected prime palette.

The reader recorded eight condition builds, 247 hits, 184 saved prefix-fiber reads, 224 saved contribution reads, 369 prefix comparisons, 306 tail comparisons, 128 offset comparisons, 81 symbolic selections, 68 symbolic ranks, 996 new Catalan steps, 29 direct Catalan cache reads and 39 materializations. New prefix contributions, Fibonacci recurrence and primality work were zero. These counters are selected operation counts from this use, not an exhaustive instruction count or benchmark.

## Checkpoint and release custody

The public source/input/plan was acknowledged as native Git blobs before construction, with the exact prime-input lineage. The full certificate was acknowledged before any reader, and the reader plan before its first call. Every request and response plus current caches/work was retained; the complete reader was then acknowledged. No old accepted computation or proof was rerun as a check.

`public_checkpoints.json` holds the public manifest chain and acknowledged artifact identities, without private provider or Slack raw. Native acknowledgement is distinguished from a computed-only identity and does not promise indefinite Git retention. The frozen full publication specification is separately checkpointed before its guarded writer, with its locator in the release receipt to avoid circular content identities.

All complete immutable source files must match prepared bytes and provider/independent Git identities. A main alias is allowed only on an independently observed equality to the same verified merge; otherwise complete observed-main content reads are required.
