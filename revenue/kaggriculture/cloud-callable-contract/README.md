# Single-invocation executor loading

The model-lab executor selects `agent(obs, cfg)` or `agent(obs)` by binding the
callable signature once when constructing a per-match callable. The action path
executes exactly that call shape. A `TypeError` raised by the policy body therefore
propagates to the existing failure recorder without executing the policy again.

This is a direct change to `cloud-model-lab/execute_arm.py`, not a second executor
or policy wrapper. Two arguments remain preferred when both forms are supported.
The supported interface is an introspectable Python callable; a callable whose
signature cannot be inspected fails construction rather than being probed by
execution. Signature selection itself executes no policy action.

## Run the regression tests

From the repository root:

```sh
python -B revenue/kaggriculture/cloud-callable-contract/test_execute_arm_callable.py
```

To test an extracted earlier executor:

```sh
TITAN_EXECUTOR_PATH=/path/to/execute_arm.py python -B revenue/kaggriculture/cloud-callable-contract/test_execute_arm_callable.py
```

The suite compiles the supplied executor with only its unused top-level
`import cards as cards_mod` removed. All executor function bodies, especially
`load_callable`, are unchanged by the test loader. Real temporary Python policy
modules exercise one/two argument functions, optional configurations, variadic
and positional-only functions, bound methods, callable factories, partials,
state isolation, metadata and policy/construction exceptions. No environment,
opponent or simulation is created.

## Source-specific local result

Executed in an ephemeral cloud container on CPython 3.13.5, September 7, 2026.
The original executor at commit `3c8cd3fb26dd53e2a42969385acf53abe5d4a9ba`
is Git blob `2b4ee527682e8ad3cd0fde50aeb94e7cb38ad539`, SHA-256
`70d66c4519307a30d8b64cfa75217719ed74bda356e6b377475f2e74b58c3918`.
It runs 16 tests with 3 failures: a required-two-argument body error is replaced,
an optional-configuration body error is silently retried, and a variadic stateful
policy executes twice. The other 13 tests pass.

The repaired executor is Git blob `6469ead662bd9f3a0b818d195d61f5881c1041d8`,
SHA-256 `1a85339c8d591671f9ec9f3f211b1242992df2bf34583372c91072287fd2a2e1`.
All 16 tests pass. This result covers loader invocation and error propagation,
not game outcomes, speed improvement, whole-repository CI or hosted deployment.

The patch changes one import and the callable dispatch inside `load_callable`.
Game loop, policies, opponent resolver, seeds, timing fields and result schema
remain unchanged. Existing `worst_action_s` measures action calls, not imports
or factory construction. No running panel needs to be restarted for this change.
The patch is based on the model-lab working branch; it does not merge that
branch's other experiments to main or reinterpret their source freezes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
