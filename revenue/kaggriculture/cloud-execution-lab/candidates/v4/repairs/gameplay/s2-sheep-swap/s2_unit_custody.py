# SPDX-License-Identifier: Apache-2.0
"""Native observable-unit primitives for the parked S2 candidate.

This text is appended by build_s2_lifecycle.py, not a second controller.  Only
own-farm/private observations are copied.  No market forecast or RNG is run.
"""
from mechanics import _apply_unit_action as _s2_engine_unit


def _s2_world(observation, action):
    own = observation["farms"][observation["player"]]
    farm, private = copy.deepcopy((own, observation["private"]))
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        hands = []
    workers = [action.get("farmer", ["PASS"]), *hands]
    demand = {}
    # The official interpreter counts even surplus raw PLANT commands before
    # applying actions to actual actors. Do not truncate before this census.
    for work in workers:
        if isinstance(work, list) and len(work) >= 2 and work[0] == "PLANT":
            demand[work[1]] = demand.get(work[1], 0) + 1
    blocked = {crop for crop, n in demand.items()
               if n > private.get("seeds", {}).get(crop, 0)}
    return farm, private, workers, blocked


def _s2_advance(farm, private, actor, work, blocked, step):
    if (isinstance(work, list) and len(work) >= 2
            and work[0] == "PLANT" and work[1] in blocked):
        work = ["PASS"]
    _s2_engine_unit(farm, private, actor, work, 10, step // 24, 24, 100)


def _s2_projected_shed(action, observation):
    farm, private, workers, blocked = _s2_world(observation, action)
    for actor, work in enumerate(workers[:1 + len(farm.get("hands", []))]):
        _s2_advance(farm, private, actor, work, blocked, observation["step"])
    return private["shed"]


def _s2_eod_return(private, carrying, market):
    """Lower bound on owned sheep retained at EOD, never an arrival forecast.

    Ignore capacity released by market sales. Reserve space for every possible
    BUY_PRODUCT/BUY_ANIMAL unit in the executable prefix, even an unaffordable
    one. Real post-market capacity is consequently no smaller. Inventory and
    item iteration order is the engine's order; all vanished hands are retired.
    Sheep tokens are fungible: retained/picked/placed units consume owned tokens
    first, consistently. New S2 purchases still require next-observation proof.
    """
    possible_deposits = 0
    for order in market[:MAX_ORDERS]:
        if (isinstance(order, list) and len(order) >= 3
                and order[0] in ("BUY_PRODUCT", "BUY_ANIMAL")):
            try:
                possible_deposits += max(0, int(order[2]))
            except (TypeError, ValueError, OverflowError):
                # Unknown deposit quantity cannot establish free storage.
                possible_deposits += 100
    room = max(0, 100 - sum(private["shed"].values()) - possible_deposits)
    returned = 0
    for actor, inventory in enumerate(private["inventories"]):
        for item, quantity in inventory.items():
            take = min(max(0, quantity), room)
            if item == "SHEEP":
                returned += min(carrying.get(actor, 0), take)
            room -= take
    return returned


def _s2_unit_stage(observation, parent_action, state):
    result = copy.deepcopy(parent_action)
    if (not state["reserved"] and not any(state["carrying"].values())
            and not state["sites"]):
        state["carrying"] = {}
        return result
    farm, private, workers, blocked = _s2_world(observation, result)
    step = observation["step"]
    reserved = min(max(0, state["reserved"]), private["shed"].get("SHEEP", 0))
    carrying = {
        actor: min(max(0, state["carrying"].get(actor, 0)), inv.get("SHEEP", 0))
        for actor, inv in enumerate(private["inventories"])
    }
    for actor, work in enumerate(workers[:1 + len(farm.get("hands", []))]):
        if not isinstance(work, list) or not work:
            continue
        inventory = private["inventories"][actor]
        position = farm["farmer"] if actor == 0 else farm["hands"][actor - 1]
        x, y = position
        tile = farm["tiles"][y][x]
        site = (x, y)
        if len(work) >= 2 and work[:2] == ["PICKUP", "COW"]:
            quantity = max(0, int(work[2]) if len(work) >= 3 else 1)
            if (quantity and reserved >= quantity
                    and private["shed"].get("SHEEP", 0) >= quantity
                    and _beside_shed(position)
                    and not any(inventory.get(animal, 0) for animal in ANIMALS)):
                work[1] = "SHEEP"
        if (len(work) >= 2 and work[:2] == ["PLACE", "COW"]
                and carrying.get(actor, 0) > 0 and inventory.get("SHEEP", 0) > 0
                and isinstance(tile, dict) and tile.get("kind") == "PASTURE"
                and "animal" not in tile):
            work[1] = "SHEEP"
        owned_harvest = (
            work[0] == "HARVEST" and site in state["sites"]
            and isinstance(tile, dict) and tile.get("animal") == "SHEEP"
            and tile.get("placed_day") == state["sites"][site]
        )
        before_sheep = inventory.get("SHEEP", 0)
        before_wool = inventory.get("WOOL", 0)
        before_shed = private["shed"].get("SHEEP", 0)
        owned = carrying.get(actor, 0)
        was_empty_pasture = (isinstance(tile, dict)
                             and tile.get("kind") == "PASTURE"
                             and "animal" not in tile)
        _s2_advance(farm, private, actor, work, blocked, step)
        after_sheep = inventory.get("SHEEP", 0)
        if len(work) >= 2 and work[:2] == ["PICKUP", "SHEEP"]:
            transferred = min(reserved, max(0, after_sheep - before_sheep))
            reserved -= transferred
            carrying[actor] = owned + transferred
            state["picked"] += transferred
        else:
            removed = max(0, before_sheep - after_sheep)
            owned_removed = min(owned, removed)
            deposited = max(0, private["shed"].get("SHEEP", 0) - before_shed)
            reserved += min(owned_removed, deposited)
            carrying[actor] = owned - owned_removed
            if (owned_removed and was_empty_pasture and len(work) >= 2
                    and work[:2] == ["PLACE", "SHEEP"]
                    and farm["tiles"][y][x].get("animal") == "SHEEP"):
                state["pending_places"].append({"actor": actor, "site": site,
                                                "day": step // 24})
        reserved = min(reserved, private["shed"].get("SHEEP", 0))
        if owned_harvest:
            units = max(0, inventory.get("WOOL", 0) - before_wool)
            state["wool_credit"] += units
            state["extra_wool_harvested"] += units
    result["farmer"], result["hands"] = workers[0], workers[1:]
    if (step + 1) % 24 == 0:
        reserved += _s2_eod_return(private, carrying, result["market"])
        carrying = {}
    state["reserved"], state["carrying"] = reserved, carrying
    return result


def _s2_same(left, right):
    """Type-sensitive equality for the candidate's plain action/state values."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (left.keys() == right.keys()
                and all(_s2_same(value, right[key]) for key, value in left.items()))
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(_s2_same(a, b) for a, b in zip(left, right))
    return left == right


class S2Proposal:
    """One-shot state receipt for a final-return owner, not a runtime controller.

    Build on a state copy, then commit only the action actually returned. Rejects
    mutation, state drift and replay. A rejected receipt never changes live S2
    state. The original apply_s2_swap API remains usable only as the last stage.
    """
    def __init__(self, before, after, action):
        self._before = copy.deepcopy(before)
        self._after = copy.deepcopy(after)
        self._action = copy.deepcopy(action)
        self._used = False

    @property
    def action(self):
        return copy.deepcopy(self._action)

    def commit(self, state, returned_action):
        if self._used:
            return False
        self._used = True
        if not _s2_same(state, self._before) or not _s2_same(returned_action, self._action):
            return False
        state.clear()
        state.update(copy.deepcopy(self._after))
        return True


def propose_s2_swap(observation, parent_action, state, *, enabled,
                    configuration, native_tape):
    tentative = copy.deepcopy(state)
    candidate = apply_s2_swap(observation, parent_action, tentative, enabled=enabled,
                              configuration=configuration, native_tape=native_tape)
    return S2Proposal(state, tentative, candidate)
