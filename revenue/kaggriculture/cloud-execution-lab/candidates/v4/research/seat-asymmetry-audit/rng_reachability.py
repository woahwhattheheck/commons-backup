#!/usr/bin/env python3
"""Current-callback SHOPSTREAM reachability for the single TITAN V4.

Research-only. This module consumes an *already-authored* current-policy action
and asks whether the exact official unit-phase semantics change the number of
``None`` farm tiles that the end-of-day weed loop will scan before a public
shop unlock.

It never invents an action, never accepts a hidden episode seed as live policy
input, and never grants gameplay/default/activation authority. The separate
WEEDBANK occupancy-lease gate owns deliberate reversible BUILD<->DIG economics.
"""
from __future__ import annotations

import hashlib
import random
from collections import Counter
from typing import Any, Mapping, Sequence

CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
SHOPS = (
    "BAKERY",
    "BRUNCH_SPOT",
    "FARMERS_MARKET",
    "ICE_CREAM_SHOP",
    "PET_CAFE",
    "PIZZA_SHOP",
    "SMOOTHIE_SHOP",
    "YARN_STORE",
)
MAX_SHOP_INSTANCES = 8

# Same immutable official engine authority already used by SHOPSTREAM/TOWNRNG.
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"


class Refusal(ValueError):
    """Fail closed on malformed evidence or source drift."""


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def authenticate_engine_bytes(data: bytes) -> dict[str, str]:
    """Authenticate the exact official engine bytes behind the semantics."""
    if not isinstance(data, bytes):
        raise Refusal("engine snapshot must be bytes")
    git_blob = _git_blob(data)
    sha256 = hashlib.sha256(data).hexdigest()
    if git_blob != ENGINE_GIT_BLOB or sha256 != ENGINE_SHA256:
        raise Refusal(
            "official engine drift: "
            f"git_blob={git_blob} sha256={sha256}"
        )
    return {"git_blob": git_blob, "sha256": sha256}


def _plain_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise Refusal(f"{name} must be a plain int")
    return value


def _plain_nonnegative_int(value: object, name: str) -> int:
    value = _plain_int(value, name)
    if value < 0:
        raise Refusal(f"{name} must be a plain nonnegative int")
    return value


def _tiles(farm: Mapping[str, Any]) -> Sequence[Sequence[Any]]:
    if not isinstance(farm, Mapping):
        raise Refusal("farm must be a mapping")
    tiles = farm.get("tiles")
    if isinstance(tiles, (str, bytes)) or not isinstance(tiles, Sequence) or not tiles:
        raise Refusal("farm.tiles must be a non-empty square matrix")
    n = len(tiles)
    for row in tiles:
        if isinstance(row, (str, bytes)) or not isinstance(row, Sequence) or len(row) != n:
            raise Refusal("farm.tiles must be a square matrix")
    return tiles


def _point(value: object, board_size: int, name: str) -> tuple[int, int]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise Refusal(f"{name} must be [x,y]")
    x, y = value
    if type(x) is not int or type(y) is not int:
        raise Refusal(f"{name} coordinates must be plain ints")
    if not (0 <= x < board_size and 0 <= y < board_size):
        raise Refusal(f"{name} out of bounds")
    return x, y


def actor_positions(farm: Mapping[str, Any]) -> tuple[tuple[int, int], ...]:
    tiles = _tiles(farm)
    n = len(tiles)
    farmer = _point(farm.get("farmer"), n, "farm.farmer")
    hands = farm.get("hands", [])
    if isinstance(hands, (str, bytes)) or not isinstance(hands, Sequence):
        raise Refusal("farm.hands must be a sequence")
    out = [farmer]
    for index, hand in enumerate(hands):
        out.append(_point(hand, n, f"farm.hands[{index}]"))
    return tuple(out)


def empty_tile_count(farm: Mapping[str, Any]) -> int:
    return sum(tile is None for row in _tiles(farm) for tile in row)


def shop_unlock_due(
    *, day: int, shop_interval: int = 3, unlocked_shop_count: int = 0
) -> bool:
    """Mirror the official `next_day % interval == 0` unlock boundary."""
    day = _plain_nonnegative_int(day, "day")
    shop_interval = _plain_nonnegative_int(shop_interval, "shop_interval")
    unlocked_shop_count = _plain_nonnegative_int(
        unlocked_shop_count, "unlocked_shop_count"
    )
    if shop_interval == 0:
        raise Refusal("shop_interval must be positive")
    next_day = day + 1
    return (
        next_day > 0
        and next_day % shop_interval == 0
        and unlocked_shop_count < MAX_SHOP_INSTANCES
    )


