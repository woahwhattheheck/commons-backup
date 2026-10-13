#!/usr/bin/env python3
"""Portable semantics for TITAN's cross-product SELL slot reservation closure.

The production scheduler stores future rows in ``self.planned`` as scheduler-owned
excess above inherited route SELLs.  Every non-zero excess tranche therefore
needs one appended market row when it becomes due.  Candidate feasibility must
reserve those rows before admitting a new product-local extra SELL.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


class LedgerError(ValueError):
    """The internal planned-row ledger is malformed; admission must fail closed."""


def _strict_nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LedgerError(f"{field} must be a non-negative integer")
    return value


def planned_slot_reservations(
    planned: Mapping[str, Sequence[Sequence[int]]],
    *,
    candidate_item: str,
    now: int,
    step: int,
    current_quantities: Mapping[str, int] | None = None,
    orders: Sequence[Any] | None = None,
) -> int:
    """Count other-product excess rows that claim a market slot at ``step``.

    On the current turn, every overdue row (``due <= now``) is still presented as
    due-now by the production scheduler.  At a future candidate step, every
    retained nonzero row due at or before that step stays reserved until retired.
    Multiple tranches for one product still need just one appended
    SELL row because settlement aggregates that product before emission.
    """
    if not isinstance(planned, Mapping):
        raise LedgerError("planned must be a mapping")
    if not isinstance(candidate_item, str) or not candidate_item:
        raise LedgerError("candidate_item must be a non-empty string")
    now_i = _strict_nonnegative_int(now, "now")
    step_i = _strict_nonnegative_int(step, "step")
    if step_i < now_i:
        raise LedgerError("step cannot precede now")

    if current_quantities is not None and not isinstance(current_quantities, Mapping):
        raise LedgerError("current_quantities must be a mapping when supplied")
    if orders is not None and not isinstance(orders, (list, tuple)):
        raise LedgerError("orders must be a list or tuple when supplied")
    if (current_quantities is None) != (orders is None):
        raise LedgerError("current_quantities and orders must be supplied together")

    reserved = 0
    for other, rows in planned.items():
        if not isinstance(other, str) or not other:
            raise LedgerError("planned product keys must be non-empty strings")
        if other == candidate_item:
            continue
        if not isinstance(rows, (list, tuple)):
            raise LedgerError(f"planned rows for {other} must be a list or tuple")

        active = False
        for index, row in enumerate(rows):
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                raise LedgerError(f"planned row {other}[{index}] must have due and quantity")
            due = _strict_nonnegative_int(row[0], f"planned row {other}[{index}].due")
            quantity = _strict_nonnegative_int(row[1], f"planned row {other}[{index}].quantity")
            if quantity == 0:
                continue
            if step_i == now_i and due <= now_i:
                if current_quantities is None:
                    active = True
                elif other in current_quantities:
                    desired = _strict_nonnegative_int(current_quantities[other], f"current {other}")
                    active = desired > inherited_sell_quantity(orders, other)
            elif step_i != now_i and due <= step_i:
                # Current source can retain already-due rows after zero-stock
                # or partial settlement. They may execute after replenishment,
                # so every row due by this future step reserves until retired.
                active = True
        if active:
            reserved += 1
    return reserved


def inherited_sell_quantity(orders: Sequence[Any], item: str) -> int:
    """Mirror the current scheduler's matching inherited-SELL quantity reader."""
    if not isinstance(orders, (list, tuple)):
        raise LedgerError("orders must be a list or tuple")
    if not isinstance(item, str) or not item:
        raise LedgerError("item must be a non-empty string")
    total = 0
    for index, order in enumerate(orders):
        if not order:
            continue
        if not isinstance(order, (list, tuple)):
            raise LedgerError(f"order {index} must be a list or tuple")
        if order[0] != "SELL" or len(order) < 2 or order[1] != item:
            continue
        if len(order) < 3:
            raise LedgerError(f"matching SELL order {index} lacks quantity")
        total += _strict_nonnegative_int(order[2], f"order {index}.quantity")
    return total


@dataclass(frozen=True)
class SlotDecision:
    feasible: bool
    inherited_rows: int
    cap: int
    inherited_same_item_quantity: int
    requested_quantity: int
    prior_reservations: int
    candidate_needs_extra_row: bool
    reason: str


def reservation_aware_feasible(
    *,
    orders: Sequence[Any],
    cap: int,
    item: str,
    quantity: int,
    planned: Mapping[str, Sequence[Sequence[int]]],
    now: int,
    step: int,
    current_quantities: Mapping[str, int] | None = None,
) -> SlotDecision:
    """Decide only the shared market-row capacity part of plan feasibility."""
    if not isinstance(orders, (list, tuple)):
        raise LedgerError("orders must be a list or tuple")
    cap_i = _strict_nonnegative_int(cap, "cap")
    if cap_i == 0:
        raise LedgerError("cap must be positive")
    quantity_i = _strict_nonnegative_int(quantity, "quantity")
    offered = inherited_sell_quantity(orders, item)
    reserved = planned_slot_reservations(
        planned,
        candidate_item=item,
        now=now,
        step=step,
        current_quantities=current_quantities,
        orders=orders if current_quantities is not None else None,
    )
    needs = quantity_i > offered
    feasible = (not needs) or (len(orders) + reserved < cap_i)
    reason = "INHERITED_ROW" if not needs else ("FREE_RESERVED_SLOT" if feasible else "SLOT_RESERVED")
    return SlotDecision(
        feasible=feasible,
        inherited_rows=len(orders),
        cap=cap_i,
        inherited_same_item_quantity=offered,
        requested_quantity=quantity_i,
        prior_reservations=reserved,
        candidate_needs_extra_row=needs,
        reason=reason,
    )


