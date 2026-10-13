# UIOWA-095 -- production workflow capacity benchmark

Measured results for the evidence-and-report preparation workflow. Every number
below was produced by `benchmark.py` on the machine described under Environment,
in the run stamped there. Nothing here is illustrative and nothing is carried over
from an earlier run -- this file is generated from `benchmark_results.json`.

All workloads are SYNTHETIC fixtures. No University of Iowa data was used.

## Environment

| Property | Value |
| --- | --- |
| python_version | 3.11.15 |
| python_implementation | CPython |
| python_build | main Mar  3 2026 09:26:23 |
| platform | Linux-6.18.44-fc-v37-x86_64-with-glibc2.39 |
| machine | x86_64 |
| processor_model | Intel(R) Xeon(R) Processor @ 2.80GHz |
| cpu_count_logical | 4 |
| cpu_affinity_count | 4 |
| timer | time.perf_counter |
| memory_probe | tracemalloc (Python-level allocations only; excludes interpreter overhead and OS RSS) |
| page_cache | warm -- one uncounted warmup run precedes the counted repeats at every size |
| container_note | Shared CI-style container. Minimum-of-repeats is the cleanest signal; median is reported alongside so noise is visible. |
| measured_at_utc | 2026-09-19T14:05:15Z |

## Workload sizes

Sizes are inputs chosen for this benchmark. They are not an estimate of the
University's real collection, which is **UNKNOWN**.

| Size | Evidence rows | Findings | Recommendations | Trace statements | Documents listed | Report chars | Collection bytes | Largest document bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| small | 200 | 60 | 24 | 60 | 40 | 12,030 | 831,031 | 238,295 |
| medium | 2,000 | 600 | 240 | 600 | 200 | 122,220 | 10,671,438 | 715,382 |
| large | 10,000 | 3,000 | 1,200 | 3,000 | 600 | 631,500 | 59,068,523 | 1,430,897 |

## End-to-end elapsed time (measured)

Minimum and median of the counted repeats, after one uncounted warmup.

| Size | Repeats | Baseline min (s) | Baseline median (s) | Optimized min (s) | Optimized median (s) | Speedup on min |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| small | 5 | 0.0043 | 0.0045 | 0.0041 | 0.0044 | 1.06x |
| medium | 5 | 0.0461 | 0.0472 | 0.0275 | 0.0277 | 1.68x |
| large | 3 | 0.8427 | 0.8458 | 0.1287 | 0.1292 | 6.55x |

## Per-stage elapsed time (measured, minimum of repeats, seconds)

This is the table that says which stages were actually hot and which only
looked expensive. `link_check`, `coverage_rollup` and `export` are the same code
in both modes; they are measured anyway so the claim 'these are not the
bottleneck' is a measurement rather than an assertion.

| Size | Stage | Baseline (s) | Optimized (s) | Delta (s) | Speedup |
| --- | --- | ---: | ---: | ---: | ---: |
| small | import | 0.001438 | 0.001469 | -0.000031 | 0.98x |
| small | link_check | 0.000270 | 0.000275 | -0.000005 | 0.98x |
| small | statement_presence | 0.000191 | 0.000603 | -0.000412 | 0.32x |
| small | document_labels | 0.001500 | 0.000976 | +0.000524 | 1.54x |
| small | coverage_rollup | 0.000103 | 0.000100 | +0.000003 | 1.03x |
| small | export | 0.000545 | 0.000507 | +0.000038 | 1.07x |
| medium | import | 0.012259 | 0.012126 | +0.000133 | 1.01x |
| medium | link_check | 0.002905 | 0.002836 | +0.000068 | 1.02x |
| medium | statement_presence | 0.015860 | 0.005961 | +0.009899 | 2.66x |
| medium | document_labels | 0.013432 | 0.004887 | +0.008545 | 2.75x |
| medium | coverage_rollup | 0.000955 | 0.000894 | +0.000061 | 1.07x |
| medium | export | 0.000669 | 0.000622 | +0.000047 | 1.08x |
| large | import | 0.062565 | 0.060322 | +0.002243 | 1.04x |
| large | link_check | 0.017624 | 0.016643 | +0.000981 | 1.06x |
| large | statement_presence | 0.694289 | 0.030794 | +0.663495 | 22.55x |
| large | document_labels | 0.060024 | 0.014478 | +0.045547 | 4.15x |
| large | coverage_rollup | 0.005000 | 0.004892 | +0.000107 | 1.02x |
| large | export | 0.000599 | 0.000640 | -0.000041 | 0.94x |

## Scaling of the repaired stages (measured growth, small -> large)

| Quantity | small | large | growth |
| --- | ---: | ---: | ---: |
| trace statements | 60 | 3,000 | 50.0x |
| report characters | 12,030 | 631,500 | 52.5x |
| statement_presence baseline (s) | 0.000191 | 0.694289 | 3635.4x |
| statement_presence optimized (s) | 0.000603 | 0.030794 | 51.0x |
| document bytes on disk | 748,328 | 55,152,446 | 73.7x |
| document_labels baseline (s) | 0.001500 | 0.060024 | 40.0x |
| document_labels optimized (s) | 0.000976 | 0.014478 | 14.8x |

