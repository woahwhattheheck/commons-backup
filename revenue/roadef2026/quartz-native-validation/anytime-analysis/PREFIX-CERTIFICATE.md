# B12: a certified 23-value leading prefix

**Result:** the retained feasible B12 solution attains a lower bound on its first
**23 sorted load values**, at six-decimal comparison precision under the pinned
mathematical ECMP model. Any strictly better full vector must preserve those
23 values. This does not make every named arc invariant, establish a full-vector
optimum, or justify skipping all top 32 coordinates.

This extends the [peak certificate](PEAK-CERTIFICATE.md), reusing its exact
first-departure enumeration. The [timeline](README.md) and all original QUARTZ
solver/checker results remain unchanged. No native solver, official checker,
new instance evaluation, or contest submission is executed here.

## Construction

Use sources **77** and **969** at all **12** time slots. Each source has exactly
two outgoing arcs; none of those four arcs is affected by the retained maintenance
schedule. Node 77's exit capacities are 101 and 114; node 969's are 102 and 111.
These give **24 disjoint coordinate groups**, covering 48 of the checker's
53,448 `(time, from, to)` coordinates.

The original first-departure argument applies separately to each group. Each
positive demand leaving that source places 0, half, or all its volume on the first
exit. The exact rational allocation sets contain 9, 27, or 81 cases, totaling
**630** across the 24 groups. Other traffic and later revisits contribute only
nonnegative additional load. Ignoring cross-slot route-change budgets, reachability
restrictions, and subsequent traffic enlarges the feasible set, so it weakens rather
than invalidates the bound.

For nonnegative exact utilization `x`, define the integer micro-load

```text
Q(x) = floor(1,000,000 * x).
```

For each group, enumerate every first-departure allocation, apply `Q` to both
loads, sort the pair in descending order, and take the lexicographic minimum:

```text
P_g = min_lex { sort_desc(Q(load_0(a)), Q(load_1(a))) : a in group allocations }.
L   = sort_desc(union of all P_g, followed by 53,400 zero coordinates).
```

**Minimize after quantization, not before.** For example, exact pairs
`(1.0000001, 0.9)` and `(1.0000002, 0.1)` favor the first pair before truncation.
After truncation both leading entries are 1.000000, and the second pair is better.
The new consumer explicitly handles this order; it does not merely round the
previous exact peak minimizer.

## Why the merged bound is valid

For a particular actual first-departure allocation, each final arc load is at
least its first-departure contribution. Truncation is monotone on nonnegative
values. Sorting therefore leaves the actual group pair lexicographically no
smaller than the minimum `P_g`. This is a **lexicographic** relation, not a
componentwise claim: `(0.65, 0.4)` is worse than `(0.60, 0.58)` even though its
second coordinate is smaller.

The needed merge lemma is: if descending vectors `A >=_lex B`, merging the same
multiset `C` and sorting preserves that order. To see this, compare multiplicities
from the largest value downward. The largest value where the multiplicities of
`A` and `B` differ determines their lexicographic order. Adding identical counts
from `C` cannot change that first difference. Equality remains equality.

The groups have no shared coordinates. Apply this lemma one group at a time,
replacing its actual sorted pair with `P_g`, and replace all unaccounted nonnegative
coordinates with zero. The full actual vector cannot become larger by these
replacements. Hence **every feasible full vector is lexicographically at least
`L`** under the stated mathematical/quantization semantics. The executable rejects
overlapping group coordinates rather than counting the same arc twice.

The existing checker-valid candidate matches `L` through rank 23. A purported
strict improvement first differing within those ranks would be smaller than `L`,
contradicting the lower bound. Therefore a strict improvement must preserve this
sorted-value prefix.

## Attained prefix and first unresolved rank

The 23 certified values, in descending order, are:

```text
0.629742  0.609075  0.601780  0.587192  0.579471  0.556852
0.550390  0.542913  0.539619  0.521245  0.519111  0.501106
0.499577  0.485619  0.475346  0.474994  0.465707  0.445406
0.436443  0.421139  0.418141  0.393892  0.386673
```

At **rank 24**, this relaxed bound is **0.351129**, whereas the retained candidate
has **0.373232**. That gap is unresolved; the construction does not show the lower
value is jointly attainable. It does not certify ranks 24-32 or authorize ignoring
those ranks.

