"""Observation-only opponent perturbations for a frozen Kaggriculture league.

These are stress opponents, not claims of improved play. Decisions use only the
same observation and action that the original policy receives/returns. No hidden
state, environment seed, persistent game history, or future shop schedule enters
this module. Emergency/full-shed and final-day exceptions avoid trivial stranding.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

VARIANTS = ("sale_cadence", "crop_demand", "labor_cadence")
CROPS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"}
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")


def _time(observation: dict, configuration: Any) -> tuple[int, int, int]:
    cfg = configuration if isinstance(configuration, dict) else {}
    per_day = max(1, int(cfg.get("turnsPerDay", 24)))
    if "episodeSteps" in cfg:
        # Official actions run from step 0 through episodeSteps - 2 inclusive.
        # The terminal recorded state is not another opportunity to sell.
        last_action_step = max(0, int(cfg["episodeSteps"]) - 2)
        days = last_action_step // per_day + 1
    else:
        days = max(1, int(cfg.get("days", 30)))
    if "step" in observation:
        step = int(observation["step"])
        day, hour = divmod(step, per_day)
    else:
        day, hour = int(observation.get("day", 0)), int(observation.get("hour", 0))
    return day, hour, days


def _may_delay(observation: dict, configuration: Any) -> bool:
    day, hour, days = _time(observation, configuration)
    private = observation.get("private", {})
    shed = private.get("shed", {})
    cfg = configuration if isinstance(configuration, dict) else {}
    capacity = private.get("shed_capacity", cfg.get("shedCapacity", 100))
    used = sum(v for v in shed.values() if isinstance(v, (int, float)))
    return day < days - 1 and used < 0.8 * capacity and hour % 4 != 0


def _configuration_value(configuration: Any, key: str, default: Any) -> Any:
    """Mirror the pinned engine's dict-or-attribute configuration lookup."""
    if isinstance(configuration, dict):
        return configuration.get(key, default)
    return getattr(configuration, key, default)


def _market_limit(configuration: Any) -> int:
    """Mirror the pinned engine's raw market-prefix limit exactly."""
    return max(1, int(_configuration_value(configuration, "maxMarketOrdersPerTurn", 10)))


def _sell_item(order: Any) -> str | None:
    """Return the item only for a SELL the pinned engine can actually execute.

    ``int`` coercion and its exceptions intentionally mirror ``_parse_order``:
    TypeError/ValueError make the row inert, while OverflowError remains fatal.
    Trailing fields are accepted by the engine and therefore by this classifier.
    """
    if not isinstance(order, list) or len(order) < 3 or order[0] != "SELL":
        return None
    try:
        quantity = int(order[2])
    except (TypeError, ValueError):
        return None
    if quantity <= 0:
        return None
    item = order[1]
    if not isinstance(item, str) or item not in PRODUCTS:
        return None
    return item


def _is_hire(order: Any) -> bool:
    """Match the pinned engine's atomic HIRE grammar, including trailing fields."""
    return isinstance(order, list) and bool(order) and order[0] == "HIRE"


def transform(action: dict, observation: dict, variant: str,
              shops: dict, configuration: Any = None) -> dict:
    """Return a fresh action with only executable prefix rows filtered in place.

    The engine first slices the raw market list to ``maxMarketOrdersPerTurn`` and
    only then parses each slot. Rebuilding the list by deletion can therefore
    pull a capped suffix order into execution. Variant suppression is represented
    as ``[]`` at the original raw index so market topology and the capped suffix
    remain byte-for-byte stable.
    """
    if variant not in VARIANTS:
        raise ValueError("unknown opponent variant: " + variant)
    if not isinstance(action, dict):
        raise ValueError("parent policy returned an invalid action shape")
    result = copy.deepcopy(action)
    market = action.get("market", [])
    # The pinned engine treats a non-list market container as an empty queue.
    # Preserve the legacy non-dict parent contract, but do not turn inert market
    # bytes into a transform error.
    if not isinstance(market, list):
        return result

    orders = result.get("market", [])
    end = min(len(orders), _market_limit(configuration))
    if variant in ("sale_cadence", "crop_demand") and not _may_delay(observation, configuration):
        return result

    if variant == "sale_cadence":
        for index in range(end):
            if _sell_item(orders[index]) is not None:
                orders[index] = []
    elif variant == "crop_demand":
        unlocked = observation.get("town", {}).get("unlocked_shops", [])
        demand: Counter = Counter()
        for name in unlocked:
            # The official engine maps each shop name to a list of product names.
            # Duplicate unlocked shops are real demand and remain counted.
            demand.update(x for x in shops.get(name, []) if x in CROPS)
        peak = max(demand.values(), default=0)
        if peak:
            for index in range(end):
                item = _sell_item(orders[index])
                if item in CROPS and demand[item] < peak:
                    orders[index] = []
    else:
        _, hour, _ = _time(observation, configuration)
        hires = 0
        for index in range(end):
            if not _is_hire(orders[index]):
                continue
            hires += 1
            if hour % 2 or hires > 1:
                orders[index] = []
    return result


def actor_class(base: type, shops: dict) -> type:
    """Compose with cloud-eval.Actor without changing its process/IPC isolation."""
    class VariantActor(base):
        def __init__(self, spec: str, *args: Any, **kwargs: Any):
            parent, sep, variant = spec.partition("|league=")
            self.variant = variant if sep else ""
            if self.variant and self.variant not in VARIANTS:
                raise ValueError("unknown opponent variant: " + self.variant)
            super().__init__(parent, *args, **kwargs)
            self.stats["league_variant"] = self.variant or "intact"
            self.stats["league_changed_turns"] = 0

        def act(self, observation: dict, configuration: Any, timeout: float):
            response = super().act(observation, configuration, timeout)
            if self.variant and response.get("kind") == "action":
                result = transform(response["action"], observation, self.variant, shops, configuration)
                if result != response["action"]:
                    self.stats["league_changed_turns"] += 1
                response = dict(response, action=result)
            return response

    return VariantActor
