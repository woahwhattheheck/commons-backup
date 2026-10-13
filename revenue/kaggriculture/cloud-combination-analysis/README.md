# Executor initialization and first-action timing

`execution_timing.py` observes an existing per-match factory and its already-bound
callable. It changes no policy, arity selection, source loader, game loop,
opponent, seed choice or timeout behavior. Every factory/action invocation is
forwarded once, with identical argument and result objects; exceptions propagate.

## Existing executor binding

Keep CALLABLE's signature-selection correction in `cloud-model-lab/execute_arm.py`.
This observer composes *after* that binding and does not replace it. Make a new
observer inside each `game(...)` call, after the existing factory argument is
available:

```python
from execution_timing import TimedFactory

observer = TimedFactory(factory)
try:
    # Existing environment/opponent setup stays here.
    me = observer()  # replaces only me = factory()
    # Existing game loop, me(obs, cfg), receipts and exception handling remain.
finally:
    row['executor_timing'] = observer.timings()
```

Add the `finally` to the existing result-preserving try/except, rather than
replacing its error handling. The snapshot survives a constructor failure. If an
error occurs before the factory is attempted it remains `None`, not zero time.
No current run needs to be restarted. The source owner decides when to consume
this optional binding; delivery of this component is not a live-ingestion claim.

## Interpreting the fields

- `initialization_s`: wall time inside the **supplied** factory, including only
  imports/construction it actually performs. Interpreter launch, earlier imports,
  source retrieval, environment/opponent setup and external work are excluded.
- `first_action_s` and `max_action_s`: first attempted action and largest observed
  action respectively, including failed calls. `max_later_action_s` excludes the
  first. Unattempted quantities stay `None`.
- `initialization_plus_first_action_s`: initialization plus the **same actor's
  first attempted action**, never initialization plus a different turn's maximum.
- `initialization_failed`, `calls`, `failures`: preserve measurement state even
  when the wrapped factory/action raises. Existing exception objects remain intact.

These are in-process timings with existing Python/import/OS caches. They are NOT
fresh-process cold-start, worst possible runtime, enforced deadline or hosted
performance measurements. The observer does not interrupt slow calls. Use
FINCH's independent budget work and ECON-STRESS's reached-state/timeout work for
those questions. Async or generator policies would require timing their deferred
execution separately; this synchronous observer measures only the direct call.
The observer introduces clock/counter overhead; it does not assert zero overhead.

## Validation and reproduction

```sh
cd revenue/kaggriculture/cloud-combination-analysis
python -B -m unittest -v test_execution_timing
python -B policy_smoke.py \
  --arlene /path/to/existing/intact/arlene.py --out policy-smoke.json
```

Sixteen regression methods pass. They cover exact once-only forwarding, same-instance
timing sums, initialization/action failures, independent per-match records, preserved
argument/result/exception identity, bound-state continuity and no invented timing.
The smoke executes actual intact Arlene SHA256
`1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4`
on twelve explicit **synthetic** observations across both player positions.
All actions and post-call observations match uninstrumented controls. These are
callable-compatibility cases, not reached-game evidence. Zero new games or seeds.

`VALIDATION.json` retains the complete test log, smoke actions/timings and source
hashes. Existing artifact10030763484 supplied the source; no new export was run.

## Provenance and scope

The observed executor blob was `2b4ee527682e8ad3cd0fde50aeb94e7cb38ad539` on
`claude/kaggriculture-titan-cloud-if51sj`. It creates `me=factory()` before timing
the first action. Its existing `worst_action_s` therefore does not include that
factory. This addition supplies a separate field; it does not relabel historical
results or change CALLABLE's independent arity repair.

TANDEM owns only this directory. Claude owns the executor; CALLABLE owns its
signature repair; FINCH owns runtime-budget A. Existing integrated candidate,
selection, game panels and peer source files are unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
