# SPDX-License-Identifier: Apache-2.0
"""Pure market optimizer extracted from frozen scheduler32c8610c; no parent code.

The selected standalone scheduler is preserved separately.
"""
from functools import lru_cache
from pathlib import Path
import importlib.util
import json
import mechanics as m

_spec = importlib.util.spec_from_file_location("selected_sell_receipts", Path(__file__).resolve().parent / "reference/decision/decision.py")
receipt_math = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(receipt_math)

def absorption(item, step, shops, config):
    n=0
    shop_interval=max(1,int(config.get('townShopSellInterval',4)))
    center_interval=max(1,int(config.get('townCenterSellInterval',24)))
    if step % shop_interval==0:
        for shop in shops:
            products=m.SHOPS.get(shop,())
            if item in products:n+=2 if len(products)==1 else 1
    if item!='FERTILIZER' and step % center_interval==0:n+=1
    return n

class MarketPath:
    """Exact rounded, floor-admitting paired units for conditional sale streams."""
    def __init__(self, item, inventory, params, shops, config, now, end):
        self.item,self.inventory,self.params=item,inventory,params
        self.shops,self.config,self.now,self.end=shops,config,now,end
        self.quote=lru_cache(maxsize=2048)(lambda inv:m.market_price(item,inv,params))
        self.single=lru_cache(maxsize=8192)(self._single)
        self.joint=lru_cache(maxsize=8192)(self._joint)

    def _single(self, inv, quantity):
        # Reuse SORREL's repaired receipt interface; admission is derived from
        # the same exact quote condition, not raw quantity added as supply.
        cash=receipt_math.sale_receipts([{'step':0,'quantity':quantity,'product':self.item}],lambda _p,_t:inv,lambda _p,i:self.quote(int(i)),0)
        initial=inv
        for _ in range(quantity):
            if self.quote(inv)>1:inv+=1
            else:break
        return int(cash),inv

    def _joint(self, inv, own, rival, alignment):
        if alignment=='after':
            cash,inv=self.single(inv,own)
            other,inv=self.single(inv,rival)
            return cash,other,inv
        if alignment=='before':
            other,inv=self.single(inv,rival)
            cash,inv=self.single(inv,own)
            return cash,other,inv
        cash=other=0
        for k in range(max(own,rival)):
            price=self.quote(inv)
            a=k<own;b=k<rival
            cash+=price*a;other+=price*b
            if price>1:inv+=int(a)+int(b)
        return cash,other,inv

    def score(self, plan, quantity, rival, alignment, terminal=False):
        inv=self.inventory;own_cash=other_cash=0;sold=0
        orders=dict(plan)
        steps=range(self.now,self.end+1)
        consumed=()
        if steps:
            rival_orders=dict(rival) if isinstance(rival,tuple) else {self.now:rival}
            # A model scores many plans against the same dated town consumption.
            # Key the observable inputs, so edits between calls invalidate the
            # schedule rather than inheriting stale shops or configuration.
            context=(self.item,self.now,self.end,tuple(self.shops),
                     self.config.get('townShopSellInterval',4),
                     self.config.get('townCenterSellInterval',24))
            if getattr(self,'_score_context',None)!=context:
                consumed=tuple(absorption(self.item,t,self.shops,self.config)
                               for t in steps)
                self._score_context=context
                self._score_consumed=consumed
            else:
                consumed=self._score_consumed
        for step,used in zip(steps,consumed):
            q=min(quantity-sold,max(0,orders.get(step,0)))
            r=rival_orders.get(step,0)
            a,b,inv=self.joint(inv,q,r,alignment)
            own_cash+=a;other_cash+=b;sold+=q
            inv-=used
        remaining=quantity-sold
        # Artificial planning boundaries retain inventory at a conservative
        # continuation value. No mandatory horizon-end liquidation constraint.
        carry=0.0
        if remaining and not terminal:
            carry=float(self.single(inv,remaining)[0])
        return own_cash+carry-other_cash, own_cash,other_cash,remaining


