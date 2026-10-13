# SPDX-License-Identifier: Apache-2.0
"""2x2 causal ablation of submitted-V4's always-on SELL funding policy.

Evidence tooling only. Every arm starts from the exact submitted-V4 archive and
changes at most two source seams in ``frozen_selected.py``:

A. ``funded_minimum_now`` -> the submitted-V3.1 cash-vs-budget minimum rule.
B. disable post-materialization ``fund_same_turn_acquisition`` queue reordering.

This is not a V3.1 reconstruction and does not modify production V5.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

BASELINE_SHA256 = "4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b"
V31_SOURCE = "a90d888f03987ef0b35cfd20ec3519c6144db08a"
V4_SOURCE = "4af1113154e78c662780e6658cd920daac7902e3"

ARMS = ("control", "min_v31", "no_reorder", "funding_pair_v31")
ARM_AXES = {
    "control": {"legacy_minimum": False, "disable_reorder": False},
    "min_v31": {"legacy_minimum": True, "disable_reorder": False},
    "no_reorder": {"legacy_minimum": False, "disable_reorder": True},
    "funding_pair_v31": {"legacy_minimum": True, "disable_reorder": True},
}

_MINIMUM_TARGET = b"""            minimum,funding=funded_minimum_now(obs,config,base,farm,private,route,item_end,
                                                current,targets,item)
            funding['nominal_future_spend']=item_budget
            self.diagnostics.setdefault('funding_certificates',{})[item]=funding
"""
_MINIMUM_REPLACEMENT = b"""            minimum=current[item] if farm['money']<item_budget else 0
            funding={'mode':'v31-minimum-evidence-ablation',
                     'baseline_now':current[item],'minimum_now':minimum,
                     'nominal_future_spend':item_budget}
            self.diagnostics.setdefault('funding_certificates',{})[item]=funding
"""
_REORDER_TARGET = b"""        out['market'],funding=fund_same_turn_acquisition(
            out['market'],farm,private,obs['market'],shops,config,now,targets,
            lambda product:self.rival_supply(obs,product))
        if funding is not None:self.diagnostics['same_turn_funding']=funding
"""
_REORDER_REPLACEMENT = b"""        funding=None  # evidence-only: disable V4 same-turn SELL queue reordering
"""
_MINIMUM_PROVIDER = b"def funded_minimum_now(obs, config, base, farm, private, route, end,"
_REORDER_PROVIDER = b"def fund_same_turn_acquisition("


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture_exact_archive(path: Path) -> bytes:
    """Read the submitted-V4 archive once and authenticate those exact bytes."""
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


def _require_surface(members: dict[str, bytes]) -> bytes:
    if not isinstance(members, dict) or not members:
        raise ValueError("Archive member map must be a non-empty dict")
    for name in ("main.py", "frozen_selected.py"):
        if name not in members or type(members[name]) is not bytes:
            raise ValueError(f"Exact V4 archive is missing byte member: {name}")
    frozen = members["frozen_selected.py"]
    checks = (
        (_MINIMUM_TARGET, "funded-minimum callsite"),
        (_REORDER_TARGET, "same-turn funding callsite"),
        (_MINIMUM_PROVIDER, "funded-minimum provider"),
        (_REORDER_PROVIDER, "same-turn funding provider"),
    )
    for needle, label in checks:
        if frozen.count(needle) != 1:
            raise ValueError(f"Exact V4 {label} drifted")
    return frozen


def ablate(members: dict[str, bytes], *, legacy_minimum: bool,
           disable_reorder: bool) -> tuple[dict[str, bytes], dict]:
    """Build one arm while preserving archive membership and all other bytes."""
    before = _require_surface(members)
    after = before
    applied = []

    if legacy_minimum:
        after = after.replace(_MINIMUM_TARGET, _MINIMUM_REPLACEMENT, 1)
        applied.append("legacy_minimum")
    if disable_reorder:
        after = after.replace(_REORDER_TARGET, _REORDER_REPLACEMENT, 1)
        applied.append("disable_reorder")

    candidate = dict(members)
    candidate["frozen_selected.py"] = after
    if set(candidate) != set(members):
        raise AssertionError("Funding-policy ablation changed archive membership")
    changed = [name for name in members if candidate[name] != members[name]]
    expected = [] if not applied else ["frozen_selected.py"]
    if changed != expected:
        raise AssertionError(f"Funding-policy ablation changed unexpected members: {changed}")

    if legacy_minimum:
        if after.count(_MINIMUM_TARGET) != 0 or after.count(_MINIMUM_REPLACEMENT) != 1:
            raise AssertionError("Legacy-minimum replacement failed")
    else:
        if after.count(_MINIMUM_TARGET) != 1:
            raise AssertionError("Control arm lost V4 funded-minimum callsite")
    if disable_reorder:
        if after.count(_REORDER_TARGET) != 0 or after.count(_REORDER_REPLACEMENT) != 1:
            raise AssertionError("Same-turn funding replacement failed")
    else:
        if after.count(_REORDER_TARGET) != 1:
            raise AssertionError("Control arm lost V4 same-turn funding callsite")

    receipt = {
        "schema": "astra.v5.v4-funding-policy-ablation.v1",
        "baseline_archive_sha256": BASELINE_SHA256,
        "v31_source": V31_SOURCE,
        "v4_source": V4_SOURCE,
        "axes": {
            "legacy_minimum": bool(legacy_minimum),
            "disable_reorder": bool(disable_reorder),
        },
        "changed_members": changed,
        "baseline_frozen_selected_sha256": sha256_bytes(before),
        "candidate_frozen_selected_sha256": sha256_bytes(after),
        "semantic_delta": (
            "submitted-V4 funding policy 2x2 only; no seller objective, joint-plan, "
            "feature-flag, runtime, config, or archive-membership changes"
        ),
    }
    return candidate, receipt


def build_arms(members: dict[str, bytes]) -> tuple[dict[str, dict[str, bytes]], dict[str, dict]]:
    """Return the complete 2x2 arm matrix and immutable source receipts."""
    _require_surface(members)
    payloads = {}
    receipts = {}
    for arm in ARMS:
        axes = ARM_AXES[arm]
        payload, receipt = ablate(members, **axes)
        payloads[arm] = payload
        receipts[arm] = {"arm": arm, **receipt}
    return payloads, receipts
