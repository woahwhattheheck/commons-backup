# SPDX-License-Identifier: Apache-2.0
"""W2 service salvage, evaluated in the interpreter's farmer/hand order.

Candidate-only: call BEFORE the native selected checkpoint and consumer, not
as an outer agent wrapper. No configuration or production default is changed.
A literal FEED may become CARE only after a successful earlier same-site FEED
(or an observed fed flag). A failed first FEED is never presumed successful.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

# structure, first production day, production interval, product capacity
ANIMALS = {
    "GOOSE": ("COOP", 4, 1, 4),
    "COW": ("PASTURE", 8, 2, 6),
    "SHEEP": ("PASTURE", 6, 3, 6),
}
telemetry: Counter = Counter()


def _cfg(configuration: Any, key: str) -> Any:
    if isinstance(configuration, dict):
        return configuration.get(key)
    return getattr(configuration, key, None)


def _position(value: Any):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(v) is not int or not 0 <= v < 10 for v in value)):
        return None
    return tuple(value)


def _animal(tile: Any, day: int):
    if not isinstance(tile, dict):
        return None
    species = tile.get("animal")
    if not isinstance(species, str) or species not in ANIMALS:
        return None
    kind, first, interval, maximum = ANIMALS[species]
    placed, units = tile.get("placed_day"), tile.get("yield_units")
    bonus, unfed = tile.get("pending_care_bonus"), tile.get("consecutive_unfed")
    if (tile.get("kind") != kind or type(placed) is not int
            or not 0 <= placed <= day or type(units) is not int
            or not 0 <= units <= maximum or type(bonus) is not int
            or not 0 <= bonus <= day - placed + 1 or type(unfed) is not int
            or not 0 <= unfed <= 1
            or any(type(tile.get(k)) is not bool
                   for k in ("fed_today", "cared_today", "fertilizer_available"))):
        return None
    # EOD consumes the OLD bank before banking today's CARE. Today's new bank
    # needs a production boundary >= day+2, and an EOD before terminal step718.
    first_usable = max(placed + first, day + 2)
    first_usable += (placed + first - first_usable) % interval
    return {"species": species, "fed": tile["fed_today"],
            "cared": tile["cared_today"], "observed_fed": tile["fed_today"],
            "first_usable_day": first_usable, "useful": first_usable <= 29}


def plan_dead_feed_care(action: Any, observation: Any, configuration: Any) -> list[dict]:
    """Return prospective rewrites without mutating input or global telemetry.

    Strict JSON-shaped custody avoids phantom workers, shared inventory/tile
    aliases, invented wheat, or actor-row compaction. No transition is executed.
    Only existing placed animal tiles can be candidates; placement remains cold.
    """
    for key, expected in (("boardSize", 10), ("turnsPerDay", 24), ("episodeSteps", 720)):
        value = _cfg(configuration, key)
        if type(value) is not int or value != expected:
            return []
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return []
    step, player = observation.get("step"), observation.get("player")
    farms = observation.get("farms")
    if (type(step) is not int or not 0 <= step <= 718
            or type(player) is not int or player not in (0, 1)
            or not isinstance(farms, list) or len(farms) != 2):
        return []
    farm, private = farms[player], observation.get("private")
    if not isinstance(farm, dict) or not isinstance(private, dict):
        return []
    hands, tiles = farm.get("hands"), farm.get("tiles")
    rows, farmer = action.get("hands"), action.get("farmer")
    if (not isinstance(hands, list) or not isinstance(rows, list)
            or len(rows) != len(hands) or not isinstance(action.get("market"), list)
            or not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)):
        return []
    positions = [_position(p) for p in [farm.get("farmer"), *hands]]
    commands = [farmer, *rows]
    if any(p is None for p in positions):
        return []
    if any(not isinstance(row, list) or not row or type(row[0]) is not str
           for row in commands):
        return []
    inventories = private.get("inventories")
    if (not isinstance(inventories, list)
            or any(not isinstance(inv, dict) for inv in inventories)
            or len({id(inv) for inv in inventories}) != len(inventories)
            or any(inv is private.get("shed") or inv is private.get("seeds")
                   for inv in inventories)):
        return []
    wheat = [inv.get("WHEAT", 0) for inv in inventories]
    if any(type(n) is not int or n < 0 for n in wheat):
        return []
    tile_ids = [id(tile) for row in tiles for tile in row if isinstance(tile, dict)]
    if len(tile_ids) != len(set(tile_ids)):
        return []
    # A later authored CARE already subsumes this turn's optional rewrite.
    care_sites = {site for site, row in zip(positions, commands) if row[0] == "CARE"}
    day, sites, changes = step // 24, {}, []
    for actor, (site, row) in enumerate(zip(positions, commands)):
        if site not in sites:
            sites[site] = _animal(tiles[site[1]][site[0]], day)
        animal = sites[site]
        if animal is None:
            continue
        op = row[0]
        if op == "CARE":
            animal["cared"] = True
        elif op == "FEED":
            if not animal["fed"]:
                # Each actor acts once. Other actors cannot add to THIS bag.
                # Missing physical inventories are created empty by the engine.
                if actor < len(wheat) and wheat[actor] >= 1:
                    animal["fed"] = True
            elif (row == ["FEED"] and not animal["cared"] and animal["useful"]
                  and site not in care_sites):
                changes.append({"actor": actor, "site": list(site),
                                "species": animal["species"],
                                "reason": "observed_fed" if animal["observed_fed"] else "ordered_feed",
                                "first_usable_day": animal["first_usable_day"]})
                # Simulate the candidate CARE so repeated FEED rows do not
                # produce several redundant CARE rewrites at the same site.
                animal["cared"] = True
    return changes


def apply_dead_feed_care(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Keep identity on disabled/no-match; clone and alter only certified rows."""
    if enabled is not True:
        return action
    changes = plan_dead_feed_care(action, observation, configuration)
    if not changes:
        return action
    result = deepcopy(action)
    for change in changes:
        actor = change["actor"]
        if actor == 0:
            result["farmer"] = ["CARE"]
        else:
            result["hands"][actor - 1] = ["CARE"]
    # Record only after building the complete output. Not an observed-fill or
    # profit claim; a later native transform/fallback can still replace it.
    for change in changes:
        telemetry["rewrites"] += 1
        telemetry[change["reason"]] += 1
        telemetry[change["species"]] += 1
    return result


