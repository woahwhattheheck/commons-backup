# SPDX-License-Identifier: Apache-2.0
"""Source-bound preparation and observed planting for an annual crop release.

The owner supplies an already completed unit snapshot. These helpers do not call
the producer or execute an environment. The later shared-input and delivery
obligations must be installed by that same owner before this can be activated.
"""
from copy import deepcopy
import hashlib
import json

MAIN = '7015cc00acfa4922'
MILK_GLUT = 'a84d06f1d12add7c'
# Complete rows, including all actors and markets, over [372,459). MAIN and the
# compatible later MILK_GLUT branch have this identical source interval.
RECIPE_SHA256 = '51ad4c904b8f4cefb412d5fc1f4f604be6b906a8290dc85d435229873d1af223'
SITE = (3, 9)
WORKER = 10
MOVES = {'NORTH': (0,-1), 'SOUTH': (0,1), 'EAST': (1,0), 'WEST': (-1,0)}
SERVICES = {(373,10): ['PLANT','WHEAT'], (374,10): ['WATER'],
            (407,10): ['WATER'], (429,3): ['WATER'], (443,10): ['WATER'],
            (444,10): ['HARVEST'], (445,10): ['PLANT','WHEAT']}


def units(action):
    return [action.get('farmer') or ['PASS'], *(action.get('hands') or [])]


def _public_identity(observation):
    """Return the canonical public seat/clock pair, rejecting coercible aliases."""
    if not isinstance(observation, dict):
        return None
    player = observation.get('player')
    step = observation.get('step')
    if type(player) is not int or player not in (0, 1):
        return None
    if type(step) is not int or step < 0:
        return None
    return player, step


def recipe_compatible(routes, current):
    if current not in (MAIN, MILK_GLUT):
        return False
    for name in (MAIN, MILK_GLUT):
        route = routes.get(name, ())
        if len(route) < 459:
            return False
        raw = json.dumps(route[372:459], sort_keys=True).encode()
        if hashlib.sha256(raw).hexdigest() != RECIPE_SHA256:
            return False
    # The existing branch checks keep their pristine past. The intent can cross
    # 433 only because both complete source prefixes remain identical there.
    return routes[MAIN][:577] == routes[MILK_GLUT][:577]


def input_price_bounds(mechanics, observation, configuration, route, through=456,
                       current_orders=()):
    """Price a bounded physical-input horizon, including negative inventory.

    Below the observed above-floor quote, a rival's net market removal in one
    turn cannot exceed its 100-unit shed: every sale there restores inventory,
    and market processing has no transfer to carried stock. Floor-price sales
    only destroy stock above that threshold. Charge all own requested buys and
    the possible repair separately. No future sale is credited. Eight shops is
    the pinned engine maximum, including duplicate instances.
    """
    now=observation.get('step')
    if type(now) is not int or now < 0:return None
    cfg=configuration or {};market=observation['market']
    if (market.get('params') not in (None, mechanics.MARKET_PARAMS)
            or cfg.get('shedCapacity',100)!=100 or cfg.get('boardSize',10)!=10
            or cfg.get('maxMarketOrdersPerTurn',10)!=10
            or cfg.get('farmHandCostMult',1)!=1
            or cfg.get('turnsPerDay',24)!=24 or cfg.get('episodeSteps',720)!=720
            or cfg.get('townShopSellInterval',4)!=4
            or cfg.get('townCenterSellInterval',24)!=24):
        return None
    requested={'WHEAT':3,'FERTILIZER':0}
    for row in [{'market':current_orders},*route[now+1:through+1]]:
        for a in row.get('market',[])[:10]:
            if a and a[0]=='BUY_PRODUCT':
                if len(a)!=3 or a[1] not in requested or type(a[2]) is not int or a[2]<0:
                    return None
                requested[a[1]]+=a[2]
    # Include the current market, since preparation happens before it, and a
    # one-unit quote offset because BUY_PRODUCT prices at post-buy inventory.
    turns=through-now+1
    town_wheat=8*sum(t%4==0 for t in range(now,through+1))
    town_wheat+=sum(t%24==0 for t in range(now,through+1))
    bounds={}
    for item,n in requested.items():
        initial=int(market['inventory'][item])
        if mechanics.market_price(item,initial)<=1:return None
        lower=initial-100*turns-n-(town_wheat if item=='WHEAT' else 0)-1
        bounds[item]={'inventory_lower':lower,
                      'price_upper':mechanics.market_price(item,lower),
                      'own_requested_units_upper':n,
                      'rival_net_removal_upper':100*turns}
    return bounds


