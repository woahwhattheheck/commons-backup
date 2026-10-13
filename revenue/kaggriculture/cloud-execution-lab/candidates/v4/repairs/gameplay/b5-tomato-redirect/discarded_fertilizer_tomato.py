# SPDX-License-Identifier: Apache-2.0
"""Experimental B5 companion: productive tomato fertilizer from certain EOD waste.

This is NEW native-compatible source, not a reconstruction of the unpublished
b5_tomato_redirect.py donor. It does not implement that donor's config switch.
The certificate is one-transition physical evidence, NOT future cash/field EV.
"""
from __future__ import annotations

from copy import deepcopy

_MOVES = frozenset(('NORTH', 'SOUTH', 'EAST', 'WEST'))
_UNIT = _MOVES | frozenset(('PASS', 'WATER', 'CARE', 'FEED', 'HARVEST',
                          'FERTILIZE', 'COLLECT_FERTILIZER', 'DIG',
                          'BUILD_COOP', 'BUILD_PASTURE', 'DROP'))
_CROPS = frozenset(('WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY', 'MELON'))
_BUYS = {'BUY_PRODUCT': frozenset(('WHEAT', 'FERTILIZER')),
         'BUY_SEED': _CROPS,
         'BUY_ANIMAL': frozenset(('GOOSE', 'COW', 'SHEEP'))}


def _integer(value, low=0):
    return type(value) is int and value >= low


def _counts(value):
    return (isinstance(value, dict)
            and all(type(k) is str and _integer(v) for k, v in value.items()))


