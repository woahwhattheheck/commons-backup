# Critical-rank-band results

## Result

The source-fixed expanded-rank continuation found an official-vector improvement that the equal-allowance top-32 control did not find.

The exact starting point was QUARTZ's completed B12 portfolio output:

```text
solution SHA-256 a1c4df68fd610c1ca0a65b5a6c7faab03202dfa53e8af2c4fb23c87fc6b83e53
valid at 6 and 12 decimal checker settings
six-decimal peak 0.629742
diagnostic transition cost 50
```

### Fixed 64 rounds

| Arm | Rank limit | Rounds | Attempts | Accepted | Deepest zero-based rank | Band visits | Band accepts | Wall seconds | Official result |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |
| control | 32 | 64 | 4,256,279 | 0 | 31 | `[64]` | `[0]` | 33.6745 | incumbent unchanged |
| expanded, GCC | 128 | 64 | 1,161,637 | 2 | 32 | `[63,1]` | `[0,2]` | 11.2785 | wins at rank 33 |
| expanded, Clang | 128 | 64 | 1,161,637 | 2 | 32 | `[63,1]` | `[0,2]` | source/counters/output byte-identical to GCC |

At the first newly opened coordinate, zero-based rank 32, the expanded arm accepted two route changes. The six-decimal official saturation vector first differs at one-based rank 33:

```text
control   0.296067
expanded  0.294548
```

Peak and diagnostic cost remain `0.629742` and 50.

The fixed-round runtime difference is reported, but it is not treated as an isolated speed result: the accepted moves change subsequent search work.

### Equal 34-second pair A — expanded then control

| Arm | Attempts | Accepted | Rounds | Deepest rank | Band visits | Band accepts | Cost |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| top-32 | 4,255,889 | 0 | 64 | 31 | `[64]` | `[0]` | 50 |
| expanded | 4,031,310 | 41 | 341 | 32 | `[339,2]` | `[31,10]` | 56 |

Official vector first difference, rank 33:

```text
control   0.296067327102  (t=4, 84→75)
expanded  0.294532344587  (t=6, 978→1054)
```

At six decimals this is `0.296067 → 0.294532`. Peak remains `0.629742`.

### Equal 34-second pair B — control then expanded

| Arm | Attempts | Accepted | Rounds | Deepest rank | Band visits | Band accepts | Cost |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| top-32 | 4,181,362 | 0 | 63 | 31 | `[63]` | `[0]` | 50 |
| expanded | 4,178,909 | 42 | 351 | 32 | `[349,2]` | `[32,10]` | 62 |

The official vector again first improves at rank 33, `0.296067 → 0.294532`, with unchanged six-decimal peak.

The two expanded timed solutions are not byte-identical: their first mutual vector difference is later, at rank 1,631. Both independently beat the top-32 incumbent at rank 33.

## Validation boundaries

- Original fleet source: Commons `2885d176373c33410148829fef93c310c3752c0b`, SHA-256 `322ec2e6…`.
- Candidate transformed source: SHA-256 `f3c76d2a…`.
- Official checker source: challenge commit `d84d319a…`, Networktools `aebafc9e…`.
- B12 net/TM/scenario hashes match the retained QUARTZ receipt.
- `moveTogether`, `routeFlow`, `distance`, `contributors`, `waypointCandidates`, `eject` and `writeSolution` function bodies remain byte-identical.
- Default `rank_limit=32`, `stall_limit=64` matches original solutions and core statistics over all retained focused cases.

## Interpretation

The result is causal at the mechanism level: the top-32 control repeatedly exhausted the incumbent without an acceptance, while the first deeper coordinate produced accepted changes and a better official vector. The deeper changes also unlocked additional improvements back in the top band during timed runs.

It is still a single-instance development experiment. It does not establish that rank 128 is optimal, that every instance benefits, or that the variant should replace the current solver. Later canonical optimizations are deliberately not folded into this evidence. S139 remains unsubmitted.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
