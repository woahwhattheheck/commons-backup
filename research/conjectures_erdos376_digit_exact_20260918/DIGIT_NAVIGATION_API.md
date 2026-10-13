# Exact restricted-digit navigation and the Erdős 376 input

[restricted_digit_navigation.cjs](restricted_digit_navigation.cjs) provides an
exact ceiling operation for restricted digit alphabets and a bounded search
of their intersection. The search skips whole intervals that fail a digit
rule and returns JSON restart options for its first unprocessed integer.

The completed consumer in
[interval_1000001_1000000000000.json](interval_1000001_1000000000000.json)
covers `1,000,001 <= n <= 10^12` under the Erdős 376 digit rules. It found
four values in 832 ceiling calls across a real restart. The full found list,
digit representations, checkpoint and resumed output are retained.

This is a connected capability and a new retained Commons input. Existing
published tables cover far larger ranges; the source credits below are part
of the deliverable. No new external computational frontier or mathematical
priority is claimed.

## Mathematical input and conventions

For an odd prime `p`, the classical Kummer characterization says that
`p` does not divide `binomial(2*n,n)` precisely when every base-`p`
digit of `n` is at most `(p-1)/2`.
[Pomerance, Section 4, pp. 638–639](https://math.dartmouth.edu/~carlp/amm2015.pdf)
states this digit characterization.

The default rules are therefore:

| Base | Allowed digits | Maximum digit |
|---:|---|---:|
| 3 | `0,1` | 1 |
| 5 | `0,1,2` | 2 |
| 7 | `0,1,2,3` | 3 |

Their intersection is exactly the set of nonnegative indices whose central
binomial coefficient is coprime to 105. Zero is admitted; its central
binomial coefficient is 1. The earlier Commons count of 13 through
`10^6` includes zero, so it contains 12 positive values. This run begins
strictly after that accepted range.

The generic API accepts any bases and initial digit alphabets within its
limits. Its general output describes those digit languages. The
central-binomial interpretation above uses the specified odd-prime rules.

## Exact new finite output

There are exactly four admissible values in the requested new interval.
Every representation is most-significant digit first:

| n | Base 3 | Base 5 | Base 7 |
|---:|---|---|---|
| 59548377 | `11011001101000110` | `110221022002` | `1322103300` |
| 59548401 | `11011001101001100` | `110221022101` | `1322103333` |
| 45773612811 | `11101011001010110100000` | `1222221021102221` | `3210212201133` |
| 45775397187 | `11101011011111010001000` | `1222222000202222` | `3210233312322` |

By the cited digit characterization, these are exactly the indices in this
finite interval with `gcd(binomial(2*n,n),105)=1`.

The exact accounting is

```text
999,998,999,996 excluded integers
+             4 accepted integers
= 999,999,000,000 requested integers
= 10^12 - 1,000,001 + 1.
```

The source assigns every skipped interval to the rule that excludes it:

| Rule base | Ceiling calls | Skip intervals | Excluded integers |
|---:|---:|---:|---:|
| 3 | 498 | 232 | 466,489,791,843 |
| 5 | 265 | 196 | 199,026,288,125 |
| 7 | 69 | 65 | 334,482,920,028 |
| Total | 832 | 493 | 999,998,999,996 |

These are actual operation counts, not a comparative runtime benchmark.
The existing Python carrier and its accepted arithmetic and witness ranges
were not rerun.

## The one-language ceiling

A rule `{base:b, max_digit:c}` permits exactly the digits
`0,...,c`. For an input `x`, the ceiling is the least permitted
integer `y>=x`.

If every digit of `x` is already permitted, the ceiling is `x`.
Otherwise, find the first forbidden digit when reading from the most
significant end. Every preceding digit is permitted. A permitted integer
at least `x` must increase a digit before that forbidden position,
because the forbidden digit is larger than every permitted digit.

Increase the rightmost preceding digit that is below `c`, and set every
following digit to zero. If all preceding digits equal `c`, prepend a
leading 1 and use a zero suffix of the original length. This minimizes
both the first increased position and its suffix, so it gives the least
permitted integer at or above `x`.

The special alphabet `{0}` admits only zero: a positive input has no
ceiling. The full alphabet `0,...,b-1` admits every input.

The actual first interval skip was:

```text
input x       = 1,000,001
rule          = base 3, digits <= 1
next ceiling  = 1,594,323 = 3^13
excluded      = [1,000,001, 1,594,322].
```

Every number in `[x,y-1]` fails the rule when the ceiling is `y>x`.
This is the interval-exclusion fact used by the intersection search.

## Intersecting the languages

The search keeps a candidate `x` and checks the rules in their supplied
order. A rule that raises `x` to its ceiling excludes the entire interval
from the previous candidate through one less than the new candidate.
The search records that mass, moves to the new candidate and starts the
rule checks again.

If every rule leaves the candidate fixed, the candidate lies in the
intersection. It is emitted once, and the search continues at `x+1`.
If a ceiling exceeds the requested upper endpoint, or no ceiling exists,
the remaining interval is excluded and the search completes.

The processed region is always one contiguous prefix. Every step either
excludes a disjoint interval or emits its next single value; it never
skips a possible solution. At completion the implementation requires

```text
excluded_count + found_count = through - from + 1
candidate                   = through + 1.
```

The finite upper endpoint ensures that an unrestricted sequence of advances
terminates: a raised candidate increases, and a full pass of unchanged
rules emits and increments it. Individual advances remain explicitly
bounded even before completion.

## A real JSON restart

The initial search used the new interval and advanced by two ceiling calls.
It excluded the first 594,322 integers and returned:

```text
status                  = IN_PROGRESS
covered_through         = 1,594,322
resume_options.from     = 1,594,323
pending_rule_index      = 1.
```

That runtime ended. A fresh V8 runtime parsed the serialized
`resume_options`, loaded the same complete module source and created a
new search handle. The new handle completed the adjacent suffix through
`10^12` in 830 ceiling calls.

The completed pieces are exactly

```text
[1,000,001, 1,594,322]
[1,594,323, 1,000,000,000,000].
```

They are adjacent and disjoint. Their processed counts and found-value
lists therefore combine directly. The full JSON retains both original
API outputs, the exact consumed restart options, the boundary and the
combined result.

Restarting rechecks the first unprocessed candidate from rule zero. In
this actual handoff, base 3 had already been checked at that pending
candidate; that repeated pending-candidate check is included in the
832-call total. The covered prefix was not revisited. Restart options
are a new suffix request, not an assertion that the preceding output
has been independently verified.

## Public API

The module exports:

- `ceilingRestrictedDigits(value, rule)`
- `createDigitIntersectionSearch(options)`
- frozen `default_rules` and `limits`

It has no imports, network or filesystem access, native-process calls,
floating-point integer arithmetic, or required host service. CommonJS
consumers can load it normally. A connected V8 consumer can use the complete
source text as follows:

```javascript
const moduleBox = {exports: {}};
new Function("module", "exports", completeModuleText)(
  moduleBox, moduleBox.exports
);
const api = moduleBox.exports;

const search = api.createDigitIntersectionSearch({
  from: requestedFrom,
  through: requestedThrough,
  max_saved_values: 4096,
  max_saved_jumps: 64
});

const output = search.advance(10_000);
```

Default rules are the ordered base-3/base-5/base-7 rules above. To search
another intersection, supply a `rules` array explicitly.

### Exact inputs and limits

Values `from`, `through` and the primitive's `value` accept
nonnegative BigInt values, safe integer Numbers, or canonical natural
decimal strings. Signs, whitespace, leading-zero alternatives and
non-integer forms are not accepted as strings. The inclusive interval
must satisfy `from<=through`.

| Parameter | Accepted bound | Default |
|---|---|---|
| Exact integer input size | At most 256 decimal digits | Required values |
| Rules per search | 1 through 16 | The three default rules |
| Rule `base` | Safe integer from 2 through 36 | Required in a supplied rule |
| Rule `max_digit` | Safe integer from 0 through `base-1` | Required |
| Calls per `advance` | Safe integer from 1 through 10,000 | Required |
| `max_saved_values` | Safe integer from 0 through 65,536 | 4,096 |
| `max_saved_jumps` | Safe integer from 0 through 4,096 | 64 |

Unknown option or rule fields are rejected. Invalid objects or exact-value
representations produce `TypeError`; negative parsed integers,
out-of-range numeric settings, oversized parsed values and reversed
intervals produce `RangeError`. An oversized decimal string fails
exact-value parsing before conversion.

A one-language ceiling can have one more decimal digit than the input
limit. The bounded intersection terminates if such a ceiling exceeds
its valid upper endpoint. The alphabet `{0}` has no ceiling above
zero; that case is explicit in the primitive result.

### Ceiling result

`ceilingRestrictedDigits` returns schema
`erdos376.restricted_digit_ceiling/v1` with:

- exact `value` and `next_admissible` decimal strings;
- a copied `rule` and most-significant-first input/output digit strings;
- `changed`, `skipped_interval` and
  `no_admissible_at_or_above`.

If no ceiling exists, `next_admissible` and the output digit string
are null. The skip interval's null upper endpoint then denotes exclusion
of every integer at or above its start. If the input is already allowed,
`skipped_interval` is null.

### Search handle and output

The frozen handle has `advance(budget)` and `describe()`.
`advance` performs at most `budget` new ceiling calls;
`describe` returns a fresh JSON-safe view without advancing.
An already-complete handle keeps returning its complete result, with
advance-budget validation still applied.

The search schema is `erdos376.digit_intersection_search/v1`.
All unbounded integers and counts are decimal strings. Bases, digit caps,
array limits and the pending-rule index are bounded JSON numbers.

Principal fields include:

| Fields | Meaning |
|---|---|
| `status`, `from`, `through`, `rules` | Requested interval, language rules and completion |
| `requested_count`, `processed_count`, `unprocessed_count` | Exact interval coverage |
| `excluded_count`, `found_count` | Disjoint excluded mass and accepted count |
| `covered_through` | Last fully processed integer; null when none is processed |
| `ceiling_calls`, `calls_by_rule` | Exact operation counts |
| `jump_count`, `jumps_by_rule`, `excluded_by_rule` | Exact exclusion accounting |
| `values`, `first_value`, `last_value` | Retained values and endpoint values |
| `jump_intervals`, `last_jump` | Retained initial jump records and final observed jump |
| `resume_options` | Direct factory input for the unprocessed suffix; null on completion |
| `pending_rule_index`, `resume_rechecks_pending_candidate` | In-memory partial-candidate state and restart behavior |

Each retained value includes its exact digit representation under every
supplied rule. Digit strings use lowercase letters for digits above 9.

`values_truncated` and `jumps_truncated` compare retained collection
sizes with their exact counts. A zero retention limit is permitted.
Counts and coverage continue after a storage limit is reached.
`first_value`, `last_value` and `last_jump` remain available
independently of the prefix-retention limits.

### Consume a saved partial result

```javascript
const partial = JSON.parse(savedPartialText);
const nextSearch =
  api.createDigitIntersectionSearch(partial.resume_options);
const nextOutput = nextSearch.advance(10_000);
```

Use this only when `resume_options` is non-null. Retain the previous
covered range and values before moving on. The restart request begins at
the first unprocessed integer, so adjacent covered ranges can be combined
without overlap. The earlier counts are not copied into the new handle;
the new handle reports only its suffix request.

## Retention in the completed input

All four accepted values and every requested digit representation are
retained. The combined processed count covers the entire interval.

There were 493 skip intervals. The operation kept one initial-segment
jump, the first 64 resumed-segment jumps, and each segment's final jump.
The first segment's last jump duplicates its sole initial record.
The resumed final jump is retained separately. The data explicitly says
the jump trace is incomplete; the resumed `jumps_truncated` flag is
true.

Thus the artifact retains complete found values and exact coverage/counts
with a capped explanatory trace. It does not present the saved jump
records as a complete independently replayable exclusion transcript.
The algorithm and interval accounting establish the finite search result.
No independent run of the same range was performed to enlarge the trace.

## Prior work and retained ownership

The [original Commons carrier #16046](https://github.com/woahwhattheheck/commons/pull/16046)
merged at `ea57ea4515c2f4b50cd1a382fd3e067e84ea0c73`.
Its Python verifier, receipt, tests and unexecuted Lean candidate remain
unchanged. The earlier 600,003 digit/carry cases, 4,097 exact binomial
cases and 13 values through `10^6` are accepted inputs.

[OEIS A030979](https://oeis.org/A030979), authored by Shawn Godin, credits
Christopher E. Thompson's 1,374-value table including zero as complete
through `10^70` (2015), extending Max Alekseyev's earlier 62 terms.
It also records T. D. Noe's intersection formulation/program and
Charles R. Greathouse IV's valuation program. This new interval lies
within that already-published range; those computations were not rerun.

[The July 28, 2026 working report](https://www.erdosproblemaday.com/report/376),
by Patrick White with disclosed model assistance, self-reports 14,273
positive values, or 14,274 including zero, through `10^100`.
It describes intersecting allowed prefix cylinders. The site labels the
report PARTIAL and not independently verified. It is credited as prior
disclosed work, without adopting its computation as a newly certified
frontier.

The [current target page](https://conjectures.io/problems/erdos376-erdos-376)
still presents the infinitude statement and the published 11-lemma
carry/digit contribution. The retained source-type hash is
`83aa384e77fe25f943ed3670056017df36b3d4ba6760b2beb7b855321c36d887`.
Its current task identifier and commitment are recorded in the new JSON.
The earlier Commons reverse-direction Lean candidate remains unexecuted;
this API is not a new formal receipt.

Operation: `ERDOS376-DIGIT-NAVIGATION-API-20261004-7CA6`.
Original mathematics thread `1789742728.512289`, channel
`C0C3MEWHTR6`; claim `1791101551.772689`.
Original authorship and submission ownership are preserved. No sponsor
submission, infinitude, external frontier, priority or payment claim
is represented.
