# SPDX-License-Identifier: Apache-2.0
"""Reserve useful operating inputs already owned by the active producer.

This is a bounded market proposal, not another production controller. It keeps
the emitted unit stream and every market slot. All obligations are rebuilt from
the current observation; no requested purchase is treated as a receipt.
"""
from collections import Counter
from copy import deepcopy
import math

MOVES = {'NORTH': (0, -1), 'SOUTH': (0, 1), 'EAST': (1, 0), 'WEST': (-1, 0)}
SHED_ACCESS = {(4, 4), (5, 4), (4, 5), (5, 5)}


def _whole(value):
    if type(value) is not int or value < 0:
        raise ValueError('expected a nonnegative integer')
    return value


def _order_quantity(order):
    """Mirror the pinned engine's quantity parse while keeping proof failures named."""
    if not isinstance(order, list) or len(order) < 3:
        raise ValueError('expected an engine quantity order')
    try:
        quantity = int(order[2])
    except (TypeError, ValueError, OverflowError):
        raise ValueError('expected an engine quantity order')
    # The engine ignores nonpositive quantity rows. Modeling them as zero keeps
    # the same physical/cash effect without making an invalid row finance proof.
    return max(0, quantity)


def _market_prefix(row, maximum):
    """Return only list-shaped executable market rows or fail closed.

    The pinned engine ignores malformed rows after its raw prefix cap. These
    optional proof transforms therefore validate only that effective prefix and
    never let a truthy non-list row escape as a Python indexing exception.
    """
    if not isinstance(row, dict):
        raise ValueError('malformed_market_row')
    market = row.get('market')
    if market is None:
        market = []
    if not isinstance(market, list):
        raise ValueError('malformed_market_row')
    prefix = market[:maximum]
    if any(order and not isinstance(order, list) for order in prefix):
        raise ValueError('malformed_market_row')
    return prefix


