# B12 peak bound from one two-exit node

**Result:** under the pinned one-path-per-demand, equal-next-hop ECMP model, the
maximum link utilization on `setB-12` is at least

```text
127207967 / 202000000 = 0.6297424108910891089...
```

The retained feasible candidate reports `0.629742410891` at 12 decimal places
and `0.629742` at six. Thus its peak matches the mathematical bound to checker
reporting precision. This is a **peak-only certificate**, not an optimum for the
full lexicographic load vector. The [existing timeline](README.md) still shows
useful later-rank improvements long after this peak was reached.

No solver, official checker, native binary, or new benchmark is executed by this
consumer. It reads QUARTZ's original B12 evidence and pinned official source. The
proof is new analysis of that existing instance, not another experimental sample.

## Fixed boundary

At zero-based time slot **7**, node **77** has exactly two outgoing arcs; neither
is affected by that slot's maintenance interventions. Capacities and metrics come
from the retained `inputs/setB-12-net.json`; demand volumes come from the same
archive's `setB-12-tm.json`, with slot selection from `setB-12-scenario.json`.
The executable checks these identities rather than assuming every instance has
this structure.

| Arc ID | Direction | Capacity | Positive metric |
|---:|---|---:|---:|
| 2945 | 77 to 83 | 101 | 500000 |
| 2946 | 77 to 84 | 114 | 500000 |

These are all three positive demands originating at 77, with distinct destinations:

| Zero-based demand index | Destination | Volume at slot 7 |
|---:|---:|---:|
| 976 | 133 | 88.898232 |
| 4410 | 1117 | 38.309735 |
| 14435 | 844 | 2.455752 |

Total originating volume is `129.663719`. Dividing by combined exit capacity gives
only the weaker continuous cut relaxation `129.663719 / 215 = 0.603087065116...`.
That relaxation allows arbitrary splitting. The actual equal-next-hop rule does not.

## Proof

Each demand has one segment-routing path, not an arbitrary mixture of independently
weighted paths. At its first nontrivial departure from its source, its entire volume
is routed to the next waypoint. A unique shortest path takes one exit; ECMP splits
equally among the eligible next-hop arcs. There are only two exits, so the fraction
on 77-to-83 is necessarily **0, 1/2, or 1**. A direct arc segment, where permitted,
also falls within this set. Zero-length leading waypoints can be skipped because
the distinct destination requires an eventual departure. [S1, S2]

All active metrics are positive. Shortest-path distance therefore strictly decreases
at every forwarding step within the first segment: that segment cannot return to
the source and cause a new first departure. Later segment revisits and other demands
can only add nonnegative load. Ignoring that additional traffic can only weaken a
lower bound. The official checker routes the full nonnegative demand volume at each
slot; maintenance makes selected metrics infinite and restores them afterward. [S1-S4]

Let `a_i` be the first-exit fraction for the three listed demands, and let `v_i` be
their volumes. Every feasible full solution satisfies

```text
peak >= max(sum(a_i * v_i) / 101,
            sum((1 - a_i) * v_i) / 114),   a_i in {0, 1/2, 1}.
```

Minimize the right-hand side over all `3^3 = 27` combinations. This is a relaxation:
some combinations may not correspond to reachable waypoint choices. Including such
choices cannot invalidate a lower bound. Cross-slot budgets, route-length limits,
and any other feasibility restrictions only shrink the feasible set.

Exact rational enumeration gives the unique relaxed minimizer **(1/2, 1/2, 0)**.
Its two first-departure utilizations are

```text
77-to-83: (88.898232/2 + 38.309735/2) / 101
        = 127207967 / 202000000
        = 0.629742410891089...
77-to-84: (88.898232/2 + 38.309735/2 + 2.455752) / 114
        = 132119471 / 228000000
        = 0.579471364035088...
```

### All 27 cases

Entries are maximum first-departure utilization, displayed to 12 places for
readability. The computation and full JSON store exact numerator/denominator pairs;
no rounded value is used to choose the minimum.

| First demand share | Second demand share | Third: 0 | Third: 1/2 | Third: 1 |
|---:|---:|---:|---:|---:|
| 0 | 0 | 1.137401043860 | 1.126630201754 | 1.115859359649 |
| 0 | 1/2 | 0.969375890351 | 0.958605048246 | 0.947834206140 |
| 0 | 1 | 0.801350736842 | 0.790579894737 | 0.779809052632 |
| 1/2 | 0 | 0.747496517544 | 0.736725675439 | 0.725954833333 |
| 1/2 | 1/2 | 0.629742410891 | 0.641899599010 | 0.654056787129 |
| 1/2 | 1 | 0.819394564356 | 0.831551752475 | 0.843708940594 |
| 1 | 0 | 0.880180514851 | 0.892337702970 | 0.904494891089 |
| 1 | 1/2 | 1.069832668317 | 1.081989856436 | 1.094147044554 |
| 1 | 1 | 1.259484821782 | 1.271642009901 | 1.283799198020 |

## Retained feasible witness and precision

