#!/usr/bin/env python3
"""Bounded TITAN V5 owned-input purchase sizing reducer.

Operation provenance:
  TITAN-V5-OWNED-INPUT-PURCHASE-SIZING-ZSOL17-20260914

This component is intentionally default-OFF.  When explicitly enabled it may
only reduce the quantity of one already-authored ``BUY_PRODUCT WHEAT`` market
row.  It never adds, removes, reorders, retimes, or increases an order.

The reducer is fail-closed.  A reduction requires:
* exact current owned WHEAT from the official observation ``private`` shape;
* a complete caller-declared near-term commitment window;
* every in-window WHEAT commitment to be source-proven and executable; and
* exactly one well-formed positive-quantity authored WHEAT purchase row.

Zero is represented by keeping the authored row in place and setting quantity
to 0.  The official interpreter parses non-positive quantities as no-ops; keeping
the row preserves market queue length/indexes and therefore cannot pull a later
authored tail order into the ``maxMarketOrdersPerTurn`` execution window.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

SCHEMA = "titan-v5-owned-input-purchase-sizing-v1"
OPERATION = "TITAN-V5-OWNED-INPUT-PURCHASE-SIZING-ZSOL17-20260914"
SUPPORTED_PRODUCT = "WHEAT"


class EvidenceError(ValueError):
    """Evidence is incomplete or inconsistent, so the reducer must stay inert."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise EvidenceError(message)


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _owned_units(observation: Mapping[str, Any], product: str) -> tuple[int, dict[str, Any]]:
    """Read currently owned product units from the official private-state shape.

    Owned means bytes that are already controlled now: shed inventory plus all
    farmer/hand carried inventories.  Seeds and future purchases/harvests are
    deliberately excluded.
    """
    _require(isinstance(observation, Mapping), "observation must be an object")
    private = observation.get("private")
    _require(isinstance(private, Mapping), "observation.private must be an object")

    shed = private.get("shed")
    inventories = private.get("inventories")
    _require(isinstance(shed, Mapping), "private.shed must be an object")
    _require(isinstance(inventories, list), "private.inventories must be a list")

    shed_units = shed.get(product, 0)
    _require(
        _is_int(shed_units) and shed_units >= 0,
        f"private.shed.{product} must be a non-negative integer",
    )

    carried: list[int] = []
    for index, inventory in enumerate(inventories):
        _require(
            isinstance(inventory, Mapping),
            f"private.inventories[{index}] must be an object",
        )
        units = inventory.get(product, 0)
        _require(
            _is_int(units) and units >= 0,
            f"private.inventories[{index}].{product} must be a non-negative integer",
        )
        carried.append(units)

    total = shed_units + sum(carried)
    return total, {"shed": shed_units, "carried": carried, "total": total}


def _required_units(
    evidence: Mapping[str, Any], product: str
) -> tuple[int, list[dict[str, Any]], int, int]:
    """Return source-proven executable obligations inside the complete window."""
    _require(isinstance(evidence, Mapping), "evidence must be an object")
    _require(
        evidence.get("commitments_complete") is True,
        "commitments_complete must be literal true",
    )

    current_step = evidence.get("current_step")
    horizon_end_step = evidence.get("horizon_end_step")
    _require(_is_int(current_step) and current_step >= 0, "current_step invalid")
    _require(
        _is_int(horizon_end_step) and horizon_end_step >= current_step,
        "horizon_end_step invalid",
    )

    commitments = evidence.get("commitments")
    _require(isinstance(commitments, list), "commitments must be a list")

    accepted: list[dict[str, Any]] = []
    for index, raw in enumerate(commitments):
        _require(isinstance(raw, Mapping), f"commitments[{index}] must be an object")
        row_product = raw.get("product")
        units = raw.get("units")
        due_step = raw.get("due_step")

        _require(
            isinstance(row_product, str) and row_product,
            f"commitments[{index}].product invalid",
        )
        _require(
            _is_int(units) and units > 0,
            f"commitments[{index}].units must be a positive integer",
        )
        _require(
            _is_int(due_step) and due_step >= 0,
            f"commitments[{index}].due_step invalid",
        )

        if row_product != product:
            continue

        # A stale target obligation means the supplied window is not safe to use.
        _require(
            due_step >= current_step,
            f"commitments[{index}] is stale for {product}",
        )
        if due_step > horizon_end_step:
            continue

        _require(
            raw.get("source_proven") is True,
            f"commitments[{index}] is not source-proven",
        )
        _require(
            raw.get("executable") is True,
            f"commitments[{index}] is not executable",
        )
        source = raw.get("source")
        _require(
            isinstance(source, str) and source.strip(),
            f"commitments[{index}].source required",
        )
        accepted.append(
            {
                "product": product,
                "units": units,
                "due_step": due_step,
                "source": source.strip(),
            }
        )

    # No proven target commitment means there is no source-bound sizing theorem
    # for this turn.  Stay inert rather than interpreting silence as permission
    # to erase a strategic carry purchase.
    _require(accepted, f"no source-proven {product} commitment in window")
    accepted.sort(key=lambda row: (row["due_step"], row["source"], row["units"]))
    return sum(row["units"] for row in accepted), accepted, current_step, horizon_end_step


