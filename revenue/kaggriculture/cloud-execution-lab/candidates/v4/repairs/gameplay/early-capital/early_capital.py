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
import math

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

    add(selected)
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

        # Match the official interpreter's atomic same-crop PLANT admission:
        # over-subscribed current batches become all PASS before unit execution.
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


def _certified_land_targets(active, observation, mechanics):
    """Allocate remaining official quadrant unlocks to BUY_LAND rows.

    The official engine selects land structurally from ``LAND_ORDER`` and makes
    every later BUY_LAND a no-op once all quadrants are unlocked. A stable
    original-order allocation prevents multiple rows from claiming the same
    remaining unlock, just as funding certification debits shared shed stock.
    ``None`` denotes malformed or source-mismatched farm state.
    """
    try:
        if not isinstance(observation, dict):
            return None
        player = observation.get('player', 0)
        if isinstance(player, bool) or not isinstance(player, int):
            return None
        farms = observation.get('farms')
        if (not isinstance(farms, (list, tuple))
                or not (0 <= player < len(farms))):
            return None
        farm = farms[player]
        if not isinstance(farm, dict):
            return None
        unlocked = farm.get('unlocked_quadrants')
        land_order = getattr(mechanics, 'LAND_ORDER', None)
        if (not isinstance(unlocked, list)
                or not isinstance(land_order, (list, tuple))):
            return None
        official = ['NW', *land_order]
        if (not all(isinstance(value, str) for value in official)
                or len(set(official)) != len(official)
                or not unlocked
                or unlocked != official[:len(unlocked)]):
            return None

        slots = len(official) - len(unlocked)
        targets = set()
        for index, order in enumerate(active):
            if slots <= 0:
                break
            if isinstance(order, list) and order and order[0] == 'BUY_LAND':
                targets.add(index)
                slots -= 1
        return targets
    except (AttributeError, IndexError, OverflowError, TypeError, ValueError):
        return None


def _operating_admitted(order, mechanics, plant_demand, seeds_held):
    if not isinstance(order, list) or not order:
        return False
    op = order[0]
    if op == 'HIRE':
        return True
    if op == 'BUY_SEED' and len(order) > 2 and order[1] in mechanics.CROPS:
        crop = order[1]
        need = max(
            0,
            int(plant_demand.get(crop, 0))
            - int(seeds_held.get(crop, 0)),
        )
        return need > 0
    return False


def _public_row0_sell_quote(mechanics, observation, item):
    """Return the exact public row-0 SELL quote, or None on any drift.

    Once certified SELL rows are stably promoted, the first certified unit is
    quoted before either player commits row 0. Later units can only rely on the
    official price floor because rival rows may have changed public inventory.
    """
    try:
        market = observation.get('market')
        if not isinstance(market, dict):
            return None
        inventory = market.get('inventory')
        if not isinstance(inventory, dict) or item not in inventory:
            return None
        amount = inventory[item]
        if isinstance(amount, bool) or not isinstance(amount, int):
            return None
        quote_fn = getattr(mechanics, 'market_price', None)
        if not callable(quote_fn):
            return None
        quote = quote_fn(item, amount, market.get('params'))
        if isinstance(quote, bool) or not isinstance(quote, (int, float)):
            return None
        if not math.isfinite(float(quote)):
            return None
        floor = getattr(mechanics, 'PRICE_FLOOR', None)
        if isinstance(floor, bool) or not isinstance(floor, (int, float)):
            return None
        if quote < floor:
            return None
        prices = market.get('prices')
        if isinstance(prices, dict) and item in prices:
            published = prices[item]
            if (isinstance(published, bool)
                    or not isinstance(published, (int, float))
                    or not math.isfinite(float(published))
                    or published != quote):
                return None
        return float(quote)
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        return None