def _feed_window(mechanics, observation, configuration, selected, farm, private,
                 route, checkpoints):
    """A position/input requirement, without executing future game states.

    Start from completed own units. Only a day-close observation may cross its
    reset. Future hires are prepaid from actual cash; sales earn no cash here.
    Future harvests, deposits and requested purchases never supply wheat.
    """
    now = _whole(observation['step']); day = now // 24
    reset = now % 24 == 23
    end = min((day + 1 + int(reset)) * 24 - 1, 695, len(route) - 1)
    if end <= now or any(now < int(t) <= end for t in checkpoints):
        raise ValueError('unresolved_feed_window')
    positions = [tuple(farm['farmer']), *map(tuple, farm['hands'])]
    initial = [_whole(v.get('WHEAT', 0)) for v in private['inventories']]
    if len(initial) != len(positions):
        raise ValueError('missing_worker_inventory')
    animals = { (x, y): dict(tile) for y, row in enumerate(farm['tiles'])
               for x, tile in enumerate(row)
               if isinstance(tile, dict) and tile.get('animal') in mechanics.ANIMALS }
    cash = float(farm['money']); spent = 0
    if not math.isfinite(cash) or cash < 0:raise ValueError('invalid_observed_cash')
    hires = _whole(farm.get('hires_today', len(farm['hands'])))
    land = len(farm.get('unlocked_quadrants', ['NW'])) - 1
    mult = _whole(configuration.get('farmHandCostMult', 1))
    pickups = []; feeds = []; transfers = set(); prior_requests = 0
    arrivals = []; unit_deposits = []; uncovered = []; wheat_sales = []
    requests_by_actor = Counter(); feed_count = Counter(); before_pickup = Counter()
    fertilizer_requests = 0
    for step in range(now, end + 1):
        row = selected if step == now else route[step]
        if step > now:
            for actor, pos in enumerate(positions):
                action = _action(row, actor)
                if not isinstance(action, list) or not action:
                    raise ValueError('malformed_future_unit')
                op = action[0]
                tile = animals.get(pos)
                if (op == 'PLACE' and len(action) > 1 and action[1] in mechanics.ANIMALS
                        and tile is None):
                    raise ValueError('uncertified_future_animal_placement')
                if op in ('DIG', 'PLANT', 'BUILD_PASTURE', 'BUILD_COOP') and tile:
                    raise ValueError('feed_target_has_other_asset_intent')
                if op == 'DROP' or action[:2] == ['PLACE', 'WHEAT']:
                    transfers.add(actor)
                # A failed animal placement at shed access can also fall
                # through to the engine's deposit path.
                if op in ('DROP', 'PLACE'):
                    unit_deposits.append(step)
                if action[:2] == ['PICKUP', 'WHEAT'] and pos in SHED_ACCESS:
                    q = _whole(action[2] if len(action) > 2 else 1)
                    pickups.append({'step': step, 'actor': actor, 'quantity': q,
                                    'prior_requests': prior_requests})
                    requests_by_actor[actor] += q; prior_requests += q
                if op == 'FEED' and tile and not tile.get('fed_today'):
                    if actor in transfers:
                        raise ValueError('feed_after_uncertified_input_transfer')
                    if initial[actor] + requests_by_actor[actor] <= feed_count[actor]:
                        uncovered.append({'step': step, 'actor': actor, 'position': pos})
                        continue
                    tile['fed_today'] = True
                    feed_count[actor] += 1
                    if not requests_by_actor[actor]:before_pickup[actor] += 1
                    feeds.append({'step': step, 'actor': actor, 'position': pos,
                                  'animal': tile['animal']})
                if op in MOVES:
                    dx, dy = MOVES[op]; q = (pos[0] + dx, pos[1] + dy)
                    if 0 <= q[0] < 10 and 0 <= q[1] < 10:positions[actor] = q
        for slot, order in enumerate(_market_prefix(row, 10)):
            if not order:continue
            op = order[0]; cost = 0
            if op == 'SELL':
                q = _order_quantity(order)
                if order[1] not in mechanics.PRODUCTS:raise ValueError('invalid_sale_product')
                if step > now and order[1] == 'WHEAT' and q:wheat_sales.append(step)
                continue
            if op == 'HIRE':
                cost = mechanics._hire_cost(hires, mult)
            elif op == 'BUY_LAND':
                if land < len(mechanics.LAND_PRICES):cost = mechanics.LAND_PRICES[land]
            elif op in ('BUY_SEED', 'BUY_ANIMAL'):
                table = mechanics.CROPS if op == 'BUY_SEED' else mechanics.ANIMALS
                cost = _order_quantity(order) * table[order[1]]['seed' if op == 'BUY_SEED' else 'cost']
                if op == 'BUY_ANIMAL' and step > now:arrivals.append((step, _order_quantity(order)))
            elif op == 'BUY_PRODUCT':
                q = _order_quantity(order)
                if q and order[1] != 'FERTILIZER':
                    raise ValueError('unresolved_wheat_replenishment')
                if q:
                    if step > now:arrivals.append((step, q))
                    market = observation['market']; params = market.get('params') or mechanics.MARKET_PARAMS
                    if params['FERTILIZER'] != mechanics.MARKET_PARAMS['FERTILIZER']:
                        raise ValueError('unsupported_fertilizer_cost_curve')
                    fertilizer_requests += min(q, 100)
                    # FERTILIZER has no town absorption. At most100 rival units
                    # can be bought per slot, even if earlier purchases failed.
                    lower = (market['inventory']['FERTILIZER'] - fertilizer_requests
                             - ((step - now) * 10 + slot + 1) * 100)
                    cost = min(q, 100) * mechanics.market_price('FERTILIZER', lower, params)
            else:raise ValueError('unsupported_market_operation')
            if cash < cost:raise ValueError('feed_window_not_prepaid')
            cash -= cost; spent += cost
            if op == 'HIRE':
                shape = {'farmer': positions[0], 'hands': positions[1:]}
                positions.append(tuple(mechanics._spawn_hand(shape, 10)))
                initial.append(0); hires += 1
            elif op == 'BUY_LAND' and land < len(mechanics.LAND_PRICES):land += 1
        if step == now and reset:
            animals = {pos: dict(tile, fed_today=False) for pos, tile in animals.items()
                       if tile.get('fed_today') or int(tile.get('consecutive_unfed', 0)) < 1}
            positions = [tuple(mechanics._default_spawn(10))]; initial = [0]; hires = 0
    if uncovered:raise ValueError('scheduled_feed_has_uncovered_carried_input')
    obligations = []; required = 0
    for actor, count in feed_count.items():
        deficit = max(0, count - initial[actor])
        if not deficit:continue
        choices = [p for p in pickups if p['actor'] == actor and p['quantity'] > 0]
        if len(choices) != 1 or actor in transfers:
            raise ValueError('ambiguous_protected_worker_transfers')
        pickup = choices[0]
        if before_pickup[actor] > initial[actor] or deficit > pickup['quantity']:
            raise ValueError('pickup_does_not_cover_feed_suffix')
        required = max(required, pickup['prior_requests'] + deficit)
        obligations.append(dict(pickup, required_acquisition=deficit,
                                feeds=[f for f in feeds if f['actor'] == actor]))
    last_pickup = max((p['step'] for p in obligations), default=now)
    if any(t <= last_pickup for t in unit_deposits):
        raise ValueError('uncertified_deposit_before_protected_pickup')
    if any(t < last_pickup for t in wheat_sales):
        raise ValueError('intervening_wheat_sale_before_protected_pickup')
    if obligations:
        last = max(obligations, key=lambda p: (p['step'], p['actor']))
        needs = {p['actor']: p['required_acquisition'] for p in obligations}
        # A changed sale leaves exactly required_wheat. Every earlier pickup
        # must use its full request in reachable feeds; the last pickup receives
        # only its useful remainder. Thus none of the retained stock can return
        # through a later DROP or the automatic EOD deposit as unused surplus.
        for pickup in pickups:
            if ((pickup['step'], pickup['actor']) >= (last['step'], last['actor'])
                    or not pickup['quantity']):continue
            if (pickup['quantity'] != needs.get(pickup['actor'], 0)
                    or pickup['actor'] in transfers):
                raise ValueError('competing_pickup_has_uncertified_wheat_return')
    return {'through_step': end, 'crosses_reset': reset, 'required_wheat': required,
            'obligations': obligations, 'cash_spending_upper': spent,
            'cash_lower_after_requests': cash, 'future_sale_cash_credit': 0,
            'future_wheat_receipt_credit': 0,
            'arrival_upper_before_last_pickup': sum(q for t, q in arrivals if t < last_pickup)}