def funded_services(mechanics, observation, configuration, post, route):
    """Bound paid workers and trace the same site's existing service actions.

    This is source-row accounting, not an environment rollout. No future sale
    or requested stock purchase becomes a receipt. For the pinned default
    curves every physical purchase is charged at the horizon inventory bound.
    The extra seed and a possible three-wheat repair are prepaid in this
    cash lower bound. Every scheduled HIRE must remain funded through 456.
    """
    identity=_public_identity(observation)
    if identity is None:return None, 'unsupported_service_funding_model'
    seat,now=identity
    cfg=configuration or {};market=observation['market']
    if (now != 372 or len(route) <= 456
            or market.get('params') not in (None, mechanics.MARKET_PARAMS)
            or float(cfg.get('farmHandCostMult', 1)) != 1
            or _public_identity(post)!=(seat,now)
            or any(len(f['tiles'])!=10 or any(len(row)!=10 for row in f['tiles'])
                   for f in observation['farms']+post['farms'])):
        return None, 'unsupported_service_funding_model'
    prices=input_price_bounds(mechanics,observation,cfg,route)
    if prices is None:return None, 'unsupported_input_price_bound'
    farm=post['farms'][seat]
    positions=[tuple(farm['farmer']), *map(tuple, farm['hands'])]
    cash=float(farm['money']);hires=int(farm.get('hires_today', len(farm['hands'])))
    initial=cash
    reserve=mechanics.CROPS['CARROT']['seed'] + 3 * prices['WHEAT']['price_upper']
    cash-=reserve
    if cash<0:return None, 'new_input_reserve_not_funded'
    paid_hires=0;spending=0;seen=[]
    for step in range(373,457):
        row=route[step];actions=units(row)
        for (due,worker),expected in SERVICES.items():
            if due != step:continue
            if (worker >= len(positions) or worker >= len(actions)
                    or positions[worker] != SITE or actions[worker] != expected):
                return None, 'scheduled_service_worker_or_position_unavailable'
            seen.append({'step':step, 'worker':worker, 'action':expected})
        for worker,pos in enumerate(positions):
            a=actions[worker] if worker < len(actions) else ['PASS']
            op=a[0] if a else 'PASS'
            if (pos == SITE and step <= 445 and op in ('PLANT','DIG','HARVEST','FERTILIZE')
                    and (step,worker) not in SERVICES):
                return None, 'other_actor_changes_the_owned_site'
            if op in MOVES:
                dx,dy=MOVES[op];q=(pos[0]+dx,pos[1]+dy)
                if 0 <= q[0] < 10 and 0 <= q[1] < 10:positions[worker]=q
        for a in row.get('market',[])[:10]:
            if not a:continue
            op=a[0]
            if op=='HIRE':
                cost=mechanics._hire_cost(hires,1)
                if cash < cost:return None, 'scheduled_hire_not_funded_without_sales'
                cash-=cost;spending+=cost;hires+=1;paid_hires+=1
                positions.append(tuple(mechanics._spawn_hand(
                    {'farmer':positions[0], 'hands':positions[1:]},10)))
            elif op in ('BUY_SEED','BUY_PRODUCT','BUY_ANIMAL'):
                if len(a)!=3 or type(a[2]) is not int or a[2]<0:
                    return None, 'unbounded_source_purchase'
                item,n=a[1],a[2]
                if op=='BUY_SEED' and item in mechanics.CROPS:
                    cost=n*mechanics.CROPS[item]['seed']
                elif op=='BUY_ANIMAL' and item in mechanics.ANIMALS:
                    cost=n*mechanics.ANIMALS[item]['cost']
                elif op=='BUY_PRODUCT' and item in ('WHEAT','FERTILIZER'):
                    cost=n*prices[item]['price_upper']
                else:return None, 'unsupported_source_purchase'
                if cash < cost:return None, 'scheduled_purchase_not_funded_without_sales'
                cash-=cost;spending+=cost
            elif op!='SELL':return None, 'unsupported_source_capital_or_market_action'
        if step%24==23:
            positions=[tuple(mechanics._default_spawn(10))];hires=0
    return {'through_step':456, 'required_services':seen, 'paid_hires':paid_hires,
            'input_price_bounds':prices,
            'scheduled_spending_upper':spending, 'seed_and_wheat_repair_cash_reserve':reserve,
            'starting_actual_cash':initial, 'ending_cash_lower':cash,
            'future_sale_cash_credit':0, 'requested_input_stock_credit':0},None