def _carebank_animal(tile: Any, day: int):
    """Return exact old-bank-at-risk facts for a placed animal, or ``None``."""
    if not isinstance(tile, dict):
        return None
    species = tile.get("animal")
    if not isinstance(species, str) or species not in ANIMALS:
        return None
    kind, first, interval, maximum = ANIMALS[species]
    placed = tile.get("placed_day")
    units = tile.get("yield_units")
    pending = tile.get("pending_care_bonus")
    unfed = tile.get("consecutive_unfed")
    if (tile.get("kind") != kind
            or type(placed) is not int or not 0 <= placed <= day
            or type(units) is not int or not 0 <= units <= maximum
            or type(pending) is not int or not 0 <= pending <= day - placed + 1
            or type(unfed) is not int or unfed not in (0, 1)
            or any(type(tile.get(k)) is not bool
                   for k in ("fed_today", "cared_today", "fertilizer_available"))):
        return None
    age = day + 1 - placed - first
    production_due = age >= 0 and age % interval == 0
    headroom_after_base = max(0, maximum - units - 1)
    realizable_bonus = min(pending, headroom_after_base)
    return {
        "species": species,
        "fed": tile["fed_today"],
        "cared": tile["cared_today"],
        "fertilizer_available": tile["fertilizer_available"],
        "unfed": unfed,
        "pending": pending,
        "production_due": production_due,
        "yield_units": units,
        "max_held": maximum,
        "realizable_bonus": realizable_bonus,
    }


def _no_future_feed_before_eod(route: Any, step: int) -> dict | None:
    """Certify that authored remaining same-day rows cannot FEED any animal.

    This deliberately over-blocks: a FEED anywhere in the remaining route is
    enough to decline. Unknown rows or a future HIRE also decline, because a
    dynamically added hand would make a static absence proof incomplete.
    """
    hour = step % 24
    eod_step = step + (23 - hour)
    if eod_step == step:
        return {"from_step": step + 1, "eod_step": eod_step, "checked_steps": 0}
    if not isinstance(route, list) or eod_step >= len(route):
        return None
    for future_step in range(step + 1, eod_step + 1):
        authored = route[future_step]
        if not isinstance(authored, dict):
            return None
        farmer = authored.get("farmer", ["PASS"])
        hands = authored.get("hands", [])
        market = authored.get("market", [])
        if (not isinstance(farmer, list) or not farmer or type(farmer[0]) is not str
                or not isinstance(hands, list) or not isinstance(market, list)):
            return None
        commands = [farmer, *hands]
        if any(not isinstance(row, list) or not row or type(row[0]) is not str
               for row in commands):
            return None
        if any(row[0] == "FEED" for row in commands):
            return None
        for order in market:
            if not isinstance(order, list) or not order or type(order[0]) is not str:
                return None
            if order[0] == "HIRE":
                return None
    return {"from_step": step + 1, "eod_step": eod_step,
            "checked_steps": eod_step - step}