def _current_room_bound(mechanics, private, orders, reset, capacity=100,
                        maximum=10):
    """Credit each initial physical unit once; buys never enlarge sale credit."""
    capacity = _whole(capacity)
    maximum = _whole(maximum)
    stock = {k: _whole(n) for k, n in private['shed'].items()}
    upper = sum(stock.values()); peak = upper
    for order in orders[:maximum]:
        if not order:continue
        op = order[0]
        if op == 'SELL':
            if order[1] not in mechanics.PRODUCTS:raise ValueError('invalid_sale_product')
            q = min(_order_quantity(order), stock.get(order[1], 0))
            stock[order[1]] = stock.get(order[1], 0) - q; upper -= q
        elif op in ('BUY_PRODUCT', 'BUY_ANIMAL'):upper += _order_quantity(order)
        peak = max(peak, upper)
        if upper > capacity:raise ValueError('withholding_conflicts_with_current_arrival_room')
    carry = sum(_whole(n) for v in private['inventories'] for n in v.values()) if reset else 0
    if upper + carry > capacity:raise ValueError('withholding_conflicts_with_reset_delivery')
    return {'market_stock_upper': upper, 'market_peak_upper': peak,
            'eod_carry_upper': carry, 'after_delivery_upper': upper + carry}


def protect_feed_stock(mechanics, observation, configuration, selected,
                       post_farm, post_private, route, checkpoints=()):
    """Preserve up to two owned wheat units for the producer's reachable feeds.

    This repairs an input/sale contradiction in the existing service plan. It
    does not decide which new animals to acquire or estimate a game cash gain.
    The caller must use this at the final returned-action boundary, including
    any selected-action fallback with a completed matching unit snapshot.
    """
    report = {'changed': False, 'reason': 'no_wheat_sale', 'certified': False,
              'future_cash_gain_measured': False}
    try:
        orders = _market_prefix(selected, 10)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as error:
        report['reason'] = str(error)
        return selected, report
    if not any(o and o[:2] == ['SELL', 'WHEAT'] for o in orders):return selected, report
    try:
        cfg = configuration or {}; now = _whole(observation['step'])
        if (len(post_farm['tiles']) != 10 or int(cfg.get('turnsPerDay', 24)) != 24
                or int(cfg.get('episodeSteps', 720)) != 720
                or int(cfg.get('shedCapacity', 100)) != 100
                or int(cfg.get('maxMarketOrdersPerTurn', 10)) != 10 or now >= 695):
            raise ValueError('outside_supported_feed_window')
        window = _feed_window(mechanics, observation, cfg, selected, post_farm,
                              post_private, route, checkpoints)
        report['window'] = window
        required = window['required_wheat']; reset = window['crosses_reset']
        stock = _whole(post_private['shed'].get('WHEAT', 0))
        returned_wheat = sum(_whole(v.get('WHEAT', 0)) for v in post_private['inventories']) if reset else 0
        if required > stock + returned_wheat:raise ValueError('observed_wheat_cannot_cover_feed_prefix')
        offered = sum(_order_quantity(o) for o in orders if o and o[:2] == ['SELL', 'WHEAT'])
        permitted = min(stock, max(0, stock + returned_wheat - required))
        withheld = max(0, min(stock, offered) - permitted)
        if withheld > 2:raise ValueError('feed_reservation_exceeds_two_units')
        result = deepcopy(selected) if withheld else selected
        if withheld:
            remaining = permitted
            for slot, order in enumerate(result['market'][:10]):
                if order and order[:2] == ['SELL', 'WHEAT']:
                    take = min(_order_quantity(order), remaining); remaining -= take
                    if take:
                        order[2] = take
                    else:
                        result['market'][slot] = []
        room = _current_room_bound(mechanics, post_private, result.get('market', []), reset)
        # No credit for future sales or requested pickups when reserving room.
        # This intentionally declines busy arrival windows instead of trading
        # another producer's delivered goods for the protected wheat.
        if room['after_delivery_upper'] + window['arrival_upper_before_last_pickup'] > 100:
            raise ValueError('withholding_conflicts_with_future_arrival_room')
        report.update(changed=bool(withheld), certified=True,
                      reason='reserve_reachable_feed' if withheld else 'feed_prefix_already_covered',
                      withheld_units=withheld, required_wheat=required,
                      observed_shed_wheat=stock, eod_wheat_credit=returned_wheat,
                      room=room)
        return result, report
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as error:
        report['reason'] = str(error)
        return selected, report


