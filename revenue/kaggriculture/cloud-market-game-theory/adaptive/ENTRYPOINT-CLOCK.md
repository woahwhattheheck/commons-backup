# Adaptive entrypoint clock and actor lifetime

ASTRA-CLOCK; canonical T08 claim `1788829732.093379`.

The existing `main.py`, `fixed_main.py` and `static_main.py` treated a missing
`step` as zero. Two successive observations carrying only `day=0,hour=0` and
`day=0,hour=1` therefore constructed two actors, each receiving its first call
with no normalized step. The inner integrated parent normalizes its own copy;
that does not normalize the outer adaptive runtime's history/recourse input.

The entrypoints now consume the runtime's existing `sale.absolute_step`, copy
the caller's observation, and normalize its clock before selecting/resetting
an actor. Explicit non-null step still wins; day/hour and configured day length
are the fallback. Actual zero resets the actor; a new day does not. The runtime
module is loaded once per entrypoint namespace while actor state remains
separate across episodes and independently loaded entrypoints. Modes and
returned action identity are preserved. Constructor/action errors propagate
without a second invocation.

Direct compile/exec with a real filename but no `__file__` or `__raw_path__` is
also supported by the existing code-filename convention. This is additional
compatibility, not a claim the normal official path was broken: the pinned
Kaggle `agent.py::build_agent` supplies `configuration['__raw_path__']`, while
`get_last_callable` directly compiles into an empty namespace. The existing
private-path contract remains supported and ordinary `__file__` takes priority.
Primary source: Kaggle/kaggle-environments commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, agent.py blob
`537c1af1dfb2b2c8f90edab06596e3134f2c70e6`.

## Executed regression

```sh
python3 -B revenue/kaggriculture/cloud-market-game-theory/adaptive/test_entrypoint_clock.py \
  --report /tmp/entrypoint-clock.json
```

Eighteen methods run against all three entrypoints: 54 subcases pass on the
published source, with no failures/errors. Exact original sources produced
39 failing subcases (18 assertion failures and 21 errors); those are not 39
independent defects and some cases assert the new lifecycle contract.
`ENTRYPOINT-CLOCK-VALIDATION.json` records source hashes, original results and
the successful log. `--entrypoint-dir` supports testing preserved old files;
`--clock-source` can point to an existing source closure.

These are explicit recording-runtime boundary fixtures. They compile the real
unchanged `absolute_step` function from `selected_action_sell.py`; they do not
execute the complete adaptive runtime or establish game strength, whole-agent
speed, or a cause for earlier held timeouts. Original PR9997 source transport
was reused, not exported again. No games or experimental seed reservations.

Only the three existing entrypoints and this regression/evidence change.
`runtime.py`, COVE/BIRCH/BROOK changes, economic logic, ASH continuation, FINCH's
profiler, RAWLOAD's funded entrypoint, INTEGRATION's timer adapter, existing
workflow ownership and frozen PR9997 archive remain untouched. The consumer is
the next ordinary invocation of these existing adaptive/fixed/static files;
do not restart a running experiment or rewrite an older source-bound result.

## Real-parent consumer regression (separate follow-through)

The follow-on `test_entrypoint_real_clock.py` executes actual adaptive, fixed
and static actors in both seats: three methods, six constructed short prefixes,
48 integrated-parent calls, 48 cap-producer calls and 48 intact Arlene calls.
Every decision invokes each layer exactly once. Python call instrumentation
counts the real source functions; no implementation body is substituted.
Day/hour-only and explicit-step controls have identical complete actions and
selected adaptive snapshots at steps 0, 1, 2 and a fresh 0. Identified history
counts are 0, 7, 14, 0. Actors persist across nonzero calls and reset at zero;
the runtime module remains cached. The caller's observation stays unchanged.

Twelve official engine transitions advance the accepted control prefixes.
These are not full games and do not use game initialization seeds. The initial
projection fallback is identical in both clocks and remains in the raw records;
it is not hidden as an adaptive admission. Original entrypoint bytes under the
same real runtime produce six `KeyError: step` errors after the parent call,
while their six explicit controls succeed. Those runs have 12 actual calls per
layer and zero prefix transitions, not the fixed run's 48 calls and 12 transitions.

```sh
python3 -B revenue/kaggriculture/cloud-market-game-theory/adaptive/test_entrypoint_real_clock.py \
  --evaluator /existing/peer/evaluate.py --engine /existing/engine \
  --report /tmp/entrypoint-real-clock.json
```

All inputs must already be local. The test refuses to download a missing engine.
Use `--entrypoint-dir` for a preserved alternate entrypoint directory; its sibling
runtime and imports must keep the same dependency layout. The executed source
composition is deliberately not a claim about all of current main:

- Three entrypoints from PR10058 merge `f9dba7394dbd4c8b78fbf6e36912471dbbce9ddb`.
- Runtime plus eight other files from `fd80861e1420c5b1a79c781814f2364aef484fc8`:
  game-theory dependencies, selector, solver and history_streams; adaptive
  runtime and recourse; plan-continuation continuation; market-response flow
  and vendor/sorrel_adapter. Runtime blob is `fc633655bdb5df026ce2654668337214ec6771e5`.
- Unchanged original PR9997 parent closure, existing provider artifact10036877991,
  nested archive SHA256 `95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153`.
  This is not newer SPRUCE/WREN ledger or DELVE funding policy bytes.
- Existing evaluator and three pinned engine files from artifact10005621438.

`ENTRYPOINT-REAL-CLOCK-VALIDATION.json` binds the executed test, source recipe,
counts and successful log to the complete before/after evidence. The full 32
source identities per run, all actions/call counts/snapshot hashes, original
tracebacks and reproduction recipe are retained in Bryce's Library:
`TITAN-entrypoint-real-clock-evidence.zip`, file ID
`file_000000003dc881f5a45c5cca061ef8ab`, 17452 bytes, SHA256
`894af9924ab176e4101105b04206eabdaaa6d636f2387448a0e99fd219a483ea`.
All archive member hashes were verified after packaging. This follow-through
changes only test/evidence/this guide, not production, runtime, workflow, frozen
sources or running panels. It makes no whole-agent speed or game-strength claim.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
