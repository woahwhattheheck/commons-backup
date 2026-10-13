# SPDX-License-Identifier: Apache-2.0
"""Render, but never apply, the measured TITAN performance-consumer patch.

The composer is source-bound to the current funded-payback successor. It copies
only the five canonical target files into a temporary tree, applies the already
landed QUICKSTEP/PULSE/worker-trace deltas there, and emits an exact unified diff
plus a machine receipt. Canonical files are never written by this tool.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterable

CURRENT_ARCHIVE = "499989ab907331d4c0c990af2ab3703e6731dc83078964aca8563ea5a069e48e"
CURRENT_BYTES = 313471
CURRENT_RUNTIME_FILES = 83
CURRENT_SOURCE = "6350d80c2dc211e803da7741bba5f6b95b770e96827d65bb1343655754f25133"

TARGET_BLOBS = {
    "revenue/kaggriculture/cloud-execution-lab/frozen_selected.py": "58fde0ad70cbec2c653c7383a6c2835e6726423a",
    "revenue/kaggriculture/cloud-execution-lab/scheduler.py": "97085acebd7268e87a09e4b5c1bf7d049038cb25",
    "revenue/kaggriculture/cloud-execution-lab/reference/integrated-selected/alder/seed_budget.py": "ef21710d6275a7146854b0fde46f00beb2dcb372",
    "revenue/kaggriculture/cloud-execution-lab/reference/titan-current/deadline_adapter.py": "184ff5354451d764df95ffb5c952eecd0f4266f0",
    "revenue/kaggriculture/cloud-execution-lab/build_integrated.py": "8ca5fcae2f49a14f1dc166ed8c1ca391a350e081",
}

HELPER_BLOBS = {
    "revenue/kaggriculture/cloud-quickstep/seller_snapshot.py": "58ac31dada1c35b6dbaaaeef29fd83a0e52481ab",
    "revenue/kaggriculture/cloud-quickstep/frozen_selected.integration.patch": "26682068bc43e817d50fdabbb9ab07850d1d5c48",
    "revenue/kaggriculture/cloud-runtime-pulse/observed_clone.py": "f810d53193d3035655a36c21021e18ba1d415916",
    "revenue/kaggriculture/cloud-runtime-pulse/plant_suffix.py": "95d05ff28aa79074d82bdc08ce4148d3ace1b13d",
    "revenue/kaggriculture/cloud-worker-trace/worker-trace-lines.patch": "623fdec3859586f5dfab6f3597d868eaa2e1aad8",
}

POINTER = "revenue/kaggriculture/cloud-execution-lab/runtime/integrated-selected/CURRENT-ARCHIVE.json"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{path}: expected one replacement site, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def _verify_blob(repo: Path, rel: str, expected: str) -> None:
    data = (repo / rel).read_bytes()
    actual = git_blob_sha(data)
    if actual != expected:
        raise ValueError(f"{rel}: expected Git blob {expected}, found {actual}")


def verify_source(repo: Path) -> dict:
    pointer = json.loads((repo / POINTER).read_text(encoding="utf-8"))
    expected_pointer = {
        "sha256": CURRENT_ARCHIVE,
        "bytes": CURRENT_BYTES,
        "runtime_files": CURRENT_RUNTIME_FILES,
        "source_manifest_sha256": CURRENT_SOURCE,
    }
    for key, expected in expected_pointer.items():
        if pointer.get(key) != expected:
            raise ValueError(f"CURRENT {key}: expected {expected!r}, found {pointer.get(key)!r}")
    for rel, expected in TARGET_BLOBS.items():
        _verify_blob(repo, rel, expected)
    for rel, expected in HELPER_BLOBS.items():
        _verify_blob(repo, rel, expected)
    return pointer


def _copy_targets(repo: Path, scratch: Path) -> None:
    for rel in TARGET_BLOBS:
        src = repo / rel
        dst = scratch / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def _git_apply(scratch: Path, patch: Path, *, directory: str | None = None) -> None:
    command = ["git", "apply", "--check"]
    if directory:
        command.append(f"--directory={directory}")
    command.append(str(patch))
    subprocess.run(command, cwd=scratch, check=True, capture_output=True, text=True)
    command = ["git", "apply", "--unsafe-paths"]
    if directory:
        command.append(f"--directory={directory}")
    command.append(str(patch))
    subprocess.run(command, cwd=scratch, check=True, capture_output=True, text=True)


def compose_tree(repo: Path, scratch: Path) -> None:
    _copy_targets(repo, scratch)
    quickstep = repo / "revenue/kaggriculture/cloud-quickstep/frozen_selected.integration.patch"
    _git_apply(scratch, quickstep, directory="revenue/kaggriculture/cloud-execution-lab")
    worker = repo / "revenue/kaggriculture/cloud-worker-trace/worker-trace-lines.patch"
    _git_apply(scratch, worker)

    scheduler = scratch / "revenue/kaggriculture/cloud-execution-lab/scheduler.py"
    _replace_once(
        scheduler,
        "import mechanics as m\n",
        "import mechanics as m\nfrom observed_clone import detached_json_value\n",
    )
    _replace_once(
        scheduler,
        "    farm, private = copy.deepcopy(obs['farms'][obs['player']]), copy.deepcopy(obs['private'])\n",
        "    farm = detached_json_value(obs['farms'][obs['player']])\n"
        "    private = detached_json_value(obs['private'])\n",
    )

    seed = scratch / "revenue/kaggriculture/cloud-execution-lab/reference/integrated-selected/alder/seed_budget.py"
    _replace_once(seed, "from collections import Counter\n", "from plant_suffix import immutable_plant_suffixes\n")
    old_suffix = '''    for name, route in routes.items():\n        suffix = [Counter() for _ in range(len(route) + 1)]\n        for t in range(len(route) - 1, -1, -1):\n            suffix[t] = suffix[t + 1].copy()\n            row = route[t]\n            for action in [row.get("farmer", []), *row.get("hands", [])]:\n                if len(action) >= 2 and action[0] == "PLANT":\n                    suffix[t][action[1]] += 1\n        suffixes[name] = tuple(MappingProxyType(dict(c)) for c in suffix)\n'''
    new_suffix = '''    for name, route in routes.items():\n        suffixes[name] = immutable_plant_suffixes(route)\n'''
    _replace_once(seed, old_suffix, new_suffix)

    builder = scratch / "revenue/kaggriculture/cloud-execution-lab/build_integrated.py"
    anchor = "    mapping={p:p for p in RUNTIME if p not in ('integrated_main.py','integrated_parent.py')}\n"
    _replace_once(
        builder,
        anchor,
        anchor
        + "    mapping['seller_snapshot.py']='../cloud-quickstep/seller_snapshot.py'\n"
        + "    mapping['observed_clone.py']='../cloud-runtime-pulse/observed_clone.py'\n"
        + "    mapping['plant_suffix.py']='../cloud-runtime-pulse/plant_suffix.py'\n",
    )


def _diff_one(repo: Path, scratch: Path, rel: str) -> str:
    before = (repo / rel).read_text(encoding="utf-8").splitlines(keepends=True)
    after = (scratch / rel).read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(difflib.unified_diff(before, after, fromfile=f"a/{rel}", tofile=f"b/{rel}"))


def render_plan(repo: Path) -> tuple[str, dict]:
    repo = repo.resolve()
    pointer = verify_source(repo)
    before_fingerprint = {rel: sha256((repo / rel).read_bytes()) for rel in TARGET_BLOBS}
    with tempfile.TemporaryDirectory(prefix="titan-perf-consumer-") as tmp:
        scratch = Path(tmp)
        compose_tree(repo, scratch)
        patch = "".join(_diff_one(repo, scratch, rel) for rel in TARGET_BLOBS)
        after = {}
        for rel in TARGET_BLOBS:
            data = (scratch / rel).read_bytes()
            after[rel] = {"git_blob": git_blob_sha(data), "sha256": sha256(data), "bytes": len(data)}
            if rel.endswith(".py"):
                compile(data, rel, "exec")
    after_fingerprint = {rel: sha256((repo / rel).read_bytes()) for rel in TARGET_BLOBS}
    if before_fingerprint != after_fingerprint:
        raise RuntimeError("composer mutated canonical source")
    receipt = {
        "operation": "titan-current-perf-consumer-20260908-01",
        "current": pointer,
        "targets": {rel: {"base_git_blob": TARGET_BLOBS[rel], **after[rel]} for rel in TARGET_BLOBS},
        "helpers": HELPER_BLOBS,
        "patch_sha256": sha256(patch.encode()),
        "patch_bytes": len(patch.encode()),
        "canonical_mutated": False,
        "expected_runtime_files_after_canonical_build": CURRENT_RUNTIME_FILES + 3,
    }
    return patch, receipt


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    patch, receipt = render_plan(args.repo)
    if args.output:
        args.output.write_text(patch, encoding="utf-8")
    else:
        print(patch, end="")
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
