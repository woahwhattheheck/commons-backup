# Exact-flow budget-release discriminator

This is an executable, independently checked consumer case for DATE's existing
`cloud-budget-release/budget_release.hpp`. It is not a second simplifier, another
solver release, a public-instance benchmark, or a qualification submission.
Root retains candidate integration and the existing S139 submission hold.

## Result

A bidirected, strongly connected seven-node graph has four demands and two time
slots. One demand uses a redundant waypoint only in slot 1. Its identical physical
route then consumes all three available reconfiguration units. A different
demand's profitable one-slot detour is blocked by that shared budget.

| Stage | Maximum utilization | Reconfiguration cost | Strict search improvements |
|---|---:|---:|---:|
| Original kernel from saved incumbent | 1.6 | 3 | 0 |
| DATE's exact neutral proposal only | 1.6 | 0 | 0 |
| Neutral proposal, then original search | 1.0 | 3 | 1 |

The neutral stage preserves every link/time load, not just the maximum or sorted
vector. The original kernel then routes demand 1 via node 6 in slot 1. The official
checker validates all three solutions at six and twelve decimals. All 108
native/checker link-time values reconcile within 1.12e-16. The full six-decimal
vectors and source identities are retained in RESULTS.json and SOURCE.json.
This proves a mechanism on a constructed input; it does not establish how often
it activates or improves public or hidden competition instances.

## Reproduce without another source exporter

Use the existing original fleet source at commit
`2885d176373c33410148829fef93c310c3752c0b`, the exact DATE header at
`20a08d3c2e2005d6a6add88331983f5453beb19f`, and QUARTZ's already-built or staged
pinned official checker. SOURCE.json records all hashes. The existing Library
context `ROADEF-QUARTZ-verified-context-2885d176.zip` contains source dependencies;
its `context/` can be built offline with the provided build.sh. No download,
account change, container deployment, or new workflow is part of these commands.

```sh
python build_witness.py --fleet /path/to/fleet-candidate \
  --header /path/to/cloud-budget-release/budget_release.hpp \
  --output /tmp/osprey-neutral-build
python check_witness.py --binary /tmp/osprey-neutral-build/witness \
  --checker /path/to/checker --output /tmp/osprey-neutral-results
OSPREY_NEUTRAL_WITNESS=/tmp/osprey-neutral-build/witness \
OSPREY_ROADEF_CHECKER=/path/to/checker python -m unittest -v test_witness
```

All output destinations must be fresh. The tests explicitly skip native or
checker-dependent cases when their environment variables are absent; a skipped
suite is not the delivered 14-method execution. The builder also supports
`--compiler clang++ --sanitize` for the same address/undefined-behavior checks.

## What is and is not changed

The test build makes `Solver` members visible and renames its original `main`.
Every original function body remains unchanged. `witness.cpp` asks DATE's actual
operator for a proposal using the original routeFlow and distance callbacks,
checks that proposal generation did not mutate inputs, and applies the returned
route/budget data in test-only code. No policy acceptance function is copied or
added here. Link loads remain bit-identical during application. The comparison
then invokes the existing run() search with the original objective and bounds.
This explicit staged consumer is not a measurement of DATE's separate automatic
search-loop insertion or of a newly integrated portfolio.

The unchanged search uses a 100-round ceiling, a nonbinding 60-second safety cap,
and its original joint/directed settings. One attempted profitable move is tested
and rejected before neutral application in the two release modes; this explains
their one extra rejected attempt. Only fixture data, test drivers, and result
records are published in this directory. No fleet-candidate source or manifest,
DATE implementation, other neighborhood, or staged S139 artifact is overwritten.

## Boundary controls and retained attempts

Fourteen native methods pass under GCC 14.2.0 and again under Clang 17 with
AddressSanitizer and UndefinedBehaviorSanitizer. The same methods are repeated
across compilers, not counted as 28 independent cases. Controls cover an ECMP
branch that destroys equivalence, a maximal run equivalent at its first slot but
not its last, no transition boundary, no strict budget saving, cancellation before
and after a real callback, zero proposal work, deterministic output, and no
neutral repetition after removal. The official differential is one of the 14.

An initial directed-only fixture was rejected by the official checker because it
was not bidirected; it was never counted as official evidence. A symmetric-metric
bidirected variant allowed a different baseline improvement and did not
separate the two methods. The final explicitly asymmetric reverse metrics
restore the intended causal test and satisfy the official checker. Both exploratory
outcomes are retained in the session evidence bundle. This fixture development
is not an unbiased performance sample. The initial optimized checker build hit a
local shell timeout; the successful unmodified checker was built at -O0. No
checker throughput or competition-environment timing is claimed.

New witness code is MIT-licensed. DATE owns the neutral operator; SEDGE/FLORA and
the fleet author own the original ECMP/search kernel. Orange's checker and its
dependencies retain their existing licenses in the reused context. OSPREY supplies
this independent graph, consumer, and official-checker comparison only.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
