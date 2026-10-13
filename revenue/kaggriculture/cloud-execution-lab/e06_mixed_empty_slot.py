"""Bounded E06 candidate selection for inert slots in mixed market queues.

This helper does not execute market mechanics.  It enumerates one conservative
replacement location per remaining selected product, then delegates the *entire*
market prefix to a caller-supplied exact scenario evaluator.  Positive inherited
economic rows never move or disappear.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

ReceiptEvaluator = Callable[[list], Mapping]


def _positive_sell(row: Any) -> bool:
    return (
        isinstance(row, list)
        and len(row) >= 3
        and row[0] == "SELL"
        and not isinstance(row[2], bool)
        and isinstance(row[2], int)
        and row[2] > 0
    )


def _inert_slot(row: Any) -> bool:
    if row == []:
        return True
    return (
        isinstance(row, list)
        and len(row) >= 3
        and row[0] == "SELL"
        and not isinstance(row[2], bool)
        and isinstance(row[2], int)
        and row[2] == 0
    )


def _mixed_prefix(prefix: Sequence[Any]) -> bool:
    """True when the executable prefix contains a positive non-SELL row."""
    return any(row and not _positive_sell(row) and not _inert_slot(row) for row in prefix)


def _normalize_receipt(receipt: Mapping) -> dict:
    if not isinstance(receipt, Mapping):
        raise ValueError("prefix evaluator must return a mapping")
    if receipt.get("complete") is not True:
        return {"complete": False}
    values = receipt.get("scenario_value")
    acquisitions = receipt.get("successful_acquisitions")
    if not isinstance(values, Mapping) or not values:
        raise ValueError("complete receipt requires non-empty scenario_value mapping")
    if not isinstance(acquisitions, Mapping):
        raise ValueError("complete receipt requires successful_acquisitions mapping")
    if any(not isinstance(scenario, str) or not scenario for scenario in values):
        raise ValueError("scenario ids must be non-empty strings")
    if any(not isinstance(scenario, str) or not scenario for scenario in acquisitions):
        raise ValueError("scenario ids must be non-empty strings")
    if set(values) != set(acquisitions):
        raise ValueError("receipt scenario sets must match exactly")
    normalized_values = {}
    normalized_acquisitions = {}
    for scenario in values:
        value = values[scenario]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("scenario values must be finite numbers")
        rows = acquisitions[scenario]
        if not isinstance(rows, (list, tuple)):
            raise ValueError("successful acquisition receipts must be ordered sequences")
        # Preserve validated scenario ids exactly. Never stringify arbitrary keys:
        # raw 1 and raw "1" are distinct inputs and must not alias at the gate.
        normalized_values[scenario] = float(value)
        normalized_acquisitions[scenario] = tuple(copy.deepcopy(rows))
    return {
        "complete": True,
        "scenario_value": normalized_values,
        "successful_acquisitions": normalized_acquisitions,
    }


def reclaim_mixed_empty_slot(
    market: list,
    remaining_sales: Mapping[str, int],
    *,
    max_orders: int,
    evaluate: ReceiptEvaluator,
) -> tuple[list, dict]:
    """Return the best strictly-admitted one-slot replacement and diagnostics.

    The candidate surface is identity plus at most one replacement per product:
    the earliest inert executable slot is used because its exact effects on later
    funding, rival prices, partial purchases, and clipping are delegated to the
    complete-prefix evaluator.  The clipped suffix is copied byte-for-structure.

    Admission is deliberately conservative: baseline and candidate must both
    produce complete receipts over the identical scenario set; every scenario's
    successful acquisition receipt must stay exactly equal; and candidate value
    must improve strictly in every scenario.  Thus SELL-before-BUY is not treated
    as equivalent to BUY-before-SELL merely because the queue rows are retained.
    """
    if not isinstance(market, list):
        raise ValueError("market must be a list")
    if not isinstance(remaining_sales, Mapping):
        raise ValueError("remaining_sales must be a mapping")
    if isinstance(max_orders, bool) or not isinstance(max_orders, int) or max_orders < 1:
        raise ValueError("max_orders must be a positive integer")
    if not callable(evaluate):
        raise ValueError("evaluate must be callable")

    original = copy.deepcopy(market)
    prefix_end = min(len(original), max_orders)
    prefix = original[:prefix_end]
    report = {
        "changed": False,
        "reason": None,
        "prefix_end": prefix_end,
        "candidate_count": 0,
        "accepted_count": 0,
        "chosen": None,
        "worst_gain": 0.0,
    }

    # Existing emitter already has append capacity; E06 is only the full-prefix gap.
    if len(original) < max_orders:
        report["reason"] = "append_capacity_available"
        return original, report
    if not _mixed_prefix(prefix):
        report["reason"] = "sale_only_delegate"
        return original, report
    vacancies = [i for i, row in enumerate(prefix) if _inert_slot(row)]
    if not vacancies:
        report["reason"] = "no_inert_executable_slot"
        return original, report

    eligible = []
    for product, quantity in remaining_sales.items():
        if not isinstance(product, str) or not product:
            raise ValueError("remaining sale product must be a non-empty string")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError("remaining sale quantities must be non-negative integers")
        if quantity:
            eligible.append((product, quantity))
    eligible.sort()
    if not eligible:
        report["reason"] = "no_remaining_sale"
        return original, report

    baseline = _normalize_receipt(evaluate(copy.deepcopy(original[:max_orders])))
    if not baseline.get("complete"):
        report["reason"] = "baseline_receipt_incomplete"
        return original, report

    slot = vacancies[0]
    best = None
    scenario_names = set(baseline["scenario_value"])
    for candidate_index, (product, quantity) in enumerate(eligible):
        candidate = copy.deepcopy(original)
        candidate[slot] = ["SELL", product, quantity]
        report["candidate_count"] += 1
        receipt = _normalize_receipt(evaluate(copy.deepcopy(candidate[:max_orders])))
        if not receipt.get("complete"):
            continue
        if set(receipt["scenario_value"]) != scenario_names:
            continue
        if any(
            receipt["successful_acquisitions"][scenario]
            != baseline["successful_acquisitions"][scenario]
            for scenario in scenario_names
        ):
            continue
        deltas = {
            scenario: receipt["scenario_value"][scenario] - baseline["scenario_value"][scenario]
            for scenario in scenario_names
        }
        if not deltas or min(deltas.values()) <= 0:
            continue
        report["accepted_count"] += 1
        rank = (min(deltas.values()), sum(deltas.values()), -candidate_index)
        if best is None or rank > best[0]:
            best = (rank, candidate, product, quantity, deltas)

    if best is None:
        report["reason"] = "no_strict_scenario_safe_replacement"
        return original, report
    _, chosen, product, quantity, deltas = best
    report.update({
        "changed": True,
        "reason": "strict_scenario_safe_replacement",
        "chosen": {"slot": slot, "product": product, "quantity": quantity},
        "worst_gain": min(deltas.values()),
        "scenario_gain": dict(sorted(deltas.items())),
    })
    return chosen, report
