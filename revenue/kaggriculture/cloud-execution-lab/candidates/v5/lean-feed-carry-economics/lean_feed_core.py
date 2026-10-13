#!/usr/bin/env python3
"""TITAN V5 paired lean-feed carry economics oracle and promotion gate.

Research-only and fail-closed: this module never imports or mutates a gameplay
policy. It recomputes MIN_PROVABLE from public state, distinguishes owned feed
from fresh purchase cost, and promotes a lean candidate only when liberated cash
is explicitly redeployed without an obligation/productivity loss.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "titan-v5-lean-feed-carry-economics-v1"
REPORT_SCHEMA = "titan-v5-lean-feed-carry-report-v1"
MANIFEST_SCHEMA = "titan-v5-lean-feed-carry-manifest-v1"
D2_ARCHIVE_SHA256 = "3d250d7bd32bf51f26ec1f69c2c10bc3c914e7d0cf64a078ae5bac5832465bd8"
D2_MEMBER_COUNT = 94
D2_RUNTIME_MEMBER = "titan_runtime.py"
D2_HOSTED_PYTHON = "3.12.13"

ARM_MIN = "MIN_PROVABLE"
ARM_CURRENT = "CURRENT_POLICY"
ARM_PLUS = "PLUS_ONE"
ARMS = (ARM_MIN, ARM_CURRENT, ARM_PLUS)
SEATS = (1, 2)
SPLITS = ("dev", "holdout")
CURRENT_POLICY = {"Corn": 2, "Pasture": 5, "Straw": 1}
PLUS_ONE = {feed: qty + 1 for feed, qty in CURRENT_POLICY.items()}
ALLOWED_CASH_USE = frozenset({"animal", "fertilizer", "hire", "land", "seed", "water", "other_game_action"})


class EvidenceError(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise EvidenceError(message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value: Any, label: str, *, nonnegative: bool = True) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label} must be numeric")
    value = float(value)
    _require(math.isfinite(value), f"{label} must be finite")
    if nonnegative:
        _require(value >= 0, f"{label} must be non-negative")
    return value


def _int_map(value: Any, label: str, feeds: Iterable[str] | None = None) -> dict[str, int]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    result: dict[str, int] = {}
    for key, qty in value.items():
        _require(isinstance(key, str) and key, f"{label} contains invalid feed")
        _require(_is_int(qty) and qty >= 0, f"{label}.{key} must be a non-negative integer")
        result[key] = qty
    if feeds is not None:
        _require(set(result) == set(feeds), f"{label} feed set mismatch")
    return dict(sorted(result.items()))


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _simulate_purchase(
    request: Mapping[str, int], market: Mapping[str, Mapping[str, Any]], order: Sequence[str], cash: float
) -> dict[str, Any]:
    remaining = cash
    executable: dict[str, int] = {feed: 0 for feed in order}
    authored_rows = 0
    executable_rows = 0
    for feed in order:
        wanted = request[feed]
        if wanted > 0:
            authored_rows += 1
        row = market[feed]
        available = row["available"]
        action_cap = row["action_cap"]
        price = row["unit_price"]
        affordable = int(remaining // price) if price > 0 else wanted
        bought = min(wanted, available, action_cap, affordable)
        executable[feed] = bought
        if bought > 0:
            executable_rows += 1
        remaining -= bought * price
    return {
        "authored": dict(request),
        "executable": executable,
        "authored_rows": authored_rows,
        "executable_rows": executable_rows,
        "fresh_cost": cash - remaining,
        "cash_after": remaining,
    }


def compute_reserve_oracle(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Compute MIN_PROVABLE and bounded comparators from public/current state.

    Only source-proven, executable obligations at the next boundary count. Feed
    already on hand satisfies obligations before any fresh purchase is valued.
    """
    _require(isinstance(snapshot, Mapping), "snapshot must be an object")
    owned = _int_map(snapshot.get("feed_on_hand"), "feed_on_hand", CURRENT_POLICY)
    cash = _number(snapshot.get("cash"), "cash")
    order = snapshot.get("purchase_order")
    _require(isinstance(order, list) and set(order) == set(CURRENT_POLICY) and len(order) == len(CURRENT_POLICY), "purchase_order must contain every feed exactly once")
    _require(len(order) == len(set(order)), "purchase_order contains duplicates")
    current_authored = _int_map(snapshot.get("current_authored"), "current_authored", CURRENT_POLICY)
    _require(current_authored == dict(sorted(CURRENT_POLICY.items())), "current_authored differs from pinned policy")

    raw_market = snapshot.get("market")
    _require(isinstance(raw_market, Mapping) and set(raw_market) == set(CURRENT_POLICY), "market feed set mismatch")
    market: dict[str, dict[str, Any]] = {}
    for feed in sorted(CURRENT_POLICY):
        row = raw_market[feed]
        _require(isinstance(row, Mapping), f"market.{feed} must be an object")
        available = row.get("available")
        action_cap = row.get("action_cap")
        _require(_is_int(available) and available >= 0, f"market.{feed}.available invalid")
        _require(_is_int(action_cap) and action_cap >= 0, f"market.{feed}.action_cap invalid")
        price = _number(row.get("unit_price"), f"market.{feed}.unit_price")
        _require(price > 0, f"market.{feed}.unit_price must be positive")
        market[feed] = {"available": available, "action_cap": action_cap, "unit_price": price}

    obligations = snapshot.get("obligations")
    _require(isinstance(obligations, list), "obligations must be a list")
    proven: list[dict[str, Any]] = []
    for index, raw in enumerate(obligations):
        _require(isinstance(raw, Mapping), f"obligations[{index}] invalid")
        feed = raw.get("feed")
        units = raw.get("units")
        boundary = raw.get("boundary_step")
        _require(feed in CURRENT_POLICY, f"obligations[{index}].feed invalid")
        _require(_is_int(units) and units > 0, f"obligations[{index}].units invalid")
        _require(_is_int(boundary) and boundary >= 0, f"obligations[{index}].boundary_step invalid")
        if raw.get("source_proven") is True and raw.get("executable") is True:
            source = raw.get("source")
            _require(isinstance(source, str) and source, f"obligations[{index}].source required")
            proven.append({"feed": feed, "units": units, "boundary_step": boundary, "source": source})

    next_boundary = min((row["boundary_step"] for row in proven), default=None)
    due = {feed: 0 for feed in sorted(CURRENT_POLICY)}
    due_sources: list[dict[str, Any]] = []
    if next_boundary is not None:
        for row in proven:
            if row["boundary_step"] == next_boundary:
                due[row["feed"]] += row["units"]
                due_sources.append(row)
    owned_applied = {feed: min(owned[feed], due[feed]) for feed in due}
    min_fresh = {feed: max(0, due[feed] - owned_applied[feed]) for feed in due}

    arms = {
        ARM_MIN: _simulate_purchase(min_fresh, market, order, cash),
        ARM_CURRENT: _simulate_purchase(current_authored, market, order, cash),
        ARM_PLUS: _simulate_purchase(PLUS_ONE, market, order, cash),
    }
    current_exec = arms[ARM_CURRENT]["executable"]
    min_exec = arms[ARM_MIN]["executable"]
    min_satisfies = all(owned[feed] + min_exec[feed] >= due[feed] for feed in due)
    subset_only = all(min_exec[feed] <= current_exec[feed] for feed in due)
    removed = {feed: max(0, current_exec[feed] - min_exec[feed]) for feed in due}
    cash_liberated = sum(removed[feed] * market[feed]["unit_price"] for feed in removed)
    safe_to_lean = min_satisfies and subset_only
    seam = safe_to_lean and any(removed.values())
    cash_tied = cash_liberated if seam else 0.0

    result = {
        "next_boundary_step": next_boundary,
        "source_bound_obligations": due,
        "obligation_sources": sorted(due_sources, key=lambda row: (row["feed"], row["source"])),
        "feed_on_hand": owned,
        "owned_feed_applied": owned_applied,
        "min_provable_fresh": min_fresh,
        "market": market,
        "purchase_order": list(order),
        "cash_at_boundary": cash,
        "arms": arms,
        "min_satisfies_obligations": min_satisfies,
        "min_is_subset_of_current": subset_only,
        "safe_to_lean": safe_to_lean,
        "reachable_excess": seam,
        "units_removed": removed if seam else {feed: 0 for feed in removed},
        "cash_tied_in_discretionary_feed": cash_tied,
    }
    result["oracle_sha256"] = sha256_json(result)
    return result