def _guaranteed_funding_proceeds(
        active, funding, funding_units, mechanics, observation):
    """Lower-bound proceeds after the stable FUNDING partition.

    The first promoted SELL unit has an exact public row-0 quote. Every
    additional certified unit is bounded only by the official positive price
    floor, which remains valid under all rival market interleavings.
    """
    try:
        floor = getattr(mechanics, 'PRICE_FLOOR', None)
        if (isinstance(floor, bool)
                or not isinstance(floor, (int, float))
                or not math.isfinite(float(floor))
                or floor <= 0):
            return None
        total = 0.0
        detail = []
        first_unit = True
        for index in sorted(funding):
            units = funding_units.get(index)
            order = active[index]
            if (isinstance(units, bool)
                    or not isinstance(units, int)
                    or units <= 0
                    or not isinstance(order, list)
                    or len(order) < 3
                    or order[0] != 'SELL'):
                return None
            item = order[1]
            exact_units = 0
            proceeds = float(floor) * units
            if first_unit:
                quote = _public_row0_sell_quote(mechanics, observation, item)
                if quote is None:
                    return None
                proceeds += quote - float(floor)
                exact_units = 1
                first_unit = False
            total += proceeds
            detail.append({
                'index': index,
                'item': item,
                'units': units,
                'exact_row0_units': exact_units,
                'proceeds_lower_bound': proceeds,
            })
        return total, detail
    except (IndexError, KeyError, OverflowError, TypeError, ValueError):
        return None


def _operating_cost_upper_bound(
        active, operating_rows, mechanics, observation, configuration):
    """Return the full exact cost of every row promoted ahead of capital."""
    try:
        player = observation.get('player', 0)
        if isinstance(player, bool) or not isinstance(player, int):
            return None
        farms = observation.get('farms')
        if (not isinstance(farms, (list, tuple))
                or not (0 <= player < len(farms))):
            return None
        farm = farms[player]
        if not isinstance(farm, dict):
            return None
        hires_today = farm.get('hires_today', 0)
        if (isinstance(hires_today, bool)
                or not isinstance(hires_today, int)
                or hires_today < 0):
            return None
        hire_mult = configuration.get(
            'farmHandCostMult',
            getattr(mechanics, 'FARM_HAND_COST_MULT', 1),
        )
        if (isinstance(hire_mult, bool)
                or not isinstance(hire_mult, int)
                or hire_mult < 0):
            return None
        hire_cost = getattr(mechanics, '_hire_cost', None)
        if not callable(hire_cost):
            return None

        total = 0.0
        detail = []
        for index in sorted(operating_rows):
            order = active[index]
            op = order[0]
            if op == 'HIRE':
                cost = hire_cost(hires_today, hire_mult)
                hires_today += 1
            elif op == 'BUY_SEED':
                quantity = _qty(order)
                if quantity <= 0:
                    return None
                seed_cost = mechanics.CROPS[order[1]]['seed']
                cost = seed_cost * quantity
            else:
                return None
            if (isinstance(cost, bool)
                    or not isinstance(cost, (int, float))
                    or not math.isfinite(float(cost))
                    or cost < 0):
                return None
            total += float(cost)
            detail.append({
                'index': index,
                'op': op,
                'cost_upper_bound': float(cost),
            })
        return total, detail
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError):
        return None


def _capital_window_admitted(order, index, mechanics, remaining, day, land_targets):
    if not isinstance(order, list) or not order:
        return False
    if day > EARLY_DAY_LIMIT:
        return False
    op = order[0]
    if op == 'BUY_LAND':
        return (
            land_targets is not None
            and index in land_targets
            and remaining >= PAYBACK_DAYS['LAND']
        )
    if (op == 'BUY_ANIMAL' and len(order) > 2 and order[1] in mechanics.ANIMALS
            and _qty(order) > 0):
        return remaining >= PAYBACK_DAYS[order[1]]
    return False