def plan_carebank_feed_swap(action: Any, observation: Any, configuration: Any,
                            route: Any) -> list[dict]:
    """Return conservative COLLECT_FERTILIZER->FEED old-CARE-bank salvage.

    The transform is only an admission candidate. It proves the old CARE bank
    would otherwise be at risk on this day's production boundary, that at least
    one bonus product unit can physically fit after base production, and that
    the replaced fertilizer collection and consumed WHEAT are both source-real.
    It never asserts economic acceptance.
    """
    for key, expected in (("boardSize", 10), ("turnsPerDay", 24), ("episodeSteps", 720)):
        value = _cfg(configuration, key)
        if type(value) is not int or value != expected:
            return []
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return []
    step, player = observation.get("step"), observation.get("player")
    farms, private = observation.get("farms"), observation.get("private")
    if (type(step) is not int or not 0 <= step <= 718
            or type(player) is not int or player not in (0, 1)
            or not isinstance(farms, list) or len(farms) != 2
            or not isinstance(private, dict)):
        return []
    farm = farms[player]
    if not isinstance(farm, dict):
        return []
    hands, tiles = farm.get("hands"), farm.get("tiles")
    hand_rows, farmer_row, market = action.get("hands"), action.get("farmer"), action.get("market")
    if (not isinstance(hands, list) or not isinstance(hand_rows, list)
            or len(hand_rows) != len(hands) or not isinstance(market, list)
            or not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)):
        return []
    positions = [_position(p) for p in [farm.get("farmer"), *hands]]
    rows = [farmer_row, *hand_rows]
    if any(p is None for p in positions):
        return []
    if any(not isinstance(row, list) or not row or type(row[0]) is not str for row in rows):
        return []
    inventories = private.get("inventories")
    if (not isinstance(inventories, list) or len(inventories) != len(positions)
            or any(not isinstance(inv, dict) for inv in inventories)
            or len({id(inv) for inv in inventories}) != len(inventories)
            or any(inv is private.get("shed") or inv is private.get("seeds")
                   for inv in inventories)):
        return []
    wheat = []
    for inv in inventories:
        amount = inv.get("WHEAT", 0)
        if type(amount) is not int or amount < 0:
            return []
        if any(type(n) is not int or n < 0 for n in inv.values()):
            return []
        wheat.append(amount)
    tile_ids = [id(tile) for row in tiles for tile in row if isinstance(tile, dict)]
    if len(tile_ids) != len(set(tile_ids)):
        return []
    # A current HIRE can create a new hand whose later authored service row is
    # outside this static pre-HIRE surface. Decline rather than certify absence.
    for order in market:
        if not isinstance(order, list) or not order or type(order[0]) is not str:
            return []
        if order[0] == "HIRE":
            return []
    route_cert = _no_future_feed_before_eod(route, step)
    if route_cert is None:
        return []

    # Any authored FEED on the same site in THIS callback can already satisfy
    # the old-bank requirement in interpreter order; decline instead of proving
    # whether that FEED will be funded.
    feed_sites = {site for site, row in zip(positions, rows) if row[0] == "FEED"}
    collect_counts: dict[tuple[int, int], int] = {}
    for site, row in zip(positions, rows):
        if row[0] == "COLLECT_FERTILIZER":
            collect_counts[site] = collect_counts.get(site, 0) + 1
    day = step // 24
    changes = []
    for actor, (site, row) in enumerate(zip(positions, rows)):
        if (row != ["COLLECT_FERTILIZER"] or site in feed_sites
                or collect_counts.get(site) != 1):
            continue
        animal = _carebank_animal(tiles[site[1]][site[0]], day)
        if (animal is None or animal["fed"] or not animal["fertilizer_available"]
                or not animal["production_due"] or animal["pending"] <= 0
                or animal["realizable_bonus"] <= 0 or wheat[actor] < 1):
            continue
        changes.append({
            "actor": actor,
            "site": list(site),
            "species": animal["species"],
            "pending_care_bonus": animal["pending"],
            "realizable_bonus": animal["realizable_bonus"],
            "yield_units": animal["yield_units"],
            "max_held": animal["max_held"],
            "consecutive_unfed": animal["unfed"],
            "cared_today": animal["cared"],
            "wheat_before": wheat[actor],
            "forgone_fertilizer": 1,
            "route_certificate": route_cert,
            "reason": "production_care_bank_at_risk",
        })
        # One rewrite is enough to feed this animal for the entire day. Later
        # same-site COLLECT rows remain untouched.
        feed_sites.add(site)
    return changes


def apply_carebank_feed_swap(action: Any, observation: Any, configuration: Any,
                             route: Any, *, enabled=False):
    """Apply only certified CARE-bank salvage; disabled/no-match preserves identity."""
    if enabled is not True:
        return action
    changes = plan_carebank_feed_swap(action, observation, configuration, route)
    if not changes:
        return action
    result = deepcopy(action)
    for change in changes:
        actor = change["actor"]
        if actor == 0:
            result["farmer"] = ["FEED"]
        else:
            result["hands"][actor - 1] = ["FEED"]
    for change in changes:
        telemetry["carebank_feed_swaps"] += 1
        telemetry["carebank_" + change["species"]] += 1
        telemetry["carebank_bonus_units_admitted"] += change["realizable_bonus"]
    return result
