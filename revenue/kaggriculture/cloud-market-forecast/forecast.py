# SPDX-License-Identifier: MIT OR CC-BY-4.0
"""Visible crop supply scenarios at explicit market realization steps.

No hidden environment state, future shop labels, opponent private stock, persistent
replay lookup or action selection. Supply is conditional, never guaranteed sales.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import forecast_events as events
from forecast_market_mechanics import CROPS, PRODUCTS, SHOPS, TOWN_CENTER_PRODUCTS, market_price

SCENARIOS = {
    'no_future_work': {'water': False, 'fertilizer': False, 'harvest': False},
    'maintained_buffered': {'water': True, 'fertilizer': False, 'harvest': True},
    'fertilized_prompt': {'water': True, 'fertilizer': True, 'harvest': True},
}


def _config(configuration):
    cfg = configuration or {}
    get = cfg.get if isinstance(cfg, dict) else lambda k,d: getattr(cfg,k,d)
    return {'turns': max(1,int(get('turnsPerDay',24))),
            'end': int(get('episodeSteps',720))-2,
            'shop_interval': max(1,int(get('townShopSellInterval',4))),
            'center_interval': max(1,int(get('townCenterSellInterval',24)))}


def public_demand(observation, configuration, realization_step):
    """Exact demand from CURRENT shop copies, from now up to (excluding) sale step.

    A sale at step H sees consumption from [now,H), not H's subsequent town phase.
    Inventory may become negative: the engine never clamps town consumption.
    Future shop draws are unavailable and are deliberately not extrapolated.
    """
    cfg=_config(configuration); now=int(observation['step']); end=int(realization_step)
    if end < now or end > cfg['end']:
        raise ValueError('Realization step outside actionable horizon')
    counts={p:0 for p in PRODUCTS}
    copies=Counter(observation.get('town',{}).get('unlocked_shops',[]))
    def ticks(interval):
        return (end-1)//interval-(now-1)//interval if end>now else 0
    shop_ticks=ticks(cfg['shop_interval']); center_ticks=ticks(cfg['center_interval'])
    for shop,n in copies.items():
        goods=SHOPS[shop]
        for product in goods:
            counts[product] += n*shop_ticks*(2 if len(goods)==1 else 1)
    shop_units=dict(counts)
    center_units={p:center_ticks if p in TOWN_CENTER_PRODUCTS else 0 for p in PRODUCTS}
    for product in TOWN_CENTER_PRODUCTS:
        counts[product] += center_ticks
    return {'units':counts,'shop_units':shop_units,'center_units':center_units,'shop_copies':dict(copies),'shop_ticks':shop_ticks,
            'center_ticks':center_ticks,'interval':'[observation.step, realization_step)',
            'new_shop_draws_included':False}


def _tile_scenario(tile, x, y, farm, now, end, cfg, scenario, harvest_delay, contracts=None):
    """Conditional per-tile transitions; no joint labor/cash/shed reservation claim."""
    api=contracts or events
    def call(name,*args,**kwargs):
        function=api[name] if isinstance(api,dict) else getattr(api,name)
        return function(*args,**kwargs)
    plant=deepcopy(tile); crop=plant['crop']; cd=CROPS[crop]; turns=cfg['turns']
    schedule={e['refresh_step']:e for e in call('production_events',plant,now,turns,cfg['end']+2)}
    contract=call('harvest_contract',plant,now,turns,cfg['end']+2)
    fertilizer=call('fertilizer_contract',plant,now,turns,cfg['end']+2)
    pos=[farm['farmer'],*farm.get('hands',[])]
    first_reach=now+min(abs(p[0]-x)+abs(p[1]-y) for p in pos)
    size=len(farm['tiles']); centers=[(a,b) for a in (size//2-1,size//2) for b in (size//2-1,size//2)]
    return_steps=min(abs(x-a)+abs(y-b) for a,b in centers)
    sale_queue=defaultdict(int); snapshots={}; harvest_due=None
    generated=0; clipped=0; harvested=0; sold=0; decay_loss=0
    alive=True
    for step in range(now,end+1):
        day=step//turns
        # Quote is before this turn's town phase. Scenario sales on the same turn
        # are included as an inventory-after-supply quote, not exact order priority.
        sold += sale_queue.pop(step,0)
        if alive:
            # Existing observed watered/fertilized flags are retained. Future care
            # is a scenario assumption; no seed or fertilizer purchase is invented.
            if scenario['water'] and step>=first_reach and not plant['watered_today']:
                plant['watered_today']=True
                if not cd['ongoing'] and (cd['max_yield_day']+1)//2 <= day-plant['planted_day'] <= cd['max_yield_day']:
                    bonus=2 if scenario['fertilizer'] or plant['fertilized_until_day']>=day else 1
                    accepted=min(bonus,cd['max_yield']-plant['yield_units'])
                    plant['yield_units']+=accepted;generated+=accepted;clipped+=bonus-accepted
            held=plant['yield_units']; age=day-plant['planted_day']
            ripe=age>=cd['first_yield_day'] and held>0
            event=schedule.get(step)
            projected_bonus=2 if event and ((scenario['fertilizer'] and step>=first_reach) or event['fertilizer_already_covers']) and plant['watered_today'] else 1
            expires=plant['max_lifespan_step']>=0 and step>=plant['max_lifespan_step']
            trigger=(held>=cd['max_yield'] or expires or
                     (event is not None and held+projected_bonus>cd['max_yield']) or
                     (not cd['ongoing'] and age>=cd['max_yield_day']) or
                     (scenario['fertilizer'] and cd['ongoing']))
            if scenario['harvest'] and ripe and trigger:
                if harvest_due is None:
                    harvest_due=max(step,first_reach)+harvest_delay
                if step>=harvest_due:
                    window=call('liquidation_window',step,0,return_steps,turns_per_day=turns,episode_steps=cfg['end']+2)
                    if window['cash_before_terminal']:
                        harvested+=held; sale_queue[window['earliest_sale_step']]+=held
                        plant['yield_units']=0;harvest_due=None
                        if not cd['ongoing']:
                            alive=False
        snapshots[step]={'new_yield_units':generated,'capacity_clipped_units':clipped,
                         'harvested_units':harvested,'sale_units':sold,
                         'held_units':plant['yield_units'] if alive else 0,
                         'decay_loss_units':decay_loss,'alive':alive}
        # Same ordering as interpreter: market quote/sales, decay, then EOD refresh.
        if alive:
            mls=plant['max_lifespan_step']
            if mls>=0 and step>=mls and (step-mls)%2==0:
                plant['yield_units']-=1;decay_loss+=1
                if plant['yield_units']<=0: alive=False
        if alive and (step+1)%turns==0:
            watered=plant['watered_today']
            plant['consecutive_unwatered']=0 if watered else plant['consecutive_unwatered']+1
            plant['watered_today']=False
            if plant['consecutive_unwatered']>=2:
                alive=False
            elif step in schedule:
                event=schedule[step]
                bonus=2 if watered and ((scenario['fertilizer'] and step>=first_reach) or event['fertilizer_already_covers']) else 1
                accepted=min(bonus,cd['max_yield']-plant['yield_units'])
                plant['yield_units']+=accepted;generated+=accepted;clipped+=bonus-accepted
                if step==max(schedule):
                    # Only the actual final crop event starts decay, not the last
                    # queried horizon. ROWAN schedule spans the season, not end.
                    production_count=((day+1-plant['planted_day']-cd['first_yield_day'])//cd['interval'])+1
                    if production_count==cd['max_yield']:
                        plant['max_lifespan_step']=(day+2)*turns
    return snapshots, contract, fertilizer


def project_sale_timeline(initial_inventory, sales, horizons, quote, demand_before):
    """Conditional batches with floor-aware supply and same-unit joint quotes.

    sales maps action step to {seat: quantity}; each product's two seat batches
    are assumed aligned at one order slot, flattened across that seat's tiles.
    Actual cross-product order indices are unknown. This is an explicit scenario
    convention, not an opponent order prediction or a guarantee of revenues.
    demand_before(step) is cumulative exogenous town consumption before step.
    """
    inventory = initial_inventory
    previous_demand = 0
    sold = defaultdict(int); admitted = defaultdict(int); cash = defaultdict(int)
    snapshots = {}; timeline = []
    for step in sorted(set(sales) | set(horizons)):
        demand = demand_before(step)
        inventory -= demand - previous_demand
        previous_demand = demand
        quantities = sales.get(step, {})
        step_supply = defaultdict(int); step_cash = defaultdict(int)
        for unit in range(max(quantities.values(), default=0)):
            # Both seats quote before either commit; $1 pays but adds no supply.
            price = quote(inventory)
            active = [seat for seat, qty in quantities.items() if unit < qty]
            for seat in active:
                sold[seat] += 1; cash[seat] += price; step_cash[seat] += price
                if price > 1:
                    admitted[seat] += 1; step_supply[seat] += 1
            if price > 1:
                inventory += len(active)
        if quantities:
            timeline.append({'step': step, 'sale_units_by_seat': dict(quantities),
                             'market_supply_units_by_seat': dict(step_supply),
                             'conditional_cash_by_seat': dict(step_cash)})
        if step in horizons:
            snapshots[step] = {'inventory': inventory, 'sale_units_by_seat': dict(sold),
                               'market_supply_units_by_seat': dict(admitted),
                               'conditional_cash_by_seat': dict(cash)}
    return snapshots, timeline


def forecast_market(observation, configuration, horizons, *, contracts=None, buffered_harvest_delay=None):
    """Forecast current visible crops on BOTH farms at absolute sale-action steps.

    Returns per-product scenario ranges, not calibrated confidence intervals.
    No new planting, animals, private inventories, purchases or unknown shops are
    projected. FLORA can add its animal/net-trade estimates to the exposed crop
    inventory deltas and call market_price with the observation's exact params.
    """
    cfg=_config(configuration); now=int(observation['step'])
    horizons=sorted(set(horizons))
    if not horizons or any(not isinstance(h,int) or h<now or h>cfg['end'] for h in horizons):
        raise ValueError('Supply nonempty integer absolute sale steps in the actionable horizon')
    if buffered_harvest_delay is None: buffered_harvest_delay=max(1,cfg['turns']//2)
    if not isinstance(buffered_harvest_delay,int) or buffered_harvest_delay<0:
        raise ValueError('Harvest delay must be a nonnegative integer')
    end=max(horizons); totals={name:{h:{p:defaultdict(int) for p in PRODUCTS} for h in horizons} for name in SCENARIOS}
    def zero(): return {name:{h:{p:defaultdict(int) for p in PRODUCTS} for h in horizons} for name in SCENARIOS}
    by_side={'own':zero(),'opponent':zero()}
    sale_batches={name:{p:defaultdict(Counter) for p in PRODUCTS} for name in SCENARIOS}
    observed_held={'own':Counter(),'opponent':Counter()}
    witnesses=[]
    for seat,farm in enumerate(observation['farms']):
        for y,row in enumerate(farm['tiles']):
            for x,tile in enumerate(row):
                if not isinstance(tile,dict) or tile.get('kind')!='PLANT': continue
                crop=tile['crop'];side='own' if seat==observation['player'] else 'opponent'
                observed_held[side][crop]+=tile['yield_units']
                witness={'seat':seat,'x':x,'y':y,'crop':crop,'observed_held':tile['yield_units'],'scenarios':{}}
                for name,scenario in SCENARIOS.items():
                    delay=buffered_harvest_delay if name=='maintained_buffered' else 0
                    snapshots,contract,fertilizer=_tile_scenario(tile,x,y,farm,now,end,cfg,scenario,delay,contracts)
                    previous_sales = 0
                    for sale_step, snapshot in snapshots.items():
                        quantity = snapshot['sale_units'] - previous_sales
                        if quantity:
                            sale_batches[name][crop][sale_step][seat] += quantity
                        previous_sales = snapshot['sale_units']
                    witness['harvest_contract']=contract;witness['fertilizer_contract']=fertilizer
                    witness['scenarios'][name]={str(h):snapshots[h] for h in horizons}
                    for h in horizons:
                        for key,value in snapshots[h].items():
                            if key!='alive':
                                totals[name][h][crop][key]+=value
                                by_side[side][name][h][crop][key]+=value
                witnesses.append(witness)
    # Price-dependent supply must be replayed at its sale time, not inferred
    # from cumulative sale counts at a later requested horizon.
    demand_cache={}
    def demand_at(step):
        if step not in demand_cache:
            demand_cache[step]=public_demand(observation,configuration,step)
        return demand_cache[step]
    projected={name:{} for name in SCENARIOS}; sale_timeline={name:{} for name in SCENARIOS}
    for name in SCENARIOS:
        for product in PRODUCTS:
            projected[name][product], sale_timeline[name][product] = project_sale_timeline(
                observation['market']['inventory'][product], sale_batches[name][product], horizons,
                lambda inventory, p=product: market_price(p,inventory,observation['market'].get('params')),
                lambda step, p=product: demand_at(step)['units'][p])
    frames=[]
    for h in horizons:
        demand=public_demand(observation,configuration,h)
        products={}
        for product in PRODUCTS:
            rows={}
            for name in SCENARIOS:
                values=dict(totals[name][h][product]); sold=values.get('sale_units',0)
                projection=projected[name][product][h]
                supply=sum(projection['market_supply_units_by_seat'].values())
                inventory=projection['inventory']
                for side in ('own','opponent'):
                    seats=[seat for seat in range(len(observation['farms']))
                           if (seat==observation['player']) == (side=='own')]
                    by_side[side][name][h][product]['market_supply_units']=sum(
                        projection['market_supply_units_by_seat'].get(seat,0) for seat in seats)
                rows[name]={**values,'conditional_crop_sale_units':sold,
                            'conditional_crop_market_supply_units':supply,
                            'floor_sale_units':sold-supply,
                            'inventory_delta':supply-demand['units'][product],
                            'inventory':inventory,'price':market_price(product,inventory,observation['market'].get('params'))}
            prices=[row['price'] for row in rows.values()]
            own={name:dict(by_side['own'][name][h][product]) for name in SCENARIOS}
            opponent={name:dict(by_side['opponent'][name][h][product]) for name in SCENARIOS}
            products[product]={'current_price':observation['market']['prices'][product],
                               'known_shop_demand_units':demand['units'][product],
                               'shop_copy_demand':demand['shop_units'][product],
                               'town_center_demand':demand['center_units'][product],
                               'own_supply':{'observed_held':observed_held['own'][product],'guaranteed':0,
                                   'care_possible':max(s.get('new_yield_units',0) for s in own.values()),
                                   'harvest_possible':max(s.get('harvested_units',0) for s in own.values()),
                                   'sale_possible':max(s.get('sale_units',0) for s in own.values()),'conditional':own},
                               'opponent_public_supply':{'observed_held':observed_held['opponent'][product],'conditional':opponent},
                               'price_scenarios':{'floor':min(prices),'base':rows['maintained_buffered']['price'],'ceiling':max(prices)},
                               'guaranteed_future_crop_sales':0,'scenarios':rows,
                               'scenario_price_range':[min(prices),max(prices)]}
        frames.append({'realization_step':h,'realization_day':h//cfg['turns'],'demand':demand,'products':products})
    return {'schema':2,'observation_step':now,'scope':'visible existing crops on both farms; known shop copies only',
            'frames':frames,'crop_witnesses':witnesses,'conditional_sale_timeline':sale_timeline,
            'assumptions':{'new_shop_draws':False,'hidden_seed':False,'new_planting':False,'animal_supply':False,
                'private_inventory_sales':False,'future_market_buys':False,
                'joint_labor_cash_feed_shed_capacity_reserved':False,
                'buffered_harvest_delay_steps':buffered_harvest_delay,
                'scenario_sales_conditional_on_transport_and_shed_space':True,
                'floor_sales_add_market_supply':False,
                'same_unit_quotes':'both seats use the same pre-commit inventory',
                'order_alignment':'one aligned batch per product and step; actual cross-product slots unknown',
                'quote':'after scenario crop supply at H, before town consumption at H; not exact trade-order revenue',
                'no_future_work':'no further care/harvest/sale; observed flags still apply',
                'maintained_buffered':'daily water, existing fertilizer coverage only; harvest after configured service delay',
                'fertilized_prompt':'daily water and fertilizer coverage assumed available; earliest conditional harvesting',
                'ranges':'scenario envelope only, not guaranteed bounds under omitted animal/private-stock trades'}}
