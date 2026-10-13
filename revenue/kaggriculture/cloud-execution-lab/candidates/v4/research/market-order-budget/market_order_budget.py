#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound helpers for TITAN V4 market-order execution-budget audits.

The official Kaggriculture interpreter truncates each player's raw ``market``
queue to ``maxMarketOrdersPerTurn`` before parsing any order.  These helpers do
not reorder, compact, or execute orders; they only classify returned actions and
identify whether a future composer has an executable slot available.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

DEFAULT_CAP = 10
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"


def _cap(value: Any = DEFAULT_CAP) -> int:
    """Mirror the engine's ``max(1, int(value))`` cap normalization."""
    return max(1, int(value))


def _validate_row(row: Any, slot: int) -> None:
    if not isinstance(row, list):
        raise TypeError(f"market[{slot}] must be a list")
    if row and not isinstance(row[0], str):
        raise TypeError(f"market[{slot}][0] must be a string when present")


def analyze_action(action: dict[str, Any], cap: int = DEFAULT_CAP) -> dict[str, Any]:
    """Classify one raw returned action without changing it.

    ``structural_overflow`` means the raw queue contains rows that the engine
    never even parses. ``dropped_nonempty`` is the stronger witness that an
    authored order is silently unreachable. Empty rows still consume raw slot
    indices before the slice and therefore matter to future composition.
    """
    if not isinstance(action, dict):
        raise TypeError("action must be a dict")
    cap = _cap(cap)
    market = action.get("market", [])
    if market is None:
        market = []
    if not isinstance(market, list):
        raise TypeError("action['market'] must be a list")
    for slot, row in enumerate(market):
        _validate_row(row, slot)

    active_slots = [i for i, row in enumerate(market) if row]
    dropped = market[cap:]
    dropped_nonempty = [
        {"slot": cap + offset, "order": row}
        for offset, row in enumerate(dropped)
        if row
    ]
    executable_active_slots = [slot for slot in active_slots if slot < cap]
    first_empty = next((slot for slot, row in enumerate(market[:cap]) if not row), None)
    if first_empty is None and len(market) < cap:
        first_empty = len(market)

    return {
        "cap": cap,
        "raw_rows": len(market),
        "executable_rows": min(len(market), cap),
        "active_rows": len(active_slots),
        "executable_active_rows": len(executable_active_slots),
        "structural_overflow": len(market) > cap,
        "overflow_rows": max(0, len(market) - cap),
        "dropped_nonempty": dropped_nonempty,
        "dropped_nonempty_count": len(dropped_nonempty),
        "last_active_slot": max(active_slots) if active_slots else None,
        "last_executable_active_slot": max(executable_active_slots) if executable_active_slots else None,
        "admission_slot": first_empty,
        "has_admission_slot": first_empty is not None,
    }


def scan_actions(actions: Iterable[dict[str, Any]], cap: int = DEFAULT_CAP,
                 witness_limit: int = 24) -> dict[str, Any]:
    """Aggregate queue-budget evidence across a deterministic action sequence."""
    cap = _cap(cap)
    hist = Counter()
    active_hist = Counter()
    total = structural = dropped_nonempty_callbacks = no_headroom = 0
    dropped_nonempty_rows = 0
    max_rows = 0
    max_active_slot = None
    witnesses: list[dict[str, Any]] = []

    for step, action in enumerate(actions):
        row = analyze_action(action, cap)
        total += 1
        hist[str(row["raw_rows"])] += 1
        active_hist[str(row["active_rows"])] += 1
        max_rows = max(max_rows, row["raw_rows"])
        if row["last_active_slot"] is not None:
            max_active_slot = row["last_active_slot"] if max_active_slot is None else max(max_active_slot, row["last_active_slot"])
        structural += int(row["structural_overflow"])
        dropped_nonempty_callbacks += int(row["dropped_nonempty_count"] > 0)
        dropped_nonempty_rows += row["dropped_nonempty_count"]
        no_headroom += int(not row["has_admission_slot"])
        if len(witnesses) < witness_limit and (row["structural_overflow"] or not row["has_admission_slot"]):
            witnesses.append({
                "step": step,
                "raw_rows": row["raw_rows"],
                "active_rows": row["active_rows"],
                "dropped_nonempty": row["dropped_nonempty"],
                "admission_slot": row["admission_slot"],
            })

    return {
        "cap": cap,
        "callbacks": total,
        "raw_rows_histogram": dict(sorted(hist.items(), key=lambda kv: int(kv[0]))),
        "active_rows_histogram": dict(sorted(active_hist.items(), key=lambda kv: int(kv[0]))),
        "max_raw_rows": max_rows,
        "max_active_slot": max_active_slot,
        "structural_overflow_callbacks": structural,
        "dropped_nonempty_callbacks": dropped_nonempty_callbacks,
        "dropped_nonempty_rows": dropped_nonempty_rows,
        "no_admission_slot_callbacks": no_headroom,
        "witnesses": witnesses,
    }


def admission_slot(action: dict[str, Any], cap: int = DEFAULT_CAP) -> int | None:
    """Return a row index usable by a future composer without displacing an existing row.

    This is deliberately a *planning* primitive, not a mutator. Existing
    market-row indices are never changed by this package.
    """
    return analyze_action(action, cap)["admission_slot"]
