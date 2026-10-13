#!/usr/bin/env python3
"""Source-bound V5 bulk-feeder pocket-routing research helper.

This module does not mutate production defaults. It identifies same-day route
windows where one actor repeatedly PICKUPs WHEAT from the shed and later FEEDs,
then can consolidate those pickups into the first pickup. The candidate keeps
all movement and service actions byte-equivalent; only later WHEAT PICKUP turns
become PASS. Exact observed unit-stage replay is required before materializing a
candidate because early removal of shed WHEAT can interfere with other actors.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[2]
MECHANICS_PATH = LAB / "mechanics.py"
ARLENE_PATH = LAB / "reference" / "next-panel" / "vendor" / "arlene.py"

MECHANICS_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"
ARLENE_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"


class CustodyError(RuntimeError):
    """The audited canonical source no longer matches this research carrier."""


class WitnessError(ValueError):
    """A proposed rewrite is malformed or not exactly verified."""


def git_blob_id(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _require_sources() -> None:
    actual = {
        "mechanics.py": git_blob_id(MECHANICS_PATH.read_bytes()),
        "reference/next-panel/vendor/arlene.py": git_blob_id(ARLENE_PATH.read_bytes()),
    }
    expected = {
        "mechanics.py": MECHANICS_BLOB,
        "reference/next-panel/vendor/arlene.py": ARLENE_BLOB,
    }
    drift = {name: {"expected": expected[name], "actual": blob}
             for name, blob in actual.items() if blob != expected[name]}
    if drift:
        raise CustodyError(f"canonical source drift: {json.dumps(drift, sort_keys=True)}")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CustodyError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unit(row: dict[str, Any], actor: int) -> list[Any]:
    if actor == 0:
        action = row.get("farmer", ["PASS"])
        return action if isinstance(action, list) and action else ["PASS"]
    hands = row.get("hands", [])
    if not isinstance(hands, list) or actor > len(hands):
        return ["PASS"]
    action = hands[actor - 1]
    return action if isinstance(action, list) and action else ["PASS"]


def set_unit(row: dict[str, Any], actor: int, action: list[Any]) -> None:
    if actor == 0:
        row["farmer"] = list(action)
        return
    hands = row.setdefault("hands", [])
    if not isinstance(hands, list):
        raise WitnessError("hands must be a list")
    while len(hands) < actor:
        hands.append(["PASS"])
    hands[actor - 1] = list(action)


def wheat_pickup_quantity(action: Any) -> int | None:
    if not isinstance(action, list) or len(action) < 2:
        return None
    if action[:2] != ["PICKUP", "WHEAT"]:
        return None
    try:
        quantity = int(action[2]) if len(action) >= 3 else 1
    except (TypeError, ValueError, OverflowError):
        return None
    return quantity if quantity > 0 else None


def _route_actor_count(route: list[dict[str, Any]]) -> int:
    count = 1
    for row in route:
        hands = row.get("hands", []) if isinstance(row, dict) else []
        if isinstance(hands, list):
            count = max(count, 1 + len(hands))
    return count


def scan_route(route: list[dict[str, Any]], route_id: str = "") -> list[dict[str, Any]]:
    """Find conservative same-day repeated-WHEAT-pickup windows.

    The scan itself does not claim semantic equivalence. A witness is merely a
    candidate until ``verify_unit_window`` succeeds against an observed state.
    Non-empty market rows split windows because market execution can change shed
    availability/capacity between unit stages.
    """
    if not isinstance(route, list):
        raise WitnessError("route must be a list")
    witnesses: list[dict[str, Any]] = []
    for actor in range(_route_actor_count(route)):
        step = 0
        while step < len(route):
            row = route[step]
            if not isinstance(row, dict):
                step += 1
                continue
            first_q = wheat_pickup_quantity(unit(row, actor))
            if first_q is None:
                step += 1
                continue
            day_end = min(len(route), (step // 24 + 1) * 24)
            pickup_steps = [step]
            feed_steps: list[int] = []
            total_q = first_q
            cursor = step + 1
            while cursor < day_end:
                later = route[cursor]
                if not isinstance(later, dict):
                    break
                if later.get("market"):
                    break
                action = unit(later, actor)
                op = action[0] if action else "PASS"
                if op == "DROP" or (op == "PLACE" and len(action) > 1 and action[1] == "WHEAT"):
                    break
                q = wheat_pickup_quantity(action)
                if q is not None:
                    pickup_steps.append(cursor)
                    total_q += q
                elif op == "FEED":
                    feed_steps.append(cursor)
                cursor += 1
            last_pickup = pickup_steps[-1]
            feed_after_last = [s for s in feed_steps if s > last_pickup]
            if len(pickup_steps) >= 2 and feed_after_last:
                end_step = feed_after_last[-1]
                used_feeds = [s for s in feed_steps if s <= end_step]
                witnesses.append({
                    "route_id": route_id,
                    "actor": actor,
                    "start_step": step,
                    "end_step": end_step,
                    "pickup_steps": pickup_steps,
                    "feed_steps": used_feeds,
                    "bulk_quantity": total_q,
                    "reclaimable_pickup_action_slots": len(pickup_steps) - 1,
                    "travel_savings_lower_bound": 0,
                    "requires_observed_unit_witness": True,
                })
                step = end_step + 1
            else:
                step += 1
    return witnesses


def _validate_witness(route: list[dict[str, Any]], witness: dict[str, Any]) -> None:
    actor = witness.get("actor")
    pickups = witness.get("pickup_steps")
    feeds = witness.get("feed_steps")
    start = witness.get("start_step")
    end = witness.get("end_step")
    if type(actor) is not int or actor < 0:
        raise WitnessError("actor must be a nonnegative plain int")
    if not isinstance(pickups, list) or len(pickups) < 2:
        raise WitnessError("witness requires at least two pickup steps")
    if any(type(s) is not int for s in pickups):
        raise WitnessError("pickup steps must be plain ints")
    if not isinstance(feeds, list) or not feeds or any(type(s) is not int for s in feeds):
        raise WitnessError("feed steps must be a nonempty plain-int list")
    if type(start) is not int or type(end) is not int or not (0 <= start <= end < len(route)):
        raise WitnessError("invalid witness bounds")
    if pickups[0] != start or any(s < start or s > end for s in pickups):
        raise WitnessError("pickup steps outside witness bounds")
    if any(s < start or s > end for s in feeds) or max(feeds) != end:
        raise WitnessError("feed steps outside witness bounds")
    if not any(s > pickups[-1] for s in feeds):
        raise WitnessError("witness requires a FEED after its final pickup")
    if start // 24 != end // 24:
        raise WitnessError("witness crosses a day boundary")
    expected_reclaimable = len(pickups) - 1
    if witness.get("reclaimable_pickup_action_slots") != expected_reclaimable:
        raise WitnessError("reclaimable pickup action slots do not match source pickups")
    if witness.get("travel_savings_lower_bound", 0) != 0:
        raise WitnessError("movement savings are not proved by this carrier")
    for s in range(start, end + 1):
        row = route[s]
        if not isinstance(row, dict):
            raise WitnessError("route row must be an object")
        if row.get("market"):
            raise WitnessError("market-bearing row inside unit-only witness")
    total = 0
    for s in pickups:
        q = wheat_pickup_quantity(unit(route[s], actor))
        if q is None:
            raise WitnessError(f"step {s} is not a positive WHEAT pickup")
        total += q
    if total != witness.get("bulk_quantity"):
        raise WitnessError("bulk quantity does not match source pickups")
    for s in feeds:
        if unit(route[s], actor)[:1] != ["FEED"]:
            raise WitnessError(f"step {s} is not a FEED for the witness actor")


def apply_witness(route: list[dict[str, Any]], witness: dict[str, Any]) -> list[dict[str, Any]]:
    """Consolidate the witness pickups while preserving every other action."""
    _validate_witness(route, witness)
    out = copy.deepcopy(route)
    actor = witness["actor"]
    pickups = witness["pickup_steps"]
    set_unit(out[pickups[0]], actor, ["PICKUP", "WHEAT", witness["bulk_quantity"]])
    for step in pickups[1:]:
        set_unit(out[step], actor, ["PASS"])
    for index, (before, after) in enumerate(zip(route, out)):
        if index in pickups:
            continue
        if before != after:
            raise WitnessError(f"unexpected rewrite outside pickup steps: {index}")
    return out


def _apply_rows(mechanics, observation: dict[str, Any], route: list[dict[str, Any]],
                start: int, end: int, turns_per_day: int, shed_capacity: int):
    farm = copy.deepcopy(observation["farms"][observation["player"]])
    private = copy.deepcopy(observation["private"])
    for step in range(start, end + 1):
        row = route[step]
        actions = [row.get("farmer", ["PASS"]), *row.get("hands", [])]
        for actor, action in enumerate(actions):
            mechanics._apply_unit_action(
                farm, private, actor, action, len(farm["tiles"]),
                step // turns_per_day, turns_per_day, shed_capacity,
            )
    return farm, private


def _validate_observation_start(observation: dict[str, Any], start: int) -> None:
    if not isinstance(observation, dict):
        raise WitnessError("observation must be an object")
    player = observation.get("player")
    step = observation.get("step")
    farms = observation.get("farms")
    if type(player) is not int or not isinstance(farms, list) or not (0 <= player < len(farms)):
        raise WitnessError("observation player must be an in-range plain int")
    if type(step) is not int or step != start:
        raise WitnessError("observation step must exactly match witness start")
    if not isinstance(observation.get("private"), dict):
        raise WitnessError("observation private state must be an object")


def verify_unit_window(observation: dict[str, Any], route: list[dict[str, Any]],
                       witness: dict[str, Any], *, mechanics=None,
                       turns_per_day: int = 24, shed_capacity: int = 100) -> dict[str, Any]:
    """Prove exact final farm/private equality for the unit-only witness window.

    This deliberately excludes market-bearing windows. It catches shared-shed
    interference from other actors because every actor's unit action is replayed
    in both streams.
    """
    _validate_witness(route, witness)
    start, end = witness["start_step"], witness["end_step"]
    _validate_observation_start(observation, start)
    if type(turns_per_day) is not int or turns_per_day <= 0:
        raise WitnessError("turns_per_day must be a positive plain int")
    if turns_per_day != 24:
        raise WitnessError("turns_per_day must match the canonical 24-turn route calendar")
    if type(shed_capacity) is not int or shed_capacity <= 0:
        raise WitnessError("shed_capacity must be a positive plain int")
    if mechanics is None:
        _require_sources()
        mechanics = _load("v5_bulk_feeder_mechanics", MECHANICS_PATH)
    candidate = apply_witness(route, witness)
    baseline_state = _apply_rows(mechanics, observation, route, start, end,
                                 turns_per_day, shed_capacity)
    candidate_state = _apply_rows(mechanics, observation, candidate, start, end,
                                  turns_per_day, shed_capacity)
    equivalent = baseline_state == candidate_state
    return {
        "equivalent": equivalent,
        "route_id": witness.get("route_id", ""),
        "actor": witness["actor"],
        "start_step": start,
        "end_step": end,
        "reclaimable_pickup_action_slots": len(witness["pickup_steps"]) - 1 if equivalent else 0,
        "travel_savings_lower_bound": 0,
        "candidate": candidate if equivalent else None,
    }


def materialize_verified(observation: dict[str, Any], route: list[dict[str, Any]],
                         witness: dict[str, Any], **kwargs) -> list[dict[str, Any]]:
    result = verify_unit_window(observation, route, witness, **kwargs)
    if not result["equivalent"]:
        raise WitnessError("candidate failed exact observed unit-stage equality")
    return result["candidate"]


def scan_canonical_routes() -> list[dict[str, Any]]:
    _require_sources()
    arlene = _load("v5_bulk_feeder_arlene", ARLENE_PATH)
    found: list[dict[str, Any]] = []
    for route_id, route in sorted(arlene.routes().items()):
        found.extend(scan_route(route, route_id))
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-json", type=Path,
                        help="optional JSON route list; canonical Arlene routes are used otherwise")
    parser.add_argument("--route-id", default="external")
    args = parser.parse_args(argv)
    if args.route_json:
        route = json.loads(args.route_json.read_text())
        rows = route["route"] if isinstance(route, dict) and "route" in route else route
        result = scan_route(rows, args.route_id)
    else:
        result = scan_canonical_routes()
    print(json.dumps({
        "schema": "titan-v5-bulk-feeder-pocket-audit/v2",
        "default_enabled": False,
        "witness_count": len(result),
        "reclaimable_pickup_action_slots_upper_bound": sum(
            w["reclaimable_pickup_action_slots"] for w in result
        ),
        "travel_savings_lower_bound": 0,
        "witnesses": result,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
