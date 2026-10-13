# Native TRACE inputs and exact actor construction

The existing saved-observation profiler now accepts TRACE's candidate-only JSONL or JSONL.gz directly, with its separate `titan.recorded-actor-inputs.v1` receipt. This is a consumer adaptation, not another frame aligner, replay implementation or policy runner.

## Invocation

```sh
D=revenue/kaggriculture/cloud-runtime-budget
R=/existing/DELVE/runtime/revenue/kaggriculture
python -B "$D/profile_saved.py" \
  --entrypoint "$R/cloud-integration-differentials/funded_main.py" \
  --factory make_agent --factory-kwargs '{"funded":false}' \
  --source-root "$R" \
  --timing-source revenue/kaggriculture/cloud-combination-analysis/execution_timing.py \
  --replay /existing/inputs.jsonl.gz --input-receipt /existing/receipt.json \
  --seat 0 --max-decisions 719 --classification retained-development-inputs \
  --output /new/control-profile.json
```

Use the actual source closure recorded by the input owner. DELVE's funding-off controller uses the archived JUNIPER integration hook with SELL on; it is not a byte-identical PR9997 or current-main candidate. `--factory-kwargs` is a JSON object forwarded once to the existing factory. Body exceptions stay failures, not retries. `--source-root` covers Python dependencies in sibling directories and includes their functions in sampled profiles. Its default remains the entrypoint directory. Files outside the chosen root are not implicitly included.

## Input and execution binding

The receipt supplies `output_file_sha256`, `input_jsonl_sha256`, `observation_count`, `candidate_seat`, `candidate_actor_rng_seed`, and `candidate_pythonhashseed`. The consumer checks the compressed/plain file and decoded stream, keeps per-row configuration, and executes the selected uninterrupted prefix. A prefix limit does not change the recorded whole-stream identity. The original JSON/JSON.gz input modes remain available.

`PYTHONHASHSEED` is set before each child interpreter starts. Python `random` is seeded before importing the selected actor, following the existing evaluator's independent actor-seed convention. The environment/game seed remains provenance and is never supplied as policy configuration. Normalized metadata without an explicit `--input-receipt` does not reseed the legacy actor. This does not infer or recover any unrecorded random state.

Full expected-action correspondence is separate from ordinary/instrumented parity. The former compares this actor against the supplied original actions; the latter checks whether profiling changed its outputs. A complete pair of matching instrumented/ordinary streams alone does not prove that an input is on-policy, that the correct historical source was supplied, or that a provenance receipt is authentic. Preserve the original source and input-owner receipt alongside each result.

## Executed compatibility

Twenty-seven methods pass: the original16 are unchanged, plus11 native-input, seeded-process, configuration, factory and sibling-source checks. The real PR9997 archived agent also consumed a three-observation native-format fixture copied from the already-used public106540665 prefix. Both processes emitted exactly the three hashes already recorded by PR10052, with all17 Python source files unchanged. This fixture checks the real consumer without repeating a game; it is not TRACE output or a recovered historical development trajectory. Source, test and report digests are in `TRACE-RESULTS.json`.

Original PR10052 measurements, reports and `RESULTS.json` remain pinned to their original profiler and archive. The source-parse, path-manifest and spec-guard jobs succeeded. Its open-door job101905153313 matched a README paragraph about complete observations as an admission phrase; that paragraph is clarified here without changing the shared guard or input semantics. Hosted checks for this new source are separate.

TRACE retains original frame alignment, digest validation and WIDEFIELD input recovery. No new game, engine transition, submission, source export, workflow or selected-policy change is part of this consumer.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
