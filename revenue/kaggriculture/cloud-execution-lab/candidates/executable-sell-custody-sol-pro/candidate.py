# SPDX-License-Identifier: Apache-2.0
"""Runnable TITAN V3 executable SELL-custody candidate.

This entry reuses the exact source-reviewed private archive carrier from closed
PR #11840, but replaces its not-yet-invoked install hook before canonical lazy
construction.  Only ``ExecutableSellCustodyFrozenSelected`` is installed.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
CARRIER = HERE / "carrier.py"
DORMANT_PATCH = HERE / "executable_receipt_profile.py"
PATCH = HERE / "executable_sell_custody.py"

EXPECTED_CARRIER_GIT_BLOB = "6cf5fa502e5f79dabbb1a95cf645558cb5c52bce"
EXPECTED_DORMANT_PATCH_GIT_BLOB = "8e984812e15a84db14ee7311b047e0c8483132da"
EXPECTED_PATCH_GIT_BLOB = "ff1b87b590fec4815bf7638f5aaa796edec0e3bc"


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _regular_exact(path: Path, expected: str, label: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"{label} is not a regular file: {path}")
    actual = git_blob_sha1(path)
    if actual != expected:
        raise RuntimeError(f"{label} drift: expected {expected}, got {actual}")
    return actual


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    return module


_CARRIER_BLOB = _regular_exact(CARRIER, EXPECTED_CARRIER_GIT_BLOB, "private carrier")
_DORMANT_PATCH_BLOB = _regular_exact(
    DORMANT_PATCH, EXPECTED_DORMANT_PATCH_GIT_BLOB, "carrier bootstrap patch"
)
_PATCH_BLOB = _regular_exact(PATCH, EXPECTED_PATCH_GIT_BLOB, "SELL-custody patch")

_CARRIER = _load("_sol_pro_sell_custody_carrier", CARRIER)
_PATCH_MODULE = _load("_sol_pro_executable_sell_custody_patch", PATCH)

if getattr(_CARRIER, "_LAST_INSTALL_RECEIPT", None) is not None:
    raise RuntimeError("private carrier was constructed before SELL-custody hook replacement")

# The carrier has already verified/materialized the exact canonical archive and
# loaded canonical main without constructing TITAN.  Its construction hook looks
# these globals up at call time, so replace them atomically before first action.
_CARRIER._install = _PATCH_MODULE.install
_CARRIER.actual_patch_blob = _PATCH_BLOB
_CARRIER._PATCH_MODULE = _PATCH_MODULE

LAB = _CARRIER.LAB
_ARENA_ROOT = _CARRIER._ARENA_ROOT
_ARENA_RECEIPT = _CARRIER._ARENA_RECEIPT
_CANONICAL = _CARRIER._CANONICAL


def _candidate_new_instance(root: Path, feature_data: dict[str, Any]):
    return _CARRIER._candidate_new_instance(root, feature_data)


def install_receipt() -> dict[str, Any] | None:
    value = getattr(_CARRIER, "_LAST_INSTALL_RECEIPT", None)
    return dict(value) if isinstance(value, dict) else None


def agent(observation, configuration=None):
    return _CARRIER.agent(observation, configuration)
