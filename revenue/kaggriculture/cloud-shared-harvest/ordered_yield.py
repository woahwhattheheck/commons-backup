# SPDX-License-Identifier: Apache-2.0
"""Ordered own-unit yield accounting using injected official mechanics.

This is the unit-action stage only: no market, decay, daily refresh or route
planning. Positive visible yield need not be mature; only the official action's
inventory transfer establishes a harvest. Harvesting has no carrying cap.
"""
from __future__ import annotations

import json


def _detached(value):
    """Detach the JSON observation/action values without retaining aliases."""
    return json.loads(json.dumps(value, allow_nan=False))


def _tile(farm, position):
    return farm['tiles'][position[1]][position[0]] if position is not None else None


def _yield(tile):
    return tile.get('yield_units', 0) if isinstance(tile, dict) else 0


def _resource_identity(tile):
    if not isinstance(tile, dict):
        return ('empty_or_scalar', tile)
    return tuple(tile.get(k) for k in ('kind', 'crop', 'animal', 'planted_day', 'placed_day'))


def _inventory(private, actor):
    inventories = private['inventories']
    return dict(inventories[actor]) if actor < len(inventories) else {}


def apply_joint_units(mechanics, farm, private, action, config, day):
    """Apply one official own-unit stage to supplied detached mutable state.

    Return ordered receipts and proven within-turn depletion groups. The caller
    owns farm/private and must detach them before use. Action/config are not
    modified. Mechanics must be the pinned official implementation.

    The all-or-none PLANT gate counts every submitted order, even a request for
    a hand that does not exist yet. Market HIRE does not create an actor here.
    Claims are discarded if intervening work replaces the resource or restores
    positive yield. A zero-transfer HARVEST without a surviving positive claim
    is not labelled a depletion conflict.
    """
    selected = _detached(action) if isinstance(action, dict) else {}
    cfg = config if config is not None else {}
    board_size = int(cfg.get('boardSize', 10))
    turns_per_day = max(1, int(cfg.get('turnsPerDay', 24)))
    shed_capacity = int(cfg.get('shedCapacity', 100))
    hands = selected.get('hands', [])
    if not isinstance(hands, list):
        hands = []
    actions = [selected.get('farmer', ['PASS']), *hands]
    demand = {}
    for order in actions:
        if isinstance(order, list) and len(order) >= 2 and order[0] == 'PLANT':
            crop = order[1]
            demand[crop] = demand.get(crop, 0) + 1
    blocked = {crop for crop, count in demand.items() if count > private.get('seeds', {}).get(crop, 0)}
    receipts, claims, groups = [], {}, []
    for actor, order in enumerate(actions):
        effective = (['PASS'] if isinstance(order, list) and len(order) >= 2
                     and order[0] == 'PLANT' and order[1] in blocked else order)
        raw_position = mechanics._farmer_position(farm, actor)
        position = list(raw_position) if raw_position is not None else None
        exists = position is not None
        before_tile = _tile(farm, position)
        before_yield = _yield(before_tile) if exists else None
        before_inventory = _inventory(private, actor)
        # This primitive itself ignores absent actors and illegal/no-op orders.
        mechanics._apply_unit_action(farm, private, actor, effective, board_size,
                                     day, turns_per_day, shed_capacity)
        after_inventory = _inventory(private, actor)
        after_tile = _tile(farm, position)
        after_yield = _yield(after_tile) if exists else None
        harvest = isinstance(effective, list) and bool(effective) and effective[0] == 'HARVEST'
        received = ({product: quantity - before_inventory.get(product, 0)
                     for product, quantity in after_inventory.items()
                     if quantity > before_inventory.get(product, 0)} if harvest and exists else {})
        status = 'applied' if exists else 'absent_actor'
        if harvest and exists:
            key = tuple(position)
            if received:
                status = 'harvest_received'
                claim = {'position': position, 'claimant': actor, 'received': dict(received),
                         'depleted_actors': []}
                groups.append(claim)
                claims[key] = (claim, _resource_identity(after_tile))
            elif key in claims and before_yield == 0:
                status = 'harvest_depleted'
                claims[key][0]['depleted_actors'].append(actor)
            else:
                status = 'harvest_no_transfer'
        receipts.append({'actor': actor, 'action': order, 'effective_action': effective,
                         'exists': exists, 'position': position,
                         'visible_yield_before': before_yield, 'visible_yield_after': after_yield,
                         'inventory_before': before_inventory, 'inventory_after': after_inventory,
                         'received': received, 'received_units': sum(received.values()), 'status': status})
        # Update all outstanding claims after every ordered action. Identity and
        # yield can change through planting, placement, watering or destruction.
        for key, (_, identity) in list(claims.items()):
            tile = _tile(farm, key)
            if _resource_identity(tile) != identity or _yield(tile) > 0:
                del claims[key]
    return {'unit_receipts': receipts,
            'depletion_groups': [g for g in groups if g['depleted_actors']],
            'blocked_plant_products': [crop for crop in demand if crop in blocked]}


def account_ordered_yield(mechanics, observation, action, configuration=None, *, audit):
    """Return structural and actual ordered-yield accounts without input edits.

    ``audit`` is the exact injected read-only duplicate_harvest_targets callable.
    Malformed/incompatible mechanics or observations raise; this helper does not
    replace errors with a claimed successful simulation or profitable repair.
    """
    observed = _detached(observation)
    selected = _detached(action)
    cfg = _detached(configuration) if configuration is not None else {}
    seat = observed.get('player', 0)
    farm = _detached(observed['farms'][seat])
    private = _detached(observed['private'])
    day = observed.get('step', 0) // max(1, int(cfg.get('turnsPerDay', 24)))
    structural = audit(observed, selected)
    result = apply_joint_units(mechanics, farm, private, selected, cfg, day)
    result.update(structural_duplicates=structural, final_farm=farm, final_private=private)
    return result
