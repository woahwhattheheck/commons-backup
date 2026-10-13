# Aggregate saved activation telemetry

`report.py` consumes the shared `cok-activation-v1` JSONL emitted by
`CokObserver.last_record` and the existing observation CLI. It imports only the
landed observer's aggregation function. No source artifact, opponent instance,
engine, configuration, replay reconstruction or network is needed to aggregate
already-saved telemetry.

```sh
python report.py --input existing-activation.jsonl --output activation-summary.json
```

Supply one JSON object per line, with `match_id` added by the caller when a file
contains multiple games. The source identity and schema are checked by the same
`summarize` function used in `observe.py`. The output preserves the opponent's
branch-selection state, expert transitions, cached-retry counts, observed step coverage,
telemetry errors and optional expected-action mismatches. It never infers game
outcomes from activation. A full observed step set remains distinct from a
validated full game or continuous state trajectory.

The input is streamed one row at a time rather than collected in a list. Memory
still grows with distinct actors, unique observed steps and reported transitions;
this is not a constant-memory guarantee for arbitrary logs. The summary is
written to a temporary file in the destination directory and atomically replaced
only after all records are read and validated. Invalid JSON, schema/source drift
or a failed replacement leaves the previous output intact. Identical, resolved
and hard-linked input/output paths are rejected so the input is preserved.

Exit status is 0 for a completed aggregate with no reported mismatches/errors,
1 for a completed aggregate containing such reports, and 2 for an input/output
failure. An empty log produces an empty actor list, not evidence of successful
execution. Blank lines are ignored.

## Reproduction

```sh
python -m unittest -v test_report
```

Six report-consumer tests pass: equivalence with the existing aggregator,
separate actors and retries, a no-controller-call assertion, source/schema drift,
recorded errors and action mismatch exit codes, malformed/nonobject input,
input-alias preservation, atomic replacement failure, lazy iteration and empty
input. These are report fixtures, not newly run games. The original 16-test
observer result and its exact source bytes remain unchanged in `VALIDATION.json`.
The report follow-through is recorded separately in `REPORT-VALIDATION.json`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
