Development candidate; qualification not submitted.

Three independent single-thread solver processes
start together: unchanged SEDGE, unchanged FLORA in standalone mode, and the new
candidate. A separate official-checker process validates immutable checkpoints
while search continues. Only a strictly better, feasible official six-decimal
descending saturation vector replaces the output. Total transition cost remains
a diagnostic and never breaks ties. The shared official-result comparator is
included beside the runtime and copied unchanged into each build context.

The four-argument interface is:

```sh
./run.sh network.json traffic.json scenario.json output.json
```

All default lanes receive 565 seconds including their own preparation. The
supervisor starts final shutdown at its 565-second wall deadline, allows a
two-second graceful exit, and spends the remainder up to 585 seconds validating
final checkpoints. It has a further five-second margin before the organizer's
590-second SIGTERM and fifteen before 600-second SIGKILL. An earlier SIGTERM or
SIGINT ends search immediately and leaves at most seven seconds for final checks.
Linux children are placed in process groups and are killed after the grace period.
Windows is supported for development runs; its forced termination does not prove
the Linux graceful signal behavior.

An empty-waypoint solution is atomically written immediately. It incurs no route
changes; topology reachability still requires the checker, so the receipt labels
it unvalidated until that succeeds. Once validated, the selected output is never
replaced by unchecked, infeasible, tied, or worse results. Crashed lanes retain
their last complete checkpoints. A checker timeout, crash, malformed result, or
launch failure retries the same frozen bytes once while time remains, including
after its producing lane has exited. Conclusive valid/invalid judgments and
exhausted retries are distinguished in the receipt. The prior best survives all
failures. If no solution validates, the wrapper returns exit code 1 and its
receipt says `no_validated_solution`. A killed process retains the last atomic
output and last receipt; the receipt's `running` status must not be called a
completed run.

The adjacent `output.json.portfolio.json` records selected binary/checker/solution
hashes, lane exits, validation timing, and output status. Detailed logs, frozen
solutions, and checker results remain in a unique temporary artifact directory
named in that receipt. This keeps exactly the checked bytes reviewable. Memory
keeps only the current best vector plus the active validation result; past
checkpoint hashes are deduplicated without retaining past vectors. On Linux, the
receipt also records a 0.5-second sampled RSS sum of supervisor, solver and checker
processes. This excludes page cache and can miss between-sample peaks; it is not a
hard memory bound. Windows leaves this measurement unavailable. Three search
lanes plus one serial checker use at most four compute processes; no runtime
network calls or instance-name-specific choices occur.

## Build and development controls

Place the published candidate source beside the runtime as `main.cpp`.
In the cloud build environment, prepare a fresh context and build its image:

```sh
python3 prepare_context.py --output context-v1
docker build -t roadef-portfolio context-v1
```

Preparation downloads exactly four pinned source archives: SEDGE, FLORA, the
official challenge checker, and Networktools. It verifies their recorded SHA-256
values before extracting selected source families, rejects unsafe archive paths
and symbolic links, and preserves original licenses. Any hash mismatch stops the
build preparation; it does not substitute a different source. `--archive-dir`
accepts an existing folder containing the four named ZIP files for offline
preparation. `--candidate` can select a candidate source in another location.
The context must be new; existing files are never overwritten. Its
`source-manifest.json` records exact archive URLs/hashes and staged file hashes.
The build-time downloader is not copied into the runtime image.

The Ubuntu 24.04 image installs a C++ compiler during its build stage and Python 3
into the runtime stage at image-build time. It compiles all solvers and the pinned
official checker from local staged sources. Runtime consists of those binaries,
the Python standard library, and the shared comparator. It uses the organizer's
UID 1006410000, `/home` working directory, and idle-container convention. The image
build and actual Linux signal behavior require execution evidence before claims
of competition readiness.

`PORTFOLIO_SECONDS=30` scales a development run to 26.4 search seconds plus 3.6
seconds reserve. `PORTFOLIO_CHECK_INTERVAL` changes periodic checkpoint spacing;
`PORTFOLIO_CHECK_TIMEOUT` bounds any one checker process. Paths can be overridden
with `PORTFOLIO_SEDGE`, `PORTFOLIO_FLORA`, `PORTFOLIO_CANDIDATE`, and
`PORTFOLIO_CHECKER`, including native `.exe` files for Windows trials.
`PORTFOLIO_ARTIFACTS` selects an existing parent directory for retained run files;
`PORTFOLIO_RECEIPT` selects a receipt file. None of these controls examines an
instance name. C++ diagnostic environment overrides that could accidentally
shorten a lane or resume it from an unrelated solution are cleared.

This portfolio construction preserves each lane's full search allowance, but
resource contention can change search progress. No dominance, largest-instance
memory bound, hidden-instance quality, or winning rank is established by its
design alone. Those require equal-resource, full-budget measured trials and
official validation.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
