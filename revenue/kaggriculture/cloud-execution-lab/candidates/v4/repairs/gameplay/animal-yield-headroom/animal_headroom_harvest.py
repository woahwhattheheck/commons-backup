"""Default-OFF pre-EOD animal-product headroom rescue for TITAN V4.

This helper is deliberately narrow.  It does not buy animals, feed/care them,
move actors, schedule SELLs, or mutate shared runtime defaults.  It may replace
an already-authored literal PASS with HARVEST only when the standing animal is
provably due to produce at this end of day and the official engine would clip
part of that production at ``max_held``.

The official engine source pin is part of the contract.  Runtime composition
must authenticate it before treating this helper as eligible.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any, Mapping

EXPECTED_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"

ANIMALS = {
    "GOOSE": {
        "first_yield_day": 4,
        "interval": 1,
        "max_held": 4,
        "product": "EGG",
    },
    "COW": {
        "first_yield_day": 8,
        "interval": 2,
        "max_held": 6,
        "product": "MILK",
    },
    "SHEEP": {
        "first_yield_day": 6,
        "interval": 3,
        "max_held": 6,
        "product": "WOOL",
    },
}
SHED_BUY_PRODUCTS = {"WHEAT", "FERTILIZER"}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _strict_int(value: Any, *, minimum: int | None = None) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if minimum is not None and value < minimum:
        return None
    return value


def git_blob_sha1(path: str | Path) -> str:
    data = Path(path).read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def verify_engine_source(path: str | Path) -> bool:
    return git_blob_sha1(path) == EXPECTED_ENGINE_GIT_BLOB


def _position(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    x = _strict_int(raw[0], minimum=0)
    y = _strict_int(raw[1], minimum=0)
    if x is None or y is None:
        return None
    return (x, y)


def _farm_and_private(observation: Any) -> tuple[Any, Any, int] | None:
    farms = _get(observation, "farms")
    private = _get(observation, "private")
    player = _strict_int(_get(observation, "player"), minimum=0)
    if not isinstance(farms, list) or private is None or player is None:
        return None
    if player >= len(farms):
        return None
    return farms[player], private, player


def _clock(observation: Any, configuration: Any) -> tuple[int, int, int] | None:
    turns_per_day = _strict_int(_get(configuration, "turnsPerDay", 24), minimum=1)
    if turns_per_day is None:
        return None

    raw_hour = _get(observation, "hour")
    raw_day = _get(observation, "day")
    raw_step = _get(observation, "step")

    hour = _strict_int(raw_hour, minimum=0) if raw_hour is not None else None
    day = _strict_int(raw_day, minimum=0) if raw_day is not None else None
    step = _strict_int(raw_step, minimum=0) if raw_step is not None else None

    if step is not None:
        step_hour = step % turns_per_day
        step_day = step // turns_per_day
        if hour is not None and hour != step_hour:
            return None
        if day is not None and day != step_day:
            return None
        hour = step_hour
        day = step_day

    if hour is None or day is None or hour >= turns_per_day:
        return None
    return day, hour, turns_per_day


def _actor_positions(farm: Any) -> list[tuple[int, int]] | None:
    farmer = _position(_get(farm, "farmer"))
    hands = _get(farm, "hands", [])
    if farmer is None or not isinstance(hands, list):
        return None
    positions = [farmer]
    for raw in hands:
        pos = _position(raw)
        if pos is None:
            return None
        positions.append(pos)
    return positions


def _unit_actions(action: Any, hand_count: int) -> list[list[Any]] | None:
    if not isinstance(action, Mapping):
        return None
    farmer = action.get("farmer")
    hands = action.get("hands")
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if len(hands) != hand_count:
        return None
    rows = [farmer, *hands]
    if any(not isinstance(row, list) or not row for row in rows):
        return None
    return rows


def _tiles(farm: Any) -> list[list[Any]] | None:
    tiles = _get(farm, "tiles")
    if not isinstance(tiles, list) or not tiles:
        return None
    width = None
    for row in tiles:
        if not isinstance(row, list) or not row:
            return None
        if width is None:
            width = len(row)
        elif len(row) != width:
            return None
    return tiles


def _tile_at(tiles: list[list[Any]], pos: tuple[int, int]) -> Any:
    x, y = pos
    if y >= len(tiles) or x >= len(tiles[y]):
        return None
    return tiles[y][x]


def _nonnegative_count(value: Any) -> int | None:
    return _strict_int(value, minimum=0)


def _mapping_total(mapping: Any) -> int | None:
    if not isinstance(mapping, Mapping):
        return None
    total = 0
    for value in mapping.values():
        n = _nonnegative_count(value)
        if n is None:
            return None
        total += n
    return total


def _private_goods_total(private: Any) -> int | None:
    shed_total = _mapping_total(_get(private, "shed"))
    inventories = _get(private, "inventories")
    if shed_total is None or not isinstance(inventories, list):
        return None
    total = shed_total
    for inv in inventories:
        subtotal = _mapping_total(inv)
        if subtotal is None:
            return None
        total += subtotal
    return total


def _market_worst_case_new_shed_units(action: Mapping[str, Any]) -> int | None:
    market = action.get("market", [])
    if not isinstance(market, list):
        return None
    total = 0
    for row in market:
        if not isinstance(row, list) or not row:
            continue
        op = row[0]
        if op not in ("BUY_PRODUCT", "BUY_ANIMAL"):
            continue
        if len(row) < 3:
            return None
        qty = _strict_int(row[2], minimum=1)
        if qty is None:
            return None
        item = row[1] if len(row) >= 2 else None
        if op == "BUY_PRODUCT":
            if item not in SHED_BUY_PRODUCTS:
                # Malformed engine order cannot deposit, so ignoring it is conservative
                # only if we know it is not a legal shed-buy product.
                continue
            total += qty
        elif op == "BUY_ANIMAL":
            if item not in ANIMALS:
                continue
            total += qty
    return total


def _other_unit_worst_case_new_goods(
    rows: list[list[Any]],
    positions: list[tuple[int, int]],
    tiles: list[list[Any]],
    *,
    excluded_indices: set[int],
) -> int:
    total = 0
    for idx, row in enumerate(rows):
        if idx in excluded_indices:
            continue
        op = row[0]
        tile = _tile_at(tiles, positions[idx])
        if op == "HARVEST" and isinstance(tile, Mapping):
            units = _nonnegative_count(tile.get("yield_units", 0))
            if units is not None:
                total += units
        elif op == "COLLECT_FERTILIZER" and isinstance(tile, Mapping):
            if "animal" in tile and tile.get("fertilizer_available") is True:
                total += 1
    return total


def _production_gain(tile: Mapping[str, Any], day: int) -> dict[str, Any] | None:
    animal = tile.get("animal")
    spec = ANIMALS.get(animal)
    if spec is None:
        return None

    placed_day = _strict_int(tile.get("placed_day"), minimum=0)
    current_yield = _strict_int(tile.get("yield_units"), minimum=0)
    consecutive_unfed = _strict_int(tile.get("consecutive_unfed"), minimum=0)
    pending = _strict_int(tile.get("pending_care_bonus", 0), minimum=0)
    fed_today = tile.get("fed_today")
    if (
        placed_day is None
        or current_yield is None
        or consecutive_unfed is None
        or pending is None
        or not isinstance(fed_today, bool)
    ):
        return None

    # Engine increments consecutive_unfed before production and removes the
    # animal at >=2.  A currently-unfed animal at streak >=1 therefore produces
    # nothing because it escapes first.
    if not fed_today and consecutive_unfed >= 1:
        return {
            "animal": animal,
            "product": spec["product"],
            "current_yield": current_yield,
            "max_held": spec["max_held"],
            "production_due": False,
            "gain": 0,
            "clipped_units": 0,
            "recoverable_clipped_units": 0,
            "reason": "animal_escapes_before_production",
        }

    next_day = day + 1
    days_since_first = next_day - placed_day - spec["first_yield_day"]
    due = days_since_first >= 0 and days_since_first % spec["interval"] == 0
    if not due:
        return {
            "animal": animal,
            "product": spec["product"],
            "current_yield": current_yield,
            "max_held": spec["max_held"],
            "production_due": False,
            "gain": 0,
            "clipped_units": 0,
            "recoverable_clipped_units": 0,
            "reason": "production_not_due",
        }

    gain = 1 + (pending if fed_today else 0)
    # Engine state itself should never hold above max_held.  Refuse synthetic/
    # corrupted over-cap observations rather than laundering them into a rewrite.
    if current_yield > spec["max_held"]:
        return None

    clipped = max(0, current_yield + gain - spec["max_held"])
    # HARVEST clears only the *already-held* product before EOD.  If the new
    # production gain itself exceeds max_held, that intrinsic excess still clips
    # after the harvest.  The actually recoverable amount is therefore bounded by
    # the current held product, not the full baseline clip.
    recoverable = min(current_yield, clipped)
    return {
        "animal": animal,
        "product": spec["product"],
        "current_yield": current_yield,
        "max_held": spec["max_held"],
        "production_due": True,
        "gain": gain,
        "clipped_units": clipped,
        "recoverable_clipped_units": recoverable,
        "reason": "clip" if recoverable > 0 else "headroom_sufficient",
    }


def plan_animal_headroom_harvest(
    action: Any,
    observation: Any,
    configuration: Any,
) -> dict[str, Any]:
    """Return a fail-closed rewrite plan without mutating ``action``.

    A candidate is eligible only when all proof obligations are visible in the
    current observation and selected action.  Capacity is treated pessimistically:
    legal same-turn BUY_PRODUCT/BUY_ANIMAL rows and other authored HARVEST/COLLECT
    rows are charged in full, while SELL/DROP/consumption receives no credit.
    """
    base_report = {
        "schema": "titan-v4-animal-headroom-plan-v1",
        "engine_git_blob": EXPECTED_ENGINE_GIT_BLOB,
        "eligible": False,
        "rewrites": [],
        "reason": None,
    }
    farm_private = _farm_and_private(observation)
    clock = _clock(observation, configuration)
    if farm_private is None or clock is None:
        return {**base_report, "reason": "malformed_observation_or_clock"}
    farm, private, player = farm_private
    day, hour, turns_per_day = clock
    if hour != turns_per_day - 1:
        return {**base_report, "reason": "not_eod_callback"}

    positions = _actor_positions(farm)
    tiles = _tiles(farm)
    if positions is None or tiles is None:
        return {**base_report, "reason": "malformed_farm_geometry"}
    rows = _unit_actions(action, len(positions) - 1)
    if rows is None:
        return {**base_report, "reason": "malformed_unit_action_cardinality"}

    # Do not reason through co-located actors: an earlier actor can mutate the
    # shared tile before a later actor executes.
    if len(set(positions)) != len(positions):
        return {**base_report, "reason": "co_located_actor_order_ambiguous"}

    shed_capacity = _strict_int(_get(configuration, "shedCapacity", 100), minimum=1)
    current_goods = _private_goods_total(private)
    market_add = _market_worst_case_new_shed_units(action)
    if shed_capacity is None or current_goods is None or market_add is None:
        return {**base_report, "reason": "malformed_capacity_state"}

    candidates: list[dict[str, Any]] = []
    candidate_indices: set[int] = set()
    for idx, row in enumerate(rows):
        if row != ["PASS"]:
            continue
        tile = _tile_at(tiles, positions[idx])
        if not (isinstance(tile, Mapping) and "animal" in tile):
            continue
        prod = _production_gain(tile, day)
        if prod is None:
            continue
        if (
            prod["production_due"]
            and prod.get("recoverable_clipped_units", 0) > 0
            and prod["current_yield"] > 0
        ):
            candidate_indices.add(idx)
            candidates.append(
                {
                    "actor_index": idx,
                    "position": list(positions[idx]),
                    **prod,
                }
            )
    if not candidates:
        return {**base_report, "reason": "no_provable_clipping_pass"}

    other_add = _other_unit_worst_case_new_goods(
        rows, positions, tiles, excluded_indices=candidate_indices
    )
    # Greedy actor-index order; every accepted rewrite is independently useful
    # and capacity-safe under the same pessimistic same-turn budget.
    used = current_goods + market_add + other_add
    rewrites: list[dict[str, Any]] = []
    for cand in candidates:
        harvest_units = cand["current_yield"]
        if used + harvest_units > shed_capacity:
            continue
        used += harvest_units
        rewrites.append(cand)

    if not rewrites:
        return {
            **base_report,
            "reason": "eod_shed_capacity_not_certified",
            "capacity": {
                "current_private_goods": current_goods,
                "worst_case_market_add": market_add,
                "worst_case_other_unit_add": other_add,
                "shed_capacity": shed_capacity,
            },
        }

    return {
        **base_report,
        "eligible": True,
        "reason": "provable_animal_product_clip",
        "player": player,
        "day": day,
        "hour": hour,
        "rewrites": rewrites,
        "saved_clipped_units": sum(r["recoverable_clipped_units"] for r in rewrites),
        "capacity": {
            "current_private_goods": current_goods,
            "worst_case_market_add": market_add,
            "worst_case_other_unit_add": other_add,
            "accepted_harvest_units": sum(r["current_yield"] for r in rewrites),
            "post_action_worst_case_private_goods": used,
            "shed_capacity": shed_capacity,
        },
    }


def apply_animal_headroom_harvest(
    action: Any,
    observation: Any,
    configuration: Any,
    *,
    enabled: bool = False,
) -> Any:
    """Return ``action`` unchanged unless the default-OFF proof gate passes."""
    if enabled is not True:
        return action
    plan = plan_animal_headroom_harvest(action, observation, configuration)
    if not plan["eligible"]:
        return action

    out = deepcopy(action)
    hands = out["hands"]
    for row in plan["rewrites"]:
        idx = row["actor_index"]
        if idx == 0:
            out["farmer"] = ["HARVEST"]
        else:
            hands[idx - 1] = ["HARVEST"]
    return out
