#!/usr/bin/env python3
"""Verify the fast-tape current-runtime transform after REBIND.

This is a source/custody proof only. It never writes titan_runtime.py, changes a
feature default, materializes a release package, or runs a game.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
CURRENT_RUNTIME = HERE.parents[4] / "titan_runtime.py"
REBIND_TRANSFORMER = HERE.parent / "module-cache-binding" / "repair_loader_binding.py"
PORT_TRANSFORMER = HERE / "port_current_runtime.py"

BASELINE_BLOB = "b952c9c228ecbde592bf3d2df01638677abb0d24"
CURRENT_BLOB = "6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0"
LEGACY_FAST_BLOB = "2b2bd80e3fa76c61139bdbfeaa58dc8a8987339a"
COMBINED_BLOB = "6472260d9aa82f1d6e4008afb24a2645bfb1226c"
COMBINED_SHA256 = "1c409b5fdf7942f31b37580987b10074aa231984edbe67e0080edfc31b65b0c5"
PORT_TRANSFORMER_BLOB = "4c7474062292feb25638ae0af5161e9d5382e6f5"
REBIND_TRANSFORMER_BLOB = "9d39ead6f905d009d1285eddde4e6b2132e63bec"
FOUNDATION_ARTIFACT_ID = 10175943272
FOUNDATION_ARCHIVE_SHA256 = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_exact(path: Path, name: str, expected_blob: str) -> ModuleType:
    data = path.read_bytes()
    require(git_blob(data) == expected_blob,
            f"{path.name} identity drift: {git_blob(data)}")
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(current_runtime: Path = CURRENT_RUNTIME,
           baseline_runtime: Path | None = None) -> dict[str, Any]:
    port = load_exact(PORT_TRANSFORMER, "_titan_v4_fast_port_rebind", PORT_TRANSFORMER_BLOB)
    rebind = load_exact(REBIND_TRANSFORMER, "_titan_v4_cache_rebind", REBIND_TRANSFORMER_BLOB)

    current = current_runtime.read_bytes()
    require(git_blob(current) == CURRENT_BLOB,
            f"current runtime drift: {git_blob(current)}")
    repaired_current, repaired_report = rebind.repair_source(current)
    require(repaired_current == current and repaired_report["changed"] is False,
            "live current runtime is not an exact REBIND fixed point")

    combined = port.transform(current, CURRENT_BLOB)
    require(git_blob(combined) == COMBINED_BLOB,
            f"combined Git blob drift: {git_blob(combined)}")
    require(hashlib.sha256(combined).hexdigest() == COMBINED_SHA256,
            "combined SHA-256 drift")
    compile(combined, "<fast-tape-after-rebind>", "exec")

    report: dict[str, Any] = {
        "schema": "titan-v4-fast-tape-rebind/v1",
        "decision_authority": False,
        "current_runtime_git_blob": CURRENT_BLOB,
        "fast_tape_output_git_blob": COMBINED_BLOB,
        "fast_tape_output_sha256": COMBINED_SHA256,
        "fast_tape_output_bytes": len(combined),
        "port_transformer_git_blob": PORT_TRANSFORMER_BLOB,
        "rebind_transformer_git_blob": REBIND_TRANSFORMER_BLOB,
        "rebind_fixed_point": True,
        "full_diamond_checked": False,
        "foundation_artifact_id": FOUNDATION_ARTIFACT_ID,
        "foundation_archive_sha256": FOUNDATION_ARCHIVE_SHA256,
        "scope": "source identity and transform commutation only",
        "runtime_promoted": False,
        "feature_enabled": False,
        "games_run": 0,
    }

    if baseline_runtime is not None:
        baseline = baseline_runtime.read_bytes()
        require(git_blob(baseline) == BASELINE_BLOB,
                f"baseline runtime drift: {git_blob(baseline)}")
        legacy_fast = port.transform(baseline, BASELINE_BLOB)
        require(git_blob(legacy_fast) == LEGACY_FAST_BLOB,
                f"legacy fast-tape output drift: {git_blob(legacy_fast)}")
        rebind_first, first_report = rebind.repair_source(baseline)
        require(first_report["changed"] is True and git_blob(rebind_first) == CURRENT_BLOB,
                "REBIND baseline edge drift")
        require(rebind_first == current,
                "artifact REBIND postimage does not equal live current runtime")
        fast_after_rebind = port.transform(rebind_first, CURRENT_BLOB)
        rebind_after_fast, second_report = rebind.repair_source(legacy_fast)
        require(second_report["changed"] is True,
                "legacy fast-tape output did not expose the reviewed loader preimage")
        require(fast_after_rebind == rebind_after_fast == combined,
                "REBIND and fast-tape transforms do not commute byte-for-byte")
        report.update(
            full_diamond_checked=True,
            baseline_runtime_git_blob=BASELINE_BLOB,
            legacy_fast_tape_git_blob=LEGACY_FAST_BLOB,
            rebind_then_fast_git_blob=git_blob(fast_after_rebind),
            fast_then_rebind_git_blob=git_blob(rebind_after_fast),
            transforms_commute=True,
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-runtime", type=Path, default=CURRENT_RUNTIME)
    parser.add_argument("--baseline-runtime", type=Path,
                        help="Optional exact b952 runtime extracted from artifact 10175943272")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.current_runtime, args.baseline_runtime),
                         sort_keys=True, indent=2 if args.pretty else None))
        return 0
    except (OSError, UnicodeError, ValueError, SyntaxError, TypeError) as error:
        parser.exit(2, f"{type(error).__name__}: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
