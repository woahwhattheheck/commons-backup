# Preserve report bytes from timed-out profiler processes

Operation: `astra-delta-profiler-timeout-evidence-20260908-01`.
Consumer: the existing FINCH/TRACE `profile_saved.py` CLI. This changes no game,
actor policy, saved observation, source loader, or timing observer.

## Behavior

When a worker times out, the supervisor retains any existing child-output bytes
in `<basename>.ordinary.timeout.bin` or `<basename>.profile.timeout.bin` before
writing its process-timeout envelope. `timed_out_child_report` identifies the
retained path, byte count, and SHA-256. The bytes are not parsed, normalized, or
claimed complete; a valid child report, a truncated JSON document, an empty
file, and non-UTF-8 bytes all survive exactly. Missing output does not acquire an
invented evidence file. Both reserved timeout paths participate in the existing
output-preservation preflight.

Process timeout remains authoritative: `status=process_timeout`, parent exit 2,
false instrumentation parity, and `process_exit_code=null` retain their existing
meaning. A child report saying complete cannot turn the timeout into success.
The original stdout/stderr diagnostic path and one process per mode are unchanged;
there is no retry. Saved counters remain in the retained raw child report rather
than being promoted into a successfully completed profiling pass.

## Source and executed validation

Baseline: main `1e31f2b2bef235bb145980c9ceed49580b1e55fb`, profiler Git blob
`8ae01c736bd44ffc424f91f657c2861126115d24`. The source materialized from the
existing PR10135 delivery package matches that Git blob exactly.

Only `supervise` changes. Every other function is AST-identical. Prior PR10118
source binding and PR10135 exited-child recovery remain intact.

Executed locally with Python 3.13.5 in an isolated cloud container:

```sh
cd revenue/kaggriculture/cloud-runtime-budget
python -B -m unittest -v test_timeout_reports
python -B -m unittest -v test_profile_saved test_trace_consumer test_source_binding test_child_reports
python -m py_compile profile_saved.py test_timeout_reports.py
```

Ten new methods pass; fifty unchanged compatibility methods pass in a separate
invocation, for sixty distinct methods. The identical final ten-method test file
fails on the baseline with ten assertion failures and zero errors. This is not
ten independent defects. An earlier outer-shell 45-second interrupted compatibility
invocation is retained separately and is not counted as a complete passing suite;
the final uninterrupted invocation completes all fifty methods.

Coverage includes both timeout orders; valid, malformed, empty, absent, and
non-UTF-8 report files; preserved log output; no extra child processes; prior-file
preservation; and a real profiler CLI actor which completes its one action and
report but hangs in an `atexit` handler. That actual worker report survives, but
the supervisor still returns timeout and false parity.

The simple two-child witness writes a 99-byte original diagnostic with SHA-256
`83d3b9a22ecc12d6d0db95cfc9387893038943e5e5ba304a156c47992a6ece6d`.
The baseline retains neither original; the repaired supervisor retains both.
Original failure text stays in the exact retained bytes.

These are process/transport regressions, not full-game measurements, a runtime
speedup, a hosted deadline verdict, or whole-repository CI certification. No new
workflow, game seed, selected default, running panel, or provider submission changes.

## Limits and credit

The original profiler, native TRACE input, source binding, and exited-child report
contracts retain their existing ownership and historical evidence. Direct-entrypoint
source binding does not freeze transitive imports. This change does not add
periodic worker checkpoints, reconstruct a report that was never written, recover
unflushed bytes, or guarantee recovery from storage read/write failures. A failed
exclusive retention write remains an error instead of overwriting prior evidence.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
