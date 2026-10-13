# SPDX-License-Identifier: Apache-2.0
"""Stable market-prefix transport repair for TITAN V3.

The pinned Kaggriculture interpreter slices the raw market queue to
``maxMarketOrdersPerTurn`` before parsing each row.  An exact ``[]`` inside that
prefix therefore consumes a transport slot even though it is a no-op.  This
module moves only exact blank rows, preserves every non-blank value and relative
order, and commits the edit only when a structurally executable tail order
crosses into the interpreter-visible prefix.

"Structurally executable" deliberately does not mean "realized".  Affordability,
stock, shed capacity, and all other live preconditions remain engine decisions.
The evidence carrier measures post-interpreter state separately.

Mechanism and original implementation credit: Commons PR #11616.  This version
is a fresh-current-main rebuild with fail-closed configuration handling and
separate realized-execution custody.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping, Optional

CROPS = frozenset({"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"})
ANIMALS = frozenset({"GOOSE", "COW", "SHEEP"})
PRODUCTS = frozenset(
    {
        "WHEAT",
        "CARROT",
        "TOMATO",
        "STRAWBERRY",
        "MELON",
        "EGG",
        "MILK",
        "WOOL",
        "FERTILIZER",
    }
)
QUANTITY_OPS = frozenset({"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"})
ATOMIC_OPS = frozenset({"HIRE", "BUY_LAND"})
SCHEMA = "titan-market-prefix-rescue/v2"


def _config_value(configuration: Any, key: str, default: Any) -> Any:
    if configuration is None:
        return default
    if isinstance(configuration, Mapping):
        return configuration.get(key, default)
    return getattr(configuration, key, default)


def market_limit(configuration: Any = None) -> Optional[int]:
    """Return the exact lower-bounded engine cap, or ``None`` on invalid input.

    Missing configuration uses the official default.  Malformed explicit values
    decline the transformation rather than silently inventing a cap.
    """

    try:
        return max(1, int(_config_value(configuration, "maxMarketOrdersPerTurn", 10)))
    except (TypeError, ValueError, OverflowError):
        return None


def is_structurally_executable_order(order: Any) -> bool:
    """Whether a row can reach a pinned-engine market operation handler.

    This is intentionally independent of money, inventory, shed capacity, and
    other dynamic preconditions.  Those determine realized execution later.
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
    if quantity <= 0 or len(order) < 2:
        return False
    item = order[1]
    if op == "BUY_SEED":
        return item in CROPS
    if op == "BUY_ANIMAL":
        return item in ANIMALS
    if op == "BUY_PRODUCT":
        return item in {"WHEAT", "FERTILIZER"}
    return item in PRODUCTS


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def rescue_market_prefix(action: Any, configuration: Any = None):
    """Return ``(action_or_copy, report)`` after one narrow stable packing.

    The input is never mutated.  No order is added, removed, edited, or reordered
    relative to another non-blank order.  Exact blank rows move only when at
    least one structurally executable order originally outside the raw cap lands
    inside it.
    """

    limit = market_limit(configuration)
    report = {
        "schema": SCHEMA,
        "syntactic_changed": False,
        "reason": "ineligible",
        "max_market_orders": limit,
        "blank_prefix_slots": [],
        "crossings": [],
        "prefix_structural_before": 0,
        "prefix_structural_after": 0,
    }
    if limit is None:
        report["reason"] = "invalid_market_limit"
        return action, report
    if not isinstance(action, dict):
        report["reason"] = "action_not_object"
        return action, report
    market = action.get("market")
    if not isinstance(market, list):
        report["reason"] = "market_not_list"
        return action, report

    prefix = market[:limit]
    blanks = [index for index, row in enumerate(prefix) if row == []]
    report["blank_prefix_slots"] = blanks
    report["market_length"] = len(market)
    report["prefix_structural_before"] = sum(
        is_structurally_executable_order(row) for row in prefix
    )
    if not blanks:
        report["reason"] = "no_exact_blank_in_prefix"
        return action, report

    tagged = list(enumerate(market))
    packed = [entry for entry in tagged if entry[1] != []]
    packed.extend(entry for entry in tagged if entry[1] == [])
    crossings = [
        {
            "from_index": old_index,
            "to_index": new_index,
            "order": deepcopy(row),
        }
        for new_index, (old_index, row) in enumerate(packed[:limit])
        if old_index >= limit and is_structurally_executable_order(row)
    ]
    if not crossings:
        report["reason"] = "no_structural_tail_order_crosses_cap"
        return action, report

    packed_market = [deepcopy(row) for _, row in packed]
    output = deepcopy(action)
    output["market"] = packed_market
    report.update(
        syntactic_changed=True,
        reason="structural_tail_order_crossed_cap",
        crossings=crossings,
        moved_blank_count=len(blanks),
        prefix_structural_after=sum(
            is_structurally_executable_order(row) for row in packed_market[:limit]
        ),
        market_sha256_before=_digest(market),
        market_sha256_after=_digest(packed_market),
    )
    return output, report
