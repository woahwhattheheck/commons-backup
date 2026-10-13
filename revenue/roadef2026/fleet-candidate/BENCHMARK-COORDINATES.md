# ROADEF benchmark coordinate-universe validation

## Scope

This change validates load coordinates before the matched-budget benchmark ranks a
solver result. It composes on top of the landed timeout-evidence, output-reservation,
sprint-reference, numeric-compatibility, and finite-load work. It changes no solver,
official-checker binary, score ordering, tolerance, budget accounting, process
handling, candidate configuration, qualification draft, attachment, or submission.

The source inspected for this work was Commons main `c5ddbbb57f130b27e1553e3a32c25db8648a081c`:

- `benchmark.py` Git blob `02779e670c846881ccf8e69f5e6cf62e51cce02a`
- 9,447 bytes
- SHA-256 `430e6499c88a592c2bf73284a10c7b2eac3f6c4c8cf4f7d5f159486a491d1653`

That source already rejects non-finite saturation values through `finite_loads`.
The function is retained byte-for-byte at the AST level.

## Reproduced defect

The benchmark previously sorted `checker-6.saturations` before proving that the
six-decimal report contained the same coordinates as the twelve-decimal report,
solver diagnostics, and the other solver arms. Python list ordering therefore
made a shortened equal prefix look better.

A real local CLI invocation using explicit synthetic solver/checker children gave:

- baseline six-decimal vector: `[0.75, 0.25]`
- candidate six-decimal vector: `[0.75]`
- candidate twelve-decimal and diagnostic vectors: both complete
- benchmark exit: `0`
- published candidate: `valid: true`, `vs_first: "win"`, `load_count: 1`
- `first_difference_rank: null`

The original result bytes are retained in the evidence packet. This controlled
fixture does **not** show that the official checker emitted an incomplete report or
that a historical ROADEF score was wrong.

## Correction

`load_coordinates` now requires a nonempty list of load-row objects, canonicalizes
`from` and `to` identifiers exactly as the existing reconciliation did, rejects
duplicate coordinates, and rejects booleans, nonnumeric values, and negative loads.
It then calls the existing `finite_loads` guard, preserving its native scientific
notation and non-finite diagnostics.

`validated_loads` requires equal coordinate sets across:

1. the six-decimal checker report used for ranking;
2. the twelve-decimal checker report used for reconciliation;
3. the solver's diagnostic loads; and
4. every solver arm for the same instance.

Only after those checks does it apply the existing descending sort and the unchanged
`2e-9` reconciliation tolerance. The benchmark still ignores transition cost when
load vectors differ, retains the incumbent on exact ties, and writes no result or
summary for a rejected arm. Raw process/checker outputs remain on disk.

Agreement among these reports is not an independent topology-completeness proof. If
all producers omit exactly the same legal coordinate, this check alone cannot know
that the topology contained it.

## Executed validation

The final source is 11,165 bytes, SHA-256
`789fda06bb7f255cbe9be77a9e2f7be4a2f03d7f3c5a81b4988df77735902c99`.

`test_benchmark_coordinates.py` contains 26 methods:

- **24 actual benchmark CLI-path methods pass.** They cover missing peaks/tails,
  altered coordinates, duplicates in each producer, string/int identifier aliases,
  cross-solver mismatches, malformed rows, empty reports, negative/bool/string
  values, retained finite-number rejection, order independence, a real lower-rank
  improvement, native scientific notation, and one real synthetic-child witness.
- The identical 24-method CLI bank against the exact landed source has **18 failed
  methods / 0 errors**. Thirteen failures are malformed cases that returned success;
  five are missing explicit diagnostics or evidence-order guarantees.
- Two additional source-contract methods pass: the landed `digest`, `execute`,
  `finite_loads`, and `reserve_outputs` function AST hashes remain exact; 300
  generated valid report triplets preserve every score, coordinate set, error value,
  zero tail, and input object.
- Python compilation passes. A generated unified diff applies cleanly to the exact
  landed benchmark source and reproduces the final bytes.

No official solver, official checker, network call, public-instance benchmark,
container run, qualification action, or new workflow was used. The real-child test
launches only local synthetic fixture scripts.

## Replay

From `revenue/roadef2026/fleet-candidate/`:

```sh
python test_benchmark_coordinates.py \
  --report /tmp/benchmark-coordinate-result.json
python -m py_compile benchmark.py test_benchmark_coordinates.py
```

For a bounded negative control, pass a copy of the pre-change benchmark with
`--benchmark` and select the 24 CLI methods recorded in the results file. The
historical false-win witness and all local test logs are retained outside the source
tree in the durable evidence archive referenced by the merge receipt.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
