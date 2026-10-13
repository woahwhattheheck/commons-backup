# SPDX-License-Identifier: Apache-2.0
"""Parked TITAN V4 S2 candidate: bounded COW -> SHEEP substitution in wool towns.

This module is intentionally standalone and has no GitHub/ref plumbing.  It mirrors the
published V231 transaction discipline: confirm the animal purchase from the next observed
shed delta before rewriting linked PICKUP/PLACE commands, and only top up an already-existing
SELL row with production physically attributable to confirmed swapped animals.

Integration contract: call this *after* the existing V231/V233 parent action and pass the
selected native tape for same-day future-purchase conflict checks.  Ship behind an OFF key.
"""
from __future__ import annotations

import copy
from typing import Any

MILK_SHOPS = {"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"}
ANIMALS = {"COW", "SHEEP", "GOOSE"}
PURCHASE_OPS = {"HIRE", "BUY_LAND", "BUY_PRODUCT", "BUY_ANIMAL", "BUY_SEED"}
MAX_ORDERS = 10
SHEEP_COST = 500
MAX_GAME_SWAPS = 6
MAX_ORDER_QTY = 2
START_STEP = 72
END_STEP = 360


def new_state() -> dict[str, Any]:
    return {
        "last": -1,
        "confirmed": 0,
        "reserved": 0,
        "pending_buy": None,
        "carrying": {},
        "pending_places": [],
        "sites": {},
        "wool_credit": 0,
        "requested": 0,
        "failed_purchase_units": 0,
        "picked": 0,
        "placed": 0,
        "failed_placements": 0,
        "extra_wool_harvested": 0,
        "extra_wool_sale_requests": 0,
    }


def _exact_standard(configuration: Any) -> bool:
    if configuration is None:
        return False
    expected = {
        "episodeSteps": 720,
        "boardSize": 10,
        "turnsPerDay": 24,
        "shedCapacity": 100,
        "maxMarketOrdersPerTurn": 10,
    }
    for key, value in expected.items():
        try:
            got = configuration[key] if isinstance(configuration, dict) else getattr(configuration, key)
        except (KeyError, AttributeError, TypeError):
            return False
        if type(got) is not int or got != value:
            return False
    return True


def _valid_observation(obs: Any) -> bool:
    try:
        player = obs["player"]
        farms = obs["farms"]
        private = obs["private"]
        farm = farms[player]
        tiles = farm["tiles"]
        inventories = private["inventories"]
    except (KeyError, IndexError, TypeError):
        return False
    if type(player) is not int or player not in (0, 1) or len(farms) < 2:
        return False
    if len(tiles) != 10 or any(not isinstance(row, list) or len(row) != 10 for row in tiles):
        return False
    positions = [farm.get("farmer"), *(farm.get("hands") or [])]
    if len(inventories) != len(positions):
        return False
    for position in positions:
        if not (isinstance(position, (list, tuple)) and len(position) == 2
                and all(type(coord) is int and 0 <= coord < 10 for coord in position)):
            return False
    return True


def _beside_shed(position: Any, board_size: int = 10) -> bool:
    if not (isinstance(position, (list, tuple)) and len(position) == 2):
        return False
    center = board_size // 2
    return position[0] in (center - 1, center) and position[1] in (center - 1, center)