def predecessor_feasible(*, orders: Sequence[Any], cap: int, item: str, quantity: int) -> bool:
    """Literal current product-local slot predicate, isolated for the witness."""
    offered = inherited_sell_quantity(orders, item)
    if len(orders) >= cap and quantity > offered:
        return False
    return True


def settle_current_extras(
    *,
    orders: Sequence[Any],
    cap: int,
    desired: Mapping[str, int],
    available: Mapping[str, int],
) -> list[list[Any]]:
    """Mirror the current final append loop closely enough to bind the defect."""
    if not isinstance(orders, (list, tuple)):
        raise LedgerError("orders must be a list or tuple")
    out = [list(order) if isinstance(order, (list, tuple)) else order for order in orders]
    remaining = dict(desired)
    stock = dict(available)

    # The predecessor witness has no inherited target SELL rows.  Keep the
    # general matching rewrite here so the portable oracle covers that branch.
    rewritten: list[list[Any]] = []
    for index, raw in enumerate(out):
        if not isinstance(raw, list):
            raise LedgerError(f"order {index} must be list-like")
        order = list(raw)
        if order and order[0] == "SELL" and len(order) > 2 and order[1] in remaining:
            item = order[1]
            requested = _strict_nonnegative_int(order[2], f"order {index}.quantity")
            q = min(requested, max(0, int(remaining.get(item, 0))), max(0, int(stock.get(item, 0))))
            remaining[item] = int(remaining.get(item, 0)) - q
            stock[item] = int(stock.get(item, 0)) - q
            rewritten.append(["SELL", item, q] if q else [])
        else:
            rewritten.append(order)

    for item in sorted(remaining):
        q = min(max(0, int(remaining.get(item, 0))), max(0, int(stock.get(item, 0))))
        if q > 0 and len(rewritten) < cap:
            rewritten.append(["SELL", item, q])
            stock[item] = int(stock.get(item, 0)) - q
    return rewritten


def build_witness() -> dict[str, Any]:
    orders = [["BUY_SEED", "WHEAT", 1] for _ in range(9)]
    planned = {"CARROT": [(100, 1)]}
    desired = {"CARROT": 1, "MILK": 1}
    emitted = settle_current_extras(
        orders=orders,
        cap=10,
        desired=desired,
        available=desired,
    )
    current_predecessor = predecessor_feasible(
        orders=orders, cap=10, item="MILK", quantity=1
    )
    current_successor = reservation_aware_feasible(
        orders=orders,
        cap=10,
        item="MILK",
        quantity=1,
        planned=planned,
        now=100,
        step=100,
        current_quantities=desired,
    )
    future_predecessor = predecessor_feasible(
        orders=orders, cap=10, item="MILK", quantity=1
    )
    future_successor = reservation_aware_feasible(
        orders=orders,
        cap=10,
        item="MILK",
        quantity=1,
        planned={"CARROT": [(101, 1)]},
        now=100,
        step=101,
    )
    overdue_future_successor = reservation_aware_feasible(
        orders=orders,
        cap=10,
        item="MILK",
        quantity=1,
        planned={"CARROT": [(99, 1)]},
        now=100,
        step=101,
    )
    emitted_products = [o[1] for o in emitted if o and o[0] == "SELL"]
    return {
        "schema": "titan-v3-cross-product-slot-reservation-witness-v1",
        "operation": "TITAN-V3-CROSS-PRODUCT-SELL-SLOT-RESERVATION-CLOSURE-20260910-01",
        "current_turn": {
            "inherited_rows": len(orders),
            "cap": 10,
            "prior_planned": {"CARROT": [[100, 1]]},
            "chosen_item": "MILK",
            "chosen_quantity": 1,
            "predecessor_admits": current_predecessor,
            "successor": asdict(current_successor),
            "emitted_products": emitted_products,
            "chosen_item_emitted": "MILK" in emitted_products,
        },
        "future_turn": {
            "now": 100,
            "step": 101,
            "prior_planned": {"CARROT": [[101, 1]]},
            "candidate_item": "MILK",
            "predecessor_admits": future_predecessor,
            "successor": asdict(future_successor),
        },
        "overdue_future_turn": {
            "now": 100,
            "step": 101,
            "prior_planned": {"CARROT": [[99, 1]]},
            "candidate_item": "MILK",
            "predecessor_admits": future_predecessor,
            "successor": asdict(overdue_future_successor),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    witness = build_witness()
    text = json.dumps(witness, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
