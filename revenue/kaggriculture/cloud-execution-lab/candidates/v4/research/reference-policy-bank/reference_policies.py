# SPDX-License-Identifier: Apache-2.0
"""Source-pinned public policies for the ONE V4 gauntlet.

This is a bridge, not another simulator. Preparation uses the existing pinned
file-loader adapter; play uses cloud-eval.Actor's fresh persistent process.
Run executable policies only in a trusted isolated cloud/container environment.
The process/IPC guard does not constitute a general filesystem security sandbox.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA = "titan.v4.reference-policy.v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def checked_path(root: Path, relative: str) -> Path:
    """Reject escaping paths and symlinks; closure members are ordinary files."""
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts or not part.parts:
        raise ValueError(f"Unsafe relative source path: {relative!r}")
    path = root / part
    if any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise ValueError(f"Symlink source path: {relative!r}")
    path.resolve(strict=True).relative_to(root.resolve(strict=True))
    if not path.is_file():
        raise ValueError(f"Not a source file: {relative!r}")
    return path


def verify_files(root: Path, files: Mapping[str, str]) -> None:
    if not files:
        raise ValueError("Empty source closure")
    for name, expected in files.items():
        path = checked_path(root, name)
        if digest(path) != expected:
            raise ValueError(f"Source hash mismatch: {name}")


def prepare(key: str, kg_root: Path, output: Path,
            registry_path: Path = HERE / "REFERENCE-POLICIES.json") -> dict:
    """Verify existing source, copy only declared files, precompile, then adapt.

    The upstream policy is never edited. Existing output is never overwritten.
    Kaito/Igor missing source fails explicitly; a historical score is not source.
    """
    kg_root = kg_root.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    registry = json.loads(registry_path.read_text())
    record = registry["policies"][key]
    source = kg_root / record["root"]
    verify_files(source, record["files"])
    notices = record.get("notices", {})
    if notices:
        verify_files(kg_root, notices)
    support = ["cloud-eval/evaluate.py", "20260907-offline-agent/evaluate.py",
               "cloud-pack/pack.py", "cloud-pack/official.py",
               "cloud-frontier-policy/next-panel/offline.py"]
    upstream = kg_root / "cloud-pack/upstream"
    loader_manifest = json.loads((upstream / "manifest.json").read_text())
    support += ["cloud-pack/upstream/manifest.json"]
    support += ["cloud-pack/upstream/" + n for n in loader_manifest["files"]]
    support_hashes = {name: digest(checked_path(kg_root, name)) for name in support}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Build in a private temporary directory, but emit the adapter only AFTER
    # moving to its final path: pack.write_adapter embeds absolute paths.
    with tempfile.TemporaryDirectory(prefix="reference-build-", dir=output.parent) as temp:
        stage = Path(temp) / "policy"
        stage.mkdir()
        for name in record["files"]:
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checked_path(source, name), target)
        compiler = None
        if key == "apex_v7":
            command = ["g++", "-O3", "-std=c++17", "-Wall", "-Wextra", "-pedantic",
                       "-shared", "-fPIC", "-Isource/include", "-o", "agent.so",
                       "source/policy.cpp", "submission_bridge.cpp"]
            built = subprocess.run(command, cwd=stage, capture_output=True, text=True,
                                   check=True, timeout=60)
            compiler = {"command": command, "stdout": built.stdout, "stderr": built.stderr,
                        "version": subprocess.check_output(["g++", "--version"], text=True)}
        # mkdir provides create-only publication even if another worker raced us.
        output.mkdir()
        try:
            shutil.copytree(stage, output / "policy")
            for index, name in enumerate(notices):
                shutil.copyfile(kg_root / name, output / (f"upstream-{index}-" + Path(name).name))
            (output / "UPSTREAM-ATTRIBUTION.json").write_text(json.dumps(record, indent=2) + "\n")
            pack = load_module(kg_root / "cloud-pack/pack.py", "basalt_existing_pack")
            adapter = output / "adapter.py"
            pack.write_adapter(adapter, output / "policy" / record["entry"])
            guard = kg_root / "cloud-frontier-policy/next-panel/offline.py"
            prefix = ("import importlib.util as _guard_util\n"
                      f"_guard_spec = _guard_util.spec_from_file_location('basalt_offline', {str(guard)!r})\n"
                      "_guard = _guard_util.module_from_spec(_guard_spec)\n"
                      "_guard_spec.loader.exec_module(_guard)\n_guard.restrict()\n")
            adapter.write_text(prefix + adapter.read_text())
            files = {p.relative_to(output).as_posix(): digest(p)
                     for p in sorted(output.rglob("*")) if p.is_file()}
            manifest = {"schema": SCHEMA, "key": key, "kind": record["kind"],
                        "source": record, "source_registry_sha256": digest(registry_path),
                        "bridge_sha256": digest(Path(__file__)), "runtime_files": files,
                        "support_root": str(kg_root), "support_files": support_hashes,
                        "adapter": "adapter.py", "compiler": compiler,
                        "method": "Existing cloud-pack pinned raw file loader + cloud-eval.Actor; "
                                  "not hosted Kaggle; fresh process per game; no PASS on failure."}
            (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            return manifest
        except BaseException:
            shutil.rmtree(output)
            raise


class PolicyFailure(RuntimeError):
    def __init__(self, response: dict):
        self.response = response
        super().__init__(json.dumps(response, sort_keys=True))


class ReferencePolicy:
    """One public policy instance for exactly one game and one player position.

    Construct inside each gauntlet match's context/finally. No cached singleton,
    thread-global module or on-error fallback is used. A failed/closed instance
    cannot continue. Runtime source verification precedes every actor startup.
    """
    def __init__(self, runtime: Path, engine_dir: Path, *, rng_seed: int = 20260908,
                 action_timeout: float = 1.0, startup_timeout: float = 10.0):
        if any(isinstance(v, bool) or not math.isfinite(v) or v <= 0
               for v in (action_timeout, startup_timeout)):
            raise ValueError("Timeouts must be finite and positive")
        if type(rng_seed) is not int:
            raise TypeError("Policy RNG seed must be an integer, independent of game seed/seat")
        self.actor = None
        self.closed = False
        self.step = -1
        self.seat = None
        self.action_timeout = action_timeout
        runtime = runtime.resolve(strict=True)
        self.manifest = json.loads((runtime / "manifest.json").read_text())
        if self.manifest["schema"] != SCHEMA:
            raise ValueError("Unknown reference-policy schema")
        verify_files(runtime, self.manifest["runtime_files"])
        root = Path(self.manifest["support_root"])
        verify_files(root, self.manifest["support_files"])
        ev = load_module(root / "cloud-eval/evaluate.py", "basalt_existing_evaluator")
        ev.verify_sources(engine_dir)
        try:
            self.actor = ev.Actor(str(runtime / self.manifest["adapter"]), engine_dir,
                                  root / "20260907-offline-agent/evaluate.py",
                                  rng_seed, startup_timeout)
            if self.actor.ready.get("kind") != "ready":
                raise PolicyFailure(self.actor.ready)
        except BaseException:
            self.close()
            raise

    def __call__(self, observation: Mapping[str, Any], configuration: Mapping[str, Any]) -> dict:
        if self.closed or self.actor is None:
            raise RuntimeError("Reference policy is closed")
        step = observation.get("step")
        seat = observation.get("player")
        if type(step) is not int or step != self.step + 1:
            raise ValueError("Policy requires consecutive steps starting at zero; use a fresh instance per game")
        if type(seat) is not int or seat not in (0, 1) or (self.seat is not None and seat != self.seat):
            raise ValueError("Policy cannot switch player positions within a game")
        if configuration.get("seed") is not None:
            raise ValueError("Do not expose the private engine seed to an opponent")
        response = self.actor.act(observation, configuration, self.action_timeout)
        if response.get("kind") != "action":
            self.close()
            raise PolicyFailure(response)
        self.step, self.seat = step, seat
        return response["action"]

    def report(self) -> dict:
        return self.actor.report() if self.actor is not None else {}

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            if self.actor is not None:
                self.actor.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key", required=True)
    p.add_argument("--kg-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--registry", type=Path, default=HERE / "REFERENCE-POLICIES.json")
    a = p.parse_args()
    result = prepare(a.key, a.kg_root, a.out, a.registry)
    print(json.dumps({k: result[k] for k in ("schema", "key", "kind", "adapter")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
