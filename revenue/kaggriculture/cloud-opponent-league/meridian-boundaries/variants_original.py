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


def _time(observation: dict, configuration: Any) -> tuple[int, int, int]:
    cfg = configuration if isinstance(configuration, dict) else {}
    per_day = int(cfg.get("turnsPerDay", 24))
    days = int(cfg.get("days", 30))
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
    capacity = private.get("shed_capacity", cfg.get("shedCapacity", 1000))
    used = sum(v for v in shed.values() if isinstance(v, (int, float)))
    return day < days - 1 and used < 0.8 * capacity and hour % 4 != 0


def transform(action: dict, observation: dict, variant: str,
              shops: dict, configuration: Any = None) -> dict:
    """Return a fresh action with only market orders filtered, never invented."""
    if variant not in VARIANTS:
        raise ValueError("unknown opponent variant: " + variant)
    if not isinstance(action, dict) or not isinstance(action.get("market", []), list):
        raise ValueError("parent policy returned an invalid action shape")
    result = copy.deepcopy(action)
    orders = result.get("market", [])
    if variant in ("sale_cadence", "crop_demand") and not _may_delay(observation, configuration):
        return result
    if variant == "sale_cadence":
        result["market"] = [o for o in orders if not (isinstance(o, list) and o and o[0] == "SELL")]
    elif variant == "crop_demand":
        unlocked = observation.get("town", {}).get("unlocked_shops", [])
        demand: Counter = Counter()
        for name in unlocked:
            # The official engine maps each shop name to a list of product names.
            # Duplicate unlocked shops are real demand and remain counted.
            demand.update(x for x in shops.get(name, []) if x in CROPS)
        peak = max(demand.values(), default=0)
        if peak:
            result["market"] = [o for o in orders if not (
                isinstance(o, list) and len(o) >= 2 and o[0] == "SELL"
                and o[1] in CROPS and demand[o[1]] < peak)]
    else:
        _, hour, _ = _time(observation, configuration)
        hires = 0
        filtered = []
        for order in orders:
            if isinstance(order, list) and order and order[0] == "HIRE":
                hires += 1
                if hour % 2 or hires > 1:
                    continue
            filtered.append(order)
        result["market"] = filtered
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
