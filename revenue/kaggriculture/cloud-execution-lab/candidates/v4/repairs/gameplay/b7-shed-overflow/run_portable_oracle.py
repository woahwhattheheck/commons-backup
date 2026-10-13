#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the existing pinned B7 oracle without installing Kaggle dependencies.

Only six authenticated files enter a disposable tree. Existing repository files
are never overwritten; an existing wrong blob cannot be repaired from an archive.
The full engine executes unchanged. Only its external seed-resolver import is
adapted, using the exact function AST from the separately pinned official utils.
This is component evidence, not agent/package/hosted-game validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile

LAB = "revenue/kaggriculture/cloud-execution-lab/"
HOME = LAB + "candidates/v4/repairs/gameplay/b7-shed-overflow/"
ORACLE = HOME + "current_engine_oracle.py"
HELPER = HOME + "legacy/b7_shed_room_guard.py"
PINS = {
    ORACLE: "109bf70a385b211eede790f00a2de05a979b4e02",
    HELPER: "a27da659884c0f9a9594cbd9332b5edb4d7f3307",
    LAB + "reference/engine/kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    LAB + "reference/engine/kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    LAB + "reference/engine/utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
    LAB + "titan_runtime.py": "b952c9c228ecbde592bf3d2df01638677abb0d24",
}
MAX_FILE_BYTES = 512 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 4096


class PortableError(RuntimeError):
    """A custody, dependency, subprocess, or oracle check failed."""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def checked(data: bytes, relative: str) -> bytes:
    if len(data) > MAX_FILE_BYTES or git_blob(data) != PINS[relative]:
        raise PortableError(f"source drift: {relative}")
    return data


def local_bytes(root: Path, relative: str) -> bytes | None:
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise PortableError(f"symlink source: {relative}")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise PortableError(f"invalid source file: {relative}")
    return checked(path.read_bytes(), relative)


def archive_bytes(archives: list[Path], missing: set[str]) -> dict[str, bytes]:
    """Read candidate members as data; never trust names as extraction paths."""
    found = {}
    by_name = {PurePosixPath(rel).name: rel for rel in missing}
    for archive in archives:
        if not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise PortableError(f"invalid archive: {archive}")
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
                raise PortableError("archive exceeds bounded staging limits")
            for info in infos:
                name = PurePosixPath(info.filename)
                rel = by_name.get(name.name)
                if rel is None:
                    continue
                mode = (info.external_attr >> 16) & 0xFFFF
                if (name.is_absolute() or ".." in name.parts or "\\" in info.filename
                        or info.is_dir() or info.flag_bits & 1
                        or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                        or info.file_size > MAX_FILE_BYTES):
                    raise PortableError(f"invalid candidate archive member: {info.filename}")
                data = zf.read(info)
                if len(data) != info.file_size:
                    raise PortableError("archive member size mismatch")
                if git_blob(data) == PINS[rel]:
                    found[rel] = data
    return found


def collect(root: Path, archives: list[Path]) -> dict[str, bytes]:
    data = {}
    for relative in PINS:
        value = local_bytes(root, relative)
        if value is not None:
            data[relative] = value
    for relative in (ORACLE, HELPER):
        if relative not in data:
            raise PortableError(f"canonical source missing: {relative}")
    missing = set(PINS) - data.keys()
    if missing:
        data.update(archive_bytes(archives, missing))
    if set(data) != set(PINS):
        raise PortableError("missing pinned dependencies: " + ", ".join(sorted(set(PINS) - data.keys())))
    return data


