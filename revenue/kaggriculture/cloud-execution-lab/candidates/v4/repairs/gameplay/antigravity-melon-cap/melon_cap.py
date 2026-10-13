# SPDX-License-Identifier: Apache-2.0
"""Conservative MELON production cap for the recovered R04 lane.

The original Antigravity carrier counted only MELON already sold. That is not
sufficient to cap lifetime production: held MELON and live MELON plantings are
already committed supply too. This source therefore reserves all three before
admitting any new MELON proposal.

FourthQuadrant proposals are mutually exclusive alternatives. Their executable
work lives in ``proposal['variants'][route_id]['patches']`` and each harvested
bundle lot binds the planted tile, plant step, and 1-based worker slot back to
that program. Outer ``tiles`` and ``seed_units`` are metadata only. MELON
alternatives are therefore admitted whole and unchanged only after every route
variant authenticates the same executable MELON PLANT set and the producer's
first-day BUY_LAND/BUY_SEED/HIRE append block. Any extra executable MELON PLANT
not represented by a lot, or any mismatched producer seed purchase, fails
closed. An oversized or malformed MELON alternative is dropped; inspecting one
alternative never spends budget for another.

The default cap remains 28 units as a deliberately conservative policy knob;
it is *not* claimed to equal exact full-season town consumption. Official
engine town-center consumption is handled only by the sold-count fallback.

Default OFF. The runtime must not call this module unless the existing
``r04_melon_cap`` flag is exactly ``True``.
"""
from __future__ import annotations

from typing import Any

MELON_LIFETIME_UNIT_CAP = 28
MELON_UNITS_PER_PLANT = 6  # official engine CROPS['MELON']['max_yield']
TOWN_CENTER_INTERVAL = 24
MARKET_I0 = 10_000


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _plain_nonnegative_int(value: Any) -> int | None:
    if type(value) is not int or value < 0:
        return None
    return value


def _own_farm(observation: Any) -> dict[str, Any] | None:
    player = _plain_nonnegative_int(_get(observation, "player"))
    farms = _get(observation, "farms")
    if player is None or not isinstance(farms, (list, tuple)) or player >= len(farms):
        return None
    farm = farms[player]
    return farm if isinstance(farm, dict) else None


def _town_consumed_before_step(step: int) -> int:
    # Agent observation at step s reflects interpreter transitions for steps
    # 0..s-1. _town_consume fires at transition step % 24 == 0.
    return 0 if step == 0 else (step + TOWN_CENTER_INTERVAL - 1) // TOWN_CENTER_INTERVAL


def lifetime_melon_sold(observation: Any) -> int | None:
    """Conservative sold-unit count, or ``None`` when custody is malformed."""
    farm = _own_farm(observation)
    if farm is None:
        return None

    counters = farm.get("sale_counters")
    if isinstance(counters, dict) and "MELON" in counters:
        return _plain_nonnegative_int(counters["MELON"])

    step = _plain_nonnegative_int(_get(observation, "step"))
    market = _get(observation, "market")
    inventory = market.get("inventory") if isinstance(market, dict) else None
    inv = _plain_nonnegative_int(inventory.get("MELON")) if isinstance(inventory, dict) else None
    if step is None or inv is None:
        return None

    # MELON cannot be BUY_PRODUCT'ed and shops do not consume it. Rival sales
    # raise the same public inventory, so attributing all positive drift to us
    # is conservative for a cap.
    return max(0, inv - MARKET_I0 + _town_consumed_before_step(step))


def held_melon_units(observation: Any) -> int | None:
    """Own MELON already harvested into shed/worker inventories."""
    private = _get(observation, "private")
    if not isinstance(private, dict):
        return None
    shed = private.get("shed")
    inventories = private.get("inventories")
    if not isinstance(shed, dict) or not isinstance(inventories, list):
        return None

    shed_melon = _plain_nonnegative_int(shed.get("MELON", 0))
    if shed_melon is None:
        return None
    total = shed_melon
    for inv in inventories:
        if not isinstance(inv, dict):
            return None
        qty = _plain_nonnegative_int(inv.get("MELON", 0))
        if qty is None:
            return None
        total += qty
    return total


