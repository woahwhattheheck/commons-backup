# SPDX-License-Identifier: Apache-2.0
"""S03 deterministic branch-gated UCT over source-compatible route tails.

The live decision uses only public observation plus the active player's own private
packet. Opponent response is represented by named public-flow hypotheses; no
rival private inventory, hidden RNG seed, or replay suffix enters a score.
"""
from __future__ import annotations

import copy, hashlib, json, math, random, time
from dataclasses import dataclass, field
from typing import Any

DECISION_STEPS = (226, 360, 433)
SCENARIOS = ("incumbent", "visible_before", "adversarial_feasible")
PRODUCTS = ("WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER")
ANIMAL_PRODUCT = {"GOOSE":"EGG","COW":"MILK","SHEEP":"WOOL"}
SHED_ACCESS = {(4,4),(5,4),(4,5),(5,5)}


def _cfg(cfg,key,default):
    value=(cfg or {}).get(key,default)
    if isinstance(value,dict): value=value.get("default",default)
    return value


def prefix_compatible_routes(routes,current,step):
    if current not in routes:return ()
    base=routes[current]
    return tuple(sorted(k for k,rows in routes.items()
        if k!=current and len(rows)>step and len(base)>step
        and all(base[t]==rows[t] for t in range(step))))


def _stable_seed(obs,budget,current):
    me=int(obs.get("player",0)); farms=obs.get("farms") or []
    own=farms[me] if 0<=me<len(farms) else {}
    rival=farms[1-me] if len(farms)>1 else {}
    packet={"step":int(obs.get("step",0)),"player":me,"budget":int(budget),"current":current,
        "money":own.get("money"),"rival_money":rival.get("money"),
        "market":(obs.get("market") or {}).get("inventory"),
        "shops":(obs.get("town") or {}).get("unlocked_shops"),
        "own_positions":[own.get("farmer"),*(own.get("hands") or [])],
        "rival_positions":[rival.get("farmer"),*(rival.get("hands") or [])]}
    digest=hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(",",":"),default=str).encode()).digest()
    return int.from_bytes(digest[:8],"big")


def _visible_rival_supply(obs,item):
    me=int(obs.get("player",0)); farms=obs.get("farms") or []
    if len(farms)<2:return 0
    rival=farms[1-me]; total=0
    for row in rival.get("tiles") or []:
        for tile in row:
            if not isinstance(tile,dict):continue
            product=tile.get("crop") if tile.get("kind")=="PLANT" else ANIMAL_PRODUCT.get(tile.get("animal"))
            if product==item:total+=max(0,int(tile.get("yield_units",0)))
    return min(100,total)


def _market_price(mechanics,item,inventory,params):
    return int(mechanics.market_price(item,int(inventory),params))


def _units(row):return [row.get("farmer") or ["PASS"],*(row.get("hands") or [])]


def _positions(farm):return [tuple(farm.get("farmer") or ()),*map(tuple,farm.get("hands") or [])]


def _current_unit_feasible(row,farm,private):
    invs=private.get("inventories") or []; positions=_positions(farm); seeds=private.get("seeds") or {}; shed=private.get("shed") or {}
    for i,a in enumerate(_units(row)):
        if not a:continue
        op=a[0]; inv=invs[i] if i<len(invs) else {}; pos=positions[i] if i<len(positions) else ()
        if op=="PICKUP":
            if len(a)<2 or pos not in SHED_ACCESS:return False,"pickup_not_at_shed"
            item=a[1]; q=max(0,int(a[2] if len(a)>2 else 1))
            if q<=0 or int(shed.get(item,0))<q:return False,"pickup_unavailable"
        elif op=="DROP":
            if pos not in SHED_ACCESS or not any(int(v)>0 for v in inv.values()):return False,"drop_not_executable"
        elif op=="FEED" and int(inv.get("WHEAT",0))<1:return False,"feed_without_wheat"
        elif op=="FERTILIZE" and int(inv.get("FERTILIZER",0))<1:return False,"fertilize_without_input"
        elif op=="PLANT":
            crop=a[1] if len(a)>1 else None
            if not crop or int(seeds.get(crop,0))<1:return False,"plant_without_seed"
    return True,"ok"


