# SPDX-License-Identifier: Apache-2.0
"""Conservative uncared end-of-day FEED suppression for the TITAN V4 animal-service lane.

The source-bound mechanism permits one unfed EOD, but activation is stricter:
``apply_guarded_uncared_eod_feed_skip`` additionally requires a no-displacement
EOD stock certificate and an authored next-day route that carries the saved
WHEAT from the reset shed state to an effective FEED before the second EOD.

Candidate-only transform. Default-off at every integration seam.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

ANIMALS = {
    "GOOSE": ("COOP", 4, 1, 4),
    "COW": ("PASTURE", 8, 2, 6),
    "SHEEP": ("PASTURE", 6, 3, 6),
}
MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "WEST": (-1, 0), "EAST": (1, 0)}
telemetry: Counter = Counter()
last_guard_report: dict[str, Any] = {}


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
    placed = tile.get("placed_day")
    units = tile.get("yield_units")
    pending = tile.get("pending_care_bonus")
    unfed = tile.get("consecutive_unfed")
    if (tile.get("kind") != kind
            or type(placed) is not int or not 0 <= placed <= day
            or type(units) is not int or not 0 <= units <= maximum
            or type(pending) is not int or pending < 0
            or type(unfed) is not int or unfed not in (0, 1)
            or any(type(tile.get(k)) is not bool
                   for k in ("fed_today", "cared_today", "fertilizer_available"))):
        return None
    next_day = day + 1
    age = next_day - placed - first
    production_due = age >= 0 and age % interval == 0
    return {
        "species": species,
        "fed": tile["fed_today"],
        "cared": tile["cared_today"],
        "unfed": unfed,
        "pending": pending,
        "production_due": production_due,
        "yield_units": units,
        "max_held": maximum,
    }


def _validated_surface(action: Any, observation: Any, configuration: Any):
    for key, expected in (("boardSize", 10), ("turnsPerDay", 24), ("episodeSteps", 720)):
        value = _cfg(configuration, key)
        if type(value) is not int or value != expected:
            return None
    if not isinstance(action, dict) or not isinstance(observation, dict):
        return None
    step, player = observation.get("step"), observation.get("player")
    farms, private = observation.get("farms"), observation.get("private")
    if (type(step) is not int or not 0 <= step <= 718 or step % 24 != 23
            or type(player) is not int or player not in (0, 1)
            or not isinstance(farms, list) or len(farms) != 2
            or not isinstance(private, dict)):
        return None
    farm = farms[player]
    if not isinstance(farm, dict):
        return None
    hands, tiles = farm.get("hands"), farm.get("tiles")
    hand_rows, farmer_row, market = action.get("hands"), action.get("farmer"), action.get("market")
    if (not isinstance(hands, list) or not isinstance(hand_rows, list)
            or len(hand_rows) != len(hands) or not isinstance(market, list)
            or not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)):
        return None
    positions = [_position(p) for p in [farm.get("farmer"), *hands]]
    rows = [farmer_row, *hand_rows]
    if any(p is None for p in positions):
        return None
    if any(not isinstance(row, list) or not row or type(row[0]) is not str for row in rows):
        return None
    inventories = private.get("inventories")
    if (not isinstance(inventories, list) or len(inventories) != len(positions)
            or any(not isinstance(inv, dict) for inv in inventories)
            or len({id(inv) for inv in inventories}) != len(inventories)
            or any(inv is private.get("shed") or inv is private.get("seeds") for inv in inventories)):
        return None
    wheat = []
    for inv in inventories:
        amount = inv.get("WHEAT", 0)
        if type(amount) is not int or amount < 0:
            return None
        if any(type(n) is not int or n < 0 for n in inv.values()):
            return None
        wheat.append(amount)
    shed = private.get("shed")
    if not isinstance(shed, dict) or any(type(n) is not int or n < 0 for n in shed.values()):
        return None
    tile_ids = [id(tile) for row in tiles for tile in row if isinstance(tile, dict)]
    if len(tile_ids) != len(set(tile_ids)):
        return None
    return step, farm, private, tiles, positions, rows, wheat, market


def plan_uncared_eod_feed_skip(action: Any, observation: Any, configuration: Any) -> list[dict]:
    """Mechanism-level FEED->PASS candidates, without future-route activation claims."""
    surface = _validated_surface(action, observation, configuration)
    if surface is None:
        return []
    step, farm, private, tiles, positions, rows, wheat, market = surface
    feed_actors: dict[tuple[int, int], list[int]] = {}
    care_sites: set[tuple[int, int]] = set()
    for actor, (site, row) in enumerate(zip(positions, rows)):
        if row == ["FEED"]:
            feed_actors.setdefault(site, []).append(actor)
        elif row[0] == "CARE":
            care_sites.add(site)
    day = step // 24
    changes = []
    for site, actors in feed_actors.items():
        if len(actors) != 1 or site in care_sites:
            continue
        animal = _animal(tiles[site[1]][site[0]], day)
        if animal is None or animal["fed"] or animal["cared"] or animal["unfed"] != 0:
            continue
        if animal["production_due"] and animal["pending"] > 0:
            continue
        actor = actors[0]
        if actor >= len(wheat) or wheat[actor] < 1:
            continue
        changes.append({
            "actor": actor,
            "site": list(site),
            "species": animal["species"],
            "production_due": animal["production_due"],
            "pending_care_bonus": animal["pending"],
            "yield_units": animal["yield_units"],
            "max_held": animal["max_held"],
            "guaranteed_wheat_saved": 1,
            "reason": "one_unfed_eod_is_nonterminal",
        })
    return changes


def _farmer_action(row: Any) -> list | None:
    if not isinstance(row, dict):
        return None
    action = row.get("farmer", ["PASS"])
    if not isinstance(action, list) or not action or type(action[0]) is not str:
        return None
    return action


def _route_feed_certificate(route: Any, step: int, site: tuple[int, int]) -> dict | None:
    """Trace the one saved WHEAT through the authored next-day main-farmer tape.

    EOD resets the farmer to the NW shed-access tile, deposits all inventories to
    the shed, removes hands, and empties inventories. We therefore rely on only
    one lower-bound unit of WHEAT in the shed and require the main farmer to
    PICKUP that unit, retain it through its authored actions, and FEED this same
    animal no later than the next EOD callback.
    """
    deadline = step + 24
    if not isinstance(route, list) or deadline >= len(route):
        return None
    pos = (4, 4)  # exact default spawn for boardSize=10
    shed_saved = 1
    carried_saved = 0
    pickup_step = None
    for t in range(step + 1, deadline + 1):
        row = route[t]
        action = _farmer_action(row)
        if action is None:
            return None
        # Until the saved unit is in the main farmer bag, no authored hand or
        # market action may have a path that removes WHEAT from the shed.
        if shed_saved:
            hands = row.get("hands", []) if isinstance(row, dict) else None
            market = row.get("market", []) if isinstance(row, dict) else None
            if not isinstance(hands, list) or not isinstance(market, list):
                return None
            for hand in hands:
                if (not isinstance(hand, list) or not hand or type(hand[0]) is not str):
                    return None
                if hand[0] == "PICKUP" and len(hand) >= 2 and hand[1] == "WHEAT":
                    return None
            for order in market:
                if not isinstance(order, list) or not order or type(order[0]) is not str:
                    return None
                if order[0] == "SELL" and len(order) >= 2 and order[1] == "WHEAT":
                    return None
        op = action[0]
        if op in MOVES:
            dx, dy = MOVES[op]
            q = (pos[0] + dx, pos[1] + dy)
            if 0 <= q[0] < 10 and 0 <= q[1] < 10:
                pos = q
            continue
        if op == "PICKUP" and len(action) >= 2 and action[1] == "WHEAT":
            if pos in ((4, 4), (5, 4), (4, 5), (5, 5)) and shed_saved:
                requested = 1
                if len(action) >= 3:
                    if type(action[2]) is not int or action[2] <= 0:
                        return None
                    requested = action[2]
                taken = min(shed_saved, requested)
                shed_saved -= taken
                carried_saved += taken
                if taken and pickup_step is None:
                    pickup_step = t
            continue
        if op == "DROP":
            # Once the certified unit is in the main farmer bag, re-DROP would
            # re-expose it to same-callback hands/market and later shed-capacity
            # competition. Decline instead of inventing a second custody model.
            if carried_saved > 0:
                return None
            continue
        if op == "FEED":
            if carried_saved > 0:
                carried_saved -= 1
                if pos == site:
                    return {
                        "pickup_step": pickup_step,
                        "feed_step": t,
                        "feed_site": list(site),
                        "steps_before_escape": deadline - t,
                    }
            continue
        # The candidate saved unit is fungible. These operations cannot consume
        # WHEAT from farmer inventory. FERTILIZE consumes fertilizer; PLANT seeds.
        if op in ("PASS", "CARE", "WATER", "HARVEST", "COLLECT_FERTILIZER",
                  "FERTILIZE", "PLANT", "DIG", "BUILD_COOP", "BUILD_PASTURE"):
            continue
        # PLACE can consume carried WHEAT via shed-drop syntax, and unknown ops
        # have no source-bound custody proof here.
        return None
    return None


def _stock_certificate(surface, action: dict, configuration: Any) -> dict | None:
    step, farm, private, tiles, positions, rows, wheat, market = surface
    cap = _cfg(configuration, "shedCapacity")
    if type(cap) is not int or cap <= 0:
        return None
    # Current unit actions that can create new carried goods make the EOD bound
    # state-dependent; decline rather than invent future capacity.
    if any(row[0] in ("HARVEST", "COLLECT_FERTILIZER") for row in rows):
        return None
    # Market executes before EOD. Product/animal purchases add physical stock;
    # decline. Seed/land/hire do not add shed/inventory goods; SELL only removes.
    for order in market:
        if not isinstance(order, list) or not order or type(order[0]) is not str:
            return None
        if order[0] in ("BUY_PRODUCT", "BUY_ANIMAL"):
            return None
        if order[0] not in ("SELL", "BUY_SEED", "BUY_LAND", "HIRE"):
            return None
    total = sum(private["shed"].values()) + sum(sum(inv.values()) for inv in private["inventories"])
    if total > cap:
        return None
    return {"pre_action_physical_stock": total, "shed_capacity": cap,
            "guaranteed_eod_room": cap - total}


def plan_guarded_starvation_skip(action: Any, observation: Any, configuration: Any,
                                 route: Any) -> tuple[list[dict], dict]:
    """Activation-grade subset of mechanism candidates; at most one site/EOD."""
    report = {"eligible": 0, "admitted": 0, "blocked": Counter(), "step": None}
    surface = _validated_surface(action, observation, configuration)
    if surface is None:
        report["blocked"]["invalid_surface"] += 1
        return [], _plain_report(report)
    report["step"] = surface[0]
    candidates = plan_uncared_eod_feed_skip(action, observation, configuration)
    report["eligible"] = len(candidates)
    if not candidates:
        report["blocked"]["no_mechanism_candidate"] += 1
        return [], _plain_report(report)
    stock = _stock_certificate(surface, action, configuration)
    if stock is None:
        report["blocked"]["eod_stock_not_certified"] += len(candidates)
        return [], _plain_report(report)
    # If current observed stock exactly fills the shed, a skipped FEED still
    # frees one unit relative to observed stock only if it executes. We require
    # the candidate to preserve a unit already counted in `total`, so total<=cap
    # is sufficient and no other carried good can be displaced.
    for candidate in candidates:
        cert = _route_feed_certificate(route, surface[0], tuple(candidate["site"]))
        if cert is None:
            report["blocked"]["next_feed_route_not_certified"] += 1
            continue
        accepted = dict(candidate)
        accepted["stock_certificate"] = stock
        accepted["next_feed_certificate"] = cert
        accepted["activation_reason"] = "eod_saved_wheat_reused_before_escape"
        report["admitted"] = 1
        report["selected_site"] = accepted["site"]
        report["next_feed_step"] = cert["feed_step"]
        return [accepted], _plain_report(report)
    return [], _plain_report(report)


def _plain_report(report: dict) -> dict:
    out = dict(report)
    if isinstance(out.get("blocked"), Counter):
        out["blocked"] = dict(out["blocked"])
    return out


def apply_uncared_eod_feed_skip(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Mechanism transform retained for source tests; not activation-grade."""
    if not enabled:
        return action
    changes = plan_uncared_eod_feed_skip(action, observation, configuration)
    if not changes:
        return action
    result = deepcopy(action)
    for change in changes:
        actor = change["actor"]
        if actor == 0:
            result["farmer"] = ["PASS"]
        else:
            result["hands"][actor - 1] = ["PASS"]
    for change in changes:
        telemetry["rewrites"] += 1
        telemetry["guaranteed_wheat_saved"] += 1
        telemetry[change["species"]] += 1
    return result


def apply_guarded_uncared_eod_feed_skip(action: Any, observation: Any, configuration: Any,
                                         route: Any, *, enabled=False):
    """Default identity; guarded mode applies at most one route-backed skip."""
    global last_guard_report
    if not enabled:
        last_guard_report = {"eligible": 0, "admitted": 0, "blocked": {"disabled": 1}}
        return action
    changes, report = plan_guarded_starvation_skip(action, observation, configuration, route)
    last_guard_report = report
    for reason, count in report.get("blocked", {}).items():
        telemetry[f"blocked:{reason}"] += count
    telemetry["guard_calls"] += 1
    telemetry["guard_eligible"] += report.get("eligible", 0)
    if not changes:
        return action
    change = changes[0]
    result = deepcopy(action)
    actor = change["actor"]
    if actor == 0:
        result["farmer"] = ["PASS"]
    else:
        result["hands"][actor - 1] = ["PASS"]
    telemetry["guarded_rewrites"] += 1
    telemetry["guaranteed_wheat_saved"] += 1
    telemetry[f"guarded:{change['species']}"] += 1
    return result