def planted_melon_reserve(observation: Any) -> int | None:
    """Maximum future units reserved by every live own MELON tile."""
    farm = _own_farm(observation)
    if farm is None:
        return None
    rows = farm.get("tiles")
    if not isinstance(rows, list):
        return None
    plants = 0
    for row in rows:
        if not isinstance(row, list):
            return None
        for tile in row:
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "MELON":
                plants += 1
    return plants * MELON_UNITS_PER_PLANT


def committed_melon_units(observation: Any) -> int | None:
    """Sold + held + maximum future yield of already-planted MELON."""
    sold = lifetime_melon_sold(observation)
    held = held_melon_units(observation)
    planted = planted_melon_reserve(observation)
    if sold is None or held is None or planted is None:
        return None
    return sold + held + planted


def remaining_melon_budget(observation: Any, cap: int = MELON_LIFETIME_UNIT_CAP) -> int:
    """Uncommitted MELON units; malformed custody fails closed to zero."""
    limit = _plain_nonnegative_int(cap)
    committed = committed_melon_units(observation)
    if limit is None or committed is None:
        return 0
    return max(0, limit - committed)


def max_melon_plants(observation: Any, cap: int = MELON_LIFETIME_UNIT_CAP) -> int:
    return remaining_melon_budget(observation, cap) // MELON_UNITS_PER_PLANT


def _tile_key(tile: Any) -> tuple[int, int] | None:
    if not isinstance(tile, (list, tuple)) or len(tile) != 2:
        return None
    x, y = tile
    if type(x) is not int or type(y) is not int:
        return None
    return x, y


def _worker_action(row: Any, worker: int) -> Any:
    """Return FourthQuadrant's 1-based hired-hand action from a patch row."""
    if not isinstance(row, dict) or type(worker) is not int or worker <= 0:
        return None
    hands = row.get("hands")
    if not isinstance(hands, list) or worker > len(hands):
        return None
    return hands[worker - 1]


def _is_semantic_melon_plant(action: Any) -> bool:
    """Official unit dispatch is prefix based; extended PLANT rows still execute."""
    return (
        isinstance(action, list)
        and len(action) >= 2
        and action[0] == "PLANT"
        and action[1] == "MELON"
    )


def _executable_melon_plant_identities(patches: Any) -> set[tuple[int, int]] | None:
    """Return every patched MELON PLANT as ``(step, actor)``; actor 0 is farmer."""
    if not isinstance(patches, dict):
        return None
    identities: set[tuple[int, int]] = set()
    for step, row in patches.items():
        if type(step) is not int or step < 0 or not isinstance(row, dict):
            return None
        farmer = row.get("farmer", ["PASS"])
        hands = row.get("hands", [])
        if not isinstance(hands, list):
            return None
        if _is_semantic_melon_plant(farmer):
            identities.add((step, 0))
        for actor, action in enumerate(hands, 1):
            if _is_semantic_melon_plant(action):
                identities.add((step, actor))
    return identities


def _producer_first_day_orders_ok(
    patches: Any,
    bundle: Any,
    expected_seed_units: int,
    workers: int,
) -> bool:
    """Bind FourthQuadrant's complete first-day appended market suffix.

    ``bundle.land.slot`` is the length of the inherited market row before the
    producer appends BUY_LAND, BUY_SEED, then exactly ``workers`` HIRE rows.
    Comparing the whole suffix prevents an extra unbound seed/spend row from
    hiding behind otherwise valid proposal metadata.
    """
    if not isinstance(patches, dict) or not isinstance(bundle, dict):
        return False
    land = bundle.get("land")
    if not isinstance(land, dict):
        return False
    step = _plain_nonnegative_int(land.get("step"))
    slot = _plain_nonnegative_int(land.get("slot"))
    if step is None or slot is None:
        return False
    row = patches.get(step)
    if not isinstance(row, dict):
        return False
    market = row.get("market")
    if not isinstance(market, list) or slot > len(market):
        return False
    expected_suffix = [
        ["BUY_LAND"],
        ["BUY_SEED", "MELON", expected_seed_units],
        *([[["HIRE"]][0]] * workers),
    ]
    return market[slot:] == expected_suffix


