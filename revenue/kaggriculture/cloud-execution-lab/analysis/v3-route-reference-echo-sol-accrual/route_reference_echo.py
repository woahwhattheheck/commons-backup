# SPDX-License-Identifier: Apache-2.0
"""Prevent inherited future route sales from becoming duplicate SELL intent.

The canonical planner includes inherited future route SELL rows in an optimizer
reference.  The canonical checkpoint then stores the *whole* selected future
plan in ``self.planned`` even though later execution adds the inherited route
quantity again.  This adapter changes no current action.  For a representable
single-product plan, it checkpoints only quantity above the fixed route floor.
Joint plans and plans that try to undershoot a fixed route sale retain exact
predecessor behavior rather than being reinterpreted.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Mapping, Sequence

from frozen_selected import FrozenSelected as CanonicalFrozenSelected


SCHEMA_VERSION = 1
OPERATION = "titan-v3-route-reference-echo-20260909-sol-accrual-01"


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _selected_future(plan: Sequence[Sequence[Any]], now: int) -> list[tuple[int, int]]:
    """Return positive future rows without changing their represented totals."""
    rows: list[tuple[int, int]] = []
    for index, row in enumerate(plan):
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError(f"plan row {index} is not a two-field sequence")
        step = _strict_int(row[0], f"plan row {index} step")
        quantity = _strict_int(row[1], f"plan row {index} quantity")
        if step > now and quantity > 0:
            rows.append((step, quantity))
    return rows


def _inherited_sales_at(route: Sequence[Any], item: str, step: int) -> int:
    """Return exact inherited SELL quantity for one item and route step."""
    if step < 0 or step >= len(route):
        return 0
    action = route[step]
    if not isinstance(action, Mapping):
        raise ValueError(f"route step {step} is not a mapping")
    market = action.get("market", [])
    if not isinstance(market, (list, tuple)):
        raise ValueError(f"route step {step} market is not a sequence")
    total = 0
    for index, order in enumerate(market):
        if not order:
            continue
        if not isinstance(order, (list, tuple)):
            raise ValueError(f"route step {step} market row {index} is not a sequence")
        if len(order) < 1 or order[0] != "SELL":
            continue
        if len(order) < 3:
            raise ValueError(f"route step {step} SELL row {index} is malformed")
        if order[1] != item:
            continue
        quantity = _strict_int(order[2], f"route step {step} SELL row {index} quantity")
        total += max(0, quantity)
    return total


def normalize_future_plan(
    plan: Sequence[Sequence[Any]],
    route: Sequence[Any],
    item: str,
    now: int,
    *,
    end: int | None = None,
) -> tuple[list[tuple[int, int]] | None, dict[str, Any]]:
    """Remove the fixed inherited-route floor from a selected future plan.

    ``self.planned`` is later added to the current inherited ``baseline_q``.
    Therefore it must contain scheduler-owned *excess*, not the total selected
    quantity.  A selected plan that places fewer units at a future step than the
    fixed route already sells cannot be represented by this checkpoint model;
    malformed or unrepresentable input fails closed to predecessor state.
    """
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "operation": OPERATION,
        "item": item,
        "now": now,
        "status": "INVALID",
        "changed": False,
    }
    try:
        if not isinstance(item, str) or not item:
            raise ValueError("item must be a non-empty string")
        now = _strict_int(now, "now")
        canonical_rows = _selected_future(plan, now)
        totals: dict[int, int] = defaultdict(int)
        for step, quantity in canonical_rows:
            totals[step] += quantity

        if end is None:
            end = max(totals, default=now)
        end = _strict_int(end, "end")
        if end < now:
            raise ValueError("end precedes now")

        inherited = {
            step: _inherited_sales_at(route, item, step)
            for step in range(now + 1, end + 1)
        }
        inherited = {step: quantity for step, quantity in inherited.items() if quantity}
        deficits = {
            step: quantity - totals.get(step, 0)
            for step, quantity in inherited.items()
            if totals.get(step, 0) < quantity
        }
        if deficits:
            report.update(
                status="UNREPRESENTABLE_ROUTE_FLOOR",
                reason="selected plan undershoots an inherited future route sale",
                canonical_future=[[step, quantity] for step, quantity in sorted(totals.items())],
                inherited_route=[[step, inherited[step]] for step in sorted(inherited)],
                deficits=[[step, deficits[step]] for step in sorted(deficits)],
            )
            return None, report

        # Preserve the canonical checkpoint's row order and multiplicity.  The
        # only permitted edit is consuming the inherited floor from rows at the
        # same step; unrelated duplicate rows must not be coalesced as a side
        # effect of this guard.
        normalized: list[tuple[int, int]] = []
        remaining_route = dict(inherited)
        removed: dict[int, int] = defaultdict(int)
        for step, quantity in canonical_rows:
            route_quantity = min(quantity, remaining_route.get(step, 0))
            if route_quantity:
                removed[step] += route_quantity
                remaining_route[step] -= route_quantity
            scheduler_quantity = quantity - route_quantity
            if scheduler_quantity:
                normalized.append((step, scheduler_quantity))

        report.update(
            status="NORMALIZED",
            canonical_future=[[step, quantity] for step, quantity in canonical_rows],
            canonical_totals=[[step, quantity] for step, quantity in sorted(totals.items())],
            inherited_route=[[step, inherited[step]] for step in sorted(inherited)],
            scheduler_owned=[[step, quantity] for step, quantity in normalized],
            removed_route_echo=[[step, removed[step]] for step in sorted(removed) if removed[step]],
            canonical_quantity=sum(totals.values()),
            scheduler_owned_quantity=sum(quantity for _step, quantity in normalized),
            removed_quantity=sum(removed.values()),
            changed=bool(any(removed.values())),
        )
        return normalized, report
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        report["reason"] = f"{type(exc).__name__}: {exc}"
        return None, report


def _chosen_single(chosen: Mapping[str, Any] | None) -> tuple[str, Sequence[Sequence[Any]], int] | None:
    """Return one canonical single-product choice; joint behavior is untouched."""
    if not isinstance(chosen, Mapping) or isinstance(chosen.get("plans"), Mapping):
        return None
    item = chosen.get("item")
    plan = chosen.get("plan")
    end = chosen.get("horizon_end")
    if (
        isinstance(item, str)
        and isinstance(plan, (list, tuple))
        and isinstance(end, int)
        and not isinstance(end, bool)
    ):
        return item, plan, end
    return None


class RouteEchoGuardedFrozenSelected(CanonicalFrozenSelected):
    """Canonical FrozenSelected with a post-selection checkpoint correction."""

    def transform(self, obs, config, base):
        returned = super().transform(obs, config, base)
        now = int(obs["step"])
        chosen = self.diagnostics.get("chosen")
        selected = _chosen_single(chosen)
        if selected is None:
            if isinstance(chosen, Mapping) and isinstance(chosen.get("plans"), Mapping):
                self.diagnostics["route_reference_echo"] = {
                    "schema_version": SCHEMA_VERSION,
                    "operation": OPERATION,
                    "status": "JOINT_PREDECESSOR_PRESERVED",
                    "changed": False,
                }
            return returned

        item, selected_plan, end = selected
        existing = self.planned.get(item)
        if existing is None:
            self.diagnostics["route_reference_echo"] = {
                "schema_version": SCHEMA_VERSION,
                "operation": OPERATION,
                "item": item,
                "now": now,
                "status": "NO_PERSISTED_FUTURE",
                "changed": False,
            }
            return returned

        try:
            expected = _selected_future(selected_plan, now)
        except (TypeError, ValueError, OverflowError) as exc:
            self.diagnostics["route_reference_echo"] = {
                "schema_version": SCHEMA_VERSION,
                "operation": OPERATION,
                "item": item,
                "now": now,
                "status": "INVALID",
                "changed": False,
                "reason": f"selected plan invalid: {type(exc).__name__}: {exc}",
            }
            return returned
        if list(existing) != expected:
            self.diagnostics["route_reference_echo"] = {
                "schema_version": SCHEMA_VERSION,
                "operation": OPERATION,
                "item": item,
                "now": now,
                "status": "CHECKPOINT_DRIFT",
                "changed": False,
                "expected": [list(row) for row in expected],
                "observed": deepcopy(list(existing)),
            }
            return returned

        try:
            route = self.controller.R[self.controller.cur]
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            self.diagnostics["route_reference_echo"] = {
                "schema_version": SCHEMA_VERSION,
                "operation": OPERATION,
                "item": item,
                "now": now,
                "status": "INVALID",
                "changed": False,
                "reason": f"route lookup failed: {type(exc).__name__}: {exc}",
            }
            return returned

        normalized, report = normalize_future_plan(
            selected_plan, route, item, now, end=end
        )
        self.diagnostics["route_reference_echo"] = report
        if normalized is None or not report.get("changed") or normalized == list(existing):
            return returned
        if normalized:
            self.planned[item] = normalized
        else:
            self.planned.pop(item, None)
        return returned