def prepare_release(mechanics, observation, configuration, selected, post,
                    routes, current, *, extra_seed_obligations=0):
    """Prepare a new seed only after the bound unit stage releases the tile.

    Return a proposed market row and an uncommitted intent. Native receipts,
    actual final return and next-observation seed/site state remain separate.
    """
    report = {'changed': False, 'reason': 'outside_recipe_preparation'}
    identity=_public_identity(observation)
    if identity is None:return selected,None,report
    seat,now=identity
    cfg = configuration or {}
    if (now != 372 or post is None or _public_identity(post)!=(seat,now)
            or cfg.get('turnsPerDay', 24) != 24
            or cfg.get('episodeSteps', 720) != 720
            or cfg.get('shedCapacity', 100) != 100
            or cfg.get('maxMarketOrdersPerTurn', 10) != 10):
        return selected, None, report
    if not recipe_compatible(routes, current):
        report['reason'] = 'incompatible_complete_source_rows'
        return selected, None, report
    farm = observation['farms'][seat]
    positions = [farm['farmer'], *farm['hands']]
    actions = units(selected)
    if (len(positions) <= WORKER or len(actions) <= WORKER
            or tuple(positions[WORKER]) != SITE or actions[WORKER] != ['HARVEST']):
        report['reason'] = 'release_worker_not_observed'
        return selected, None, report
    before = farm['tiles'][SITE[1]][SITE[0]]
    after = post['farms'][seat]['tiles'][SITE[1]][SITE[0]]
    if (not isinstance(before, dict) or before.get('crop') != 'WHEAT'
            or before.get('kind') != 'PLANT' or before.get('yield_units', 0) <= 0
            or now // 24 - before['planted_day'] < mechanics.CROPS['WHEAT']['first_yield_day']
            or after is not None):
        report['reason'] = 'harvest_did_not_release_expected_crop'
        return selected, None, report
    if selected.get('market'):
        report['reason'] = 'preparation_market_not_empty'
        return selected, None, report
    private = post['private']
    shed_carrot,carry_carrot,sites_carrot=_carrots(post)
    if shed_carrot or any(carry_carrot) or sites_carrot:
        report['reason']='another_carrot_source_is_active'
        return selected,None,report
    seed_floor = max(0, int(private['seeds'].get('CARROT', 0)))
    wheat = max(0, int(private['shed'].get('WHEAT', 0)))
    if wheat < 3 or extra_seed_obligations:
        report['reason'] = 'existing_input_obligations_require_resolution'
        return selected, None, report
    market = observation['market']; params = market.get('params')
    owned = max(0, int(private['shed'].get('CARROT', 0)))
    owned += sum(max(0, int(inv.get('CARROT', 0))) for inv in private['inventories'])
    owned += sum(max(0, int(tile.get('yield_units', 0)))
                 for row in post['farms'][seat]['tiles'] for tile in row
                 if isinstance(tile, dict) and tile.get('crop') == 'CARROT')
    seed_cost = mechanics.CROPS['CARROT']['seed']
    wheat_value = sum(mechanics.market_price('WHEAT', market['inventory']['WHEAT'] + k, params)
                      for k in range(3))
    # Current quotes plus already owned product and a named 100-unit rival
    # supply stress. This is not a multi-day bound or a measured cash gain.
    carrot_value = sum(mechanics.market_price('CARROT', market['inventory']['CARROT'] + owned + 100 + k, params)
                       for k in range(3))
    if carrot_value <= wheat_value + seed_cost:
        report['reason'] = 'marginal_product_screen_not_favorable'
        return selected, None, report
    if float(post['farms'][seat]['money']) < 100 * (wheat_value + seed_cost):
        report['reason'] = 'actual_cash_cushion_insufficient'
        return selected, None, report
    funding,reason=funded_services(mechanics,observation,cfg,post,routes[current])
    if funding is None:
        report['reason']=reason
        return selected,None,report
    intent = {'kind': 'annual_crop_release', 'player': seat, 'prepared_step': 372,
              'plant_step': 373, 'site': SITE, 'worker': WORKER, 'route': current,
              'seed_floor': seed_floor, 'seed_order': ['BUY_SEED', 'CARROT', 1],
              'unit_binding': deepcopy(actions), 'status': 'proposed',
              'replacement_wheat_units': 3, 'harvest_step': 444,
              'replant_step': 445, 'deposit_step': 455, 'outlet_step': 457,
              'input_value_scenario': wheat_value + seed_cost,
              'product_value_scenario': carrot_value,
              'rival_supply_stress_units': 100, 'service_funding':funding}
    out = deepcopy(selected); out['market'] = [list(intent['seed_order'])]
    report.update(changed=True, reason='prepared_new_seed_for_observed_release',
                  input_value_scenario=wheat_value + seed_cost,
                  product_value_scenario=carrot_value,
                  cash_cushion_multiple=100, future_cash_gain_measured=False)
    return out, intent, report


def commit_preparation(intent, observation, returned):
    """Bind preparation to the one actual emitted action, not its proposal."""
    identity=_public_identity(observation)
    if (intent is None or intent.get('status') != 'proposed'
            or identity != (intent['player'],intent['prepared_step'])
            or units(returned) != intent['unit_binding']
            or returned.get('market', []) != [intent['seed_order']]):
        return None
    return dict(intent, status='awaiting_seed_and_site_observation')


