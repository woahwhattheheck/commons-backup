# Translation-weighted Sidon gap search

[translated_sidon_gap_search.cjs](translated_sidon_gap_search.cjs) supplies a
separate exact search API that traverses only minimum-zero representatives
and counts every translation fitting the requested window. It preserves
the original Sidon condition and gap-square objective while avoiding
repeated objective evaluation on translated copies.

The [completed ten-element input](N10_FINITE_PREMISES.md) is the first
retained consumer of this API. Its full output is
[n10_finite_premises.json](n10_finite_premises.json). The earlier
[sidon_gap_search.cjs](sidon_gap_search.cjs) API and accepted inputs remain
unchanged.

## The normalization and exact weights

For every nonempty set `B` of natural integers, let `t = min(B)` and
`A = B-t`. Then `min(A)=0`, and the pair `(A,t)` is unique.
A normalized set with diameter `d=max(A)` fits in `[0,D]` at exactly
the translations

```text
A+t,  t = 0,1,...,D-d.
```

Its weight is therefore `D-d+1`.

Translating every element by `t` adds `2t` to every unordered pair
sum. It preserves uniqueness of those sums and preserves every
consecutive gap in their sorted order. Thus both Sidon membership and
the gap-square energy are translation invariant. This is the gap energy
of the sumset, with diagonal pairs included and denominator `|A+A|`.

### Weight of a rejected prefix

Fix a normalized increasing prefix of length `k`, beginning at zero
and ending at `x`. Let `m=n-k` elements remain to be selected. For a
fixed translation `t`, the remaining elements of the original set
can be selected from `{x+t+1,...,D}`, giving `C(D-x-t,m)` choices.

Each original set has a unique minimum `t`, so the total original-set
mass of all completions of the prefix is

```text
sum_{t=0}^{D-x} C(D-x-t,m)
  = sum_{j=0}^{D-x} C(j,m)
  = C(D-x+1,m+1)
  = C(D-x+1,n-k+1).
```

The middle identity follows by counting the `(m+1)`-subsets of
`{0,...,D-x}` by their largest element `j`: the other `m` elements
have `C(j,m)` choices. The convention is `C(a,b)=0` for `b>a`.
The same expression covers `k=n`, where it becomes `D-x+1`.

The unweighted number of normalized completions is `C(D-x,n-k)`.
The API retains and accounts for both quantities.

## Traversal and completeness

The traversal fixes the first coordinate at zero and extends a strictly
increasing prefix. As in the predecessor API, it stores the positive
differences of that prefix. On appending a new largest coordinate, a
repeated difference makes the prefix non-Sidon, so every full extension
of it is non-Sidon.

Each such subtree is charged once at its first invalid prefix and is
then pruned. The subtree contributes its unweighted binomial count to
the normalized non-Sidon total and its translation-weighted binomial
count to the original non-Sidon total. A valid full normalized set is
evaluated once and contributes `D-d+1` original Sidon sets.

At completion the API requires both exact identities:

```text
normalized_pruned_non_sidon_subsets + normalized_sidon_subsets
  = normalized_total_subsets
  = C(D,n-1)

pruned_non_sidon_subsets + sidon_subsets
  = total_subsets
  = C(D+1,n).
```

The first fixed zero coordinate is not an extension attempt, so the
first entry of `attempts_by_depth` is zero. Later entries correspond
to prefix lengths 2 through `n`. Rejected-prefix counts describe
branches; the separately weighted subset counts describe full sets.

Every surviving Sidon leaf is evaluated. The API performs no
energy-based pruning and no reflection quotienting. Its energy
histogram is over Sidon sets. Pruned non-Sidon mass carries no
energy-histogram claim.

## Public API

The module has no imports, native-process access, network access, I/O,
or required host service. A CommonJS consumer uses
`createTranslatedSidonGapSearch` from the module exports. A connected
V8 consumer can load the complete source and use:

```javascript
const moduleBox = {exports: {}};
new Function("module", "exports", completeModuleText)(
  moduleBox, moduleBox.exports
);

const search = moduleBox.exports.createTranslatedSidonGapSearch({
  n: requestedCardinality,
  cutoff: inclusiveCutoff,
  max_saved_minimizers: 4096,
  max_saved_minimizer_families: 4096
});

const progress = search.advance(1_000_000);
```

The factory accepts the following numeric options:

| Option | Accepted values | Default |
|---|---|---|
| `n` | Safe integer from 2 through 12 | Required |
| `cutoff` | Safe integer from 0 through 512, inclusive | Required |
| `max_saved_minimizers` | Safe integer from 1 through 65,536 | 4,096 |
| `max_saved_minimizer_families` | Safe integer from 1 through 65,536 | 4,096 |

