"""Observation-only, same-service-calendar cow/sheep counterfactuals.

Independent implementation of the public pinned Kaggriculture animal rules.
The caller supplies a feasible, ordered visit calendar and available feed. This
module does not route workers, predict hidden stock, deposit goods, or sell them.
A harvest receipt is carried product, NEVER cash or proof of a feasible sale.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
ANIMALS = {
    "COW": {"cost": 400, "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}
OPS = frozenset({"PASS", "FEED", "CARE", "HARVEST", "COLLECT_FERTILIZER"})


@dataclass(frozen=True)
class ServiceAction:
    """One worker's action while visiting the target pasture.

    unit is the actual farmer/hand index (farmer=0); same-step actions resolve in
    increasing unit order. wheat_available describes this worker's inventory at
    that action, after earlier transfers. Zero is the conservative default. It
    is not a new purchase, free feed, or shared shed stock. Input dates must be
    feasible under the caller's route; omitted visits mean no service.
    """
    step: int
    op: str
    unit: int = 0
    wheat_available: int = 0


def _integer(value: int, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _species(name: str) -> dict:
    if name not in ANIMALS:
        raise ValueError("species must be COW or SHEEP")
    return ANIMALS[name]


def _calendar(actions: Iterable[ServiceAction], placement: int, last: int) -> list[ServiceAction]:
    events = list(actions)
    seen: set[tuple[int, int]] = set()
    for event in events:
        if not isinstance(event, ServiceAction):
            raise TypeError("calendar entries must be ServiceAction values")
        _integer(event.step, "step")
        _integer(event.unit, "unit")
        _integer(event.wheat_available, "wheat_available")
        if not placement <= event.step <= last:
            raise ValueError("service step is outside the supplied placement/horizon")
        if event.op not in OPS:
            raise ValueError(f"unsupported service operation: {event.op}")
        key = (event.step, event.unit)
        if key in seen:
            raise ValueError("a worker cannot perform two actions in one step")
        seen.add(key)
    return sorted(events, key=lambda event: (event.step, event.unit))


def project_calendar(
    species: str,
    placement_step: int,
    actions: Iterable[ServiceAction],
    *,
    episode_steps: int = 720,
    turns_per_day: int = 24,
    last_action_step: int | None = None,
    include_trace: bool = False,
) -> dict:
    """Project one hypothetical *new placement*, not a live-animal conversion.

    Both alternatives begin at the identical successful placement step. Animal
    purchase, pickup, placement feasibility and worker visits are caller-owned.
    Production at a day boundary is available only on the next action; CARE at
    that boundary contributes AFTER production. The normal 720-step game ends
    after decision 718, so boundary 719 is not executed or credited.
    """
    spec = _species(species)
    _integer(episode_steps, "episode_steps", 2)
    _integer(turns_per_day, "turns_per_day", 1)
    _integer(placement_step, "placement_step")
    last = episode_steps - 2 if last_action_step is None else _integer(last_action_step, "last_action_step")
    if placement_step > last or last > episode_steps - 2:
        raise ValueError("placement and horizon must end by the last executable decision")
    calendar = _calendar(actions, placement_step, last)
    by_step: dict[int, list[ServiceAction]] = {}
    for event in calendar:
        by_step.setdefault(event.step, []).append(event)
    tile: dict = {
        "kind": "PASTURE", "animal": species,
        "placed_day": placement_step // turns_per_day, "yield_units": 0,
        "consecutive_unfed": 0, "fed_today": False, "cared_today": False,
        "fertilizer_available": False, "pending_care_bonus": 0,
    }
    harvests: list[dict] = []
    production: list[dict] = []
    feed: list[dict] = []
    fertilizer: list[dict] = []
    trace: list[dict] = []
    lost_to_cap = lost_on_escape = discarded_bonus = 0
    escape_step = None
    action_results: list[dict] = []
    for step in range(placement_step, last + 1):
        for event in by_step.get(step, []):
            before = dict(tile)
            alive = "animal" in tile
            units = 0
            if alive and event.op == "FEED" and not tile["fed_today"] and event.wheat_available > 0:
                tile["fed_today"] = True
                feed.append({"step": step, "unit": event.unit, "units": 1})
                units = 1
            elif alive and event.op == "CARE" and not tile["cared_today"]:
                tile["cared_today"] = True
            elif alive and event.op == "HARVEST" and tile["yield_units"] > 0:
                units = tile["yield_units"]
                tile["yield_units"] = 0
                harvests.append({"step": step, "unit": event.unit, "product": spec["product"], "units": units})
            elif alive and event.op == "COLLECT_FERTILIZER" and tile["fertilizer_available"]:
                tile["fertilizer_available"] = False
                units = 1
                fertilizer.append({"step": step, "unit": event.unit, "units": 1})
            action_results.append({"step": step, "unit": event.unit, "op": event.op,
                                   "applied": tile != before, "units": units})
            if include_trace:
                trace.append({"step": step, "phase": "action", "unit": event.unit, "tile": dict(tile)})
        if (step + 1) % turns_per_day == 0 and "animal" in tile:
            day = step // turns_per_day
            tile["consecutive_unfed"] = 0 if tile["fed_today"] else tile["consecutive_unfed"] + 1
            if tile["consecutive_unfed"] >= 2:
                lost_on_escape += tile["yield_units"]
                discarded_bonus += tile["pending_care_bonus"]
                escape_step = step
                tile = {"kind": "PASTURE"}
            else:
                age = day + 1 - tile["placed_day"] - spec["first_yield_day"]
                if age >= 0 and age % spec["interval"] == 0:
                    pending = tile["pending_care_bonus"]
                    bonus = pending if tile["fed_today"] else 0
                    discarded_bonus += pending - bonus
                    gross = 1 + bonus  # Base production does not require feeding.
                    retained = min(gross, spec["max_held"] - tile["yield_units"])
                    tile["yield_units"] += retained
                    lost_to_cap += gross - retained
                    production.append({"step": step, "available_step": step + 1,
                                       "base_units": 1, "care_units": bonus,
                                       "retained_units": retained, "lost_to_cap": gross - retained,
                                       "discarded_unfed_bonus": pending - bonus})
                    tile["pending_care_bonus"] = 0
                # This day's CARE is carried forward, never spent in the event above.
                if tile["cared_today"] and tile["fed_today"]:
                    tile["pending_care_bonus"] += 1
                tile["fertilizer_available"] = True
                tile["fed_today"] = tile["cared_today"] = False
            if include_trace:
                trace.append({"step": step, "phase": "daily", "tile": dict(tile)})
    result = {
        "schema": "titan.livestock-calendar.v1", "engine_ref": ENGINE_REF,
        "species": species, "placement_step": placement_step, "last_action_step": last,
        "purchase_cost": spec["cost"], "harvest_receipts": harvests,
        "feed_receipts": feed, "fertilizer_receipts": fertilizer,
        "production_events": production, "action_results": action_results,
        "feed_units": len(feed), "harvested_units": sum(r["units"] for r in harvests),
        "lost_to_cap": lost_to_cap, "lost_on_escape": lost_on_escape,
        "discarded_care_bonus": discarded_bonus, "escape_step": escape_step,
        "terminal_tile": dict(tile), "terminal_held_units": tile.get("yield_units", 0),
        "cash_receipts": None,
        "scope": "Conditional on caller-supplied feasible visits and feed; harvest is carried stock, not a sale.",
    }
    if include_trace:
        result["trace"] = trace
    return result


def compare_species(
    placement_step: int,
    actions: Iterable[ServiceAction],
    *,
    baseline: str = "COW",
    candidate: str = "SHEEP",
    **projection_options,
) -> dict:
    """Return both dated ledgers without treating milk and wool as fungible cash."""
    calendar = tuple(actions)  # Generators must feed both alternatives identically.
    old = project_calendar(baseline, placement_step, calendar, **projection_options)
    new = project_calendar(candidate, placement_step, calendar, **projection_options)
    return {"schema": "titan.livestock-pair.v1", "baseline": old, "candidate": new,
            "candidate_minus_baseline": {
                "purchase_cost": new["purchase_cost"] - old["purchase_cost"],
                "feed_units": new["feed_units"] - old["feed_units"],
                "cash": None,
            },
            "valuation_inputs_required": [
                "legal ordered collection/deposit/sale dates and shared capacity",
                "feed and displaced-purchase opportunity costs",
                "paired own/rival market scenarios with the same uncertainty assumptions",
            ]}


def purchase_checkpoint(
    cash_before_buy: int,
    shed_units_before_buy: int,
    *,
    reserve_after_buy: int = 0,
    shed_capacity: int = 100,
    baseline: str = "COW",
    candidate: str = "SHEEP",
) -> dict:
    """Compare one-unit BUY_ANIMAL at its actual market-order checkpoint.

    Caller must project all preceding unit actions and market orders first.
    reserve_after_buy is an explicit caller-estimated obligation, not an arbitrary
    worker cap. This does not imply feasible pickup/placement or invent sales.
    """
    _integer(cash_before_buy, "cash_before_buy")
    _integer(shed_units_before_buy, "shed_units_before_buy")
    _integer(reserve_after_buy, "reserve_after_buy")
    _integer(shed_capacity, "shed_capacity", 1)
    result = {}
    for name, species in (("baseline", baseline), ("candidate", candidate)):
        cost = _species(species)["cost"]
        affordable = cash_before_buy >= cost
        room = shed_units_before_buy < shed_capacity
        result[name] = {"species": species, "cost": cost,
                        "engine_purchase_possible": affordable and room,
                        "cash_after_if_purchased": cash_before_buy - cost if affordable and room else None,
                        "preserves_cash_reserve": affordable and room and cash_before_buy - cost >= reserve_after_buy}
    result["capital_delta"] = _species(candidate)["cost"] - _species(baseline)["cost"]
    return result
