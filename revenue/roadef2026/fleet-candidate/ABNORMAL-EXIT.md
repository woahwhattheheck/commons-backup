# Abnormal supervisor termination

The portfolio receipt distinguishes solution validity from search completion.
After an exception escapes `start_lanes` or the polling loop, the supervisor
retains its last checked solution and records `status: "error"`. A validated
incumbent still has `validated: true`, its original digest, lane and vector.
An abort before any successful check has `validated: false`. The original
exception, including `KeyboardInterrupt` or the original `SystemExit` code,
continues to the caller; no retry or successful exit is substituted.

The existing event stream adds `supervisor_failed` with `error_type`. If that
stream is closed, the final error receipt is still attempted. If the final
receipt cannot be written, the original exception remains authoritative and
the previous atomic receipt survives. A retained `running` receipt is not a
completed execution. Final-receipt failures on an otherwise normal run are
not swallowed.

Normal completed searches, runs with no validated solution, and handled
SIGTERM/SIGINT draining keep their existing statuses and exit behavior. The
change does not alter solver selection, checker ranking, search budgets,
checkpoint bytes or process-group cleanup. Initial preflight and failures
inside cleanup remain separate boundaries; error reporting is best effort,
not a guarantee against a failed filesystem or hard process termination.

## Executed coverage

From this directory on a POSIX host, in the main Python thread:

```sh
python3 -S -B -m unittest test_supervisor test_abnormal_exit -v
```

Twelve new methods plus three unchanged supervisor methods pass on the
status-only candidate. The exact original supervisor at
`2885d176373c33410148829fef93c310c3752c0b` fails eight of the twelve new methods
as assertions, with no execution errors. `JOINT_SUPERVISOR=/path/to/original/supervisor.py`
selects that original for the new tests; keep its comparator beside it.

The fixtures launch real solver/checker subprocesses but deliberately use a
synthetic checker protocol, not an official feasibility assessment. A real
file/directory collision exercises checkpoint I/O failure. Other cases cover
escaping exceptions, failed diagnostics, preserved checked output, normal
completion, invalid output and handled TERM. Non-POSIX hosts explicitly skip
the new process fixtures. Linux Python 3.13.5 execution has no skips.

Exact source identities and result scope are in `ABNORMAL-EXIT-VALIDATION.json`.
The status-only evidence is distinct from SPRUCE's process-group repair and
any subsequent joined-source run. QUARTZ's frozen native benchmarks, the
solver algorithms and the held S139 submission are unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
