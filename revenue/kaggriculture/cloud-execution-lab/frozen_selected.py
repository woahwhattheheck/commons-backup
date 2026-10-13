# SPDX-License-Identifier: Apache-2.0
"""Frozen SELL method with selected base parameter; no second parent call.

Generated mechanically from scheduler.py SHA256 32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9.
The selected-action boundary also optionally exposes its exact unit snapshot.
Original scheduler and sale valuation remain intact.
"""
from scheduler import *
import scheduler as scheduling
from seller_snapshot import seller_public_observation
from selected_sell_core import optimize_lot, joint_plan_metrics, shared_slot_ledger


def _engine_market_prefix(action, config):
    """Return exactly the market rows the pinned engine can execute this turn."""
    market=action.get('market',[]) if isinstance(action,dict) else []
    queue=list(market) if isinstance(market,list) else []
    return queue[:max(1,int(config.get('maxMarketOrdersPerTurn',10)))]


def materialize_sales(orders, current, shed, targets, max_orders):
    """The existing emitter, including empty indexes and one physical lot budget."""
    market=[];remaining=dict(current);available=dict(shed)
    max_orders=max(1,int(max_orders))
    for index,raw in enumerate(orders):
        if index>=max_orders:
            market.append(raw)
            continue
        o=list(raw)
        if o and o[0]=='SELL' and len(o)>2 and o[1] in targets:
            item=o[1]
            q=min(max(0,int(o[2])),remaining.get(item,0),max(0,available.get(item,0)))
            remaining[item]=remaining.get(item,0)-q;available[item]=available.get(item,0)-q
            market.append(['SELL',item,q] if q else [])
        else:market.append(o)
    for item in sorted(targets):
        q=min(remaining.get(item,0),max(0,available.get(item,0)))
        if q>0 and len(market)<max_orders:
            market.append(['SELL',item,q]);available[item]=available.get(item,0)-q
    return market


def sale_quantities(orders):
    result={}
    for o in orders:
        if o and len(o)>2 and o[0]=='SELL':
            result[o[1]]=result.get(o[1],0)+max(0,int(o[2]))
    return result

def _stressed_sale_receipt(item, quantity, inventory, market, shops, config, now,
                            rival_quantity):
    """Worst receipt across the selected scheduler's explicit same-turn rival cases."""
    quantity=max(0,int(quantity))
    if quantity<=0 or item not in m.PRODUCTS:return 0,int(inventory),'none'
    rival=max(0,int(rival_quantity or 0))
    model=MarketPath(item,int(inventory),market.get('params'),shops,config,now,now)
    cases={}
    for name,r,alignment in (
            ('no_rival',0,'paired'),
            ('observed_paired',rival,'paired'),
            ('observed_before',rival,'before')):
        cases[name]=model.joint(int(inventory),quantity,r,alignment)
    name,(cash,_other,ending)=min(
        cases.items(),key=lambda entry:(int(entry[1][0]),-int(entry[1][2]),entry[0]))
    return int(cash),int(ending),name


def _market_prefix_state(orders, farm, private, market, shops, config, now,
                         rival_quantity, stop):
    """Execute our queue prefix with exact fixed costs and conservative SELL receipts."""
    money=int(farm['money']);hires=int(farm['hires_today'])
    unlocked=list(farm['unlocked_quadrants']);shed=dict(private['shed'])
    inventory=dict(market['inventory']);cap=int(config.get('shedCapacity',100))
    outcomes={};stress=[]
    stop=min(int(stop),len(orders)-1)
    for index,order in enumerate(orders[:stop+1]):
        if not order:continue
        op=order[0]
        if op=='SELL' and len(order)>2 and order[1] in m.PRODUCTS:
            item=order[1];requested=max(0,int(order[2]))
            sold=min(requested,max(0,int(shed.get(item,0))))
            rival=(rival_quantity(item) if callable(rival_quantity)
                   else dict(rival_quantity or {}).get(item,0))
            cash,ending,scenario=_stressed_sale_receipt(
                item,sold,inventory[item],market,shops,config,now,rival)
            money+=cash;shed[item]=max(0,int(shed.get(item,0))-sold)
            inventory[item]=ending
            stress.append({'index':index,'item':item,'quantity':sold,
                           'receipt':cash,'scenario':scenario})
            continue
        if op=='BUY_PRODUCT':
            return {'money':money,'outcomes':outcomes,'unsupported_index':index,
                    'shed':shed,'inventory':inventory,'sale_stress':stress}
        if op=='HIRE':
            cost,_=scheduling._order_spend(
                order,{'unlocked_quadrants':unlocked},inventory,market.get('params'),
                hires,config)
            completed=1 if money>=cost else 0
            if completed:money-=cost;hires+=1
            outcomes[index]={'required':1,'completed':completed,'cost_per_unit':cost}
            continue
        if op=='BUY_LAND':
            required=1 if len(unlocked)<=len(m.LAND_ORDER) else 0
            if not required:continue
            cost,_=scheduling._order_spend(
                order,{'unlocked_quadrants':unlocked},inventory,market.get('params'),
                hires,config)
            completed=1 if money>=cost else 0
            if completed:
                money-=cost
                unlocked.append(m.LAND_ORDER[len(unlocked)-1])
            outcomes[index]={'required':1,'completed':completed,'cost_per_unit':cost}
            continue
        if op=='BUY_SEED' and len(order)>2 and order[1] in m.CROPS:
            required=max(0,int(order[2]));cost=int(m.CROPS[order[1]]['seed'])
            completed=0
            for _ in range(required):
                if money<cost:break
                money-=cost;completed+=1
            outcomes[index]={'required':required,'completed':completed,
                             'cost_per_unit':cost}
            continue
        if op=='BUY_ANIMAL' and len(order)>2 and order[1] in m.ANIMALS:
            item=order[1];required=max(0,int(order[2]));cost=int(m.ANIMALS[item]['cost'])
            completed=0
            for _ in range(required):
                if money<cost or sum(max(0,int(n)) for n in shed.values())>=cap:break
                money-=cost;shed[item]=int(shed.get(item,0))+1;completed+=1
            outcomes[index]={'required':required,'completed':completed,
                             'cost_per_unit':cost}
    return {'money':money,'outcomes':outcomes,'unsupported_index':None,
            'shed':shed,'inventory':inventory,'sale_stress':stress}