def observed_plant(intent, observation, selected, current, *, actor_owned=False):
    """Use the acquired seed while leaving the preexisting stock floor intact."""
    identity=_public_identity(observation)
    if (intent is None or intent.get('status') != 'awaiting_seed_and_site_observation'
            or identity != (intent['player'],intent['plant_step'])
            or current != intent['route'] or actor_owned):
        return selected, False
    farm = observation['farms'][intent['player']]
    positions = [farm['farmer'], *farm['hands']]; actions = units(selected)
    worker = intent['worker']; x, y = intent['site']
    if (len(positions) <= worker or len(actions) <= worker
            or tuple(positions[worker]) != (x, y) or farm['tiles'][y][x] is not None
            or actions[worker] != ['PLANT', 'WHEAT']):
        return selected, False
    other = sum(isinstance(a, (list, tuple)) and len(a) >= 2
                and a[0] == 'PLANT' and a[1] == 'CARROT'
                for i, a in enumerate(actions) if i != worker)
    if int(observation['private']['seeds'].get('CARROT', 0)) < intent['seed_floor'] + other + 1:
        return selected, False
    if other:return selected,False  # One exclusive crop source owns this receipt lane.
    shed,carried,sites=_carrots(observation)
    if shed or any(carried) or sites:
        return selected,False
    out = deepcopy(selected); out['hands'][worker - 1] = ['PLANT', 'CARROT']
    return out, True


def _carrots(observation, exclude_site=None):
    """Public/private own carrot sources; seeds are separate operating inputs."""
    identity=_public_identity(observation)
    if identity is None:raise ValueError('invalid_crop_observation_identity')
    seat,_=identity
    farm = observation['farms'][seat]
    private = observation['private']
    tiles = [(x, y) for y, row in enumerate(farm['tiles']) for x, tile in enumerate(row)
             if isinstance(tile, dict) and tile.get('crop') == 'CARROT'
             and (x, y) != exclude_site]
    return (int(private['shed'].get('CARROT', 0)),
            [int(inv.get('CARROT', 0)) for inv in private['inventories']], tiles)


def commit_plant(intent, observation, returned, current):
    """Record only the final emitted change; its success is observed next turn."""
    identity=_public_identity(observation)
    if intent is None or identity is None or identity[0] != intent['player']:
        return None
    seat,now=identity
    actions = units(returned); worker = intent['worker']
    if len(actions) <= worker or actions[worker] != ['PLANT', 'CARROT']:
        return None
    original = deepcopy(returned); original['hands'][worker - 1] = ['PLANT', 'WHEAT']
    if not observed_plant(intent, observation, original, current)[1]:
        return None
    # This receipt lane owns one crop. Other same-turn carrot planting may be
    # legal but cannot certify exclusive provenance for its later sale.
    if any(a and len(a) >= 2 and a[:2] == ['PLANT', 'CARROT']
           for i, a in enumerate(actions) if i != worker):
        return None
    shed, carried, tiles = _carrots(observation)
    if shed or any(carried) or tiles:
        return None
    return dict(intent, status='awaiting_observed_plant',
                last_observed_step=now,
                expected_seed_stock=int(observation['private']['seeds'].get('CARROT', 0)) - 1,
                planted_day=now // 24,
                wheat_reserve_required=3, input_repair_remaining=3,
                input_repair_receipts=[], crop_receipts=[])


def observe_crop(intent, observation, current):
    """Advance a persistent site/carrier receipt, never a forecasted outcome.

    Daily worker resets do not erase an owned planted site. A missing or
    ambiguous receipt retains the input obligation but cannot mint another lot.
    The caller remains responsible for the wheat reservation/recovery policy.
    """
    if intent is None or intent['status'] in ('proposed', 'awaiting_seed_and_site_observation'):
        return intent
    identity=_public_identity(observation)
    if identity is None:return intent
    seat,now=identity
    prior = int(intent.get('last_observed_step', intent['plant_step']))
    if seat != intent['player'] or now < prior:
        return None
    if now == prior:
        return intent
    p = deepcopy(intent); p['last_observed_step'] = now
    if p['status'] in ('sale_attribution_unknown', 'input_recovery_only', 'sold'):
        return p
    if current not in (MAIN, MILK_GLUT) or now != prior + 1:
        p.update(status='input_recovery_only', receipt_failure='unbound_observation_or_route')
        return p
    farm = observation['farms'][seat]; private = observation['private']
    x, y = p['site']; tile = farm['tiles'][y][x]
    status = p['status']
    shed, carried, other_sites = _carrots(observation, (x, y))
    if status in ('carried', 'awaiting_observed_deposit', 'deposited'):
        shed, carried, other_sites = _carrots(observation)
    if status == 'awaiting_observed_plant':
        valid = (now == p['plant_step'] + 1 and isinstance(tile, dict)
                 and tile.get('kind') == 'PLANT' and tile.get('crop') == 'CARROT'
                 and tile.get('planted_day') == p['planted_day']
                 and int(private['seeds'].get('CARROT', 0)) == p['expected_seed_stock']
                 and p['expected_seed_stock'] >= p['seed_floor']
                 and not shed and not any(carried) and not other_sites)
        if valid:
            p['status'] = 'growing'
            p['crop_receipts'].append({'kind': 'plant', 'step': p['plant_step'], 'observed_at': now})
        else:p.update(status='input_recovery_only', receipt_failure='plant_not_observed')
    elif status == 'growing':
        if (not isinstance(tile, dict) or tile.get('kind') != 'PLANT'
                or tile.get('crop') != 'CARROT' or tile.get('planted_day') != p['planted_day']
                or shed or any(carried) or other_sites):
            p.update(status='input_recovery_only', receipt_failure='owned_site_or_exclusive_source_changed')
    elif status == 'awaiting_observed_harvest':
        worker = p['worker']; n = p['harvest_quantity']
        valid = (now == p['harvest_step'] + 1 and tile is None and not shed
                 and not other_sites and worker < len(carried) and carried[worker] == n
                 and not any(q for i, q in enumerate(carried) if i != worker)
                 and tuple([farm['farmer'], *farm['hands']][worker]) == (x, y))
        if valid:
            p['status'] = 'carried'
            p['crop_receipts'].append({'kind': 'harvest', 'step': p['harvest_step'],
                                      'observed_at': now, 'units': n})
        else:p.update(status='input_recovery_only', receipt_failure='harvest_not_observed')
    elif status == 'carried':
        worker = p['worker']
        if (shed or other_sites or worker >= len(carried)
                or carried[worker] != p['harvest_quantity']
                or any(q for i, q in enumerate(carried) if i != worker)):
            p.update(status='input_recovery_only', receipt_failure='carrier_or_exclusive_stock_changed')
    elif status == 'awaiting_observed_deposit':
        valid = (now == p['deposit_step'] + 1 and shed == p['harvest_quantity']
                 and not any(carried) and not other_sites
                 and not farm['hands'] and len(private['inventories']) == 1)
        if valid:
            p.update(status='deposited', sale_quantity_remaining=p['harvest_quantity'],
                     offered_to_seller=False)
            p['crop_receipts'].append({'kind': 'deposit', 'step': p['deposit_step'],
                                      'observed_at': now, 'units': p['harvest_quantity']})
        else:p.update(status='input_recovery_only', receipt_failure='deposit_not_observed')
    elif status == 'deposited':
        if shed != p['sale_quantity_remaining'] or any(carried) or other_sites:
            p.update(status='sale_attribution_unknown', receipt_failure='owned_shed_stock_changed')
    return p


