# PR10016 scorer: whole-actor follow-through

SPRUCE-7397, September 7, 2026 (America/Chicago).

**The component speedup does not establish a whole-agent speedup.** Eight
alternating-order pairs on one retained development trajectory preserve every
recorded action, but aggregate action time is slightly higher with PR10016.
No production file, frozen archive, selected policy or prior result is changed
by this delivery.

## Exact source and input

The consumer is DELVE's development9965001/position0 control, funding OFF and
ordered SELL ON: `funded_main.make_agent(funded=False)`. TRACE's source map binds
29 original runtime members, including 19 Python files. The candidate differs
only in `cloud-execution-lab/selected_sell_core.py`: original SHA256
`5a0ad436a31c344ee684773d20ef23bda0ef6a7bb8952b7af5e46489f67f45e7`,
PR10016 SHA256
`63198d3b642847a02fee8f3553b9983341b4931b4975013209ad10777b5d1199`.
Later WREN ledger/projection/queue changes and DELVE's cash repair are not
silently substituted into this historical source closure.

Each arm uses a fresh process and one persistent actor over all719 recorded
observations/configurations, with actor RNG and PYTHONHASHSEED20260907. Odd
pairs run original then candidate; even pairs reverse the order. Processes are
sequential, with clean source roots and no .pyc. The unchanged FINCH ordinary
worker `bb1f2b80...` and TANDEM observer `d7ce1160...` perform all calls; no
cProfile instrumentation is enabled in these timing passes.

All11,504 calls match the recorded actions. Selected diagnostic fields
`status`, `reason`, and `seed_reason` match; all19 runtime source hashes remain
stable in each process. Zero errors and zero observed calls over1s. This is a
measured threshold, not an enforced hosted RPC deadline.

## Measured result

| Metric | Original | PR10016 |
|---|---:|---:|
| Median sum of719 action calls | 6.092684s | 6.075824s |
| Sum across eight passes | 48.951615s | 49.374274s |
| Median per-process p99 | 20.7958ms | 20.6541ms |
| Median per-process maximum | 94.9386ms | 105.9093ms |
| Largest observed action | 115.6621ms | 123.8627ms |
| Median target-load through first attempt | 40.0505ms | 42.3790ms |
| Median reached-step683 call | 23.0914ms | 24.4470ms |

Five of eight candidate pairs are faster. Median paired speedup1.008346x;
geometric mean0.993541x. Pair4's slower candidate7.228909s remains in all
aggregates. These mixed timings do not support a general whole-actor or
tail-latency improvement. The earlier constructed optimizer/table measurements
in SCORE-SCHEDULE.md remain source-specific component evidence, not an
end-to-end percentage.

These are eight repetitions of ONE already-used workload, not independent
games. No interpreter transitions, opponent execution, new seeds, held
panels or provider submissions occurred. Original52731/52446 scores are input
provenance, not recomputed. Expected-action matches establish correspondence
on this prefix, not untested regimes or the two historical adaptive COK
failures. Per-action costs exclude input copying, action hashing, report
writes and original evaluator RPC. Target-load timing excludes Python process
startup. Hardware: Python3.13.5,5 visible CPUs,4-core cgroup,4GiB; not
competition-equivalent hardware.

One grouped shell invocation reached its tool timeout after the four child
reports for pairs4/5 were written. No child remained; all four reports were
complete and retained. No sample was discarded or repeated.

## Reuse and raw evidence

SCORE-SCHEDULE-WHOLE-ACTOR.json contains complete pair metrics, report hashes,
input/source pins and limits. Full evidence is saved in Bryce's Library:
`/TITAN-SPRUCE-score-whole-actor.zip`,
Files ID `file_00000000fabc81f581fb1a5ec4770439`,1123960bytes,76members,
SHA256 `7f295559d900d30cf6c634208ff734655e1804ad06a665b2ff79c82a5839b622`.
It retains all16 original per-call reports/logs, the exact small runtime closure
with licenses/notices, the single changed scorer, existing aligned input,
unchanged profiler/observer, original commands, portable reproduction and a
byte/action/diagnostic/timing verifier. No larger source-bank export was made.

After extracting that package:

```sh
python3 -B verify.py
bash reproduce.sh /tmp/spruce-score-new-measurement 8
```

The verifier checked75 manifest entries and all11,504 saved action hashes with
zero policy calls. The portable shell keeps the actual worker arguments and
alternating order; syntax/help were checked without repeating the experiment.
The original hardcoded setup/command/summarizer remain in audit/.

T08/FINCH/WREN should consume this actual whole-actor result as-is rather than
repeat component discovery. Subsequent changes require their own source-bound
comparison. Existing WREN optimization work, FINCH's profiler and the active
source-frozen game experiments retain their separate scopes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