def fund_same_turn_acquisition(orders, farm, private, market, shops, config, now,
                               targets, rival_quantity):
    """Move only already-planned SELL units ahead of the first failing fixed buy.

    Producer order indexes never move. A sale can occupy an earlier empty slot or
    enlarge an earlier SELL of the same product. Total same-turn sale quantities
    are invariant, so this only realizes proceeds earlier; it never invents stock
    or future cash. BUY_PRODUCT is a hard boundary because its unit price changes
    with same-index market interleaving.
    """
    original=copy.deepcopy(orders)
    if not original:return original,None
    max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))
    baseline=_market_prefix_state(
        original,farm,private,market,shops,config,now,rival_quantity,
        min(len(original),max_orders)-1)
    target=None
    for index in sorted(baseline['outcomes']):
        outcome=baseline['outcomes'][index]
        if outcome['required']>outcome['completed']:
            target=index;break
    barrier=baseline.get('unsupported_index')
    if target is None:
        return original,({'applied':False,'reason':'unsupported-buy-product',
                          'barrier_index':barrier} if barrier is not None else None)
    if barrier is not None and barrier<target:
        return original,{'applied':False,'reason':'unsupported-buy-product',
                         'barrier_index':barrier}
    before=baseline['outcomes'][target]
    candidates=[]
    targets=set(targets)
    source_limit=min(barrier if barrier is not None else len(original),max_orders)
    for source in range(target+1,source_limit):
        row=original[source]
        if not (row and len(row)>2 and row[0]=='SELL'
                and row[1] in targets and int(row[2])>0):continue
        item=row[1];available=max(0,int(row[2]))
        same=[i for i in range(target)
              if original[i] and len(original[i])>2
              and original[i][0]=='SELL' and original[i][1]==item]
        empty=[i for i in range(target) if not original[i]]
        if same:destination=max(same)
        elif empty:destination=max(empty)
        else:continue
        for moved in range(1,available+1):
            candidate=copy.deepcopy(original)
            if candidate[destination]:
                candidate[destination][2]=int(candidate[destination][2])+moved
            else:candidate[destination]=['SELL',item,moved]
            remaining=available-moved
            candidate[source]=['SELL',item,remaining] if remaining else []
            if sale_quantities(candidate)!=sale_quantities(original):continue
            state=_market_prefix_state(
                candidate,farm,private,market,shops,config,now,rival_quantity,target)
            outcome=state['outcomes'].get(target,{})
            if outcome.get('completed',0)<before['required']:continue
            candidates.append((
                (moved,-int(state['money']),source-target,target-destination,item),
                candidate,
                {'applied':True,'target_index':target,
                 'target_order':copy.deepcopy(original[target]),
                 'baseline_completed':before['completed'],
                 'funded_completed':outcome['completed'],
                 'source_index':source,'destination_index':destination,
                 'item':item,'moved_quantity':moved,
                 'remaining_cash_after_target':int(state['money']),
                 'sale_stress':state['sale_stress'],
                 'sale_quantities_preserved':True}))
            break
    if not candidates:
        return original,{'applied':False,'reason':'no-safe-prefix-sale',
                         'target_index':target,
                         'baseline_completed':before['completed'],
                         'required':before['required']}
    _rank,best,info=min(candidates,key=lambda entry:entry[0])
    return best,info