# This bootstrap never modifies oracle/engine/helper bytes or imports titan_runtime.
# It runs in a fresh isolated interpreter, not in the caller's import namespace.
BOOTSTRAP = r'''
import ast, importlib.util, json, random, sys, types
from pathlib import Path
from typing import Any, Callable
root = Path(sys.argv[1])
lab = root / "revenue/kaggriculture/cloud-execution-lab"
source = (lab / "reference/engine/utils.py").read_text(encoding="utf-8")
nodes = [n for n in ast.parse(source).body
         if isinstance(n, ast.FunctionDef) and n.name == "resolve_episode_seed"]
if len(nodes) != 1:
    raise RuntimeError("seed resolver is not unique")
namespace = {"Any": Any, "Callable": Callable, "random": random}
exec(compile(ast.Module(body=nodes, type_ignores=[]), "pinned-utils-resolver", "exec"), namespace)
resolver = namespace["resolve_episode_seed"]
seed_calls = 0
def counted(*args, **kwargs):
    global seed_calls
    seed_calls += 1
    return resolver(*args, **kwargs)
package = types.ModuleType("kaggle_environments")
package.__path__ = []
utils = types.ModuleType("kaggle_environments.utils")
utils.resolve_episode_seed = counted
package.utils = utils
sys.modules[package.__name__] = package
sys.modules[utils.__name__] = utils
path = lab / "candidates/v4/repairs/gameplay/b7-shed-overflow/current_engine_oracle.py"
spec = importlib.util.spec_from_file_location("_pinned_b7_portable_oracle", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.run()
print(json.dumps({"oracle": result, "seed_resolver_calls": seed_calls}, sort_keys=True))
'''


def execute(staged: Path, optimized: bool) -> dict:
    command = [sys.executable, "-I", "-B"]
    if optimized:
        command.append("-O")
    command += [str(staged / "bootstrap.py"), str(staged)]
    process = subprocess.run(command, cwd=staged, capture_output=True, text=True, timeout=30)
    if process.returncode != 0:
        raise PortableError("oracle subprocess failed: " + process.stderr[-2000:])
    try:
        result = json.loads(process.stdout)
        oracle = result["oracle"]
        matrix = oracle["matrix"]
        if (oracle["status"] != "PASS" or type(result["seed_resolver_calls"]) is not int
                or result["seed_resolver_calls"] != 0
                or matrix != {"cells": 128, "changed_cells": 80, "unchanged_cells": 48,
                              "changed_by_seat": {"0": 40, "1": 40},
                              "changed_by_actor": {"0": 40, "1": 40}}
                or oracle["boundaries"] != {"count": 5, "passed": [
                    "prior_product_place", "prior_drop", "prior_pickup_fail_closed",
                    "ambiguous_place_fail_closed", "disabled_identity"]}):
            raise PortableError("oracle result differs from the pinned contract")
    except (ValueError, KeyError, TypeError) as error:
        raise PortableError("malformed oracle result") from error
    return result


def run(root: Path, archives: list[Path], mode: str = "both") -> dict:
    if mode not in ("normal", "optimized", "both"):
        raise PortableError("unknown execution mode")
    root = root.resolve(strict=True)
    data = collect(root, archives)
    modes = (False, True) if mode == "both" else (mode == "optimized",)
    results = {}
    with tempfile.TemporaryDirectory(prefix="titan-b7-portable-") as directory:
        staged = Path(directory)
        if staged.is_relative_to(root):
            raise PortableError("temporary directory must be outside the source root")
        for relative, payload in data.items():
            path = staged / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        (staged / "bootstrap.py").write_text(BOOTSTRAP, encoding="utf-8")
        for optimized in modes:
            results["optimized" if optimized else "normal"] = execute(staged, optimized)
        for relative, payload in data.items():
            if (staged / relative).read_bytes() != payload:
                raise PortableError("staged input changed during execution")
    if collect(root, archives) != data:
        raise PortableError("input changed during execution")
    identical = results.get("normal") == results.get("optimized") if mode == "both" else None
    if identical is False:
        raise PortableError("normal/optimized result mismatch")
    return {"status": "PASS", "scope": "B7 component oracle only; unwired; no game-strength claim",
            "adapter": "unchanged AST-extracted official seed resolver in isolated child",
            "pins": dict(PINS), "runs": results, "normal_optimized_identical": identical}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    parser.add_argument("--mode", choices=("normal", "optimized", "both"), default="both")
    args = parser.parse_args(argv)
    try:
        result = run(args.root, args.artifact, args.mode)
    except (PortableError, OSError, ValueError, RuntimeError, zipfile.BadZipFile,
            subprocess.SubprocessError) as error:
        print(f"B7_PORTABLE_FAIL: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
