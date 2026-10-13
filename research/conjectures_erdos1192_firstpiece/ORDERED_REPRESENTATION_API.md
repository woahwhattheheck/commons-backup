# Exact ordered representation counts and witnesses

The connected API in [ordered_representation_index.cjs](ordered_representation_index.cjs) computes ordinary ordered representation counts for a finite set of natural numbers and constructs individual representations by rank. It uses exact coefficient tables, so its work depends on the normalized sum range instead of visiting every tuple.

The actual new input is the retained finite set

```text
B = [0, 1, 9, 14, 24, 35, 41, 53, 57, 60], order = 20.
```

There are `100000000000000000000` ordered tuples. One connected-runtime construction used **12,621 coefficient cells and 111,490 coefficient additions**. All **1,201 final counts** are saved in [r20_retained_set_representations.json](r20_retained_set_representations.json), including the zero counts and every selected or ranked witness described below. No wall-time benchmark is claimed.

Operation: `ERDOS1192-ORDERED-REPRESENTATION-INDEX-20261004-7CA6`.

## Source, conventions and prior work

The [FormalConjectures definition of Erdős 1192](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/1192.lean), read on October 4, 2026, counts functions from `Fin r` to the natural numbers whose coordinates belong to the set and sum to the target. Thus tuples are ordered, coordinates may repeat, and zero is available exactly when it belongs to the set. Its truncated energy uses targets from zero through the endpoint inclusive. It also states the order-zero empty-tuple value; the conjecture itself quantifies over orders at least two.

The interface follows those conventions and deduplicates repeated input values. Zero-based lexicographic ranks are an API choice. No operation reduces sums modulo a period.

Nonnegativity gives the exact truncation needed to connect finite inputs to a specified infinite set: a tuple summing to a target at most `x` has every coordinate at most `x`. Therefore all queries through `x` depend only on `A intersect [0,x]`. A caller must actually supply that truncation before interpreting the API as a count for that `A`. The arbitrary finite set used here is its own input; it is not asserted to be the truncation of an infinite basis witness.

For established credit, Imre Z. Ruzsa's [A just basis, Monatshefte für Mathematik 109 (1990), 145–151](https://link.springer.com/article/10.1007/BF01302934), DOI `10.1007/BF01302934`, proves the order-two square-mean basis result. The publisher's abstract explicitly uses nonnegative integers and ordered pairs. This work does not reconstruct that proof.