def executable_melon_plants(proposal: Any) -> int | None:
    """Authenticate one canonical FourthQuadrant MELON alternative.

    Each bundle lot must bind a unique outer tile to the exact ``plant_step``
    and 1-based worker slot whose patch action is exactly ``PLANT MELON``. Every
    route variant must cover the same outer tile set. In addition, the complete
    patched executable MELON-PLANT identity set must equal the lot identity set,
    so an extra farmer/hand PLANT cannot hide behind valid metadata. The
    producer's full first-day market suffix is authenticated from the recorded
    land coordinates.
    """
    if not isinstance(proposal, dict) or proposal.get("crop") != "MELON":
        return None

    tiles = proposal.get("tiles")
    if not isinstance(tiles, (list, tuple)) or not tiles:
        return None
    outer_tiles = [_tile_key(tile) for tile in tiles]
    if any(tile is None for tile in outer_tiles) or len(set(outer_tiles)) != len(outer_tiles):
        return None
    expected = len(outer_tiles)

    # Canonical FourthQuadrant MELON has exactly one planting cycle. Therefore
    # its seed requirement is exactly one seed per selected tile.
    seed_units = _plain_nonnegative_int(proposal.get("seed_units"))
    if seed_units != expected:
        return None
    workers = _plain_nonnegative_int(proposal.get("workers"))
    if workers is None or workers <= 0:
        return None

    variants = proposal.get("variants")
    if not isinstance(variants, dict) or not variants:
        return None

    expected_tiles = set(outer_tiles)
    for route_id, variant in variants.items():
        if not isinstance(route_id, str) or not route_id or not isinstance(variant, dict):
            return None
        patches = variant.get("patches")
        bundle = variant.get("bundle")
        lots = bundle.get("lots") if isinstance(bundle, dict) else None
        if not isinstance(patches, dict) or not isinstance(lots, list):
            return None
        if not _producer_first_day_orders_ok(patches, bundle, seed_units, workers):
            return None

        melon_lots: list[tuple[tuple[int, int], int, int]] = []
        for lot in lots:
            if not isinstance(lot, dict) or lot.get("crop") != "MELON":
                return None
            tile = _tile_key(lot.get("tile"))
            plant_step = _plain_nonnegative_int(lot.get("plant_step"))
            worker = _plain_nonnegative_int(lot.get("worker"))
            if tile is None or plant_step is None or worker is None or worker <= 0:
                return None
            row = patches.get(plant_step)
            if _worker_action(row, worker) != ["PLANT", "MELON"]:
                return None
            melon_lots.append((tile, plant_step, worker))

        if len(melon_lots) != expected:
            return None
        lot_tiles = [item[0] for item in melon_lots]
        if len(set(lot_tiles)) != expected or set(lot_tiles) != expected_tiles:
            return None

        lot_identities = [(item[1], item[2]) for item in melon_lots]
        if len(set(lot_identities)) != expected:
            return None
        executable_identities = _executable_melon_plant_identities(patches)
        if executable_identities is None or executable_identities != set(lot_identities):
            return None

    return expected


def filter_proposals(proposals: Any, observation: Any,
                     cap: int = MELON_LIFETIME_UNIT_CAP) -> list[Any]:
    """Keep complete MELON alternatives whose executable commitment fits.

    FourthQuadrant admission selects at most one supplied proposal, so candidate
    alternatives do not spend one another's budget. Objects are never shrunk:
    admitted alternatives retain identity for the consumer's membership check.
    """
    if not isinstance(proposals, (list, tuple)):
        return []
    plants_left = max_melon_plants(observation, cap)
    out: list[Any] = []
    for proposal in proposals:
        if not isinstance(proposal, dict) or proposal.get("crop") != "MELON":
            out.append(proposal)
            continue
        plants = executable_melon_plants(proposal)
        if plants is not None and plants <= plants_left:
            out.append(proposal)
    return out


def plants_blocked(observation: Any, planned_melon_plants: Any,
                   cap: int = MELON_LIFETIME_UNIT_CAP) -> int:
    """Number of requested new MELON tiles that exceed the remaining reserve."""
    planned = _plain_nonnegative_int(planned_melon_plants)
    if planned is None:
        return 0
    return max(0, planned - max_melon_plants(observation, cap))
