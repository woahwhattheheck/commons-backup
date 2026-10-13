# V5 callback runtime-budget profile

`runtime_budget_profile.py` turns the diagnostics already emitted by
`titan_runtime.TitanAgent.act()` into a deterministic, fail-closed performance
receipt. It does **not** instrument or change gameplay.

Use this before widening an expensive V5 policy or composition. The profiler
answers two separate questions:

1. Did every callback in the declared experiment design produce exactly one
   valid timing receipt?
2. Does the observed candidate fit the declared planner budget with an
   acceptable deadline-fallback rate?

Example:

```bash
python -B candidates/v5/runtime-budget/runtime_budget_profile.py \
  callbacks.jsonl \
  --expected-jsonl expected-callbacks.jsonl \
  --budget-seconds 0.10 \
  --reserve-seconds 0.02 \
  --max-fallback-rate 0.001 \
  --output runtime-budget.json
```

Input callback rows identify `candidate`, `seed`, `seat`, and `step`. Timing
diagnostics can be nested under `diagnostics` or flat:

```json
{"candidate":"v5c:abc","seed":1209124001,"seat":0,"step":240,"diagnostics":{"status":"completed","elapsed_seconds":0.012,"act_cpu_seconds":0.011}}
```

A deadline fallback must include the exact `fallback_stage`. The tool rejects
duplicate identities, booleans/type aliases in integer identity fields,
negative/non-finite timing, unknown statuses, malformed expected designs, and
invalid budget contracts.

The report contains wall/CPU nearest-rank p50/p95/p99/max overall, by game
third (early/mid/late), and by candidate; fallback-stage counts; expected
missing/extra identities; and p99 planner headroom. `promotion_ready=true`
requires all of the following:

- an explicit expected-key JSONL was supplied;
- no expected callback identity is missing;
- the deadline-fallback rate is at or below `--max-fallback-rate`;
- p99 wall time is at or below `budget_seconds - reserve_seconds`.

An observed subset can still be useful diagnostically, but it cannot
masquerade as performance-admission evidence.
