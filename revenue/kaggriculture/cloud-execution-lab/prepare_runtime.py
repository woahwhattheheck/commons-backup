"""Build the pinned public Apex opponent and timed official-loader adapters.

Only local reviewed sources are read; all paths remain in this cloud lane.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ENGINE_SHA256 = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(runtime, targets=None):
    runtime = Path(runtime).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    for name, expected in ENGINE_SHA256.items():
        actual = sha256(HERE / "reference/engine" / name)
        if actual != expected:
            raise ValueError(f"Pinned engine hash differs: {name}: {actual}")
    upstream = json.loads((HERE / "reference/next-panel/UPSTREAM.json").read_text())
    for name, detail in upstream["files"].items():
        if name.startswith("vendor/apex/"):
            source = HERE / "reference/apex" / name.removeprefix("vendor/apex/")
            if sha256(source) != detail["sha256"]:
                raise ValueError(f"Pinned Apex hash differs: {name}")
    arlene = HERE / "reference/next-panel/vendor/arlene.py"
    if sha256(arlene) != upstream["files"]["vendor/arlene.py"]["sha256"]:
        raise ValueError("Pinned unchanged Arlene hash differs")
    shutil.copytree(HERE / "reference/apex", runtime / "apex", dirs_exist_ok=True)
    # Preserve the upstream public-parent attribution beside the built opponent.
    for filename in ("LICENSE", "NEXT-DISTRIBUTION-NOTICE.txt", "UPSTREAM.json"):
        shutil.copy2(HERE / "reference/next-panel" / filename, runtime / "apex" / filename)
    command = ["g++", "-O3", "-std=c++17", "-Wall", "-Wextra", "-pedantic",
               "-shared", "-fPIC", "-Isource/include", "-o", "agent.so",
               "source/policy.cpp", "submission_bridge.cpp"]
    result = subprocess.run(command, cwd=runtime / "apex", capture_output=True, text=True, check=True)
    (runtime / "compile.txt").write_text(result.stdout + result.stderr)
    spec = importlib.util.spec_from_file_location("existing_cloud_pack", HERE / "reference/evaluator/pack.py")
    pack = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pack
    spec.loader.exec_module(pack)
    all_targets = {"baseline": arlene, "arlene": arlene, "apex": runtime / "apex/main.py"}
    all_targets.update(targets or {})
    for name, target in all_targets.items():
        adapter = runtime / (name + "-adapter.py")
        pack.write_adapter(adapter, Path(target).resolve())
        # Reuse the already-reviewed benchmark restriction from the public panel.
        prefix = ("import sys\n" + f"sys.path.insert(0, {str(HERE / 'reference/next-panel')!r})\n"
                  + "from offline import restrict\nrestrict()\n")
        adapter.write_text(prefix + adapter.read_text())
    files = {str(p.relative_to(HERE)): {"sha256": sha256(p), "bytes": p.stat().st_size}
             for folder in (HERE / "reference/evaluator", HERE / "reference/apex", runtime)
             for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and p.name != "manifest.json"}
    manifest = {
        "commons_reference": "8329e78768906dc6e75ca3712e1690adc1ab2148",
        "engine_reference": "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c",
        "engine_sha256": ENGINE_SHA256,
        "compiler": subprocess.check_output(["g++", "--version"], text=True),
        "compile_command": command,
        "targets": {name: {"path": str(Path(path).resolve()), "sha256": sha256(path)}
                    for name, path in all_targets.items()},
        "lane_python_sources": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size}
                                for p in HERE.glob("*.py")},
        "first_call": "Existing official file-loader initialization, source compilation, imports and policy initialization occur inside first timed action.",
        "isolation": "Existing evaluator: fresh persistent process per actor/game, private cwd and scrubbed environment, only seat observation. Existing next-panel Linux seccomp restriction loaded before policy.",
        "files": files,
    }
    (runtime / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=HERE / "runtime")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--naive", type=Path)
    args = parser.parse_args()
    manifest = prepare(args.runtime, {name: value for name, value in
                       (("candidate", args.candidate), ("naive", args.naive)) if value})
    print(json.dumps({key: manifest[key] for key in ("engine_sha256", "targets", "compile_command")}, indent=2))