def _future_obligation_penalty(route,step,private,horizon=12):
    """One-sided own-route obligation certificate. Future requested receipts get no credit."""
    stock={k:max(0,int(v)) for k,v in (private.get("shed") or {}).items()}
    for inv in private.get("inventories") or []:
        for k,v in inv.items():stock[k]=stock.get(k,0)+max(0,int(v))
    seeds={k:max(0,int(v)) for k,v in (private.get("seeds") or {}).items()}
    need={}; seed_need={}
    end=min(len(route),step+1+int(horizon))
    for t in range(step+1,end):
        for a in _units(route[t]):
            if not a:continue
            if a[0]=="FEED":need["WHEAT"]=need.get("WHEAT",0)+1
            elif a[0]=="FERTILIZE":need["FERTILIZER"]=need.get("FERTILIZER",0)+1
            elif a[0]=="PLANT" and len(a)>1:seed_need[a[1]]=seed_need.get(a[1],0)+1
    missing=sum(max(0,n-stock.get(k,0)) for k,n in need.items())+sum(max(0,n-seeds.get(k,0)) for k,n in seed_need.items())
    return missing


def _scenario_supply(obs,item,scenario):
    visible=_visible_rival_supply(obs,item)
    if scenario=="incumbent":return 0
    if scenario=="visible_before":return visible
    # Pessimistic but public-bounded: one legal market slot, never private stock.
    return min(100,max(visible,32))


def leaf_value(route_id,routes,step,obs,cfg,mechanics,scenario,horizon=12):
    """Realizable current-turn economics minus hard own-obligation infeasibility."""
    row=routes[route_id][step];me=int(obs.get("player",0));farm=copy.deepcopy(obs["farms"][me]);private=copy.deepcopy(obs["private"])
    ok,reason=_current_unit_feasible(row,farm,private)
    if not ok:return -1e15,{"feasible":False,"reason":reason}
    market=obs.get("market") or {};inventory={k:int(v) for k,v in (market.get("inventory") or {}).items()};params=market.get("params")
    money=float(farm.get("money",0));shed={k:max(0,int(v)) for k,v in (private.get("shed") or {}).items()};hires=max(0,int(farm.get("hires_today",len(farm.get("hands") or []))))
    land=max(0,len(farm.get("unlocked_quadrants") or ["NW"])-1);cap=int(_cfg(cfg,"shedCapacity",100)); slots=int(_cfg(cfg,"maxMarketOrdersPerTurn",10)); mult=int(_cfg(cfg,"farmHandCostMult",1))
    receipts=spend=0.0
    for order in (row.get("market") or [])[:slots]:
        if not order:continue
        op=order[0]
        if op=="SELL" and len(order)>2 and order[1] in PRODUCTS:
            item=order[1];q=min(max(0,int(order[2])),shed.get(item,0));inv=inventory.get(item,0)+_scenario_supply(obs,item,scenario)
            cash=0
            for j in range(q):cash+=_market_price(mechanics,item,inv+j,params)
            money+=cash;receipts+=cash;shed[item]=shed.get(item,0)-q;inventory[item]=inv+q
        elif op=="HIRE":
            cost=float(mechanics._hire_cost(hires,mult));
            if money<cost:return -1e15,{"feasible":False,"reason":"hire_unfunded","cost":cost,"money":money}
            money-=cost;spend+=cost;hires+=1
        elif op=="BUY_LAND":
            prices=getattr(mechanics,"LAND_PRICES",())
            cost=float(prices[land]) if land<len(prices) else 0.0
            if money<cost:return -1e15,{"feasible":False,"reason":"land_unfunded"}
            money-=cost;spend+=cost;land+=1
        elif op in ("BUY_SEED","BUY_ANIMAL") and len(order)>2:
            item=order[1];q=max(0,int(order[2]));table=mechanics.CROPS if op=="BUY_SEED" else mechanics.ANIMALS;key="seed" if op=="BUY_SEED" else "cost";cost=float(q*table[item][key])
            if money<cost:return -1e15,{"feasible":False,"reason":"fixed_buy_unfunded","op":op}
            if op=="BUY_ANIMAL" and sum(shed.values())+q>cap:return -1e15,{"feasible":False,"reason":"shed_capacity"}
            money-=cost;spend+=cost
        elif op=="BUY_PRODUCT" and len(order)>2:
            item=order[1];q=max(0,int(order[2]));inv=inventory.get(item,0)-_scenario_supply(obs,item,scenario)
            cost=0
            for j in range(q):cost+=_market_price(mechanics,item,inv-j-1,params)
            if money<cost:return -1e15,{"feasible":False,"reason":"product_buy_unfunded"}
            if sum(shed.values())+q>cap:return -1e15,{"feasible":False,"reason":"shed_capacity"}
            money-=cost;spend+=cost
    missing=_future_obligation_penalty(routes[route_id],step,private,horizon)
    if missing:return -1e15,{"feasible":False,"reason":"future_owned_obligation_shortfall","missing":missing}
    # Keep the score cash-realizable. A tiny canonical-distance regularizer is applied by UCT, not here.
    return float(money),{"feasible":True,"money":money,"receipts":receipts,"spend":spend,"scenario":scenario}

