# Exact inverse for a five-factor consecutive window

[window_five_inverse.cjs](window_five_inverse.cjs) locates a natural-number offset for a five-factor consecutive product using one exact fifth root and one possible candidate. It also classifies the ratio-four equation and supplies a bounded scan with complete compact records.

The new connected-runtime input is **1,000,001 through 1,010,000 inclusive**, beginning immediately after the retained Commons #16065 range. It contains **10,000 new offsets and no eligible ratio-four witness**. Every candidate is disjoint and every candidate-minus-target difference is positive. All 10,000 roots and differences are retained in [inverse_interval_1000001_1010000.json](inverse_interval_1000001_1010000.json).

Operation: `ERDOS686-LEN5-INVERSE-API-20261004-7CA6`.

## Sources and finite scope

The [FormalConjectures statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/686.lean) uses natural-number offsets and factors indexed from one through the window length. This API specializes the ratio-four variant to

```text
P(m)=4P(n),  P(x)=(x+1)(x+2)(x+3)(x+4)(x+5),
n>=0,  m>=n+5.
```

Zero is an allowed offset, never a zero factor. Equality in the disjointness condition permits adjacent windows: when `m=n+5`, the lower window ends at `n+5` and the upper begins at `n+6`. Negative zero-product points and modular congruence solutions are outside this contract.

