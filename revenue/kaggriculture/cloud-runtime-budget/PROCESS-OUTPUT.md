# Decode diagnostic streams without losing child results

Operation: `astra-delta-profiler-process-output-20260908-01`.
Consumer: the existing FINCH/TRACE `profile_saved.py` supervisor and CLI.

## Behavior

The supervisor explicitly decodes exited-child stdout and stderr as UTF-8 with
`backslashreplace`. Invalid bytes become readable escapes such as `\xff`; valid
Unicode and text-mode newline normalization remain supported. Diagnostic output
can no longer abort report collection with a `UnicodeDecodeError` before the
original child report, exit status, and final supervisor summary are saved.

These `.log` files are display text, not lossless raw-byte archives. A literal
backslash escape can resemble the rendering of an invalid byte. This change does
not claim exact raw stdout/stderr identity, nor introduce a new raw-log format.
The existing timeout exception display still uses replacement characters; its
separate exact child-report `.timeout.bin` preservation is unchanged.

A child's original error and nonzero process exit code remain authoritative.
A complete-looking JSON report cannot hide exit 7. Conversely, diagnostic bytes
alone do not invalidate a complete, source-bound, successful actor execution.
Malformed report recovery, timeout retention, one child per mode, source binding,
expected-action comparison, and instrumentation parity retain their prior meaning.
There is no retry, policy change, or new process.

## Source and reproduction

Baseline source is the PR10178 merge
`439e73a8428caa9425e60f9ac300dcf33a9a6f8a`, profiler Git blob
`8f877c05667b139d0e7bdeec04c9dcfe53898a12`.
The direct main read before publication still returned that exact blob.
The repair changes only the subprocess capture keyword arguments in `supervise`;
all other function ASTs are identical. The earlier source binding and both
exited-child and timeout-report recovery repairs are retained intact.

```sh
cd revenue/kaggriculture/cloud-runtime-budget
python -B -m unittest -v test_process_output
python -B -m unittest -v test_profile_saved test_trace_consumer test_source_binding test_child_reports test_timeout_reports
python -m py_compile profile_saved.py test_process_output.py
```

The new eight-method suite passes on Python 3.13.5 in an isolated cloud container.
The sixty unchanged compatibility methods pass in a separate complete invocation,
for sixty-eight distinct methods. Syntax compilation also passes.
The identical suite on the exact baseline has one failed assertion and five
errors, with two controls passing. These are six failing methods, not six
independent production defects. The tests execute real child processes; the
command-dispatch seam does not replace the child process or its outcome.

Coverage includes invalid stdout and stderr, valid UTF-8 and CRLF/CR text output,
successful report collection, nonzero exit preservation, malformed report
recovery, and binary diagnostic output during timeouts. An actual profiler CLI
actor writes invalid diagnostic bytes during its one action; both fresh worker
processes complete, both expected actions match, and the saved logs remain
readable. No engine transition or full game is run.

The retained minimal witness separates source versions: the baseline stops after
its first child with `UnicodeDecodeError`, no log, and no final summary. The
repaired supervisor runs its existing two modes once each, retains both original
RuntimeError reports and exit-7 values, writes both escaped logs and the final
summary, and returns 2 with false instrumentation parity. That failure remains a
failure; decoding resilience is not an actor correctness claim.

Historical profiles, timing measurements, saved observations, actor policies,
transitive-import scope, and running panels are unchanged. Local regression
coverage is not a full-repository CI or hosted deadline claim.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
