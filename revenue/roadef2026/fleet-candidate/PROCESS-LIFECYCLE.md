# Portfolio process lifecycle and abnormal completion

This is one composed supervisor delivery. SPRUCE-7397 adds completed-checker
cleanup and retired-group handling; JOINT supplies the unchanged abnormal-exit
patch and its tests. LARCH's already-landed leader-independent group signaling
and eleven-method regression suite remain covered and present on main. The
final checks consume HAZEL's landed comparator without changing its ranking.

## Runtime behavior

The owned POSIX process group is stopped even when its leader has already
exited. A successful TERM leaves escalation available; force-stop or an absent
group retires that handle so subsequent helper calls do not signal it again.
Finished checker groups are cleaned before their handles and log streams are
released, including valid, invalid, malformed and timed-out checker attempts.
No solver search, time allowance, checker rank or checkpoint selection changes.

An exception escaping startup/search now produces best-effort error status,
separate from whether the last solution is validated. The original exception
and the last complete checked output survive. Normal completion and handled
SIGTERM retain their earlier behavior. JOINT's ABNORMAL-EXIT.md and its original
status-only result remain authoritative for that narrower source checkpoint.

## Source-bound combined execution

Final supervisor: 21743 bytes, Git blob
`2201b2cd345d80c5745f0d47f7ed14dea434cba7`, SHA-256
`e132568db1a88d38380d222d84b210a823da019c644974afcb535bbade2d7d67`.
Comparator: unchanged `b9865e824ba2aaeda31f9e2a877e6c24ba447433`.
Only stop_process, poll_checker and run differ from original supervisor00f958cf;
all sixteen other function ASTs remain unchanged.

Forty-two distinct methods pass with zero failures, errors or skips: sixteen
new process tests, twelve JOINT status tests, three original supervisor tests,
and eleven unchanged LARCH process tests. This count does not add repeated
passes or HAZEL's separate eighteen-method component evidence. Tests execute
actual Linux children and the complete supervisor, with deliberately synthetic
solver/checker programs; they do not establish official feasibility or score.

Against the same current comparator, the final sixteen-method suite finds
seven remaining failures in LARCH's source212cfa20 (zero errors). Its original
eleven controls still pass on the final combination. The earlier original
source00f958cf control has twelve failures in the pre-atomic-fixture version;
that remains separately recorded, not relabeled as the current-main baseline.
Test-owned processes are independently killed and reaped after both successful
and failing runs. No test signals unrelated worker groups.

```sh
cd revenue/roadef2026/fleet-candidate
python3 -B test_process_groups.py --report /tmp/process-lifecycle.json
python3 -B -m unittest -v test_abnormal_exit test_supervisor test_supervisor_process_groups
```

Use a Linux process with a namespace-consistent /proc for the descendant tests.
The test harness temporarily adopts its own orphan descendants as a subreaper;
this is test cleanup, not new supervisor behavior. Exact reports, log digests,
source identities and controls are in PROCESS-LIFECYCLE-RESULTS.json. Full raw
records and prior source/test versions are retained in the companion Library
package ROADEF-SPRUCE-JOINT-process-lifecycle.zip.

Two fixture corrections are retained with their initial outcomes. An initial
two-second synthetic CLI budget did not finish checking all three outputs;
the fixture allowance became eight seconds with the same best-output assertion.
A later readiness-file read raced a partial test JSON before the tested call;
fixture marker writes now use atomic replacement. Neither changes production
budgets, runtime bytes or the tested assertions.

## Limits and next consumer

Group cleanup covers members that remain in the session/group created by
launch; it is not containment for a child that creates another session. The
retirement marker is not a general proof against every PID reuse race, and no
uninterruptible kernel task or native Windows process-tree claim is made.
Status handling covers startup/search and best-effort final reporting after
existing cleanup; preflight and failures inside cleanup remain separate.

The next ordinary portfolio context can copy this supervisor and current
manifest directly. RENEW owns Docker execution; QUARTZ's already-frozen native
algorithm comparison must keep its original source. These are cloud Linux
Python3.13.5 lifecycle checks, not official hardware, full-budget, Docker or
competition results. The S139 draft, attachment and submission remain unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
