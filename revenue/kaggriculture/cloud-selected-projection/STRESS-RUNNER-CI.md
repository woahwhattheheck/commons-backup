# Actual stress-runner tests in the existing focused workflow

PR10122 joined the actual economic stress runner to the existing deadline guard.
The prior `titan-selected-projection.yml` did not trigger on the runner or its
new test file and did not check them out. This follow-through binds the actual
consumer tests into that same workflow; it introduces no new workflow, exporter,
runtime implementation, policy, game panel or package builder.

## Coverage and counting

The existing `test_runner_guard_join.py` CLI runs its 20 boundary methods with
real POSIX timers. Its optional three retained-state/official-engine methods are
not run by this hosted command and must not be counted in this hosted result.
Their prior source-specific local execution remains documented in
`cloud-economic-stress/RUNNER-GUARD.md`.

Of the five original `test_runner.py` methods, three guard methods are already
AST-selected unchanged by the existing cancellation suite. That command remains
untouched. The added runner step invokes only the two other original methods:
`test_known_order_cost_keeps_sequence` and `test_summary_counts_cash_and_timeouts`.
All five original methods therefore remain covered without running three twice.
The unchanged cancellation suite retains its existing separate count.

A third added step runs 13 report-binding fixture methods, separately from the
34 unchanged existing report tests. Thus this change adds 20 + 2 + 13 = 35
method invocations to the then-current workflow, not 38 and not a replay of the
historical 210 methods. The actual hosted total must come from that run's logs;
concurrent source/test changes can alter the pre-existing count.

## Source binding and failure behavior

The existing reporter gets one opt-in `--include-stress-runner` flag. Its three
new suite rows bind logs to the same source snapshot as the old rows. Boundary
JSON additionally binds the executed runner, adapter and test SHA-256 values,
requires empty failure/error/skip arrays, and checks JSON/log count agreement.
It requires `actual_source=false`, integer `full_games=0`, and an empty seed list
so a local actual-state result cannot be relabelled as this hosted boundary run.
Missing logs remain an incomplete/unsuccessful result; original JSON bytes are
read, not rewritten. Existing flags, schema and result fields retain their prior
behavior when the new flag is omitted.

The workflow adds two trigger and sparse-checkout paths, three focused steps,
and the flag on the existing final report command. All pre-existing test commands,
source-snapshot code, permissions, timeout, frozen archive pin and upload step
remain unchanged. The already-listed source roots capture the new file bytes.

## Executed local checks

The complete 47-method reporter suite passes: 34 unchanged methods plus 13 new
fixture methods. The new fixtures separately test successful counting, opt-in
compatibility, runner/adapter/test mismatches, invalid counts, failure/skip arrays,
local/hosted boundary distinctions, missing logs/source rows, malformed JSON,
deterministic read-only results and the actual CLI's success/failure exits.
The original reporter does not support the new API/CLI flag; its original failing
fixture output is retained rather than described as gameplay evidence.

Each of the three exact new YAML commands was executed from a minimal local
source checkout and passed: 20 runner-boundary, two original runner and 13 new
reporter methods. The workflow comparison confirms that only checkout and the
final report command changed among existing steps. Reading the preserved real
artifact10037676771 with the old and new reporter (old flags) yields identical
successful 210-method reports. This is reader compatibility, not new execution
of those historical tests. No games or new seeds were used.

Reproduction from the repository:

```sh
cd revenue/kaggriculture/cloud-selected-projection
python -B -m unittest -v test_combined_report test_stress_runner_report
```

The ordinary pull-request-triggered `titan-selected-projection` job is the
source for the actual new combined hosted result. Its `SOURCE-SNAPSHOT.json`,
all individual logs, boundary JSON and `COMBINED-RESULTS.json` travel through the
existing artifact upload. A green generic repository guard alone is not proof
that these focused commands ran. The canonical TITAN builder and ECON-STRESS
should consume the actual focused artifact on its recorded merge/source commit;
do not restart or relabel active policy experiments.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
