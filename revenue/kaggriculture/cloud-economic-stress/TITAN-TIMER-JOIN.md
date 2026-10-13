# Canonical TitanAgent timer join

PR10144 introduced a new direct consumer of the existing ECON timer. The prior
245-method workflow result covers its declared selected/stress inputs, not this
new TitanAgent boundary. This independent check executes the unchanged actual
`TitanAgent.act` and `_DeadlineTimer` with controlled initialization, production
and transform callbacks. No production repair is needed on the inspected source.

## Result and source

Ten methods pass on runtime blob `4985b934d31883708db8ef64396e05b9e2a41ea8`
(6824 bytes, SHA-256 `57195e3a3b8fefcb78054739b5dd37b07690a77f9319e3b53a99cce7f4151240`)
and adapter blob `1c777790cf74cd528461466765c2a48ef49cf191`
(SHA-256 `c3bef158763cb4f5f8b8436800f442b1acc94be2c407c5db1e740edd3a0d68f0`).
Both are exact PR10144 merge `4f743f8ec29bddc36220b2169a2609fe159776e2` source.

The checks cover ordinary Exception handlers in each of three phases, exact
foreign-cancellation identity, an enclosing timer's distinct expiry, earlier and
later caller alarms, periodic cadence, one total production/transform budget,
and actual ready-state reinitialization before the next call. The phase callbacks
are controlled test doubles, not the real frozen/ordered/seed policies.

An isolated negative control changes only `DeadlineExceeded(BaseException)` to
`DeadlineExceeded(Exception)` in a local adapter copy. All three broad-handler
checks then fail, showing that those checks detect swallowed cancellation through
the new entrypoint. The real runtime is unchanged in both runs. That mutation is
not a historical shipped source and is never published into a runtime directory.

With deliberately delayed callbacks and a 40 ms budget, observed cold/production/
transform cancellation times were 40.188/40.126/40.144 ms. These are boundary
measurements, not full-agent performance. Five periodic caller ticks were observed
with the original 15 ms cadence. The next-call fixture records exactly two
initializations, two producer calls and two transforms over two calls; it does not
prove that reconstructing a real controller preserves every strategic state.

## Reuse

Run in a fresh main-thread POSIX subprocess, with the runtime's existing reference
adapter beside it. The test supports an explicit source path, including the
canonical builder's next exact source or extracted archive:

```sh
python -B revenue/kaggriculture/cloud-economic-stress/test_titan_timer_join.py \
  --runtime revenue/kaggriculture/cloud-execution-lab/titan_runtime.py \
  --report /tmp/titan-timer-join.json
```

The JSON records executed runtime, adapter and test byte identities, method counts,
original failures and measurements. `--broad-only` selects the three cancellation
controls for an isolated local mutant; do not change a shared runtime to run it.
Full actual/negative reports, logs and both exact two-file source closures are
retained in the associated Library evidence package.

## Scope

This test neither imports the engine nor initializes real policy modules. It is
not a full archive execution, standalone main.py import check, game, seed draw,
held result, hosted test result, or proof of a future source revision. The builder's
12 relocated archive cases remain its own separate evidence and were not repeated.
No runtime, package, manifest, workflow, default, game panel or peer-owned history
integration changes. Canonical builder and T09 remain the consumers: reuse the test
on the next changed timer boundary, without duplicating the existing game shards.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
