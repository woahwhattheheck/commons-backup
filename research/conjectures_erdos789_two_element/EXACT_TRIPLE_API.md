# Exact separating triples in a connected JavaScript runtime

`separating_triple.cjs` supplies two public functions:

- `constructSeparatingTriple(values)` selects a separating triple from an integer set.
- `classifySeparatingTriple(values)` classifies one triple and supplies an explicit collision when it fails.

The functions use exact `BigInt` arithmetic, return JSON-safe data, and require no process,
imports, packages, network calls, or host-specific API.

## Sources and attribution

The triple criterion and the five-nonzero guarantee are already given in
sections 3–4 of the [July 28, 2026 report for Erdős 789](https://www.erdosproblemaday.com/report/789).
This implementation makes that construction available through a bounded public API.
It claims no new small value of the threshold function.

The convention follows
[Formal Conjectures, `789.lean`](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/789.lean),
observed October 4, 2026 at Git blob
`2e30b63699a5f0e4cc52e41092e0b3c78db5fd77`:
integer sets may contain zero, and the two compared subsets must be nonempty;
they may overlap. This source observation does not replace the historical task
pin or the original contribution's ownership.

## Input contract

Both functions accept an array whose items are any mixture of:

| JavaScript type | Accepted values |
| --- | --- |
| `bigint` | Any signed integer |
| `number` | Integers satisfying `Number.isSafeInteger` |
| `string` | `0` or a signed decimal integer with no leading zero, plus sign, spaces, fraction, or exponent |

Numeric negative zero is normalized to zero. The string `"-0"` is not canonical
and is rejected. Invalid items, including sparse array entries, cause
`TypeError`. Every item is read and validated, even if the early portion of
the array already provides a witness. The caller's array is not modified.

The constructor treats the array as a set: equal integers are deduplicated,
including equal values supplied in different accepted types. The first input
index is retained. The classifier instead requires exactly three distinct
integers; a wrong length or duplicate value causes `RangeError`.

All integer values and subset sums in the output are decimal strings.
Counts and zero-based indices are ordinary numbers.

## Construction and bounds

The constructor retains the first five distinct nonzero values, or all of them
if fewer exist. It visits their triples in increasing index order and stops at
the first separating triple. The cited guarantee ensures that five distinct
nonzero values suffice. A failure to find a triple in a five-element pool raises
an invariant error rather than reporting nonexistence.

There are at most ten candidate triples. A negative result has at most four
nonzero triples to explain. Reading, deduplicating, and filtering the input
takes a linear number of container operations and linear storage in the number
of distinct input values. The ten-candidate bound does not bound the input size
or integer digit length; parsing, hashing, and arithmetic costs still depend on
those quantities.

The result has schema `erdos789.triple_construction/v1` and contains the input
counts, the retained pool, `candidate_limit: 10`, and the number actually examined.

| Status | Payload and meaning |
| --- | --- |
| `SEPARATING_TRIPLE` | `triple.values` and `triple.input_indices` identify a witness. `subset_sums_by_cardinality` contains its three singleton sums, three pair sums, and full sum. |
| `NO_SEPARATING_TRIPLE` | The distinct input set contains no separating triple. The obstruction explains every nonzero triple and, if present, all zero-containing triples. Fewer than three distinct values are identified explicitly. |

The constructor does not search for a maximum separating subset.

## Collision semantics

The classifier has schema `erdos789.triple_classification/v1` and returns
`SEPARATING` with the seven nonempty subset sums, or `COLLISION` with:

- `left_indices` and `right_indices`, selecting two nonempty subsets of the returned
  three `values`;
- `common_sum`, the exact shared sum;
- a `kind` explaining the relation.

The indices in a collision are local to that triple; they are not indices into
the original constructor input. Use the triple's `input_indices` for that mapping.

A zero member gives `{a}` and `{a,0}`; an opposite pair gives the remaining
singleton and the whole triple; otherwise a singleton may equal the other pair.
These are the three failure types from the cited criterion. A whole-triple sum
of zero alone is allowed: the empty subset does not participate.

The constructor's negative result stores every nonzero triple's concrete
collision. Zero-containing triples are covered compactly by `a = a + 0`, with
cardinalities 1 and 2 and the zero's original input index. Subset overlap is
intentional in both this rule and the opposite-pair witness.

## Connected runtime use

Read the complete source text from
`research/conjectures_erdos789_two_element/separating_triple.cjs`
through the connected repository file reader, then evaluate that text:

```javascript
const moduleBox = {exports: {}};
new Function("module", "exports", completeSource)(
  moduleBox,
  moduleBox.exports
);
const {constructSeparatingTriple, classifySeparatingTriple} = moduleBox.exports;

const result = constructSeparatingTriple(
  ["-5", "-4", "-3", "-2", "-1", "0", "1", "2", "3", "4", "5"]
);
text(JSON.stringify(result));
```

In an ordinary CommonJS host, the same exports are available through
`require("./separating_triple.cjs")`.

## Actual source inputs consumed

[construction_results.json](construction_results.json) retains two calls made
through the public constructor in the connected V8 runtime on October 4, 2026.
The input sets are the report's section 6 objects, not a new extremal search.

| Source object | Returned result | Candidates examined |
| --- | --- | ---: |
| `A_5 = {-2,-1,0,1,2}` | No separating triple; four explicit nonzero collisions plus the zero rule | 4 |
| `A_11 = {-5,-4,...,5}` | Triple `{-5,-4,-3}` with sums `{-5,-4,-3}`, `{-9,-8,-7}`, and `{-12}` in sizes 1, 2, and 3 | 1 |

The original 7,007-case carrier calculation and the report's maximality
enumerations were not rerun. The new artifact is a callable exact-integer
construction with reusable output, not an additional theorem or a new Lean result.
