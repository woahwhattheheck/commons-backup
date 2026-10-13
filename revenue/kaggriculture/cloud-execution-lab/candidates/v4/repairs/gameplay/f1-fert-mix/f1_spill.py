# SPDX-License-Identifier: Apache-2.0
"""F1 native variant: spend only a carried fertilizer unit certified to spill.

No extra hand, hire, buy, movement, registry or cross-turn plan. The certificate
is about immediate end-of-day inventory conservation, NOT future profit. The
native composer must call this before stock/receipt/history finalization.
"""
from __future__ import annotations
from copy import deepcopy

PRODUCTS = frozenset(('WHEAT', 'CARROT', 'MELON', 'TOMATO', 'STRAWBERRY',
                      'MILK', 'WOOL', 'EGG', 'FERTILIZER'))
MOVES = frozenset(('NORTH', 'SOUTH', 'EAST', 'WEST'))


def whole(value):
    if type(value) is not int or value < 0:
        raise ValueError('nonnegative integer required')
    return value


def discarded_tail(private, orders, actor, item='FERTILIZER', capacity=100,
                   max_orders=10):
    """Certify the LAST unit of item spills for every possible market fill.

    Input is AFTER the exact own-unit stage. SELL quantity bounds freed shed
    space; buys can only reduce it. Raw capped slots and ordered inventory
    prefixes are retained. Return None when unsupported or uncertified.
    """
    try:
        whole(actor); whole(capacity); whole(max_orders)
        if max_orders < 1 or type(orders) is not list:
            return None
        inventories = private['inventories']; shed = private['shed']
        if type(inventories) is not list or not 0 <= actor < len(inventories):
            return None
        containers = [shed, *inventories]
        if any(type(v) is not dict for v in containers):
            return None
        if len({id(v) for v in containers}) != len(containers):
            return None
        for inv in containers:
            for key, value in inv.items():
                if type(key) is not str:
                    return None
                whole(value)
        inv = inventories[actor]; held = whole(inv.get(item, 0))
        if not held:
            return None
        release = 0
        for order in orders[:max_orders]:
            # Invalid/empty rows occupy a slot. Only a literal supported SELL
            # may release space; ambiguous numeric conversion is not guessed.
            if order is None or order == []:
                continue
            if type(order) is not list or not order or type(order[0]) is not str:
                return None
            op = order[0]
            if op in ('HIRE', 'BUY_LAND'):
                continue
            if op not in ('SELL', 'BUY_PRODUCT', 'BUY_ANIMAL', 'BUY_SEED'):
                return None
            if len(order) < 3 or type(order[1]) is not str:
                return None
            quantity = whole(order[2])
            if op == 'SELL' and order[1] in PRODUCTS:
                release += quantity
        initial_shed = sum(shed.values())
        room_upper = max(0, capacity - max(0, initial_shed - release))
        prefix = sum(sum(v.values()) for v in inventories[:actor])
        for key, value in inv.items():
            prefix += value
            if key == item:
                break
        if prefix <= room_upper:
            return None
        return {'actor': actor, 'item': item, 'held': held,
                'tail_offset': prefix, 'room_upper': room_upper,
                'sell_release_upper': release, 'initial_shed': initial_shed}
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def potential(tile, day):
    """Optimistic future WATER gain, only an opportunity screen, not a forecast."""
    try:
        if type(tile) is not dict or tile.get('kind') != 'PLANT' or tile.get('crop') != 'WHEAT':
            return 0
        planted = whole(tile['planted_day']); have = whole(tile['yield_units'])
        covered = tile['fertilized_until_day']
        if type(covered) is not int or planted > day or have >= 6:
            return 0
        life = whole(tile['max_lifespan_step'])
        if life <= (day + 1) * 24:
            return 0
        base = arm = have
        for water_day in range(day + 1, min(day + 2, planted + 4, 29) + 1):
            if water_day < planted + 2 or life <= water_day * 24:
                continue
            base = min(6, base + (2 if covered >= water_day else 1))
            arm = min(6, arm + 2)
        return max(0, arm - base)
    except (KeyError, TypeError, ValueError):
        return 0