def commit_harvest(intent, observation, returned):
    """Bind the existing actor's actual harvest; do not alter a unit action."""
    identity=_public_identity(observation)
    if (intent is None or intent['status'] != 'growing' or identity is None
            or identity[0] != intent['player']
            or identity[1] != intent.get('last_observed_step')):
        return intent
    seat,now=identity; worker = intent['worker']; x, y = intent['site']
    if now != intent['harvest_step']:
        return intent
    farm = observation['farms'][seat]
    positions = [farm['farmer'], *farm['hands']]; actions = units(returned)
    tile = farm['tiles'][y][x]
    shed, carried, other_sites = _carrots(observation, (x, y))
    valid = (worker < len(positions) and worker < len(actions)
             and tuple(positions[worker]) == (x, y) and actions[worker] == ['HARVEST']
             and isinstance(tile, dict) and tile.get('crop') == 'CARROT'
             and tile.get('planted_day') == intent['planted_day']
             and tile.get('yield_units') == 3 and now // 24 - tile['planted_day'] >= 2
             and observation['private']['inventories'][worker] == {}
             and not shed and not any(carried) and not other_sites)
    if valid:
        valid = not any(i != worker and i < len(actions) and tuple(pos) == (x, y)
                        and actions[i] and actions[i][0] not in ('PASS','NORTH','SOUTH','EAST','WEST')
                        for i, pos in enumerate(positions))
    if not valid:
        return dict(intent, status='input_recovery_only', receipt_failure='harvest_return_not_bound')
    return dict(intent, status='awaiting_observed_harvest', harvest_quantity=3)


def commit_deposit(intent, observation, returned, post):
    """Certify EOD transfer from the existing completed final-unit snapshot.

    All carried items, both current collections and every physical purchase
    consume shared room. Current/future sales provide no capacity credit.
    """
    identity=_public_identity(observation)
    if (intent is None or intent['status'] != 'carried' or identity is None
            or identity[0] != intent['player']
            or identity[1] != intent.get('last_observed_step')):
        return intent
    seat,now=identity
    if now != intent['deposit_step']:
        return intent
    if _public_identity(post) != (seat,now):
        return dict(intent, status='input_recovery_only', receipt_failure='deposit_snapshot_unbound')
    private = post['private']; worker = intent['worker']
    shed, carried, other_sites = _carrots(post)
    buys = 0
    for a in returned.get('market', [])[:10]:
        if not a:continue
        if len(a) > 1 and a[1] == 'CARROT' and a[0] in ('SELL', 'BUY_PRODUCT'):
            return dict(intent, status='input_recovery_only', receipt_failure='carrot_touched_before_deposit')
        if a[0] in ('BUY_PRODUCT', 'BUY_ANIMAL'):
            if len(a) < 3 or type(a[2]) is not int or a[2] < 0:
                return dict(intent, status='input_recovery_only', receipt_failure='unbounded_purchase')
            buys += a[2]
    bound = sum(private['shed'].values()) + sum(sum(inv.values()) for inv in private['inventories']) + buys
    if (now % 24 != 23 or bound > 100 or shed or other_sites
            or worker >= len(carried) or carried[worker] != intent['harvest_quantity']
            or any(q for i, q in enumerate(carried) if i != worker)):
        return dict(intent, status='input_recovery_only', receipt_failure='deposit_not_exclusively_feasible')
    return dict(intent, status='awaiting_observed_deposit', deposit_stock_upper=bound,
                deposit_future_sale_credit=0)


