"""Frozen-source Kaggriculture study. Preparation is the only networked phase.

Extends Euler's published device-side work; never modifies the accepted agent.
All scores are development games, not hosted Kaggle placement or cash earnings.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
SOURCE_REF = "c57fc2962d7a0da5109162f0b6a267967c3a616e"
PEER_PATH = "revenue/kaggriculture/20260907-offline-agent"
SOURCE_BLOBS = {
    "main.py": "f76bfdaa442b63c2a35de829e52e006fc55f6049",
    "incumbent_20260907.py": "be6543695b89322e8d3f4cb96f010dc15f8030f1",
    "evaluate.py": "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5",
    "ECONOMICS.md": "1ccf3c0eb3e6d895c19057c1052e5142ce677c8f",
}
DEV_SEEDS = [733, 2801, 8191]
VALIDATION_SEEDS = [1237, 4421, 10007, 32771, 65539, 131071, 262147, 524287]
VARIANTS = {
    "compact22": dict(animal_cap=22, max_hands=9, expansion=False),
    "lean20": dict(animal_cap=20, max_hands=8, expansion=False),
    "dense24": dict(animal_cap=24, max_hands=8, crop_cap=0, expansion=False),
    "lean22": dict(animal_cap=22, max_hands=8, crop_cap=3, expansion=False),
    "compact_care": dict(animal_cap=22, max_hands=9, expansion=False, care_headroom=True),
    "lean_care": dict(animal_cap=22, max_hands=8, crop_cap=3, expansion=False, care_headroom=True),
    "dense_care": dict(animal_cap=24, max_hands=8, crop_cap=0, expansion=False, care_headroom=True),
    "travel22": dict(animal_cap=22, max_hands=9, expansion=False, distance_penalty=1.1),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as tmp:
        tmp.write(canonical(value) + b"\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        name = tmp.name
    os.replace(name, path)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def evaluator():
    return load(HERE.parent / "cloud-eval" / "evaluate.py", "study_evaluator")


def verify_peer(root):
    hashes = {}
    for name, expected in SOURCE_BLOBS.items():
        data = (Path(root) / "peer" / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != expected:
            raise ValueError(f"Frozen peer source mismatch: {name}")
        hashes[name] = digest(data)
    return hashes


def prepare(root):
    root = Path(root)
    (root / "peer").mkdir(parents=True, exist_ok=True)
    for name in SOURCE_BLOBS:
        url = f"https://raw.githubusercontent.com/woahwhattheheck/commons/{SOURCE_REF}/{PEER_PATH}/{name}"
        with urllib.request.urlopen(url, timeout=45) as response:
            (root / "peer" / name).write_bytes(response.read())
    hashes = verify_peer(root)
    ev = evaluator()
    _, engine_hashes = ev.get_engine(root / "engine", root / "peer/evaluate.py", prepare=True)
    write_json(root / "sources.json", dict(peer_ref=SOURCE_REF, peer_hashes=hashes,
               engine_ref=ev.ENGINE_REF, engine_hashes=engine_hashes))


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one exact source span: {old[:70]}")
    return text.replace(old, new, 1)


def build_variant(source, options, source_name="main.py"):
    """Emit a complete standalone, not a runtime wrapper or imported live policy."""
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "POLICY" for t in node.targets)]
    if len(nodes) != 1:
        raise ValueError("Expected exactly one POLICY assignment")
    node = nodes[0]
    policy = ast.literal_eval(node.value)
    policy.update({k: v for k, v in options.items() if k in policy})
    lines = source.splitlines(keepends=True)
    lines[node.lineno-1:node.end_lineno] = ["POLICY = " + repr(policy) + "\n"]
    changed = "".join(lines)
    if options.get("care_headroom"):
        changed = replace_once(changed,
            'and animal["fed_today"] and remaining_days > 1):',
            'and animal["fed_today"] and remaining_days > 1\n'
            '                    and animal.get("yield_units", 0) + animal.get("pending_care_bonus", 0)\n'
            '                    < ANIMALS[animal["animal"]][4]):')
    if "distance_penalty" in options:
        changed = replace_once(changed, "score = value / (1 + d * .65)",
                               f"score = value / (1 + d * {options['distance_penalty']!r})")
    changed = ("# Derived from Euler / TokenJunkieLabs / Bryce Muhlnickel.\n"
               f"# Frozen source: {SOURCE_REF}/{PEER_PATH}/{source_name}\n"
               "# ASTRA-WORK bounded strategy variation; source license retained.\n" + changed)
    compile(changed, "candidate.py", "exec")
    return changed


class Journal:
    """Every completed/failure result is fsynced; resume never mixes source versions."""
    def __init__(self, path, contract):
        self.path, self.signature = Path(path), digest(canonical(contract))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rows = {}
        if self.path.exists():
            with self.path.open("r+b") as stream:
                while True:
                    start = stream.tell()
                    line = stream.readline()
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        stream.truncate(start)
                        break
                    record = json.loads(line)
                    if record["signature"] != self.signature:
                        raise ValueError("Resume contract changed: source, runtime, settings or seeds differ")
                    key = record["key"]
                    if key in self.rows:
                        raise ValueError("Duplicate game ID in journal")
                    self.rows[key] = record["result"]

    def put(self, key, result):
        if key in self.rows:
            raise ValueError("Game ID already exists")
        with self.path.open("ab") as stream:
            stream.write(canonical(dict(signature=self.signature, key=key, result=result)) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.rows[key] = result


def paired_summary(rows):
    valid = [row for row in rows if row["status"] == "complete"]
    margins = [r["scores"][r["candidate_seat"]] - r["scores"][1-r["candidate_seat"]] for r in valid]
    pairs = {}
    for row, margin in zip(valid, margins):
        pairs.setdefault(row["seed"], {})[row["candidate_seat"]] = margin
    seed_means = [statistics.mean(seats.values()) for seats in pairs.values() if set(seats) == {0, 1}]
    interval = None
    if len(seed_means) >= 2:
        rng = random.Random(1907)
        samples = sorted(statistics.mean(rng.choices(seed_means, k=len(seed_means))) for _ in range(2000))
        interval = [samples[49], samples[1949]]
    return dict(games=len(rows), completed=len(valid), failures=len(rows)-len(valid),
                wins=sum(m>0 for m in margins), ties=sum(m==0 for m in margins), losses=sum(m<0 for m in margins),
                mean_margin=statistics.mean(margins) if margins else None,
                min_margin=min(margins) if margins else None,
                paired_seeds=len(seed_means), seed_bootstrap_95_percentile=interval,
                note="Seat-paired seed bootstrap; descriptive, not a multiple-selection-corrected guarantee.")


def run(root, phase):
    root = Path(root).resolve()
    ev = evaluator()
    peer_hashes = verify_peer(root)
    engine, engine_hashes = ev.get_engine(root / "engine", root / "peer/evaluate.py")
    generated = root / "generated"
    generated.mkdir(exist_ok=True)
    base = (root / "peer/main.py").read_text()
    files = {}
    for name, options in VARIANTS.items():
        path = generated / f"{name}.py"
        path.write_text(build_variant(base, options))
        files[name] = str(path)
    compact_path = generated / "frozen_compact22.py"
    compact_path.write_text(build_variant((root / "peer/incumbent_20260907.py").read_text(), VARIANTS["compact22"], "incumbent_20260907.py"))
    opponents = {"euler28": str(root / "peer/main.py"), "compact22": str(compact_path)}
    selection = None
    if phase == "validation":
        selection = json.loads((root / "selection.json").read_text())
        names = [selection["variant"]]
        seeds = VALIDATION_SEEDS
        if digest(Path(files[names[0]]).read_bytes()) != selection["candidate_sha256"]:
            raise ValueError("Selected candidate changed before validation")
        opponents.update(incumbent36=str(root / "peer/incumbent_20260907.py"), starter="official_starter")
    else:
        names, seeds = list(VARIANTS), DEV_SEEDS
    source_contract = dict(peer_ref=SOURCE_REF, peer_hashes=peer_hashes, engine_hashes=engine_hashes,
                    engine_ref=ev.ENGINE_REF, study_sha256=digest(Path(__file__).read_bytes()),
                    evaluator_sha256=digest(Path(ev.__file__).read_bytes()), python=sys.version,
                    platform=sys.platform, variant_settings=VARIANTS,
                    candidates={n:digest(Path(files[n]).read_bytes()) for n in names},
                    opponents={n:digest(Path(p).read_bytes()) if p != "official_starter" else ev.ENGINE_REF for n,p in opponents.items()},
                    phase=phase, seeds=seeds, seats=[0,1], action_timeout=1.0, rng_seed=20260907,
                    runtime_image=os.environ.get("KAG_RUNTIME_IMAGE", "unrecorded"))
    journal = Journal(root / f"{phase}.jsonl", source_contract)
    summaries = {}
    for name in names:
        summaries[name] = {}
        for rival, opponent in opponents.items():
            for seed in seeds:
                for seat in (0, 1):
                    key = f"{name}/{rival}/{seed}/{seat}"
                    if key not in journal.rows:
                        pair = [files[name], opponent] if seat == 0 else [opponent, files[name]]
                        row = ev.play(engine, pair, root / "engine", root / "peer/evaluate.py", seed, seat)
                        row.update(variant=name, opponent=rival)
                        journal.put(key, row)
                        print(json.dumps({k:row[k] for k in ("variant","opponent","seed","candidate_seat","status","scores","failure")}), flush=True)
            rows = [r for r in journal.rows.values() if r["variant"] == name and r["opponent"] == rival]
            summaries[name][rival] = paired_summary(rows)
    report = dict(contract=source_contract, summary=summaries, games=list(journal.rows.values()))
    write_json(root / f"{phase}.json", report)
    print("RESULT " + json.dumps(summaries), flush=True)
    if any(row["status"] != "complete" for row in journal.rows.values()):
        raise RuntimeError("Study contains failures; preserved in report, not counted as wins")
    if phase == "development":
        def score(name):
            values = [s["mean_margin"] for s in summaries[name].values()]
            return min(values), statistics.mean(values), name
        selected = max(names, key=score)
        selection = dict(variant=selected, candidate_sha256=digest(Path(files[selected]).read_bytes()),
                         settings=VARIANTS[selected], development_contract=digest(canonical(source_contract)),
                         selection_rule="max(min(mean margin vs euler28, mean margin vs frozen compact22)); ties by mean then name",
                         validation_seeds=VALIDATION_SEEDS)
        write_json(root / "selection.json", selection)
        (root / "selected_main.py").write_bytes(Path(files[selected]).read_bytes())
        print("SELECTED " + json.dumps(selection), flush=True)
    else:
        checks = {}
        for name, opponent in opponents.items():
            pair = [files[names[0]], opponent]
            repeated = ev.play(engine, pair, root / "engine", root / "peer/evaluate.py", seeds[0], 0)
            original = journal.rows[f"{names[0]}/{name}/{seeds[0]}/0"]
            checks[name] = (repeated["status"] == original["status"] == "complete" and
                            repeated["scores"] == original["scores"] and repeated["trace_sha256"] == original["trace_sha256"])
        report["replay_by_opponent"] = checks
        write_json(root / "validation.json", report)
        if not all(checks.values()):
            raise RuntimeError("A validation replay differed")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "development", "validation"])
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.root)
    else:
        run(args.root, args.phase)


if __name__ == "__main__":
    main()
