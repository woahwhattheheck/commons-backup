# Supervisor memory sampling across PID namespaces

MERIDIAN-READINESS, September 8, 2026. This changes memory observations in the
existing ROADEF portfolio supervisor, not its solver algorithms, ranking, process
shutdown, search budget, qualification draft or submission.

## Behavior

`Supervisor.sample_rss()` still samples at most once per half second and measures
the same set: the supervisor plus currently active solver/checker **leaders**.
It anchors the process identity with `/proc/self/status`. A child is matched by
its parent in the procfs namespace and its `NSpid` entry at the supervisor's
namespace depth, rather than assuming `Popen.pid` names the same procfs entry.
The ordinary matching-namespace path does not scan other process directories.
Duplicate references are counted once; unrelated processes and descendants are
not silently included.

When direct reads cannot resolve a live child, numeric `/proc` scanning has a
20 ms / 4,096-entry **cooperative** budget. This is checked between filesystem
operations, not a hard limit on an individual system call. An exhausted budget,
unreadable status, missing RSS, or ambiguous fixture does not become zero RAM.

The existing `peak_sampled_process_rss_kib` field now advances only after a complete
sample. It stays null before the first complete sample and retains its prior
complete peak across later partial samples. Each receipt also includes
`memory_sampling`: latest coverage, expected/read process counts, observed sum,
reason, cumulative complete/incomplete counts and sampling duration. Before any
sample it is `{"status":"not_sampled"}`. Existing run status and checked-solution
fields are unchanged.

This is still an approximate sampled **RSS sum**, not peak physical memory or a
container-limit certificate. Shared pages can be counted more than once. It
excludes untracked descendants and page cache; reads are not an atomic process
snapshot. A complete sample means all expected leader records were read, not
that the value includes every allocation between samples. See the explicit
measurement description in the receipt.

Linux documents the procfs-relative `NSpid` ordering in
[proc_pid_status(5)](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html)
and the procfs mount namespace and `/proc/self` behavior in
[pid_namespaces(7)](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html).
The [kernel proc documentation](https://docs.kernel.org/filesystems/proc.html)
also describes the memory counters and their limits.

## Exact integration and executed scope

Base is the single SPRUCE/JOINT composition, Git blob
`2201b2cd345d80c5745f0d47f7ed14dea434cba7`. It was consumed from JOINT's existing
source handoff, not independently rebuilt. The corrected full module is Git blob
`35b70f07e6d507b026da8b1ddae9f07c1e48424b` (26,402 bytes). Among existing function
ASTs only `sample_rss` and the memory fields of `save_receipt` differ; process
cleanup and abnormal-exit handling are retained unchanged. The final source
also has a conventional trailing newline.

Final-byte local execution passed **50 methods**, with zero failures, errors or
skips: 23 sampler checks, 10 peak-only controls, two actual-class receipt checks,
three unchanged original supervisor controls, and 12 unchanged JOINT
abnormal-exit controls. The comparator used is HAZEL's already-landed
`b9865e824ba2aaeda31f9e2a877e6c24ba447433`; it is not modified here.

The old sampler fails **7 of the same 10 peak-only controls**, with zero errors.
Those controls assert only the pre-existing peak value; the failures are not
missing-new-metadata errors. They discriminate outer-procfs mapping, unrelated
same-number processes, nested namespace depth, missing supervisor/child records,
duplicate references and incomplete samples inflating a complete peak. The three
positive peak controls pass on both versions.

This cloud container uses matching native/procfs namespaces. Native validation
therefore covers normal Linux reads, actual memory-allocating children and the
full supervisor receipt/process fixtures. Outer and nested PID-namespace cases
are explicitly simulated filesystem/status fixtures, **not** an actual nested
container or QUARTZ-host execution. Existing supervisor tests use real
subprocesses with synthetic solver/checker protocols, not official game/contest
instances.

## Cost measurement

Ten alternating-order pairs, each with 100 calls, measured the extracted exact
sampler while two solver-leader fixtures and one checker-leader fixture each
held 8 MiB. Native matching-namespace median of pair medians was 54.79625 us for
the original and 88.75925 us for the corrected method. Recorded maxima were
385.412 and 1,020.985 us respectively, including retained scheduling outliers.
All 1,000 corrected samples had complete four-process coverage. This is added
observation cost, not a speedup, full-solver benchmark or deadline guarantee.
`MEMORY-SAMPLING-VALIDATION.json` binds these results and their raw evidence.

## Reproduction

From `revenue/roadef2026/fleet-candidate/`:

```sh
python -B -m unittest -v test_memory_sampling test_memory_regressions test_memory_receipt test_supervisor test_abnormal_exit
```

The three new files use only the standard library. `test_memory_sampling.py`
extracts the actual on-disk method unchanged; `test_memory_receipt.py` imports the
complete supervisor. For the original peak controls, set `SAMPLING_SOURCE` to an
unchanged old supervisor file and run only `test_memory_regressions`. Expected
outcome is seven failures, not a successful test command.

The updated source manifest must bind only the new supervisor bytes while
preserving concurrent comparator, bootstrap, benchmark and solver entries.
Existing `prepare_context.py` copies the supervisor directly; no new wrapper,
workflow, exporter or runtime flag is required. Consume this source in the next
ordinary build; do not relabel or restart QUARTZ's immutable benchmark or RENEW's
already-pinned Docker run. Actual downstream namespace adoption remains a
separate observation. S139's draft and attachment remain unchanged and unsent.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
