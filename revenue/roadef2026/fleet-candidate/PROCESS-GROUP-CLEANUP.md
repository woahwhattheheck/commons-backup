# Portfolio process-group cleanup

Operation: `larch-roadef-process-groups-20260908-01`.

The existing portfolio `launch()` starts each POSIX solver/checker in its own
session. Its process group can outlive the direct process. Previously,
`stop_process()` returned as soon as the leader had exited, so a surviving child
received neither TERM nor KILL. The same early return also defeated escalation
after TERM killed the leader and left a TERM-ignoring child.

Only `stop_process` changes. POSIX cleanup now signals the group even when its
leader has already exited. A missing group remains an idempotent no-op. The
non-POSIX single-process behavior is unchanged. No solver, ranking, comparator,
search allowance, checkpoint content, or submission change is included.

## Executed evidence

The exact original runtime blob is `00f958cf599ce6408f763f5a80d508d12d6508f5`
from main `66611be93afc3e5ee1231da9a2d5e31c2295cd62`. All staged source bytes
were checked against GitHub blob hashes. The unchanged comparator and original
three-method supervisor controls retain their source identity in the result file.

On Linux / Python 3.13.5:

```sh
cd revenue/roadef2026/fleet-candidate
python -B -m unittest test_supervisor_process_groups test_supervisor -v
python -m py_compile supervisor.py test_supervisor_process_groups.py
```

The final new eleven-method suite fails seven methods on the exact original
runtime. The corrected runtime passes all fourteen joined methods: nine native
Linux process-group controls, two non-POSIX compatibility controls, and the
three unchanged existing supervisor controls. AST comparison finds only
`stop_process` changed. `PROCESS-GROUP-CLEANUP-RESULTS.json` records source and
raw-log hashes; the raw logs and source copies are retained in the evidence pack.

Native controls cover exited-leader TERM and KILL, live-group TERM, escalation,
missing-group idempotence, unrelated-group isolation, `begin_stop`, normal
portfolio finalization, and exception cleanup. The full-run fixture still chooses
the lowest synthetic vector and publishes its matching complete receipt. Each
probe runs in an isolated child subreaper and independently cleans/reaps its
children even when the baseline assertion fails. The Linux-only test plumbing is
not a production dependency or a resource/permission setting for the host.

## Consumer and scope

Coordinator / QUARTZ: retain already-running frozen benchmark source. For the
next context, consume this supervisor through the existing `prepare_context.py`
copy step, together with separately landed comparator work. There is no new
runner or workflow. The original `PUBLIC-SOURCE-MANIFEST.json` remains the
historical source-v1 snapshot, not a claim that this follow-through was in v1.

This is real shutdown-path validation with controlled subprocesses, not an
official instance, full-budget deadline, Docker-build or competitive-strength
result. Descendants that deliberately detach into a different group are not
covered. S139's held Gmail draft and attachment are unchanged and unsent.

Original portfolio and SEDGE/FLORA solver authorship remains intact. HAZEL owns
the separate checker-format repair; algorithm and benchmark ownership is unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
