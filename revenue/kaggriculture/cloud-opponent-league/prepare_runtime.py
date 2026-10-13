#!/usr/bin/env python3
"""Prepare T09 from a verified, already-downloaded public source pack; no network.

Uses the existing frontier preparer/archive verifier and native Apex compiler.
A C++17 compiler and the Python standard library are required. It never submits
an agent, reads credentials, changes an existing runtime, or chooses a policy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

FRONTIER_REF = "8329e78768906dc6e75ca3712e1690adc1ab2148"
CAP_REF = "473e63d7151d4acdcdeeb76c784aaf4054c062e3"
ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_pack(source: Path) -> dict:
    manifest = json.loads((source / "SOURCE_MANIFEST.json").read_text())
    if manifest.get("complete") is not True or not manifest.get("files"):
        raise ValueError("source pack is incomplete")
    seen = set()
    for row in manifest["files"]:
        rel = row["path"]
        path = (source / rel).resolve()
        if rel in seen or not path.is_relative_to(source.resolve()) or not path.is_file():
            raise ValueError("invalid/duplicate source member: " + rel)
        seen.add(rel)
        data = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if digest(data) != row["sha256"] or blob != row["git_blob"]:
            raise ValueError("source content mismatch: " + rel)
        expected = (FRONTIER_REF if rel.startswith("frontier/") else
                    CAP_REF if rel.startswith("cap/") else
                    ENGINE_REF if rel.startswith("engine/") else None)
        if row.get("ref") != expected or expected is None:
            raise ValueError("unexpected source pin: " + rel)
    return manifest


def prepare(source: Path, runtime: Path) -> dict:
    if runtime.exists():
        raise FileExistsError("runtime exists; preserve it and use a new path")
    manifest = verified_pack(source)
    runtime.mkdir(parents=True)
    base = runtime / "commons/revenue/kaggriculture"
    shutil.copytree(source / "frontier/revenue/kaggriculture", base)
    shutil.copytree(source / "cap/revenue/kaggriculture/cloud-model-lab",
                    base / "cloud-model-lab")
    shutil.copytree(source / "engine", runtime / "engine")
    # Existing cap engine_pin.py resolves this exact sibling, not a replacement
    # model; preserve the official bytes and the parent's own validation.
    shutil.copytree(source / "engine", base / "cloud-frontier-policy/vendor/engine-pin",
                    dirs_exist_ok=True)
    shutil.copy2(source / "SOURCE_MANIFEST.json", runtime / "SOURCE_MANIFEST.json")
    prepared = runtime / "prepared"
    preparer = base / "cloud-frontier-policy/next-panel/prepare.py"
    command = [sys.executable, "-B", str(preparer), "--runtime", str(prepared)]
    result = subprocess.run(command, cwd=runtime, text=True, capture_output=True, timeout=120)
    (runtime / "preparation.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("existing frontier preparer failed; see runtime/preparation.log")
    # Retain the native offline guard from the already-built original adapter.
    original_adapter = (prepared / "arlene-adapter.py").read_text()
    marker = "import importlib.util\n"
    if marker not in original_adapter:
        raise ValueError("original adapter format changed")
    guard = original_adapter.split(marker, 1)[0]
    cap = guard + f'''import sys
from pathlib import Path
BASE = Path({str(base)!r})
sys.path.insert(0, str(BASE / "cloud-model-lab"))
import importlib.util, arlene_plan
import native_motifs as motifs
spec = importlib.util.spec_from_file_location("_league_arlene_parent", BASE / "cloud-frontier-policy/next-panel/vendor/arlene.py")
original = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = original
spec.loader.exec_module(original)
_policy = arlene_plan.PlanOverlay(original, arlene_plan.CapChooser(motifs.engine()),
    max_steps=14, deposit=True, one_way=True, last_day=29, min_value=0.0)
def agent(observation, configuration=None):
    return _policy.act(observation)
'''
    (runtime / "cap.py").write_text(cap)
    original_target = str(preparer.parent / "vendor/arlene.py")
    carrot_target = str(preparer.parent / "carrot-demand-main.py")
    if original_adapter.count(repr(original_target)) != 1:
        raise ValueError("original Arlene file adapter target changed")
    (runtime / "carrot.py").write_text(original_adapter.replace(repr(original_target), repr(carrot_target)))
    paths = {
        "control": "prepared/arlene-adapter.py", "cap": "cap.py", "carrot": "carrot.py",
        "apex": "prepared/apex-adapter.py", "engine": "engine/kaggriculture.py",
        "schema": "engine/kaggriculture.json", "utils": "engine/utils.py",
        "evaluator": "commons/revenue/kaggriculture/cloud-eval/evaluate.py",
        "loader": "commons/revenue/kaggriculture/20260907-offline-agent/evaluate.py",
    }
    for rel in paths.values():
        if not (runtime / rel).is_file():
            raise ValueError("missing prepared asset: " + rel)
    assets = {"paths": paths, "provenance": {
        "commons_frontier_ref": FRONTIER_REF, "commons_cap_ref": CAP_REF,
        "engine_ref": ENGINE_REF, "source_pack_artifact": 10030683172,
        "source_pack_manifest_sha256": digest((source / "SOURCE_MANIFEST.json").read_bytes()),
        "preparer_sha256": digest(Path(__file__).read_bytes()),
        "source_files_verified": len(manifest["files"]),
        "cap_configuration": {"max_steps": 14, "deposit": True, "one_way": True,
                              "last_day": 29, "min_value": 0.0},
        "carrot": "unchanged frozen frontier export; adapter only",
        "build": command, "network": "no network used during preparation"}}
    (runtime / "assets.json").write_text(json.dumps(assets, indent=2) + "\n")
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pack", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_pack.resolve(), args.runtime.resolve()), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
