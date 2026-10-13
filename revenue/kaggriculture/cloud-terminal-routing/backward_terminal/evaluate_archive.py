#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evaluate retained OSPREY suffixes without publishing their private frames."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import random
import sys
import types
from typing import Any, Callable

from backward_terminal import scan_records

ARCHIVE_SHA256 = "a85fdedc100b54d9e853c0db43c6609fece99e93497a49d01df91fdcc12948f4"
ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
ENGINE_HASHES = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_engine(root: Path):
    actual = {name: sha(root / name) for name in ENGINE_HASHES}
    if actual != ENGINE_HASHES:
        raise ValueError("official engine files differ from the recorded source pin")
    tree = ast.parse((root / "utils.py").read_text(encoding="utf-8"))
    helper = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "resolve_episode_seed")
    namespace = {"Any": Any, "Callable": Callable, "random": random}
    exec(compile(ast.Module(body=[helper], type_ignores=[]),
                 str(root / "utils.py"), "exec"), namespace)
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = namespace["resolve_episode_seed"]
    previous = {name: sys.modules.get(name)
                for name in (package.__name__, utils.__name__)}
    sys.modules[package.__name__] = package
    sys.modules[utils.__name__] = utils
    try:
        spec = importlib.util.spec_from_file_location(
            "backward_terminal_official_engine", root / "kaggriculture.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def read_records(path: Path):
    if sha(path) != ARCHIVE_SHA256:
        raise ValueError("retained source archive differs from the recorded pin")
    with lzma.open(path, "rt", encoding="utf-8") as handle:
        outer = json.load(handle)
    if not isinstance(outer, dict):
        raise ValueError("retained archive root must be an object")
    rows = []
    for name, text in sorted(outer.items()):
        if not name.startswith("dev/"):
            continue
        record = json.loads(text)
        if record.get("status") == "complete":
            rows.append((name, record))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("RESULTS.json"))
    args = parser.parse_args()
    records = read_records(args.archive)
    report = scan_records(load_engine(args.engine_dir), records)
    report.update({
        "source_archive_sha256": ARCHIVE_SHA256,
        "engine_ref": ENGINE_REF,
        "engine_sha256": ENGINE_HASHES,
        "independent_development_seeds": sorted({record["seed"] for _, record in records}),
        "new_games": 0,
        "new_agent_calls": 0,
    })
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