def _funding_prefix_end(trace, now, end):
    """Stop before the next actually executed positive-cash future sale.

    Requested future revenue is not cash. A requested SELL that clips to
    zero fill does not terminate the prefix.
    """
    for t, _item, _units, cash in trace.get('executed_sales', ()):
        if t > now and cash > 0:
            return t - 1, t
    return end, None


def _funding_trace(obs, config, farm, private, route, now, end, current_market,
                   stress_units=0):
    """Execute the bounded own market tape and return actual acquisition fills.

    Only the current turn's materialized sales may fund the prefix.  Future unit
    actions are applied before their market turn so shed clipping remains real.
    `stress_units` is a named prior rival draw from every BUY_PRODUCT market.
    Future SELL rows are simulated for prefix discovery; only positive-cash
    fills count as funding events.
    """
    f, p = copy.deepcopy(farm), copy.deepcopy(private)
    inventory = {k: int(v) for k, v in obs['market']['inventory'].items()}
    params = obs['market'].get('params')
    cap = int(config.get('shedCapacity', 100))
    max_orders = max(1, int(config.get('maxMarketOrdersPerTurn', 10)))
    hires = int(f.get('hires_today', 0))
    buy_items = set()
    for t in range(now, end + 1):
        orders = current_market if t == now else (route[t].get('market', []) if t < len(route) else [])
        for o in orders[:max_orders]:
            if o and len(o) > 2 and o[0] == 'BUY_PRODUCT':
                buy_items.add(o[1])
    if stress_units:
        for item in buy_items:
            inventory[item] = inventory.get(item, 0) - int(stress_units)
    acquisitions = []
    executed_sales = []
    for t in range(now, end + 1):
        if t > now:
            action = route[t] if t < len(route) else parent.PASS
            acts = [action.get('farmer', ['PASS']), *action.get('hands', [])]
            for i, a in enumerate(acts):
                m._apply_unit_action(f, p, i, a, len(f['tiles']), t // 24, 24, 10**6)
        if t > now and t % 24 == 0:
            hires = 0
        orders = current_market if t == now else (route[t].get('market', []) if t < len(route) else [])
        for index, order in enumerate(orders[:max_orders]):
            if not order:
                continue
            op = order[0]
            item = order[1] if len(order) > 1 else ''
            requested = max(0, int(order[2])) if len(order) > 2 else 1
            executed = 0
            if op == 'SELL' and len(order) > 2:
                cash = 0
                for _ in range(requested):
                    if p['shed'].get(item, 0) <= 0:
                        break
                    price = m.market_price(item, inventory[item], params)
                    p['shed'][item] -= 1
                    f['money'] += price
                    cash += price
                    executed += 1
                    if price > 1:
                        inventory[item] += 1
                if t > now:
                    executed_sales.append((t, item, executed, cash))
            elif op == 'HIRE':
                price = m._hire_cost(hires, int(config.get('farmHandCostMult', 1)))
                if f['money'] >= price:
                    f['money'] -= price
                    hires += 1
                    executed = 1
                    f['hands'].append(m._spawn_hand(f, len(f['tiles'])))
                    p['inventories'].append({})
                acquisitions.append(((t, index, op, ''), executed))
            elif op == 'BUY_LAND':
                land_index = len(f['unlocked_quadrants']) - 1
                price = m.LAND_PRICES[land_index] if land_index < len(m.LAND_PRICES) else 0
                if f['money'] >= price:
                    f['money'] -= price
                    executed = 1
                    if len(f['unlocked_quadrants']) <= len(m.LAND_ORDER):
                        f['unlocked_quadrants'].append(
                            m.LAND_ORDER[len(f['unlocked_quadrants']) - 1])
                acquisitions.append(((t, index, op, ''), executed))
            elif op == 'BUY_SEED' and len(order) > 2 and item in m.CROPS:
                price = int(m.CROPS[item]['seed'])
                for _ in range(requested):
                    if f['money'] < price:
                        break
                    f['money'] -= price
                    p['seeds'][item] = p['seeds'].get(item, 0) + 1
                    executed += 1
                acquisitions.append(((t, index, op, item), executed))
            elif op == 'BUY_ANIMAL' and len(order) > 2 and item in m.ANIMALS:
                price = int(m.ANIMALS[item]['cost'])
                for _ in range(requested):
                    if f['money'] < price or sum(p['shed'].values()) >= cap:
                        break
                    f['money'] -= price
                    p['shed'][item] = p['shed'].get(item, 0) + 1
                    executed += 1
                acquisitions.append(((t, index, op, item), executed))
            elif op == 'BUY_PRODUCT' and len(order) > 2 and item in m.PRODUCTS:
                for _ in range(requested):
                    if sum(p['shed'].values()) >= cap:
                        break
                    price = m.market_price(item, inventory[item] - 1, params)
                    if f['money'] < price:
                        break
                    f['money'] -= price
                    inventory[item] -= 1
                    p['shed'][item] = p['shed'].get(item, 0) + 1
                    executed += 1
                acquisitions.append(((t, index, op, item), executed))
    return {'cash': int(f['money']), 'acquisitions': acquisitions,
            'executed_sales': executed_sales}


def funded_minimum_now(obs, config, base, farm, private, route, end,
                       current, targets, item, stress_units=32):
    """Smallest current sale that preserves the inherited executable prefix."""
    now = int(obs['step'])
    baseline = max(0, int(current.get(item, 0)))
    max_orders = int(config.get('maxMarketOrdersPerTurn', 10))
    certificate = {
        'item': item, 'baseline_now': baseline, 'prefix_end': end,
        'funding_turn': None, 'stress_units': int(stress_units),
        'fallback': False,
    }
    try:
        reference_market = materialize_sales(
            base['market'], current, private['shed'], targets, max_orders)
        scout = _funding_trace(
            obs, config, farm, private, route, now, end,
            reference_market, stress_units=0)
        prefix_end, funding_turn = _funding_prefix_end(scout, now, end)
        certificate['prefix_end'] = prefix_end
        certificate['funding_turn'] = funding_turn
        if prefix_end == end:
            reference = scout
        else:
            reference = _funding_trace(
                obs, config, farm, private, route, now, prefix_end,
                reference_market, stress_units=0)
        required = {key: units for key, units in reference['acquisitions'] if units > 0}
        certificate['reference_acquisitions'] = sum(required.values())
        certificate['reference_terminal_cash'] = reference['cash']
        if not required:
            certificate['minimum_now'] = 0
            return 0, certificate
        for quantity in range(baseline + 1):
            totals = dict(current)
            totals[item] = quantity
            candidate_market = materialize_sales(
                base['market'], totals, private['shed'], targets, max_orders)
            traces = [
                _funding_trace(obs, config, farm, private, route, now, prefix_end,
                               candidate_market, stress_units=0),
                _funding_trace(obs, config, farm, private, route, now, prefix_end,
                               candidate_market, stress_units=stress_units),
            ]
            safe = True
            for trace in traces:
                filled = dict(trace['acquisitions'])
                if any(filled.get(key, 0) < units for key, units in required.items()):
                    safe = False
                    break
            if safe:
                certificate['minimum_now'] = quantity
                certificate['scenario_terminal_cash'] = [trace['cash'] for trace in traces]
                return quantity, certificate
    except Exception as exc:
        certificate['error'] = f'{type(exc).__name__}: {exc}'[:500]
    certificate['fallback'] = True
    certificate['minimum_now'] = baseline
    return baseline, certificate


def joint_resource_bound(obs, config, base, farm, private, route, end,
                         current_market=None, rival_quantity=None):
    """Bound fixed capital and same-day stock, optionally using current sales.

    With no DROP or day close, only literal PLACE quantities and animal buys
    can add shed stock. Count all such requests, even unreachable ones; carried
    harvest is not in the shed. No unit transitions or future fills are assumed.
    The extra capital boundary includes the next turn's hires. Variable-price
    purchases remain outside joint admission. An explicit current market may
    fund the window with conservative physical SELL receipts, provided every
    current acquisition executes in order. Requested future sales earn no cash.
    """
    now=int(obs['step']);size=len(farm['tiles']);cap=int(config.get('shedCapacity',100))
    max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))
    if (int(config.get('turnsPerDay',24))!=24 or size!=10
            or now//24!=end//24 or end<=now or end%24==23):return None
    last=int(config.get('episodeSteps',720))-2
    if end==last:return None
    capital_end=min(last,end+1)
    if capital_end%24==23:return None
    if any(now<checkpoint<=capital_end for checkpoint,*_ in parent.DECISIONS):return None
    def orders_at(t):
        return (base['market'] if current_market is None else current_market) if t==now else route[t].get('market',[]) if t<len(route) else []
    budget_farm={'unlocked_quadrants':list(farm['unlocked_quadrants'])}
    hires=int(farm['hires_today']);cost=0;arrivals={}
    for t in range(now,capital_end+1):
        if t>now and t%24==0:hires=0
        for order in list(orders_at(t))[:max_orders]:
            if not order:continue
            op=order[0]
            if op not in ('SELL','HIRE','BUY_LAND','BUY_SEED','BUY_ANIMAL'):return None
            if op in ('SELL','BUY_SEED','BUY_ANIMAL'):
                if len(order)<3:return None
                item,n=order[1],max(0,int(order[2]))
                if op=='BUY_SEED' and item not in m.CROPS:return None
                if op=='BUY_ANIMAL':
                    if item not in m.ANIMALS:return None
                    arrivals[item]=arrivals.get(item,0)+n
            amount,hires=scheduling._order_spend(order,budget_farm,{},None,hires,config)
            cost+=amount
            if op=='BUY_LAND' and len(budget_farm['unlocked_quadrants'])<=len(m.LAND_ORDER):
                budget_farm['unlocked_quadrants'].append(m.LAND_ORDER[len(budget_farm['unlocked_quadrants'])-1])
    funding=None
    if farm['money']<cost:
        if current_market is None:return None
        state=_market_prefix_state(
            current_market,farm,private,obs['market'],
            obs.get('town',{}).get('unlocked_shops',[]),config,now,
            rival_quantity,min(len(current_market),max_orders)-1)
        if (state['unsupported_index'] is not None
                or any(row['completed']<row['required']
                       for row in state['outcomes'].values())):return None
        spent=sum(row['completed']*row['cost_per_unit']
                  for row in state['outcomes'].values())
        # Every current purchase must execute in order. Only current physical
        # sales can fund the remaining fixed spend; future SELLs earn no credit.
        future_cost=cost-spent
        if state['money']<future_cost:return None
        funding={'current_sale_receipt':state['money']-int(farm['money'])+spent,
                 'current_fixed_spend':spent,'remaining_cash':state['money'],
                 'future_fixed_cost':future_cost,'sale_stress':state['sale_stress']}
    upper={p:max(0,int(n)) for p,n in private['shed'].items()}
    # A boundary unit-stage deposit runs before the next chance to sell.
    for t in range(now+1,capital_end+1):
        action=route[t] if t<len(route) else parent.PASS
        for a in [action.get('farmer',['PASS']),*action.get('hands',[])]:
            if not a:continue
            if a[0]=='DROP':return None
            if a[0]=='PLACE' and len(a)>1:
                n=max(0,int(a[2])) if len(a)>2 else 1
                upper[a[1]]=upper.get(a[1],0)+n
    for item,n in arrivals.items():upper[item]=upper.get(item,0)+n
    if sum(upper.values())>cap:return None
    bound={'fixed_cost':cost,'capital_end':capital_end,'stock_upper':upper,
           'stock_total_upper':sum(upper.values()),'capacity':cap}
    if funding is not None:bound['current_sale_funding']=funding
    return bound


def joint_queue_ledger(plans, current, planned, shed, bound, orders_at, now, end, max_orders):
    """Account for every retained plan using the actual emitter and stock bounds."""
    max_orders=max(1,int(max_orders))
    committed={p:list(rows) for p,rows in planned.items()}
    wanted_now=dict(current)
    for item,plan in plans.items():
        wanted_now[item]=dict(plan).get(now,0)
        committed[item]=[(t,q) for t,q in plan if t>now and q>0]
    all_plans={}
    for t in range(now,end+1):
        stock=shed if t==now else bound['stock_upper']
        targets={p for p in PRODUCTS if stock.get(p,0)>0}
        raw=sale_quantities(list(orders_at(t))[:max_orders])
        # Unfilled earlier intentions can still be due. Do not take credit for
        # their requested sales, or forget unchanged products with existing plans.
        wanted=(wanted_now if t==now else {
            p:min(stock[p],raw.get(p,0)+sum(q for d,q in committed.get(p,[]) if d<=t))
            for p in targets})
        market=materialize_sales(orders_at(t),wanted,stock,targets,max_orders)
        actual=sale_quantities(market[:max_orders])
        if any(actual.get(p,0)!=q for p,q in wanted.items() if p in targets):return None
        for p,q in wanted.items():
            if p in targets:all_plans.setdefault(p,[]).append((t,q))
    return shared_slot_ledger(all_plans,orders_at,max_orders)


def seller_choice_rank(info):
    """Return active admission plus deterministic rank for one optimizer report."""
    forced=bool(info.get('forced_feasibility',False))
    accepted=bool(info.get('accepted',float(info.get('worst_relative_gain',0.0))>0))
    score=float(info.get('acceptance_score',info.get('worst_relative_gain',0.0)))
    return forced or accepted,(forced,score)


def event_aware_horizon(now, last, route, targets, shops, config):
    """Bound SELL lookahead to represented public market-service events.

    The inherited eight-turn window is the baseline.  Extension cannot cross
    the current day, terminal boundary, represented controller tape, or the
    first unresolved controller checkpoint.  A later product service date is
    useful only when that product has an executable market slot there.
    """
    represented_end=min(last,(now//24+1)*24-1,max(now,len(route)-1))
    checkpoints=[checkpoint for checkpoint,*_ in parent.DECISIONS
                 if now<checkpoint<=represented_end]
    if checkpoints:
        represented_end=min(represented_end,min(checkpoints)-1)
    baseline_end=min(now+HORIZON,represented_end)
    max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))
    service_dates={}
    for item in sorted(targets):
        for date in range(baseline_end+1,represented_end+1):
            if not absorption(item,date-1,shops,config):
                continue
            orders=route[date].get('market',[]) if date<len(route) else []
            prefix=(orders if isinstance(orders,list) else [])[:max_orders]
            has_slot=len(prefix)<max_orders
            has_item_slot=any(
                o and len(o)>2 and o[0]=='SELL' and o[1]==item
                for o in prefix)
            if has_slot or has_item_slot:
                service_dates[item]=date
                break
    end=max([baseline_end,*service_dates.values()])
    return end,{'baseline_end':baseline_end,'hard_end':represented_end,
                'service_dates':service_dates,'unit_event':None,
                'extended':end>baseline_end}


def apply_represented_market(farm, private, orders, size, max_orders):
    """Apply one represented market stage to copied own physical state.

    Current-step post-unit state is pre-market.  HIRE, SELL, and product/animal
    buys must land before later unit stages, matching receipt_profile's current
    then future market transition.
    """
    queue=orders if isinstance(orders,list) else []
    for order in queue[:max(1,int(max_orders))]:
        if not order:
            continue
        if order[0]=='SELL' and len(order)>2:
            private['shed'][order[1]]=max(
                0,private['shed'].get(order[1],0)-max(0,int(order[2])))
        elif order[0] in ('BUY_PRODUCT','BUY_ANIMAL') and len(order)>2:
            private['shed'][order[1]]=private['shed'].get(order[1],0)+max(0,int(order[2]))
        elif order[0]=='HIRE':
            farm['hands'].append(m._spawn_hand(farm,size))
            private['inventories'].append({})


def represented_shed_event(now, baseline_end, hard_end, route, farm, private, config,
                           current_market=None):
    """Return the first represented post-baseline unit stage that adds shed load.

    HARVEST alone only creates carried inventory, so it is not an extension
    trigger.  We execute the unchanged represented tape on copied public/private
    own state and trigger only when DROP or shed-PLACE (or another exact unit
    sequence) actually increases requested shed occupancy before market.  The
    oversized projection capacity matches receipt_profile: overflow pressure
    must remain visible rather than being clipped away by the real cap.
    """
    if hard_end<=baseline_end:
        return None
    f,p=copy.deepcopy(farm),copy.deepcopy(private)
    size=len(f['tiles'])
    market_limit=config.get('maxMarketOrdersPerTurn',10)
    apply_represented_market(f,p,current_market,size,market_limit)
    turns_per_day=int(config.get('turnsPerDay',24))
    for t in range(now+1,hard_end+1):
        action=route[t] if t<len(route) else parent.PASS
        before=sum(p['shed'].values())
        acts=[action.get('farmer',['PASS']),*action.get('hands',[])]
        for i,a in enumerate(acts):
            m._apply_unit_action(
                f,p,i,a,size,t//turns_per_day,turns_per_day,10**6)
        after=sum(p['shed'].values())
        if t>baseline_end and after>before:
            return t
        apply_represented_market(f,p,action.get('market',[]),size,market_limit)
    return None


def product_event_dates(item, now, end, shops, config):
    """Executable SELL dates use only this product's exact public absorption."""
    dates=[now]+[t for t in range(now+1,end+1)
                 if absorption(item,t-1,shops,config)]
    if len(dates)>3:
        dates=dates[:2]+dates[-1:]
    if dates[-1]!=end:
        dates.append(end)
    return sorted(set(dates))


class FrozenSelected(SellScheduler):
    def transform(self, obs, config, base):
        config=dict(config or {});now=int(obs['step']);last=int(config.get('episodeSteps',720))-2
        self.observe(obs)
        exec_pace_state=getattr(self,'exec_pace_state',None)
        if exec_pace_state is not None:exec_pace_state.note_prices(obs)
        farm,private=post_units(obs,base,config)
        if (getattr(self, 'capture_post_units', False)
                or (getattr(self, 'capture_operating_stock', False)
                    and any(o and len(o) > 2 and o[0] == 'SELL'
                            and o[1] in ('FERTILIZER', 'WHEAT')
                            for o in base.get('market', [])))):
            self.selected_post_units = (copy.deepcopy(farm), copy.deepcopy(private))
            self.selected_post_units_binding = (
                now, int(obs['player']), copy.deepcopy(base['farmer']),
                copy.deepcopy(base.get('hands', [])))
        shed=private['shed'];self.diagnostics={'step':now,'evaluations':[]}
        # Operating WHEAT/FERTILIZER and animal stock remain baseline-controlled.
        if now==last:
            out=copy.deepcopy(base)
            out['market']=parent._terminal_settlement(shed,obs['market']['prices'],out['market'])
            self.pending={};self.previous=seller_public_observation(obs);return out
        baseline_q={}
        for o in _engine_market_prefix(base,config):
            if o and o[0]=='SELL' and len(o)>2 and o[1] in PRODUCTS:
                baseline_q[o[1]]=baseline_q.get(o[1],0)+max(0,int(o[2]))
        targets={p:max(0,int(shed.get(p,0))) for p in PRODUCTS if shed.get(p,0)>0}
        current={p:min(targets[p],baseline_q.get(p,0)+sum(q for t,q in self.planned.get(p,[]) if t<=now)) for p in targets}
        route=self.controller.R[self.controller.cur]
        shops=obs.get('town',{}).get('unlocked_shops',[])
        end,horizon=event_aware_horizon(now,last,route,targets,shops,config)
        unit_event=(represented_shed_event(
            now,horizon['baseline_end'],horizon['hard_end'],route,farm,private,config,
            base.get('market',[]))
                    if targets else None)
        if unit_event is not None:
            end=max(end,unit_event)
        horizon['unit_event']=unit_event
        horizon['extended']=end>horizon['baseline_end']
        self.diagnostics['horizon']=horizon
        budget=self.cash_reserve(obs,config,base,end)
        best=None;options=[]
        for item,quantity in targets.items():
            if quantity<=0:continue
            item_end=max(horizon['baseline_end'],
                         horizon['service_dates'].get(item,horizon['baseline_end']),
                         horizon['unit_event'] or horizon['baseline_end'])
            dates=product_event_dates(item,now,item_end,shops,config)
            reference=[(now,current[item])]
            rem=quantity-current[item]
            pending_future=[(max(now,t),q) for t,q in self.planned.get(item,[]) if t>now]
            for t,q in pending_future:
                q=min(rem,q)
                if q>0:reference.append((min(t,item_end),q));rem-=q
            for t in range(now+1,item_end+1):
                action=route[t] if t<len(route) else parent.PASS
                for order in _engine_market_prefix(action,config):
                    if order and order[0]=='SELL' and order[1]==item and rem>0:
                        q=min(rem,max(0,int(order[2])));reference.append((t,q));rem-=q
            reference=tuple((t,sum(q for d,q in reference if d==t)) for t in sorted({t for t,_ in reference}))
            if self.mode=='naive':
                item_budget=self.cash_reserve(obs,config,base,item_end)
                take=min(quantity,6)
                if farm['money']<item_budget or now%24==23:take=max(take,current[item])
                if take!=current[item]:
                    info={'item':item,'quantity':quantity,'worst_relative_gain':0,
                          'plan':[(now,take),(min(last,now+1),quantity-take)],
                          'baseline_horizon_end':horizon['baseline_end'],
                          'horizon_end':item_end}
                    best=(item,tuple(info['plan']),info);break
                continue
            if len(dates)<2:continue
            item_budget=self.cash_reserve(obs,config,base,item_end)
            minimum,funding=funded_minimum_now(obs,config,base,farm,private,route,item_end,
                                                current,targets,item)
            funding['nominal_future_spend']=item_budget
            self.diagnostics.setdefault('funding_certificates',{})[item]=funding
            receipt_feasible=self.receipt_profile(obs,base,farm,private,item_end,item,config)
            def feasible(plan):
                for t,q in plan:
                    if q<=0:continue
                    market_action=base if t==now else (route[t] if t<len(route) else parent.PASS)
                    orders=_engine_market_prefix(market_action,config)
                    if len(orders)>=max(1,int(config.get('maxMarketOrdersPerTurn',10))):
                        offered=sum(max(0,int(o[2])) for o in orders if o and o[0]=='SELL' and o[1]==item)
                        if q>offered:return False
                return receipt_feasible(plan)
            plan,info=optimize_lot(item=item,quantity=quantity,inventory=int(obs['market']['inventory'][item]),params=obs['market'].get('params'),shops=shops,config=config,now=now,dates=dates,reference=reference,rival_quantity=self.rival_supply(obs,item),minimum_now=minimum,capacity_ok=feasible,last=last)
            info['baseline_horizon_end']=horizon['baseline_end'];info['horizon_end']=item_end
            exec_pace_apply=getattr(self,'exec_pace_apply',None)
            if exec_pace_apply is not None:
                plan,info=exec_pace_apply(exec_pace_state,item,reference,plan,info)
            self.diagnostics['evaluations'].append(info)
            eligible,rank=seller_choice_rank(info)
            if eligible:
                options.append((item,plan,info,reference))
                if best is None or rank>seller_choice_rank(best[2])[1]:best=(item,plan,info)
        # Compose ordinary per-product plans inside a shared resource bound.
        # A pair can use its executable current sales to fund fixed purchases;
        # a failed pair never changes the legacy single-product choice.
        if (len(options)>1
                and not getattr(self,'joint_producer_busy',False)
                and not (best and best[2].get('forced_feasibility',False))):
            ranked=sorted(options,key=lambda x:seller_choice_rank(x[2])[1],reverse=True)[:4]
            route=self.controller.R[self.controller.cur]
            prepaid_bound=(joint_resource_bound(obs,config,base,farm,private,route,end)
                           if farm['money']>=budget else None)
            def orders_at(step):
                return base['market'] if step==now else route[step].get('market',[]) if step<len(route) else []
            for left in range(len(ranked)):
                for right in range(left+1,len(ranked)):
                    pair=(ranked[left],ranked[right])
                    if any(entry[2].get('forced_feasibility',False) for entry in pair):continue
                    plans={entry[0]:entry[1] for entry in pair}
                    bound=prepaid_bound
                    if bound is None:
                        pair_current=dict(current)
                        for item,plan in plans.items():
                            pair_current[item]=dict(plan).get(now,0)
                        pair_market=materialize_sales(
                            base['market'],pair_current,shed,targets,
                            int(config.get('maxMarketOrdersPerTurn',10)))
                        pair_market,_=fund_same_turn_acquisition(
                            pair_market,farm,private,obs['market'],shops,config,now,
                            targets,lambda product:self.rival_supply(obs,product))
                        bound=joint_resource_bound(
                            obs,config,base,farm,private,route,end,
                            current_market=pair_market,
                            rival_quantity=lambda product:self.rival_supply(obs,product))
                    if bound is None:continue
                    # A future carried-goods commitment cannot be consumed by
                    # this new joint sale. Ordinary inputs remain producer-owned.
                    if any(a and len(a)>1 and a[0]=='PICKUP' and a[1] in plans
                           for t in range(now+1,bound['capital_end']+1)
                           if t<len(route)
                           for a in [route[t].get('farmer',['PASS']),*route[t].get('hands',[])]):continue
                    ledger=joint_queue_ledger(plans,current,self.planned,shed,bound,orders_at,
                                              now,bound['capital_end'],int(config.get('maxMarketOrdersPerTurn',10)))
                    metrics=joint_plan_metrics([entry[2] for entry in pair])
                    if ledger is None or metrics is None or metrics['worst_relative_gain']<=0:continue
                    minima=[min(float(s['relative_value'])-float(s['reference_relative_value'])
                                for s in entry[2]['scenarios'].values()) for entry in pair]
                    if min(minima)<=0:continue
                    independent=sum(minima)
                    joint={'items':[entry[0] for entry in pair],
                           'plans':{entry[0]:list(entry[1]) for entry in pair},
                           'slot_ledger':ledger,'resource_bound':bound,**metrics,
                           'named_worst_relative_gain':metrics['worst_relative_gain'],
                           'worst_relative_gain':independent,
                           'accepted':True,'acceptance_score':independent,
                           'acceptance_rule':'joint_strict'}
                    rank=(False,independent)
                    if best is None or rank>seller_choice_rank(best[2])[1]:
                        best=('__joint__',plans,joint)
        if best:
            item,plan,info=best
            selected_plans=plan if item=='__joint__' else {item:plan}
            for selected_item,selected_plan in selected_plans.items():
                current[selected_item]=dict(selected_plan).get(now,0)
                self.planned[selected_item]=[(t,q) for t,q in selected_plan if t>now and q>0]
            self.diagnostics['chosen']=info
        out=copy.deepcopy(base)
        # Preserve every original order index, including withheld SELL positions.
        # Extra stock is offered only after inherited orders unless moving an
        # already-selected sale earlier is required to fund a fixed acquisition.
        out['market']=materialize_sales(out['market'],current,shed,targets,
                                        int(config.get('maxMarketOrdersPerTurn',10)))
        out['market'],funding=fund_same_turn_acquisition(
            out['market'],farm,private,obs['market'],shops,config,now,targets,
            lambda product:self.rival_supply(obs,product))
        if funding is not None:self.diagnostics['same_turn_funding']=funding
        for item,q in targets.items():
            sold=sum(o[2] for o in _engine_market_prefix(out,config)
                     if o and o[0]=='SELL' and o[1]==item)
            self.pending[item]=max(0,q-sold)
            if not self.pending[item]:self.planned.pop(item,None)
        self.previous=seller_public_observation(obs)
        return out
