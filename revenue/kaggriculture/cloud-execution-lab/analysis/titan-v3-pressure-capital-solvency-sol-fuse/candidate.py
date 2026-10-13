# SPDX-License-Identifier: Apache-2.0
"""Exact-current TITAN with a final-pressure acquisition-solvency interlock.

This additive carrier does not edit canonical source.  It replaces only the
instance's existing ``_early_capital_selected`` composition hook so the same
canonical early-capital and pressure implementations run in the same order,
then compares their two already-produced actions with the stateless guard.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import MethodType
from typing import Any

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
KAG = LAB.parent
BASE_COMMIT = "2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb"
EXPECTED_BLOBS = {
    "main.py": "4a8cf7bcda1f0fea231a144692cb84a779a9e73e",
    "titan_runtime.py": "b952c9c228ecbde592bf3d2df01638677abb0d24",
    "early_capital.py": "9bb3a0da4359900abda69da4a5e9154adf0818cc",
    "../cloud-opponent-league/lark-responsive/pressure_priority.py":
        "7261674962d10fc8bc6af5ff73ff9212c40f61ad",
}

if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))


def _load(name: str, path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def source_receipt() -> dict[str, Any]:
    files = {}
    for relative, expected in EXPECTED_BLOBS.items():
        path = (LAB / relative).resolve()
        actual = _git_blob_sha1(path)
        files[relative] = {"path": str(path), "expected_git_blob": expected,
                           "actual_git_blob": actual, "bytes": path.stat().st_size}
    return {"base_commit": BASE_COMMIT, "files": files,
            "valid": all(row["actual_git_blob"] == row["expected_git_blob"]
                         for row in files.values())}


_SOURCE = source_receipt()
if not _SOURCE["valid"]:
    drift = {name: row for name, row in _SOURCE["files"].items()
             if row["actual_git_blob"] != row["expected_git_blob"]}
    raise RuntimeError(f"exact-current pressure/capital source drift: {drift}")

_CANONICAL = _load("_sol_fuse_current_main", LAB / "main.py")
_GUARD = _load("_sol_fuse_pressure_capital_guard", HERE / "pressure_capital_solvent.py")
_ORIGINAL_NEW_INSTANCE = _CANONICAL._new_instance
_LAST_REPORT: dict[str, Any] | None = None


def last_report() -> dict[str, Any] | None:
    return deepcopy(_LAST_REPORT)


def _install(instance):
    """Install once on one exact-current FinalPressureAgent instance."""
    if getattr(instance, "_sol_fuse_installed", False):
        return instance
    from titan_runtime import TitanAgent

    # Bind the exact superclass methods used by current main.FinalPressureAgent.
    # Calling the instance's original method here would already have discarded
    # the pre-pressure queue we need for a safe comparison.
    early_capital = TitanAgent._early_capital_selected.__get__(instance, type(instance))
    market_pressure = TitanAgent._market_pressure_selected.__get__(instance, type(instance))

    def early_capital_pressure_solvent(self, observation, configuration, selected):
        global _LAST_REPORT
        before_pressure = early_capital(observation, configuration, selected)
        if self.diagnostics.get("status") != "completed":
            _LAST_REPORT = {"changed": False, "accepted": True,
                            "reason": "noncompleted_action"}
            return before_pressure

        self._final_pressure_boundary = True
        try:
            after_pressure = market_pressure(observation, configuration, before_pressure)
        finally:
            self._final_pressure_boundary = False

        try:
            import mechanics
            returned, report = _GUARD.preserve_acquisition_solvency(
                mechanics, observation, configuration, before_pressure, after_pressure)
        except Exception as exc:
            # A guard failure cannot be allowed to replace the already-complete
            # stock/capital queue or consume canonical fallback state.
            returned = deepcopy(before_pressure)
            report = {"changed": after_pressure != before_pressure,
                      "accepted": False, "reason": "guard_error",
                      "error": f"{type(exc).__name__}: {exc}"[:500]}
        _LAST_REPORT = deepcopy(report)
        diagnostics = dict(getattr(self, "diagnostics", {}) or {})
        diagnostics["pressure_capital_solvency"] = deepcopy(report)
        self.diagnostics = diagnostics
        return returned

    instance._early_capital_selected = MethodType(early_capital_pressure_solvent, instance)
    instance._sol_fuse_installed = True
    return instance


def _new_instance(root, feature_data):
    return _install(_ORIGINAL_NEW_INSTANCE(root, feature_data))


_CANONICAL._new_instance = _new_instance


def agent(observation, configuration=None):
    global _LAST_REPORT
    _LAST_REPORT = None
    return _CANONICAL.agent(observation, configuration)
