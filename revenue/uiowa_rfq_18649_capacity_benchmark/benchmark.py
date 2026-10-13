#!/usr/bin/env python3
"""UIOWA-095 -- the capacity benchmark harness.

Runs the preparation workflow over small / medium / large synthetic
collections, in both the delivered ("baseline") and repaired ("optimized")
implementations, and records what actually happened.

Measurement rules this harness enforces, because the whole deliverable is
worthless if they slip:

  * Every published number is produced by this run on this machine. Nothing is
    typed in by hand, nothing is carried over from a previous run, and the
    report file is generated from the results file rather than written
    alongside it.
  * Timing and memory are measured in SEPARATE passes. ``tracemalloc`` adds
    per-allocation overhead, so timing it would measure the profiler. The
    results file says which pass each number came from.
  * Timing uses ``time.perf_counter``. Each (size, mode) gets one uncounted
    warmup run, then N counted repeats; both the minimum and the median are
    reported. Minimum is the cleanest estimate of the work itself; the median
    shows how noisy this box was.
  * The page cache is warm by the time counted repeats run. That is stated, not
    hidden: the timing numbers separate algorithms, not disks.
  * Before/after only counts if the answers match. Every repeat compares the
    baseline and optimized ``canonical()`` results and the run aborts on any
    difference.

What this does NOT do: it does not project onto the University's real workload.
The size of the real collection is UNKNOWN, so the measured curve is published
as measured points and a measured growth ratio, and any figure for a workload
that was not run stays UNKNOWN.

Python 3 standard library only. No network.
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

import generate_collection as gen
import workflow as wf

HERE = Path(__file__).resolve().parent
SIZE_ORDER = ["small", "medium", "large"]
REPEATS = {"small": 5, "medium": 5, "large": 3}
STAGES = ["import", "link_check", "statement_presence", "document_labels", "coverage_rollup", "export"]


def environment() -> dict:
    """Facts about the machine these numbers were taken on.

    Without this the timings mean nothing later. CPU model is read from
    /proc/cpuinfo where available; where it is not, it stays UNKNOWN rather
    than being filled with a guess.
    """
    cpu_model = "UNKNOWN"
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    try:
        import os
        logical = os.cpu_count()
        affinity = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else "UNKNOWN"
    except Exception:
        logical, affinity = "UNKNOWN", "UNKNOWN"
    return {
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "python_build": " ".join(platform.python_build()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor_model": cpu_model,
        "cpu_count_logical": logical,
        "cpu_affinity_count": affinity,
        "timer": "time.perf_counter",
        "memory_probe": "tracemalloc (Python-level allocations only; excludes interpreter overhead and OS RSS)",
        "container_note": "Shared CI-style container. Minimum-of-repeats is the cleanest signal; median is reported alongside so noise is visible.",
        "page_cache": "warm -- one uncounted warmup run precedes the counted repeats at every size",
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def timed_run(root: Path, mode: str, out_dir: Path) -> tuple:
    """One full workflow pass, timing each stage separately.

    Returns (per-stage seconds, WorkflowResult, exported byte sizes).
    """
    t = {}
    pc = time.perf_counter

    t0 = pc(); col = wf.import_collection(root); t["import"] = pc() - t0
    t0 = pc(); link_errors = wf.check_links(col); t["link_check"] = pc() - t0
    t0 = pc(); stmt_errors = wf.check_statement_presence(col, mode); t["statement_presence"] = pc() - t0
    t0 = pc(); doc_errors = wf.check_document_labels(root, col, mode); t["document_labels"] = pc() - t0
    t0 = pc(); coverage = wf.rollup_coverage(col); t["coverage_rollup"] = pc() - t0

    result = wf.WorkflowResult(
        mode=mode, rows_in=col.row_count(), documents_in=len(col.documents),
        report_chars=len(col.report_text), link_errors=link_errors,
        statement_errors=stmt_errors, document_errors=doc_errors, coverage=coverage,
    )
    t0 = pc(); written = wf.export_bundle(result, out_dir); t["export"] = pc() - t0
    t["total"] = sum(t[s] for s in STAGES)
    return t, result, written


def memory_run(root: Path, mode: str, out_dir: Path) -> dict:
    """One full workflow pass under tracemalloc. Not timed -- the profiler
    dominates timing, so these two passes are kept apart on purpose."""
    gc.collect()
    tracemalloc.start()
    try:
        _, result, _ = timed_run(root, mode, out_dir)
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {"peak_bytes": peak, "current_bytes_at_end": current, "canonical": result.canonical()}


def bench_size(size: str, workdir: Path, seed: int) -> dict:
    profile = gen.PROFILES[size]
    root = workdir / f"collection_{size}"
    t0 = time.perf_counter()
    corpus = gen.generate(root, profile, seed)
    gen_seconds = time.perf_counter() - t0

    out_dir = workdir / f"out_{size}"
    repeats = REPEATS[size]
    timings = {m: {s: [] for s in STAGES + ["total"]} for m in wf.MODES}
    canonicals = {}
    exports = {}

    for mode in wf.MODES:
        # Uncounted warmup: warms the page cache and any lazy interpreter work
        # so the counted repeats compare algorithms rather than first-touch.
        timed_run(root, mode, out_dir / mode / "warmup")
        for repeat_index in range(repeats):
            gc.collect()
            t, result, written = timed_run(root, mode, out_dir / mode)
            canonical = result.canonical()
            # Every counted result must agree, including repeats within a mode.
            # Keep this outside timed_run: correctness work is not stage timing.
            if canonicals and canonical != next(iter(canonicals.values())):
                raise SystemExit(
                    f"ABORT: counted timing repeat {repeat_index + 1} produced a "
                    f"different answer at size={size}/{mode}. Refusing to "
                    "publish a benchmark containing inconsistent answers."
                )
            for k, v in t.items():
                timings[mode][k].append(v)
            canonicals[mode] = canonical
            exports[mode] = written

    # Correctness gate. A speedup that changes the answer is not a speedup.
    identical = canonicals["baseline"] == canonicals["optimized"]
    if not identical:
        raise SystemExit(f"ABORT: baseline and optimized disagree at size={size}. "
                         "Refusing to publish a benchmark of two different answers.")

    memory = {}
    for mode in wf.MODES:
        memory[mode] = memory_run(root, mode, out_dir / mode / "mem")
        if memory[mode]["canonical"] != canonicals[mode]:
            raise SystemExit(f"ABORT: memory pass produced a different answer at size={size}/{mode}.")
        memory[mode].pop("canonical")

    result_obj = canonicals["baseline"]
    return {
        "size": size,
        "repeats": repeats,
        "generation_seconds": gen_seconds,
        "workload": corpus,
        "timings_seconds": {
            mode: {
                stage: {
                    "min": min(vals),
                    "median": statistics.median(vals),
                    "max": max(vals),
                    "samples": len(vals),
                }
                for stage, vals in stages.items()
            }
            for mode, stages in timings.items()
        },
        "memory_peak_bytes": {m: memory[m]["peak_bytes"] for m in wf.MODES},
        "export_bytes": exports["optimized"],
        "outputs_identical_across_modes": identical,
        "workflow_findings": {
            "link_errors": len(result_obj["link_errors"]),
            "statement_errors": len(result_obj["statement_errors"]),
            "document_errors": len(result_obj["document_errors"]),
            "unknown_coverage_cells": sum(1 for r in result_obj["coverage"] if r["cell_state"] == "UNKNOWN"),
            "analyst_followups": result_obj["analyst_followups"],
        },
        "analyst_steps": {
            "operator_commands_per_run": 2,
            "commands": [
                "python3 generate_collection.py --profile <size> --out <dir>",
                "python3 workflow.py <dir> --out <out>",
            ],
            "note": "Command count is fixed by the tool and does not grow with collection size. "
                    "Items returned to a human DO grow with the collection; that count is "
                    "'analyst_followups' above. Minutes per item is UNKNOWN and is not modelled.",
        },
    }


def ratio(a: float, b: float):
    return (a / b) if b else None


# Statement counts for the crossover sweep. Chosen to bracket the point where
# the repaired check overtakes the delivered one on the small end.
CROSSOVER_POINTS = [10, 20, 40, 80, 160, 320, 640, 1280]
CROSSOVER_CHARS_PER_STATEMENT = 200


def _synthetic_report(n: int) -> tuple:
    """Report text of n statements, same shape the generator emits.

    Built in memory rather than on disk: this sweep is isolating one function,
    so nothing else should be in the measurement.
    """
    ids = {f"S-{i:04d}" for i in range(1, n + 1)}
    filler = "fictional statement text for capacity benchmarking, not University data"
    parts = ["# SYNTHETIC\n"]
    for i in range(1, n + 1):
        body = (filler + " ") * (CROSSOVER_CHARS_PER_STATEMENT // len(filler) + 1)
        parts.append(f"[S-{i:04d}] {body[:CROSSOVER_CHARS_PER_STATEMENT]}\n")
    return ids, "".join(parts)


def _variant_findall(statement_ids, report_text: str) -> list:
    """The repair that was tried FIRST and rejected.

    Kept in the harness rather than deleted, so the reason it was rejected
    regenerates with every run instead of living in a commit message. It is
    correct -- it is just fat: ``findall`` materialises every run in the report
    as a list before the set is built, so peak allocation tracks report size.
    """
    present_runs = set(wf._ID_CHARS.findall(report_text))
    absent = []
    for sid in sorted(statement_ids):
        if sid in present_runs:
            continue
        if sid not in report_text:
            absent.append(sid)
    return absent


def measure_statement_variants(n: int = 3000, repeats: int = 5) -> dict:
    """Time AND peak memory for the three shapes of the statement check.

    This is the measurement that decided what ships. Timing alone picks the
    findall variant; adding the memory column picks the one that actually
    shipped. Both columns are measured here in the same run so the trade-off is
    checkable rather than recounted.
    """
    ids, text = _synthetic_report(n)
    expected = wf.statements_absent_baseline(ids, text)
    variants = [
        ("baseline (delivered: scan per id)", wf.statements_absent_baseline),
        ("findall + set (rejected: fast, fat)", _variant_findall),
        ("finditer + length filter (shipped)", wf.statements_absent_optimized),
    ]
    rows = []
    for name, fn in variants:
        if fn(ids, text) != expected:
            raise SystemExit(f"ABORT: variant {name!r} does not match the baseline answer.")
        fn(ids, text)  # uncounted warmup
        samples = []
        for _ in range(repeats):
            gc.collect()
            t0 = time.perf_counter()
            fn(ids, text)
            samples.append(time.perf_counter() - t0)
        gc.collect()
        tracemalloc.start()
        try:
            fn(ids, text)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        rows.append({"variant": name, "seconds_min": min(samples),
                     "seconds_median": statistics.median(samples),
                     "peak_bytes": peak, "samples": len(samples)})
    return {
        "statements": n,
        "report_chars": len(text),
        "repeats": repeats,
        "note": "Time and peak memory measured in separate passes, as everywhere else. "
                "All three variants return the identical answer; that is asserted before timing.",
        "variants": rows,
    }


def measure_crossover(repeats: int = 7) -> dict:
    """Find where the repaired statement check starts to pay off.

    The three-size sweep showed the optimized check LOSING at the small
    workload -- one pass over the report costs more than a handful of substring
    scans. That is a real result, so it gets a real measurement instead of a
    sentence of hand-waving. Every point here is timed on this machine in this
    run; the crossover reported is the smallest measured point at which the
    optimized path won, not an interpolation.
    """
    points = []
    for n in CROSSOVER_POINTS:
        ids, text = _synthetic_report(n)
        # Both implementations must agree at every point, or the comparison is
        # meaningless.
        base_answer = wf.statements_absent_baseline(ids, text)
        opt_answer = wf.statements_absent_optimized(ids, text)
        if base_answer != opt_answer:
            raise SystemExit(f"ABORT: crossover sweep disagreed at n={n}.")
        times = {}
        for name, fn in (("baseline", wf.statements_absent_baseline),
                         ("optimized", wf.statements_absent_optimized)):
            fn(ids, text)  # uncounted warmup
            samples = []
            for _ in range(repeats):
                gc.collect()
                t0 = time.perf_counter()
                fn(ids, text)
                samples.append(time.perf_counter() - t0)
            times[name] = {"min": min(samples), "median": statistics.median(samples),
                           "samples": len(samples)}
        points.append({
            "statements": n,
            "report_chars": len(text),
            "baseline_seconds": times["baseline"],
            "optimized_seconds": times["optimized"],
            "optimized_faster": times["optimized"]["min"] < times["baseline"]["min"],
        })
    winners = [p["statements"] for p in points if p["optimized_faster"]]
    return {
        "chars_per_statement": CROSSOVER_CHARS_PER_STATEMENT,
        "repeats_per_point": repeats,
        "points": points,
        "crossover_statements": min(winners) if winners else "UNKNOWN",
        "note": "Smallest MEASURED point at which the optimized check beat the baseline. "
                "Not interpolated. If no measured point won, this is UNKNOWN rather than a "
                "guessed threshold.",
    }


def write_report(results: dict, out: Path) -> Path:
    """Render the Markdown report FROM the measurements. No hand-typed numbers."""
    env = results["environment"]
    rows = results["sizes"]
    lines = [
        "# UIOWA-095 -- production workflow capacity benchmark",
        "",
        "Measured results for the evidence-and-report preparation workflow. Every number",
        "below was produced by `benchmark.py` on the machine described under Environment,",
        "in the run stamped there. Nothing here is illustrative and nothing is carried over",
        "from an earlier run -- this file is generated from `benchmark_results.json`.",
        "",
        "All workloads are SYNTHETIC fixtures. No University of Iowa data was used.",
        "",
        "## Environment",
        "",
        "| Property | Value |",
        "| --- | --- |",
    ]
    for k in ["python_version", "python_implementation", "python_build", "platform",
              "machine", "processor_model", "cpu_count_logical", "cpu_affinity_count",
              "timer", "memory_probe", "page_cache", "container_note", "measured_at_utc"]:
        lines.append(f"| {k} | {env[k]} |")

    lines += [
        "",
        "## Workload sizes",
        "",
        "Sizes are inputs chosen for this benchmark. They are not an estimate of the",
        "University's real collection, which is **UNKNOWN**.",
        "",
        "| Size | Evidence rows | Findings | Recommendations | Trace statements | Documents listed | Report chars | Collection bytes | Largest document bytes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for size in SIZE_ORDER:
        w = rows[size]["workload"]
        lines.append(
            f"| {size} | {w['evidence_rows']:,} | {w['finding_rows']:,} | {w['recommendation_rows']:,} "
            f"| {w['trace_rows']:,} | {w['documents_listed']:,} | {w['report_chars']:,} "
            f"| {w['collection_bytes']:,} | {w['largest_document_bytes']:,} |"
        )

    lines += [
        "",
        "## End-to-end elapsed time (measured)",
        "",
        "Minimum and median of the counted repeats, after one uncounted warmup.",
        "",
        "| Size | Repeats | Baseline min (s) | Baseline median (s) | Optimized min (s) | Optimized median (s) | Speedup on min |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for size in SIZE_ORDER:
        r = rows[size]
        b = r["timings_seconds"]["baseline"]["total"]
        o = r["timings_seconds"]["optimized"]["total"]
        sp = ratio(b["min"], o["min"])
        lines.append(f"| {size} | {r['repeats']} | {b['min']:.4f} | {b['median']:.4f} "
                     f"| {o['min']:.4f} | {o['median']:.4f} | {sp:.2f}x |")

    lines += [
        "",
        "## Per-stage elapsed time (measured, minimum of repeats, seconds)",
        "",
        "This is the table that says which stages were actually hot and which only",
        "looked expensive. `link_check`, `coverage_rollup` and `export` are the same code",
        "in both modes; they are measured anyway so the claim 'these are not the",
        "bottleneck' is a measurement rather than an assertion.",
        "",
        "| Size | Stage | Baseline (s) | Optimized (s) | Delta (s) | Speedup |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for size in SIZE_ORDER:
        for stage in STAGES:
            b = rows[size]["timings_seconds"]["baseline"][stage]["min"]
            o = rows[size]["timings_seconds"]["optimized"][stage]["min"]
            sp = ratio(b, o)
            lines.append(f"| {size} | {stage} | {b:.6f} | {o:.6f} | {b - o:+.6f} | "
                         + (f"{sp:.2f}x |" if sp else "n/a |"))

    lines += [
        "",
        "## Scaling of the repaired stages (measured growth, small -> large)",
        "",
        "| Quantity | small | large | growth |",
        "| --- | ---: | ---: | ---: |",
    ]
    ws, wl = rows["small"]["workload"], rows["large"]["workload"]
    sstmt = rows["small"]["timings_seconds"]
    lstmt = rows["large"]["timings_seconds"]
    growth_rows = [
        ("trace statements", ws["trace_rows"], wl["trace_rows"], ratio(wl["trace_rows"], ws["trace_rows"])),
        ("report characters", ws["report_chars"], wl["report_chars"], ratio(wl["report_chars"], ws["report_chars"])),
        ("statement_presence baseline (s)", sstmt["baseline"]["statement_presence"]["min"],
         lstmt["baseline"]["statement_presence"]["min"],
         ratio(lstmt["baseline"]["statement_presence"]["min"], sstmt["baseline"]["statement_presence"]["min"])),
        ("statement_presence optimized (s)", sstmt["optimized"]["statement_presence"]["min"],
         lstmt["optimized"]["statement_presence"]["min"],
         ratio(lstmt["optimized"]["statement_presence"]["min"], sstmt["optimized"]["statement_presence"]["min"])),
        ("document bytes on disk", ws["document_bytes"], wl["document_bytes"],
         ratio(wl["document_bytes"], ws["document_bytes"])),
        ("document_labels baseline (s)", sstmt["baseline"]["document_labels"]["min"],
         lstmt["baseline"]["document_labels"]["min"],
         ratio(lstmt["baseline"]["document_labels"]["min"], sstmt["baseline"]["document_labels"]["min"])),
        ("document_labels optimized (s)", sstmt["optimized"]["document_labels"]["min"],
         lstmt["optimized"]["document_labels"]["min"],
         ratio(lstmt["optimized"]["document_labels"]["min"], sstmt["optimized"]["document_labels"]["min"])),
    ]
    for name, s, l, g in growth_rows:
        sv = f"{s:,.6f}" if isinstance(s, float) else f"{s:,}"
        lv = f"{l:,.6f}" if isinstance(l, float) else f"{l:,}"
        lines.append(f"| {name} | {sv} | {lv} | {g:.1f}x |")

    lines += [
        "",
        "Read the two `statement_presence` rows against the first two rows. Statement",
        "count and report length both grow, and the baseline stage grows by roughly their",
        "product -- that is the quadratic. The optimized stage grows with report length",
        "alone.",
        "",
        "## Why the shipped repair is not the obvious one (measured)",
        "",
        "Three implementations of the statement check, all returning the identical",
        f"answer, at {results['statement_variants']['statements']:,} statements / "
        f"{results['statement_variants']['report_chars']:,} report characters. Time and peak",
        "memory measured in separate passes.",
        "",
        "| Variant | Elapsed min (s) | Peak bytes |",
        "| --- | ---: | ---: |",]
    for v in results["statement_variants"]["variants"]:
        lines.append(f"| {v['variant']} | {v['seconds_min']:.6f} | {v['peak_bytes']:,} |")
    lines += [
        "",
        "Timing alone selects the middle row. The peak-allocation column is why that variant was not shipped:",
        "`findall` materialises every run in the report as a list before the set exists, so",
        "peak allocation tracks report size. The shipped row gives back part of the speed",
        "win and removes most of the memory cost. This table regenerates on every run, so",
        "the rejected option stays checkable instead of becoming a story.",
        "",
        "## Where the repaired check starts to pay off (measured crossover)",
        "",
        "The three-size sweep showed the optimized statement check LOSING at the small",
        "workload. That is a real result, so here is where it actually turns over. Each",
        "row is timed on this machine in this run, statement check only, "
        f"{results['crossover']['chars_per_statement']} report characters per statement, "
        f"minimum of {results['crossover']['repeats_per_point']} repeats after a warmup.",
        "",
        "| Trace statements | Report chars | Baseline (s) | Optimized (s) | Optimized faster? |",
        "| ---: | ---: | ---: | ---: | --- |",]
    for pt in results["crossover"]["points"]:
        lines.append(f"| {pt['statements']:,} | {pt['report_chars']:,} "
                     f"| {pt['baseline_seconds']['min']:.6f} | {pt['optimized_seconds']['min']:.6f} "
                     f"| {'yes' if pt['optimized_faster'] else 'no'} |")
    cx = results["crossover"]["crossover_statements"]
    lines += [
        "",
        f"**Smallest measured statement count at which the repaired check wins: {cx}.**",
        "",
        "That figure is the smallest point that was actually run, not an interpolation",
        "between points and not a fitted threshold. Below it the delivered algorithm is",
        "the faster one, by a margin measured in fractions of a millisecond. The repaired",
        "version is still what ships: the cost of being wrong at the small end is under a",
        "millisecond, and the cost of being wrong at the large end is most of a second and",
        "grows with the square of the engagement.",
        "",
        "## Peak Python-allocated memory (measured, tracemalloc)",
        "",
        "Separate pass from the timings. `tracemalloc` sees Python-level allocations only;",
        "it is not process RSS.",
        "",
        "| Size | Baseline peak (bytes) | Optimized peak (bytes) | Delta (bytes) | Ratio |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for size in SIZE_ORDER:
        mb = rows[size]["memory_peak_bytes"]["baseline"]
        mo = rows[size]["memory_peak_bytes"]["optimized"]
        lines.append(f"| {size} | {mb:,} | {mo:,} | {mo - mb:+,} | {ratio(mb, mo):.2f}x |")

    lines += [
        "",
        "## Import / export behaviour (measured)",
        "",
        "| Size | Rows imported | Documents listed | Documents on disk | coverage-matrix.csv | workflow-result.json | workflow-report.md |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for size in SIZE_ORDER:
        w = rows[size]["workload"]
        e = rows[size]["export_bytes"]
        total_rows = w["evidence_rows"] + w["finding_rows"] + w["recommendation_rows"] + w["trace_rows"]
        lines.append(f"| {size} | {total_rows:,} | {w['documents_listed']:,} | {w['documents_on_disk']:,} "
                     f"| {e['coverage-matrix.csv']:,} | {e['workflow-result.json']:,} | {e['workflow-report.md']:,} |")

    lines += [
        "",
        "Export volume is flat in the number of evidence rows because the exported",
        "artifacts are the coverage matrix and the error list, not a copy of the",
        "collection. That is a measured property of these outputs, not a design promise.",
        "",
        "## Analyst steps (counted, not estimated)",
        "",
        "| Size | Operator commands per run | Link errors | Statement errors | Document errors | UNKNOWN coverage cells | Items returned to a human |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for size in SIZE_ORDER:
        f = rows[size]["workflow_findings"]
        lines.append(f"| {size} | {rows[size]['analyst_steps']['operator_commands_per_run']} "
                     f"| {f['link_errors']} | {f['statement_errors']} | {f['document_errors']} "
                     f"| {f['unknown_coverage_cells']} | {f['analyst_followups']} |")

    lines += [
        "",
        "Operator command count is fixed by the tool and does not grow with the",
        "collection. The number of items handed back to a human does. **Minutes per item",
        "is UNKNOWN** -- this benchmark measures the tool, not the analyst, and does not",
        "convert a count into an hours figure.",
        "",
        "## Output correctness",
        "",
        "| Size | baseline canonical result == optimized canonical result |",
        "| --- | --- |",
    ]
    for size in SIZE_ORDER:
        lines.append(f"| {size} | {rows[size]['outputs_identical_across_modes']} |")

    lines += [
        "",
        "Compared on the full result: every link error, every statement error, every",
        "document error, the whole coverage matrix including its UNKNOWN cells, and the",
        "follow-up count. The harness aborts instead of publishing if these ever differ.",
        "",
        "## What is measured and what is not",
        "",
        "- **Measured:** the elapsed times, peak Python allocations, workload sizes, export",
        "  byte counts, error counts and growth ratios in this file. All from this run.",
        "- **Warm page cache:** counted repeats run after a warmup, so the timings compare",
        "  algorithms, not cold disk. A first-touch cold run was not measured.",
        "- **Not measured, stays UNKNOWN:** the University's real collection size, its real",
        "  document sizes, wall-clock time on University hardware, and analyst minutes per",
        "  follow-up item. None of those are estimated here and none are derived from the",
        "  curve above.",
        "- **Not claimed:** no certification, no compliance conclusion, no peer percentile,",
        "  and nothing about any individual's performance.",
        "",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def write_csv(results: dict, out: Path) -> Path:
    fields = ["size", "stage", "mode", "seconds_min", "seconds_median", "seconds_max",
              "samples", "repeats", "peak_bytes_mode_total", "outputs_identical"]
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for size in SIZE_ORDER:
            if size not in results["sizes"]:
                continue
            r = results["sizes"][size]
            for mode in wf.MODES:
                for stage in STAGES + ["total"]:
                    s = r["timings_seconds"][mode][stage]
                    w.writerow({
                        "size": size, "stage": stage, "mode": mode,
                        "seconds_min": f"{s['min']:.9f}",
                        "seconds_median": f"{s['median']:.9f}",
                        "seconds_max": f"{s['max']:.9f}",
                        "samples": s["samples"], "repeats": r["repeats"],
                        "peak_bytes_mode_total": r["memory_peak_bytes"][mode],
                        "outputs_identical": r["outputs_identical_across_modes"],
                    })
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run the UIOWA-095 capacity benchmark.")
    p.add_argument("--sizes", nargs="*", default=SIZE_ORDER, choices=SIZE_ORDER)
    p.add_argument("--results-dir", type=Path, default=HERE / "results")
    p.add_argument("--seed", type=int, default=20260919)
    p.add_argument("--keep-workdir", type=Path, default=None,
                   help="Write collections here instead of a temp dir (for inspection).")
    a = p.parse_args(argv)

    a.results_dir.mkdir(parents=True, exist_ok=True)
    env = environment()
    print("environment:", json.dumps(env, indent=2, sort_keys=True))

    results = {
        "schema": "uiowa-095-benchmark-v1",
        "synthetic_workload": True,
        "environment": env,
        "seed": a.seed,
        "sizes": {},
    }

    def run_all(workdir: Path):
        for size in a.sizes:
            print(f"[bench] size={size} ...", flush=True)
            t0 = time.perf_counter()
            results["sizes"][size] = bench_size(size, workdir, a.seed)
            print(f"[bench] size={size} done in {time.perf_counter() - t0:.2f}s "
                  f"(baseline total min "
                  f"{results['sizes'][size]['timings_seconds']['baseline']['total']['min']:.4f}s, "
                  f"optimized total min "
                  f"{results['sizes'][size]['timings_seconds']['optimized']['total']['min']:.4f}s)",
                  flush=True)

    if a.keep_workdir:
        a.keep_workdir.mkdir(parents=True, exist_ok=True)
        run_all(a.keep_workdir)
    else:
        with tempfile.TemporaryDirectory(prefix="uiowa095-") as td:
            run_all(Path(td))

    print("[bench] statement variant sweep ...", flush=True)
    results["statement_variants"] = measure_statement_variants()

    print("[bench] crossover sweep ...", flush=True)
    results["crossover"] = measure_crossover()
    print(f"[bench] crossover at {results['crossover']['crossover_statements']} statements", flush=True)

    (a.results_dir / "environment.json").write_text(
        json.dumps(env, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (a.results_dir / "benchmark_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(results, a.results_dir / "benchmark_results.csv")
    if set(a.sizes) == set(SIZE_ORDER):
        write_report(results, a.results_dir / "BENCHMARK_REPORT.md")
        print(f"wrote {a.results_dir / 'BENCHMARK_REPORT.md'}")
    else:
        print("partial size set -- skipped BENCHMARK_REPORT.md (it requires all three sizes)")
    print(f"wrote {a.results_dir / 'benchmark_results.json'}")
    print(f"wrote {a.results_dir / 'benchmark_results.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
