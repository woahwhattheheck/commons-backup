# SPDX-License-Identifier: Apache-2.0
"""Prove the SELL-custody candidate through stripped private-runtime execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
KAG = LAB.parent
CANDIDATE = HERE / "candidate.py"
EVALUATOR = KAG / "cloud-eval" / "evaluate.py"
LOADER = KAG / "20260907-offline-agent" / "evaluate.py"
ENGINE = LAB / "reference" / "engine"

EXPECTED_ARCHIVE_SHA256 = "17f536087b3a6baf4ae1222a051285766a3ea8c2ca5af6edc190d4f527e12b86"
EXPECTED_RUNTIME_FILES = 109
EXPECTED_CONSUMER = "ExecutableSellCustodyFrozenSelected"
EXPECTED_MARKER = "_sol_pro_executable_sell_custody_v1"
EXPECTED_EVALUATOR_GIT_BLOB = "077feb2208b6e0c1727835eb4f8089709bf67f3b"
EXPECTED_LOADER_GIT_BLOB = "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5"
SEED = 2611092217
EPISODE_STEPS = 4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def minimal_environment(home: Path) -> dict[str, str]:
    return {
        "PATH": os.defpath,
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def completed(command: list[str], *, cwd: Path, env: dict[str, str], timeout: float):
    result = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"isolated command failed (rc={result.returncode})\n"
            f"stdout tail:\n{result.stdout[-4000:]}\n"
            f"stderr tail:\n{result.stderr[-4000:]}"
        )
    return result


def fresh_private_runtime_smoke() -> dict[str, Any]:
    probe = r"""
import importlib.util
import json
from pathlib import Path
import sys

path = Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(path.parent))
name = "_sol_pro_sell_custody_fresh_candidate"
spec = importlib.util.spec_from_file_location(name, path)
if spec is None or spec.loader is None:
    raise RuntimeError("candidate spec unavailable")
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
spec.loader.exec_module(module)
config = json.loads((module._ARENA_ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
instance = module._candidate_new_instance(module._ARENA_ROOT, config)
instance._initialize()
import frozen_selected
import observed_clone
import scheduler
import titan_runtime

arena = module._ARENA_ROOT.resolve()
def inside(value):
    path = Path(value).resolve()
    try:
        path.relative_to(arena)
        return True
    except ValueError:
        return False

receipt = module.install_receipt() or {}
consumer_type = type(instance.consumer)
payload = {
    "consumer_type": consumer_type.__name__,
    "consumer_module": consumer_type.__module__,
    "patch_marker": bool(getattr(consumer_type, "_sol_pro_executable_sell_custody_v1", None)),
    "factor": receipt.get("factor"),
    "patch_git_blob": receipt.get("patch_git_blob"),
    "archive_sha256": (receipt.get("private_runtime") or {}).get("archive_sha256"),
    "runtime_files": (receipt.get("private_runtime") or {}).get("runtime_files"),
    "archive_members": (receipt.get("private_runtime") or {}).get("archive_members"),
    "origins_inside_private_arena": {
        "frozen_selected": inside(frozen_selected.__file__),
        "scheduler": inside(scheduler.__file__),
        "observed_clone": inside(observed_clone.__file__),
        "titan_runtime": inside(titan_runtime.__file__),
    },
    "ambient_lab_on_sys_path": str(module.LAB.resolve()) in sys.path,
}
print(json.dumps(payload, sort_keys=True, allow_nan=False))
"""
    with tempfile.TemporaryDirectory(prefix="sell-custody-init-") as raw:
        home = Path(raw).resolve()
        result = completed(
            [sys.executable, "-I", "-B", "-c", probe, str(CANDIDATE.resolve())],
            cwd=home,
            env=minimal_environment(home),
            timeout=60,
        )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"fresh-process probe emitted {len(lines)} nonempty lines")
    receipt = json.loads(lines[0])
    if receipt.get("consumer_type") != EXPECTED_CONSUMER:
        raise RuntimeError(f"patched consumer was not instantiated: {receipt}")
    if receipt.get("patch_marker") is not True:
        raise RuntimeError("SELL-custody marker missing")
    if receipt.get("factor") != "engine-inactive market suffix quarantine":
        raise RuntimeError("SELL-custody factor receipt mismatch")
    if receipt.get("archive_sha256") != EXPECTED_ARCHIVE_SHA256:
        raise RuntimeError("private archive identity mismatch")
    if receipt.get("runtime_files") != EXPECTED_RUNTIME_FILES:
        raise RuntimeError("private runtime cardinality mismatch")
    if receipt.get("archive_members") != EXPECTED_RUNTIME_FILES + 1:
        raise RuntimeError("private archive-member cardinality mismatch")
    origins = receipt.get("origins_inside_private_arena")
    if not isinstance(origins, dict) or set(origins.values()) != {True}:
        raise RuntimeError(f"runtime import escaped private arena: {origins}")
    if receipt.get("ambient_lab_on_sys_path") is not False:
        raise RuntimeError("candidate depended on mutable repository lab path")
    return receipt


def evaluator_smoke() -> dict[str, Any]:
    if git_blob_sha1(EVALUATOR) != EXPECTED_EVALUATOR_GIT_BLOB:
        raise RuntimeError("pinned evaluator source drift")
    if git_blob_sha1(LOADER) != EXPECTED_LOADER_GIT_BLOB:
        raise RuntimeError("pinned loader source drift")
    with tempfile.TemporaryDirectory(prefix="sell-custody-evaluator-") as raw:
        home = Path(raw).resolve()
        output = home / "EVALUATOR-SMOKE.json"
        result = completed(
            [
                sys.executable,
                "-B",
                str(EVALUATOR.resolve()),
                "--engine-dir",
                str(ENGINE.resolve()),
                "--loader",
                str(LOADER.resolve()),
                "--candidate",
                str(CANDIDATE.resolve()) + "::agent",
                "--opponent",
                "starter=official_starter",
                "--seeds",
                str(SEED),
                "--rng-seed",
                "20260910",
                "--action-timeout",
                "1.0",
                "--startup-timeout",
                "15",
                "--game-timeout",
                "60",
                "--episode-steps",
                str(EPISODE_STEPS),
                "--output",
                str(output),
            ],
            cwd=home,
            env=minimal_environment(home),
            timeout=180,
        )
        if not output.is_file():
            raise RuntimeError("pinned evaluator produced no report")
        report = json.loads(output.read_text(encoding="utf-8"))

    progress = report.get("progress") or {}
    games = report.get("games")
    if report.get("schema_version") != 1 or progress.get("state") != "complete":
        raise RuntimeError("pinned evaluator did not complete")
    if report.get("candidate", {}).get("sha256") != sha256_file(CANDIDATE):
        raise RuntimeError("candidate entry digest mismatch")
    if not isinstance(games, list) or len(games) != 2:
        raise RuntimeError("expected one seed in both candidate seats")

    seen = set()
    normalized = []
    for game in games:
        seat = game.get("candidate_seat")
        scores = game.get("scores")
        actors = game.get("actors")
        if seat not in (0, 1) or seat in seen:
            raise RuntimeError(f"invalid candidate seat: {seat!r}")
        seen.add(seat)
        if (
            game.get("status") != "complete"
            or game.get("failure") is not None
            or not isinstance(scores, list)
            or len(scores) != 2
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in scores
            )
            or not isinstance(actors, list)
            or len(actors) != 2
        ):
            raise RuntimeError(f"invalid evaluator game: {game}")
        actor = actors[seat]
        calls = actor.get("calls") if isinstance(actor, dict) else None
        if type(calls) is not int or calls != game.get("steps") or calls <= 0:
            raise RuntimeError(f"candidate failed action custody in seat {seat}")
        normalized.append(
            {
                "candidate_seat": seat,
                "steps": game["steps"],
                "calls": calls,
                "scores": scores,
                "exit_code": actor.get("exit_code"),
            }
        )
    if seen != {0, 1}:
        raise RuntimeError("both candidate seats were not exercised")
    return {
        "candidate_sha256": report["candidate"]["sha256"],
        "evaluator_sha256": report.get("evaluator_sha256"),
        "loader_sha256": report.get("loader_sha256"),
        "engine_sha256": report.get("engine_sha256"),
        "seed": SEED,
        "episode_steps": EPISODE_STEPS,
        "games": sorted(normalized, key=lambda row: row["candidate_seat"]),
        "stdout_summary_present": "SUMMARY " in result.stdout,
    }


def run() -> dict[str, Any]:
    for path in (CANDIDATE, EVALUATOR, LOADER, ENGINE / "kaggriculture.py"):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"smoke dependency is not a regular file: {path}")
    return {
        "schema_version": 1,
        "operation": "TITAN-V3-EXECUTABLE-SELL-CUSTODY-20260910-01",
        "scope": "private carrier and four-step execution; no gameplay-strength claim",
        "fresh_private_runtime": fresh_private_runtime_smoke(),
        "pinned_evaluator": evaluator_smoke(),
        "decision": "PASS",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    payload = json.dumps(run(), indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
