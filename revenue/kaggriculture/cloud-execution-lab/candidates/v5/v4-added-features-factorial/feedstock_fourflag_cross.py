#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose the submitted-V4 feed-stock × four-feature causal interaction cross.

This is evidence tooling for the existing v4-added-features-factorial family.
It changes no production/default/archive pointer.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import sys
import types

BASELINE_SHA256 = "4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b"
FACTORIAL_REL = "cloud-execution-lab/candidates/v5/v4-added-features-factorial/paired.py"
FACTORIAL_GIT_BLOB = "198006f24936fe1ec8a6ac6d6d6cae015adf91cc"
FEED_STOCK_REL = "cloud-execution-lab/candidates/v5/v4-feed-stock-ablation/feed_stock_ablation.py"
FEED_STOCK_GIT_BLOB = "5dc273dcbfaf07d69b2ded7de672bfd003d7454d"
ARMS = ("v4", "feed_stock_off", "all_four_off", "both_off")
RUNTIME_MEMBER = "titan_runtime.py"
CONFIG_MEMBER = "TITAN-CONFIG.json"
STOCK_MEMBER = "operating_stock.py"


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def capture_git_blob(path: Path, expected: str, label: str) -> bytes:
    """Single-read an ordinary source file and authenticate those exact bytes."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be an ordinary file: {path}")
    raw = path.read_bytes()
    actual = git_blob_bytes(raw)
    if actual != expected:
        raise ValueError(f"{label} Git blob mismatch; expected {expected}, got {actual}")
    return raw


def load_captured(raw: bytes, origin: Path, name: str):
    """Execute only bytes already captured and authenticated by the caller."""
    if type(raw) is not bytes:
        raise TypeError("captured source must be bytes")
    module = types.ModuleType(name)
    module.__file__ = str(origin)
    module.__package__ = ""
    sys.modules[name] = module
    code = compile(raw, str(origin), "exec", dont_inherit=True)
    exec(code, module.__dict__)
    return module


def load_donors(kg_root: Path):
    """Load the exact two landed treatment authorities from captured source bytes."""
    root = Path(kg_root).resolve(strict=True)
    factorial_path = root / FACTORIAL_REL
    feed_path = root / FEED_STOCK_REL
    factorial_raw = capture_git_blob(factorial_path, FACTORIAL_GIT_BLOB, "factorial donor")
    feed_raw = capture_git_blob(feed_path, FEED_STOCK_GIT_BLOB, "feed-stock donor")
    factorial = load_captured(
        factorial_raw, factorial_path, "v5_feed_fourflag_factorial_donor"
    )
    feed_stock = load_captured(
        feed_raw, feed_path, "v5_feed_fourflag_feed_donor"
    )
    if getattr(factorial, "BASELINE_SHA256", None) != BASELINE_SHA256:
        raise ValueError("factorial donor baseline authority mismatch")
    if getattr(feed_stock, "BASELINE_SHA256", None) != BASELINE_SHA256:
        raise ValueError("feed-stock donor baseline authority mismatch")
    return factorial, feed_stock


def changed_members(control: dict[str, bytes], candidate: dict[str, bytes]) -> tuple[str, ...]:
    if set(control) != set(candidate):
        raise ValueError("arm changed archive membership")
    return tuple(sorted(path for path in control if control[path] != candidate[path]))


def compose_cross_arms(
    control: dict[str, bytes],
    feed_stock_off: dict[str, bytes],
    factorial,
) -> dict[str, dict[str, bytes]]:
    """Compose the exact aggregate 2×2 without inventing a third treatment."""
    feed_changed = changed_members(control, feed_stock_off)
    if feed_changed != (RUNTIME_MEMBER,):
        raise ValueError(f"feed-stock donor changed unexpected members: {feed_changed}")
    all_four_off = factorial.arm_members(control, "all_four_off")
    both_off = factorial.arm_members(feed_stock_off, "all_four_off")
    arms = {
        "v4": dict(control),
        "feed_stock_off": dict(feed_stock_off),
        "all_four_off": all_four_off,
        "both_off": both_off,
    }
    expected = {
        "v4": (),
        "feed_stock_off": (RUNTIME_MEMBER,),
        "all_four_off": (CONFIG_MEMBER,),
        "both_off": tuple(sorted((CONFIG_MEMBER, RUNTIME_MEMBER))),
    }
    for name, members in arms.items():
        actual = changed_members(control, members)
        if actual != expected[name]:
            raise AssertionError(f"{name} changed {actual}, expected {expected[name]}")
        if STOCK_MEMBER in control and members[STOCK_MEMBER] != control[STOCK_MEMBER]:
            raise AssertionError(f"{name} changed {STOCK_MEMBER}")
    if both_off[RUNTIME_MEMBER] != feed_stock_off[RUNTIME_MEMBER]:
        raise AssertionError("combined arm did not preserve exact feed-stock treatment bytes")
    if both_off[CONFIG_MEMBER] != all_four_off[CONFIG_MEMBER]:
        raise AssertionError("combined arm did not preserve exact four-feature treatment bytes")
    return arms


def exact_cross_arms(baseline_raw: bytes, factorial, feed_stock) -> dict[str, dict[str, bytes]]:
    """Build all four arms from the exact submitted-V4 archive capture."""
    if type(baseline_raw) is not bytes:
        raise TypeError("baseline archive capture must be bytes")
    if hashlib.sha256(baseline_raw).hexdigest() != BASELINE_SHA256:
        raise ValueError("baseline is not exact submitted V4")
    feed_arms = feed_stock.exact_v4_arms(baseline_raw)
    if set(feed_arms) != {"control", "feed_stock_off"}:
        raise ValueError("feed-stock donor arm contract drift")
    return compose_cross_arms(
        feed_arms["control"], feed_arms["feed_stock_off"], factorial
    )


def _number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return value


def interaction_contrast(values: dict[str, float]) -> dict[str, float]:
    """Return main/conditional effects and the 2×2 interaction contrast."""
    if set(values) != set(ARMS):
        raise ValueError(f"interaction values must contain exactly {ARMS}")
    c = _number(values["v4"], "v4")
    a = _number(values["feed_stock_off"], "feed_stock_off")
    b = _number(values["all_four_off"], "all_four_off")
    ab = _number(values["both_off"], "both_off")
    return {
        "feed_effect_flags_on": a - c,
        "fourflag_effect_feed_on": b - c,
        "feed_effect_flags_off": ab - b,
        "fourflag_effect_feed_off": ab - a,
        "joint_effect": ab - c,
        "interaction": ab - a - b + c,
    }


def summarize_interaction(cells: list[dict], value_key: str = "margins") -> dict:
    """Aggregate only complete four-arm cells, preserving opponent stratification."""
    opponents = sorted({
        cell.get("opponent") for cell in cells if isinstance(cell.get("opponent"), str)
    })
    result = {}
    for opponent in opponents:
        rows = [cell for cell in cells if cell.get("opponent") == opponent]
        contrasts = []
        for cell in rows:
            values = cell.get(value_key)
            if not isinstance(values, dict) or set(values) != set(ARMS):
                continue
            try:
                contrasts.append(interaction_contrast(values))
            except ValueError:
                continue
        keys = (
            "feed_effect_flags_on",
            "fourflag_effect_feed_on",
            "feed_effect_flags_off",
            "fourflag_effect_feed_off",
            "joint_effect",
            "interaction",
        )
        result[opponent] = {
            "cells": len(rows),
            "complete_cells": len(contrasts),
            **{
                f"mean_{key}": (
                    sum(item[key] for item in contrasts) / len(contrasts)
                    if contrasts else None
                )
                for key in keys
            },
        }
    return result
