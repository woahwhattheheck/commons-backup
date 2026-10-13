# SPDX-License-Identifier: Apache-2.0
"""Default-off dependent-animal capital rebind for the canonical V4 early-capital family.

This helper never credits future SELLs or guessed fills.  It handles one narrow,
route-proved failure mode: a full current market queue spends on deferable seed
inventory while a later zero-quantity SHEEP acquisition is followed by authored
PICKUP/PLACE obligations.  The rebind replaces the *current* deferable WHEAT
seed row one-for-one with one SHEEP, trims only the current STRAWBERRY seed
quantity to the maximum affordable quantity from observed cash after preserving
every HIRE, and returns an exact WHEAT backfill obligation.  Backfill is allowed
only on a route-authenticated parent-empty market callback, with observed cash,
before the first authored WHEAT PLANT.

No runtime/default/config/archive/Kaggle activation lives here.  Callers must
authenticate the exact source bindings below and explicitly enable the helper.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math

EXPECTED_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
EXPECTED_PARENT_GIT_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
REVISION = "flockbind-zero-credit-v1"


def git_blob_sha1(data):
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("git blob input must be bytes")
    raw = bytes(data)
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def source_binding_report(engine_bytes, parent_bytes):
    """Authenticate the exact official-engine and current Arlene parent bytes."""
    try:
        engine_blob = git_blob_sha1(engine_bytes)
        parent_blob = git_blob_sha1(parent_bytes)
    except (TypeError, ValueError):
        return {
            "bound": False,
            "engine_git_blob": None,
            "parent_git_blob": None,
            "expected_engine_git_blob": EXPECTED_ENGINE_GIT_BLOB,
            "expected_parent_git_blob": EXPECTED_PARENT_GIT_BLOB,
        }
    return {
        "bound": (
            engine_blob == EXPECTED_ENGINE_GIT_BLOB
            and parent_blob == EXPECTED_PARENT_GIT_BLOB
        ),
        "engine_git_blob": engine_blob,
        "parent_git_blob": parent_blob,
        "expected_engine_git_blob": EXPECTED_ENGINE_GIT_BLOB,
        "expected_parent_git_blob": EXPECTED_PARENT_GIT_BLOB,
    }


def _qty(order):
    if not isinstance(order, list) or len(order) < 3:
        return 0
    try:
        value = int(order[2])
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, value)


def _market_limit(configuration):
    if not isinstance(configuration, dict):
        return None
    value = configuration.get("maxMarketOrdersPerTurn", 10)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(1, value)


def _now(observation, configuration):
    try:
        if observation.get("step") is not None:
            value = observation["step"]
            if isinstance(value, bool):
                return None
            return int(value)
        tpd = configuration.get("turnsPerDay", 24)
        if isinstance(tpd, bool) or not isinstance(tpd, int) or tpd <= 0:
            return None
        return int(observation["day"]) * tpd + int(observation["hour"])
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return None


def _own_farm(observation):
    try:
        player = observation.get("player", 0)
        farms = observation["farms"]
        if isinstance(player, bool) or not isinstance(player, int):
            return None
        if not isinstance(farms, (list, tuple)) or not (0 <= player < len(farms)):
            return None
        farm = farms[player]
        return farm if isinstance(farm, dict) else None
    except (AttributeError, KeyError, TypeError):
        return None


def _unit_actions(row):
    if not isinstance(row, dict):
        return None
    farmer = row.get("farmer", ["PASS"])
    hands = row.get("hands", [])
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if not all(isinstance(action, list) for action in hands):
        return None
    return [farmer, *hands]


def _nonmarket_signature(row):
    if not isinstance(row, dict):
        return None
    farmer = row.get("farmer", ["PASS"])
    hands = row.get("hands", [])
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if not all(isinstance(action, list) for action in hands):
        return None
    return {"farmer": deepcopy(farmer), "hands": deepcopy(hands)}


def _market(row):
    if not isinstance(row, dict):
        return None
    value = row.get("market", [])
    return value if isinstance(value, list) else None


def _action_matches_parent(selected, parent_row):
    if not isinstance(selected, dict) or not isinstance(parent_row, dict):
        return False
    return (
        _nonmarket_signature(selected) == _nonmarket_signature(parent_row)
        and _market(selected) == _market(parent_row)
    )


def _route_obligation(route, now):
    """Prove the dependent SHEEP chain and a WHEAT backfill window from parent route."""
    if not isinstance(route, list) or not isinstance(now, int):
        return None
    if now < 0 or now >= len(route):
        return None

    first_wheat_plant = None
    zero_sheep_buy = None
    positive_sheep_buy = None
    pickup = None
    place = None

    for step in range(now + 1, len(route)):
        row = route[step]
        market = _market(row)
        units = _unit_actions(row)
        if market is None or units is None:
            return None

        for order in market:
            if not isinstance(order, list) or not order:
                return None
            if len(order) >= 2 and order[0] == "BUY_ANIMAL" and order[1] == "SHEEP":
                if _qty(order) > 0 and positive_sheep_buy is None:
                    positive_sheep_buy = step
                elif _qty(order) <= 0 and zero_sheep_buy is None:
                    zero_sheep_buy = step

        for action in units:
            if not action:
                continue
            if len(action) >= 2 and action[0] == "PICKUP" and action[1] == "SHEEP":
                if pickup is None:
                    pickup = step
            if len(action) >= 2 and action[0] == "PLACE" and action[1] == "SHEEP":
                if place is None:
                    place = step
            if len(action) >= 2 and action[0] == "PLANT" and action[1] == "WHEAT":
                first_wheat_plant = step
                break
        if first_wheat_plant is not None:
            break

    if None in (zero_sheep_buy, pickup, place, first_wheat_plant):
        return None
    if positive_sheep_buy is not None and positive_sheep_buy < pickup:
        return None
    if not (now < zero_sheep_buy < pickup < place < first_wheat_plant):
        return None

    eligible = {}
    for step in range(place + 1, first_wheat_plant):
        row = route[step]
        market = _market(row)
        signature = _nonmarket_signature(row)
        if market is None or signature is None:
            return None
        if market == []:
            eligible[str(step)] = signature
    if not eligible:
        return None

    return {
        "zero_sheep_buy_step": zero_sheep_buy,
        "pickup_step": pickup,
        "place_step": place,
        "deadline_step": first_wheat_plant,
        "eligible_empty_callbacks": eligible,
    }


def _project_post_unit_private(mechanics, observation, configuration, selected, now):
    """Project the exact pinned deterministic unit phase on private copies."""
    apply_unit = getattr(mechanics, "_apply_unit_action", None)
    if not callable(apply_unit):
        return None
    try:
        player = observation.get("player", 0)
        farms = observation.get("farms")
        if isinstance(player, bool) or not isinstance(player, int):
            return None
        if not isinstance(farms, (list, tuple)) or not (0 <= player < len(farms)):
            return None
        farm = deepcopy(farms[player])
        private = deepcopy(observation.get("private"))
        if not isinstance(farm, dict) or not isinstance(private, dict):
            return None
        if not isinstance(farm.get("tiles"), list):
            return None
        shed = private.get("shed")
        seeds = private.get("seeds")
        inventories = private.get("inventories")
        if not isinstance(shed, dict) or not isinstance(seeds, dict) or not isinstance(inventories, list):
            return None

        actions = _unit_actions(selected)
        if actions is None:
            return None

        plant_demand = {}
        for action in actions:
            if len(action) >= 2 and action[0] == "PLANT":
                plant_demand[action[1]] = plant_demand.get(action[1], 0) + 1
        blocked = {
            crop for crop, count in plant_demand.items()
            if count > seeds.get(crop, 0)
        }

        tpd = configuration.get("turnsPerDay", 24)
        board = configuration.get("boardSize", 10)
        capacity = configuration.get("shedCapacity", 100)
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (tpd, board, capacity)):
            return None
        if tpd <= 0 or board <= 0 or capacity < 0:
            return None
        day = now // tpd

        for index, action in enumerate(actions):
            allowed = (
                ["PASS"]
                if len(action) >= 2 and action[0] == "PLANT" and action[1] in blocked
                else action
            )
            apply_unit(farm, private, index, allowed, board, day, tpd, capacity)

        post_shed = private.get("shed")
        if not isinstance(post_shed, dict):
            return None
        return private
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError):
        return None


def _costs(mechanics, observation, configuration, market):
    """Return exact fixed current-turn cost inputs without SELL/future credit."""
    farm = _own_farm(observation)
    if farm is None:
        return None
    try:
        money = farm.get("money")
        if isinstance(money, bool) or not isinstance(money, (int, float)):
            return None
        if not math.isfinite(float(money)) or money < 0:
            return None

        animal = mechanics.ANIMALS["SHEEP"]
        sheep_cost = animal["cost"]
        strawberry_cost = mechanics.CROPS["STRAWBERRY"]["seed"]
        wheat_cost = mechanics.CROPS["WHEAT"]["seed"]
        for value in (sheep_cost, strawberry_cost, wheat_cost):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            if not math.isfinite(float(value)) or value <= 0:
                return None

        hire_fn = getattr(mechanics, "_hire_cost", None)
        if not callable(hire_fn):
            return None
        hires_today = farm.get("hires_today", 0)
        if isinstance(hires_today, bool) or not isinstance(hires_today, int) or hires_today < 0:
            return None
        multiplier = configuration.get(
            "farmHandCostMult",
            getattr(mechanics, "FARM_HAND_COST_MULT", 1),
        )
        if isinstance(multiplier, bool) or not isinstance(multiplier, int) or multiplier < 0:
            return None

        hire_total = 0.0
        hire_rows = 0
        for order in market:
            if isinstance(order, list) and order and order[0] == "HIRE":
                cost = hire_fn(hires_today, multiplier)
                if isinstance(cost, bool) or not isinstance(cost, (int, float)):
                    return None
                if not math.isfinite(float(cost)) or cost < 0:
                    return None
                hire_total += float(cost)
                hires_today += 1
                hire_rows += 1
        return {
            "cash": float(money),
            "sheep_cost": float(sheep_cost),
            "strawberry_seed_cost": float(strawberry_cost),
            "wheat_seed_cost": float(wheat_cost),
            "hire_cost": hire_total,
            "hire_rows": hire_rows,
        }
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        return None


def propose_dependent_sheep_rebind(
    mechanics,
    observation,
    configuration,
    selected,
    route,
    *,
    enabled=False,
    source_bound=False,
    minimum_strawberry=1,
):
    """Return ``(action, obligation, report)``; fail closed to the parent action."""
    report = {"changed": False, "reason": "init", "revision": REVISION}
    if not enabled:
        report["reason"] = "disabled"
        return selected, None, report
    if not source_bound:
        report["reason"] = "source_unbound"
        return selected, None, report
    if not isinstance(selected, dict) or not isinstance(route, list):
        report["reason"] = "unsupported_action"
        return selected, None, report
    now = _now(observation, configuration)
    if now is None or now < 0 or now >= len(route):
        report["reason"] = "unsupported_time"
        return selected, None, report
    if not _action_matches_parent(selected, route[now]):
        report["reason"] = "parent_action_drift"
        return selected, None, report

    market = _market(selected)
    limit = _market_limit(configuration)
    if market is None or limit is None or len(market) != limit:
        report["reason"] = "requires_full_executable_market"
        return selected, None, report

    wheat_rows = []
    strawberry_rows = []
    hire_rows = []
    for index, order in enumerate(market):
        if not isinstance(order, list) or not order:
            report["reason"] = "unsupported_market_row"
            return selected, None, report
        op = order[0]
        if op == "HIRE" and len(order) == 1:
            hire_rows.append(index)
        elif op == "BUY_SEED" and len(order) >= 3 and order[1] == "WHEAT" and _qty(order) > 0:
            wheat_rows.append(index)
        elif op == "BUY_SEED" and len(order) >= 3 and order[1] == "STRAWBERRY" and _qty(order) > 0:
            strawberry_rows.append(index)
        else:
            report["reason"] = "unsupported_market_shape"
            return selected, None, report
    if len(wheat_rows) != 1 or len(strawberry_rows) != 1 or not hire_rows:
        report["reason"] = "unsupported_market_shape"
        return selected, None, report

    proof = _route_obligation(route, now)
    if proof is None:
        report["reason"] = "dependent_route_not_proved"
        return selected, None, report

    post_private = _project_post_unit_private(
        mechanics, observation, configuration, selected, now
    )
    if post_private is None:
        report["reason"] = "post_unit_projection_failed"
        return selected, None, report
    shed = post_private.get("shed")
    capacity = configuration.get("shedCapacity", 100)
    if not isinstance(shed, dict) or isinstance(capacity, bool) or not isinstance(capacity, int):
        report["reason"] = "unsupported_capacity"
        return selected, None, report
    occupancy = 0
    for quantity in shed.values():
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            report["reason"] = "unsupported_capacity"
            return selected, None, report
        occupancy += quantity
    if occupancy >= capacity or int(shed.get("SHEEP", 0)) != 0:
        report["reason"] = "sheep_capacity_or_stock_not_clean"
        return selected, None, report

    costs = _costs(mechanics, observation, configuration, market)
    if costs is None:
        report["reason"] = "cost_projection_failed"
        return selected, None, report

    strawberry_index = strawberry_rows[0]
    wheat_index = wheat_rows[0]
    original_strawberry = _qty(market[strawberry_index])
    wheat_quantity = _qty(market[wheat_index])
    if (
        isinstance(minimum_strawberry, bool)
        or not isinstance(minimum_strawberry, int)
        or minimum_strawberry < 1
        or original_strawberry < minimum_strawberry
    ):
        report["reason"] = "minimum_strawberry_not_preservable"
        return selected, None, report

    fixed = costs["sheep_cost"] + costs["hire_cost"]
    affordable = math.floor((costs["cash"] - fixed) / costs["strawberry_seed_cost"])
    keep_strawberry = min(original_strawberry, int(affordable))
    if keep_strawberry < minimum_strawberry:
        report["reason"] = "observed_cash_insufficient"
        return selected, None, report

    result = deepcopy(selected)
    result["market"][wheat_index] = ["BUY_ANIMAL", "SHEEP", 1]
    result["market"][strawberry_index] = [
        "BUY_SEED", "STRAWBERRY", keep_strawberry
    ]
    if len(result["market"]) != len(market):
        report["reason"] = "cardinality_drift"
        return selected, None, report

    obligation = {
        "schema": "titan-v4-flockbind-wheat-obligation/v1",
        "revision": REVISION,
        "source_step": now,
        "item": "WHEAT",
        "quantity": wheat_quantity,
        "unit_cost": costs["wheat_seed_cost"],
        "deadline_step": proof["deadline_step"],
        "eligible_empty_callbacks": deepcopy(proof["eligible_empty_callbacks"]),
        "status": "pending",
    }
    report.update(
        changed=True,
        reason="rebound",
        source_step=now,
        current_rows=len(market),
        row_limit=limit,
        wheat_row=wheat_index,
        strawberry_row=strawberry_index,
        hire_rows=hire_rows,
        observed_cash=costs["cash"],
        sheep_cost=costs["sheep_cost"],
        hire_cost=costs["hire_cost"],
        strawberry_seed_cost=costs["strawberry_seed_cost"],
        strawberry_original=original_strawberry,
        strawberry_preserved=keep_strawberry,
        strawberry_trimmed=original_strawberry - keep_strawberry,
        wheat_deferred=wheat_quantity,
        zero_sheep_buy_step=proof["zero_sheep_buy_step"],
        pickup_step=proof["pickup_step"],
        place_step=proof["place_step"],
        wheat_plant_deadline=proof["deadline_step"],
        eligible_empty_steps=[int(step) for step in proof["eligible_empty_callbacks"]],
    )
    return result, obligation, report


def apply_wheat_backfill(
    mechanics,
    observation,
    configuration,
    selected,
    obligation,
    *,
    enabled=False,
    source_bound=False,
):
    """Fill a pending WHEAT obligation only on an authenticated parent-empty callback."""
    report = {"changed": False, "reason": "init", "revision": REVISION}
    if not enabled:
        report["reason"] = "disabled"
        return selected, obligation, report
    if not source_bound:
        report["reason"] = "source_unbound"
        return selected, obligation, report
    if not isinstance(selected, dict) or not isinstance(obligation, dict):
        report["reason"] = "unsupported_input"
        return selected, obligation, report
    if obligation.get("schema") != "titan-v4-flockbind-wheat-obligation/v1":
        report["reason"] = "unsupported_obligation"
        return selected, obligation, report
    if obligation.get("revision") != REVISION or obligation.get("status") != "pending":
        report["reason"] = "inactive_obligation"
        return selected, obligation, report

    now = _now(observation, configuration)
    if now is None:
        report["reason"] = "unsupported_time"
        return selected, obligation, report
    try:
        source_step = int(obligation["source_step"])
        deadline = int(obligation["deadline_step"])
        quantity = int(obligation["quantity"])
        unit_cost = float(obligation["unit_cost"])
    except (KeyError, TypeError, ValueError, OverflowError):
        report["reason"] = "malformed_obligation"
        return selected, obligation, report
    if quantity <= 0 or unit_cost <= 0 or not math.isfinite(unit_cost):
        report["reason"] = "malformed_obligation"
        return selected, obligation, report
    if not (source_step < now < deadline):
        report["reason"] = "outside_backfill_window"
        return selected, obligation, report

    eligible = obligation.get("eligible_empty_callbacks")
    expected = eligible.get(str(now)) if isinstance(eligible, dict) else None
    if expected is None or expected != _nonmarket_signature(selected):
        report["reason"] = "parent_callback_drift"
        return selected, obligation, report
    market = _market(selected)
    if market != []:
        report["reason"] = "parent_market_not_empty"
        return selected, obligation, report
    limit = _market_limit(configuration)
    if limit is None or limit < 1:
        report["reason"] = "unsupported_market_limit"
        return selected, obligation, report

    farm = _own_farm(observation)
    if farm is None:
        report["reason"] = "unsupported_farm"
        return selected, obligation, report
    cash = farm.get("money")
    if isinstance(cash, bool) or not isinstance(cash, (int, float)):
        report["reason"] = "unsupported_cash"
        return selected, obligation, report
    if not math.isfinite(float(cash)) or cash < quantity * unit_cost:
        report["reason"] = "observed_cash_insufficient"
        return selected, obligation, report

    result = deepcopy(selected)
    result["market"] = [["BUY_SEED", "WHEAT", quantity]]
    updated = deepcopy(obligation)
    updated["status"] = "fulfilled"
    updated["fulfilled_step"] = now
    report.update(
        changed=True,
        reason="backfilled",
        step=now,
        observed_cash=float(cash),
        quantity=quantity,
        exact_cost=quantity * unit_cost,
    )
    return result, updated, report