def apply_spill(observation, selected, configuration, *, enabled=False,
                excluded=(), report=None):
    """At most ONE literal existing PASS becomes underfoot FERTILIZE.

    Projection comparison proves no other immediate unit-stage delta. Changed
    market, native owned plans and deadline actions must be handled by caller.
    No requested action is stored as an observed fertilizer/harvest receipt.
    """
    if not enabled:
        return selected
    def note(reason, **details):
        if report is not None:
            report.append({'reason': reason, **details})
    try:
        now = whole(observation['step']); player = whole(observation['player'])
        if player not in (0, 1) or now % 24 != 23 or now > 695:
            return selected
        if any(configuration.get(k, v) != v for k, v in
               (('turnsPerDay', 24), ('episodeSteps', 720), ('boardSize', 10))):
            return selected
        capacity = whole(configuration.get('shedCapacity', 100))
        cap = whole(configuration.get('maxMarketOrdersPerTurn', 10))
        if not cap or type(selected) is not dict or type(selected.get('hands', [])) is not list:
            return selected
        farm = observation['farms'][player]; private = observation['private']
        positions = [farm['farmer'], *farm['hands']]
        commands = [selected.get('farmer', ['PASS']), *selected.get('hands', [])]
        if len(private['inventories']) != len(positions):
            return selected
        possible = []
        for actor, cmd in enumerate(commands[:len(positions)]):
            if actor in excluded or cmd != ['PASS']:
                continue
            pos = positions[actor]
            if (type(pos) is not list or len(pos) != 2
                    or any(type(v) is not int or not 0 <= v < 10 for v in pos)):
                return selected
            if whole(private['inventories'][actor].get('FERTILIZER', 0)) == 0:
                continue
            tile = farm['tiles'][pos[1]][pos[0]]
            if potential(tile, now // 24):
                possible.append((actor, pos))
        if not possible:
            return selected
        from scheduler import post_units
        base_farm, base_private = post_units(observation, selected, configuration)
        for actor, (x, y) in possible:
            tile = base_farm['tiles'][y][x]
            if not potential(tile, now // 24):
                continue
            cert = discarded_tail(base_private, selected.get('market', []), actor,
                                  capacity=capacity, max_orders=cap)
            if cert is None:
                note('not_certified_spill', actor=actor, step=now)
                continue
            arm = dict(selected)
            if actor == 0:
                arm['farmer'] = ['FERTILIZE']
            else:
                arm['hands'] = list(selected['hands'])
                arm['hands'][actor-1] = ['FERTILIZE']
            arm_farm, arm_private = post_units(observation, arm, configuration)
            expected_farm = deepcopy(base_farm); expected_private = deepcopy(base_private)
            expected_farm['tiles'][y][x]['fertilized_until_day'] = max(
                tile['fertilized_until_day'], now // 24 + 2)
            inv = expected_private['inventories'][actor]
            inv['FERTILIZER'] -= 1
            if not inv['FERTILIZER']:
                del inv['FERTILIZER']
            if arm_farm != expected_farm or arm_private != expected_private:
                note('unit_stage_collateral', actor=actor, step=now)
                continue
            note('proposed', step=now, position=[x,y], certificate=cert,
                 optimistic_bonus=potential(tile, now // 24))
            return arm
        return selected
    except (KeyError, TypeError, ValueError, IndexError):
        note('unsupported_input')
        return selected


def finish_spill(runtime, observation, configuration, returned, post):
    """Final native seam, after market guards and before all receipt commits."""
    if (not runtime.features.r04_fert_mix
            or runtime.features.consumer != 'frozen'
            or runtime.diagnostics.get('status') != 'completed'):
        return returned, post
    spatial = runtime.spatial
    if spatial is not None and any(getattr(spatial, key, None) for key in
            ('plans', 'crop_intent', 'sale_obligation', '_sale_proposal')):
        return returned, post
    if spatial is not None and (getattr(spatial, '_pending', None) or {}).get('plans'):
        return returned, post
    quadrant = runtime.quadrant
    if quadrant is not None and (quadrant.plan or quadrant.pending):
        return returned, post
    events = []
    arm = apply_spill(observation, returned, configuration, enabled=True, report=events)
    runtime.diagnostics['f1_fert_mix'] = events
    if arm is returned:
        return returned, post
    # Earlier cached post-units belong to the old action. Bind the exact new
    # action before any history/route component can consume the snapshot.
    from scheduler import post_units
    pair = post_units(observation, arm, configuration)
    snapshot = deepcopy(observation)
    snapshot['farms'][observation['player']], snapshot['private'] = pair
    runtime.consumer.selected_post_units = pair
    runtime.consumer.selected_post_units_binding = (
        int(observation['step']), int(observation['player']),
        deepcopy(arm['farmer']), deepcopy(arm.get('hands', [])))
    runtime.post = snapshot
    return arm, snapshot