Read the two `statement_presence` rows against the first two rows. Statement
count and report length both grow, and the baseline stage grows by roughly their
product -- that is the quadratic. The optimized stage grows with report length
alone.

## Why the shipped repair is not the obvious one (measured)

Three implementations of the statement check, all returning the identical
answer, at 3,000 statements / 630,012 report characters. Time and peak
memory measured in separate passes.

| Variant | Elapsed min (s) | Peak bytes |
| --- | ---: | ---: |
| baseline (delivered: scan per id) | 0.629604 | 36,152 |
| findall + set (rejected: fast, fat) | 0.020972 | 5,152,986 |
| finditer + length filter (shipped) | 0.024980 | 332,883 |

Timing alone selects the middle row. The peak-allocation column is why that variant was not shipped:
`findall` materialises every run in the report as a list before the set exists, so
peak allocation tracks report size. The shipped row gives back part of the speed
win and removes most of the memory cost. This table regenerates on every run, so
the rejected option stays checkable instead of becoming a story.

## Where the repaired check starts to pay off (measured crossover)

The three-size sweep showed the optimized statement check LOSING at the small
workload. That is a real result, so here is where it actually turns over. Each
row is timed on this machine in this run, statement check only, 200 report characters per statement, minimum of 7 repeats after a warmup.

| Trace statements | Report chars | Baseline (s) | Optimized (s) | Optimized faster? |
| ---: | ---: | ---: | ---: | --- |
| 10 | 2,112 | 0.000009 | 0.000090 | no |
| 20 | 4,212 | 0.000018 | 0.000171 | no |
| 40 | 8,412 | 0.000046 | 0.000315 | no |
| 80 | 16,812 | 0.000144 | 0.000641 | no |
| 160 | 33,612 | 0.001853 | 0.001291 | yes |
| 320 | 67,212 | 0.007259 | 0.002587 | yes |
| 640 | 134,412 | 0.029523 | 0.005179 | yes |
| 1,280 | 268,812 | 0.114711 | 0.010496 | yes |

**Smallest measured statement count at which the repaired check wins: 160.**

That figure is the smallest point that was actually run, not an interpolation
between points and not a fitted threshold. Below it the delivered algorithm is
the faster one, by a margin measured in fractions of a millisecond. The repaired
version is still what ships: the cost of being wrong at the small end is under a
millisecond, and the cost of being wrong at the large end is most of a second and
grows with the square of the engagement.

## Peak Python-allocated memory (measured, tracemalloc)

Separate pass from the timings. `tracemalloc` sees Python-level allocations only;
it is not process RSS.

| Size | Baseline peak (bytes) | Optimized peak (bytes) | Delta (bytes) | Ratio |
| --- | ---: | ---: | ---: | ---: |
| small | 810,092 | 491,194 | -318,898 | 1.65x |
| medium | 4,550,716 | 3,379,396 | -1,171,320 | 1.35x |
| large | 18,256,365 | 16,454,971 | -1,801,394 | 1.11x |

## Import / export behaviour (measured)

| Size | Rows imported | Documents listed | Documents on disk | coverage-matrix.csv | workflow-result.json | workflow-report.md |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| small | 344 | 40 | 39 | 559 | 3,193 | 348 |
| medium | 3,440 | 200 | 199 | 603 | 3,240 | 351 |
| large | 17,200 | 600 | 599 | 636 | 3,280 | 352 |

Export volume is flat in the number of evidence rows because the exported
artifacts are the coverage matrix and the error list, not a copy of the
collection. That is a measured property of these outputs, not a design promise.

## Analyst steps (counted, not estimated)

| Size | Operator commands per run | Link errors | Statement errors | Document errors | UNKNOWN coverage cells | Items returned to a human |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| small | 2 | 2 | 2 | 1 | 1 | 6 |
| medium | 2 | 2 | 2 | 1 | 1 | 6 |
| large | 2 | 2 | 2 | 1 | 1 | 6 |

Operator command count is fixed by the tool and does not grow with the
collection. The number of items handed back to a human does. **Minutes per item
is UNKNOWN** -- this benchmark measures the tool, not the analyst, and does not
convert a count into an hours figure.

## Output correctness

| Size | baseline canonical result == optimized canonical result |
| --- | --- |
| small | True |
| medium | True |
| large | True |

Compared on the full result: every link error, every statement error, every
document error, the whole coverage matrix including its UNKNOWN cells, and the
follow-up count. The harness aborts instead of publishing if these ever differ.

## What is measured and what is not

- **Measured:** the elapsed times, peak Python allocations, workload sizes, export
  byte counts, error counts and growth ratios in this file. All from this run.
- **Warm page cache:** counted repeats run after a warmup, so the timings compare
  algorithms, not cold disk. A first-touch cold run was not measured.
- **Not measured, stays UNKNOWN:** the University's real collection size, its real
  document sizes, wall-clock time on University hardware, and analyst minutes per
  follow-up item. None of those are estimated here and none are derived from the
  curve above.
- **Not claimed:** no certification, no compliance conclusion, no peer percentile,
  and nothing about any individual's performance.

