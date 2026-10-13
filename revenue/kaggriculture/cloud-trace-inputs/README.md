# Recorded WIDEFIELD trace → actor input stream

Consumer: FINCH's existing runtime profiler. This adapter reconstructs a recorded
DEVELOPMENT trajectory using its already-authored joint actions, not new policy
decisions. It reuses `cloud-widefield-lab/trace_apex_loss.py::play` and the pinned
interpreter through the existing `cloud-eval` loader. Original lab, evaluator,
policy, archive and profiler files are not changed.

## Execute on the retained input

WIDEFIELD PR10009, merge `5ed418fd6d2abf5fede9e61a6def394e1368641f`,
`results/diagnosis/apex-9921001-recorded-input.json` identifies the original
`diagnosis/integrated-pr9997-fullstate.json` record. Its native temporary path is
provenance, not a portable path. Find the actual member in the original retained
archive before extracting it; the adapter needs only that JSON and the existing
source/engine checkout.

```sh
# In the existing archive-parts directory, preserve the original part order:
cat full-results-9921001-9921032.tar.gz.part-* > /tmp/widefield-results.tar.gz
sha256sum /tmp/widefield-results.tar.gz
# Required archive digest:
# 2859491973c51d21a95ec80135ac7385ce889c335ff619012f9f86dabce55a11
tar -tzf /tmp/widefield-results.tar.gz | grep 'integrated-pr9997-fullstate.json$'
```

After materializing that existing member, from the repository root:

```sh
python -B revenue/kaggriculture/cloud-trace-inputs/recorded_inputs.py \
  --record /path/to/integrated-pr9997-fullstate.json \
  --engine-dir /path/to/existing/pinned-engine \
  --expected-trace f4681e20d6bf54598d330c90ff29dc477d4dd9e790d29a3df05d2b1863d86ed3 \
  --output /path/to/output/integrated-inputs.jsonl.gz \
  --receipt /path/to/output/integrated-inputs-receipt.json
```

The requested record is seed 9921001, candidate seat 0, original terminal cash
75095 / 78506. The original archive and that historical JSON have not been
materialized by this implementation session; no successful reconstruction of
that particular record or on-policy profiling result is claimed here. The
missing input is that exact existing JSON, not permission for a new game panel.
GitHub artifact download is an available transport; original source owners can
reuse an existing artifact route rather than create another exporter.

## Contract and interpretation

The CLI verifies the original record schema, source trace selection and exact
engine hashes using the existing loader. `recover_inputs(game, evaluator,
tracer, engine, engine_dir, loader)` accepts those already-loaded dependencies
and returns `(inputs, receipt)`. The callable's caller is responsible for the
same source verification performed by the CLI.

Each output row contains `step`, `seat`, complete `observation`,
`configuration` and the recorded `expected_action` for the candidate only.
Inputs cross the same JSON serialization boundary as the original Actor.
The environment seed stays provenance-only: the engine removes it from the
configuration delivered to the agent. Opponent private observations are not
exported. The full candidate input sequence is retained, including step 683.

No real Actor is constructed. A detached facade returns only recorded actions;
it does not patch the shared evaluator module. Completion requires every
recorded action/bank row, terminal score and complete original trace digest to
agree. That digest includes the full final observations. The code does not
fabricate missing actions, observations or a new successful game result.

A recovered input sequence is NOT a serialized actor checkpoint. FINCH must
initialize the exact candidate once and feed its entire ordered prefix through
that same persistent actor. Compare each returned action with `expected_action`
before describing the workload as on-policy. Match the original candidate's
Python/random environment (`PYTHONHASHSEED=20260907`, random seed 20260907) and
source closure. Instantiating a fresh candidate at a late step is a different
workload. Changed-source replay is also a different workload until action
correspondence is established. This adapter records no policy timing and makes
no hosted deadline or strength claim.

The JSONL and receipt are written by separate atomic replacements, with the
receipt last. They are not a two-file transaction. Consumers must check the
receipt's `output_file_sha256` before accepting an output, including after an
interruption. The receipt also binds the uncompressed JSONL, source record,
engine, adapter, evaluator and tracer hashes. Gzip output uses `mtime=0`.

## Executed validation

```sh
python -B revenue/kaggriculture/cloud-trace-inputs/test_recorded_inputs.py \
  --engine-dir /path/to/existing/pinned-engine \
  --report /tmp/recorded-input-tests.json
```

19 methods pass, zero failures/errors. The two fixtures are complete 719-step,
fixed-action official-engine trajectories in both seats; they are explicitly
synthetic fixtures, not WIDEFIELD records or policy evaluation games. Cases
exercise source immutability, complete candidate inputs, trace/action/bank/score
correspondence, altered/missing/truncated records, no real actor invocation,
gzip/receipt output and failed replacement preserving the previous file.
`TEST-RESULTS.json` is the original executed result. Its `engine_calls` field
counts calls through the instrumented test engine, not additional CLI subprocess
or whole-fleet execution; it is not a game count.

Reused source identities:

- Engine ref `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, existing artifact
  `10005621438`; exact file hashes are retained in `TEST-RESULTS.json`.
- Evaluator blob `6bcde5b7dc1abc33eb3cd7ec42833affc2d28b53`, existing source-pack
  artifact `10030763484`.
- Tracer blob `8194b53a3f9df6a81998a7c56a703c056d17238f`, PR10009 source.

Source ownership: TRACE-9022 supplies this one reconstruction implementation;
TRACE-9042 was asked to consume it for original-record materialization and
independent correspondence. FINCH retains profiling and WIDEFIELD retains its
original results. No profiler, workflow, source-export job, seed reservation,
policy/default change, Kaggle upload or new spend is introduced.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
