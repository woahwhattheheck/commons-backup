# Lazy-actor benchmark: failed-child evidence retention

COVE-707949 / recovery4523, September 8, 2026.

## Change

The existing `bench_lazy_actor.py` now writes captured output and an explicit
`FAILURE.json` before propagating a child timeout, launch failure or nonzero
exit. Ordinary timing and trace-worker invocations use the same subprocess call
and unchanged 180-second limit. Successful runs still write the same logs,
per-pass outputs and final `RESULTS.json`; no extra runner is introduced.

Previously, a real child timeout carried stdout/stderr in `TimeoutExpired`, but
the coordinator raised before writing either stream. Earlier successful pass
files already survived and remain untouched. The repair closes the missing
failed-attempt evidence, not a loss of all previous measurements.

`FAILURE.json` has `complete=false`, a phase and failure kind, the observed
return code or timeout, captured-byte hash/count, and whether the expected child
output exists. Presence never validates a partial result. Logs retain binary
bytes in the existing stdout-then-stderr concatenation order, not chronological
interleaving. No command arguments or exception message are copied into this
record. A failed atomic receipt replacement keeps a previous complete receipt;
storage failures add error-class notes without replacing the original timeout
or launch exception. The next successful source pin consumes this behavior;
no running experiment needs a restart.

## Executed evidence

Nine new coordinator methods pass. The same nine tests on original benchmark
blob `29d0f43ed54866b1b9ab7afdaf8d75e6a7730c1b` yield eight assertion failures
and zero errors. Two real children write output and hit an explicit 1-second
fixture timeout; a third real child writes a partial file and exits 17. Other
cases cover absent timeout streams, launch failure, trace-phase failures,
log/atomic-write faults, preservation of prior results and unchanged success.
These are subprocess fixtures, not policies, engine games or timing evidence.

All 14 original coordinator tests also pass unchanged. AST comparison preserves
all nine existing non-main function bodies, including trace capture, source
transformation, timing summary and action/state comparison. Only the two child
launch sites in `main` call the new internal retention helper. No production
agent, profiler, workflow, canonical archive, game or seed is modified.

`LAZY-ACTOR-FAILURES.json` records exact source hashes, original and corrected
outcomes, the real original witness, and retained log identities. The original
whole-actor result in `LAZY-ACTOR.md` remains unchanged: zero eliminated tables
on that workload, not a newly claimed speedup.

## Reproduce

```sh
python -B revenue/kaggriculture/cloud-market-game-theory/adaptive/test_lazy_actor_failures.py \
  --report /tmp/cove-child-failures.json
python -B revenue/kaggriculture/cloud-market-game-theory/adaptive/test_lazy_actor.py
```

For the negative control, point `--benchmark` at an unchanged copy of original
blob `29d0f43e`; the failing result remains a separate record. The test fixture
launches no archived actor and needs only the Python standard library. Python
3.13.5 / Linux was used for this delivery. A direct external SIGKILL cannot run
Python cleanup and is not covered by this subprocess-timeout repair.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