Unknown option keys are rejected. Invalid option objects and unknown
keys produce `TypeError`; numeric range/type failures produce
`RangeError`. The exported frozen `limits` object records these
ceilings.

The returned frozen search handle has two methods:

- `advance(budget)` accepts a safe integer from 1 through 1,000,000,
  performs at most that many new prefix extension attempts, and returns
  a fresh JSON-safe result.
- `describe()` returns a fresh result without advancing the traversal.

The driver can yield between advances, retain progress, and choose an
explicit total-work limit. Keep the same handle alive in one runtime to
continue. The module does not restore a traversal from serialized
output. A saved `IN_PROGRESS` result is a partial result; it does not
establish the finite minimum or complete coverage. A completed result
is directly usable without re-executing the traversal.

If `n>D+1`, the domain is empty. Completion then has zero total and
Sidon counts and no minimum. For a nonempty domain with no Sidon set,
the minimum fields also remain null. An already-complete search
continues to return its complete result; the supplied advance budget
is still validated.

## Output contract and minimizer retention

The result schema is `erdos153.translated_sidon_gap_search/v1`.
Counts, binomial totals, gap-square sums and rational
numerators/denominators are exact decimal strings. Coordinates and
bounded input parameters are JSON numbers.

The principal field groups are:

| Fields | Meaning |
|---|---|
| `status`, `n`, `cutoff`, `sumset_cardinality` | Progress state and exact requested domain |
| `total_subsets`, `normalized_total_subsets` | All original and minimum-zero subsets |
| `extension_attempts`, `attempts_by_depth` | Actual normalized traversal work |
| `rejected_prefixes`, `rejected_prefixes_by_depth` | First-invalid branches |
| `pruned_non_sidon_subsets`, `normalized_pruned_non_sidon_subsets` | Exact masses of pruned full subsets |
| `sidon_subsets`, `normalized_sidon_subsets` | Translated Sidon count and evaluated representatives |
| `accounted_subsets`, `normalized_accounted_subsets` | Current exact coverage totals |
| `minimum_gap_square_sum`, `minimum_energy` | Incumbent value, final only at completion |
| `minimizer_count`, `normalized_minimizer_count` | Exact numbers of attaining original sets and representatives |
| `minimizers`, `minimizer_families` | Retained explicit sets and translation-family records |
| `energy_histogram` | Complete visited Sidon histogram, final at completion |

Each histogram row has `gap_square_sum`, `count` for translated
sets, and `normalized_count` for normalized representatives.
Its energy is `gap_square_sum / sumset_cardinality`.

Each family record has `normalized_values`, `translation_min=0`,
`translation_max=D-d`, and exact `translated_count=D-d+1`.
Different normalized representatives cannot create the same original
set because subtracting its unique minimum recovers its representative.

Exact minimizer counts do not depend on retention limits. Each of
`minimizers_truncated` and `minimizer_families_truncated` compares its
retained length with the corresponding exact count. A new lower energy
resets both counts and both retained collections. An equal energy adds
the new family's exact translation weight even after a retention limit
has been reached.

Explicit minimizers are retained by normalized-prefix traversal order,
with increasing translations inside each family; the list is not
globally sorted across families. With no truncation it contains every
attaining set exactly once. A truncated list must be treated as a
retained subset, with its exact larger count reported separately.

For `n<=12` and `D<=512`, coordinates, pair sums and gap-square
totals are exact safe integer Numbers. Binomial coefficients and
accumulated counts use BigInt throughout. The witness/objective API
in the predecessor module remains available for arbitrary accepted
exact-integer coordinates.

## Actual completed consumer and provenance

The new `n=10,D=71` input completed in 312 advances and 311,297,245
normalized prefix extension attempts. It evaluated 86,638 normalized
Sidon sets representing 203,840 original Sidon sets. Both coverage
identities completed, and all 24 minimizers from two normalized
families were retained. This is an actual new input, without replaying
the earlier finite windows. No comparative runtime benchmark is
asserted.

The traversal mechanics extend
[Commons PR #31130](https://github.com/woahwhattheheck/commons/pull/31130),
whose original module blob is
`82f165edd18b7d71f5746f96ff606ad14fe0aadf`. The normalization count
above is the new derivation used by this module. The original module,
the `n<=9` result files, and the
[original #16049 carrier](https://github.com/woahwhattheheck/commons/pull/16049)
retain their source and submission ownership.

See [the ten-element result](N10_FINITE_PREMISES.md) for the accepted
finite-search interface, exact cutoff, witness and evidence boundary.
This API does not provide a new Lean receipt or an asymptotic proof.
