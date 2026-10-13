# SPDX-License-Identifier: MIT
"""Bind the existing native file loader to pinned policy sources; cloud only.

No source downloads, notebook execution, engine replacement or new simulation
occur here. Supply an existing Commons checkout/source transport and compiler.
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

PINS = {
    "cloud-frontier-policy/next-panel/vendor/arlene.py": "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4",
    "cloud-titan-composition/vendor/sell/scheduler.py": "32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9",
}


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load source: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_main(source: Path, arm: str, configuration: bool) -> str:
    """The official native execution namespace does not provide __file__."""
    return f'''import importlib.util as _u
import sys as _s
_s.path.insert(0, {str(source.parent)!r})
_sp=_u.spec_from_file_location('_osprey_{arm}', {str(source)!r})
_m=_u.module_from_spec(_sp)
_sp.loader.exec_module(_m)
def agent(observation, configuration=None):
    return _m.agent(observation{', configuration' if configuration else ''})
'''


def bind(base: Path, runtime: Path, arm: str, source: Path,
         configuration: bool = True) -> None:
    pack = load(base / "cloud-pack/pack.py", "_osprey_pack")
    main = runtime / (arm + "-main.py")
    main.write_text(native_main(source, arm, configuration))
    adapter = runtime / (arm + "-adapter.py")
    pack.write_adapter(adapter, main)
    adapter.write_text(
        f"import sys\nsys.path.insert(0,{str(base/'cloud-frontier-policy/next-panel')!r})\n"
        "from offline import restrict\nrestrict()\n" + adapter.read_text())


def bind_native(base: Path, runtime: Path, arm: str, source: Path) -> None:
    """Preserve raw_path for an entrypoint that resolves its adjacent files."""
    pack = load(base / "cloud-pack/pack.py", "_osprey_pack_native")
    adapter = runtime / (arm + "-adapter.py")
    pack.write_adapter(adapter, source)
    adapter.write_text(
        f"import sys\nsys.path.insert(0,{str(base/'cloud-frontier-policy/next-panel')!r})\n"
        "from offline import restrict\nrestrict()\n" + adapter.read_text())


def prepare(repo: Path, runtime: Path, include_terminal: bool = False) -> dict:
    repo, runtime = repo.resolve(), runtime.resolve()
    if runtime.exists():
        raise FileExistsError("Preserve an existing runtime; choose a fresh destination")
    base = repo / "revenue/kaggriculture"
    for name, expected in PINS.items():
        actual = digest(base / name)
        if actual != expected:
            raise ValueError(f"Frozen source changed: {name}: {actual}")
    runtime.mkdir(parents=True)
    apex = runtime / "apex"
    shutil.copytree(base / "cloud-frontier-policy/next-panel/vendor/apex", apex)
    cmd = ["g++", "-O3", "-std=c++17", "-Wall", "-Wextra", "-pedantic",
           "-shared", "-fPIC", "-Isource/include", "-o", "agent.so",
           "source/policy.cpp", "submission_bridge.cpp"]
    result = subprocess.run(cmd, cwd=apex, capture_output=True, text=True, check=False)
    (runtime / "apex-compile.log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    bind(base, runtime, "baseline", base / next(iter(PINS)), False)
    bind(base, runtime, "sell", base / "cloud-titan-composition/vendor/sell/scheduler.py")
    pack = load(base / "cloud-pack/pack.py", "_osprey_pack_apex")
    adapter = runtime / "apex-adapter.py"
    pack.write_adapter(adapter, apex / "main.py")
    adapter.write_text(
        f"import sys\nsys.path.insert(0,{str(base/'cloud-frontier-policy/next-panel')!r})\n"
        "from offline import restrict\nrestrict()\n" + adapter.read_text())
    if include_terminal:
        t05 = runtime / "t05"
        t05.mkdir()
        own = base / "cloud-terminal-sell"
        shutil.copyfile(own / "vendor/t05-main.py", t05 / "main.py")
        shutil.copyfile(own / "vendor/terminal.py", t05 / "terminal.py")
        shutil.copyfile(base / "cloud-frontier-policy/next-panel/vendor/arlene.py", t05 / "arlene.py")
        bind_native(base, runtime, "t05", t05 / "main.py")
        bind_native(base, runtime, "composed", own / "main.py")
    manifest = {
        "policy_pins": PINS, "apex_compile_command": cmd,
        "files": {str(p.relative_to(runtime)): digest(p)
                  for p in sorted(runtime.rglob("*")) if p.is_file()},
        "meaning": "Prepared native bindings and compiled existing Apex. No game results.",
    }
    (runtime / "PREPARED.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--terminal", action="store_true", help="Also bind T05 and the composed native entrypoints")
    args = parser.parse_args()
    result = prepare(args.repo, args.runtime, args.terminal)
    print(json.dumps({"runtime": str(args.runtime.resolve()),
                      "files": len(result["files"]), "policy_pins": PINS}, indent=2))


if __name__ == "__main__":
    main()
