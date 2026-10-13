# SPDX-License-Identifier: Apache-2.0
"""CF1 family: same-day DROP deferral recovers one expiring COW fertilizer.

Pure proposal, default OFF and intentionally not wired to the original CF1
installer. Existing empty-HARVEST donor bytes remain unchanged. This module
reuses its boundary primitives; it does not copy the donor or create a new
runtime/configuration key. Full-state local proof is not full-game dominance.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

import r04_cow_fert_salvage as cf1

STANDARD = cf1.STANDARD
PRODUCTS = cf1.PRODUCTS
NONPRODUCING = cf1.NONPRODUCING
_standard = cf1._standard
_inventory_total = cf1._inventory_total

drop_telemetry = Counter()


def apply_eod_drop_fert_salvage(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Propose one DROP -> COLLECT with a same-callback state certificate.

    For accepted ordinary JSON game states, the full official EOD transition
    differs only by +1 own shed FERTILIZER. No extra farmer/hand, purchase, sale,
    route, seed request or future information is introduced. This is not a
    full-game dominance claim: the added future stock can consume capacity.

    The inventory bound includes every actor and all authored HARVEST/COLLECT
    rows. Six units per HARVEST deliberately overestimates all standard crops
    and animals. No purchases, PICKUP, PLACE, or PLANT are admitted. A sale of
    any delayed cargo product vetoes the proposal even if it looks redundant.
    """
    if enabled is not True or not _standard(configuration):
        return action
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return action
    step, player = observation.get('step'), observation.get('player')
    if type(step) is not int or not 0 <= step <= 695 or step % 24 != 23:
        return action
    if type(player) is not int or player not in (0, 1):
        return action
    farms, private = observation.get('farms'), observation.get('private')
    if not isinstance(farms, list) or len(farms) != 2 or not isinstance(private, dict):
        return action
    farm = farms[player]
    if not isinstance(farm, dict):
        return action
    farmer, hands, tiles = farm.get('farmer'), farm.get('hands'), farm.get('tiles')
    commands, market = action.get('hands'), action.get('market')
    if not isinstance(hands, list) or not isinstance(commands, list) or not isinstance(market, list):
        return action
    if not isinstance(tiles, list) or len(tiles) != 10 or any(not isinstance(row, list) or len(row) != 10 for row in tiles):
        return action
    positions = [farmer, *hands]
    rows = [action.get('farmer'), *commands]
    inventories, shed = private.get('inventories'), private.get('shed')
    if (len(positions) > 64 or len(rows) != len(positions)
            or not isinstance(inventories, list) or len(inventories) != len(positions)):
        return action
    if len({id(value) for value in [shed, *inventories]}) != len(inventories) + 1:
        return action
    total = _inventory_total(shed)
    if total is None:
        return action
    for inventory in inventories:
        quantity = _inventory_total(inventory)
        if quantity is None:
            return action
        total += quantity

    # Units are processed before the market. Deferring a DROP must not remove
    # cargo which one of our executable sale rows would have consumed.
    sold = set()
    for row in market[:10]:
        if row == [] or row == ['PASS']:
            continue
        if (not isinstance(row, list) or len(row) != 3 or row[0] != 'SELL'
                or not isinstance(row[1], str) or row[1] not in PRODUCTS
                or type(row[2]) is not int or row[2] < 0):
            return action
        if row[2] > 0:
            sold.add(row[1])

    sites = []
    for position, command in zip(positions, rows):
        if (not isinstance(position, list) or len(position) != 2
                or any(type(value) is not int or not 0 <= value < 10 for value in position)
                or not isinstance(command, list) or len(command) != 1
                or not isinstance(command[0], str)):
            return action
        x, y = position
        sites.append((x, y))
        op = command[0]
        if op == 'HARVEST':
            tile = tiles[y][x]
            # Reject synthetic unbounded harvest values rather than treating
            # the standard maximum of six as authority for malformed states.
            if isinstance(tile, dict):
                units = tile.get('yield_units', 0)
                if type(units) is not int or not 0 <= units <= 6:
                    return action
            total += 6
        elif op == 'COLLECT_FERTILIZER':
            total += 1
        elif op not in NONPRODUCING:
            return action
    if total + 1 > 100:
        return action

    for actor, ((x, y), command) in enumerate(zip(sites, rows)):
        if command != ['DROP'] or sites.count((x, y)) != 1:
            continue
        tile = tiles[y][x]
        if (not isinstance(tile, dict) or tile.get('kind') != 'PASTURE'
                or tile.get('animal') != 'COW'
                or tile.get('fertilizer_available') is not True):
            continue
        if (type(tile.get('fed_today')) is not bool
                or type(tile.get('cared_today')) is not bool):
            continue
        if any(type(tile.get(key)) is not int for key in
               ('yield_units', 'placed_day', 'consecutive_unfed', 'pending_care_bonus')):
            continue
        if (not 0 <= tile['yield_units'] <= 6
                or not 0 <= tile['placed_day'] <= step // 24
                or not 0 <= tile['consecutive_unfed'] <= 1
                or tile['pending_care_bonus'] < 0):
            continue
        # Python-object aliases are not ordinary serialized game observations.
        if sum(cell is tile for row in tiles for cell in row) != 1:
            continue
        rival = farms[1 - player]
        if isinstance(rival, dict) and isinstance(rival.get('tiles'), list):
            if any(cell is tile for row in rival['tiles'] if isinstance(row, list) for cell in row):
                continue
        if any(quantity > 0 and item in sold for item, quantity in inventories[actor].items()):
            continue

        result = copy.deepcopy(action)
        if actor == 0:
            result['farmer'] = ['COLLECT_FERTILIZER']
        else:
            result['hands'][actor - 1] = ['COLLECT_FERTILIZER']
        drop_telemetry['activations'] += 1
        drop_telemetry['fertilizer_units_recovered'] += 1
        return result
    return action
