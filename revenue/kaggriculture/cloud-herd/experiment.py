"""Frozen-source herd procurement study using the existing official-engine driver.

SPDX-License-Identifier: MIT OR CC-BY-4.0
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import sys
import urllib.request

from variants import BASE_PATH, BASE_REF, BASE_SHA256, VARIANTS, build

HERE = Path(__file__).resolve().parent
DEV_SEEDS = [1543, 4787, 9431]
VALIDATION_SEEDS = [10657, 15467, 27653, 39019, 56393, 79139, 110221, 190027]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def infrastructure():
    return load(HERE.parent / "cloud-market/study.py", "herd_existing_study")


def prepare(root):
    study = infrastructure()
    # Reuse the source-pin and three-file engine preparation already delivered.
    study.prepare(root)
    path = root / "lean20.py"
    with urllib.request.urlopen(
        f"https://raw.githubusercontent.com/woahwhattheheck/commons/{BASE_REF}/{BASE_PATH}",
        timeout=45,
    ) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != BASE_SHA256:
        raise ValueError("Frozen lean20 source mismatch")
    path.write_bytes(data)


def candidates(root):
    """Materialize runnable files without starting any test or simulation."""
    root = root.resolve()
    source = (root / "lean20.py").read_text()
    if hashlib.sha256(source.encode()).hexdigest() != BASE_SHA256:
        raise ValueError("Frozen lean20 source mismatch")
    generated = root / "herd-generated"
    generated.mkdir(exist_ok=True)
    files = {}
    for name, options in VARIANTS.items():
        path = generated / f"{name}.py"
        path.write_text(build(source, options))
        files[name] = str(path)
    return files


def opponent_hashes(opponents):
    return {name: dict(sha256=hashlib.sha256(Path(spec.partition("::")[0]).read_bytes()).hexdigest(),
                       function=spec.partition("::")[2] or "agent")
            for name, spec in opponents.items()}


def run(root, phase, extra_opponents=None):
    root = root.resolve()
    study = infrastructure()
    ev = study.evaluator()
    peer_hashes = study.verify_peer(root)
    engine, engine_hashes = ev.get_engine(root / "engine", root / "peer/evaluate.py")
    source = (root / "lean20.py").read_text()
    if study.digest(source.encode()) != BASE_SHA256:
        raise ValueError("Frozen lean20 source mismatch")
    files = candidates(root)
    generated = root / "herd-generated"
    compact = generated / "frozen_compact22.py"
    compact.write_text(study.build_variant((root / "peer/incumbent_20260907.py").read_text(),
        dict(animal_cap=22, max_hands=9, expansion=False), "incumbent_20260907.py"))
    goose = generated / "frozen_goose20.py"
    goose_source = source.replace("'mixed': True", "'mixed': False")
    if goose_source == source:
        raise ValueError("Expected one mixed-herd setting")
    goose.write_text(goose_source)
    opponents = {"lean20": str(root / "lean20.py"), "euler28": str(root / "peer/main.py")}
    for label, spec in (extra_opponents or {}).items():
        if label in {"lean20", "euler28", "compact22", "goose20"}:
            raise ValueError("Additional opponent must have a distinct label")
        opponents[label] = spec
    development_opponents = opponent_hashes(opponents)
    if phase == "development":
        names, seeds = list(VARIANTS), DEV_SEEDS
    else:
        selection = json.loads((root / "herd-selection.json").read_text())
        names, seeds = [selection["variant"]], VALIDATION_SEEDS
        if study.digest(Path(files[names[0]]).read_bytes()) != selection["candidate_sha256"]:
            raise ValueError("Selected candidate changed before validation")
        if development_opponents != selection["development_opponents"]:
            raise ValueError("Use the same exact additional opponents as development")
        opponents.update(compact22=str(compact), goose20=str(goose))
    contract = dict(base_ref=BASE_REF, base_sha256=BASE_SHA256, peer_hashes=peer_hashes,
        engine_ref=ev.ENGINE_REF, engine_hashes=engine_hashes,
        source_hashes={str(p.relative_to(HERE.parent)): study.digest(p.read_bytes()) for p in
            [Path(__file__), HERE / "variants.py", Path(study.__file__), Path(ev.__file__)]},
        python=sys.version, platform=sys.platform, variants=VARIANTS, seeds=seeds, seats=[0, 1],
        candidates={n: study.digest(Path(files[n]).read_bytes()) for n in names},
        opponents=opponent_hashes(opponents),
        action_timeout=1.0, game_timeout=120.0, rng_seed=20260907, phase=phase,
        runtime_image=os.environ.get("KAG_RUNTIME_IMAGE", "not-containerized"))
    journal = study.Journal(root / f"herd-{phase}.jsonl", contract)
    summary = {}
    for name in names:
        summary[name] = {}
        for rival, opponent in opponents.items():
            for seed in seeds:
                for seat in (0, 1):
                    key = f"{name}/{rival}/{seed}/{seat}"
                    if key not in journal.rows:
                        pair = [files[name], opponent] if seat == 0 else [opponent, files[name]]
                        result = ev.play(engine, pair, root / "engine", root / "peer/evaluate.py", seed, seat)
                        result.update(variant=name, opponent=rival)
                        journal.put(key, result)
                        print(json.dumps({k: result[k] for k in
                            ("variant", "opponent", "seed", "candidate_seat", "status", "scores", "failure")}), flush=True)
            rows = [r for r in journal.rows.values() if r["variant"] == name and r["opponent"] == rival]
            summary[name][rival] = study.paired_summary(rows)
    report = dict(contract=contract, summary=summary, games=list(journal.rows.values()))
    study.write_json(root / f"herd-{phase}.json", report)
    if any(row["status"] != "complete" for row in journal.rows.values()):
        raise RuntimeError("Failed games retained; candidate selection is unavailable")
    if phase == "development":
        def score(name):
            values = [s["mean_margin"] for s in summary[name].values()]
            return min(values), statistics.mean(values), name
        selected = max(names, key=score)
        selection = dict(variant=selected, candidate_sha256=study.digest(Path(files[selected]).read_bytes()),
            settings=VARIANTS[selected], development_contract=study.digest(study.canonical(contract)),
            development_opponents=development_opponents,
            selection_rule="Maximize minimum mean margin across all declared development opponents; ties by overall mean and name.",
            validation_seeds=VALIDATION_SEEDS)
        study.write_json(root / "herd-selection.json", selection)
        (root / "selected_herd_main.py").write_bytes(Path(files[selected]).read_bytes())
        print("SELECTED " + json.dumps(selection), flush=True)
    else:
        checks = {}
        for rival, opponent in opponents.items():
            repeated = ev.play(engine, [files[names[0]], opponent], root / "engine", root / "peer/evaluate.py", seeds[0], 0)
            original = journal.rows[f"{names[0]}/{rival}/{seeds[0]}/0"]
            checks[rival] = (repeated["status"] == original["status"] == "complete" and
                repeated["scores"] == original["scores"] and repeated["trace_sha256"] == original["trace_sha256"])
        report["replay_by_opponent"] = checks
        study.write_json(root / "herd-validation.json", report)
        if not all(checks.values()):
            raise RuntimeError("A validation replay differed")
    print("SUMMARY " + json.dumps(summary), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "candidates", "development", "validation"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--opponent", action="append", default=[], metavar="NAME=PATH[::FUNCTION]",
                        help="Additional pinned public opponent; repeat the identical set for validation")
    args = parser.parse_args()
    extras = {}
    for raw in args.opponent:
        label, sep, spec = raw.partition("=")
        if not sep or not label or not spec or label in extras:
            parser.error("Each additional opponent needs a unique NAME=PATH[::FUNCTION]")
        path, function_sep, function = spec.partition("::")
        extras[label] = str(Path(path).resolve()) + ("::" + function if function_sep else "")
    if args.phase == "prepare":
        prepare(args.root)
    elif args.phase == "candidates":
        print(json.dumps(candidates(args.root), indent=2))
    else:
        run(args.root, args.phase, extras)
