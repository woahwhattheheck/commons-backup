# Preserve caller handler replacement across deadline scopes

The existing `_DeadlineTimer` now presents the caller's own SIGALRM handler while
delivering its alarm, retains a handler installed by that callback, and restores
the guard dispatcher before guarded work resumes. On exit the caller receives
its latest handler and existing remaining timer. No second timer or policy
wrapper is introduced.

The original adapter retained timer rearming but not handler replacement. A
caller installing another callable or SIG_IGN could therefore receive or ignore
the guard's own expiry. Normal exit also restored the superseded caller handler.
The change adds three executable lines and two comments in `_deliver_outer`.
AST comparison finds every other runtime method unchanged: budgets, cancellation
identity, periodic scheduling, selected-action fallback and single producer
invocation retain their existing implementation.

## Source and measured result

Original adapter: `1c777790cf74cd528461466765c2a48ef49cf191` (PR10056).
Repaired adapter: `f918325f36493bf4cfc46c274f57128fc7b0fc82`, SHA256
`d6f818d856047add09489e7ee69ccb18a327c1afe3c47b317cd7a14858da5f04`.

The new suite executes 23 methods: 16 deterministic signal/clock boundary cases
and seven real Unix signal cases with explicitly injected phase bodies. The
original source has 19 assertion failures and one error; these are multiple
witnesses of this boundary, not twenty independent defects. Repaired source
passes all 23 with no errors or skips. The unchanged PR10023 cancellation suite
also passes all 18 methods on the repaired adapter. This is 41 local methods,
not a hosted 41-method run or full-policy coverage.

Initial real probe: 30 ms budget, 2 ms reserve, caller alarm at 8 ms, injected
90 ms production. Original returns after 90.276 ms with `completed`, runs the
transform, and discards the caller replacement. Repaired returns the existing
production fallback after 28.134 ms, skips the transform, and preserves that
replacement. Each invokes production once. These are boundary measurements,
not natural game timings or proof of a hard real-time limit.

Cases cover callable/default/ignore replacements, periodic cadence, rearm and
disarm, multiple handler generations, handler introspection, original exception
identity, nested guard cancellation, and exact production/transform fallbacks.
Readable measurements and hashes are in `CALLER-HANDLER-RESULTS.json`.

## Reproduction

Run in a fresh Unix main-thread process from the repository root:

```sh
python -B revenue/kaggriculture/cloud-economic-stress/test_caller_handler.py --report /tmp/caller-handler.json
python -B revenue/kaggriculture/cloud-economic-stress/cancellation/test_deadline_cancellation.py --report /tmp/cancellation-compatible.json
```

To reproduce the old boundary, save the original adapter from PR10056 and pass
its path through `--adapter`; the new suite intentionally exits nonzero on that
source. Both commands use the Python standard library. No engine download,
provider call, game replay or seed allocation is needed.

## Consumer adoption and limits

The canonical `cloud-execution-lab/reference/titan-current/deadline_adapter.py`
was read as the same original `1c777790` blob. This source delivery changes only
the owning `cloud-economic-stress` adapter. The canonical builder can consume
this exact tested adapter in its next normal source/package update; the old
reference and already-frozen archives do not acquire it automatically. Existing
STRESS-JOIN runner, actor-recovery work, CI/reporting and packaging owners remain
separate. No selected-policy, budget or historical game result changes here.

The patch addresses handler replacement during a delivered caller callback. It
does not establish hard real-time interruptibility of native extensions, bound
the execution of a slow caller handler, roll back interrupted producer state,
or synchronize arbitrary process-wide signal manipulation outside this scope.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
