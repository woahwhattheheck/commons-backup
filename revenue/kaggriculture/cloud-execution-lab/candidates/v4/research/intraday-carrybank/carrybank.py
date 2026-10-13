from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

CONSUMABLE_BY_ACTION = {
    "FEED": "WHEAT",
    "FERTILIZE": "FERTILIZER",
}
PREFERRED_ITEMS = ("WHEAT", "FERTILIZER")


@dataclass(frozen=True)
class CarrybankDecision:
    """A fail-closed same-day inventory-hoist decision."""

    item: str
    quantity: int
    pressure_units: int
    guaranteed_consumption_units: int

    def action(self) -> list[object]:
        return ["PICKUP", self.item, self.quantity]


def _op(action: object) -> str:
    if isinstance(action, (list, tuple)) and action:
        return str(action[0]).upper()
    return ""


def _pickup_quantity(action: object, item: str) -> int | None:
    """Return the authored pickup quantity for ``item``, or ``None`` if unrelated."""
    if not isinstance(action, (list, tuple)) or len(action) < 2 or _op(action) != "PICKUP":
        return None
    if action[1] != item:
        return None
    if len(action) < 3:
        return 1
    try:
        quantity = int(action[2])
    except (TypeError, ValueError):
        raise ValueError("malformed pickup quantity")
    if quantity <= 0:
        raise ValueError("nonpositive pickup quantity")
    return quantity


def _future_consumption(
    future_unit_actions: Sequence[object],
    turns_remaining: int,
    current_inventory: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Guaranteed *additional* carried-input sink capacity in this continuation.

    Sink capacity is net of carried stock and authored actions that can add the same
    input. DROP truncates the guarantee because relying on it is lossy by contract.
    WHEAT capacity is unprovable across HARVEST without an item-level projection.
    """
    remaining = max(0, int(turns_remaining))
    actions = list(future_unit_actions[:remaining])
    inventory = current_inventory or {}
    capacity: dict[str, int] = {}

    for item in PREFERRED_ITEMS:
        sinks = 0
        burden = max(0, int(inventory.get(item, 0)))
        unsafe_unknown_gain = False
        for action in actions:
            op = _op(action)
            if op == "DROP":
                break
            try:
                pickup = _pickup_quantity(action, item)
            except ValueError:
                unsafe_unknown_gain = True
                break
            if pickup is not None:
                burden += pickup
                continue
            if item == "FERTILIZER" and op == "COLLECT_FERTILIZER":
                burden += 1
                continue
            if item == "WHEAT" and op == "HARVEST":
                unsafe_unknown_gain = True
                break
            if CONSUMABLE_BY_ACTION.get(op) == item:
                sinks += 1
        capacity[item] = 0 if unsafe_unknown_gain else max(0, sinks - burden)
    return capacity


def admit_carrybank_pickup(
    *,
    current_unit_action: object,
    adjacent_to_shed: bool,
    shed: Mapping[str, int],
    shed_capacity: int,
    projected_shed_inflow_units: int,
    current_inventory: Mapping[str, int],
    future_unit_actions: Sequence[object],
    turns_remaining: int,
) -> CarrybankDecision | None:
    """
    Admit a proactive PICKUP only when it is capacity-useful and same-day-consumable.

    This helper is deliberately narrow:
      * it may replace only a current PASS, never productive work;
      * the actor must already be adjacent to SHED;
      * only WHEAT/FERTILIZER qualify because FEED/FERTILIZE are carried-item sinks;
      * pickup quantity is capped by projected shed-capacity pressure;
      * pickup quantity is capped by *additional guaranteed* same-day consumption after
        accounting for inventory already carried and future input acquisition.

    The official engine silently destroys DROP overflow and discards carried overflow
    at end-of-day shed return. Therefore this helper never relies on DROP or EOD return
    to make a hoist safe.
    """
    if _op(current_unit_action) != "PASS":
        return None
    if not adjacent_to_shed:
        return None

    capacity = max(0, int(shed_capacity))
    used = sum(max(0, int(v)) for v in shed.values())
    room = max(0, capacity - used)
    pressure = max(0, int(projected_shed_inflow_units) - room)
    if pressure <= 0:
        return None

    additional_capacity = _future_consumption(
        future_unit_actions, turns_remaining, current_inventory)
    candidates: list[tuple[int, int, str]] = []
    for priority, item in enumerate(PREFERRED_ITEMS):
        available = max(0, int(shed.get(item, 0)))
        quantity = min(pressure, available, additional_capacity[item])
        if quantity > 0:
            candidates.append((quantity, -priority, item))

    if not candidates:
        return None

    quantity, _neg_priority, item = max(candidates)
    return CarrybankDecision(
        item=item,
        quantity=quantity,
        pressure_units=pressure,
        guaranteed_consumption_units=additional_capacity[item],
    )