The existing full candidate solution has SHA-256
`a1c4df68fd610c1ca0a65b5a6c7faab03202dfa53e8af2c4fb23c87fc6b83e53`.
Its independent official-checker outputs are both `valid=true` and have the same
53,448 distinct `(time, from, to)` coordinates. The recorded slot-7 utilizations
for these two arcs are `0.629742410891` and `0.579471364035` at 12 places, matching
both relaxed-bound loads at reporting precision. The first is also the full
solution's maximum.

The 12-place peak differs from the exact rational bound by about `8.91e-14`, below
half of one unit in the last reported place. The conservative six-place floor of
the bound is `0.629742`, equal to the feasible witness's six-place peak. This
establishes peak-only optimality at the comparison precision under the mathematical
routing semantics. It is **not** an exact rational recomputation of every route or
a new audit of all floating-point behavior in the native implementation.

The existing 12-place checker file has SHA-256
`09684331f8625fbb28866e89aef7ab38a43706e9d923de853abdefb2f8c3933c`;
the six-place file has SHA-256
`c641183e730a3b7f062ef0428d9a58878f030df8afeb51d075fc0fc38d90cac8`.
No existing result, failure record, or checker output was replaced.

## Source basis

All source references below are exact members of QUARTZ's existing
`ROADEF-QUARTZ-verified-context-2885d176.zip`, SHA-256
`62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6`.
These are the official ECMP, segment-routing, and checker implementations, not an
inferred generic networking rule. Line numbers are for those pinned files.

- **[S1]** `context/sources/networktools/networktools/te/algorithms/ecmp.h`, lines
  98-133: whole-volume unique path; otherwise `node_flow[source] += flow`, then
  divide by the number of equal-cost next hops. SHA-256
  `77a9b11f8d05c38b39272c080266837cbbf2e2fc3a69005f6ab4e82b9c7e43e6`.
- **[S2]** `context/sources/networktools/networktools/te/algorithms/segment_routing.h`,
  lines 669-704 and 869-875: one path per demand, full demand volume passed through
  each segment, with direct-arc traversal or ECMP between node waypoints. SHA-256
  `71497104553ce63680b63cc609d49ab84fc26f30e16830f191b47744881a6d48`.
- **[S3]** `context/sources/checker/src/checker.h`, lines 443-475: slot-specific
  interventions, full-demand routing, validity check, and every per-link saturation.
  SHA-256 `282d78595da31dc0c9d80994f18099008d65bd1bc527a3494ad7a4848f3b43e8`.
- **[S4]** `context/sources/checker/src/helpers.h`, lines 438-457: interventions
  set designated arc metrics to infinity, then restore them at the slot boundary.
  SHA-256 `ece20001ee779eaa0751db600fa5e3d305a7060e8dd2ca6fcc34fe51f6b8b17b`.

The result JSON also retains the three exact input hashes. This proof is tied to
those fixed inputs; it does not claim the same bound for another graph or slot.

## Reproduce

Reuse the same two Library inputs as the timeline, without a new export:
`ROADEF-QUARTZ-B12-native-2885d176.zip` (file
`file_00000000320881f78ecce6721df75592`, SHA-256
`1494b0faf268be12b99f25444ce5bd6c42539a187c00ca7ef29f11d24484fd9f`) and the
verified context above (file `file_000000008c8481f783a95eb409c035fb`).

```sh
python -B certify_b12_peak.py \
  --evidence ROADEF-QUARTZ-B12-native-2885d176.zip \
  --context ROADEF-QUARTZ-verified-context-2885d176.zip \
  --output B12-PEAK-CERTIFICATE.json
python -B -m unittest -v test_certify_b12_peak
```

`certify_b12_peak.py` reuses only the unchanged archive-verification helpers in
`analyze_b12_anytime.py` from PR10273. That file's SHA-256 is
`902368ae6fabd8721174eb8ef49e9ce5f32e140fb438cded0c689a56fe6290c3`.
No optimizer or checker is called. The callable `minimum_two_link_peak` accepts
exact `Fraction` inputs, not binary floats, and bounds enumeration to eight demands.

Executed validation: eight arithmetic/assumption methods pass, covering the B12
minimum, swapped exits, every demand permutation, the weaker continuous relaxation,
a symmetric one-demand control, flow conservation across all 27 cases, and invalid
volume/capacity inputs. The full archive consumer also executed successfully against
169 B12 and 336 context payloads, with all file/source pins and recorded witness
identities checked. Those are reader/proof checks, not new official-checker runs.

Full output `B12-PEAK-CERTIFICATE.json`: **24,746 bytes**, SHA-256
`6da5d88f75d5ed57a09eb416ef66f2eb618e41e24581c81af953a3d975991bd4`.
The companion `ROADEF-QUILL-B12-peak-certificate-20260908.zip` retains this exact
output, executed source/tests, logs, publication readback, and payload manifest.
The earlier timeline archive remains unchanged.

## Next consumer

Root and ATLAS can treat `0.629742` as an attained peak floor for this fixed B12
case and focus their existing comparisons on later coordinates. The certificate
**does not establish invariance of all top 32 coordinates**, justify dropping
feasibility checks, or prove that a rank-band change or restart improves the full
objective. Leave those existing experiments with their owners.

S139 submission hold, draft, and attachment remain unchanged. No solver patch,
new instance run, upload to the contest, or additional spending is part of this
proof delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