def observe_crop_sale(intent, observation, fill_result):
    """Use the existing own-fill ledger; uncertain fills cannot create credit."""
    if intent is None or intent['status'] != 'awaiting_observed_sale':
        return intent
    identity=_public_identity(observation)
    if identity is None:return intent
    seat,now=identity
    if now==intent['sale_step'] and seat==intent['player']:return intent
    p = deepcopy(intent); binding = (fill_result or {}).get('binding', {})
    if (binding.get('step') != p['sale_step'] or binding.get('player') != p['player']
            or seat != p['player']
            or binding.get('action_sha256') != p.get('sale_action_sha256')
            or now != p['sale_step'] + 1
            or (fill_result or {}).get('status') not in ('reconciled', 'ambiguous')):
        p.update(status='sale_attribution_unknown', receipt_failure='sale_receipt_unbound')
        return p
    orders = {o.get('slot'): o for o in (fill_result or {}).get('orders', [])}
    sold = 0
    for slot, requested in p['sale_orders']:
        order = orders.get(slot, {})
        low = order.get('fill_min'); high = order.get('fill_max')
        if (order.get('type') != 'SELL' or order.get('item') != 'CARROT'
                or order.get('requested') != requested or type(low) is not int
                or high != low or not 0 <= low <= requested):
            p.update(status='sale_attribution_unknown', receipt_failure='sale_fill_not_exact')
            return p
        sold += low
    if sold > p['sale_quantity_remaining']:
        p.update(status='sale_attribution_unknown', receipt_failure='sale_exceeds_owned_quantity')
        return p
    remaining = p['sale_quantity_remaining'] - sold
    shed, carried, sites = _carrots(observation)
    if shed != remaining or any(carried) or sites:
        p.update(status='sale_attribution_unknown', receipt_failure='sale_stock_did_not_reconcile')
        return p
    p['sale_quantity_remaining'] = remaining
    p['status'] = 'sold' if remaining == 0 else 'deposited'
    if sold:
        p['crop_receipts'].append({'kind': 'sale', 'step': p['sale_step'],
                                  'observed_at': now, 'units': sold,
                                  'cash_receipt': None})
    return p


