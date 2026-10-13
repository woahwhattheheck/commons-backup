# SPDX-License-Identifier: Apache-2.0
"""Horizon-aware same-queue capital investment ordering.

Improves one canonical TITAN. It never invents purchases, never changes worker
actions, never credits future or rival sales, and never inspects private rival
state. Only current-queue SELL rows certified to commit at least one unit after
the exact selected unit stage may fund later capital indices.

v1 reserved cash by reducing discretionary BUY_SEED / BUY_PRODUCT to PASS,
including cross-turn upcoming land. Official first-eight games showed that
hoard: patch day-11 cash rose while terminal score and Arlene win rate fell.
v2 is ordering only. Every original purchase stays on the tape.

Distinct from P22 terminal payback, S08 maximin ranking, E16 terminal
settlement, S02 receding-horizon MPC, and fourth-quadrant land admission.
"""
from __future__ import annotations

from copy import deepcopy

PAYBACK_DAYS = {'GOOSE': 4, 'COW': 8, 'SHEEP': 6, 'LAND': 4}
EARLY_DAY_LIMIT = 20
KNOWN = frozenset(('SELL', 'HIRE', 'BUY_LAND', 'BUY_SEED', 'BUY_ANIMAL', 'BUY_PRODUCT', 'PASS'))
FUNDING = 0
OPERATING = 1
CAPITAL = 2
REST = 3


def _last_step(config):
    return int(config.get('episodeSteps', 720)) - 2


def _turns_per_day(config):
    return int(config.get('turnsPerDay', 24))


def _public_step(observation, turns_per_day):
    """Bind the optional reorder to one exact public clock representation."""
    has_step = 'step' in observation
    raw_step = observation.get('step')
    has_day = 'day' in observation
    has_hour = 'hour' in observation
    if has_day != has_hour:
        raise ValueError('public day/hour must appear together')
    derived = None
    if has_day:
        day = observation['day']
        hour = observation['hour']
        if type(day) is not int or day < 0:
            raise ValueError('public day must be a nonnegative plain integer')
        if type(hour) is not int or not 0 <= hour < turns_per_day:
            raise ValueError('public hour must be a plain integer within the day')
        derived = day * turns_per_day + hour
    if not has_step:
        if derived is None:
            raise ValueError('public clock is absent')
        return derived
    if type(raw_step) is not int or raw_step < 0:
        raise ValueError('public step must be a nonnegative plain integer')
    if derived is not None and raw_step != derived:
        raise ValueError('public clock fields disagree')
    return raw_step