@dataclass
class Arm:
    route:str
    visits:int=0
    total:float=0.0
    worst:float=float("inf")
    samples:list[float]=field(default_factory=list)
    by_scenario:dict[str,list[float]]=field(default_factory=dict)
    def observe(self,value,scenario):
        self.visits+=1;self.total+=value;self.worst=min(self.worst,value);self.samples.append(value);self.by_scenario.setdefault(scenario,[]).append(value)
    @property
    def mean(self):return self.total/self.visits if self.visits else -1e18


def run_uct(routes,current,step,obs,cfg,mechanics,simulations=64,budget_ms=40.0,horizon=12):
    alternatives=prefix_compatible_routes(routes,current,step);candidates=(current,*alternatives)
    if len(candidates)<2:return {"triggered":False,"reason":"single_candidate","winner":current,"routes":list(candidates),"elapsed_ms":0.0}
    rng=random.Random(_stable_seed(obs,simulations,current));arms={r:Arm(r) for r in candidates};opened=[current];remaining=list(alternatives);start=time.perf_counter();completed=0;deadline=start+max(0,float(budget_ms))/1000.0
    scenario_counts={s:0 for s in SCENARIOS}
    while completed<int(simulations) and time.perf_counter()<deadline:
        # Progressive widening: k*sqrt(N) with deterministic route order.
        allowed=min(len(candidates),max(1,int(1.5*math.sqrt(completed+1))))
        while len(opened)<allowed and remaining:opened.append(remaining.pop(0))
        warm=[(r,s) for r in opened for s in SCENARIOS if s not in arms[r].by_scenario]
        if warm:
            route,scenario=warm[0]
        else:
            logn=math.log(max(2,completed+1))
            def ucb(r):
                a=arms[r];prior=0.05 if r==current else 0.0
                return a.mean + 1.25*math.sqrt(logn/a.visits)+prior
            route=max(opened,key=lambda r:(ucb(r),r==current,-candidates.index(r)))
            scenario=SCENARIOS[rng.randrange(len(SCENARIOS))]
        value,_=leaf_value(route,routes,step,obs,cfg,mechanics,scenario,horizon)
        arms[route].observe(value,scenario);scenario_counts[scenario]+=1;completed+=1
    rows=[]
    for r in candidates:
        a=arms[r];rows.append({"route":r,"visits":a.visits,"mean":a.mean if a.visits else None,"worst":a.worst if a.visits else None,"samples":len(a.samples),"scenarios":sorted(a.by_scenario)})
    # No route can promote without an observed adversarial sample. Worst-case then mean; ties retain current.
    eligible=[r for r in candidates if set(arms[r].by_scenario)==set(SCENARIOS) and arms[r].worst>-1e14]
    winner=current
    if eligible:
        winner=max(eligible,key=lambda r:(arms[r].worst,arms[r].mean,r==current,-candidates.index(r)))
    base=arms[current]
    changed=winner!=current and arms[winner].worst>base.worst and arms[winner].mean>base.mean
    if not changed:winner=current
    return {"triggered":True,"simulations_requested":int(simulations),"simulations_completed":completed,"budget_ms":float(budget_ms),"elapsed_ms":1000*(time.perf_counter()-start),"current":current,"winner":winner,"changed_recommendation":changed,"routes":list(candidates),"rows":rows,"scenario_counts":scenario_counts,"seed":_stable_seed(obs,simulations,current),"horizon":int(horizon)}
