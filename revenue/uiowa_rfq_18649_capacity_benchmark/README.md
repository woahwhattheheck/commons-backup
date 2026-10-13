# UIOWA-095 — production workflow capacity benchmark

Measures what the evidence-and-report preparation workflow actually costs at
three workload sizes, finds the stages that are genuinely expensive, fixes them,
and re-measures — while proving the output did not change.

Built by seat **OP5-OBSIDIAN** (Claude Opus 5) for RFQ 18649.

**The retained `results/` describe the original measured implementation.**
They are historical measurements, not current-decoder performance. Since
September 23, 2026 the optimized document reader validates UTF-8 through EOF
in bounded chunks. The earlier prefix-only document-label timings, overall
speedups, and whole-workflow memory figures below do not measure that repair.
No benchmark rerun or new performance claim accompanies the stream repair.
`results/BENCHMARK_REPORT.md` is *generated from* `results/benchmark_results.json`
rather than written by hand, so the prose and the data cannot drift apart.

All workloads are **SYNTHETIC**. No University of Iowa data, systems, people, or
findings appear anywhere in this lane.

---

## How to run it

Python 3 standard library only. No pip installs, no network, no services.

```bash
cd revenue/uiowa_rfq_18649_capacity_benchmark

# full benchmark: regenerates everything in results/
python3 benchmark.py

# one size only (skips the report, which needs all three)
python3 benchmark.py --sizes small

# run the workflow by hand against a collection you generated
python3 generate_collection.py --profile medium --out /tmp/c
python3 workflow.py /tmp/c --mode optimized --out /tmp/out
```

`benchmark.py` builds its collections in a temp directory and removes them.
Pass `--keep-workdir DIR` to keep them for inspection.

Reproducibility: the generator is seeded (`--seed`, default `20260919`). Same
profile + same seed produces byte-identical collections, asserted in the tests.
A second operator on a different machine will get **different timings and the
same answers** — the environment block in the results explains why the timings
differ.

---

## Files

| File | What it is |
|---|---|
| `workflow.py` | The workflow being measured. Five stages; two of them ship in both a `baseline` and an `optimized` implementation. |
| `generate_collection.py` | Deterministic synthetic collection generator, three size profiles, fixed seeded defects. |
| `benchmark.py` | The harness. `time.perf_counter` + `tracemalloc`, separate passes, plus the variant sweep, the crossover sweep and the report renderer. |
| `test_capacity_benchmark.py` | 36 `unittest` tests, including a guard that fails if the README drifts from the committed results. |
| `results/BENCHMARK_REPORT.md` | Generated report — environment, sizes, per-stage timings, scaling, rejected-variant comparison, crossover, peak allocation, import/export, analyst steps. |
| `results/benchmark_results.json` | Full measurement record, including every repeat's min/median/max. |
| `results/benchmark_results.csv` | The same timings flat, for a spreadsheet. |
| `results/environment.json` | The machine the numbers were taken on. |

---

## Historical measurements of the original implementation

Two bottlenecks, both traced to patterns in **already-delivered lane tools**, not
invented for this exercise:

**B1 — accidental quadratic in the statement-presence check.**
`revenue/uiowa_rfq_18649_traceability_rehearsal/validate_trace.py` concatenates
the report surfaces into one string and then runs `for sid in sids: if sid not in
report`. Each test is a full substring scan of the whole report. Because the
report is written *from* the statements, its length grows with the statement
count, so characters scanned grow as O(statements x report length).

Measured at the large workload — 3,000 statements, 631,500 report characters:

| | baseline | optimized | speedup |
|---|---:|---:|---:|
| statement-presence stage | 0.694289 s | 0.030794 s | **22.55x** |

The crossover sweep in the report isolates the stage and shows the shape
directly: from 10 to 1,280 statements (128x more work), the baseline went
from 0.000009 s to 0.114711 s — a **13,105x** increase, against
128² = 16,384. The optimized path grew 117x over the same range.

**B2 — whole file read to inspect its first 500 characters.**
`revenue/uiowa_rfq_18649_synthetic_collection/validate_collection.py` checks the
SYNTHETIC label with `path.read_text(encoding="utf-8")[:500]`, pulling every byte
of every evidence document into memory to look at 500 characters. Cost tracks
total collection bytes; peak memory tracks the single largest document.

| | baseline | optimized | speedup |
|---|---:|---:|---:|
| document-label stage, large (55 MB of documents) | 0.060024 s | 0.014478 s | **4.15x** |

**Stages that turned out NOT to be bottlenecks**, and are published as such:
`import`, `link_check` and `coverage_rollup` are within noise of each other in
both modes at every size. They are measured anyway so "these are fine" is a
measurement rather than an assumption.

End to end at the large workload: **0.8427 s → 0.1287 s** (6.55x). See the
report for the exact run.

### The fix that was wrong, and how it got caught

The obvious repair for B1 is `set(re.findall(...))` over the report. It is the
fastest of the three — and it is the one that was rejected, because the
`tracemalloc` pass showed it carrying a far larger peak: `findall` materialises
every token in the report as a list before the set exists, so peak allocation
tracks report size. On a timing-only benchmark that version ships unnoticed. In
the first full run of this harness it pushed whole-workflow peak memory at the
large size *above* the baseline.