def _remaining_days(now, config):
    last = _last_step(config)
    tpd = _turns_per_day(config)
    if tpd <= 0 or now > last:
        return 0
    return max(0, (last - now) // tpd)


def _horizon_end(now, config, decisions):
    last = _last_step(config)
    tpd = _turns_per_day(config)
    end = min(last, now + tpd)
    for checkpoint, *_ in decisions or ():
        if now < int(checkpoint) <= end:
            end = int(checkpoint)
            break
    return end


def _market_limit(config):
    """Return the executable raw-market prefix length, or None.

    The interpreter executes at least one row even when the configured limit is
    zero. Reject non-integral configuration rather than letting an optional
    ordering transform reinterpret the action grammar.
    """
    limit = config.get('maxMarketOrdersPerTurn', 10)
    if isinstance(limit, bool) or not isinstance(limit, int):
        return None
    return max(1, limit)


def _qty(order):
    if not isinstance(order, list) or len(order) < 3:
        return 0
    try:
        return max(0, int(order[2]))
    except (TypeError, ValueError):
        return 0


def _plant_demand(selected, route, now, end):
    """Count only PLANT demand that the current market stage can still fund.

    The engine resolves the selected unit actions before market actions. A seed
    bought on turn T therefore cannot rescue a PLANT selected on turn T; only
    route PLANTs from T+1 onward may reserve BUY_SEED priority here.
    """
    demand = {}

    def add(row):
        if not isinstance(row, dict):
            return
        hands = row.get('hands', [])
        if not isinstance(hands, list):
            hands = []
        acts = [row.get('farmer', ['PASS']), *hands]
        for action in acts:
            if isinstance(action, list) and len(action) > 1 and action[0] == 'PLANT':
                crop = action[1]
                demand[crop] = demand.get(crop, 0) + 1

    # Do not count `selected`: its unit stage executes before this turn's market.
    if route:
        for t in range(now + 1, min(end + 1, len(route))):
            add(route[t])
    return demand


def _active_order_supported(order, mechanics):
    """Whether this row is safe for an optional reordering transform to parse."""
    if not isinstance(order, list) or not order:
        return False
    op = order[0]
    if op not in KNOWN:
        return False
    if op in ('HIRE', 'BUY_LAND', 'PASS'):
        return True
    if len(order) < 3:
        return False
    try:
        item = order[1]
        if op == 'SELL':
            return item in mechanics.PRODUCTS
        if op == 'BUY_SEED':
            return item in mechanics.CROPS
        if op == 'BUY_ANIMAL':
            return item in mechanics.ANIMALS
        if op == 'BUY_PRODUCT':
            return item in ('WHEAT', 'FERTILIZER')
    except (AttributeError, TypeError):
        return False
    return False


def _project_post_unit_private(mechanics, observation, configuration, selected, now):
    """Run the exact extracted deterministic unit stage on private copies.

    Returns ``None`` on any malformed input or source mismatch. Optional capital
    ordering must never guess stock that the official market stage cannot see.
    """
    apply_unit = getattr(mechanics, '_apply_unit_action', None)
    if not callable(apply_unit):
        return None
    try:
        player = int(observation.get('player', 0))
        farms = observation.get('farms')
        if not isinstance(farms, (list, tuple)) or not (0 <= player < len(farms)):
            return None
        farm = deepcopy(farms[player])
        private = deepcopy(observation.get('private'))
        if not isinstance(farm, dict) or not isinstance(private, dict):
            return None
        if not isinstance(farm.get('tiles'), list):
            return None
        shed = private.get('shed')
        seeds = private.get('seeds')
        inventories = private.get('inventories')
        if not isinstance(shed, dict) or not isinstance(seeds, dict) or not isinstance(inventories, list):
            return None

        farmer_action = selected.get('farmer', ['PASS'])
        hands_actions = selected.get('hands', [])
        if not isinstance(hands_actions, list):
            hands_actions = []
        unit_actions = [farmer_action, *hands_actions]

        plant_demand = {}
        for action in unit_actions:
            if isinstance(action, list) and len(action) >= 2 and action[0] == 'PLANT':
                crop = action[1]
                plant_demand[crop] = plant_demand.get(crop, 0) + 1
        blocked = {crop for crop, count in plant_demand.items()
                   if count > seeds.get(crop, 0)}

        turns_per_day = max(1, int(configuration.get('turnsPerDay', 24)))
        board_size = int(configuration.get('boardSize', 10))
        shed_capacity = int(configuration.get('shedCapacity', 100))
        day = now // turns_per_day
        for index, action in enumerate(unit_actions):
            allowed = (['PASS'] if isinstance(action, list) and len(action) >= 2
                       and action[0] == 'PLANT' and action[1] in blocked else action)
            apply_unit(farm, private, index, allowed, board_size, day,
                       turns_per_day, shed_capacity)

        post_shed = private.get('shed')
        if not isinstance(post_shed, dict):
            return None
        products = getattr(mechanics, 'PRODUCTS', None)
        if not isinstance(products, (list, tuple)):
            return None
        for item in products:
            quantity = post_shed.get(item, 0)
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                return None
        return private
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError):
        return None


def _certified_funding(active, mechanics, post_private):
    """Allocate post-unit shed stock to SELL rows in their original order.

    Each returned row index is guaranteed to commit at least one unit after the
    stable FUNDING partition. The allocated unit counts prevent two SELL rows
    from claiming the same private stock.
    """
    products = tuple(mechanics.PRODUCTS)
    shed = post_private['shed']
    remaining = {item: int(shed.get(item, 0)) for item in products}
    funding = set()
    units = {}
    for index, order in enumerate(active):
        if not isinstance(order, list) or len(order) < 3 or order[0] != 'SELL':
            continue
        item = order[1]
        quantity = _qty(order)
        available = remaining.get(item, 0)
        committed = min(quantity, available)
        if committed <= 0:
            continue
        funding.add(index)
        units[index] = committed
        remaining[item] = available - committed
    return funding, units


