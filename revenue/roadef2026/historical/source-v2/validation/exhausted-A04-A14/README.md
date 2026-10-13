# Historical V2 temporal OFF/ON exhausted-incumbent diagnostic

On 2026-09-08, QUARTZ ran the assigned resumed diagnostic against the exact
historical ASTRA-DOCK V2 source recovered by PR #10453. A04 ran temporal OFF
then ON; A14 ran temporal ON then OFF. The four arms were strictly sequential
on one existing 8-CPU/20-GiB cloud worker and used the same compiled binary.

Temporal search changed neither incumbent. With `FLEET_TEMPORAL=1`, V2 tried
320 temporal candidates on A04 and 190 on A14; it accepted zero and aborted
zero. Each enabled arm produced the incumbent byte-for-byte. Disabled arms did
the same. ON and OFF tie over all 500 A04 loads and all 2,216 A14 loads at both
the frozen six-decimal comparison and the twelve-decimal diagnostic.

| Case | Arm order | OFF / ON temporal attempts | Temporal accepted | Six-decimal MLU | Twelve-decimal MLU | Retained |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A04 | OFF, ON | 0 / 320 | 0 | 0.587276 / 0.587276 | 0.587276923076 / 0.587276923076 | incumbent |
| A14 | ON, OFF | 0 / 190 | 0 | 0.533147 / 0.533147 | 0.533147771569 / 0.533147771569 | incumbent |

All four processes exited zero after natural exhaustion in 0.502-2.006 seconds,
well before the external 65-second guard. All eight raw official checker calls
(six and twelve decimals for four arms) and all eight retained-solution calls
exited zero and reported valid, with complete matching coordinate sets. Since
no raw output strictly improved its six-decimal incumbent, the harness retained
the read-only fallback in every arm.

## Execution contract

The runner materializes immutable fallback copies and invokes the historical
V2 binary with four positional input/output arguments. Each arm uses
`SEDGE_SECONDS=60`, `FLEET_TEMPORAL=0/1`, `FLEET_TEMPORAL_ROUTES=12`,
`FLEET_DIRECTED=1`, `FLEET_JOINT=1`, `FLEET_WAYPOINT_LIMIT=0`,
`OMP_NUM_THREADS=1`, the exact fallback through `CLOUD_INITIAL_SOLUTION`, and a
per-arm `SEDGE_STATS`; `SEDGE_MAX_ROUNDS` is unset. An external TERM-at-65 and
KILL-after-five-seconds guard surrounds each run.

Exact source identities are `main.cpp`
`4e0c328d28e053d335328ac520cb21825601d9cabd9d0bba8015634d5919393d`
and `temporal_dp.hpp`
`a9db8fc26acc6f4127640f306dd12ff61a2726e5b5edc5b4c53d1fb6225fca8b`.
The one built binary is
`d3d2edc494d325ab781fb1d15d192cab10d6b576ddb4f93ff219cf37bbe5ce22`.
Official checker identity is
`7227194df604d627720938b163b3d63baaba5a090ed90bff574e7e26af69149a`.

`RESULT.json` is the compact result record and `run_pair.py` is the exact
executed harness. The raw 92-file archive, including inputs, sources, binary,
commands, stats, stdout/stderr, solutions, all checker reports, resources and a
per-file hash manifest, is `ROADEF-QUARTZ-DOCK-V2-A04-A14-20260908.zip`, Files
item `file_00000000717c81f5aecd2e72be602083`, 589,103 bytes, SHA-256
`a69ceb776744df63bc7daf129aef213a98fee0dc4ce440881584b73f49e4138d`.

## Scope and attribution

This executes the coordinator request at `1788858119.221029` under QUARTZ claim
`1788859227.354099`. ASTRA-DOCK retains authorship of the temporal V2 work;
QUARTZ provided the verified context and source recovery, and QUARTZ performed
this diagnostic. Existing SEDGE, FLORA, root directed/joint, Orange SA checker,
Networktools, RapidJSON and other dependency attribution remains unchanged.

This is public-case mechanism evidence only. It is not a cold run, hidden-rank
forecast, selected-policy recommendation, package selection, S139 change or
submission. No runtime/default, qualification artifact, organizer/customer
message, or incumbent was changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
