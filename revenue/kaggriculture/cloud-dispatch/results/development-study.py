"""Run the predeclared harvest study using the existing isolated evaluator.

No network is used in run/validate. Prepare official engine files separately
with cloud-eval/evaluate.py --prepare-engine before starting the study.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import sys

import variants

HERE = Path(__file__).resolve().parent
KAG = HERE.parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def existing():
    return load(KAG / "cloud-market/study.py", "harvest_peer_study")


def prepare_sources(output):
    output = Path(output).resolve()
    peer = existing()
    snapshot = output / "sources"
    paths = variants.write_candidates(snapshot / "candidates")
    core = KAG / "20260907-offline-agent"
    if sha(core / "main.py") != "acf541d46ceb2002caf0a3bba834109a92b755fb36afa4bda9e3d966665550ac":
        raise ValueError("Euler28 changed; restore the documented frozen source")
    if sha(core / "incumbent_20260907.py") != "f8e7fc319cd7240e6db2f0692cd065795574fd6651d42b7e1e9d7400987287d736":
        # Verify the Git blob directly: the original source uses this known pin.
        data = (core / "incumbent_20260907.py").read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != "be6543695b89322e8d3f4cb96f010dc15f8030f1":
            raise ValueError("Original Euler source changed")
    (snapshot / "opponents").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(core / "main.py", snapshot / "opponents/euler28.py")
    compact = peer.build_variant((core / "incumbent_20260907.py").read_text(),
        dict(animal_cap=22, max_hands=9, expansion=False), "incumbent_20260907.py")
    (snapshot / "opponents/compact22.py").write_text(compact)
    opponents = {
        "lean20": str(paths["lean20"]),
        "euler28": str(snapshot / "opponents/euler28.py"),
        "compact22": str(snapshot / "opponents/compact22.py"),
        "official_starter": "official_starter",
    }
    return paths, opponents


def game(job):
    ev = load(KAG / "cloud-eval/evaluate.py", "harvest_evaluator")
    engine, _ = ev.get_engine(job["cache"])
    pair = [job["candidate"], job["opponent_spec"]]
    if job["seat"]:
        pair.reverse()
    result = ev.play(engine, pair, job["cache"], ev.LOADER, job["seed"], job["seat"],
                     action_timeout=1.0, game_timeout=120.0)
    result.update(candidate=job["name"], opponent=job["opponent"], key=job["key"])
    return result


def run(output, cache, phase, workers):
    output, cache = Path(output).resolve(), str(Path(cache).resolve())
    peer = existing()
    ev = load(KAG / "cloud-eval/evaluate.py", "harvest_evaluator")
    _, engine_hashes = ev.get_engine(cache)
    plan = json.loads((HERE / "plan.json").read_text())
    candidates, opponents = prepare_sources(output)
    if phase == "development":
        names = plan["candidates"]
    else:
        selection = json.loads((output / "selection.json").read_text())
        names = [selection["selected"]]
        if sha(candidates[names[0]]) != selection["sha256"]:
            raise ValueError("Selected source changed before validation")
    contract = {
        "phase": phase, "plan": plan, "python": platform.python_version(),
        "engine": engine_hashes, "engine_ref": ev.ENGINE_REF,
        "sources": {str(p.relative_to(KAG)): sha(p) for p in [
            HERE / "study.py", HERE / "variants.py", HERE / "plan.json",
            KAG / "cloud-eval/evaluate.py", KAG / "cloud-market/study.py", ev.LOADER]},
        "candidates": {name: sha(path) for name, path in candidates.items()},
        "opponents": {name: sha(path) if path != "official_starter" else ev.ENGINE_REF
                      for name, path in opponents.items()},
        "limits": {"action_seconds": 1, "game_seconds": 120},
    }
    peer.write_json(output / f"{phase}-contract.json", contract)
    journal = peer.Journal(output / f"{phase}.jsonl", contract)
    jobs = []
    for name in names:
        for opponent in plan[f"{phase}_opponents"]:
            for seed in plan[f"{phase}_seeds"]:
                for seat in plan["seats"]:
                    key = f"{name}/{opponent}/{seed}/{seat}"
                    if key not in journal.rows:
                        jobs.append(dict(name=name, candidate=str(candidates[name]),
                            opponent=opponent, opponent_spec=opponents[opponent],
                            seed=seed, seat=seat, cache=cache, key=key))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(game, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            journal.put(result["key"], result)
            seat = result["candidate_seat"]
            margin = (result["scores"][seat] - result["scores"][1-seat]) if result["scores"] else None
            print(json.dumps(dict(game=result["key"], status=result["status"], margin=margin)), flush=True)
    rows = list(journal.rows.values())
    summary = {name: {opponent: peer.paired_summary([r for r in rows
                if r["candidate"] == name and r["opponent"] == opponent])
                for opponent in plan[f"{phase}_opponents"]} for name in names}
    report = {"contract": contract, "summary": summary, "games": rows}
    peer.write_json(output / f"{phase}.json", report)
    print("SUMMARY " + json.dumps(summary), flush=True)
    if any(r["status"] != "complete" for r in rows):
        raise RuntimeError("Study contains failures; results preserved")
    if phase == "development":
        def rank(name):
            means = [v["mean_margin"] for v in summary[name].values()]
            return min(means), sum(means) / len(means), name
        selected = max(names, key=rank)
        peer.write_json(output / "selection.json", {"selected": selected,
            "sha256": sha(candidates[selected]), "plan_sha256": sha(HERE / "plan.json"),
            "development_report_sha256": sha(output / "development.json"),
            "rank": rank(selected), "development_summary": summary[selected]})
    else:
        selected = names[0]
        stats = summary[selected]
        promoted = all(stats[n]["mean_margin"] > 0 and stats[n]["wins"] >=
                       .6 * stats[n]["games"] for n in ["lean20", "euler28"])
        promoted = promoted and stats["official_starter"]["losses"] == 0
        peer.write_json(output / "promotion.json", {"candidate": selected,
            "sha256": sha(candidates[selected]), "promoted": promoted,
            "rule": plan["promotion"], "summary": stats,
            "validation_report_sha256": sha(output / "validation.json")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["development", "validation"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    run(args.output, args.engine_dir, args.phase, args.workers)