def _capital_prefix_funded(ordered, ranks, funding_units, mechanics,
                           observation, configuration):
    """Prove moved-ahead operating spend cannot starve admitted capital.

    SELL receipts are credited only for already-certified own units and only at
    the official market floor. Every operating/capital row moved before an
    admitted purchase is charged at its exact fixed cost. This deliberately
    rejects a reorder when public evidence cannot prove the capital purchase
    still executes; it never assumes current quotes or rival future flow.
    """
    try:
        player = observation.get('player')
        if isinstance(player, bool) or not isinstance(player, int):
            return False, {'reason': 'unsupported_player'}
        farms = observation.get('farms')
        if not isinstance(farms, (list, tuple)) or not (0 <= player < len(farms)):
            return False, {'reason': 'unsupported_player'}
        farm = farms[player]
        money = farm.get('money')
        if isinstance(money, bool) or not isinstance(money, (int, float)) or money < 0:
            return False, {'reason': 'unsupported_cash'}
        floor = getattr(mechanics, 'PRICE_FLOOR', None)
        if isinstance(floor, bool) or not isinstance(floor, (int, float)) or floor < 0:
            return False, {'reason': 'unsupported_price_floor'}
        mult = configuration.get('farmHandCostMult', 1)
        if isinstance(mult, bool) or not isinstance(mult, (int, float)) or mult < 0:
            return False, {'reason': 'unsupported_hire_multiplier'}
        hires = farm.get('hires_today', len(farm.get('hands', [])))
        if isinstance(hires, bool) or not isinstance(hires, int) or hires < 0:
            return False, {'reason': 'unsupported_hire_count'}
        unlocked = farm.get('unlocked_quadrants')
        if not isinstance(unlocked, (list, tuple)) or not unlocked:
            return False, {'reason': 'unsupported_land_state'}
        land_index = len(unlocked) - 1
        required = 0.0
        guaranteed = float(money)
        capital_rows = []
        for original_index, order in ordered:
            rank = ranks[original_index]
            if rank == FUNDING:
                units = funding_units.get(original_index, 0)
                if isinstance(units, bool) or not isinstance(units, int) or units < 0:
                    return False, {'reason': 'unsupported_funding_units'}
                guaranteed += float(units) * float(floor)
                continue
            if rank == OPERATING:
                op = order[0]
                if op == 'HIRE':
                    hire_cost = getattr(mechanics, '_hire_cost', None)
                    if not callable(hire_cost):
                        return False, {'reason': 'unsupported_hire_cost'}
                    cost = hire_cost(hires, mult)
                    hires += 1
                elif op == 'BUY_SEED':
                    quantity = order[2] if len(order) > 2 else None
                    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                        return False, {'reason': 'unsupported_operating_quantity'}
                    cost = quantity * mechanics.CROPS[order[1]]['seed']
                else:
                    return False, {'reason': 'unsupported_operating_order'}
                required += float(cost)
                continue
            if rank != CAPITAL:
                continue
            op = order[0]
            if op == 'BUY_LAND':
                prices = getattr(mechanics, 'LAND_PRICES', None)
                if not isinstance(prices, (list, tuple)) or not (0 <= land_index < len(prices)):
                    return False, {'reason': 'unsupported_land_cost'}
                cost = prices[land_index]
                land_index += 1
            elif op == 'BUY_ANIMAL':
                quantity = order[2] if len(order) > 2 else None
                if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                    return False, {'reason': 'unsupported_capital_quantity'}
                cost = quantity * mechanics.ANIMALS[order[1]]['cost']
            else:
                return False, {'reason': 'unsupported_capital_order'}
            required += float(cost)
            capital_rows.append({'index': original_index, 'op': op,
                                 'required_cash_floor': required,
                                 'guaranteed_cash_floor': guaranteed})
            if guaranteed < required:
                return False, {'reason': 'capital_would_lose_funding',
                               'guaranteed_cash_floor': guaranteed,
                               'required_cash_floor': required,
                               'capital_rows': capital_rows}
        return True, {'reason': 'certified', 'guaranteed_cash_floor': guaranteed,
                      'required_cash_floor': required, 'capital_rows': capital_rows}
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError):
        return False, {'reason': 'unsupported_cash_certificate'}


def _capital_admitted(order, mechanics, remaining, day):
    if not isinstance(order, list) or not order:
        return False
    if day > EARLY_DAY_LIMIT:
        return False
    op = order[0]
    if op == 'BUY_LAND':
        return remaining >= PAYBACK_DAYS['LAND']
    if (op == 'BUY_ANIMAL' and len(order) > 2 and order[1] in mechanics.ANIMALS
            and _qty(order) > 0):
        return remaining >= PAYBACK_DAYS[order[1]]
    return False