The original question appears on page 78 of [Paul Erdős, Some unconventional problems in number theory, Acta Math. Acad. Sci. Hungar. 33 (1979), 71–80](https://www.renyi.hu/~p_erdos/1979-23.pdf).

Published finiteness credit belongs to F. Beukers, T. N. Shorey and R. Tijdeman, *Irreducibility of polynomials and arithmetic progressions with equal products of terms*, *Number Theory in Progress* (1999), 11–26. [Rakaczki's 2003 paper, Theorem B, p. 340](https://www.impan.pl/shop/en/publication/transaction/download/product/83210), states and attributes this classification. Substituting falling-factorial variables `X=m+5` and `Y=n+5` puts equal degrees five and multiplier four outside its infinite-family exceptions. This gives finitely many rational, hence integer, solutions. The consulted statement supplies no explicit admissible list or usable cutoff here. The source lookup supplied by the delivery lane is consumed in this section.

The inverse operation is a computational tool. This record neither settles all length-five offsets nor resolves the variant allowing arbitrary window lengths. It claims no new finiteness theorem or external computational frontier.

## The inverse bound

Use the existing carrier's centered identity

```text
P(x)=Q(x+3),  Q(t)=t^5-5t^3+4t.
```

For every integer `t>=3`,

```text
(t-1)^5 < Q(t) < t^5.
```

For the upper inequality, `t^5-Q(t)=t*(5t^2-4)>0`. For the lower one,

```text
Q(t)-(t-1)^5
 = 5t^4-15t^3+10t^2-t+1
 = 5t^3*(t-3)+10t^2-t+1
 > 0.
```

The first summand is nonnegative for `t>=3`, and the remaining quadratic is positive there. Therefore, for every natural offset `m`,

```text
(m+2)^5 < P(m) < (m+3)^5.
```

If `P(m)=T`, then necessarily

```text
m = floor(T^(1/5)) - 2.
```

There is only one candidate, and it must still be compared with `T`; not every target is a five-factor window product. The strict bound also excludes a positive perfect fifth power from being such a product.

For a ratio-four query, first compute `T=4P(n)`, obtain the integer root, and compare its candidate product. An equality counts as a problem witness only when the candidate also satisfies `m>=n+5`.

### Exact adjacent product offsets

The same information yields a general locator. Write `R=floor(T^(1/5))`, `c=R-2`, and `D=P(c)-T`, with `T>=120=P(0)`.

If `D>0`, then

```text
P(c-1) < R^5 <= T < P(c).
```

Here `c>=1`, since `P(0)<=T`. Thus the floor and ceiling offsets around `T` are `c-1` and `c`.

If `D<0`, then

```text
P(c) < T < (R+1)^5 < P(c+1),
```

so the offsets are `c` and `c+1`. For `D=0`, both offsets are `c`. Below 120 there is no floor offset, and the ceiling offset is zero. These conclusions use the strict power bounds and the monotonicity of `P`; they do not require a second candidate product.

## Public API

The module exports four functions and a frozen `limits` object. It has no imports, I/O or native-runtime dependency.

| Function | Purpose |
| --- | --- |
| `floorFifthRoot(value)` | Exact floor root with adjacent fifth powers, both gaps and integer-iteration counters. |
| `locateWindowFiveProduct(value)` | The unique possible product offset, membership result, signed difference and exact floor/ceiling product offsets. |
| `classifyLengthFiveRatio(n)` | Classify `P(m)=4P(n)` and the required disjointness for one natural `n`. |
| `createLengthFiveRatioScan({from, through})` | Construct a bounded inclusive scan with `advance`, `describe` and paged `records` methods. |

Natural-number arguments accept BigInts, nonnegative safe integer Numbers, or canonical natural decimal strings. Signs, whitespace, leading zeros, fractions, booleans and unsafe Numbers are rejected. A canonical string is `"0"` or a nonzero leading digit followed by digits.

Mathematical integers in results are decimal strings. Product differences are **signed** decimal strings. Loop counts, page indices, budgets and other bounded control fields are Numbers. They are all within the safe integer range.

### Root certificate

`floorFifthRoot` returns schema `erdos686.fifth_root_bracket/v1`. Its `floor_root=R` satisfies

```text
lower_power = R^5 <= value < (R+1)^5 = upper_power.
lower_gap = value - lower_power >= 0.
upper_gap = upper_power - value > 0.
```

`is_perfect_fifth_power` is true exactly when the lower gap is zero. Value zero is accepted and returns root zero, bracket `[0,1)`, and zero iterations.

For a positive input with bit length `b`, the initial root estimate is `2^ceil(b/5)`, strictly above the real fifth root. The iteration uses only integer arithmetic:

```text
next = floor((4*x + floor(value/x^4))/5).
```

Let `R` be the true floor root. If `x>=R`, the arithmetic-geometric mean inequality gives `4*x + R^5/x^4 >= 5R`; because `value>=R^5` and `5R` is an integer, the rounded update stays at least `R`. If `x>R`, then `value<x^5`, so the update is strictly smaller than `x`. The sequence therefore decreases to `R`; at that point the next update cannot be smaller. The implementation stops on that condition and checks both adjacent fifth-power inequalities before returning a certificate.

The hard iteration cap is an additional resource limit. If exhausted, the function throws instead of returning an uncertified root. Each counted iteration includes two integer divisions: the division by `x^4` and the division by five. The terminal iteration is included.

### Window and ratio classifications

`locateWindowFiveProduct` returns `BELOW_MINIMUM_PRODUCT`, `WINDOW_PRODUCT`, or `NOT_A_WINDOW_PRODUCT`. It includes the full root certificate. Below 120 its candidate, candidate product, signed difference and floor offset are null, while its ceiling offset is `"0"`. Otherwise, it includes the exact candidate, difference, and adjacent product offsets described above.

`classifyLengthFiveRatio` computes the denominator product and multiplier-four target, calls the window inverse, and retains the required minimum `m=n+5`. Its statuses distinguish:

- `ELIGIBLE_WITNESS`: exact equality and disjoint windows;
- `OVERLAPPING_EQUALITY`: exact equality but the required disjointness fails;
- `NO_EQUALITY`: the only possible candidate does not equal the target.

The disjointness flag is retained separately even when equality fails. Each ratio query evaluates `P(n)` and the one candidate product. Computing the fifth root has its own reported cost; the locator does not make that arithmetic free or imply a wall-time speedup.

## Bounded scans and complete records

```js
const { createLengthFiveRatioScan } =
  require("./window_five_inverse.cjs");

const scan = createLengthFiveRatioScan({
  from: "1000001",
  through: "1010000"
});

let summary;
do {
  summary = scan.advance(1000);
} while (summary.status !== "COMPLETE");

const firstPage = scan.records({ start_index: 0, limit: 1000 });
```

The constructor does no classifications. `advance(budget)` processes at most the budgeted number of new offsets and returns a summary. `describe()` returns the current summary without advancing. The summary states the original range, requested and processed counts, exact last covered offset, next unprocessed offset, equality/witness counts, sign counts, construction counters, and the first and most recent full point classifications.

Each point is committed to the in-memory scan only after its complete classification. If a classification throws, already-completed points remain available; the failing point is still the next unprocessed offset. Scans never silently skip an input.

`records({start_index, limit})` returns compact records for currently processed points, in increasing `n`. Each row is

```text
[floor_root_of_4P(n), P(floor_root-2)-4P(n)].
```

For absolute row index `i`, the input is `n=scan.from+i`, and the only candidate is `m=BigInt(row[0])-2n`. The complete certificate is determined by this input, its root bracket inequality, and the retained signed difference. There is no truncation of processed records within the scan's fixed point limit.

A null `next_start_index` means the end of the **currently available records**. A scan may still be in progress. Complete-range consumption requires `scan_status="COMPLETE"` and the available record count equal to the requested point count. The terminal page index equal to the available record count is allowed and returns an empty page.

Returned summaries and pages are independent snapshots. The live scan handle must remain available while advancing. To continue a partially completed calculation in another runtime, preserve its records with their original `from` and start a new scan at the old summary's `next_n`, with the same upper endpoint. This begins the remaining interval and does not restore or count the old prefix as new work.

### Hard limits

| Quantity | Limit |
| --- | --- |
| Decimal digits in a standalone ratio-query `n` | 256 |
| Decimal digits in a standalone root/inverse target | 1,282 |
| Newton iterations per fifth root | 256 |
| Decimal digits in scan endpoints | 32 |
| Points in one inclusive scan | 10,000 |
| New points per `advance` | 1 through 1,000 |
| Compact records per page | 1 through 1,000 |

Budgets and page indices are integer Numbers. Unknown option keys and reversed intervals are rejected. These fixed limits are not caller overrides. A large interval is rejected before any point classification; a new scan can be deliberately scoped to another bounded interval.

The 256-digit ratio bound fits within the root target's 1,282-digit limit after multiplying five consecutive factors and then multiplying by four. Standalone inverse targets have their own bound and can produce offsets slightly longer than a standalone ratio input. Output is always exact; there is no floating-point power estimate.

## Actual interval result

The starting endpoint was derived from the retained [Commons #16065](https://github.com/woahwhattheheck/commons/pull/16065) receipt:

```text
research/conjectures_erdos686_len5/RECEIPT.json
blob: daa063aba4169b9435f5e43f3d640897f2f56eca
from = scan.n_max + 1 = 1000001
through = from + 9999 = 1010000.
```

The old scan of zero through one million was not rerun. One new scan factory, ten advances of 1,000 points, and ten public record-page calls produced the retained result.

| Quantity | Exact result |
| --- | --- |
| New offsets processed | 10,000 |
| Disjoint candidates | 10,000 |
| Equalities / eligible witnesses | 0 / 0 |
| Positive / zero / negative candidate differences | 10,000 / 0 / 0 |
| Perfect-fifth-power targets | 0 |
| Fifth-root calls | 10,000 |
| Newton iterations | 70,000; exactly seven per point |
| Integer divisions in those iterations | 140,000 |
| Window-product evaluations | 20,000 |
| Candidate product comparisons | 10,000 |
| Fifth-power bracket comparisons | 20,000 |
| Complete compact records retained | 10,000 |

A candidate comparison here means the one target/candidate comparison encoded by the signed difference, not every later Boolean use of its sign or equality flag. These counts describe executed arithmetic operations and classifications; they are not a statistical or cross-runtime benchmark.

The first and last full classifications are retained:

| Input `n` | Root `R` | Only candidate `m=R-2` | `P(m)-4P(n)` |
| --- | --- | --- | --- |
| 1,000,001 | 1,319,513 | 1,319,511 | `12295644373150191232529280` |
| 1,010,000 | 1,332,706 | 1,332,704 | `813816345431574062164440` |

For the first input, the target is `4000080000620002320004176002880`. Its exact root powers are

```text
1319513^5 = 4000077138853382433422774068793
1319514^5 = 4000092296275862612775510097824.
```

The first candidate product is `4000092296264375470195408532160`, strictly above the target, while the previous window is strictly below it. This explains the returned floor/ceiling offsets `1319510` and `1319511`.

Reading the retained differences, without recalculating any root or product, finds the smallest signed difference at `n=1008839`: root `1331174`, candidate `1331172`, difference `4405665236351851108560`. This is a finite statistic of this saved interval, not a lower bound for other inputs.

The JSON preserves every new root and difference, plus exact full first/last root brackets and all scan accounting. Expanded point objects are retained only for those two endpoints. For every other row, its input index and root determine the adjacent fifth powers; the bracket was checked during that point's single classification. The compact form avoids repeating large derivable integers in every row.

Combining the existing accepted prefix with this disjoint new interval gives recorded finite negative coverage through `n=1010000`. This is a composition of two records; the new operation did not execute the older prefix again.

## Connected-runtime consumption

The source is directly usable in connected V8 after fetching the committed module. Existing count records can be consumed without reconstructing the scan.

```js
function filePayload(response) {
  let data = response.structuredContent ?? response;
  if (Array.isArray(data.content)) {
    data = JSON.parse(data.content.find(item => item.type === "text").text);
  }
  return data;
}

const directory = "research/conjectures_erdos686_len5/";
const [sourceResponse, recordResponse] = await Promise.all([
  tools.mcp__codex_apps__github_fetch_file({
    repository_full_name: "woahwhattheheck/commons",
    path: directory + "window_five_inverse.cjs",
    ref: "main"
  }),
  tools.mcp__codex_apps__github_fetch_file({
    repository_full_name: "woahwhattheheck/commons",
    path: directory + "inverse_interval_1000001_1010000.json",
    ref: "main"
  })
]);

const saved = JSON.parse(filePayload(recordResponse).content);
const row = saved.compact_records[0];
const n = BigInt(saved.input.from);
const candidate = BigInt(row[0]) - 2n;
const signedDifference = BigInt(row[1]);

// Load the public API for a deliberately chosen new point or interval.
const loaded = { exports: {} };
new Function("module", "exports", filePayload(sourceResponse).content)(
  loaded, loaded.exports
);
const classify = loaded.exports.classifyLengthFiveRatio;
```

Use a known commit instead of `main` to pin a later consumer when needed. The recorded roots, candidates and differences are already complete for the saved interval; repeating its scan is unnecessary for ordinary downstream use.

## Publication boundary

The original Python code, tests, receipt, source note and unexecuted Lean candidate retain their existing content. This new API and interval result do not revise the accepted length-two/three/four work. The new inverse derivation consumes the centered identity already present in the carrier.

No native execution, accepted-case replay, Lean elaboration, sponsor submission or external contact occurred. The published finiteness theorem remains attributed to its original authors. A future computation or proof beyond this interval is separate work.
