# SPDX-License-Identifier: Apache-2.0
"""Default-OFF V5 candidate: skip only certified redundant animal FEED actions.

The pinned engine removes an animal only after its second consecutive unfed
end-of-day. Base animal production is independent of ``fed_today``; feeding is
required for the CARE bonus. A one-day survival theorem is not a two-day route
theorem, so this transform requires a machine-checkable next-feed certificate
bound to the exact public step, day length, and current route/source/tail
identity.

The module is deliberately not wired into the canonical runtime. It is an
isolated candidate for matched evaluation.
"""
from __future__ import annotations

from copy import deepcopy


_ANIMALS = frozenset(("GOOSE", "COW", "SHEEP"))
_CERTIFICATE_SCHEMA = "titan-v5/animal-cadence/next-feed-certificate/v1"
_ROUTE_KEYS = frozenset(("route_id", "route_source_git_blob", "tail_sha256"))
_CERTIFICATE_KEYS = frozenset(
    ("schema", "observation_step", "turns_per_day", *_ROUTE_KEYS, "feeds"))
_FEED_KEYS = frozenset(("position", "next_feed_step"))


def _position(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or type(value[0]) is not int or type(value[1]) is not int):
        return None
    return (value[0], value[1])


def _action_is(action, op):
    return isinstance(action, list) and bool(action) and action[0] == op