def _rank(order, index, funding, mechanics, remaining, day, plant_demand, seeds_held):
    if not order:
        return REST
    op = order[0]
    if op == 'SELL':
        return FUNDING if index in funding else REST
    if op == 'HIRE':
        return OPERATING
    if op == 'BUY_SEED' and len(order) > 2 and order[1] in mechanics.CROPS:
        crop = order[1]
        need = max(0, int(plant_demand.get(crop, 0)) - int(seeds_held.get(crop, 0)))
        return OPERATING if need > 0 else REST
    if _capital_admitted(order, mechanics, remaining, day):
        return CAPITAL
    return REST


def order_early_capital(mechanics, observation, configuration, selected, route, decisions=()):
    """Reorder only the executable prefix of the current market tape.

    Purchases are never dropped or invented. Farmer/hands, market length, the
    multiset of active orders, and every capped suffix row remain unchanged.
    """
    report = {'changed': False, 'reason': 'init', 'moved': 0, 'reserved': 0,
              'reduced': [], 'revision': 'v4-executable-funding'}
    if not isinstance(selected, dict):
        report['reason'] = 'no_action'
        return selected, report
    raw_market = selected.get('market')
    if raw_market is None:
        raw_market = []
    if not isinstance(raw_market, list):
        report['reason'] = 'unsupported_market'
        return selected, report
    market = list(raw_market)
    if not market:
        report['reason'] = 'empty_market'
        return selected, report
    limit = _market_limit(configuration)
    if limit is None:
        report['reason'] = 'unsupported_market_limit'
        return selected, report
    active_count = min(limit, len(market))
    active = market[:active_count]
    suffix = market[active_count:]
    report.update(active_limit=limit, active_rows=active_count,
                  suffix_rows=len(suffix))

    try:
        turns_per_day = _turns_per_day(configuration)
        if turns_per_day <= 0:
            raise ValueError('turnsPerDay must be positive')
        now = _public_step(observation, turns_per_day)
        last = _last_step(configuration)
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        report['reason'] = 'unsupported_time'
        return selected, report
    if now >= last:
        report['reason'] = 'terminal_window'
        return selected, report
    if not all(_active_order_supported(order, mechanics) for order in active):
        report['reason'] = 'unsupported_active_order'
        return selected, report

    post_private = _project_post_unit_private(
        mechanics, observation, configuration, selected, now)
    if post_private is None:
        report['reason'] = 'post_unit_projection_failed'
        return selected, report
    funding, funding_units = _certified_funding(active, mechanics, post_private)
    report.update(
        certified_funding_rows=sorted(funding),
        certified_funding_units=[
            {'index': index, 'item': active[index][1], 'units': funding_units[index]}
            for index in sorted(funding)
        ],
    )

    day = now // turns_per_day
    remaining = _remaining_days(now, configuration)
    seeds_held = dict(post_private.get('seeds') or {})
    try:
        horizon = _horizon_end(now, configuration, decisions)
        plants = _plant_demand(selected, route, now, horizon)
        ranks = [
            _rank(order, index, funding, mechanics, remaining, day, plants, seeds_held)
            for index, order in enumerate(active)
        ]
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError):
        report['reason'] = 'ranking_failed'
        return selected, report
    if CAPITAL not in ranks:
        report['reason'] = 'no_admitted_capital'
        return selected, report

    indexed = list(enumerate(active))
    ordered = sorted(indexed, key=lambda item: (ranks[item[0]], item[0]))
    reordered_active = [order for _, order in ordered]
    reordered = reordered_active + suffix
    moved = sum(1 for old, new in zip(active, reordered_active) if old != new)
    if reordered_active == active:
        report.update(reason='already_ordered', moved=0, horizon_end=horizon,
                      remaining_days=remaining)
        return selected, report
    funded, cash_report = _capital_prefix_funded(
        ordered, ranks, funding_units, mechanics, observation, configuration)
    report['capital_funding'] = cash_report
    if not funded:
        report.update(reason='capital_prefix_not_fully_funded', moved=0,
                      horizon_end=horizon, remaining_days=remaining)
        return selected, report
    result = deepcopy(selected)
    result['market'] = deepcopy(reordered)
    report.update(changed=True, reason='ordered', moved=moved, reserved=0,
                  reduced=[], horizon_end=horizon, remaining_days=remaining)
    return result, report
