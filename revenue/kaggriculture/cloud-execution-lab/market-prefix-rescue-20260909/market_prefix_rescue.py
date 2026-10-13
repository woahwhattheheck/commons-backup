# SPDX-License-Identifier: Apache-2.0
"""Conservatively rescue executable market orders stranded behind empty cap slots.

The Kaggriculture interpreter truncates each raw market list to
``maxMarketOrdersPerTurn`` before parsing orders.  An exact empty-list placeholder
inside that prefix therefore consumes one issued slot even though it parses as a
no-op.  This module performs one narrow, stable transformation:

* only exact ``[]`` placeholders may move;
* every non-empty value keeps its relative order and value;
* blanks must form a contiguous suffix of the live prefix so that already-live
  non-empty rows keep their absolute market indices (no cross-player retiming);
* a queue changes only when at least one structurally executable order from
  beyond the cap crosses into the executable prefix; and
* the input object is never mutated.

The function is deliberately observation-free.  It repairs queue transport; it
does not choose purchases, sales, quantities, or timing of already-live rows.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

CROPS = frozenset({"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"})
ANIMALS = frozenset({"GOOSE", "COW", "SHEEP"})
PRODUCTS = frozenset({
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
})
QUANTITY_OPS = frozenset({"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"})
ATOMIC_OPS = frozenset({"HIRE", "BUY_LAND"})


def _config_value(configuration: Any, key: str, default: Any) -> Any:
    """Read dict-like or Struct-like configuration without mutating it."""
    if configuration is None:
        return default
    if isinstance(configuration, Mapping):
        return configuration.get(key, default)
    return getattr(configuration, key, default)


def market_limit(configuration: Any = None) -> int:
    """Mirror the official engine's lower-bounded market cap."""
    try:
        return max(1, int(_config_value(configuration, "maxMarketOrdersPerTurn", 10)))
    except (TypeError, ValueError, OverflowError):
        # Invalid configuration is an engine-level failure.  The candidate must
        # not invent a replacement cap, so fail closed to the canonical default.
        return 10


def is_engine_executable_order(order: Any) -> bool:
    """Recognize orders that can reach an official engine operation handler.

    This is stricter than ``_parse_order`` only for item names: the official
    parser accepts an unknown item, then aborts it during execution.  Such a row
    is not evidence that compaction rescued useful work.
    """
    if not isinstance(order, list) or not order:
        return False
    op = order[0]
    if op in ATOMIC_OPS:
        return True
    if op not in QUANTITY_OPS or len(order) < 3:
        return False
    try:
        quantity = int(order[2])
    except (TypeError, ValueError, OverflowError):
        return False
    if quantity <= 0:
        return False
    if op == "BUY_SEED":
        return len(order) > 1 and order[1] in CROPS
    if op == "BUY_ANIMAL":
        return len(order) > 1 and order[1] in ANIMALS
    if op == "BUY_PRODUCT":
        return len(order) > 1 and order[1] in {"WHEAT", "FERTILIZER"}
    return len(order) > 1 and order[1] in PRODUCTS


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _blanks_form_prefix_suffix(blank_slots: list[int], prefix_len: int) -> bool:
    """True iff every blank occupies a trailing contiguous slot of the prefix."""
    if not blank_slots:
        return False
    n = len(blank_slots)
    expected = list(range(prefix_len - n, prefix_len))
    return blank_slots == expected


def rescue_market_prefix(action: Any, configuration: Any = None):
    """Return ``(action_or_copy, report)`` after one fail-closed stable packing.

    Exact empty lists that form a contiguous suffix of the live prefix are moved
    behind all non-empty market rows.  The edit is committed only when an
    executable row whose original index was outside the engine cap lands inside
    it.  Interior blanks are refused so that already-live non-empty rows keep
    their absolute indices and are not retimed against the opponent.
    """
    limit = market_limit(configuration)
    report = {
        "schema_version": 1,
        "changed": False,
        "reason": "ineligible",
        "max_market_orders": limit,
        "blank_prefix_slots": [],
        "rescued_orders": [],
        "prefix_executable_before": 0,
        "prefix_executable_after": 0,
    }
    if not isinstance(action, dict):
        report["reason"] = "action_not_object"
        return action, report
    market = action.get("market")
    if not isinstance(market, list):
        report["reason"] = "market_not_list"
        return action, report

    prefix_len = min(len(market), limit)
    prefix = market[:prefix_len]
    blank_slots = [index for index, order in enumerate(prefix) if order == []]
    report["blank_prefix_slots"] = blank_slots
    report["market_length"] = len(market)
    report["prefix_executable_before"] = sum(is_engine_executable_order(order) for order in prefix)
    if not blank_slots:
        report["reason"] = "no_exact_blank_in_prefix"
        return action, report
    if not _blanks_form_prefix_suffix(blank_slots, prefix_len):
        report["reason"] = "interior_blank_refused_to_avoid_retiming"
        return action, report

    tagged = list(enumerate(market))
    packed = [entry for entry in tagged if entry[1] != []]
    packed.extend(entry for entry in tagged if entry[1] == [])
    rescued = [
        {"from_index": old_index, "to_index": new_index, "order": deepcopy(order)}
        for new_index, (old_index, order) in enumerate(packed[:limit])
        if old_index >= limit and is_engine_executable_order(order)
    ]
    if not rescued:
        report["reason"] = "no_executable_tail_order_crosses_cap"
        return action, report

    packed_market = [deepcopy(order) for _, order in packed]
    output = deepcopy(action)
    output["market"] = packed_market
    report.update(
        changed=True,
        reason="rescued_executable_tail_order",
        rescued_orders=rescued,
        moved_blank_count=len(blank_slots),
        prefix_executable_after=sum(is_engine_executable_order(order) for order in packed_market[:limit]),
        market_sha256_before=_digest(market),
        market_sha256_after=_digest(packed_market),
    )
    return output, report