def _private_seed_counts(seeds: Mapping[str, Any]) -> dict[str, int]:
    if not isinstance(seeds, Mapping):
        raise Refusal("own private seed counts are required")
    out: dict[str, int] = {}
    for crop in CROPS:
        value = seeds.get(crop, 0)
        if type(value) is not int or value < 0:
            raise Refusal("seed counts must be plain nonnegative ints")
        out[crop] = value
    return out


def _authored_rows(
    farm: Mapping[str, Any],
    authored_action: Any,
) -> tuple[Any, list[Any], list[Any]]:
    """Reproduce interpreter extraction of farmer/hands rows.

    Extra hand rows are preserved in `unit_actions` because official atomic
    PLANT preflight counts them even though only existing hands later execute.
    """
    actor_positions(farm)  # validates current actor cardinality/coordinates
    if isinstance(authored_action, Mapping):
        farmer_action = authored_action.get("farmer", ["PASS"])
        hands_actions = authored_action.get("hands", [])
        if not isinstance(hands_actions, list):
            hands_actions = []
    else:
        farmer_action = ["PASS"]
        hands_actions = []
    return farmer_action, hands_actions, [farmer_action, *hands_actions]


def _executable_market_prefix(
    authored_action: Any,
    market_prefix_limit: int,
) -> tuple[list[Any], int]:
    """Mirror the engine's prefix extraction without inventing market execution.

    The official engine applies ``max(1, int(maxMarketOrdersPerTurn))`` before
    parsing rows. This evidence layer is stricter about the supplied config
    value: it must already be a plain integer, so bool/float/string coercions
    cannot silently change which rows are considered executable.
    """
    configured = _plain_int(market_prefix_limit, "market_prefix_limit")
    executable_limit = max(1, configured)
    if not isinstance(authored_action, Mapping):
        return [], executable_limit
    rows = authored_action.get("market", [])
    if not isinstance(rows, list):
        return [], executable_limit
    return rows[:executable_limit], executable_limit


def _assert_market_vacancy_resolved(
    authored_action: Any,
    market_prefix_limit: int,
) -> int:
    """Reject executable BUY_LAND until exact market replay is supplied.

    BUY_LAND is atomic in the market phase and can turn an entire locked
    quadrant into ``None`` before the same end-of-day weed/shop RNG scan. Its
    success cannot safely be inferred from starting money alone: preceding
    authored rows and opponent lockstep can alter executable cash. Therefore a
    BUY_LAND row inside the executable market prefix is an explicit evidence
    boundary, while a suffix row beyond that prefix is inert this callback.
    """
    rows, executable_limit = _executable_market_prefix(
        authored_action, market_prefix_limit
    )
    for index, row in enumerate(rows):
        if isinstance(row, list) and row and row[0] == "BUY_LAND":
            raise Refusal(
                "executable-prefix BUY_LAND requires exact market replay "
                f"before vacancy authority (market index {index})"
            )
    return executable_limit


def _blocked_plants(
    unit_actions: Sequence[Any],
    seeds: Mapping[str, int],
) -> set[str]:
    demand: dict[str, int] = {}
    for action in unit_actions:
        if (
            isinstance(action, list)
            and len(action) >= 2
            and action[0] == "PLANT"
        ):
            crop = action[1]
            if type(crop) is not str:
                raise Refusal("PLANT crop must be a string")
            demand[crop] = demand.get(crop, 0) + 1
    return {
        crop
        for crop, count in demand.items()
        if count > seeds.get(crop, 0)
    }


def _vacancy_step(
    *,
    tile: Any,
    action: Any,
    blocked_plants: set[str],
) -> tuple[Any, int, str | None]:
    """Project only the official tile-vacancy consequence of one unit row."""
    if not isinstance(action, list) or not action:
        return tile, 0, None
    op = action[0]

    if op == "PLANT":
        if len(action) < 2:
            return tile, 0, None
        crop = action[1]
        if crop in blocked_plants or crop not in CROPS or tile is not None:
            return tile, 0, None
        return {"kind": "PLANT", "crop": crop}, -1, "PLANT"

    if op == "DIG":
        if tile is None or tile == "LOCKED":
            return tile, 0, None
        if isinstance(tile, Mapping) and "animal" in tile:
            return tile, 0, None
        return None, 1, "DIG"

    if op == "BUILD_COOP":
        if tile is not None:
            return tile, 0, None
        return {"kind": "COOP"}, -1, "BUILD_COOP"

    if op == "BUILD_PASTURE":
        if tile is not None:
            return tile, 0, None
        return {"kind": "PASTURE"}, -1, "BUILD_PASTURE"

    # Movement, PASS, HIRE (market phase), service, market rows, and unknown
    # operations do not change `farm["tiles"][y][x] is None` here.
    return tile, 0, None


