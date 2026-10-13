# SPDX-License-Identifier: Apache-2.0
"""Source-pinned certificate authority for the default-OFF animal cadence candidate.

This module does not alter production policy. It proves one narrow physical loop:
when an otherwise eligible FEED is skipped on the final step of a day, the saved
carried WHEAT survives the end-of-day deposit and the unchanged live route picks
WHEAT up on the first unit stage of the next day before feeding the same animal
later that day.

The proof deliberately reuses the landed operating-stock feed-window theorem and
binds its result to the exact completed runtime profile and live route tail
consumed by the candidate.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path


SCHEMA = "titan-v5/animal-cadence/next-feed-certificate/v1"
OFFICIAL_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_MECHANICS_GIT_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"
PRODUCER_GIT_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
OPERATING_STOCK_GIT_BLOB = "fbf11b58fc47cc922e72ddb17ae4f7a4e095702c"
CANDIDATE_GIT_BLOB = "e5f545c452e54337e978c3fa553535e967d50569"
SPATIAL_TEMPO_GIT_BLOB = "a2f13cd9871e6da24b2ccf3297c4c96ac324100e"
CROP_RELEASE_GIT_BLOB = "f8b0b2a5c2a5cbcf2f7c5e2eac5527bd4bb83974"
MAIN_GIT_BLOB = "9cf8feaa9a755ffdf85d8878baa07b1fc7940192"
RUNTIME_GIT_BLOB = "922c99a571e4ba49726a753739f95afe86e72290"
CONFIG_GIT_BLOB = "ef0bfb1dfa1ce65103a0b178647fc16bc9c7e791"
FROZEN_SELECTED_GIT_BLOB = "6a95505388ea1b5eba38bd1f927a2a2bf084490c"
EXEC_PACE_RUNTIME_GIT_BLOB = "76cbb062760f58e0c47f3bfd29e3652362180218"
SEED_FUNDING_GIT_BLOB = "2fb66257cd8e4ae5b902ab8c5f21c54a6061f3aa"
SEED_BUDGET_GIT_BLOB = "56e573d764effa3923351131a73d986e18b3eb78"
REDUNDANT_HIRE_GIT_BLOB = "a58ba3403d89f0d9a17e56225f891f1aa81a4c8f"
EARLY_CAPITAL_GIT_BLOB = "dcbae01a3db703d1bb273a6d31d23ec250a9e773"
PRESSURE_PRIORITY_GIT_BLOB = "cde454922e5cf0bb46c9bd68c4fad2e98782c4b5"
SELL_PRIORITY_GIT_BLOB = "2d0f711626a7d88ab4a0f133ef06621c6261c67b"
TOWN_PROCUREMENT_GIT_BLOB = "14b0330dcad81c3656a7f0d75fac573e2513f24e"

_SOURCE_PINS = {
    "reference/engine/kaggriculture.py": OFFICIAL_ENGINE_GIT_BLOB,
    "mechanics.py": ENGINE_MECHANICS_GIT_BLOB,
    "reference/next-panel/vendor/arlene.py": PRODUCER_GIT_BLOB,
    "operating_stock.py": OPERATING_STOCK_GIT_BLOB,
    "candidates/v5/animal-cadence/alternate_feed.py": CANDIDATE_GIT_BLOB,
    "spatial_tempo.py": SPATIAL_TEMPO_GIT_BLOB,
    "crop_release.py": CROP_RELEASE_GIT_BLOB,
    "main.py": MAIN_GIT_BLOB,
    "titan_runtime.py": RUNTIME_GIT_BLOB,
    "TITAN-CONFIG.json": CONFIG_GIT_BLOB,
    "frozen_selected.py": FROZEN_SELECTED_GIT_BLOB,
    "exec_pace_runtime.py": EXEC_PACE_RUNTIME_GIT_BLOB,
    "reference/titan-current/seed_funding.py": SEED_FUNDING_GIT_BLOB,
    "reference/integrated-selected/alder/seed_budget.py": SEED_BUDGET_GIT_BLOB,
    "reference/titan-current/redundant_hire.py": REDUNDANT_HIRE_GIT_BLOB,
    "early_capital.py": EARLY_CAPITAL_GIT_BLOB,
    "../cloud-opponent-league/lark-responsive/pressure_priority.py": PRESSURE_PRIORITY_GIT_BLOB,
    "../cloud-opponent-league/lark-responsive/sell_priority.py": SELL_PRIORITY_GIT_BLOB,
    "town_procurement.py": TOWN_PROCUREMENT_GIT_BLOB,
}

# This is the exact current production composition whose future wrapper behavior
# has been audited. A caller must pass the entrypoint-owned town flag alongside
# TitanAgent.Features; an arbitrary subset is not an authenticated profile.
_REQUIRED_FEATURES = {
    "consumer": "frozen",
    "seed": True,
    "funding": True,
    "redundant_hire": True,
    "terminal_route": False,
    "committed": True,
    "terminal_history": False,
    "spatial_pathing": False,
    "spatial_tempo": False,
    "fourth_quadrant": False,
    "market_pressure": True,
    "committed_seed_retry": False,
    "operating_stock": True,
    "idle_fertilizer": True,
    "crop_release": True,
    "early_capital": True,
    "town_procurement": True,
    "exec_pace": False,
}


def _lab_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "reference" / "next-panel" / "vendor" / "arlene.py").is_file():
            return parent
    raise RuntimeError("cloud-execution-lab root not found")


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _authenticate_sources(root: Path):
    observed = {}
    for relative, expected in _SOURCE_PINS.items():
        path = root / relative
        data = path.read_bytes()
        actual = _git_blob_sha1(data)
        observed[relative] = actual
        if actual != expected:
            raise ValueError(f"source_pin_mismatch:{relative}")
    return observed


def _feature(features, name):
    if isinstance(features, dict):
        return features.get(name)
    return getattr(features, name, None)


def _authenticate_feature_profile(features):
    for name, expected in _REQUIRED_FEATURES.items():
        value = _feature(features, name)
        if value != expected or (type(expected) is bool and type(value) is not bool):
            raise ValueError(f"unsupported_feature_profile:{name}")


def _strict_configuration(configuration):
    if not isinstance(configuration, dict):
        raise ValueError("malformed_configuration")
    expected = {
        "turnsPerDay": 24,
        "episodeSteps": 720,
        "boardSize": 10,
        "shedCapacity": 100,
        "maxMarketOrdersPerTurn": 10,
        "farmHandCostMult": 1,
    }
    resolved = {}
    for key, default in expected.items():
        value = configuration.get(key, default)
        if type(value) is not int or value != default:
            raise ValueError(f"unsupported_configuration:{key}")
        resolved[key] = value
    return resolved


def _public_identity(observation, turns_per_day=None):
    if not isinstance(observation, dict):
        raise ValueError("malformed_observation")
    player = observation.get("player")
    step = observation.get("step")
    if type(player) is not int or player not in (0, 1):
        raise ValueError("malformed_public_identity")
    if type(step) is not int or step < 0:
        raise ValueError("malformed_public_identity")
    if turns_per_day is not None:
        if type(turns_per_day) is not int or turns_per_day <= 0:
            raise ValueError("malformed_public_clock")
        missing = object()
        day = observation.get("day", missing)
        hour = observation.get("hour", missing)
        if (day is missing) != (hour is missing):
            raise ValueError("malformed_public_clock")
        if day is not missing:
            if (type(day) is not int or day < 0
                    or type(hour) is not int or not 0 <= hour < turns_per_day):
                raise ValueError("malformed_public_clock")
            if step != day * turns_per_day + hour:
                raise ValueError("public_clock_mismatch")
    farms = observation.get("farms")
    private = observation.get("private")
    if not isinstance(farms, list) or player >= len(farms) or not isinstance(farms[player], dict):
        raise ValueError("malformed_observation")
    if not isinstance(private, dict):
        raise ValueError("malformed_observation")
    return player, step


def _units(row):
    if not isinstance(row, dict):
        return []
    farmer = row.get("farmer") or ["PASS"]
    hands = row.get("hands") or []
    if not isinstance(hands, list):
        return []
    return [farmer, *hands]


def _position(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or type(value[0]) is not int or type(value[1]) is not int):
        return None
    return (value[0], value[1])


def _current_feed_positions(observation, selected):
    player, _ = _public_identity(observation)
    farm = observation["farms"][player]
    positions = [farm.get("farmer"), *(farm.get("hands") or [])]
    actions = _units(selected)
    if len(actions) != len(positions):
        raise ValueError("selected_unit_topology_mismatch")
    found = set()
    for position, action in zip(positions, actions):
        p = _position(position)
        if p is None:
            raise ValueError("malformed_unit_position")
        if isinstance(action, list) and action and action[0] == "FEED":
            found.add(p)
    return sorted(found)


def _canonical_tail_sha256(route, step):
    try:
        encoded = json.dumps(
            route[step:], sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("noncanonical_live_route") from error
    return hashlib.sha256(encoded).hexdigest()


def _route_context(controller, producer, step):
    routes = getattr(controller, "R", None)
    current = getattr(controller, "cur", None)
    if not isinstance(routes, dict) or not isinstance(current, str) or current not in routes:
        raise ValueError("malformed_live_controller")
    route = routes[current]
    if not isinstance(route, list) or step >= len(route):
        raise ValueError("malformed_live_route")
    source_routes = producer.routes()
    if current not in source_routes or not isinstance(source_routes[current], list):
        raise ValueError("unattributed_live_route")
    source = source_routes[current]
    if len(route) != len(source) or route[:step] != source[:step]:
        raise ValueError("live_route_lineage_mismatch")
    checkpoints = tuple(sorted(
        int(row[0]) for row in producer.DECISIONS
        if isinstance(row, (list, tuple)) and row and type(row[0]) is int
    ))
    identity = {
        "route_id": current,
        "route_source_git_blob": PRODUCER_GIT_BLOB,
        "tail_sha256": _canonical_tail_sha256(route, step),
    }
    return route, checkpoints, identity


def _post_units(mechanics, observation, selected, configuration):
    player, step = _public_identity(observation)
    farm = deepcopy(observation["farms"][player])
    private = deepcopy(observation["private"])
    positions = [farm.get("farmer"), *(farm.get("hands") or [])]
    actions = _units(selected)
    inventories = private.get("inventories")
    if len(actions) != len(positions) or not isinstance(inventories, list) or len(inventories) != len(positions):
        raise ValueError("selected_unit_topology_mismatch")
    if any(not isinstance(inv, dict) for inv in inventories):
        raise ValueError("malformed_inventories")
    demand = {}
    for action in actions:
        if isinstance(action, list) and len(action) >= 2 and action[0] == "PLANT":
            demand[action[1]] = demand.get(action[1], 0) + 1
    seeds = private.get("seeds")
    if not isinstance(seeds, dict):
        raise ValueError("malformed_seed_inventory")
    blocked = {crop for crop, count in demand.items() if count > seeds.get(crop, 0)}
    day = step // configuration["turnsPerDay"]
    for actor, action in enumerate(actions):
        if not isinstance(action, list) or not action:
            raise ValueError("malformed_selected_unit")
        applied = ["PASS"] if len(action) >= 2 and action[0] == "PLANT" and action[1] in blocked else action
        mechanics._apply_unit_action(
            farm, private, actor, applied, configuration["boardSize"], day,
            configuration["turnsPerDay"], configuration["shedCapacity"],
        )
    return farm, private


def _current_market_wheat_after(operating_stock, selected, private, maximum):
    stock = private.get("shed")
    if not isinstance(stock, dict) or type(stock.get("WHEAT", 0)) is not int or stock.get("WHEAT", 0) < 0:
        raise ValueError("malformed_shed_wheat")
    remaining = stock.get("WHEAT", 0)
    for order in operating_stock._market_prefix(selected, maximum):
        if not order or order[0] != "SELL" or len(order) < 2 or order[1] != "WHEAT":
            continue
        remaining -= min(remaining, operating_stock._order_quantity(order))
    return remaining


def _matching_obligation(window, position, next_day_start):
    matches = []
    for obligation in window.get("obligations", []):
        if obligation.get("step") != next_day_start or obligation.get("actor") != 0:
            continue
        for feed in obligation.get("feeds", []):
            if tuple(feed.get("position", ())) == position:
                matches.append((int(feed["step"]), obligation, feed))
    if not matches:
        return None
    return min(matches, key=lambda row: row[0])


def _route_has_market_op(route, start, end, operation, maximum):
    for step in range(start, end + 1):
        row = route[step]
        if not isinstance(row, dict):
            raise ValueError("malformed_live_route")
        market = row.get("market") or []
        if not isinstance(market, list):
            raise ValueError("malformed_live_route")
        for order in market[:maximum]:
            if isinstance(order, list) and order and order[0] == operation:
                return True
    return False


def build_next_feed_certificate(
        observation, selected, configuration, controller, features, *, completed=False):
    """Return ``(route_identity, certificate, report)`` or fail closed.

    Admission is intentionally narrow:
    * caller certifies this is a fully completed runtime action, never fallback;
    * current step is exact day close under the pinned 24-turn calendar;
    * exact current V5 wrapper profile and source closure are authenticated;
    * current live route descends from pinned Arlene and crosses no unresolved
      route checkpoint before next day close;
    * no next-day HIRE exists, excluding the one enabled wrapper which can
      change worker topology and mutate future route rows;
    * a hypothetical #13331 edit passes the canonical candidate guards;
    * landed operating-stock mechanics prove the candidate post-unit state can
      survive reset and fund the route feed window without future receipt credit;
    * the same animal tile has a main-farmer WHEAT pickup on the *first* next-day
      unit stage and a later feed on that day.

    Unit actions execute before market processing. Once the reset main farmer
    recovers the protected WHEAT on the first next-day unit stage, the pinned
    market-only seed/funding/pressure/capital/town wrappers cannot consume that
    carried unit. The raw next-day HIRE guard excludes redundant-hire's only
    worker-topology admission surface from the certified window.
    """
    report = {
        "certified": False,
        "reason": "not_evaluated",
        "candidate_position": None,
        "source_pins": {},
        "proof": None,
    }
    try:
        if completed is not True:
            raise ValueError("runtime_action_not_completed")
        root = _lab_root()
        report["source_pins"] = _authenticate_sources(root)
        _authenticate_feature_profile(features)
        cfg = _strict_configuration(configuration)
        player, step = _public_identity(observation, cfg["turnsPerDay"])
        if step % cfg["turnsPerDay"] != cfg["turnsPerDay"] - 1:
            raise ValueError("not_day_close")
        if step >= cfg["episodeSteps"] - cfg["turnsPerDay"]:
            raise ValueError("no_complete_next_day")

        mechanics = _load("_cadence_cert_mechanics", root / "mechanics.py")
        producer = _load("_cadence_cert_producer", root / "reference/next-panel/vendor/arlene.py")
        operating_stock = _load("_cadence_cert_operating_stock", root / "operating_stock.py")
        candidate = _load(
            "_cadence_cert_candidate",
            root / "candidates/v5/animal-cadence/alternate_feed.py",
        )
        route, checkpoints, route_identity = _route_context(controller, producer, step)
        next_day_start = step + 1
        next_day_end = next_day_start + cfg["turnsPerDay"] - 1
        if next_day_end >= len(route):
            raise ValueError("incomplete_next_day_route")
        if any(step < checkpoint <= next_day_end for checkpoint in checkpoints):
            raise ValueError("next_day_crosses_route_checkpoint")
        if _route_has_market_op(
                route, next_day_start, next_day_end, "HIRE",
                cfg["maxMarketOrdersPerTurn"]):
            raise ValueError("next_day_has_dynamic_hire_surface")

        positions = _current_feed_positions(observation, selected)
        if not positions:
            raise ValueError("no_current_feed")

        failures = []
        for position in positions:
            provisional = {
                "schema": SCHEMA,
                "observation_step": step,
                "turns_per_day": cfg["turnsPerDay"],
                **route_identity,
                "feeds": [{"position": list(position), "next_feed_step": next_day_start}],
            }
            trial, candidate_report = candidate.apply_alternate_feed(
                observation,
                selected,
                next_feed_certificate=provisional,
                route_identity=route_identity,
                turns_per_day=cfg["turnsPerDay"],
            )
            if not candidate_report.get("changed"):
                failures.append({"position": list(position), "reason": "candidate_guard_declined"})
                continue
            try:
                post_farm, post_private = _post_units(mechanics, observation, trial, cfg)
                window = operating_stock._feed_window(
                    mechanics, observation, cfg, trial, post_farm, post_private,
                    route, checkpoints,
                )
                matching = _matching_obligation(window, position, next_day_start)
                if matching is None:
                    raise ValueError("no_first_stage_pickup_for_same_tile_feed")
                feed_step, obligation, feed = matching
                if not next_day_start < feed_step <= next_day_end:
                    raise ValueError("same_tile_feed_outside_next_day")

                room = operating_stock._current_room_bound(
                    mechanics, post_private, trial.get("market", []), True,
                    capacity=cfg["shedCapacity"], maximum=cfg["maxMarketOrdersPerTurn"],
                )
                if room["after_delivery_upper"] + window["arrival_upper_before_last_pickup"] > cfg["shedCapacity"]:
                    raise ValueError("candidate_wheat_can_overflow_before_protected_pickup")
                shed_after_market = _current_market_wheat_after(
                    operating_stock, trial, post_private, cfg["maxMarketOrdersPerTurn"])
                returned_wheat = sum(
                    inv.get("WHEAT", 0) for inv in post_private["inventories"]
                    if isinstance(inv, dict) and type(inv.get("WHEAT", 0)) is int
                )
                if any(type(inv.get("WHEAT", 0)) is not int or inv.get("WHEAT", 0) < 0
                       for inv in post_private["inventories"] if isinstance(inv, dict)):
                    raise ValueError("malformed_returned_wheat")
                available = shed_after_market + returned_wheat
                required = window["required_wheat"]
                if type(required) is not int or required < 1 or required > available:
                    raise ValueError("candidate_wheat_does_not_cover_feed_window")
                if obligation.get("required_acquisition", 0) < 1:
                    raise ValueError("same_tile_feed_does_not_require_protected_pickup")

                certificate = {
                    "schema": SCHEMA,
                    "observation_step": step,
                    "turns_per_day": cfg["turnsPerDay"],
                    **route_identity,
                    "feeds": [{"position": list(position), "next_feed_step": feed_step}],
                }
                accepted, accepted_report = candidate.apply_alternate_feed(
                    observation,
                    selected,
                    next_feed_certificate=certificate,
                    route_identity=route_identity,
                    turns_per_day=cfg["turnsPerDay"],
                )
                if not accepted_report.get("changed") or accepted == selected:
                    raise ValueError("canonical_candidate_rejected_certificate")
                report.update(
                    certified=True,
                    reason="day_close_saved_wheat_reclaimed_before_next_day_market",
                    candidate_position=list(position),
                    proof={
                        "current_player": player,
                        "current_step": step,
                        "next_day_start_step": next_day_start,
                        "next_day_end_step": next_day_end,
                        "same_tile_feed_step": feed_step,
                        "pickup_step": obligation["step"],
                        "pickup_actor": obligation["actor"],
                        "pickup_quantity": obligation["quantity"],
                        "required_acquisition": obligation["required_acquisition"],
                        "feed_actor": feed["actor"],
                        "route_checkpoints": list(checkpoints),
                        "required_wheat": required,
                        "shed_wheat_after_current_market_lower": shed_after_market,
                        "returned_wheat_before_eod": returned_wheat,
                        "protected_wheat_available": available,
                        "room": room,
                        "feed_window": window,
                        "candidate_report": accepted_report,
                    },
                )
                return route_identity, certificate, report
            except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as error:
                failures.append({"position": list(position), "reason": str(error)})

        report["reason"] = "no_certifiable_current_feed"
        report["failures"] = failures
        return None, None, report
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError, OSError) as error:
        report["reason"] = str(error)
        return None, None, report


build = build_next_feed_certificate