def _market_path_key(item, inventory, params, shops, config, now, end):
    """Return an immutable projection identity, or None when inputs are exotic.

    The cache is intentionally scoped to values MarketPath actually observes.
    JSON-like market parameters and the relevant global shop/product membership
    are snapshotted so caller or mechanics mutation cannot reuse stale work.
    Unsupported/custom objects simply take the original uncached path.
    """
    try:
        params_blob=json.dumps(params,sort_keys=True,separators=(',',':'),allow_nan=False)
        shops_key=tuple(shops)
        shop_products=tuple((shop,tuple(m.SHOPS.get(shop,()))) for shop in shops_key)
        hash((shops_key,shop_products))
        shop_interval=max(1,int(config.get('townShopSellInterval',4)))
        center_interval=max(1,int(config.get('townCenterSellInterval',24)))
        return (item,int(inventory),params_blob,shops_key,shop_products,shop_interval,
                center_interval,int(now),int(end))
    except (TypeError,ValueError,OverflowError):
        return None


@lru_cache(maxsize=32)
def _cached_market_path(key):
    item,inventory,params_blob,shops,_shop_products,shop_interval,center_interval,now,end=key
    # Reconstruct from the canonical key instead of retaining mutable caller
    # dictionaries/lists.  The shop signature is identity-only: score() reads
    # the same current mechanics mapping that produced this key.
    params=json.loads(params_blob)
    config={'townShopSellInterval':shop_interval,
            'townCenterSellInterval':center_interval}
    return MarketPath(item,inventory,params,shops,config,now,end)


def shared_market_path(item, inventory, params, shops, config, now, end):
    """Reuse exact market projections across optimizer calls when inputs match."""
    key=_market_path_key(item,inventory,params,shops,config,now,end)
    if key is None:
        return MarketPath(item,inventory,params,shops,config,now,end)
    return _cached_market_path(key)


def clear_shared_market_path_cache():
    """Clear bounded shared projections (primarily for deterministic tests)."""
    _cached_market_path.cache_clear()


def shared_market_path_cache_info():
    """Expose cache counters without exposing mutable cached objects."""
    return _cached_market_path.cache_info()


def joint_plan_metrics(infos):
    """Sum comparable per-product scenario deltas without double-counting slots."""
    if not infos:
        return None
    names=tuple(infos[0].get('scenarios',{}))
    if not names or any(tuple(info.get('scenarios',{}))!=names for info in infos[1:]):
        return None
    deltas={}
    for name in names:
        deltas[name]=sum(float(info['scenarios'][name]['relative_value'])-
                         float(info['scenarios'][name]['reference_relative_value'])
                         for info in infos)
    return {'scenario_deltas':deltas,'worst_relative_gain':min(deltas.values()),
            'total_relative_gain':sum(deltas.values())}


def shared_slot_ledger(plans, orders_by_step, max_orders):
    """Return an exact per-date queue ledger, or None when additions clip."""
    dates=sorted({t for plan in plans.values() for t,_ in plan})
    ledger={}
    for step in dates:
        orders=list(orders_by_step(step) or [])
        extras=[]
        for item,plan in sorted(plans.items()):
            wanted=max(0,int(dict(plan).get(step,0)))
            offered=sum(max(0,int(o[2])) for o in orders
                        if o and len(o)>2 and o[0]=='SELL' and o[1]==item)
            if wanted>offered:
                extras.append(item)
        ledger[step]={'inherited_slots':len(orders),'extra_items':extras,
                      'total_slots':len(orders)+len(extras)}
        if ledger[step]['total_slots']>int(max_orders):
            return None
    return ledger


def _acceptance_rule(config):
    rule=str((config or {}).get('sellAcceptanceRule','strict')).strip().lower()
    return rule if rule in ('strict','expected_downside','minimax_regret') else 'strict'


def _scenario_weights(names, config):
    raw=(config or {}).get('sellScenarioWeights',{})
    weights=[]
    if isinstance(raw,dict):
        for name in names:
            try:weights.append(max(0.0,float(raw.get(name,0.0))))
            except (TypeError,ValueError):weights.append(0.0)
    if len(weights)!=len(names) or sum(weights)<=0:
        weights=[1.0 for _ in names]
    total=sum(weights)
    return {name:weight/total for name,weight in zip(names,weights)}


def _weighted_gain(deltas, names, weights):
    return sum(float(delta)*float(weights[name]) for name,delta in zip(names,deltas))