def authored_vacancy_projection(
    *,
    farm: Mapping[str, Any],
    own_seeds: Mapping[str, Any],
    authored_action: Any,
    market_prefix_limit: int,
) -> dict[str, Any]:
    """Project exact same-callback vacancy change from an already-authored action.

    Unit actions execute main farmer first, then existing hands in list order.
    Same-crop PLANT oversubscription is blocked atomically before execution,
    matching the official interpreter. Market rows are checked first so an
    executable BUY_LAND cannot be mislabeled vacancy-neutral.
    """
    executable_market_limit = _assert_market_vacancy_resolved(
        authored_action, market_prefix_limit
    )
    tiles = _tiles(farm)
    positions = actor_positions(farm)
    seeds = _private_seed_counts(own_seeds)
    farmer_action, hands_actions, unit_actions = _authored_rows(
        farm, authored_action
    )
    blocked = _blocked_plants(unit_actions, seeds)

    projected = [list(row) for row in tiles]
    executable_rows = [
        farmer_action,
        *[
            hands_actions[index] if index < len(hands_actions) else ["PASS"]
            for index in range(len(positions) - 1)
        ],
    ]

    effects: list[dict[str, Any]] = []
    total_delta = 0
    for actor_index, ((x, y), action) in enumerate(
        zip(positions, executable_rows)
    ):
        before = projected[y][x]
        after, delta, op = _vacancy_step(
            tile=before,
            action=action,
            blocked_plants=blocked,
        )
        if delta:
            projected[y][x] = after
            total_delta += delta
            effects.append(
                {
                    "actor_index": actor_index,
                    "position": [x, y],
                    "op": op,
                    "delta": delta,
                }
            )

    empty_before = sum(tile is None for row in tiles for tile in row)
    empty_after = sum(tile is None for row in projected for tile in row)
    if empty_after - empty_before != total_delta:
        raise Refusal("internal vacancy projection mismatch")

    return {
        "schema": "titan-v4-rngreach/authored-vacancy-v2",
        "empty_before": empty_before,
        "empty_after": empty_after,
        "delta": total_delta,
        "market_prefix_limit": executable_market_limit,
        "market_vacancy_resolved": True,
        "blocked_plant_crops": sorted(blocked),
        "effects": effects,
        "natural_engagement": total_delta != 0,
        "invented_action": False,
    }


def shop_after_empty_counts(
    *,
    seed: int,
    day: int,
    empty_tiles_by_farm: Sequence[int],
    shops: Sequence[str] = SHOPS,
) -> str:
    """Offline SHOPSTREAM cursor model; `seed` is never a live-policy input."""
    seed = _plain_nonnegative_int(seed, "seed")
    day = _plain_nonnegative_int(day, "day")
    if isinstance(empty_tiles_by_farm, (str, bytes)) or not isinstance(
        empty_tiles_by_farm, Sequence
    ):
        raise Refusal("empty_tiles_by_farm must be a sequence")
    counts = [
        _plain_nonnegative_int(value, f"empty_tiles_by_farm[{index}]")
        for index, value in enumerate(empty_tiles_by_farm)
    ]
    if not counts:
        raise Refusal("at least one farm count is required")
    if isinstance(shops, (str, bytes)) or not isinstance(shops, Sequence) or not shops:
        raise Refusal("shops must be a non-empty sequence")
    if any(type(shop) is not str or not shop for shop in shops):
        raise Refusal("shops must contain non-empty strings")

    rng = random.Random((seed * 1_000_003) ^ day)
    for count in counts:
        for _ in range(count):
            rng.random()
    return rng.choice(sorted(shops))


