# Stream observations into COK activation telemetry

`stream_observations.py` adds a lower-memory observation consumer beside the
existing observer and saved-report CLI. The original `observe.py`, `report.py`,
COK source, official loader and their accepted results are unchanged.

```sh
python stream_observations.py --source "$SOURCES/cok-v10/main.py" --pack "$PACK" \
  --input existing-observations.jsonl --output activation.jsonl \
  --summary activation-summary.json
```

The input and output schemas are identical to `observe.py::run_jsonl`. Each input
line contains `observation`, optional `configuration`, optional `match_id`, and
optional `expected_action`. Blank lines still count toward input line numbers.
Use original delivered observations; missing history is not reconstructed.

The callable `iter_records(source, pack, lines)` yields one detached telemetry
record at a time. `run_jsonl(source, pack, input_path, output_path, summary_path)`
writes each record and immediately passes it to the existing `summarize`
function. It no longer retains every generated record in a list. Each match and
player position still has its own persistent original controller, so interleaved
matches and same-step cached retries retain their original behavior. Match IDs
remain reporting metadata and are not passed to the policy.

This is not a constant-memory promise: open controller histories, per-match
counters, unique observed steps and transition summaries still occupy memory.
The implementation removes retained full telemetry rows, not required policy
state. It neither imports an engine nor runs additional games.

## Measured processing behavior

Python 3.13.5, fresh subprocess per consumer, with `tracemalloc` started before
loading the actual opponent. Input repeats the original development-9894001
position-0 step-72 observation. This is explicitly a repeated-observation retry
load, not a chronological game, new validation seed, or representative league.

| Input records | Original peak Python bytes | Streaming peak Python bytes | Reduction |
| --- | ---: | ---: | ---: |
| 1,024 | 19,805,345 | 17,873,903 | 9.75% |
| 8,192 | 33,890,311 | 17,873,866 | 47.26% |

Both runs produced byte-identical telemetry and summary files, with zero
telemetry errors and unchanged inputs. Instrumented duration on the larger load
was 52.078413 seconds original versus 52.078563 seconds streaming; there is no
measured speedup claim. These are traced Python allocations, not total process
RSS or in-game action latency. Exact records are in `STREAM-VALIDATION.json`.

The 18 original sparse checkpoints (nine per position) also produce identical
old/new telemetry and summaries. Their missing full histories remain missing;
this is consumer equivalence, not a repeat of IRIS's complete-game action proof.
No original scored panel or interpreter replay was performed.

## Output handling

Both output files are staged before publication. Invalid input or policy loading
leaves previous outputs unchanged. Output aliases of the supplied source or
observation file, including symbolic and hard links, are detected. Outputs may
not refer to each other. An ordinary second-replacement failure restores the
first previous output; a failed rollback retains the original backup path in the
error. Existing output symlinks keep referring to their intended targets.

Individual file replacements are atomic; the pair is **not** a crash-atomic
transaction. A process kill or concurrent reader can observe a partial pair.
Staging needs disk space for new outputs and temporary copies of old outputs.
Do not use dependency files or concurrently edited files as output destinations.

Exit 0 means completed processing with no recorded telemetry/action mismatch;
exit 1 means completed processing with such records; exit 2 means an input/output
failure. Empty input produces an empty report, not evidence of successful games.

## Reproduce

Use the existing source/loader paths from [README.md](README.md). The exact COK
source remains SHA256 `56831f3c43c9727d90016b7a7a8d4eb51d1a4c08c1120d58f061d9176e8bc109`.
The consumed observer remains Git blob `eee78b475e4a9a5e30ac59025e7eeb507d41135b`.

```sh
T07_COK_SOURCE="$SOURCES/cok-v10/main.py" T07_PACK="$PACK" \
  python -m unittest -v test_stream_observations
python benchmark_stream.py --source "$SOURCES/cok-v10/main.py" --pack "$PACK" \
  --input supplied-observations.jsonl --output-dir new-benchmark-directory
```

The benchmark creates a new output directory, executes each consumer once in a
fresh process, and writes its actual hashes, timings, memory peaks and output
comparison. Timing includes allocation instrumentation. It does not execute an
engine. Eleven dedicated tests cover exact legacy output, interleaved histories,
retry behavior, lazy consumption, real-source calls, errors and output recovery.

Original-data locator: Library `/TITAN-IRIS-COK9894001-evidence-20260907.zip`,
SHA256 `27294547deb92ae9ddf7f6ffa8860aa2f5744e09ce2674b139904a2092446c8f`.
Use its retained bytes rather than rerunning an export or game. To construct the
retry load from that extracted archive, let `IRIS` name the extraction root:

```python
import json
from pathlib import Path

rows = (Path(IRIS) / "original-games/seed-9894001-seat-0/cok.jsonl").read_text().splitlines()
checkpoint = next(row for row in map(json.loads, rows) if row["step"] == 72)
record = {"match_id": "retry-load-test", "observation": checkpoint["observation"],
          "configuration": checkpoint["configuration"]}
line = json.dumps(record, sort_keys=True) + "\n"
with Path("retry-input.jsonl").open("w", encoding="utf-8") as output:
    for _ in range(8192):
        output.write(line)
```

New consumer, tests and benchmark: Apache-2.0 under the repository license.
Original source, loader and evidence retain their existing notices and provenance.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
