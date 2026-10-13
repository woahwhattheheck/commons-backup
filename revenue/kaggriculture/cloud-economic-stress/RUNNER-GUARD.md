# Stress runner: shared deadline-guard binding

## Change and consumer

`InstrumentedIntegrated` now uses the existing `DeadlineFallbackAgent` for every
non-null `deadline_s`. The adapter itself is unchanged (Git blob
`1c777790cf74cd528461466765c2a48ef49cf191`). The small phase observer forwards to
the already-created production owner and transform; it creates no controller,
policy, timer, process or service. ECON-STRESS/T08 can use the existing runner
command and choose the next ordinary experiment without replacing a live panel.

Original runner blob `01a6e843d93b703d552d2e9f1db72570c81bb832` armed its own timer
only after natural production returned, used a catchable `Exception`, and erased
caller timers. Production-stage injections shorter than the budget also ran a
second time before transformation. The new branch shares one total phase budget,
preserves caller alarms through the existing adapter, and injects a delay only
at its named stage. Old import names point to the shared cancellation helper.

Natural, no-deadline runs retain direct producer/transform execution. The two
explicit production-timeout treatments remain distinct: legacy PASS versus
`terminal_liquidation`. After selection, the exact saved selected action remains
the fallback. Existing row fields are retained; deadline rows additionally state
`fallback_stage`, `selection_completed` and `deadline_binding=shared-guard-v1`.
The existing `selected` field contains the fallback on an incomplete selection,
as before, but is now explicitly marked `selection_completed=false`. New reports
include runner/adapter SHA-256 values and the binding label. Historical reports,
source archives, arms and selected defaults are not rewritten or relabelled.

## Executed validation

The canonical before/after suite contains 23 methods. On the original runner,
10 assertions fail and there are no errors or skips. On the new runner all 23
pass. All five unchanged `test_runner.py` methods also pass: 28 final passing
methods, not a sum of repeated checkpoint runs. `RUNNER-GUARD-RESULTS.json`
contains source pins, measured values and original log/report digests.

The 20 focused boundary methods exercise the actual runner with real SIGALRM,
including ordinary and foreign exceptions, caller one-shot/periodic alarms,
one persistent owner, unchanged successful outputs and the two injection stages.
Three additional actual-source methods use the unmodified PR9997 runtime archive
`95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153` and pinned
official interpreter. Six guarded decisions match six direct controls, with
exactly one real producer/controller/transform invocation per decision and six
completed official transitions across both seats. Two real-transform delay cases
return the selected action and identify the transform stage. Two manufactured
bookkeeping calls enter the actual unchanged `PlanOverlay._commit` handler;
cancellation crosses it before an errand is committed. These latter calls are
controlled method invocations, not naturally selected errands or new games.

In the final controlled production probe, a 40 ms budget allowed the original
120 ms producer to finish (120.442 ms observed); the new runner interrupted it
at 40.344 ms. The transform swallowing probe changed from zero recorded timeouts
to one. These controlled delays demonstrate the boundary repair, not an ordinary
performance speedup. There are no new full games, random seed draws, held results,
leaderboard measurements or policy-strength claims.

## Reproduction using existing inputs

Boundary-only, on Linux/main-thread SIGALRM:

```sh
python -B revenue/kaggriculture/cloud-economic-stress/test_runner_guard_join.py \
  --report /tmp/stress-join-boundary.json
```

For all 23 new methods, reuse existing artifact `10037676771` (its member
`integrated-selected-v1.tar.gz`) and Library `TITAN-DELVE-funded-seed-evidence.zip`
(SHA-256 `aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`).
After extracting these existing archives into `$FROZEN` and `$DELVE`:

```sh
python -B revenue/kaggriculture/cloud-economic-stress/test_runner_guard_join.py \
  --runtime "$FROZEN" --engine "$DELVE/engine/engine" \
  --frame-stream "$DELVE/evaluation/v2-seed2-p0-control/9965019-p0-control.frames.jsonl.gz" \
  --report /tmp/stress-join-actual.json
(cd revenue/kaggriculture/cloud-economic-stress && python -B -m unittest -v test_runner)
```

The actual-source test verifies every runtime-manifest entry, reads only the
retained initial frame, and takes three short continuation transitions per seat.
It does not reinitialize a game, replay a completed panel or infer a new seed.
The input is the already-exposed DELVE development state, not a fresh held state.
To reproduce original failures, use `--runner` with original runner blob above
and the same unchanged current adapter alongside it. Full original/final logs,
reports and exact sources are retained in the associated Library evidence package.

## Limits

This is a synchronous main-thread POSIX signal guard, not a hard real-time or
cross-platform process deadline. It retains the runner's configured phase budget
with zero extra reserve; observation copying, fallback preparation and reporting
are not all inside the alarm scope. Cancellation does not roll back producer
state. Unknown caller cancellations are propagated, not converted into success.
Actual-source compatibility is pinned to PR9997's frozen closure, not a claim to
have tested every later current-main optimization. The adapter's prior timer
proofs, frozen game outcomes and other workers' suites were reused, not reminted.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