def _find_authored_buy(action: Mapping[str, Any], product: str) -> tuple[int, int]:
    _require(isinstance(action, Mapping), "action must be an object")
    market = action.get("market")
    _require(isinstance(market, list), "action.market must be a list")

    matches: list[tuple[int, int]] = []
    for index, row in enumerate(market):
        if not (isinstance(row, list) and len(row) >= 2):
            continue
        if row[0] != "BUY_PRODUCT" or row[1] != product:
            continue
        _require(
            len(row) >= 3,
            f"market[{index}] target BUY_PRODUCT is missing quantity",
        )
        quantity = row[2]
        _require(
            _is_int(quantity) and quantity > 0,
            f"market[{index}] target quantity must be a positive integer",
        )
        matches.append((index, quantity))

    _require(matches, f"no authored BUY_PRODUCT {product} row")
    _require(
        len(matches) == 1,
        f"multiple authored BUY_PRODUCT {product} rows are ambiguous",
    )
    return matches[0]


def _identity_report(
    action: Any,
    *,
    enabled: bool,
    reason: str,
    product: str,
    error: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    candidate = copy.deepcopy(action)
    report = {
        "schema": SCHEMA,
        "operation": OPERATION,
        "enabled": enabled,
        "changed": False,
        "reason": reason,
        "product": product,
        "action_sha256_before": _canonical_sha(action),
        "action_sha256_after": _canonical_sha(candidate),
        "market_length_preserved": True,
    }
    if error is not None:
        report["error"] = error
    return candidate, report


def size_existing_buy_product(
    action: Mapping[str, Any],
    observation: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    enabled: bool = False,
    product: str = SUPPORTED_PRODUCT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reduce one already-authored BUY_PRODUCT WHEAT quantity when proven safe.

    The return value is ``(candidate_action, report)``.  Invalid/incomplete
    evidence never raises to the caller: it returns an identity candidate with
    ``reason='fail_closed'`` and a diagnostic string.  The original action is
    never mutated.
    """
    if product != SUPPORTED_PRODUCT:
        candidate, report = _identity_report(
            action,
            enabled=enabled,
            reason="unsupported_product",
            product=product,
        )
        return candidate, report

    if not enabled:
        candidate, report = _identity_report(
            action,
            enabled=False,
            reason="disabled",
            product=product,
        )
        return candidate, report

    try:
        index, before_qty = _find_authored_buy(action, product)
        owned, owned_breakdown = _owned_units(observation, product)
        required, commitments, current_step, horizon_end_step = _required_units(
            evidence, product
        )
    except EvidenceError as exc:
        candidate, report = _identity_report(
            action,
            enabled=True,
            reason="fail_closed",
            product=product,
            error=str(exc),
        )
        return candidate, report

    fresh_required = max(0, required - owned)

    # This reducer can only shrink.  If the parent already buys <= the proven
    # fresh requirement, preserving the parent is the sole legal result.
    if before_qty <= fresh_required:
        candidate, report = _identity_report(
            action,
            enabled=True,
            reason="parent_already_at_or_below_proven_requirement",
            product=product,
        )
        report.update(
            {
                "target_market_index": index,
                "quantity_before": before_qty,
                "quantity_after": before_qty,
                "owned_units": owned,
                "owned_breakdown": owned_breakdown,
                "commitment_units": required,
                "fresh_required": fresh_required,
                "current_step": current_step,
                "horizon_end_step": horizon_end_step,
                "commitments": commitments,
            }
        )
        return candidate, report

    candidate = copy.deepcopy(action)
    before_market = action["market"]
    candidate_market = candidate["market"]

    # Slot-preserving zero is intentional; do NOT delete the row.
    candidate_market[index][2] = fresh_required

    # Executable contract assertions.  They make accidental broadening obvious
    # during integration and are independent of Python optimization mode.
    if len(candidate_market) != len(before_market):
        raise AssertionError("market length changed")
    for row_index, before_row in enumerate(before_market):
        after_row = candidate_market[row_index]
        if row_index == index:
            expected = copy.deepcopy(before_row)
            expected[2] = fresh_required
            if after_row != expected:
                raise AssertionError("target row changed beyond quantity")
        elif after_row != before_row:
            raise AssertionError(f"non-target market row {row_index} changed")

    if candidate.get("farmer") != action.get("farmer"):
        raise AssertionError("farmer action changed")
    if candidate.get("hands") != action.get("hands"):
        raise AssertionError("hands actions changed")

    report = {
        "schema": SCHEMA,
        "operation": OPERATION,
        "enabled": True,
        "changed": True,
        "reason": "source_bound_owned_stock_reduction",
        "product": product,
        "target_market_index": index,
        "quantity_before": before_qty,
        "quantity_after": fresh_required,
        "units_removed": before_qty - fresh_required,
        "owned_units": owned,
        "owned_breakdown": owned_breakdown,
        "commitment_units": required,
        "fresh_required": fresh_required,
        "current_step": current_step,
        "horizon_end_step": horizon_end_step,
        "commitments": commitments,
        "zero_quantity_row_preserved": fresh_required == 0,
        "market_length_preserved": len(candidate_market) == len(before_market),
        "action_sha256_before": _canonical_sha(action),
        "action_sha256_after": _canonical_sha(candidate),
    }
    return candidate, report
