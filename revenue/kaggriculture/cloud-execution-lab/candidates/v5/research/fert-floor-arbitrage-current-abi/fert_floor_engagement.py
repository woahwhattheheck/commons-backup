# SPDX-License-Identifier: Apache-2.0
"""Fail-closed natural-engagement receipt for the V5 fertilizer-floor re-author.

A returned command is never treated as execution proof. Engagement requires a
contiguous public custody chain:
  source-authorized low-price BUY_PRODUCT -> shed custody
  -> parent PICKUP -> actor custody
  -> same actor FERTILIZE -> inventory consumption + fertilizer window effect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping

from fert_floor_current import (
    ITEM,
    MAX_BUY_PRICE,
    TURNS_PER_DAY,
    _eligible_plant,
    _source_postbuy_price,
    _source_public_price,
)

TAPE_SCHEMA = "titan-v5-fert-floor-natural-tape/v1"
RECEIPT_SCHEMA = "titan-v5-fert-floor-natural-engagement/v1"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_TAPE_KEYS = frozenset(("schema", "source_sha", "engine_id", "rows"))
_ROW_KEYS = frozenset(("observation", "returned_action"))


class EngagementError(ValueError):
    pass


def _strict_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise EngagementError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def _reject_constant(token):
    raise EngagementError(f"non-finite JSON constant is forbidden: {token}")


def loads_strict(text: str):
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise EngagementError(f"invalid JSON: {exc.msg}") from exc


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _exact_nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise EngagementError(f"{field} must be a nonnegative plain int")
    return value


def _finite_number(value: Any, field: str):
    if type(value) is int:
        if value < 0:
            raise EngagementError(f"{field} must be nonnegative")
        return value
    if type(value) is float and math.isfinite(value) and value >= 0:
        return value
    raise EngagementError(f"{field} must be a finite nonnegative number")


def _fert_qty(inventory: Any, field: str) -> int:
    if not isinstance(inventory, Mapping):
        raise EngagementError(f"{field} must be a mapping")
    return _exact_nonnegative_int(inventory.get(ITEM, 0), f"{field}.{ITEM}")


def _position(value: Any, field: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(part) is not int for part in value)
    ):
        raise EngagementError(f"{field} must be [x,y] plain ints")
    x, y = value
    if x < 0 or y < 0:
        raise EngagementError(f"{field} coordinates must be nonnegative")
    return x, y


def _tile_at(tiles: list[list[Any]], position: tuple[int, int]) -> Any:
    x, y = position
    if y >= len(tiles) or x >= len(tiles[y]):
        return None
    return tiles[y][x]


def _coverage(tile: Any) -> int | None:
    if not isinstance(tile, Mapping) or tile.get("kind") != "PLANT":
        return None
    value = tile.get("fertilized_until_day", -1)
    return value if type(value) is int else None


def _snapshot(observation: Any, returned_action: Any) -> dict[str, Any]:
    if not isinstance(observation, Mapping) or not isinstance(returned_action, Mapping):
        raise EngagementError("row observation/action must be mappings")
    player = observation.get("player")
    step = observation.get("step")
    if type(player) is not int or player not in (0, 1):
        raise EngagementError("observation.player must be plain int 0 or 1")
    if type(step) is not int or step < 0:
        raise EngagementError("observation.step must be a nonnegative plain int")

    farms = observation.get("farms")
    private = observation.get("private")
    market_state = observation.get("market")
    if (
        not isinstance(farms, list)
        or player >= len(farms)
        or not isinstance(farms[player], Mapping)
        or not isinstance(private, Mapping)
        or not isinstance(market_state, Mapping)
    ):
        raise EngagementError("observation farm/private/market shape invalid")
    farm = farms[player]
    hands = farm.get("hands")
    if not isinstance(hands, list):
        raise EngagementError("farm.hands must be a list")
    positions = [_position(farm.get("farmer"), "farm.farmer")]
    positions.extend(
        _position(value, f"farm.hands[{i}]")
        for i, value in enumerate(hands)
    )

    tiles = farm.get("tiles")
    if (
        not isinstance(tiles, list)
        or not tiles
        or any(not isinstance(row, list) for row in tiles)
    ):
        raise EngagementError("farm.tiles must be a non-empty matrix")

    inventories = private.get("inventories")
    shed = private.get("shed")
    if (
        not isinstance(inventories, list)
        or len(inventories) != len(positions)
        or not isinstance(shed, Mapping)
    ):
        raise EngagementError("private fertilizer custody cardinality invalid")
    actor_fert = tuple(
        _fert_qty(inventory, f"private.inventories[{i}]")
        for i, inventory in enumerate(inventories)
    )
    shed_fert = _fert_qty(shed, "private.shed")

    prices = market_state.get("prices")
    market_inventory = market_state.get("inventory")
    if not isinstance(prices, Mapping) or not isinstance(market_inventory, Mapping):
        raise EngagementError("public market price/inventory maps required")
    price = _finite_number(prices.get(ITEM), "public fertilizer price")
    fert_inventory = _exact_nonnegative_int(
        market_inventory.get(ITEM), "public fertilizer inventory"
    )

    farmer_action = returned_action.get("farmer")
    hand_actions = returned_action.get("hands")
    market_actions = returned_action.get("market")
    if (
        not isinstance(farmer_action, list)
        or not farmer_action
        or not isinstance(hand_actions, list)
        or len(hand_actions) != len(hands)
        or not isinstance(market_actions, list)
        or any(
            not isinstance(row, list) or not row
            for row in [farmer_action, *hand_actions]
        )
        or any(not isinstance(row, list) or not row for row in market_actions)
    ):
        raise EngagementError("returned action cardinality/rows invalid")

    return {
        "step": step,
        "player": player,
        "day": step // TURNS_PER_DAY,
        "positions": tuple(positions),
        "tiles": tiles,
        "actor_fert": actor_fert,
        "shed_fert": shed_fert,
        "price": price,
        "fert_market_inventory": fert_inventory,
        "commands": tuple(tuple(row) for row in [farmer_action, *hand_actions]),
        "market": tuple(tuple(row) for row in market_actions),
    }


def _fert_market_rows(snapshot: Mapping[str, Any]) -> list[tuple[Any, ...]]:
    return [
        row
        for row in snapshot["market"]
        if len(row) >= 2 and row[1] == ITEM
    ]


def _source_authorized_buy(snapshot: Mapping[str, Any]) -> tuple[bool, int | None]:
    inventory = snapshot["fert_market_inventory"]
    public = _source_public_price(inventory)
    postbuy = _source_postbuy_price(inventory)
    rows = _fert_market_rows(snapshot)
    return (
        postbuy is not None
        and snapshot["price"] == public
        and snapshot["shed_fert"] + sum(snapshot["actor_fert"]) == 0
        and rows == [("BUY_PRODUCT", ITEM, 1)]
    ), postbuy


def _pickup_actor(snapshot: Mapping[str, Any]) -> int | None:
    hits = [
        index
        for index, command in enumerate(snapshot["commands"])
        if command == ("PICKUP", ITEM)
    ]
    return hits[0] if len(hits) == 1 else None


def _fertilize_actor(snapshot: Mapping[str, Any], actor: int) -> bool:
    if actor < 0 or actor >= len(snapshot["commands"]):
        return False
    tile = _tile_at(snapshot["tiles"], snapshot["positions"][actor])
    return (
        snapshot["commands"][actor] == ("FERTILIZE",)
        and snapshot["actor_fert"][actor] > 0
        and _eligible_plant(tile, snapshot["day"])
    )


class NaturalEngagementTracker:
    def __init__(self):
        self._prior = None
        self._pending = None
        self._phase = "idle"
        self._cycle = None
        self._cycles = []
        self._counts = {
            "floor_buy_returned": 0,
            "floor_buy_custody_confirmed": 0,
            "pickup_returned": 0,
            "pickup_custody_confirmed": 0,
            "fertilize_returned": 0,
            "fertilize_effect_confirmed": 0,
            "aborted_cycles": 0,
        }

    def _abort(self):
        if self._phase != "idle" or self._pending is not None:
            self._counts["aborted_cycles"] += 1
        self._phase = "idle"
        self._pending = None
        self._cycle = None

    def _resolve_pending(self, current):
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        before = pending["before"]
        kind = pending["kind"]

        if kind == "buy":
            confirmed = (
                current["shed_fert"] == before["shed_fert"] + 1
                and current["actor_fert"] == before["actor_fert"]
            )
            if confirmed:
                self._counts["floor_buy_custody_confirmed"] += 1
                self._phase = "bought"
                self._cycle["buy_custody_step"] = current["step"]
            else:
                self._abort()
            return

        actor = pending["actor"]
        if actor >= len(current["actor_fert"]):
            self._abort()
            return

        if kind == "pickup":
            others_same = all(
                current["actor_fert"][index] == before["actor_fert"][index]
                for index in range(len(current["actor_fert"]))
                if index != actor
            )
            confirmed = (
                current["shed_fert"] == before["shed_fert"] - 1
                and current["actor_fert"][actor] == before["actor_fert"][actor] + 1
                and others_same
            )
            if confirmed:
                self._counts["pickup_custody_confirmed"] += 1
                self._phase = "picked"
                self._cycle["pickup_custody_step"] = current["step"]
                self._cycle["actor_index"] = actor
            else:
                self._abort()
            return

        if kind == "fertilize":
            position = before["positions"][actor]
            prior_tile = _tile_at(before["tiles"], position)
            current_tile = _tile_at(current["tiles"], position)
            prior_cover = _coverage(prior_tile)
            current_cover = _coverage(current_tile)
            target_cover = before["day"] + 2
            others_same = all(
                current["actor_fert"][index] == before["actor_fert"][index]
                for index in range(len(current["actor_fert"]))
                if index != actor
            )
            confirmed = (
                prior_cover is not None
                and current_cover is not None
                and current_cover >= target_cover
                and current_cover > prior_cover
                and current["actor_fert"][actor] == before["actor_fert"][actor] - 1
                and current["shed_fert"] == before["shed_fert"]
                and others_same
            )
            if confirmed:
                self._counts["fertilize_effect_confirmed"] += 1
                self._cycle["fertilize_effect_step"] = current["step"]
                self._cycles.append(dict(self._cycle))
                self._phase = "idle"
                self._cycle = None
            else:
                self._abort()
            return

        raise EngagementError(f"unknown pending engagement kind: {kind}")

    def observe(self, observation: Any, returned_action: Any):
        current = _snapshot(observation, returned_action)
        if self._prior is not None:
            if current["player"] != self._prior["player"]:
                raise EngagementError("tape player changed")
            if current["step"] != self._prior["step"] + 1:
                raise EngagementError("tape callbacks must be strictly contiguous")
            self._resolve_pending(current)

        fert_market = _fert_market_rows(current)
        if self._phase != "idle" and fert_market:
            self._abort()

        authorized, postbuy = _source_authorized_buy(current)
        if self._phase == "idle" and authorized:
            self._counts["floor_buy_returned"] += 1
            self._phase = "buy_returned"
            self._cycle = {
                "buy_step": current["step"],
                "buy_price_ceiling": MAX_BUY_PRICE,
                "observed_public_price": current["price"],
                "source_postbuy_price": postbuy,
                "fert_market_inventory_before": current["fert_market_inventory"],
            }
            self._pending = {"kind": "buy", "before": current}

        elif self._phase == "bought":
            actor = _pickup_actor(current)
            if actor is not None and current["shed_fert"] > 0:
                self._counts["pickup_returned"] += 1
                self._cycle["pickup_step"] = current["step"]
                self._pending = {
                    "kind": "pickup",
                    "before": current,
                    "actor": actor,
                }

        elif self._phase == "picked":
            actor = self._cycle["actor_index"]
            if _fertilize_actor(current, actor):
                self._counts["fertilize_returned"] += 1
                self._cycle["fertilize_step"] = current["step"]
                self._pending = {
                    "kind": "fertilize",
                    "before": current,
                    "actor": actor,
                }

        self._prior = current

    def receipt(
        self,
        *,
        source_sha: str,
        engine_id: str,
        rows_sha256: str,
        callback_count: int,
    ):
        if type(source_sha) is not str or _HEX40.fullmatch(source_sha) is None:
            raise EngagementError("source_sha must be 40 lowercase hex")
        if type(engine_id) is not str or not engine_id.strip():
            raise EngagementError("engine_id must be a non-empty string")
        if (
            type(rows_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", rows_sha256) is None
        ):
            raise EngagementError("rows_sha256 must be 64 lowercase hex")
        return {
            "schema": RECEIPT_SCHEMA,
            "source_sha": source_sha,
            "engine_id": engine_id,
            "rows_sha256": rows_sha256,
            "callback_count": callback_count,
            "engaged": bool(self._cycles),
            "completed_cycle_count": len(self._cycles),
            "cycles": list(self._cycles),
            "pending_phase": self._phase,
            **self._counts,
        }


def reduce_tape(report: Any) -> dict[str, Any]:
    if type(report) is not dict or set(report) != _TAPE_KEYS:
        raise EngagementError(
            "tape must have exact schema/source_sha/engine_id/rows keys"
        )
    if report["schema"] != TAPE_SCHEMA:
        raise EngagementError(f"tape schema must be {TAPE_SCHEMA}")
    rows = report["rows"]
    if not isinstance(rows, list) or not rows:
        raise EngagementError("tape rows must be a non-empty list")

    tracker = NaturalEngagementTracker()
    for index, row in enumerate(rows):
        if type(row) is not dict or set(row) != _ROW_KEYS:
            raise EngagementError(
                f"rows[{index}] must have exact observation/returned_action keys"
            )
        tracker.observe(row["observation"], row["returned_action"])
    digest = hashlib.sha256(_canonical_bytes(rows)).hexdigest()
    return tracker.receipt(
        source_sha=report["source_sha"],
        engine_id=report["engine_id"],
        rows_sha256=digest,
        callback_count=len(rows),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tape", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = loads_strict(args.tape.read_text(encoding="utf-8"))
        receipt = reduce_tape(report)
        payload = _canonical_bytes(receipt) + b"\n"
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            args.output.write_bytes(payload)
    except (OSError, EngagementError, TypeError, ValueError) as exc:
        print(f"fert_floor_engagement: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