def offline_delta_panel(
    *,
    day: int,
    empty_tiles_by_farm: Sequence[int],
    farm_id: int,
    delta: int,
    seed_start: int = 1,
    seed_stop: int = 512,
    engine_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Measure SHOPSTREAM sensitivity for an observed authored vacancy delta.

    This is an explicit offline panel. It cannot establish live seed knowledge
    or desired-shop targeting.
    """
    day = _plain_nonnegative_int(day, "day")
    seed_start = _plain_nonnegative_int(seed_start, "seed_start")
    seed_stop = _plain_nonnegative_int(seed_stop, "seed_stop")
    if seed_start < 1 or seed_stop < seed_start:
        raise Refusal("seed panel must satisfy 1 <= seed_start <= seed_stop")
    if type(farm_id) is not int or farm_id < 0:
        raise Refusal("farm_id must be a plain nonnegative int")
    if type(delta) is not int or delta == 0:
        raise Refusal("delta must be a nonzero plain int")

    source_identity = (
        authenticate_engine_bytes(engine_bytes) if engine_bytes is not None else None
    )
    counts = [
        _plain_nonnegative_int(value, f"empty_tiles_by_farm[{index}]")
        for index, value in enumerate(empty_tiles_by_farm)
    ]
    if not counts or farm_id >= len(counts):
        raise Refusal("farm_id outside empty_tiles_by_farm")
    variant = list(counts)
    variant[farm_id] += delta
    if variant[farm_id] < 0:
        raise Refusal("delta would make empty tile count negative")

    transitions: Counter[tuple[str, str]] = Counter()
    changed = 0
    for seed in range(seed_start, seed_stop + 1):
        before = shop_after_empty_counts(
            seed=seed, day=day, empty_tiles_by_farm=counts
        )
        after = shop_after_empty_counts(
            seed=seed, day=day, empty_tiles_by_farm=variant
        )
        transitions[(before, after)] += 1
        changed += before != after

    total = seed_stop - seed_start + 1
    return {
        "schema": "titan-v4-rngreach/offline-panel-v1",
        "analysis_only": True,
        "source_authenticated": source_identity is not None,
        "source_identity": source_identity,
        "hidden_seed_live_input": False,
        "day": day,
        "seed_panel": [seed_start, seed_stop],
        "empty_tiles_before": counts,
        "empty_tiles_variant": variant,
        "farm_id": farm_id,
        "delta": delta,
        "cells": total,
        "shop_changed": changed,
        "shop_unchanged": total - changed,
        "transition_counts": [
            {"before": before, "after": after, "count": count}
            for (before, after), count in sorted(transitions.items())
        ],
        "authority": {
            "desired_shop_targeting": False,
            "economically_preferred": False,
            "activation_authority": False,
        },
    }


def reachability_report(
    *,
    farms: Sequence[Mapping[str, Any]],
    own_farm_id: int,
    own_seeds: Mapping[str, Any],
    authored_action: Any,
    day: int,
    shop_interval: int,
    unlocked_shop_count: int,
    market_prefix_limit: int,
    seed_start: int = 1,
    seed_stop: int = 512,
    engine_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Report natural current-policy engagement immediately before unlock EOD."""
    day = _plain_nonnegative_int(day, "day")
    source_identity = (
        authenticate_engine_bytes(engine_bytes) if engine_bytes is not None else None
    )
    if isinstance(farms, (str, bytes)) or not isinstance(farms, Sequence) or not farms:
        raise Refusal("farms must be a non-empty sequence")
    if type(own_farm_id) is not int or not (0 <= own_farm_id < len(farms)):
        raise Refusal("own_farm_id outside farms")

    unlock_due = shop_unlock_due(
        day=day,
        shop_interval=shop_interval,
        unlocked_shop_count=unlocked_shop_count,
    )
    counts = [empty_tile_count(farm) for farm in farms]
    projection = authored_vacancy_projection(
        farm=farms[own_farm_id],
        own_seeds=own_seeds,
        authored_action=authored_action,
        market_prefix_limit=market_prefix_limit,
    )

    panel = None
    if unlock_due and projection["delta"]:
        panel = offline_delta_panel(
            day=day,
            empty_tiles_by_farm=counts,
            farm_id=own_farm_id,
            delta=projection["delta"],
            seed_start=seed_start,
            seed_stop=seed_stop,
            engine_bytes=engine_bytes,
        )

    return {
        "schema": "titan-v4-rngreach/reachability-v2",
        "source_authenticated": source_identity is not None,
        "source_identity": source_identity,
        "unlock_due": unlock_due,
        "visible_empty_tiles": counts,
        "own_farm_id": own_farm_id,
        "authored_projection": projection,
        "offline_shop_sensitivity": panel,
        "authority": {
            "natural_current_policy_engagement": bool(
                unlock_due and projection["delta"]
            ),
            "invented_action": False,
            "opponent_same_turn_action_known": False,
            "desired_shop_targeting": False,
            "economically_preferred": False,
            "activation_authority": False,
        },
        "limits": [
            "episode seed is not a live input",
            "offline seed panel measures sensitivity, not live prediction",
            "executable-prefix BUY_LAND requires exact market replay before vacancy authority",
            "opponent same-turn tile changes can move the final RNG cursor",
            "authored engagement does not prove the action was chosen for RNG reasons",
            "WEEDBANK owns deliberate reversible occupancy-lease economics",
            "production opportunity cost and both-seat rating impact remain unpriced",
        ],
    }
