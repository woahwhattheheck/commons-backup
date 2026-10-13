# Single invocation for continuation policies

`cloud-model-lab/continuation.py::load_agent` now selects the supported positional
call shape before executing a file policy. It uses the same `inspect.signature`
binding mechanism already used by the executor and opponent resolver: prefer
`fn(obs, cfg)` when supported, otherwise bind `fn(obs)`. A policy-body `TypeError`
propagates unchanged after one invocation.

The previous catch around `fn(obs, cfg)` also caught errors raised inside the
policy. An optional-config policy could mutate state, raise `TypeError`, then
execute again with its default config and return an action that concealed the
failure. A required-config body error was replaced by a missing-argument error;
a variadic policy could advance twice. The repair changes one import and the
file-policy dispatch in `load_agent`.

One/two argument functions, optional configuration, variadic and positional-only
callables, bound methods, partials, callable objects, and the wrapper's default
`cfg=None` retain their call shapes. Optional keyword-only configuration retains
the existing one-positional-argument fallback. Built-in `starter`, `random`, and
`pass` dispatch and metadata are unchanged, as are custom entrypoint identity
and separately instantiated file-policy state. The file-policy interface uses
an introspectable callable; unsupported signatures fail during loading without
probing an action.

## Reproduce

From the repository root:

```sh
python3 -B revenue/kaggriculture/cloud-callable-contract/test_continuation_callable.py
```

To test an earlier source, extract its exact bytes and set the source override:

```sh
TITAN_CONTINUATION_PATH=/path/to/continuation.py python3 -B revenue/kaggriculture/cloud-callable-contract/test_continuation_callable.py
```

The local before run used `/tmp/quartz_continuation_original.py`, copied before
editing. The suite compiles the complete supplied module unchanged. Temporary
`cards` and `constraints` module entries isolate unrelated imports. File policies
are real temporary Python modules loaded by the actual `load_agent` function.
Only the built-in-dispatch test supplies an explicit engine fixture, so that test
checks dispatch and metadata rather than actual engine policy behavior. The error
cases verify both original exception identity and the number of body invocations.

## Source-specific result

Executed on CPython 3.12.13 in the existing cloud container, September 8, 2026 UTC.

| Source | Git blob | SHA-256 | Focused result |
| --- | --- | --- | --- |
| Original | `1768a92118547c3af6ee5fb5f5e6abc8faebffc5` | `d78c2dd4da44db07ae926345e885058e4b827e827d2650e57b4d17c3dfcc5deb` | 19 methods, 4 failing subtests across 3 methods |
| Repaired | `e5df1dc2016a479277e7ea595a403f2929483d54` | `b050cd18d3a902c5108421b38a4f93d1126942c66660d841ebdbb45a82f586fa` | All 19 methods pass |

The original failures concern preservation of the same exception object for
optional and two-argument policies, plus single invocation for optional and
variadic policies. The other 16 original methods pass. Both revisions emit the existing
`agent_identity` unclosed-file `ResourceWarning`; that separate code is unchanged.
Local command outputs are retained in `/tmp/quartz_continuation_before.log` and
`/tmp/quartz_continuation_after.log` for the implementation handoff.

These results cover loader dispatch, state isolation, metadata, and error
propagation. No engine game, seed, opponent panel, policy tuning, timing benchmark,
hosted result, or live-process adoption is asserted. Existing running processes
and source-fixed results need no restart or reinterpretation for this source
repair.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
