# SPDX-License-Identifier: Apache-2.0
"""Interleaved kernel timings weighted by executed native-game observations.

This is a local microbenchmark, not a whole-agent speed or deadline guarantee.
The exact sampled input histogram and every timing block are retained.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import sys
import time
import types
from compose_hire_cost import compose_source


def module(name, text):
    value = types.ModuleType(name)
    exec(compile(text, name, "exec"), value.__dict__)
    return value


def timed(fn, values, repeats):
    start = time.perf_counter_ns()
    checksum = 0
    for _ in range(repeats):
        for n in values:
            checksum += fn(n)
    return (time.perf_counter_ns() - start) / 1e9, checksum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--games", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blocks", type=int, default=21)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.blocks < 5 or args.repeats < 1:
        parser.error("at least five blocks and one repeat are required")
    histogram, reports = Counter(), []
    for path in sorted(args.games.glob("normal-*-baseline.json")):
        raw = path.read_bytes(); report = json.loads(raw)
        if report["status"] != {"completed": 719} or report["final_status"] != ["DONE", "DONE"]:
            raise ValueError("incomplete native input evidence")
        histogram.update({int(k): v for k, v in report["fib_argument_histogram"].items()})
        reports.append({"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
    if not histogram:
        raise ValueError("no executed native-game observations")
    values = [n for n, count in sorted(histogram.items()) for _ in range(count)]
    random.Random(9600911).shuffle(values)
    source = (args.runtime / "mechanics.py").read_text()
    base, candidate = module("baseline", source), module("candidate", compose_source(source))
    results = {}
    for name in ("_fib", "_hire_cost"):
        functions = {"baseline": getattr(base, name), "candidate": getattr(candidate, name)}
        warmups = [timed(fn, values, 1)[1] for fn in functions.values()]
        if warmups[0] != warmups[1]:
            raise ValueError("benchmark checksum mismatch")
        rows = []
        for block in range(args.blocks):
            order = ("baseline", "candidate") if block % 2 == 0 else ("candidate", "baseline")
            row = {"block": block, "order": order}
            for arm in order:
                elapsed, checksum = timed(functions[arm], values, args.repeats)
                if checksum != warmups[0] * args.repeats:
                    raise ValueError("timed checksum mismatch")
                row[arm + "_seconds"] = elapsed
            rows.append(row)
        bm = statistics.median(r["baseline_seconds"] for r in rows)
        cm = statistics.median(r["candidate_seconds"] for r in rows)
        results[name] = {"baseline_median_seconds": bm, "candidate_median_seconds": cm,
                         "ratio_of_medians": bm / cm,
                         "median_paired_speedup": statistics.median(r["baseline_seconds"] / r["candidate_seconds"] for r in rows),
                         "calls_per_block": len(values) * args.repeats,
                         "checksum": warmups[0] * args.repeats, "blocks": rows}
    table = candidate._TITAN_HIRE_FIB64
    report = {"schema": "titan.v4.hire-cost.benchmark.v1", "python": platform.python_version(),
              "optimized": bool(sys.flags.optimize), "histogram": dict(sorted(histogram.items())),
              "native_source_reports": reports, "observed_calls": len(values),
              "table_entries": len(table), "table_shallow_bytes": sys.getsizeof(table),
              "table_and_integer_object_sizes_bytes": sys.getsizeof(table) + sum(map(sys.getsizeof, table)),
              "memory_note": "Sum of Python object sizes; includes integers shared with interpreter constants. Not incremental process RSS.",
              "scope": "Local shuffled-histogram kernel microbenchmark; no whole-agent or strength inference.",
              "results": results}
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2); stream.write("\n")
    print(json.dumps({name: {k: v for k, v in result.items() if k != "blocks"}
                      for name, result in results.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