def apply_discarded_fertilizer(observation, action, configuration=None, *, enabled=False):
    """Return (action, report); OFF/ineligible preserves exact action identity.

    Only authored literal PASS commands are replaced. The shed is already full;
    no live unit PICKUP/PLACE and no executable SELL can create shed room. Thus carried
    fertilizer would be discarded, irrespective of actor inventory iteration
    order, same-turn buys, town demand, and the other player's market actions.
    On each chosen distinct tile, actual EOD production gains exactly one TOMATO.
    The only other changed tile field is fertilized_until_day (current day + 2).
    Crop survival, harvest timing, later planting and eventual sales need gates.

    No market row is removed/reordered, no command is compacted, no input mutates,
    and nothing is retained across callbacks. Reports count proposals, NOT fills.
    Strict input support is intentionally narrower than the engine's parser.
    """
    report = {'changed': False, 'reason': 'disabled', 'proposed_actors': [],
              'expected_next_dawn_extra_tomatoes': 0,
              'retained_fertilizer_cost': 0, 'observed_fill': False}
    if enabled is not True:
        return action, report

    def unchanged(reason):
        report['reason'] = reason
        return action, report

    if not isinstance(observation, dict) or not isinstance(action, dict):
        return unchanged('unsupported_packet')
    if not isinstance(configuration, dict):
        return unchanged('unsupported_configuration')
    cfg = configuration
    for key, standard in (('boardSize', 10), ('turnsPerDay', 24),
                          ('episodeSteps', 720), ('shedCapacity', 100)):
        if key not in cfg:
            return unchanged('unsupported_configuration')
        value = cfg[key]
        if type(value) is not int or value != standard:
            return unchanged('unsupported_configuration')
    if 'maxMarketOrdersPerTurn' not in cfg:
        return unchanged('unsupported_configuration')
    cap = cfg['maxMarketOrdersPerTurn']
    if type(cap) is not int:
        return unchanged('unsupported_market_cap')
    cap = max(1, cap)  # Exact engine raw-slot admission, including zero/negative.
    now = observation.get('step')
    player = observation.get('player')
    if not _integer(now) or type(player) is not int or player not in (0, 1):
        return unchanged('unsupported_clock_or_seat')
    if now > 695 or now % 24 != 23:
        return unchanged('not_a_productive_eod')
    day = now // 24
    farms = observation.get('farms')
    private = observation.get('private')
    if (not isinstance(farms, list) or len(farms) != 2
            or not all(isinstance(f, dict) for f in farms)
            or farms[0] is farms[1] or not isinstance(private, dict)):
        return unchanged('unsupported_farm_or_private')
    farm = farms[player]
    shed = private.get('shed')
    inventories = private.get('inventories')
    hands = farm.get('hands')
    if (not _counts(shed) or not isinstance(inventories, list)
            or not all(_counts(v) for v in inventories) or not isinstance(hands, list)
            or len(inventories) != len(hands) + 1
            or len({id(v) for v in [shed, *inventories]}) != len(inventories) + 1):
        return unchanged('unsupported_or_aliased_inventory')
    if sum(shed.values()) < 100:
        return unchanged('fertilizer_not_certainly_discarded')
    commands = [action.get('farmer'), *(action.get('hands') or [])] if isinstance(action.get('hands', []), list) else []
    if (not commands
            or any(not isinstance(c, list) or not c or type(c[0]) is not str
                   for c in commands)):
        return unchanged('unsupported_unit_vector')
    # Ghost actor rows still participate in atomic PLANT demand. Preserve them
    # verbatim, but do not mistake their inert PICKUP/PASS for a live actor.
    live_commands = commands[:len(inventories)]
    for command in live_commands:
        if command[0] == 'PLANT':
            if len(command) != 2 or type(command[1]) is not str or command[1] not in _CROPS:
                return unchanged('unsupported_unit_command')
        elif command[0] not in _UNIT or len(command) != 1:
            return unchanged('unit_may_release_shed_room_or_is_unsupported')
    market = action.get('market', [])
    if not isinstance(market, list):
        return unchanged('unsupported_market_vector')
    for order in market[:cap]:
        if not isinstance(order, list):
            return unchanged('unsupported_market_row')
        if order == [] or order == ['PASS'] or order == ['HIRE'] or order == ['BUY_LAND']:
            continue
        if (len(order) != 3 or type(order[0]) is not str or order[0] not in _BUYS
                or type(order[1]) is not str or order[1] not in _BUYS[order[0]]
                or not _integer(order[2])):
            return unchanged('market_may_release_shed_room_or_is_unsupported')
    positions = [farm.get('farmer'), *hands]
    if any(not isinstance(p, (list, tuple)) or len(p) != 2
           or any(not _integer(c) or c >= 10 for c in p) for p in positions):
        return unchanged('unsupported_position')
    tiles = farm.get('tiles')
    if (not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)):
        return unchanged('unsupported_grid')
    # Serialized official observations do not share tile dictionaries. Refuse
    # aliases, including cross-farm aliases, rather than invent independent sites.
    tile_objects = []
    for public_farm in farms:
        grid = public_farm.get('tiles')
        if not isinstance(grid, list) or any(not isinstance(row, list) for row in grid):
            return unchanged('unsupported_grid')
        tile_objects.extend(id(tile) for row in grid for tile in row if isinstance(tile, dict))
    if len(set(tile_objects)) != len(tile_objects):
        return unchanged('aliased_tiles')

    replacements = []
    used = set()
    for actor, command in enumerate(live_commands):
        if command != ['PASS'] or inventories[actor].get('FERTILIZER', 0) <= 0:
            continue
        x, y = positions[actor]
        if (x, y) in used:
            continue
        tile = tiles[y][x]
        if (not isinstance(tile, dict) or tile.get('kind') != 'PLANT'
                or tile.get('crop') != 'TOMATO'):
            continue
        planted = tile.get('planted_day')
        held = tile.get('yield_units')
        coverage = tile.get('fertilized_until_day')
        dry = tile.get('consecutive_unwatered')
        expiry = tile.get('max_lifespan_step')
        if (not _integer(planted) or not _integer(held) or held > 2
                or not _integer(coverage, -1) or coverage >= day
                or not _integer(dry) or dry > 1
                or type(expiry) is not int or expiry != -1
                or tile.get('watered_today') is not True
                or not 8 <= day + 1 - planted <= 11):
            continue
        # A same-tile WATER/HARVEST/FERTILIZE/DIG can change the prestate.
        # Moving actors execute only movement, not a second destination command.
        if any(i != actor and tuple(pos) == (x, y)
               and i < len(commands) and commands[i][0] not in _MOVES | {'PASS'}
               for i, pos in enumerate(positions)):
            continue
        replacements.append((actor, x, y))
        used.add((x, y))
    if not replacements:
        return unchanged('no_productive_tomato_pass')
    out = deepcopy(action)
    for actor, _, _ in replacements:
        if actor == 0:
            out['farmer'] = ['FERTILIZE']
        else:
            out['hands'][actor - 1] = ['FERTILIZE']
    report.update(changed=True, reason='productive_tomato_from_certain_eod_waste',
                  proposed_actors=[a for a, _, _ in replacements],
                  sites=[[x, y] for _, x, y in replacements],
                  expected_next_dawn_extra_tomatoes=len(replacements),
                  effective_market_cap=cap, through_step=now,
                  economic_disposition='UNMEASURED_CONTINUATION_NOT_PROMOTION')
    return out, report
