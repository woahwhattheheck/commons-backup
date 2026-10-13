# SPDX-License-Identifier: Apache-2.0
"""Fixed-slot T15/ASH feasibility callbacks over the existing SELL ledger.

No optimizer, production controller, engine or source freeze is changed. True is
conditional on the caller's complete lossless continuation and cost bounds. A
failed conservative operating-cash check is unknown, not economic impossibility.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

SALE_PRODUCTS = frozenset((
    "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL",
))


class PlanConflict(ValueError):
    """A concrete plan/slot/quantity conflict, with a non-sensitive reason."""


def _integer(value: Any) -> int:
    if type(value) is not int:
        raise PlanConflict("non_integer_plan_value")
    return value


def _sale(order: Any, item: str) -> bool:
    return (isinstance(order, list) and len(order) >= 3
            and order[:2] == ["SELL", item])


def fixed_market(orders: list, item: str, due: int, slot: int, *,
                 limit: int = 10, reserved_slots: tuple = ()) -> list:
    """Materialize T15's exact queue shape, additionally preserving reservations.

    T15 clears every sale of the lot product, then writes a positive due quantity
    into its one fixed slot. It does NOT use SELL's quantity-replacement routine.
    Empty positions, every other product, and non-SELL positions remain intact.
    """
    due, slot, limit = _integer(due), _integer(slot), _integer(limit)
    if due < 0 or slot < 0 or slot >= limit:
        raise PlanConflict("invalid_quantity_or_slot")
    if not isinstance(orders, list):
        raise ValueError("incomplete_market_queue")
    if due and slot < len(orders) and orders[slot] and not _sale(orders[slot], item):
        raise PlanConflict("fixed_slot_occupied")
    result = deepcopy(orders)
    for i, order in enumerate(result):
        if _sale(order, item):
            result[i] = []
    if due:
        while len(result) <= slot:
            result.append([])
        result[slot] = ["SELL", item, due]
    for i in reserved_slots:
        i = _integer(i)
        if i < 0 or i >= limit:
            raise ValueError("invalid_reservation_slot")
        before = orders[i] if i < len(orders) else []
        after = result[i] if i < len(result) else []
        if before != after:
            raise PlanConflict("reserved_market_slot_changed")
    return result


class PlanFeasibility:
    """An immutable caller snapshot for one decision, reused across plan checks.

    Supply the actual current ``ProjectionLedger`` class. Build a new snapshot
    on every observation/retry whose action, stock, projection or commitments
    changed. ``admit`` is T15's full-constituent callback; ``continuation`` is
    ASH's two-argument callback. Both return exactly True, False or None.

    Reservations use SELL's dated-cash schema. Pass ``selector_reservations()``
    to T15/ASH instead: their cash field is scalar, not a dated event list.
    """

    def __init__(self, ledger_class: type, observation: Mapping[str, Any],
                 configuration: Mapping[str, Any] | None, selected_action: dict,
                 *, post_unit_shed: dict | None, projection: dict | None,
                 arrival_contract: dict | None = None,
                 reservations: dict | None = None):
        self._ledger_class = ledger_class
        self._obs = deepcopy(observation)
        self._cfg = deepcopy(configuration or {})
        self._action = deepcopy(selected_action)
        self._shed = deepcopy(post_unit_shed)
        self._projection = deepcopy(projection)
        self._contract = deepcopy(arrival_contract)
        self._res = deepcopy(reservations or {})
        self.last_check: dict[str, Any] = {"status": "not_checked"}
        self.last_markets: dict[int, list] = {}

    def _now(self) -> int:
        step = self._obs.get("step")
        return _integer(step) if step is not None else (
            _integer(self._obs["day"]) * _integer(self._cfg.get("turnsPerDay", 24))
            + _integer(self._obs["hour"]))

    def selector_reservations(self) -> dict:
        """Separate T15's scalar current cash from SELL's dated commitments."""
        now = self._now()
        cash = max((e["minimum"] for e in self._res.get("cash", [])
                    if e["step"] == now and e["phase"] == "before_market"), default=0)
        return {"cash": cash, "stock": deepcopy(self._res.get("stock", {}))}

    def _finish(self, verdict: bool | None, reason: str) -> bool | None:
        self.last_check = {"status": ("certified" if verdict is True else
                                      "conflict" if verdict is False else "unknown"),
                           "reason": reason, "verdict": verdict}
        return verdict

    def admit(self, plan: dict, *, item: str, slot: int, end: int,
              quantity: int) -> bool | None:
        """Check a full constituent. T15 itself validates all constituents."""
        return self._check(plan, item=item, slot=slot, end=end, quantity=quantity)

    def continuation(self, remaining_plan: dict, context: dict) -> bool | None:
        """Check ASH's remaining schedule against the matching current snapshot."""
        try:
            if (context["now"] != self._now()
                    or context["observation"] != self._obs
                    or (context["configuration"] or {}) != self._cfg
                    or context["post_unit_shed"] != self._shed
                    or context["reservations"] != self.selector_reservations()):
                return self._finish(None, "stale_or_mismatched_caller_snapshot")
            return self._check(remaining_plan, item=context["item"],
                               slot=context["slot"], end=context["end"],
                               quantity=context["remaining_quantity"])
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return self._finish(None, "incomplete_continuation_context")

    def _check(self, plan: dict, *, item: str, slot: int, end: int,
               quantity: int) -> bool | None:
        self.last_markets = {}
        try:
            now = self._now()
            end, slot, quantity = _integer(end), _integer(slot), _integer(quantity)
            last = _integer(self._cfg.get("episodeSteps", 720)) - 2
            if item not in SALE_PRODUCTS:
                return self._finish(None, "unsupported_lot_product")
            if quantity <= 0 or not now <= end <= last:
                raise PlanConflict("invalid_quantity_or_dates")
            if end - now > 8:
                return self._finish(None, "beyond_bounded_ledger_horizon")
            sales = plan["sales"]
            if not isinstance(sales, (list, tuple)):
                raise PlanConflict("invalid_plan_schedule")
            schedule = {}
            for row in sales:
                if not isinstance(row, (list, tuple)) or len(row) != 2:
                    raise PlanConflict("invalid_plan_row")
                step, count = _integer(row[0]), _integer(row[1])
                if step in schedule or not now <= step <= end or count < 0:
                    raise PlanConflict("duplicate_or_invalid_plan_date")
                schedule[step] = count
            if sum(schedule.values()) != quantity:
                raise PlanConflict("incomplete_planned_quantity")
            completion = max(t for t, q in schedule.items() if q)
            if self._shed is None or self._projection is None:
                return self._finish(None, "missing_caller_projection")
            projection = deepcopy(self._projection)
            if projection["observed_step"] != now or projection["end_step"] < end:
                return self._finish(None, "projection_does_not_cover_plan")
            future = {int(t): orders for t, orders in projection["future_market"].items()}
            # Missing dates must not silently become empty order queues.
            if any(t not in future for t in range(now + 1, end + 1)):
                return self._finish(None, "missing_future_market_date")
            current = self._action.get("market", [])
            if now in future and future[now] != current:
                return self._finish(None, "current_action_projection_disagrees")
            projection["future_market"] = {t: q for t, q in future.items() if t <= end}
            projection["end_step"] = end
            snapshot = self

            class FixedSlotLedger(self._ledger_class):
                def market(self, step, product, due, stock):
                    inherited = self.future.get(step, [])
                    # T15 releases the key after its last positive sale. After
                    # that decision the normal caller queue resumes unchanged.
                    if step > completion:
                        return deepcopy(inherited)
                    if due > stock - self.stock_min.get(product, 0):
                        raise PlanConflict("planned_sale_exceeds_unreserved_stock")
                    queue = fixed_market(inherited, product, due, slot,
                                         limit=self.max_orders,
                                         reserved_slots=self.reserved_slots.get(step, ()))
                    snapshot.last_markets[step] = deepcopy(queue)
                    return queue

            ledger = FixedSlotLedger(deepcopy(self._obs), deepcopy(self._cfg),
                                     deepcopy(self._action), deepcopy(self._shed),
                                     projection, deepcopy(self._contract),
                                     deepcopy(self._res), 8)
            result = ledger.feasible(item, tuple(schedule.items()))
            # A low guaranteed sale-cash bound can reject a truly affordable
            # action. Do not report that as a mathematical impossibility.
            return self._finish(True if result is True else None,
                                "conditional_ledger_pass" if result is True else
                                "conditional_ledger_not_certified")
        except PlanConflict as error:
            return self._finish(False, str(error))
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return self._finish(None, "incomplete_or_unsupported_caller_facts")