Measured at 3,000 statements / 630,012 report characters, statement check only.
All three return the identical answer, asserted before timing:

```
baseline (delivered)        0.62960 s        36,152 bytes peak
findall + set (rejected)    0.02097 s     5,152,986 bytes peak
finditer + length filter    0.02498 s       332,883 bytes peak   <- shipped
```

This table is regenerated by `benchmark.py` on every run — the rejected option
stays checkable instead of becoming a story in a commit message.

The shipped shape trades part of the speed win for roughly a 15x smaller peak,
and whole-workflow peak memory now beats the baseline at all three sizes
(18,256,365 → 16,454,971 bytes at large). This is the reason the harness
measures memory in a separate pass instead of trusting the clock alone.

### An honest negative

Below **160 trace statements** (measured crossover, not interpolated) the
*delivered* algorithm is the faster one — one pass over the report costs more
than a few dozen substring scans of a small report. The optimized version still
ships: being wrong at the small end costs under a millisecond, and being wrong at
the large end costs most of a second and grows quadratically. The losing rows are
in the report rather than trimmed out of it.

---

## Output correctness

The optimized reader retains the first 500 decoded characters but consumes the
whole document in 64-Ki-character chunks, including long single-line files.
Both modes reject malformed UTF-8 anywhere in a document; the CLI names the
file, returns exit 2, and emits no success summary or new report bundle. The
reader trades prefix-only I/O for the baseline's full-stream validity contract
without retaining the entire document.

The importer also refuses `.uiowa095-incomplete`, including a dangling marker
symlink, before reading the manifest. A manifest left by an interrupted
collection generator is not a completed collection. See [OUTPUT_SAFETY.md](OUTPUT_SAFETY.md).
The marker is a local producer/consumer signal, not an atomic-publication or
concurrent-writer guarantee.

Expected input, decoding and filesystem failures produce a diagnostic on stderr
and exit 2. A completed workflow can still report evidence gaps; those existing
report semantics and output formats are unchanged. An export I/O failure can
leave partial output, and outputs are not transactionally rolled back.

The existing before/after benchmark compares completed results:

- Baseline and optimized are compared on the **full result** — every link error,
  every statement error, every document error, the entire coverage matrix
  including its UNKNOWN cells, and the follow-up count — at all three sizes, on
  every repeat. The harness raises `SystemExit` rather than publishing a
  benchmark of two different answers.
- `test_harness_refuses_to_publish_when_modes_disagree` monkeypatches the
  optimized check into a fast wrong answer and asserts the harness aborts, so the
  gate is known to work rather than merely present.
- The optimized statement check preserves the baseline's substring semantics
  **exactly**, including the case where an id is a substring of a longer id
  (`S-001` inside `S-0012`). That behaviour is arguably a bug in the delivered
  check, but an optimization is not the place to silently change an answer; the
  test pins the current behaviour so changing it later is a deliberate decision.
- Exported bytes are identical across modes and across repeat runs.

---

## What's real vs. draft

**Implemented:** the generator, workflow and benchmark harness. The retained
measurements describe their original source generations; the full-stream UTF-8
repair has not been rebenchmarked. Historical results are not relabeled as
measurements of changed code.

**Draft / scoped to this lane:** the workflow here is a faithful re-implementation
of the preparation stages for benchmarking purposes — it is not a drop-in
replacement for the delivered lane tools. B1 and B2 live in lanes owned by other
seats; per fleet rules this lane does **not** edit them. The repaired
implementation and the measurement are here, and the finding is reported for the
owning seats to take or leave.

**Fiction, labelled as fiction:** every generated collection. Documents carry a
SYNTHETIC banner in their first line, rows carry `synthetic=true`, and the
manifest carries a disclaimer. The generated content is deliberately generic —
no real system names.

---

## University inputs still UNKNOWN

These are not estimated anywhere in this lane, and the measured curve is **not**
extrapolated onto them:

- **The real size of the University's evidence collection** — number of evidence
  items, findings, recommendations, trace statements, and report length. The
  three profiles here are benchmark inputs, chosen to bracket a range, not a
  model of the engagement.
- **Real evidence document sizes and count**, and how many are large exports.
- **The hardware the workflow will actually run on.** All timings here are from
  one 4-CPU container; they separate algorithms, not machines.
- **Analyst minutes per follow-up item.** The workflow counts what it returns to
  a human; it does not convert that count into hours. Operator command count is
  fixed at 2 per run and does not grow with collection size — that part is
  measured.
- **Cold-cache first-touch cost.** Counted repeats run warm, and the report says
  so. A cold run was not measured.

---

## Guardrails

- Missing evidence stays **UNKNOWN**. A coverage cell with no evidence is
  reported as `UNKNOWN` in every field, never as `0` and never as a pass —
  asserted in tests, and carried through to the exported CSV and JSON.
- A document listed in the manifest but absent on disk is an **error**, not a
  silent skip. A missing input table or report surface raises rather than
  producing a short, clean-looking result.
- No certification, compliance, maturity-score, or peer-percentile claim is made
  anywhere. No individual is scored.
- No network at runtime, no pip installs, no writes outside the output directory
  passed in.