def _certified_capital_rows(
        active, mechanics, observation, configuration, post_private,
        funding, funding_units, operating_rows, land_targets, remaining, day):
    """Prove the promoted CAPITAL partition can commit in full.

    This is intentionally stronger than "the target exists". It carries a
    conservative cash lower bound through guaranteed SELL proceeds, every
    promoted OPERATING cost, and each capital row in stable source order. LAND
    uses the exact next LAND_PRICES slot. BUY_ANIMAL requires the entire parser-
    coerced quantity to fit both the cash and post-funding shed-capacity lower
    bounds. If any live capital-like row cannot be proved, the whole capital
    transform is disabled rather than allowing a later row to leapfrog an
    unresolved resource consumer.
    """
    try:
        player = observation.get('player', 0)
        if isinstance(player, bool) or not isinstance(player, int):
            return None
        farms = observation.get('farms')
        if (not isinstance(farms, (list, tuple))
                or not (0 <= player < len(farms))):
            return None
        farm = farms[player]
        if not isinstance(farm, dict):
            return None
        money = farm.get('money')
        if (isinstance(money, bool)
                or not isinstance(money, (int, float))
                or not math.isfinite(float(money))
                or money < 0):
            return None

        proceeds_info = _guaranteed_funding_proceeds(
            active, funding, funding_units, mechanics, observation)
        if proceeds_info is None:
            return None
        funding_proceeds, funding_detail = proceeds_info

        operating_info = _operating_cost_upper_bound(
            active, operating_rows, mechanics, observation, configuration)
        if operating_info is None:
            return None
        operating_cost, operating_detail = operating_info

        cash = float(money) + funding_proceeds - operating_cost
        if not math.isfinite(cash):
            return None

        shed = post_private.get('shed')
        if not isinstance(shed, dict):
            return None
        occupancy = 0
        for quantity in shed.values():
            if (isinstance(quantity, bool)
                    or not isinstance(quantity, int)
                    or quantity < 0):
                return None
            occupancy += quantity
        sold_units = sum(funding_units.values())
        occupancy -= sold_units
        if occupancy < 0:
            return None
        capacity = configuration.get('shedCapacity', 100)
        if (isinstance(capacity, bool)
                or not isinstance(capacity, int)
                or capacity < 0
                or occupancy > capacity):
            return None

        unlocked = farm.get('unlocked_quadrants')
        land_prices = getattr(mechanics, 'LAND_PRICES', None)
        if not isinstance(unlocked, list) or not isinstance(land_prices, (list, tuple)):
            return None
        land_slot = len(unlocked) - 1
        if land_slot < 0:
            return None

        rows = set()
        allocations = []
        for index, order in enumerate(active):
            if not isinstance(order, list) or not order:
                continue
            op = order[0]
            if op not in ('BUY_LAND', 'BUY_ANIMAL'):
                continue

            if op == 'BUY_LAND' and (land_targets is not None
                                     and index not in land_targets):
                # A structurally exhausted duplicate is proven to be a no-op
                # once all earlier certified targets execute.
                continue
            if op == 'BUY_ANIMAL' and _qty(order) <= 0:
                # The pinned parser rejects non-positive/coercion-failed rows.
                continue

            if not _capital_window_admitted(
                    order, index, mechanics, remaining, day, land_targets):
                return {
                    'rows': set(),
                    'allocations': [],
                    'funding_proceeds_lower_bound': funding_proceeds,
                    'funding_proceeds': funding_detail,
                    'operating_cost_upper_bound': operating_cost,
                    'operating_costs': operating_detail,
                    'cash_after_operating_lower_bound':
                        float(money) + funding_proceeds - operating_cost,
                    'reason': 'unproved_capital_sequence',
                }

            if op == 'BUY_LAND':
                if land_slot >= len(land_prices):
                    return None
                cost = land_prices[land_slot]
                if (isinstance(cost, bool)
                        or not isinstance(cost, (int, float))
                        or not math.isfinite(float(cost))
                        or cost < 0):
                    return None
                if cash < cost:
                    return {
                        'rows': set(),
                        'allocations': [],
                        'funding_proceeds_lower_bound': funding_proceeds,
                        'funding_proceeds': funding_detail,
                        'operating_cost_upper_bound': operating_cost,
                        'operating_costs': operating_detail,
                        'cash_after_operating_lower_bound':
                            float(money) + funding_proceeds - operating_cost,
                        'reason': 'unproved_capital_sequence',
                    }
                cash -= float(cost)
                land_slot += 1
                rows.add(index)
                allocations.append({
                    'index': index,
                    'op': op,
                    'units': 1,
                    'cost_lower_bound': float(cost),
                    'cash_after_lower_bound': cash,
                })
                continue

            item = order[1]
            quantity = _qty(order)
            animal = mechanics.ANIMALS[item]
            unit_cost = animal['cost']
            if (isinstance(unit_cost, bool)
                    or not isinstance(unit_cost, (int, float))
                    or not math.isfinite(float(unit_cost))
                    or unit_cost < 0):
                return None
            full_cost = float(unit_cost) * quantity
            room = capacity - occupancy
            if room < quantity or cash < full_cost:
                return {
                    'rows': set(),
                    'allocations': [],
                    'funding_proceeds_lower_bound': funding_proceeds,
                    'funding_proceeds': funding_detail,
                    'operating_cost_upper_bound': operating_cost,
                    'operating_costs': operating_detail,
                    'cash_after_operating_lower_bound':
                        float(money) + funding_proceeds - operating_cost,
                    'reason': 'unproved_capital_sequence',
                }
            cash -= full_cost
            occupancy += quantity
            rows.add(index)
            allocations.append({
                'index': index,
                'op': op,
                'item': item,
                'units': quantity,
                'cost_lower_bound': full_cost,
                'cash_after_lower_bound': cash,
                'shed_occupancy_after_lower_bound': occupancy,
            })

        return {
            'rows': rows,
            'allocations': allocations,
            'funding_proceeds_lower_bound': funding_proceeds,
            'funding_proceeds': funding_detail,
            'operating_cost_upper_bound': operating_cost,
            'operating_costs': operating_detail,
            'cash_after_operating_lower_bound':
                float(money) + funding_proceeds - operating_cost,
            'reason': 'certified',
        }
    except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError):
        return None