The [July 28, 2026 working report](https://www.erdosproblemaday.com/report/1192), credited to Patrick White with model assistance disclosed by the source, is labelled PARTIAL and not independently verified. It reports ordered cyclic three-basis computations for moduli 2 through 41. Its truncation is written `A intersect [1,x]`; that positive convention must not remove zero from this interface. Its modular order-three computation is a different finite question from the ordinary order-20 input here. The report's computations and structural claims were not replayed or newly certified in this operation.

The original Commons [#16053](https://github.com/woahwhattheheck/commons/pull/16053) carrier supplies the finite energy scaffold and its accepted 4,088-case record. Its Python function counts representations by enumerating the Cartesian power. This module adds a separate table-based interface; the existing Python code, receipt and Lean handoff remain their existing artifacts. The source/convention section was developed with the delivery lane's source contribution.

## Public interface

The CommonJS module exports `createOrderedRepresentationIndex` and a frozen `limits` object. The module has no imports, I/O or native-runtime requirements.

```js
const { createOrderedRepresentationIndex } =
  require("./ordered_representation_index.cjs");

const index = createOrderedRepresentationIndex({
  values: [0, 1, 9, 14, 24, 35, 41, 53, 57, 60],
  order: 20
});

index.count("600");
// "401287274551572372"

index.select("600", "200643637275786186");
// SELECTED; the exact tuple is retained below and in the data file.

index.interval({ from: "100", through: "1100" });
// fully_covered: true; all counts and energy are exact decimal strings.
```

The constructor completes synchronously within fixed table and operation bounds. It returns six methods:

| Method | Result |
| --- | --- |
| `describe()` | Normalized input, complete total and energy, support bounds, finite Cauchy accounting and construction counters. |
| `count(sum)` | The exact count as a decimal string; zero for a target outside the support or normalized lattice. |
| `interval({from, through})` | Inclusive ordinary integer range: number of targets, represented and missing targets, tuple mass, energy and whether every target is represented. |
| `distribution({start_index, limit})` | A page of final normalized coefficient slots, including zero slots, with their exact ordinary-sum mapping and next page index. |
| `select(sum, rank)` | The ordered tuple at the zero-based lexicographic rank among representations of that one sum, or `RANK_OUT_OF_RANGE`. |
| `rank(tuple)` | The sum and zero-based rank of the supplied valid ordered tuple, together with the representation count for that sum. |

All returned objects and arrays are fresh snapshots. Mutating them does not change the index.

### Natural-number inputs and endpoint behavior

Set values, tuple entries, sum queries and rank queries accept BigInts, nonnegative safe integer Numbers, or canonical natural decimal strings. A string has either the form `"0"` or a nonzero leading digit followed by digits. Signs, leading zeros, whitespace, booleans, fractional Numbers and unsafe Numbers are rejected.

The `values` input must be an array. Entries are sorted and deduplicated before counting. Repetition in a tuple is allowed; repetition in the input array adds no weight. An empty input set is allowed.

Order and pagination parameters are integer Numbers, not decimal strings. The constructor accepts orders from zero through 64. At order zero there is one empty tuple at sum zero, even for an empty input set; all other sums have count zero. A positive order with an empty set has no representations.

`rank(tuple)` requires exactly `order` entries and rejects any entry outside the set. It derives the target sum from the tuple. A syntactically valid but too-large rank passed to `select` returns `RANK_OUT_OF_RANGE`, the exact representation count, and `tuple: null`. In particular, rank zero is out of range for an unrepresented sum. Malformed inputs or reversed intervals throw descriptive errors. Unknown option keys are rejected.

Every coordinate, count, energy, sum, range size and rank in output is an exact decimal string, apart from bounded table indices, order, input cardinality and construction counters. Convert decimal strings to BigInt before arithmetic; do not convert large counts to Number.

### Distribution pages

Default pagination begins at index zero and returns at most 4,096 slots. The returned `counts[j]` belongs to the absolute coefficient index

```text
i = start_index + j
ordinary sum = base_sum + step * i.
```

Every ordinary sum not on this lattice has count zero. Lattice membership alone does not guarantee a positive count: zero coefficient slots are retained. A page is complete when `next_start_index` is null. The terminal start index equal to `total_coefficients` is allowed and returns an empty page.

The actual retained run has `base_sum=0`, `step=1`, and only 1,201 slots, so its single saved page is the full final distribution. A caller needing these particular counts can read the JSON directly without constructing another index.

### Inclusive interval queries

Interval endpoints are ordinary natural numbers and may extend beyond the possible sum range. Targets outside that range are counted as missing. The method returns both

```text
ordered_representations = sum of c(n)
energy = sum of c(n)^2
```

over the requested inclusive targets. The `fully_covered` flag compares the number of represented targets with the full ordinary interval size, including any off-lattice targets. These are finite coverage statements about the supplied set.

## Why the coefficient and witness algorithms are exact

For a nonempty sorted set let `a` be its minimum and let `g` be the gcd of its differences from `a`. For a singleton use `g=1`. Write

```text
B = {a + g*b : b in T},  min(T)=0,  L=max(T).
```

A tuple of order `r` with normalized sum `s` has original sum `r*a + g*s`. This map preserves coordinate order and multiplicity. It also gives a bijection of possible normalized sums to their original lattice sums, so it preserves the total representation mass and energy. The empty set uses minimum zero, step one and span zero as bookkeeping conventions.

Let `C_j(s)` count ordered normalized tuples of length `j`. Start with `C_0(0)=1`, with other coefficients zero. Partitioning tuples by their final coordinate gives

```text
C_j(s) = sum_{b in T} C_(j-1)(s-b).
```

The module stores the coefficient rows for every length from zero through `r`. Negative or out-of-row indices contribute zero. No tuple is explicitly visited to build these rows. Their final mass is `|B|^r`; the constructor requires that identity, the preflight update bound, and the finite Cauchy accounting to hold before returning an index.

At a prefix of a representation, suppose `k` coordinates remain and their normalized sum must be `s`. All tuples whose next coordinate is `b` form a consecutive lexicographic block of size `C_(k-1)(s-b)`. `select` subtracts whole earlier blocks until it reaches the block containing the desired rank. `rank` adds the sizes of all earlier blocks before following the supplied coordinate. Repeating this for each coordinate constructs or ranks a tuple using at most `r*|B|` coefficient lookups. Ranks are always within the representations of a fixed sum; they are not ranks across all sums.

Prefix arrays for final mass, squared mass and nonzero coefficients support interval queries. Endpoint arithmetic uses BigInt and the exact normalized lattice. There is no rounding through floating-point counts.

The constructor's finite energy record uses `m=max(B)`, with `m=0` for an empty set, and records

```text
(r*m+1) * sum_n c(n)^2 - |B|^(2*r).
```

This is the same finite Cauchy quantity as the original carrier, now calculated on the new input through coefficient tables. Its nonnegative value is not an asymptotic bound for an infinite set.

## Fixed construction and query bounds

Let `k=|B|`, `r=order`, and `L` be the shift/gcd-normalized span. The number of coefficient cells is

```text
(r+1) + L*r*(r+1)/2.
```

An upper bound on coefficient additions, before skipping zero coefficients, is

```text
k * (r + L*r*(r-1)/2).
```

These formulas also apply to the empty set with span zero. Prefix query arrays are additional to the reported coefficient table cells. All table indices and counter arithmetic are bounded exact integers.

| Quantity | Bound |
| --- | --- |
| Supplied array entries, before deduplication | 256 |
| Order | 0 through 64 |
| Decimal digits per set value or tuple entry | 256 |
| Decimal digits per sum, interval endpoint or rank query | 512 |
| Normalized span `L` | 65,536 |
| Final degree `r*L` | 65,536 |
| Coefficient table cells | 262,144 |
| Preflight coefficient-addition bound | 4,000,000 |
| Distribution page size | 1 through 4,096 |

All factory inputs satisfy the same fixed normalization and budget checks, including order-zero inputs. The limits are not caller overrides. An oversized request is rejected before coefficient-table allocation; no partial result is returned. Large original coordinates can still fit when shifting and dividing by their difference gcd gives a small span.

The largest allowed tuple count is at most `256^64`. Counts, energies and ranks use BigInt. The operation counts above describe coefficient arithmetic, not a machine-independent timing bound; gcd, BigInt arithmetic and decimal output formatting also take work.

## Actual retained input and complete result

The input comes from [Commons #31157](https://github.com/woahwhattheheck/commons/pull/31157), merge `c8c12c19ba5733c7ad7314c6590c2135afad673f`:

```text
research/conjectures_erdos153_exact_values/n10_finite_premises.json
blob: 60a1aabeb9b1e04e4dba9423ff0f57933d9e82ae
field: search.minimizer_families[0].normalized_values
```

The existing set was read from the retained artifact. Its earlier optimization was not repeated. Here it is simply a finite additive input. The new module was constructed once at order 20, then the public methods produced the retained distribution, two intervals, three selections and one tuple rank.

| Quantity | Exact result |
| --- | --- |
| Ordered tuple mass | `100000000000000000000` |
| Possible ordinary targets | 0 through 1,200 |
| Positive counts | 1,195 targets |
| Missing targets | 1189, 1192, 1195, 1196, 1198, 1199 |
| Full energy | `28732712325003132249552973891500393716` |
| Unique largest representation count | `404417993841457570`, at sum 588 |
| Count at sum 600 | `401287274551572372` |
| Coefficient cells | 12,621 |
| Actual coefficient additions | 111,490 |
| Preflight addition bound | 114,200 |

The complete support is

```text
[0,1188] union [1190,1191] union [1193,1194] union {1197,1200}.
```

The six terminal gaps also have a short structural explanation. Deficits from the largest possible sum 1200 are sums of elements of `60-B`. Its only positive elements at most eleven are 3 and 7. The deficits `1,2,4,5,8,11` cannot be formed from 3 and 7. This explains those six gaps; full coverage of the remaining interval is supplied by the retained coefficient calculation.

The separate public interval query on `[100,1100]` gives 1,001 represented targets, no missing targets, tuple mass `99999998756855490592`, and energy `28732712325003080191471803867368683650`. This interval query reuses the constructed table.

At sum 600, the first tuple is ten zeros followed by ten sixties. The last is ten sixties followed by ten zeros. The selection at rank `200643637275786186` is

```text
[35,1,14,14,24,35,57,53,57,60,9,60,0,24,57,14,1,60,24,1].
```

A separate supplied tuple consists of the retained input list concatenated with itself. Its sum is 588, and its rank among the `404417993841457570` representations of that sum is `4136416480592650`. This uses the public ranking method on an actual tuple built from the retained input.

The JSON contains the complete final coefficient page and complete query outputs. It does not retain every intermediate coefficient row or enumerate the individual tuples. It does retain each row's construction counters, so the 111,490-addition total is explicit. The intermediate orders are suffix tables required by this one construction; they are not reruns of the old finite-case certificate.

## Connected V8 consumption

The same CommonJS source runs in the connected V8 environment after fetching the committed files. This recipe shows the actual connector envelope shape used for the new calculation. Existing environments with normal module loading can use the shorter example above.

```js
function filePayload(response) {
  let data = response.structuredContent ?? response;
  if (Array.isArray(data.content)) {
    data = JSON.parse(data.content.find(item => item.type === "text").text);
  }
  return data;
}

const directory = "research/conjectures_erdos1192_firstpiece/";
const [sourceResponse, dataResponse] = await Promise.all([
  tools.mcp__codex_apps__github_fetch_file({
    repository_full_name: "woahwhattheheck/commons",
    path: directory + "ordered_representation_index.cjs",
    ref: "main"
  }),
  tools.mcp__codex_apps__github_fetch_file({
    repository_full_name: "woahwhattheheck/commons",
    path: directory + "r20_retained_set_representations.json",
    ref: "main"
  })
]);

const sourceFile = filePayload(sourceResponse);
const saved = JSON.parse(filePayload(dataResponse).content);

// The already-published final counts can be consumed directly.
const exactCountAt600 = saved.result.distribution.counts[600];

// Construct an index when suffix-based witness navigation is needed.
const loaded = { exports: {} };
new Function("module", "exports", sourceFile.content)(loaded, loaded.exports);
const index = loaded.exports.createOrderedRepresentationIndex(saved.input);
const witness = index.select("600", "200643637275786186");
```

A reader can use a known commit instead of `main` to pin a later consumption. The checked-in source, exact input provenance, final distribution and query outputs are sufficient to use the result outside the originating session.

## Evidence boundary and ownership

This delivers a reusable exact finite API and one fully retained new ordinary order-20 result. It does not optimize over sets, prove an infinite additive-basis assertion, establish the uniform energy bound in Erdős 1192, or claim a new external computational frontier. The current formal statement and prior report were used for definitions and attribution; no accepted proof was audited or rerun.

The accepted 4,088-case certificate and earlier Sidon computations were not rerun. There was no native execution, Lean elaboration, sponsor submission or external contact. The original mathematical credit and submission ownership remain with their existing sources.