def optimize_lot(*,item,quantity,inventory,params,shops,config,now,dates,
                 reference,rival_quantity,minimum_now=0,capacity_ok=None,last=718):
    end=dates[-1]
    model=shared_market_path(item,inventory,params,shops,config,now,end)
    scenarios=[('no_rival',0,'paired'),('observed_paired',rival_quantity,'paired'),('observed_later_order',rival_quantity,'after')]
    if end>now:
        scenarios.append(('observed_next_turn',((now+1,rival_quantity),),'paired'))
    if end>now+2:
        scenarios.append(('observed_before_delayed_batch',((end-1,rival_quantity),),'paired'))
    baseline=[model.score(reference,quantity,r,a,end==last) for _,r,a in scenarios]
    reference_feasible=(capacity_ok(reference) if capacity_ok else True) and dict(reference).get(now,0)>=minimum_now
    best_plan=tuple(reference);best_key=(0.0,0.0,0.0) if reference_feasible else (-float('inf'),-float('inf'),0.0);best_scores=baseline
    found_feasible=reference_feasible
    candidates={tuple(reference)}
    future=dates[1:]
    for first in range(minimum_now,quantity+1):
        remaining=quantity-first
        candidates.add(((now,first),))  # Explicit carry beyond short horizon.
        for date in future:
            candidates.add(((now,first),(date,remaining)))
        if len(future)>=2:
            for share in (1,2,3):
                a=remaining*share//4
                candidates.add(((now,first),(future[0],a),(future[-1],remaining-a)))
    # Enumerates every legal first quantity and a bounded later-tranche family.
    rule=_acceptance_rule(config)
    names=[name for name,_,_ in scenarios]
    weights=_scenario_weights(names,config)
    try:downside_bound=max(0.0,float((config or {}).get('sellDownsideBound',0.0)))
    except (TypeError,ValueError):downside_bound=0.0
    accepted=False
    acceptance_score=0.0
    weighted_expected_gain=0.0
    reference_max_regret=None
    max_regret=None
    scenario_regrets=None

    # Preserve the exact incumbent strict-dominance behavior and its cheap
    # no-rival prune. Alternative E18 rules deliberately evaluate the same
    # feasible candidate family without this economic prune.
    if reference_feasible and rule=='strict':
        for plan in sorted(candidates):
            if sum(q for _,q in plan)>quantity:continue
            if dict(plan).get(now,0)<minimum_now:continue
            first_score=model.score(plan,quantity,0,'paired',end==last)
            if first_score[0]-baseline[0][0] <= 0:
                continue
            if capacity_ok and not capacity_ok(plan):continue
            scores=[first_score]
            competitive=True
            for (_,r,a),b in zip(scenarios[1:],baseline[1:]):
                score=model.score(plan,quantity,r,a,end==last)
                if score[0]-b[0] <= 0:
                    competitive=False
                    break
                scores.append(score)
            if not competitive:continue
            deltas=[s[0]-b[0] for s,b in zip(scores,baseline)]
            key=(round(min(deltas),8),round(sum(deltas),8),float(dict(plan).get(now,0)))
            if key[0]>0 and key>best_key:
                best_key,best_plan,best_scores=key,plan,scores
                found_feasible=True
        accepted=best_key[0]>0
        acceptance_score=best_key[0] if accepted else 0.0
        chosen_deltas=[s[0]-b[0] for s,b in zip(best_scores,baseline)]
        weighted_expected_gain=_weighted_gain(chosen_deltas,names,weights)
    elif not reference_feasible:
        # Forced feasibility remains a physical rescue path, independent of
        # E18's economic comparison policy.
        for plan in sorted(candidates):
            if sum(q for _,q in plan)>quantity:continue
            if dict(plan).get(now,0)<minimum_now:continue
            if capacity_ok and not capacity_ok(plan):continue
            scores=[model.score(plan,quantity,r,a,end==last) for _,r,a in scenarios]
            deltas=[s[0]-b[0] for s,b in zip(scores,baseline)]
            key=(round(min(deltas),8),round(sum(deltas),8),float(dict(plan).get(now,0)))
            if key>best_key:
                best_key,best_plan,best_scores=key,plan,scores
                found_feasible=True
        chosen_deltas=[s[0]-b[0] for s,b in zip(best_scores,baseline)]
        acceptance_score=best_key[0] if found_feasible else 0.0
        weighted_expected_gain=_weighted_gain(chosen_deltas,names,weights) if found_feasible else 0.0
    else:
        records=[]
        for plan in sorted(candidates):
            if sum(q for _,q in plan)>quantity:continue
            if dict(plan).get(now,0)<minimum_now:continue
            if plan==tuple(reference):
                scores=baseline
            else:
                if capacity_ok and not capacity_ok(plan):continue
                scores=[model.score(plan,quantity,r,a,end==last) for _,r,a in scenarios]
            deltas=[s[0]-b[0] for s,b in zip(scores,baseline)]
            records.append({'plan':plan,'scores':scores,'deltas':deltas,
                            'expected':_weighted_gain(deltas,names,weights)})
        if rule=='expected_downside':
            best_alt=None
            for rec in records:
                if rec['plan']==tuple(reference):continue
                worst=min(rec['deltas'])
                if rec['expected']<=0 or worst < -downside_bound:continue
                key=(round(rec['expected'],8),round(worst,8),
                     round(sum(rec['deltas']),8),float(dict(rec['plan']).get(now,0)))
                if best_alt is None or key>best_alt[0]:
                    best_alt=(key,rec)
            if best_alt is not None:
                key,rec=best_alt
                best_plan,best_scores=rec['plan'],rec['scores']
                best_key=(round(min(rec['deltas']),8),round(sum(rec['deltas']),8),
                          float(dict(rec['plan']).get(now,0)))
                accepted=True;found_feasible=True
                acceptance_score=key[0];weighted_expected_gain=rec['expected']
        else:
            scenario_best=[max(rec['deltas'][i] for rec in records)
                           for i in range(len(scenarios))]
            reference_max_regret=max(scenario_best) if scenario_best else 0.0
            best_alt=None
            for rec in records:
                regrets=[best-rec['deltas'][i] for i,best in enumerate(scenario_best)]
                rec_max=max(regrets) if regrets else 0.0
                improvement=reference_max_regret-rec_max
                if rec['plan']==tuple(reference) or improvement<=0:continue
                key=(round(improvement,8),round(rec['expected'],8),
                     round(min(rec['deltas']),8),float(dict(rec['plan']).get(now,0)))
                if best_alt is None or key>best_alt[0]:
                    best_alt=(key,rec,regrets,rec_max)
            if best_alt is not None:
                key,rec,regrets,rec_max=best_alt
                best_plan,best_scores=rec['plan'],rec['scores']
                best_key=(round(min(rec['deltas']),8),round(sum(rec['deltas']),8),
                          float(dict(rec['plan']).get(now,0)))
                accepted=True;found_feasible=True
                acceptance_score=key[0];weighted_expected_gain=rec['expected']
                max_regret=rec_max
                scenario_regrets={name:regret for name,regret in zip(names,regrets)}
            else:
                max_regret=reference_max_regret
                scenario_regrets={name:best for name,best in zip(names,scenario_best)}

    forced=not reference_feasible and found_feasible
    return best_plan,{'item':item,'quantity':quantity,'rival_scenario_quantity':rival_quantity,
        'reference':list(reference),'plan':list(best_plan),'minimum_now':minimum_now,
        'scenarios':{name:{'reference_relative_value':b[0],'relative_value':s[0],
                          'own_receipts':s[1],'rival_receipts':s[2],'carry_units':s[3]}
                     for (name,_,_),b,s in zip(scenarios,baseline,best_scores)},
        'worst_relative_gain':best_key[0] if found_feasible else 0.0,
        'forced_feasibility':forced,'feasible':found_feasible,'plans_evaluated':len(candidates),
        'acceptance_rule':rule,'accepted':accepted,'acceptance_score':acceptance_score,
        'scenario_weights':weights,'weighted_expected_gain':weighted_expected_gain,
        'downside_bound':downside_bound if rule=='expected_downside' else None,
        'reference_max_regret':reference_max_regret,'max_regret':max_regret,
        'scenario_regrets':scenario_regrets}
