# Cold-only immutable suffix construction

`plant_suffix.py::immutable_plant_suffixes(route)` replaces repeated Counter construction/copying with ordinary nonnegative dictionary increments, then exposes each detached suffix as a read-only mapping. Returned values, insertion order, endpoint length, mapping type and per-step detachment match the original construction. It counts every requested PLANT, including future no-ops, exactly as before; this does not infer execution or change seed admission.

## Canonical-writer integration

This addition does not modify any runtime, configuration, build mapping or CURRENT pointer. WIDEFIELD remains canonical writer. In the packaged `reference/integrated-selected/alder/seed_budget.py`, replace the Counter import with:

```python
from plant_suffix import immutable_plant_suffixes
```

Inside `_derive`, replace only the second per-route loop body with:

```python
for name, route in routes.items():
    suffixes[name] = immutable_plant_suffixes(route)
```

Include the helper at the package root. Keep prefix comparison, marshal version/content key, bounded cache, publication-after-completion, `remaining`, `apply` and per-instance events unchanged. No work is moved outside the entrypoint deadline to create the measured improvement.

## Validation

```sh
python -B revenue/kaggriculture/cloud-runtime-pulse/test_plant_suffix.py
```

Nine standalone tests cover 1,000 generated routes, exact values/order/type, immutable distinct per-step mappings, route mutation isolation, endpoint shape, duplicate planting and matching malformed-input exception classes. Twenty existing packaged seed-cache/recovery/entrypoint/deadline tests also passed on the composed local overlay. The seed tests include exact shipped-route semantics, content invalidation, cancellation-before-publication and fresh instance ledgers.

Eight retained observation tapes (5,752 calls) with exact evaluator Struct conversion matched all accepted composed returned-action and completed SELL/route/diagnostic state hashes. No caller mutation or fallback occurred. Replays add zero full games.

A separate first-call benchmark used the original retained 2,775-byte request, unmodified f6 evaluator Actor/worker, sequential fresh processes, fixed one-second parent deadline and 12 alternating AB/BA pairs. Baseline is the existing selected-core/public-snapshot composition plus PULSE's observed projection helper; candidate adds only this suffix construction. All 24 first calls returned identical actions, and all 12 candidate pairs were faster. Median actor call time was 39.728 to 35.520 milliseconds (10.59% lower); median parent RPC was 40.160 to 35.993 milliseconds. These percentages are not added to hot-path results or compared across different protocols.

This is a local cold-input measurement, not a hosted guarantee, new strength evidence, or explanation/repair of the original unanswered timeout. The original failure remains intact with unknown child timing/stage. Private input, source freeze, native profile, raw paired timings, tests and executable reproduction are delivered only within the participating-owner project Library.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