def _lower_hex(value, length):
    return (
        isinstance(value, str)
        and len(value) == length
        and value == value.lower()
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _route_identity(value):
    if not isinstance(value, dict) or set(value) != _ROUTE_KEYS:
        return None
    route_id = value.get("route_id")
    source = value.get("route_source_git_blob")
    tail = value.get("tail_sha256")
    if not isinstance(route_id, str) or not route_id:
        return None
    if not _lower_hex(source, 40) or not _lower_hex(tail, 64):
        return None
    return {
        "route_id": route_id,
        "route_source_git_blob": source,
        "tail_sha256": tail,
    }


def _context(observation, selected):
    if not isinstance(observation, dict) or not isinstance(selected, dict):
        return None, "malformed_input"
    player = observation.get("player")
    step = observation.get("step")
    farms = observation.get("farms")
    private = observation.get("private")
    if type(player) is not int or not isinstance(farms, list) or not 0 <= player < len(farms):
        return None, "malformed_public_identity"
    if type(step) is not int or step < 0:
        return None, "malformed_public_identity"
    farm = farms[player]
    if not isinstance(farm, dict) or not isinstance(private, dict):
        return None, "malformed_private_context"
    hands = farm.get("hands")
    positions = [farm.get("farmer")]
    if not isinstance(hands, list):
        return None, "malformed_unit_positions"
    positions.extend(hands)
    positions = [_position(p) for p in positions]
    if any(p is None for p in positions):
        return None, "malformed_unit_positions"

    selected_hands = selected.get("hands")
    farmer_action = selected.get("farmer")
    if not isinstance(selected_hands, list) or len(selected_hands) != len(hands):
        return None, "malformed_selected_units"
    actions = [farmer_action, *selected_hands]
    if any(not isinstance(action, list) or not action for action in actions):
        return None, "malformed_selected_units"

    inventories = private.get("inventories")
    tiles = farm.get("tiles")
    if not isinstance(inventories, list) or len(inventories) != len(positions):
        return None, "malformed_inventories"
    if any(not isinstance(inventory, dict) for inventory in inventories):
        return None, "malformed_inventories"
    if not isinstance(tiles, list):
        return None, "malformed_tiles"
    return {
        "step": step,
        "tiles": tiles,
        "positions": positions,
        "actions": actions,
        "inventories": inventories,
    }, None


def _tile_at(tiles, position):
    x, y = position
    if y < 0 or y >= len(tiles) or not isinstance(tiles[y], list):
        return None
    row = tiles[y]
    if x < 0 or x >= len(row):
        return None
    return row[x]


def _certificate(value, route_identity, observation_step, turns_per_day):
    current = _route_identity(route_identity)
    if current is None:
        return None, None, "malformed_route_identity"
    if type(turns_per_day) is not int or turns_per_day <= 0:
        return None, current, "malformed_turns_per_day"
    if value is None:
        return None, current, "next_feed_uncertified"
    if not isinstance(value, dict) or set(value) != _CERTIFICATE_KEYS:
        return None, current, "malformed_next_feed_certificate"
    if value.get("schema") != _CERTIFICATE_SCHEMA:
        return None, current, "malformed_next_feed_certificate"
    if type(value.get("observation_step")) is not int or value["observation_step"] < 0:
        return None, current, "malformed_next_feed_certificate"
    if type(value.get("turns_per_day")) is not int or value["turns_per_day"] <= 0:
        return None, current, "malformed_next_feed_certificate"
    if value["observation_step"] != observation_step or value["turns_per_day"] != turns_per_day:
        return None, current, "next_feed_certificate_mismatch"
    for key in _ROUTE_KEYS:
        if value.get(key) != current[key]:
            return None, current, "next_feed_certificate_mismatch"

    next_day_start = ((observation_step // turns_per_day) + 1) * turns_per_day
    next_day_end = next_day_start + turns_per_day - 1
    feeds = value.get("feeds")
    if not isinstance(feeds, list) or not feeds:
        return None, current, "malformed_next_feed_certificate"
    certified = {}
    for feed in feeds:
        if not isinstance(feed, dict) or set(feed) != _FEED_KEYS:
            return None, current, "malformed_next_feed_certificate"
        position = _position(feed.get("position"))
        next_step = feed.get("next_feed_step")
        if (position is None or type(next_step) is not int
                or not next_day_start <= next_step <= next_day_end):
            return None, current, "malformed_next_feed_certificate"
        if position in certified:
            return None, current, "malformed_next_feed_certificate"
        certified[position] = next_step
    provenance = {
        "observation_step": observation_step,
        "turns_per_day": turns_per_day,
        "next_day_start_step": next_day_start,
        "next_day_end_step": next_day_end,
        **current,
    }
    return certified, provenance, None


def apply_alternate_feed(
        observation,
        selected,
        *,
        next_feed_certificate=None,
        route_identity=None,
        turns_per_day=None,
):
    """Return ``(action, report)`` without mutating either input.

    ``next_feed_certificate`` must bind every certified animal tile to a FEED
    step on the *next calendar day* and to the exact current public step, day
    length, route id, route-source Git blob, and route-tail SHA256.
    ``route_identity`` and ``turns_per_day`` are independently derived caller
    inputs. Route switch, checkpoint/rejoin, reset, source/tail changes, clock
    advance, or calendar changes therefore require a newly minted certificate.

    A current FEED is suppressed only when:
    * its tile is present in that provenance-bound next-day certificate;
    * the actor currently carries at least one WHEAT, so the edit saves spend;
    * the animal is on exact zero-strike state (``consecutive_unfed == 0``);
    * the animal is not already fed or cared today;
    * no pending CARE bonus exists; and
    * no selected CARE action targets the same current tile.
    """
    context, error = _context(observation, selected)
    report = {
        "changed": False,
        "reason": error or "no_eligible_feed",
        "feed_actions_suppressed": 0,
        "wheat_saved": 0,
        "certificate_provenance": None,
        "edits": [],
    }
    if context is None:
        return selected, report

    certified, provenance, error = _certificate(
        next_feed_certificate, route_identity, context["step"], turns_per_day)
    report["certificate_provenance"] = provenance
    if error is not None:
        report["reason"] = error
        return selected, report

    care_positions = {
        position
        for position, action in zip(context["positions"], context["actions"])
        if _action_is(action, "CARE")
    }
    eligible = []
    for actor, (position, action, inventory) in enumerate(
            zip(context["positions"], context["actions"], context["inventories"])):
        if position not in certified:
            continue
        if not _action_is(action, "FEED"):
            continue
        wheat = inventory.get("WHEAT", 0)
        if type(wheat) is not int or wheat < 1:
            continue
        tile = _tile_at(context["tiles"], position)
        if not isinstance(tile, dict) or tile.get("animal") not in _ANIMALS:
            continue
        unfed = tile.get("consecutive_unfed")
        pending = tile.get("pending_care_bonus")
        if type(unfed) is not int or unfed != 0:
            continue
        if tile.get("fed_today") is not False or tile.get("cared_today") is not False:
            continue
        if type(pending) is not int or pending != 0 or position in care_positions:
            continue
        eligible.append((actor, position, tile["animal"]))

    if not eligible:
        return selected, report

    result = deepcopy(selected)
    edits = []
    saved_tiles = set()
    for actor, position, animal in eligible:
        if actor == 0:
            result["farmer"] = ["PASS"]
        else:
            result["hands"][actor - 1] = ["PASS"]
        saved_tiles.add(position)
        edits.append({
            "actor": actor,
            "position": list(position),
            "animal": animal,
            "from": ["FEED"],
            "to": ["PASS"],
            "certified_next_feed_step": certified[position],
        })
    report.update(
        changed=True,
        reason="safe_alternate_feed",
        feed_actions_suppressed=len(edits),
        wheat_saved=len(saved_tiles),
        edits=edits,
    )
    return result, report


transform = apply_alternate_feed
