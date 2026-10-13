# SPDX-License-Identifier: Apache-2.0
"""Bounded optimizer allocation/lifetime benchmark, not game-strength evidence."""
from __future__ import annotations
import argparse
import gc
import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
import types
import weakref
from repair_cache_lifetime import transform, git_blob


def module(source, runtime):
    result = types.ModuleType("cachelife_benchmark")
    result.__file__ = str(runtime / "selected_sell_core.py")
    exec(compile(source, result.__file__, "exec"), result.__dict__)
    return result


def inputs():
    return dict(item="WHEAT", quantity=24, inventory=9800, params=None,
                shops=["BAKERY"], config={}, now=400, dates=[400, 404, 408],
                reference=((400, 24),), rival_quantity=12)


def memory_probe(source, runtime, calls, automatic_gc):
    mod = module(source, runtime)
    original = mod.MarketPath
    refs = []
    class Tracked(original):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            refs.append(weakref.ref(self))
    mod.MarketPath = Tracked
    enabled = gc.isenabled()
    gc.collect()
    (gc.enable if automatic_gc else gc.disable)()
    tracemalloc.start()
    try:
        for _ in range(calls):
            mod.optimize_lot(**inputs())
        current, peak = tracemalloc.get_traced_memory()
        retained = sum(ref() is not None for ref in refs)
    finally:
        tracemalloc.stop()
        (gc.enable if enabled else gc.disable)()
        gc.collect()
    return dict(calls=calls, automatic_gc=automatic_gc, retained_models=retained,
                traced_current_bytes=current, traced_peak_bytes=peak)


def timing_batch(mod, calls, automatic_gc):
    enabled = gc.isenabled()
    gc.collect()
    (gc.enable if automatic_gc else gc.disable)()
    before = [s["collections"] for s in gc.get_stats()]
    durations = []
    try:
        for _ in range(calls):
            start = time.perf_counter_ns()
            mod.optimize_lot(**inputs())
            durations.append((time.perf_counter_ns() - start) / 1e6)
        collections = [s["collections"] - b for s, b in zip(gc.get_stats(), before)]
    finally:
        (gc.enable if enabled else gc.disable)()
        gc.collect()
    return dict(milliseconds=durations, collections=collections)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--calls", type=int, default=32)
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    if not (1 <= args.calls <= 128 and 1 <= args.rounds <= 9):
        parser.error("use 1..128 calls and 1..9 rounds")
    runtime = args.runtime.resolve()
    sys.path.insert(0, str(runtime))
    source = (runtime / "selected_sell_core.py").read_text()
    sources = {"baseline": source, "candidate": transform(source)}
    modules = {name: module(text, runtime) for name, text in sources.items()}
    memory = {str(enabled): {name: memory_probe(text, runtime, args.calls, enabled)
                             for name, text in sources.items()}
              for enabled in (True, False)}
    timings = {}
    for enabled in (True, False):
        raw = {"baseline": [], "candidate": []}
        collections = {"baseline": [0, 0, 0], "candidate": [0, 0, 0]}
        batches = {"baseline": [], "candidate": []}
        for repeat in range(args.rounds):
            names = ["baseline", "candidate"] if repeat % 2 == 0 else ["candidate", "baseline"]
            for name in names:
                result = timing_batch(modules[name], args.calls, enabled)
                raw[name].extend(result["milliseconds"])
                batches[name].append(sum(result["milliseconds"]))
                collections[name] = [a + b for a, b in zip(collections[name], result["collections"])]
        summary = {}
        for name, values in raw.items():
            ordered = sorted(values)
            summary[name] = dict(calls=len(values), median_ms=statistics.median(values),
                                 p95_ms=ordered[int(0.95 * (len(ordered) - 1))], max_ms=max(values),
                                 batch_totals_ms=batches[name], collections=collections[name])
        summary["candidate_over_baseline_median"] = summary["candidate"]["median_ms"] / summary["baseline"]["median_ms"]
        timings[str(enabled)] = summary
    receipt = dict(schema="titan-v4-cache-lifetime-benchmark/v1", python=sys.version,
                   source_git=git_blob(source.encode()), candidate_git=git_blob(sources["candidate"].encode()),
                   workload=inputs(), memory=memory, timings=timings,
                   notes=["Memory phase uses tracemalloc; timing phase does not.",
                          "Arms alternate order each round; forced collection is outside measured calls.",
                          "GC-off phase is a retention diagnostic, not the production configuration.",
                          "No full-game, deadline-tail, Python 3.11, or leaderboard claim."],
                   strength_claim=False, package_promotion=False)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