The feasible witness is the unchanged QUARTZ candidate solution, SHA-256
`a1c4df68fd610c1ca0a65b5a6c7faab03202dfa53e8af2c4fb23c87fc6b83e53`, with
independent six-place checker output SHA-256
`c641183e730a3b7f062ef0428d9a58878f030df8afeb51d075fc0fc38d90cac8`.
Its 53,448 coordinate identities are checked for uniqueness and coverage.
This is a mathematical lower-bound proof matched to retained reported output,
not an exact rational reconstruction of every native routing operation or a
complete native floating-point audit.

## Quantization and source pins

The official source in the existing verified context explicitly truncates output:
`core/json.h` passes the requested decimal places to the writer; RapidJSON's writer
states and implements truncation, and `internal/dtoa.h` removes trailing digits.
Thus nearest rounding must not be substituted in this proof.

The following are exact members of
`ROADEF-QUARTZ-verified-context-2885d176.zip`, SHA-256
`62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`:

| Source member, beneath `context/sources/networktools/networktools/` | Source location | SHA-256 |
|---|---|---|
| `core/json.h` | Lines 98-115, decimal-place forwarding | `e85129d3b82c47f53d1ce9072130da0ecdf7df04b1a923a9f58c19a1d96a5763` |
| `@deps/rapidjson/writer.h` | Lines 152-175 and 369-374, truncation contract and formatter call | `40db14761c8f72d44261553400c24111b64bcc367bd23eeed4c45043ec80b39b` |
| `@deps/rapidjson/internal/dtoa.h` | Lines 154-204, decimal truncation | `73bdbedab68a0647156c918a7c879b7b0f13b88e2de2145c05fd7c65c8970cc5` |

The four ECMP, segment-routing, checker, and maintenance pins from the peak proof
are reused and verified unchanged. The result retains all seven source pins,
three input digests, every allocation, and each group's actual coordinate identities.
No official source or original benchmark binary is copied into this repository patch.

## Executed validation and reproduction

Eight new tests pass. They include the quantization-order counterexample,
**1,800 exhaustive small-domain merge-order comparisons**, an independent
**27-combination joint-product control**, exact truncation, invalid inputs,
overlap rejection, prefix dimensions, and the distinction between lexicographic
optimality and componentwise invariance. These are tests of the new composition;
they do not rerun earlier component suites or benchmarks.

The full archive consumer separately succeeds on all 24 groups and 630 exact
allocations. It verifies the original 169/336 evidence/context payloads and matches
the stated 23-value prefix against the retained official-checker output.

Use the same two Library inputs as PR10273 and PR10315:
`ROADEF-QUARTZ-B12-native-2885d176.zip` (file
`file_00000000320881f78ecce6721df75592`, SHA-256
`1494b0faf268be12b99f25444ce5bd6c42539a187c00ca7ef29f11d24484fd9f`) and
`ROADEF-QUARTZ-verified-context-2885d176.zip` (file
`file_000000008c8481f783a95eb409c035fb`, digest above).

```sh
python -B certify_b12_prefix.py \
  --evidence ROADEF-QUARTZ-B12-native-2885d176.zip \
  --context ROADEF-QUARTZ-verified-context-2885d176.zip \
  --output B12-PREFIX-CERTIFICATE.json
python -B -m unittest -v test_certify_b12_prefix
```

The consumer imports unchanged `minimum_two_link_peak` from `certify_b12_peak.py`
and unchanged archive helpers from `analyze_b12_anytime.py`. It does not introduce
another routing solver or comparator.

Complete `B12-PREFIX-CERTIFICATE.json`: **335,152 bytes**, SHA-256
`34ceb6c6c4f3fd44ead209af1808866cb9451e563bbe34270f459c98aa8cddd7`.
The companion `ROADEF-QUILL-B12-prefix-certificate-20260908.zip` retains the result,
source, necessary unchanged helpers, tests, execution logs, and publication receipt.
The earlier peak/timeline deliveries remain intact with their original hashes.

## Consumer boundary

Root/ATLAS can use rank **24**, not rank 1, as the first rank left unresolved by
this particular proof when comparing improvements over the existing B12 incumbent.
Keep the certified sorted prefix non-worsening, all feasibility and route-change
constraints intact, and the full objective comparison. Do not freeze named-arc
identities or assume a worse solution must share the prefix. No rank-band policy,
restart strategy, or full-vector improvement is validated by this certificate.

Existing algorithm, continuation, kernel, and Docker work stays with its owners.
S139 draft, attachment, and submission hold are unchanged. There is no new native
run, contest upload, workflow, VM, or spending in this delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
