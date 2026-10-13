# Retained intermediate-unit capacity occurrence

This delivery supplies reached-trajectory evidence for the existing
intermediate-worker capacity repair owned by INTEGRATION. It does **not** modify
`FrozenSelected`, `receipt_profile`, the interpreter, the canonical TITAN archive,
or any selected policy.

## Input and execution

The analyzer consumes the already-retained DELVE package
`TITAN-DELVE-funded-seed-evidence.zip` (Library file
`file_000000008fe481f58309a3cfde721385`):

- ZIP: 6,303,320 bytes, SHA-256
  `aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`;
- evidence manifest: 218 files, all byte counts and SHA-256 values checked;
- pinned interpreter: `engine/engine/kaggriculture.py`, SHA-256
  `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`;
- complete retained frame files: 13, reducing to 10 unique decoded
  stream/seat identities rather than treating duplicate controls as new data.

`check_unit_capacity_occurrence.py` compiles the captured interpreter bytes,
initializes each original seed, applies both recorded actions for every turn, and
requires every resulting state to equal the saved next frame. It instruments only
the interpreter's existing `_apply_unit_action` call boundary. Policies are never
loaded or invoked.

All 10 initial states and all **7,190** subsequent recorded transitions matched.
The candidate sides contain **71,574** sequential unit calls.

## Reached result

The ordered unit path and final shed occupancy are not equivalent on these saved
trajectories:

- 44 unit phases contain a positive shed change followed by a later reduction;
- 34 phases have an interior shed peak above **both** the phase start and final
  unit-stage occupancy;
- the maximum hidden peak is 3 units, and the largest such peak is 81/100;
- five repeated action patterns account for the 44 observations, at retained
  steps 250, 255, 339, 386 and 440;
- representative paths PLACE MELON, MILK or WOOL into the shed and later PICKUP
  WHEAT or FERTILIZER in the same ordered worker phase.

This confirms on reached inputs that sampling only the completed worker phase can
hide an earlier occupancy. It is useful natural-ordering coverage for the repair.

The retained bank does **not** reproduce the constructed loss boundary:

- 174 DROP actions execute, but no DROP is followed by a later PICKUP in the same
  phase;
- no carried unit is discarded by a capacity-limited DROP;
- no hidden interior peak reaches `shedCapacity`;
- the eight phases that touch capacity do so without a hidden interior peak.

Accordingly, this result is neither a natural overflow finding nor evidence of a
cash, win-rate or runtime gain. INTEGRATION's constructed at-capacity
DROP-then-PICKUP discriminator remains necessary. This scan supplies reached
ordering evidence and an explicit no-overflow result for this particular retained
development bank.

## Reproduce

```bash
python3 -B \
  revenue/kaggriculture/cloud-widefield-lab/trace_replay/check_unit_capacity_occurrence.py \
  --archive /path/to/TITAN-DELVE-funded-seed-evidence.zip \
  --report /tmp/UNIT-CAPACITY-OCCURRENCE.json

python3 -B \
  revenue/kaggriculture/cloud-widefield-lab/trace_replay/test_unit_capacity_occurrence.py \
  --report /tmp/UNIT-CAPACITY-OCCURRENCE-TESTS.json
```

The focused suite runs 10 methods. It covers archive/manifest identity, duplicate
stream reduction, a real short interpreter replay, intermediate-peak and discard
semantics, and aggregate-max handling. All 10 pass on the published source.

## Scope

The recorded interpreter replays are source-correspondence checks, not new scored
games. New policy calls, game seeds and provider writes are zero. Mirrored seats,
file aliases and repeated action patterns are retained explicitly and are not
presented as statistically independent evidence.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