def _capital_admitted(
        order, index, mechanics, remaining, day, land_targets, capital_rows):
    if capital_rows is None or index not in capital_rows:
        return False
    return _capital_window_admitted(
        order, index, mechanics, remaining, day, land_targets)


def _rank(order, index, funding, mechanics, remaining, day, plant_demand,
          seeds_held, land_targets, capital_rows):
    if not order:
        return REST
    op = order[0]
    if op == 'SELL':
        return FUNDING if index in funding else REST
    if _operating_admitted(order, mechanics, plant_demand, seeds_held):
        return OPERATING
    if _capital_admitted(
            order, index, mechanics, remaining, day, land_targets, capital_rows):
        return CAPITAL
    return REST


def order_early_capital(mechanics, observation, configuration, selected, route, decisions=()):
    """Reorder only the executable prefix of the current market tape.

    Purchases are never dropped or invented. Farmer/hands, market length, the
    multiset of active orders, and every capped suffix row remain unchanged.
    """
    report = {'changed': False, 'reason': 'init', 'moved': 0, 'reserved': 0,
              'reduced': [], 'revision': 'v6-commit-real-capital'}
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
        now = int(observation.get('step') if observation.get('step') is not None
                  else int(observation['day']) * _turns_per_day(configuration)
                  + int(observation['hour']))
        last = _last_step(configuration)
        turns_per_day = _turns_per_day(configuration)
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        report['reason'] = 'unsupported_time'
        return selected, report
    if turns_per_day <= 0:
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
    land_targets = _certified_land_targets(active, observation, mechanics)
    report['certified_land_rows'] = (
        None if land_targets is None else sorted(land_targets)
    )
    try:
        horizon = _horizon_end(now, configuration, decisions)
        # The current unit stage already ran in post_private; only future route
        # PLANT actions may still consume the post-unit seed balance.
        plants = _plant_demand(None, route, now, horizon)
        operating_rows = {
            index
            for index, order in enumerate(active)
            if _operating_admitted(order, mechanics, plants, seeds_held)
        }
        certificate = _certified_capital_rows(
            active, mechanics, observation, configuration, post_private,
            funding, funding_units, operating_rows, land_targets, remaining, day)
        if certificate is None:
            report['reason'] = 'capital_certificate_failed'
            return selected, report
        capital_rows = certificate['rows']
        report.update(
            certified_operating_rows=sorted(operating_rows),
            certified_capital_rows=sorted(capital_rows),
            capital_allocations=certificate['allocations'],
            guaranteed_funding_proceeds=
                certificate['funding_proceeds_lower_bound'],
            guaranteed_funding_detail=certificate['funding_proceeds'],
            operating_cost_upper_bound=
                certificate['operating_cost_upper_bound'],
            operating_cost_detail=certificate['operating_costs'],
            cash_after_operating_lower_bound=
                certificate['cash_after_operating_lower_bound'],
            capital_certificate_reason=certificate['reason'],
        )
        ranks = [
            _rank(order, index, funding, mechanics, remaining, day, plants,
                  seeds_held, land_targets, capital_rows)
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
    result = deepcopy(selected)
    result['market'] = deepcopy(reordered)
    report.update(changed=True, reason='ordered', moved=moved, reserved=0,
                  reduced=[], horizon_end=horizon, remaining_days=remaining)
    return result, report
