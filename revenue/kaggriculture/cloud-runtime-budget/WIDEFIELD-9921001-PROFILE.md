# Original PR9997 development-input profile

FINCH consumed TRACE-9022's delivered original WIDEFIELD input, rather than
reconstructing another trajectory or simulating another game. The existing
profiler with DELTA PR10118/PR10135 source fixes and TANDEM's unchanged timing
observer was used without implementation changes.

## Completed result

Both fresh persistent actors reproduced **all 719 original actions**, with zero
mismatches or failures, and identical action sequence SHA256
`bda35420e2d9c926ceb0855e8ebb4a40284196294644da0f597b9fb3187d6860`.
All 17 Python runtime files remained unchanged. The 26 runtime-manifest members
and all 18 input-package members were verified before execution. This closes
the original PR9997/Apex9921001 observation-stream to actor-parity handoff.

Ordinary direct-call measurements in this cloud container:

| Boundary | Measured time |
| --- | ---: |
| Target source loading through first action attempt | 40.203 ms |
| Factory initialization | 38.753 ms |
| First action, observer boundary | 0.824 ms |
| Per-action p99, outer call boundary | 22.709 ms |
| Slowest outer call, step 661 | 92.774 ms |
| Original WIDEFIELD slowest-step locator, 626 | 11.699 ms |
| Step 683 | 26.143 ms |
| Final step 718 | 5.060 ms |

Zero calls exceeded one second. Python was 3.13.5, Linux x86_64, 5 logical CPUs
visible, CPU cgroup400000/100000 (4 CPUs worth), memory limit4GiB. Peak ordinary
process RSS201568KiB. Total process7.119s includes input parsing and serialization;
it is not a cold-action time. Target-load timing excludes interpreter startup,
input parsing and timing-helper import. No hosted deadline was enforced.

The original WIDEFIELD index retains its maximum292.414ms at626 and56.333ms
at683. These differ from the present measurements; different machines, caches,
load and call boundaries mean the difference is **not a speedup claim**.

## Sampled attribution

The separate profiled actor replayed the entire prefix but instrumented only
steps0,650,652,654,660,661,683,697,718. Its actions matched both the ordinary
actor and every original expected action. Across those nine sampled calls,
`ProjectionLedger.feasible` received769 calls/327.640ms cumulative, `score`
received3717/106.867ms, `_projection`9/104.401ms, and the producer9/225.204ms.
These nested cumulative costs overlap. Do not add them or extrapolate the
sample to every call. This is concrete input for existing runtime owners,
not permission to transfer their component percentages to the whole actor.

## Exact inputs and repeat command

Input Library file: `file_00000000b4bc81f5af377ed01c1596fb`,
`TITAN-PR9997-original-actor-inputs-9921001.zip`,401280 bytes,
SHA256`50fcdcd55132610f9b171a4d212101ba4ff09b5b6786ef936e1d5aa61f0491aa`.
Original trace`f4681e20d6bf54598d330c90ff29dc477d4dd9e790d29a3df05d2b1863d86ed3`;
original recorded scores75095/78506 are provenance, not newly computed scores.
The input receipt provides actor random/PYTHONHASHSEED20260907. No environment
seed or opponent-private state is supplied to the candidate.

Runtime is the **unchanged** PR9997 archive,103527 bytes,
SHA256`95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153`,
source843f6dbb7d564204802d54e1611fe912aea497df, mainb15af384.
The existing artifact10036877991 contains that archive. Do not substitute current
main or a funded variant. Profiler Git blob8ae01c736bd44ffc424f91f657c2861126115d24;
timing source SHA256d7ce11607deb9e3cdfece07ffc1483a789a4eeb2313643b9f88ff97f8f907c13.

With the input, runtime and profiler unpacked into separate directories:

```sh
python -B "$PROFILER/profile_saved.py" \
  --entrypoint "$RUNTIME/integrated_main.py" \
  --timing-source "$PROFILER/execution_timing.py" \
  --replay "$INPUT/candidate-inputs.jsonl.gz" \
  --input-receipt "$INPUT/recovery-receipt.json" \
  --source-root "$RUNTIME" --seat 0 --profile-slowest 7 \
  --classification original-pr9997-widefield-9921001-source-parity-required \
  --process-timeout 120 --output "$NEW_OUTPUT/original.json"
```

The accompanying JSON preserves exact values and report hashes. Full reports,
executed profiler/timing bytes, runtime source map and input receipt are saved
in `TITAN_FINCH_original_PR9997_profile_9921001.zip` in Library. Original input,
engine and runtime archives are referenced, not copied into a replacement pack.

## Scope

1,438 actual candidate calls, zero new games or engine transitions. The two
passes are one retained development regime, not independent game samples.
Complete external-action correspondence supports an on-policy saved-input
workload for this historical source; it does not prove equality of every internal
field, current-candidate strength, hosted runtime, or future deadline behavior.
TRACE owns recovery; DELTA owns profiler repairs; runtime optimizations and the
canonical checkpoint stay with their owners. No source or workflow change is
included in this result delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
