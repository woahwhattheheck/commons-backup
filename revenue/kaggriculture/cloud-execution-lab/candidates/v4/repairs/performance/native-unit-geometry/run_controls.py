# SPDX-License-Identifier: Apache-2.0
"""Use the existing process-isolated evaluator; no alternative game driver."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys
import tarfile
import tempfile
import time
from check_geometry import blob, load, module
from compose_geometry import compose

ARCHIVE = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"
WRAPPER = '''import json
from pathlib import Path
import main

def agent(observation, configuration=None):
    returned = main.agent(observation, configuration)
    instance = main._INSTANCE
    if instance is None or instance.diagnostics.get("status") != "completed":
        raise RuntimeError("Native call did not complete: " + repr(None if instance is None else instance.diagnostics))
    if int(observation["step"]) == int(configuration.get("episodeSteps", 720))-2:
        import mechanics
        cache = getattr(mechanics, "_cached_shed_access", None)
        evidence = {"cache": None if cache is None else cache.cache_info()._asdict(),
                    "status": instance.diagnostics["status"]}
        Path(__file__).with_name("_native_evidence.json").write_text(json.dumps(evidence))
    return returned
'''


def benchmark(source):
    old, new = module("bench_old", source), module("bench_new", compose(source))
    result = {}
    for kind in ("membership", "unit_roundtrip"):
        samples = {"parent": [], "candidate": []}
        count = 100000 if kind == "membership" else 25000
        for round_number in range(9):
            for name, m in (("parent", old), ("candidate", new))[::1 if round_number % 2 == 0 else -1]:
                farm = {"farmer": [4, 4], "hands": [], "tiles": [["EMPTY"]*10 for _ in range(10)]}
                private = {"shed": {"WHEAT": 1}, "inventories": [{}]}
                started = time.perf_counter()
                if kind == "membership":
                    for i in range(count): m._is_shed_adjacent([4+i%2, 4], 10)
                else:
                    for i in range(count):
                        m._apply_unit_action(farm, private, 0, ["PICKUP", "WHEAT", 1], 10, 1, 24)
                        m._apply_unit_action(farm, private, 0, ["PLACE", "WHEAT", 1], 10, 1, 24)
                samples[name].append(time.perf_counter()-started)
                if kind == "unit_roundtrip" and (private["shed"].get("WHEAT") != 1 or private["inventories"] != [{}]):
                    raise RuntimeError("Benchmark ceased to be a conserved roundtrip")
        med = {k: statistics.median(v) for k, v in samples.items()}
        result[kind] = {"iterations": count, "samples_seconds": samples, "median_seconds": med,
                        "candidate_ratio": med["candidate"]/med["parent"]}
    return result


def main():
    p = argparse.ArgumentParser(); p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--skip-games", action="store_true")
    args = p.parse_args()
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != ARCHIVE:
        raise ValueError("Archive identity mismatch; revalidate rather than reuse this receipt")
    report = {"archive_sha256": ARCHIVE, "python": sys.version, "games": []}
    with tempfile.TemporaryDirectory(prefix="titan-spatial-cost-") as temp:
        parent, candidate = Path(temp)/"parent", Path(temp)/"candidate"
        with tarfile.open(args.archive) as archive:
            members = archive.getmembers()
            if any(not m.isfile() or Path(m.name).is_absolute() or ".." in Path(m.name).parts for m in members):
                raise ValueError("Unexpected archive member")
            archive.extractall(parent, filter="data")
        source = (parent/"mechanics.py").read_text()
        report["archive_members"] = len(members)
        report["member_sha256"] = {str(f.relative_to(parent)): hashlib.sha256(f.read_bytes()).hexdigest()
                                  for f in sorted(parent.rglob("*")) if f.is_file()}
        shutil.copytree(parent, candidate)
        (candidate/"mechanics.py").write_text(compose(source))
        changed = [str(f.relative_to(parent)) for f in parent.rglob("*")
                   if f.is_file() and f.read_bytes() != (candidate/f.relative_to(parent)).read_bytes()]
        if changed != ["mechanics.py"]: raise RuntimeError("Unexpected staged package changes")
        report["changed_members"] = changed
        report["candidate_mechanics_blob"] = blob((candidate/"mechanics.py").read_bytes())
        report["microbenchmark"] = benchmark(source)
        evpath = parent/"checks/reference/evaluator/evaluate.py"
        loader = parent/"checks/reference/evaluator/loader.py"
        cache = parent/"checks/reference/engine"
        ev = load(evpath, "spatial_existing_evaluator")
        engine, hashes = ev.get_engine(cache, loader)
        report["engine_sha256"] = hashes
        report["evaluator_sha256"] = hashlib.sha256(evpath.read_bytes()).hexdigest()
        for root in (parent, candidate): (root/"_geometry_observer.py").write_text(WRAPPER)
        if not args.skip_games:
            for seed in (2027, 6607):
                for seat in (0, 1):
                    cell = {"seed": seed, "seat": seat, "arms": {}}
                    for name, root in (("parent", parent), ("candidate", candidate))[::1 if seat==0 else -1]:
                        specs = [str(root/"_geometry_observer.py"), "official_starter"]
                        if seat: specs.reverse()
                        outcome = ev.play(engine, specs, cache, loader, seed, seat)
                        if outcome["status"] != "complete":
                            raise RuntimeError(json.dumps(outcome))
                        outcome["native_evidence"] = json.loads((root/"_native_evidence.json").read_text())
                        cell["arms"][name] = outcome
                    a, b = cell["arms"]["parent"], cell["arms"]["candidate"]
                    cell["identical"] = a["trace_sha256"] == b["trace_sha256"] and a["scores"] == b["scores"]
                    if not cell["identical"]: raise RuntimeError("Native action/cash/final-state divergence")
                    report["games"].append(cell)
                    print(json.dumps({"seed":seed,"seat":seat,"identical":cell["identical"],
                        "cache":b["native_evidence"]["cache"],"scores":b["scores"]}), flush=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"microbenchmark":report["microbenchmark"], "paired_games":len(report["games"])}))


if __name__ == "__main__": main()
