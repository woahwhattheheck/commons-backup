# SPDX-License-Identifier: Apache-2.0
"""Fail-closed solvency interlock for final SELL-pressure reordering.

The pressure transform is intentionally observation-only and may permute supported
SELL lots.  Different lot indexes can nevertheless change our receipts under the
official simultaneous market because the rival's same-index product is unknown.
A later fixed-price acquisition must therefore not rely on a receipt ordering that
the final pressure pass changes.

This helper never calls a policy and never predicts rival private state.  It keeps
the pressured action only when either (a) no acquisition follows the changed
executable prefix, or (b) starting cash alone pays every supported acquisition in
the executable prefix.  Unsupported variable-price purchases fail closed.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from typing import Any, Mapping

_FIXED = frozenset(("HIRE", "BUY_LAND", "BUY_SEED", "BUY_ANIMAL"))
_ACQUISITIONS = _FIXED | frozenset(("BUY_PRODUCT",))
_NOOP = frozenset(("PASS",))


def _strict_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _market_limit(configuration: Mapping[str, Any]) -> int | None:
    raw = configuration.get("maxMarketOrdersPerTurn", 10)
    if isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if value != raw:
        return None
    return max(1, value)


def _row_key(row: Any) -> str | None:
    try:
        return json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        return None


def _order_op(row: Any) -> str | None:
    if not isinstance(row, list) or not row or not isinstance(row[0], str):
        return None
    return row[0]


def _changed_indexes(before: list[Any], after: list[Any], end: int) -> list[int]:
    return [index for index in range(end) if before[index] != after[index]]


def _action_permutation_only(before: Mapping[str, Any], after: Mapping[str, Any],
                             end: int) -> tuple[bool, str]:
    """Validate the exact pressure contract before reasoning about solvency."""
    if set(before) != set(after):
        return False, "action_keys_changed"
    for key in before:
        if key == "market":
            continue
        if before[key] != after[key]:
            return False, f"non_market_changed:{key}"
    old = before.get("market")
    new = after.get("market")
    if not isinstance(old, list) or not isinstance(new, list):
        return False, "market_not_list"
    if len(old) != len(new):
        return False, "market_length_changed"
    if old[end:] != new[end:]:
        return False, "inactive_suffix_changed"
    old_keys = [_row_key(row) for row in old[:end]]
    new_keys = [_row_key(row) for row in new[:end]]
    if any(key is None for key in (*old_keys, *new_keys)):
        return False, "unserializable_market_row"
    if Counter(old_keys) != Counter(new_keys):
        return False, "executable_multiset_changed"
    return True, "permutation_only"


def _acquisition_indexes(orders: list[Any], start: int, end: int) -> list[int]:
    return [index for index in range(start, end)
            if _order_op(orders[index]) in _ACQUISITIONS]


def _cash_independent_prefix(mechanics: Any, observation: Mapping[str, Any],
                             configuration: Mapping[str, Any], orders: list[Any],
                             end: int) -> dict[str, Any]:
    """Prove every supported acquisition executes without crediting any SELL.

    This deliberately ignores all sale proceeds.  Fixed prices and the current
    HIRE/LAND indexes are replayed exactly.  BUY_PRODUCT is variable-price and is
    therefore an unsupported barrier.  Malformed/unknown nonempty rows also fail
    closed rather than becoming accidental proof assumptions.
    """
    try:
        player = int(observation["player"])
        farm = observation["farms"][player]
        cash = _strict_int(farm["money"])
        hires = _strict_int(farm.get("hires_today", 0))
        unlocked = list(farm["unlocked_quadrants"])
    except (KeyError, TypeError, ValueError, OverflowError, IndexError):
        return {"safe": False, "reason": "malformed_observation"}
    if cash is None or hires is None or cash < 0 or hires < 0:
        return {"safe": False, "reason": "malformed_cash_or_hires"}
    starting_cash = cash
    spent = 0
    acquisitions: list[dict[str, Any]] = []

    for index, row in enumerate(orders[:end]):
        if row == []:
            continue
        op = _order_op(row)
        if op in _NOOP:
            continue
        if op == "SELL":
            # The theorem is intentionally independent of all sale receipts.
            continue
        if op is None:
            return {"safe": False, "reason": "malformed_order", "index": index,
                    "starting_cash": starting_cash, "cash_before_failure": cash}
        if op == "BUY_PRODUCT":
            return {"safe": False, "reason": "variable_price_purchase", "index": index,
                    "starting_cash": starting_cash, "cash_before_failure": cash}
        if op == "HIRE":
            if len(row) != 1:
                return {"safe": False, "reason": "malformed_hire", "index": index,
                        "starting_cash": starting_cash, "cash_before_failure": cash}
            try:
                cost = int(mechanics._hire_cost(
                    hires, int(configuration.get("farmHandCostMult", 1))))
            except (AttributeError, TypeError, ValueError, OverflowError):
                return {"safe": False, "reason": "hire_cost_unavailable", "index": index,
                        "starting_cash": starting_cash, "cash_before_failure": cash}
            required = 1
            item = ""
            next_hires = hires + 1
            next_unlocked = unlocked
        elif op == "BUY_LAND":
            if len(row) != 1:
                return {"safe": False, "reason": "malformed_land", "index": index,
                        "starting_cash": starting_cash, "cash_before_failure": cash}
            try:
                land_index = len(unlocked) - 1
                if land_index >= len(mechanics.LAND_PRICES):
                    # The engine treats an exhausted land order as a no-op.
                    continue
                cost = int(mechanics.LAND_PRICES[land_index])
                next_unlocked = [*unlocked, mechanics.LAND_ORDER[len(unlocked) - 1]]
            except (AttributeError, TypeError, ValueError, OverflowError, IndexError):
                return {"safe": False, "reason": "land_cost_unavailable", "index": index,
                        "starting_cash": starting_cash, "cash_before_failure": cash}
            required = 1
            item = ""
            next_hires = hires
        elif op in ("BUY_SEED", "BUY_ANIMAL"):
            if len(row) != 3 or not isinstance(row[1], str):
                return {"safe": False, "reason": "malformed_fixed_purchase", "index": index,
                        "starting_cash": starting_cash, "cash_before_failure": cash}
            quantity = _strict_int(row[2])
            if quantity is None:
                return {"safe": False, "reason": "malformed_quantity", "index": index,
                        "starting_cash": starting_cash, "cash_before_failure": cash}
            if quantity <= 0:
                # Official parser rejects nonpositive quantities as a no-op.
                continue
            item = row[1]
            table = mechanics.CROPS if op == "BUY_SEED" else mechanics.ANIMALS
            field = "seed" if op == "BUY_SEED" else "cost"
            try:
                unit_cost = int(table[item][field])
            except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
                return {"safe": False, "reason": "fixed_cost_unavailable", "index": index,
                        "starting_cash": starting_cash, "cash_before_failure": cash}
            cost = unit_cost * quantity
            required = quantity
            next_hires = hires
            next_unlocked = unlocked
        else:
            return {"safe": False, "reason": "unsupported_order", "index": index,
                    "op": op, "starting_cash": starting_cash,
                    "cash_before_failure": cash}

        if cost < 0 or cash < cost:
            return {
                "safe": False,
                "reason": "sale_credit_required",
                "index": index,
                "op": op,
                "item": item,
                "required_units": required,
                "cost": cost,
                "starting_cash": starting_cash,
                "cash_before_failure": cash,
                "cash_shortfall": max(0, cost - cash),
                "spent_without_sales": spent,
                "acquisitions": acquisitions,
            }
        cash -= cost
        spent += cost
        hires = next_hires
        unlocked = next_unlocked
        acquisitions.append({"index": index, "op": op, "item": item,
                             "required_units": required, "cost": cost,
                             "cash_after": cash})

    return {"safe": True, "reason": "starting_cash_covers_fixed_prefix",
            "starting_cash": starting_cash, "spent_without_sales": spent,
            "ending_cash_without_sales": cash, "acquisitions": acquisitions}


def preserve_acquisition_solvency(mechanics: Any, observation: Mapping[str, Any],
                                  configuration: Mapping[str, Any] | None,
                                  before_pressure: Mapping[str, Any],
                                  after_pressure: Mapping[str, Any]) -> tuple[dict, dict]:
    """Return pressure bytes only when their downstream acquisition is solvent.

    ``before_pressure`` is the already-finished stock/capital action.  Rejection
    therefore restores that exact action; it does not synthesize a third queue.
    """
    cfg = dict(configuration or {})
    if not isinstance(before_pressure, Mapping) or not isinstance(after_pressure, Mapping):
        return deepcopy(before_pressure), {"changed": False, "accepted": False,
            "reason": "action_not_mapping"}
    before = deepcopy(dict(before_pressure))
    after = deepcopy(dict(after_pressure))
    if before == after:
        return after, {"changed": False, "accepted": True, "reason": "pressure_identity"}
    limit = _market_limit(cfg)
    if limit is None:
        return before, {"changed": True, "accepted": False,
                        "reason": "invalid_market_limit"}
    old_market = before.get("market")
    new_market = after.get("market")
    if not isinstance(old_market, list) or not isinstance(new_market, list):
        return before, {"changed": True, "accepted": False, "reason": "market_not_list"}
    end = min(len(old_market), limit)
    valid, contract = _action_permutation_only(before, after, end)
    if not valid:
        return before, {"changed": True, "accepted": False, "reason": contract,
                        "executable_end": end}
    changed = _changed_indexes(old_market, new_market, end)
    if not changed:
        # A change outside the executable prefix was rejected by the suffix check;
        # reaching here means semantically identical executable bytes.
        return after, {"changed": True, "accepted": True,
                       "reason": "no_executable_change", "executable_end": end}
    earliest = min(changed)
    acquisitions = _acquisition_indexes(new_market, earliest, end)
    if not acquisitions:
        return after, {"changed": True, "accepted": True,
                       "reason": "no_downstream_acquisition",
                       "earliest_changed_index": earliest,
                       "changed_indexes": changed, "executable_end": end}
    certificate = _cash_independent_prefix(mechanics, observation, cfg, new_market, end)
    report = {
        "changed": True,
        "accepted": bool(certificate.get("safe")),
        "reason": certificate.get("reason", "uncertified"),
        "earliest_changed_index": earliest,
        "changed_indexes": changed,
        "downstream_acquisition_indexes": acquisitions,
        "executable_end": end,
        "certificate": certificate,
    }
    return (after if report["accepted"] else before), report
