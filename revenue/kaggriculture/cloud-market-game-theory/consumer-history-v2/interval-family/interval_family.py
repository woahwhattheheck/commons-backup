# SPDX-License-Identifier: Apache-2.0
"""Complete bounded terminal scenarios from same-lag public sale intervals.

This is an additive fallback for histories that lack enough exact same-phase
windows. It enumerates every integer joint vector admitted by the supplied
marginal sale intervals and one shared shed-capacity bound, or returns a named
limit without a partial family. No endpoint is treated as independent, no
probability is assigned, and no current rival action or private stock is read.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from typing import Any, Mapping, Sequence

SCHEMA = "titan.joint-terminal-interval-history.v1"
OPERATING = frozenset(("WHEAT", "FERTILIZER"))


def _int(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")
    return value


def _names(value: Any, name: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value or len(value) > 32:
        raise ValueError(f"{name} must contain 1..32 unique product names")
    if any(not isinstance(p, str) or not p for p in value) or len(set(value)) != len(value):
        raise ValueError(f"{name} must contain unique nonempty strings")
    return list(value)


def _entries(value: Any, name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 32:
        raise ValueError(f"{name} must contain 1..32 explicit hypotheses")
    ids = []
    for entry in value:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("id"), str) or not entry["id"]:
            raise ValueError(f"{name} entries need a nonempty id")
        if not isinstance(entry.get("origin"), str) or not entry["origin"]:
            raise ValueError(f"{name} entries need an explicit origin")
        ids.append(entry["id"])
    if len(set(ids)) != len(ids):
        raise ValueError(f"{name} ids must be unique")
    return list(value)


def _bounds(row: Any, product: str, step: int, capacity: int) -> tuple[int, int]:
    values = (getattr(row, "lower", None), getattr(row, "upper", None),
              getattr(row, "admitted_lower", None), getattr(row, "admitted_upper", None))
    if (getattr(row, "step", None) != step or getattr(row, "product", None) != product
            or getattr(row, "reason", None) not in ("identified", "floor_censored")
            or any(type(value) is not int or not 0 <= value <= capacity for value in values)):
        raise ValueError("incompatible same-lag public sale interval")
    lower, upper, admitted_lower, admitted_upper = values
    if not admitted_lower <= lower <= upper or not admitted_lower <= admitted_upper <= upper:
        raise ValueError("incompatible same-lag public sale interval")
    return lower, upper


def enumerate_joint_vectors(bounds: Sequence[tuple[str, int, int]], capacity: int,
                            limit: int) -> tuple[list[tuple[int, ...]] | None, int]:
    """Return every feasible vector, or ``None`` once the exact count exceeds limit."""
    capacity = _int(capacity, "capacity", 1, 1000)
    limit = _int(limit, "limit", 1, 100000)
    rows = list(bounds)
    if not rows:
        return [()], 1
    names = [row[0] for row in rows]
    if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        raise ValueError("vector products must be unique nonempty strings")
    for _, lower, upper in rows:
        if type(lower) is not int or type(upper) is not int or not 0 <= lower <= upper <= 1000:
            raise ValueError("vector bounds must be ordered nonnegative integers")
    suffix_lower = [0] * (len(rows) + 1)
    for index in range(len(rows) - 1, -1, -1):
        suffix_lower[index] = suffix_lower[index + 1] + rows[index][1]
    if suffix_lower[0] > capacity:
        return [], 0

    @lru_cache(maxsize=None)
    def count(index: int, remaining: int) -> int:
        if index == len(rows):
            return 1
        _, lower, upper = rows[index]
        maximum = min(upper, remaining - suffix_lower[index + 1])
        if maximum < lower:
            return 0
        total = 0
        for quantity in range(lower, maximum + 1):
            total += count(index + 1, remaining - quantity)
            if total > limit:
                return limit + 1
        return total

    total = count(0, capacity)
    if total > limit:
        return None, total
    vectors: list[tuple[int, ...]] = []

    def emit(index: int, remaining: int, prefix: list[int]) -> None:
        if index == len(rows):
            vectors.append(tuple(prefix))
            return
        _, lower, upper = rows[index]
        maximum = min(upper, remaining - suffix_lower[index + 1])
        for quantity in range(lower, maximum + 1):
            if count(index + 1, remaining - quantity):
                emit(index + 1, remaining - quantity, prefix + [quantity])

    emit(0, capacity, [])
    if len(vectors) != total:
        raise AssertionError("bounded vector count and enumeration differ")
    return vectors, total


def build_interval_terminal_scenarios(
    history: Any,
    products: Sequence[str],
    now: int,
    *,
    slot_templates: Sequence[Mapping[str, Any]] | None = None,
    unobserved_products: Sequence[str] = (),
    unobserved_lots: Sequence[Mapping[str, Any]] | None = None,
    capacity: int = 100,
    max_orders: int = 10,
    max_scenarios: int = 32,
    candidate_lags: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Build a complete explicit family from retained same-phase intervals.

    Each included lag must contain one public sale interval for every observed
    product. For every explicit unobserved-stock hypothesis, all integer joint
    vectors satisfying those intervals and shared capacity are enumerated. If
    that complete set cannot fit ``max_scenarios``, the result is not ready and
    contains no partial scenario list.

    Callers should retain an already-ready exact-history family. This function
    is intended as its fail-closed fallback, or with ``candidate_lags`` for an
    exact-source parity check.
    """
    universe = _names(products, "products")
    now = _int(now, "now", 0, 100000)
    capacity = _int(capacity, "capacity", 1, 1000)
    max_orders = _int(max_orders, "max_orders", 1, 32)
    max_scenarios = _int(max_scenarios, "max_scenarios", 1, 32)
    period = _int(history.period, "history.period", 1, 100000)
    window = _int(history.window, "history.window", 1, 100000)
    minimum = _int(history.minimum, "history.minimum", 1, 100000)
    if not isinstance(getattr(history, "records", None), Mapping):
        raise ValueError("history.records must be a mapping")
    if not isinstance(unobserved_products, (list, tuple)) or any(
        product not in universe for product in unobserved_products
    ):
        raise ValueError("unobserved_products must be a subset of products")
    unknown = sorted((set(unobserved_products) | OPERATING) & set(universe))
    observed = [product for product in universe if product not in unknown]
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "ready": False,
        "status": "insufficient_interval_history",
        "now": now,
        "minimum": minimum,
        "joint_support": 0,
        "observed_products": observed,
        "unobserved_products": unknown,
        "historical_lags": [],
        "scenarios": [],
        "scenario_probabilities": None,
        "exact_set_complete": False,
        "interpretation": (
            "Complete bounded integer vectors from same-lag prior public sale "
            "intervals plus explicit slot/stock hypotheses; not calibrated, "
            "exhaustive of unmodeled facts, or current rival truth."
        ),
    }
    if not observed:
        result["status"] = "no_identified_products"
        return result
    if candidate_lags is None:
        lags = list(range(1, window + 1))
    else:
        if not isinstance(candidate_lags, (list, tuple)) or not candidate_lags:
            raise ValueError("candidate_lags must contain positive unique integers")
        lags = list(candidate_lags)
        if any(type(lag) is not int or lag < 1 or lag > window for lag in lags):
            raise ValueError("candidate_lags must fit history.window")
        if len(set(lags)) != len(lags):
            raise ValueError("candidate_lags must be unique")
        lags.sort()

    complete: list[tuple[int, int, list[tuple[str, int, int]]]] = []
    for lag in lags:
        prior = now - lag * period
        rows = []
        missing = False
        for product in observed:
            record = history.records.get(product, {}).get(prior)
            if record is None:
                missing = True
                break
            lower, upper = _bounds(record, product, prior, capacity)
            rows.append((product, lower, upper))
        if not missing:
            complete.append((lag, prior, rows))
    result.update(
        joint_support=len(complete),
        historical_lags=[lag for lag, _, _ in complete],
        product_support={
            product: sum(1 for _, prior, _ in complete
                         if prior in history.records.get(product, {}))
            for product in observed
        },
    )
    if len(complete) < minimum:
        return result
    if slot_templates is None:
        result["status"] = "slot_order_unidentified"
        return result
    templates = _entries(slot_templates, "slot_templates")
    for template in templates:
        slots = template.get("slots")
        if not isinstance(slots, (list, tuple)) or not 1 <= len(slots) <= max_orders:
            raise ValueError("slot template must fit the admitted market prefix")
        named = [product for product in slots if product is not None]
        if any(product not in universe for product in named) or len(set(named)) != len(named):
            raise ValueError("slot templates contain unique known products or None")
    if unknown and unobserved_lots is None:
        result["status"] = "unobserved_stock_unspecified"
        return result
    completions = ([{"id": "no-unobserved-products",
                     "origin": "all declared products have prior interval bounds",
                     "stock": {}}]
                   if unobserved_lots is None else _entries(unobserved_lots, "unobserved_lots"))
    for completion in completions:
        stock = completion.get("stock")
        if not isinstance(stock, Mapping) or set(stock) != set(unknown):
            raise ValueError("each completion must explicitly cover exactly every unobserved product")
        for product, quantity in stock.items():
            _int(quantity, "unobserved stock " + product, 0, capacity)

    scenarios: dict[str, dict[str, Any]] = {}
    vector_counts = []
    for completion in completions:
        fixed = dict(completion["stock"])
        remaining_capacity = capacity - sum(fixed.values())
        if remaining_capacity < 0:
            result["status"] = "unobserved_stock_exceeds_capacity"
            result["unobserved_lot"] = completion["id"]
            return result
        for lag, prior, bounds in complete:
            vectors, count = enumerate_joint_vectors(bounds, remaining_capacity, max_scenarios)
            vector_counts.append({"lag": lag, "training_step": prior,
                                  "unobserved_lot": completion["id"],
                                  "count": count if vectors is not None else None,
                                  "count_at_least": max_scenarios + 1 if vectors is None else count})
            if vectors == []:
                result.update(status="joint_capacity_exceeded", vector_counts=vector_counts,
                              failing_lag=lag, unobserved_lot=completion["id"])
                return result
            if vectors is None:
                result.update(status="interval_vector_limit", vector_counts=vector_counts,
                              failing_lag=lag, unobserved_lot=completion["id"],
                              unique_vectors_at_least=max_scenarios + 1)
                return result
            for vector in vectors:
                interval_stock = {product: quantity
                                  for (product, _, _), quantity in zip(bounds, vector)}
                stock = {**interval_stock, **fixed}
                if sum(stock.values()) > capacity:
                    raise AssertionError("enumerated vector exceeds shared capacity")
                shed = {product: stock[product] for product in universe if stock.get(product, 0)}
                for template in templates:
                    slots = template["slots"]
                    if not set(shed).issubset(set(slots)):
                        result["status"] = "unrepresented_positive_product"
                        result["failing_product"] = sorted(set(shed) - set(slots))[0]
                        return result
                    queue = [["SELL", product, shed[product]] if product in shed else []
                             for product in slots]
                    key = json.dumps([shed, queue], sort_keys=True, separators=(",", ":"))
                    witness = {
                        "lag": lag,
                        "training_start": prior,
                        "training_end": prior,
                        "slot_template": template["id"],
                        "slot_origin": template["origin"],
                        "unobserved_lot": completion["id"],
                        "stock_origin": completion["origin"],
                        "interval_bounds": {product: [lower, upper]
                                            for product, lower, upper in bounds},
                    }
                    if key not in scenarios:
                        if len(scenarios) >= max_scenarios:
                            result.update(status="scenario_limit", vector_counts=vector_counts,
                                          unique_scenarios_at_least=len(scenarios) + 1)
                            return result
                        scenarios[key] = {
                            "id": "joint-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24],
                            "shed": shed,
                            "market": queue,
                            "origin": {
                                "kind": SCHEMA,
                                "now": now,
                                "quantity_source": (
                                    "all integer same-lag prior public sale vectors "
                                    "consistent with retained intervals and shared capacity"
                                ),
                                "slot_order_identified": False,
                                "interval_set_complete": True,
                                "witnesses": [],
                            },
                        }
                    scenarios[key]["origin"]["witnesses"].append(witness)
    result.update(
        ready=True,
        status="ready_interval_enumeration",
        exact_set_complete=True,
        scenarios=deepcopy(list(scenarios.values())),
        vector_counts=vector_counts,
        unique_scenarios=len(scenarios),
    )
    return result
