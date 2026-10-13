# Frozen A04/A14/A16 qualification-budget execution

On 2026-09-08, the three assigned cold runs all remained behind the published
sprint reference at rank 1. The longer allowance alone closed none of these
peak gaps. A04 and A14 exhausted their lanes naturally; A16 used its search
allowance. This is measured public-case evidence, not a qualification rank.

| Case | Selected lane | Full loads | Candidate / reference at rank 1 | Portfolio wall (s) | End |
| --- | --- | ---: | --- | ---: | --- |
| A04 | candidate | 500 | 0.587276 / 0.581237 | 33.4798 | All three lanes exit naturally |
| A14 | candidate | 2216 | 0.533147 / 0.517621 | 68.4253 | All three lanes exit naturally |
| A16 | SEDGE | 2904 | 0.079918 / 0.044262 | 565.2062 | Internal search deadline at 565.0969 s |

Every output passes independent official six/twelve-decimal checking, with
complete matching coordinate sets. Six final checker calls exit zero and
byte-match the six original reports. Six-decimal ranking uses the unchanged
frozen exact Decimal reader and complete, equal-length reference vectors.
Twelve-decimal output is a validity diagnostic, not a different ranking rule.
Costs 44/13/12 are diagnostic. No result was chosen from repeated solver runs.

## Frozen source, inputs and actual allocation

Coordinator manifest `6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055` and the exact
B01–B04 context/binaries are reused. Candidate source SHA-256 starts75897709,
supervisor18237165, readera402a016. Exact binary/source hashes are in RESULT.json.
The complete reusable context is B01 Files item
`file_00000000187081fda7be9bc7faf7d292`. Original SEDGE/FLORA/Orange and
WREN/DELVE/KESTREL/CEDAR-JOIN attribution is retained.

All nine input files are extracted unchanged from official commit
`d84d319a7fdb8de3b1866830d2eaa2937871e5ae`, verified archive SHA-256
`e03b9ebf266755097e236d880830631574f528b872e44b67dc45af4796bd5ca8`.
Reference CSV SHA-256 is
`b6218e41ac204e73c4688aa9e0e56825c1f5b864440675c4f7ffba27a75f45ca`.
The harness records input identity separately from the generic comparator,
which correctly does not claim to establish input provenance itself.

Each case starts cold with PORTFOLIO_SECONDS585, internal search565,
FLEET_DIRECTED1/FLEET_JOINT1/FLEET_WAYPOINT_LIMIT0 and no initial solution.
No outer TERM-at-590 or KILL-at-600 signal fired. The existing worker has an
8-CPU quota and 20 GiB memory limit. At most two portfolio cases ran together:
A04+A14 from 07:37:52 UTC; A16 started at 07:38:26 after A04, overlapping
A14 until 07:39:01; A16 ended at 07:47:51. Exact intervals are retained.

| Resource | A04 | A14 | A16 |
| --- | ---: | ---: | ---: |
| Observer wall (s) | 33.676236 | 68.838863 | 565.373498 |
| Sampled process-tree peak RSS (KiB) | 23136 | 83572 | 126660 |
| Waited-child user CPU (s) | 95.599013 | 110.756729 | 1596.116803 |
| Waited-child system CPU (s) | 0.103478 | 0.202902 | 1.980210 |
| Maximum observed processes | 5 | 5 | 6 |
| Missing/racing process entries | 0 | 0 | 0 |

Half-second process-tree RSS samples exclude page cache and unsampled peaks.
Ordinary evidence processing also used the worker. Historical reference budgets
are unmatched; no dedicated-host, equal-work, Docker or speedup claim is made.

## Retained evidence and execution contract

Claim `1788852707.332779` implements root's three-case time-extension assignment
at `1788852647.403219`. Eligibility comes from the coordinator's retained-log
readback `1788852842.488019`: original run34197333541/artifact10044706015
recorded search-budget stops for these source-identical cases. That witness
remains separate from the later calibration run34197720573/artifact10044831235;
no outputs are pooled or selected between the historical executions.

The raw archive preserves all checkpoints, official vectors, inputs, source
identities, commands, resources, original and corrected harnesses, and licenses:
`ROADEF-QUARTZ-A-budget-75897709.zip`, file
`file_000000008cfc81f59b7ac6a240572622`, version0, 4651078 bytes, SHA-256
`5b6b53ecfa74a1b7c0ac911b64534e0a0bd224038a3f99564074eb9c55174a0f`.
All486 local payload hashes and saved size are verified. Independent saved-file
readback status is recorded separately in RESULT.json.

The first wrapper setup stopped before solver launch because the artifacts
parent was absent; those subsecond records remain in results/. Actual cases
each ran once in execution/. Report finalization now reads twelve-decimal
diagnostics separately from the frozen six-decimal ranking parser. Saved reports
were finalized without solver repeats; final checker exit codes were captured
in six additional verification calls, all byte-identical to the originals.

`run_budget.py` consumes the frozen context, pinned inputs/reference, observer
and source-bound eligibility JSON. It creates a fresh output directory and runs
at most two cases concurrently. `summarize_saved.py` only consumes retained
outputs and recorded final checks, invoking zero solver/checker calls. The
archive includes the exact commands and final verification helper. Focused
diagnostic checks accept the actual twelve-decimal report and reject a missing
coordinate; current source compiles.

PRISM-RANK1 retains A04/A14/A16 diversion/mechanism work; COORD-PLATEAU retains
A07/A13. No frozen runtime, selected default, package selection, S139 draft or
attachment, submission or organizer message changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