def propose_input_repair(mechanics,intent,observation,configuration,selected,post,route):
    """Replace only the crop's missing wheat after its original delivery date.

    This changes no pickup/feed. A market buy cannot rescue this turn's earlier
    unit stage. Current shared room includes all physical purchases and, at
    EOD, every carried item. All requested capital through the next day's first
    service row is funded without sale credit. Failed/partial fills retain debt;
    an ambiguous receipt blocks another buy rather than double purchasing.
    """
    report={'changed':False,'reason':'no_due_input_repair'}
    if intent is None:return selected,None,report
    identity=_public_identity(observation)
    if identity is None:return selected,None,report
    seat,now=identity;n=int(intent.get('input_repair_remaining',0))
    if (n<=0 or now<intent['deposit_step'] or now>576
            or intent.get('input_repair_pending') or intent.get('input_repair_unknown')
            or seat!=intent['player'] or now!=intent.get('last_observed_step')):
        return selected,None,report
    if _public_identity(post)!=(seat,now):
        report['reason']='repair_snapshot_unbound';return selected,None,report
    orders=selected.get('market',[])
    if any(a and len(a)>1 and a[:2]==['BUY_PRODUCT','WHEAT'] for a in orders):
        report['reason']='existing_wheat_purchase_needs_its_own_receipt';return selected,None,report
    sales=[]
    for slot,a in enumerate(orders[:10]):
        if a and len(a)>1 and a[:2]==['SELL','WHEAT']:
            if len(a)!=3 or type(a[2]) is not int or a[2]<0:
                report['reason']='unbounded_wheat_sale';return selected,None,report
            if a[2]:sales.append((slot,a[2]))
    private=post['private'];out=deepcopy(selected);kind='buy'
    baseline_sell=min(int(private['shed'].get('WHEAT',0)),sum(q for _,q in sales))
    if sales:
        n=min(n,baseline_sell)
        if n<=0:
            report['reason']='no_executable_wheat_sale_to_reserve';return selected,None,report
        kind='withhold';remaining=baseline_sell-n
        for slot,q in sales:
            allowed=min(q,remaining);remaining-=allowed
            out['market'][slot]=['SELL','WHEAT',allowed] if allowed else []
    elif len(orders)<10:out['market'].append(['BUY_PRODUCT','WHEAT',n])
    else:
        report['reason']='repair_requires_a_free_nonconflicting_slot';return selected,None,report
    buys=0
    for a in orders:
        if a and a[0] in ('BUY_PRODUCT','BUY_ANIMAL'):
            if len(a)!=3 or type(a[2]) is not int or a[2]<0:
                report['reason']='unbounded_current_purchase';return selected,None,report
            buys+=a[2]
    room_bound=sum(private['shed'].values())+buys+(n if kind=='buy' else 0)
    if now%24==23:room_bound+=sum(sum(inv.values()) for inv in private['inventories'])
    if room_bound>100:
        report['reason']='repair_or_eod_delivery_lacks_shared_room';return selected,None,report
    through=min(576,(now//24+1)*24+1)
    prices=input_price_bounds(mechanics,observation,configuration,route,through,out['market'])
    if prices is None:
        report['reason']='unsupported_repair_price_bound';return selected,None,report
    farm=post['farms'][intent['player']];cash=float(farm['money']);hires=int(farm['hires_today'])
    initial=cash
    rows=[out,*route[now+1:through+1]]
    for offset,row in enumerate(rows):
        for a in row.get('market',[])[:10]:
            if not a:continue
            op=a[0]
            if op=='HIRE':cost=mechanics._hire_cost(hires,1);hires+=1
            elif op=='SELL':continue
            elif op in ('BUY_PRODUCT','BUY_SEED','BUY_ANIMAL'):
                if len(a)!=3 or type(a[2]) is not int or a[2]<0:
                    report['reason']='unbounded_repair_funding_row';return selected,None,report
                item,q=a[1],a[2]
                if op=='BUY_PRODUCT' and item in prices:cost=q*prices[item]['price_upper']
                elif op=='BUY_SEED' and item in mechanics.CROPS:cost=q*mechanics.CROPS[item]['seed']
                elif op=='BUY_ANIMAL' and item in mechanics.ANIMALS:cost=q*mechanics.ANIMALS[item]['cost']
                else:
                    report['reason']='unsupported_repair_purchase';return selected,None,report
            else:
                report['reason']='unsupported_repair_capital';return selected,None,report
            cash-=cost
            if cash<0:
                report['reason']='repair_or_boundary_capital_not_funded';return selected,None,report
        if (now+offset)%24==23:hires=0
    proposal={'step':now,'player':intent['player'],'slot':len(orders),'units':n,'kind':kind,
              'unit_binding':deepcopy(units(selected)),
              'inherited_market':deepcopy(orders),'expected_market':deepcopy(out['market']),
              'shared_stock_upper':room_bound,
              'funding_through':through,'spending_upper':initial-cash}
    if kind=='withhold':
        expected_sales=baseline_sell-n
        proposal.update(sale_slots=[(slot,out['market'][slot][2]) for slot,_ in sales if out['market'][slot]],
            original_sale_slots=[slot for slot,_ in sales],expected_sale_units=expected_sales,
            expected_shed_wheat=int(private['shed'].get('WHEAT',0))-expected_sales+
                (sum(int(inv.get('WHEAT',0)) for inv in private['inventories']) if now%24==23 else 0))
    report.update(changed=True,reason='funded_replacement_after_unit_stage',**proposal)
    return out,proposal,report


def commit_input_repair(intent,proposal,observation,returned,post):
    if intent is None or proposal is None:return intent
    identity=_public_identity(observation)
    if identity is None:return intent
    seat,now=identity;slot=proposal['slot'];n=proposal['units']
    if (now!=proposal['step'] or seat!=proposal['player']
            or units(returned)!=proposal['unit_binding']
            or returned.get('market',[])!=proposal['expected_market']
            or _public_identity(post)!=(proposal['player'],now)):
        if any(a and len(a)>2 and a[:2]==['BUY_PRODUCT','WHEAT'] and a[2]>0
               for a in returned.get('market',[])[:10]):
            return dict(intent,input_repair_unknown=True)
        if (proposal['kind']=='withhold' and any(
                returned.get('market',[])[s:s+1]!=proposal['inherited_market'][s:s+1]
                for s in proposal['original_sale_slots'])):
            return dict(intent,input_repair_unknown=True)
        return intent
    pending=dict(proposal,action_sha256=hashlib.sha256(json.dumps(returned,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest())
    return dict(intent,input_repair_pending=pending)


def observe_input_repair(intent,observation,fill_result):
    if intent is None or not intent.get('input_repair_pending'):return intent
    identity=_public_identity(observation)
    if identity is None:return intent
    seat,now=identity;pending=intent['input_repair_pending']
    if now<=pending['step']:return intent
    p=deepcopy(intent);p.pop('input_repair_pending',None)
    binding=(fill_result or {}).get('binding',{})
    valid=(now==pending['step']+1 and seat==pending['player']
           and binding.get('step')==pending['step'] and binding.get('player')==pending['player']
           and binding.get('action_sha256')==pending['action_sha256']
           and (fill_result or {}).get('status') in ('reconciled','ambiguous'))
    rows={a.get('slot'):a for a in (fill_result or {}).get('orders',[])}
    if pending['kind']=='buy':
        row=rows.get(pending['slot'],{});n=row.get('fill_min')
        valid=(valid and row.get('type')=='BUY_PRODUCT' and row.get('item')=='WHEAT'
               and row.get('requested')==pending['units'] and type(n) is int
               and row.get('fill_max')==n and 0<=n<=pending['units'])
    else:
        sold=0;n=pending['units']
        for slot,requested in pending['sale_slots']:
            row=rows.get(slot,{});filled=row.get('fill_min')
            if (row.get('type')!='SELL' or row.get('item')!='WHEAT'
                    or row.get('requested')!=requested or type(filled) is not int
                    or row.get('fill_max')!=filled):valid=False;break
            sold+=filled
        valid=(valid and sold==pending['expected_sale_units']
               and observation['private']['shed'].get('WHEAT',0)==pending['expected_shed_wheat'])
    if not valid:return dict(p,input_repair_unknown=True)
    p['input_repair_remaining']-=n
    p['wheat_reserve_required']=p['input_repair_remaining']
    p.setdefault('input_repair_receipts',[]).append(
        {'step':pending['step'],'observed_at':now,'kind':pending['kind'],
         'requested':pending['units'],'restored_units':n,
         'purchase_filled':n if pending['kind']=='buy' else None,
         'sale_units_withheld':n if pending['kind']=='withhold' else None})
    return p


def _carrot_sell_quantity(order):
    """Return the pinned engine's executable CARROT SELL quantity, else None."""
    if not isinstance(order, list) or len(order) < 3:
        return None
    if order[0] != 'SELL' or order[1] != 'CARROT':
        return None
    try:
        quantity = int(order[2])
    except (TypeError, ValueError):
        return None
    return quantity if quantity > 0 else None


def offer_crop(intent, observation, selected):
    """Give the observed lot to the existing selected seller once.

    The seller may defer it. This proposal neither bypasses its valuation nor
    counts an emitted request as a fill. Every inherited row keeps its index.
    """
    identity=_public_identity(observation)
    if identity is None:return selected,False
    seat,now=identity
    if (intent is None or intent['status'] != 'deposited'
            or seat != intent['player'] or now != intent.get('last_observed_step')
            or intent.get('offered_to_seller')
            or not intent['outlet_step'] <= now <= 576):
        return selected, False
    n = int(intent['sale_quantity_remaining'])
    shed, carried, sites = _carrots(observation)
    if n <= 0 or shed != n or any(carried) or sites:
        return selected, False
    # No unit may move/consume a carrot before the selected seller's snapshot.
    if any(a and len(a) > 1 and a[1] == 'CARROT'
           and a[0] in ('PICKUP', 'PLACE', 'PLANT') for a in units(selected)):
        return selected, False
    market = selected.get('market', [])
    if any(isinstance(a, list) and len(a) > 1 and a[1] == 'CARROT'
           and a[0] == 'BUY_PRODUCT' for a in market[:10]):
        return selected, False
    offered = sum(_carrot_sell_quantity(a) or 0 for a in market[:10])
    if offered >= n:
        return selected, True
    if len(market) >= 10:
        return selected, False
    out = deepcopy(selected)
    out['market'].append(['SELL', 'CARROT', n - offered])
    return out, True


def commit_crop_sale(intent, observation, returned, post, *, offered=False,
                     seller_completed=False):
    """Bind final slots once, sharing the runtime's already completed snapshot."""
    identity=_public_identity(observation)
    if (intent is None or intent['status'] != 'deposited' or identity is None
            or identity[0] != intent['player']
            or identity[1] != intent.get('last_observed_step')):
        return intent
    seat,now=identity
    p = deepcopy(intent)
    if offered and seller_completed:
        p['offered_to_seller'] = True  # Planning ownership only, not a sale.
    rows = []
    for slot, a in enumerate(returned.get('market', [])[:10]):
        if not a:continue
        if (isinstance(a, list) and len(a) > 1 and a[1] == 'CARROT'
                and a[0] == 'BUY_PRODUCT'):
            p.update(status='sale_attribution_unknown', receipt_failure='carrot_purchase_in_sale_queue')
            return p
        quantity = _carrot_sell_quantity(a)
        if quantity is not None:
            rows.append((slot, quantity))
    if _public_identity(post) != (seat,now):
        p.update(status='sale_attribution_unknown', receipt_failure='sale_snapshot_unbound')
        return p
    shed, carried, sites = _carrots(post)
    if shed != p['sale_quantity_remaining'] or any(carried) or sites:
        p.update(status='sale_attribution_unknown', receipt_failure='sale_source_no_longer_exclusive')
        return p
    if not rows:
        return p
    p.update(status='awaiting_observed_sale', sale_step=now,
             sale_orders=rows, offered_to_seller=True,
             sale_action_sha256=hashlib.sha256(json.dumps(returned, sort_keys=True,
                 separators=(',', ':'), allow_nan=False).encode()).hexdigest())
    return p