def _units(row):
    return [row.get('farmer') or ['PASS'], *(row.get('hands') or [])]


def _action(row, actor):
    units = _units(row)
    return units[actor] if actor < len(units) and units[actor] else ['PASS']


def _next_bonus_day(tile, day, crops, last_refresh):
    if not isinstance(tile, dict) or tile.get('kind') != 'PLANT':
        return None
    crop = crops.get(tile.get('crop'))
    # Annual crops need a separate water/harvest certificate. This first consumer
    # covers an existing ongoing crop's production within fertilizer's lifetime.
    if not crop or not crop['ongoing']:
        return None
    first = int(tile['planted_day']) + int(crop['first_yield_day']) - 1
    interval = int(crop['interval'])
    cycle = max(0, (day - first + interval - 1) // interval)
    due = first + cycle * interval
    if (due > min(day + 2, last_refresh) or cycle >= int(crop['max_yield'])
            or int(tile.get('yield_units', 0)) > int(crop['max_yield']) - 2
            or int(tile.get('fertilized_until_day', -1)) >= due):
        return None
    expiry = int(tile.get('max_lifespan_step', -1))
    if expiry >= 0 and expiry <= (due + 1) * 24:
        return None
    return due


def _bonus_water_service(mechanics, observation, configuration, selected,
                         post_farm, route, obligations, checkpoints):
    """Check free movement/watering and paid worker availability through refresh.

    This is a position and cash lower-bound calculation, not game execution.
    Sales give no cash credit. A variable-price purchase reduces the cash lower
    bound to zero; it can never finance a later hire. Already hired workers can
    still move and water for free. Resets discard workers and recompute spawns.
    """
    now = int(observation['step']); cfg = configuration or {}
    maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
    finish = (max(o['bonus_day'] for o in obligations) + 1) * 24 - 1
    if finish >= len(route) or any(now < int(t) <= finish for t in checkpoints):
        return None, 'bonus_day_crosses_unresolved_route_boundary'
    positions = [tuple(post_farm['farmer']), *map(tuple, post_farm['hands'])]
    sites = {tuple(o['position']): o for o in obligations}
    watered = {p: bool(post_farm['tiles'][p[1]][p[0]].get('watered_today')) for p in sites}
    dry = {p: int(post_farm['tiles'][p[1]][p[0]].get('consecutive_unwatered', 0)) for p in sites}
    own_services = {(o['step'], tuple(o['position'])) for o in obligations}
    cash = max(0.0, float(post_farm['money']))
    hires = int(post_farm.get('hires_today', len(post_farm['hands'])))
    hire_cost = 0; fixed_spending = 0; water_receipts = []
    for step in range(now, finish + 1):
        row = selected if step == now else route[step]
        if step > now:
            for actor, pos in enumerate(positions):
                action = _action(row, actor); op = action[0]
                if pos in sites and step // 24 <= sites[pos]['bonus_day']:
                    if op in ('DIG', 'PLANT'):
                        return None, 'bonus_target_changes_before_refresh'
                    if op == 'FERTILIZE' and (step, pos) not in own_services:
                        return None, 'bonus_target_has_later_fertilizer'
                    if op == 'WATER':
                        watered[pos] = True
                        water_receipts.append({'step': step, 'actor': actor, 'position': pos})
                if op in MOVES:
                    dx, dy = MOVES[op]; q = (pos[0] + dx, pos[1] + dy)
                    if 0 <= q[0] < 10 and 0 <= q[1] < 10:
                        positions[actor] = q
        for order in _market_prefix(row, maximum):
            if not order:
                continue
            op = order[0]
            if op == 'HIRE':
                cost = mechanics._hire_cost(hires, float(cfg.get('farmHandCostMult', 1)))
                if cash < cost:
                    return None, 'bonus_day_hire_not_funded'
                cash -= cost; hires += 1; hire_cost += cost
                shape = {'farmer': positions[0], 'hands': positions[1:]}
                positions.append(tuple(mechanics._spawn_hand(shape, 10)))
            elif op == 'BUY_PRODUCT':
                cash = 0.0
            elif op == 'BUY_LAND':
                return None, 'bonus_day_has_capital_expansion'
            elif op in ('BUY_SEED', 'BUY_ANIMAL') and len(order) > 2:
                table = mechanics.CROPS if op == 'BUY_SEED' else mechanics.ANIMALS
                price = table[order[1]]['seed' if op == 'BUY_SEED' else 'cost']
                cost = max(0, int(order[2])) * price
                cash = max(0.0, cash - cost); fixed_spending += cost
        if step % 24 == 23:
            day = step // 24
            for pos, obligation in sites.items():
                if day > obligation['bonus_day']:
                    continue
                dry[pos] = 0 if watered[pos] else dry[pos] + 1
                if dry[pos] >= 2:
                    return None, 'bonus_target_dies_before_refresh'
                if day == obligation['bonus_day'] and not watered[pos]:
                    return None, 'missing_bonus_day_water'
                watered[pos] = False
            positions = [tuple(mechanics._default_spawn(10))]; hires = 0
    return {'through_step': finish, 'water_actions': water_receipts,
            'funded_hire_cost': hire_cost, 'fixed_spending_without_sale_credit': fixed_spending,
            'variable_purchase_cash_credit': 0}, None


def _operating_stock_commitments(mechanics, configuration, post_farm, rows):
    """Price fixed market commitments from observed cash with zero sale credit."""
    cfg = configuration or {}
    cash = float(post_farm['money'])
    if not math.isfinite(cash) or cash < 0:
        raise ValueError('invalid_observed_cash')
    hires = max(0, int(post_farm.get('hires_today', len(post_farm.get('hands', [])))))
    land = max(0, len(post_farm.get('unlocked_quadrants', ['NW'])) - 1)
    max_orders = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
    mult = float(cfg.get('farmHandCostMult', 1))
    required = 0.0; commitments = []
    for step, row in rows:
        for slot, order in enumerate(_market_prefix(row, max_orders)):
            if not order:
                continue
            op = order[0]; cost = 0.0
            if op == 'SELL':
                continue
            if op == 'HIRE':
                cost = float(mechanics._hire_cost(hires, mult)); hires += 1
            elif op == 'BUY_LAND':
                if land < len(mechanics.LAND_PRICES):
                    cost = float(mechanics.LAND_PRICES[land]); land += 1
            elif op in ('BUY_SEED', 'BUY_ANIMAL'):
                q = _order_quantity(order)
                table = mechanics.CROPS if op == 'BUY_SEED' else mechanics.ANIMALS
                cost = float(q * table[order[1]]['seed' if op == 'BUY_SEED' else 'cost'])
            elif op == 'BUY_PRODUCT':
                q = _order_quantity(order)
                if q:
                    raise ValueError('intervening_variable_price_purchase')
                continue
            else:
                continue
            required += cost
            commitments.append({'step': step, 'slot': slot, 'op': op, 'cost': cost})
    return {'required_cash': required, 'observed_cash': cash,
            'cash_after_commitments': cash - required,
            'shortfall': max(0.0, required - cash),
            'future_sale_cash_credit': 0, 'commitments': commitments}


def protect_operating_stock(mechanics, observation, configuration, selected,
                            post_farm, post_private, route, checkpoints=()):
    """Return a same-slot fertilizer-sale proposal and its explicit limits.

    The supported case contains one actual worker, one upcoming shed pickup, existing
    productive targets, no intervening hiring/branch/reset or input replenishment,
    and room for known deposits without crediting future sales. Economic admission
    uses exact observed marginal curves and fixed committed costs; it does not add
    fabricated future sale cash or a constant input-value cash cushion.
    """
    report = {'changed': False, 'reason': 'no_fertilizer_sale'}
    cfg = configuration or {}
    try:
        maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
        orders = _market_prefix(selected, maximum)
        offered = sum(_order_quantity(o) for o in orders
                      if o and len(o) > 2 and o[:2] == ['SELL', 'FERTILIZER'])
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as error:
        report['reason'] = str(error)
        return selected, report
    if not offered:
        return selected, report
    now = int(observation['step']); day = now // 24
    board = len(post_farm['tiles'])
    if (board != 10 or int(cfg.get('turnsPerDay', 24)) != 24
            or int(cfg.get('episodeSteps', 720)) != 720 or day >= 29):
        report['reason'] = 'outside_supported_production_window'
        return selected, report
    day_end = min((day + 1) * 24, len(route))
    if any(now < int(t) < day_end for t in checkpoints):
        report['reason'] = 'unresolved_same_day_branch'
        return selected, report
    end = min((day + 1) * 24 - 1, 719,
              *[int(t) for t in checkpoints if now < int(t)])
    positions = [tuple(post_farm['farmer']), *map(tuple, post_farm['hands'])]
    if any(o and o[0] == 'HIRE' for o in orders):
        report['reason'] = 'current_hiring_boundary'
        return selected, report
    scan_stop = min(end + 1, len(route))
    try:
        for step in range(now + 1, scan_stop):
            if any(o and o[0] == 'HIRE' for o in _market_prefix(route[step], maximum)):
                end = step
                scan_stop = step
                break
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as error:
        report['reason'] = str(error)
        return selected, report
    schedule = []
    pickups = []
    # Future fixed deposits only. Current BUY arrivals are traced in their real
    # queue order by _current_room_bound after the fertilizer sale is rewritten.
    deposits = 0
    try:
        for step in range(now + 1, scan_stop):
            row = route[step]
            for order in _market_prefix(row, maximum):
                if order and order[0] in ('BUY_PRODUCT', 'BUY_ANIMAL'):
                    if len(order) > 2:
                        deposits += max(0, int(order[2]))
                    if len(order) > 1 and order[1] == 'FERTILIZER':
                        report['reason'] = 'intervening_requested_replenishment'
                        return selected, report
            for actor, pos in enumerate(positions):
                action = _action(row, actor)
                schedule.append((step, actor, pos, action))
                if action[0] == 'DROP':
                    report['reason'] = 'unbounded_intervening_drop'
                    return selected, report
                if action[0] == 'PLACE' and len(action) > 1 and mechanics.ANIMALS.get(action[1]) is None:
                    deposits += max(0, int(action[2]) if len(action) > 2 else 1)
                if action[:2] == ['PICKUP', 'FERTILIZER']:
                    pickups.append((step, actor, pos, max(0, int(action[2]) if len(action) > 2 else 1)))
                if action[0] in MOVES:
                    dx, dy = MOVES[action[0]]
                    new = (pos[0] + dx, pos[1] + dy)
                    if 0 <= new[0] < board and 0 <= new[1] < board:
                        positions[actor] = new
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as error:
        report['reason'] = str(error)
        return selected, report
    if len(pickups) != 1:
        report['reason'] = 'requires_one_unambiguous_pickup'
        return selected, report
    pickup_step, actor, pickup_pos, quantity = pickups[0]
    if pickup_pos not in SHED_ACCESS or quantity <= 0:
        report['reason'] = 'pickup_not_reachable_from_shed'
        return selected, report
    carried = max(0, int(post_private['inventories'][actor].get('FERTILIZER', 0)))
    obligations = []
    for step, worker, pos, action in schedule:
        if worker != actor:
            continue
        if action[0] == 'COLLECT_FERTILIZER' or action[:2] == ['PLACE', 'FERTILIZER']:
            report['reason'] = 'actor_has_other_input_transfer'
            return selected, report
        if action[0] != 'FERTILIZE':
            continue
        tile = post_farm['tiles'][pos[1]][pos[0]]
        valid = isinstance(tile, dict) and tile.get('kind') == 'PLANT'
        if step < pickup_step:
            if valid:
                carried = max(0, carried - 1)
            continue
        due = _next_bonus_day(tile, day, mechanics.CROPS, 28)
        if due is None:
            report['reason'] = 'pickup_suffix_contains_nonproductive_consumption'
            return selected, report
        obligations.append({'step': step, 'position': pos, 'crop': tile['crop'], 'bonus_day': due})
    sites = {tuple(o['position']) for o in obligations}
    if not obligations or len(sites) != len(obligations):
        report['reason'] = 'no_distinct_useful_consumption'
        return selected, report
    for step, worker, pos, action in schedule:
        if pos not in sites:
            continue
        if action[0] in ('DIG', 'PLANT') or (action[0] == 'FERTILIZE' and worker != actor):
            report['reason'] = 'target_has_competing_asset_or_input_action'
            return selected, report
    for pos in sites:
        tile = post_farm['tiles'][pos[1]][pos[0]]
        watered = tile.get('watered_today') or any(
            place == pos and action[0] == 'WATER' for _, _, place, action in schedule)
        if int(tile.get('consecutive_unwatered', 0)) >= 1 and not watered:
            report['reason'] = 'target_lacks_water_before_reset'
            return selected, report
    if any(step < pickup_step and action[:2] == ['PLACE', 'FERTILIZER']
           for step, _, _, action in schedule):
        report['reason'] = 'intervening_requested_input_deposit'
        return selected, report
    required = max(0, len(obligations) - carried)
    stock = max(0, int(post_private['shed'].get('FERTILIZER', 0)))
    if not required or required > min(quantity, stock):
        report['reason'] = 'existing_input_covers_use_or_deficit_exceeds_stock'
        return selected, report
    limit = max(0, stock - required)
    withheld = max(0, min(stock, offered) - limit)
    if not withheld:
        report['reason'] = 'sale_already_leaves_required_stock'
        return selected, report
    reservation_bound = min(len(obligations), maximum)
    if withheld > reservation_bound:
        report['reason'] = 'reservation_exceeds_obligation_bound'
        return selected, report
    # Trace the candidate current queue after withholding so an earlier owned
    # SELL can create room for a later current BUY. Future BUY/PLACE deposits
    # remain fixed arrivals and future SELLs receive zero capacity credit.
    candidate_orders = deepcopy(orders)
    remaining = limit
    for index, order in enumerate(candidate_orders[:maximum]):
        if order and len(order) > 2 and order[:2] == ['SELL', 'FERTILIZER']:
            take = min(_order_quantity(order), remaining)
            candidate_orders[index] = ['SELL', 'FERTILIZER', take] if take else []
            remaining -= take
    capacity = int(cfg.get('shedCapacity', 100))
    try:
        room = _current_room_bound(
            mechanics, post_private, candidate_orders, False, capacity, maximum)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as error:
        if str(error) in ('withholding_conflicts_with_current_arrival_room',
                          'withholding_conflicts_with_reset_delivery'):
            report['reason'] = 'retained_stock_conflicts_with_arrival_room'
        else:
            report['reason'] = str(error)
        return selected, report
    if room['market_stock_upper'] + deposits > capacity:
        report['reason'] = 'retained_stock_conflicts_with_arrival_room'
        return selected, report
    market = observation['market']; params = market.get('params')
    input_value = sum(mechanics.market_price('FERTILIZER', market['inventory']['FERTILIZER'] + j, params)
                      for j in range(withheld))
    own_yield = Counter()
    for row in post_farm['tiles']:
        for tile in row:
            if isinstance(tile, dict) and tile.get('kind') == 'PLANT':
                own_yield[tile['crop']] += max(0, int(tile.get('yield_units', 0)))
    # Existing carried and unsold stock already funds the earlier services.
    # Only the final otherwise-unfunded uses are incremental to this sale edit.
    extra = Counter(o['crop'] for o in obligations[-withheld:])
    observed_product_value = sum(
        mechanics.market_price(crop, market['inventory'][crop] + own_yield[crop] + j, params)
        for crop, amount in extra.items() for j in range(amount))
    # Keep a named one-full-slot stress diagnostic, but do not manufacture that
    # unobserved rival lot into the admission rule. The decision uses public state.
    one_slot_stress_value = sum(
        mechanics.market_price(crop, market['inventory'][crop] + own_yield[crop] + 100 + j, params)
        for crop, amount in extra.items() for j in range(amount))
    value_scenarios = {
        'observed_public': {'rival_extra_units': 0, 'marginal_product_value': observed_product_value},
        'one_full_slot_stress_diagnostic': {
            'rival_extra_units': 100, 'marginal_product_value': one_slot_stress_value,
            'admission_weight': 0,
        },
    }
    if observed_product_value <= input_value:
        report['reason'] = 'marginal_product_screen_not_favorable'
        report['value_scenarios'] = value_scenarios
        report['input_opportunity_cost'] = input_value
        return selected, report
    try:
        liquidity = _operating_stock_commitments(
            mechanics, cfg, post_farm,
            [(now, selected), *[(step, route[step]) for step in range(now + 1, day_end)]])
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as error:
        report['reason'] = str(error)
        return selected, report
    if liquidity['shortfall'] > 0:
        report['reason'] = 'committed_liquidity_shortfall'
        report['commitment_liquidity'] = liquidity
        return selected, report
    try:
        water_service, reason = _bonus_water_service(
            mechanics, observation, cfg, selected, post_farm, route, obligations, checkpoints)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as error:
        report['reason'] = str(error)
        return selected, report
    if reason:
        report['reason'] = reason
        return selected, report
    out = deepcopy(selected)
    remaining = limit
    for index, order in enumerate(out['market'][:maximum]):
        if order and len(order) > 2 and order[:2] == ['SELL', 'FERTILIZER']:
            take = min(_order_quantity(order), remaining)
            out['market'][index] = ['SELL', 'FERTILIZER', take] if take else []
            remaining -= take
    report.update(changed=True, reason='reserve_reachable_fertilizer', actor=actor,
                  pickup_step=pickup_step, end=end, required_stock=required,
                  withheld_units=withheld, reservation_bound=reservation_bound,
                  reservation_basis='distinct_productive_obligations_and_market_slots',
                  obligations=obligations, input_opportunity_cost=input_value,
                  product_value_scenario=observed_product_value,
                  value_scenarios=value_scenarios,
                  commitment_liquidity=liquidity,
                  cash_spending_reserve=liquidity['required_cash'],
                  funding_through_step=day_end - 1, cash_input_cushion_multiple=0,
                  bonus_day_water_service=water_service,
                  future_cash_gain_measured=False)
    return out, report