def _future_purchase_conflict(native_tape: Any, step: int) -> bool:
    """Fail closed unless every remaining same-day market row is a well-formed SELL.

    Future prices are not observable now, so reserving exact cash for future BUY/HIRE rows
    would be speculative.  The ownership theorem is deliberately stronger: after an S2
    buy rewrite, the native tape must contain no later same-day cash-spending or unknown
    market operation.  Malformed rows also veto instead of being silently ignored.
    """
    if not isinstance(native_tape, list) or type(step) is not int or not (0 <= step < len(native_tape)):
        return True
    end = min(len(native_tape), ((step // 24) + 1) * 24)
    for future in native_tape[step + 1:end]:
        if not isinstance(future, dict):
            return True
        market = future.get("market", [])
        if market is None:
            market = []
        if not isinstance(market, list):
            return True
        for order in market:
            if order == []:
                continue
            if not (isinstance(order, list) and len(order) >= 3 and type(order[0]) is str):
                return True
            if order[0] != "SELL":
                return True
            if type(order[1]) is not str or type(order[2]) is not int or isinstance(order[2], bool):
                return True
    return False


def _owned_current_cow_buy(market: Any) -> list[Any] | None:
    """Return the sole owned COW buy iff every other current row is a valid SELL/empty row."""
    if not isinstance(market, list):
        return None
    target = None
    for order in market:
        if order == []:
            continue
        if not (isinstance(order, list) and order and type(order[0]) is str):
            return None
        if order[0] == "SELL":
            if (len(order) < 3 or type(order[1]) is not str
                    or type(order[2]) is not int or isinstance(order[2], bool)):
                return None
            continue
        if order[0] == "BUY_ANIMAL" and len(order) >= 3 and order[1] == "COW":
            if target is not None or type(order[2]) is not int or isinstance(order[2], bool):
                return None
            target = order
            continue
        # HIRE, other BUY_*, and unknown/malformed ops all break cash ownership.
        return None
    return target


def _projected_shed(action: dict[str, Any], obs: dict[str, Any]) -> dict[str, int]:
    """Small exact-enough shed projection for existing SELL top-up bounds only."""
    player = obs["player"]
    farm = obs["farms"][player]
    private = obs["private"]
    positions = [farm["farmer"], *(farm.get("hands") or [])]
    inventories = private["inventories"]
    stock = {k: max(0, int(v)) for k, v in (private.get("shed") or {}).items()}
    total = sum(stock.values())
    workers = [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]
    for actor, work in enumerate(workers[:len(positions)]):
        if not _beside_shed(positions[actor]):
            continue
        inv = inventories[actor]
        op = work[0] if isinstance(work, list) and work else "PASS"
        if op == "DROP":
            for item, held in inv.items():
                room = max(0, 100 - total)
                add = min(max(0, int(held)), room)
                if add:
                    stock[item] = stock.get(item, 0) + add
                    total += add
        elif op == "PLACE" and len(work) >= 2 and work[1] not in ANIMALS:
            item = work[1]
            qty = max(0, int(work[2]) if len(work) >= 3 else 1)
            room = max(0, 100 - total)
            add = min(qty, max(0, int(inv.get(item, 0))), room)
            if add:
                stock[item] = stock.get(item, 0) + add
                total += add
        elif op == "PICKUP" and len(work) >= 2:
            item = work[1]
            qty = max(0, int(work[2]) if len(work) >= 3 else 1)
            take = min(stock.get(item, 0), qty)
            stock[item] = stock.get(item, 0) - take
            total -= take
    return stock


def apply_s2_swap(
    observation: dict[str, Any],
    parent_action: dict[str, Any],
    state: dict[str, Any],
    *,
    enabled: bool,
    configuration: Any,
    native_tape: Any,
) -> dict[str, Any]:
    """Apply one S2 callback; return exact parent object whenever the theorem is not proven."""
    if not enabled or not _exact_standard(configuration) or not _valid_observation(observation):
        return parent_action

    step = observation.get("step")
    if type(step) is not int:
        return parent_action
    previous_step = state.get("last", -1)
    if previous_step >= 0 and step != previous_step + 1:
        fresh = new_state()
        state.clear(); state.update(fresh)
    state["last"] = step

    player = observation["player"]
    farm = observation["farms"][player]
    private = observation["private"]
    shed = private["shed"]
    inventories = private["inventories"]
    positions = [farm["farmer"], *(farm.get("hands") or [])]

    # Confirm only this lane's prior SHEEP purchase.  If it did not arrive, nothing later
    # is allowed to hijack the native COW transaction.
    pending = state.get("pending_buy")
    if pending is not None:
        gained = max(0, int(shed.get("SHEEP", 0)) - pending["before"])
        confirmed = min(pending["quantity"], gained)
        state["confirmed"] += confirmed
        state["reserved"] += confirmed
        state["failed_purchase_units"] += pending["quantity"] - confirmed
        state["pending_buy"] = None

    # Confirm prior placements before any new rewrite.
    for pending_place in state.get("pending_places", []):
        x, y = pending_place["site"]
        tile = farm["tiles"][y][x]
        if (isinstance(tile, dict) and tile.get("animal") == "SHEEP"
                and tile.get("placed_day") == pending_place["day"]):
            state["sites"][(x, y)] = pending_place["day"]
            state["placed"] += 1
            actor = pending_place["actor"]
            state["carrying"][actor] = max(0, state["carrying"].get(actor, 0) - 1)
        else:
            state["failed_placements"] += 1
    state["pending_places"] = []

    result = copy.deepcopy(parent_action)
    workers = [result.get("farmer") or ["PASS"], *(result.get("hands") or [])]
    seen_harvest: set[tuple[int, int]] = set()
    sheep_available = int(shed.get("SHEEP", 0))
    occupied: set[tuple[int, int]] = set()

    for actor, work in enumerate(workers[:len(positions)]):
        if not isinstance(work, list):
            continue
        inventory = inventories[actor]
        x, y = positions[actor]
        tile = farm["tiles"][y][x]
        site = (x, y)

        if (work == ["HARVEST"] and site in state["sites"] and site not in seen_harvest
                and isinstance(tile, dict) and tile.get("animal") == "SHEEP"
                and tile.get("placed_day") == state["sites"][site]):
            units = max(0, int(tile.get("yield_units", 0)))
            state["wool_credit"] += units
            state["extra_wool_harvested"] += units
            seen_harvest.add(site)

        # Only a confirmed swapped transaction may redirect the tape's linked COW pickup.
        if len(work) >= 2 and work[:2] == ["PICKUP", "COW"]:
            qty = max(0, int(work[2]) if len(work) > 2 else 1)
            center = len(farm["tiles"]) // 2
            if (qty and state["reserved"] >= qty and sheep_available >= qty
                    and x in (center - 1, center) and y in (center - 1, center)
                    and not any(inventory.get(a, 0) for a in ANIMALS)):
                work[1] = "SHEEP"
                state["reserved"] -= qty
                sheep_available -= qty
                state["carrying"][actor] = state["carrying"].get(actor, 0) + qty
                state["picked"] += qty

        if (len(work) >= 2 and work[:2] == ["PLACE", "COW"]
                and state["carrying"].get(actor, 0) > 0 and inventory.get("SHEEP", 0) > 0
                and isinstance(tile, dict) and tile.get("kind") == "PASTURE"
                and "animal" not in tile and site not in occupied):
            work[1] = "SHEEP"
            state["pending_places"].append({"actor": actor, "site": site, "day": step // 24})

        if (len(work) >= 2 and work[0] == "PLACE" and work[1] in ANIMALS
                and inventory.get(work[1], 0) > 0):
            occupied.add(site)

    result["farmer"], result["hands"] = workers[0], workers[1:]
    market = result.get("market")
    if not isinstance(market, list):
        return parent_action

    # Buy rewrite: narrow wool-town gate, fixed cost ownership, no competing current or
    # same-day future purchases, and no V233 two-YARN overlap after day 12.
    shops = observation["town"]["unlocked_shops"]
    prices = observation["market"]["prices"]
    owned_cow_buy = _owned_current_cow_buy(market)
    cargo = sum(int(inv.get(a, 0)) for inv in inventories for a in ANIMALS)
    stock_animals = sum(int(shed.get(a, 0)) for a in ANIMALS)
    wool_gate = (
        START_STEP <= step <= END_STEP
        and "YARN_STORE" in shops
        and not any(shop in MILK_SHOPS for shop in shops)
        and int(prices.get("WOOL", 0)) >= int(prices.get("MILK", 0))
        and not (step >= 288 and shops.count("YARN_STORE") >= 2)
    )
    if (wool_gate and state["requested"] < MAX_GAME_SWAPS and not state["reserved"]
            and not any(state["carrying"].values()) and not state["pending_places"]
            and not cargo and not stock_animals and owned_cow_buy is not None
            and not _future_purchase_conflict(native_tape, step)):
        order = owned_cow_buy
        qty = order[2]
        remaining = MAX_GAME_SWAPS - state["requested"]
        if (1 <= qty <= MAX_ORDER_QTY and qty <= remaining
                and int(farm.get("money", 0)) >= SHEEP_COST * qty):
            order[1] = "SHEEP"
            state["requested"] += qty
            state["pending_buy"] = {"before": int(shed.get("SHEEP", 0)), "quantity": qty}

    # Only additional physically harvested wool may top up an existing positive SELL WOOL row.
    if state["wool_credit"] > 0:
        stock = _projected_shed(result, observation)
        total_planned = sum(max(0, int(o[2])) for o in market
                            if isinstance(o, list) and len(o) >= 3 and o[:2] == ["SELL", "WOOL"])
        extra = min(state["wool_credit"], max(0, int(stock.get("WOOL", 0)) - total_planned))
        if extra:
            for order in market:
                if (isinstance(order, list) and len(order) >= 3
                        and order[:2] == ["SELL", "WOOL"] and int(order[2]) > 0):
                    order[2] = int(order[2]) + extra
                    state["wool_credit"] -= extra
                    state["extra_wool_sale_requests"] += extra
                    break

    result["market"] = market[:MAX_ORDERS]
    return result
