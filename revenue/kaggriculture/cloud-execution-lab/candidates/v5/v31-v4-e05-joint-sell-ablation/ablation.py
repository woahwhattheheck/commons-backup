# SPDX-License-Identifier: Apache-2.0
"""Exact submitted-V4 E05 joint-SELL ablation for causal evidence only.

This module does not implement a replacement seller. It takes the authenticated
submitted-V4 archive member map and disables only the E05 two-product composition
admission in ``frozen_selected.py``. The pre-existing per-product optimizer and
all later V4 source remain byte-identical.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

BASELINE_SHA256 = "4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b"
V31_SOURCE = "a90d888f03987ef0b35cfd20ec3519c6144db08a"
V4_SOURCE = "4af1113154e78c662780e6658cd920daac7902e3"
E05_PR = 11053

_TARGET = b"metrics=joint_plan_metrics([entry[2] for entry in pair])"
_REPLACEMENT = b"metrics=None  # evidence-only E05 joint-pair ablation"
_GATE = b"if ledger is None or metrics is None or metrics['worst_relative_gain']<=0:continue"
_IMPORT = b"from selected_sell_core import optimize_lot, joint_plan_metrics, shared_slot_ledger"
_PROVIDER = b"def joint_plan_metrics(infos):"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture_exact_archive(path: Path) -> bytes:
    """Read the baseline once and authenticate exactly those captured bytes."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Submitted-V4 baseline must be an ordinary file: {path}")
    raw = path.read_bytes()
    actual = sha256_bytes(raw)
    if actual != BASELINE_SHA256:
        raise ValueError(
            f"Baseline is not exact submitted V4; expected {BASELINE_SHA256}, got {actual}"
        )
    return raw


def _require_exact_e05_surface(members: dict[str, bytes]) -> None:
    if not isinstance(members, dict) or not members:
        raise ValueError("Archive member map must be a non-empty dict")
    for name in ("main.py", "frozen_selected.py", "selected_sell_core.py"):
        if name not in members or type(members[name]) is not bytes:
            raise ValueError(f"Exact V4 archive is missing byte member: {name}")
    frozen = members["frozen_selected.py"]
    core = members["selected_sell_core.py"]
    if frozen.count(_TARGET) != 1:
        raise ValueError("Exact V4 joint-plan admission callsite drifted")
    if frozen.count(_GATE) != 1:
        raise ValueError("Exact V4 joint-plan fail-closed gate drifted")
    if frozen.count(_IMPORT) != 1:
        raise ValueError("Exact V4 joint-plan import surface drifted")
    if core.count(_PROVIDER) != 1:
        raise ValueError("Exact V4 joint-plan metrics provider drifted")


def ablate_joint_sell(members: dict[str, bytes]) -> tuple[dict[str, bytes], dict]:
    """Return a V4 member map with only E05 two-product admission disabled.

    The exact call to ``joint_plan_metrics`` is replaced by ``metrics=None``.
    The immediately following incumbent guard therefore declines every two-plan
    candidate and leaves the already-computed single-product ``best`` path in
    charge. No member except ``frozen_selected.py`` may change.
    """
    _require_exact_e05_surface(members)
    candidate = dict(members)
    before = members["frozen_selected.py"]
    after = before.replace(_TARGET, _REPLACEMENT, 1)
    if after == before or after.count(_TARGET) != 0 or after.count(_REPLACEMENT) != 1:
        raise AssertionError("E05 ablation replacement failed")
    if after.count(_GATE) != 1:
        raise AssertionError("E05 ablation changed the incumbent pair gate")
    candidate["frozen_selected.py"] = after
    if set(candidate) != set(members):
        raise AssertionError("E05 ablation changed archive membership")
    changed = [name for name in members if candidate[name] != members[name]]
    if changed != ["frozen_selected.py"]:
        raise AssertionError(f"E05 ablation changed unexpected members: {changed}")
    receipt = {
        "schema": "astra.v5.v31-v4-e05-joint-sell-ablation.v1",
        "baseline_archive_sha256": BASELINE_SHA256,
        "v31_source": V31_SOURCE,
        "v4_source": V4_SOURCE,
        "historical_mechanism_pr": E05_PR,
        "changed_members": changed,
        "baseline_frozen_selected_sha256": sha256_bytes(before),
        "candidate_frozen_selected_sha256": sha256_bytes(after),
        "semantic_delta": "disable only E05 two-product joint-plan admission; retain V4 single-product optimizer",
    }
    return candidate, receipt
