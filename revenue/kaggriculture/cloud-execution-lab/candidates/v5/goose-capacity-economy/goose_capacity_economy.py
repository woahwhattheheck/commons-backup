# SPDX-License-Identifier: Apache-2.0
"""P02: one-extra-goose research treatment for exact production-v3."""
from __future__ import annotations
import copy
from collections import Counter
import r04_full_router as r04

CFG={"episodeSteps":720,"boardSize":10,"turnsPerDay":24,"shedCapacity":100,"maxMarketOrdersPerTurn":10}
GOOSE_COST=300
GOOSE_CAP=20
LAST_DAY=29
MIN_DAY=12
MAX_DAY=18
CASH_RESERVE=500
PAYBACK_MARGIN=100
WHEAT_BUFFER=10
STATE={}
telemetry=Counter()


def _cv(cfg,k):
    if isinstance(cfg,dict): return cfg.get(k)
    try: return getattr(cfg,k)
    except Exception: return None


def _cfg_ok(cfg):
    return all(type(_cv(cfg,k)) is int and _cv(cfg,k)==v for k,v in CFG.items())


def _cfg_key(cfg):
    return tuple(_cv(cfg,k) for k in CFG)


def _rows(a):
    if not isinstance(a,dict): return None
    f,h,m=a.get("farmer"),a.get("hands"),a.get("market")
    if not isinstance(f,list) or not isinstance(h,list) or not isinstance(m,list): return None
    if any(not isinstance(x,list) for x in h+m): return None
    return f,h,m


def _inv_total(d):
    if not isinstance(d,dict): return None
    n=0
    for k,v in d.items():
        if not isinstance(k,str) or type(v) is not int or v<0: return None
        n+=v
    return n


def _strict_equal(a,b):
    """Type-preserving structural equality for same-step retry evidence."""
    if type(a) is not type(b):return False
    if isinstance(a,dict):
        if a.keys()!=b.keys():return False
        return all(_strict_equal(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)):
        return len(a)==len(b) and all(_strict_equal(x,y) for x,y in zip(a,b))
    return a==b


def _access():
    return ((4,4),(5,4),(4,5),(5,5))


def _beside(p):
    return isinstance(p,list) and len(p)==2 and tuple(p) in _access()


def _nearest_access(p):
    if not isinstance(p,list) or len(p)!=2 or any(type(x) is not int for x in p): return None
    return min(_access(),key=lambda q:(abs(p[0]-q[0])+abs(p[1]-q[1]),q))


def _walk(p,t):
    if not isinstance(p,list) or len(p)!=2 or any(type(x) is not int for x in p): return None
    x,y=p; tx,ty=t
    if not 0<=x<10 or not 0<=y<10: return None
    if x<tx:return ["EAST"]
    if x>tx:return ["WEST"]
    if y<ty:return ["SOUTH"]
    if y>ty:return ["NORTH"]
    return ["PASS"]


def _distance(t):
    return max(abs(t[0]-x)+abs(t[1]-y) for x,y in _access())


def _empty_coops(farm):
    tiles=farm.get("tiles") if isinstance(farm,dict) else None
    if not isinstance(tiles,list) or len(tiles)!=10:return None
    out=[]
    for y,row in enumerate(tiles):
        if not isinstance(row,list) or len(row)!=10:return None
        for x,t in enumerate(row):
            if isinstance(t,dict) and t.get("kind")=="COOP" and "animal" not in t:out.append((x,y))
    return out


def _geese(farm,private):
    tiles=farm.get("tiles") if isinstance(farm,dict) else None
    shed=private.get("shed") if isinstance(private,dict) else None
    invs=private.get("inventories") if isinstance(private,dict) else None
    if not isinstance(tiles,list) or not isinstance(shed,dict) or not isinstance(invs,list):return None
    n=shed.get("GOOSE",0)
    if type(n) is not int or n<0:return None
    for inv in invs:
        if not isinstance(inv,dict) or type(inv.get("GOOSE",0)) is not int or inv.get("GOOSE",0)<0:return None
        n+=inv.get("GOOSE",0)
    for row in tiles:
        if not isinstance(row,list):return None
        n+=sum(isinstance(t,dict) and t.get("animal")=="GOOSE" for t in row)
    return n


def _native(player):
    p=getattr(r04,"_POLICY",None)
    try:return p.players.get(player)
    except Exception:return None


def _day(native,day):
    try: cards=r04._v219_native_day(native,day)
    except Exception:return None
    if not isinstance(cards,list) or not cards or any(not isinstance(c,dict) for c in cards):return None
    return cards


def _day_meta(native,day):
    cards=_day(native,day)
    if cards is None:return None
    expected=0; last=-1; native_hires=0
    for hour,c in enumerate(cards):
        hs=c.get("hands",[]); market=c.get("market",[])
        if not isinstance(hs,list) or not isinstance(market,list) or any(not isinstance(o,list) for o in market):return None
        expected=max(expected,len(hs))
        hires=sum(bool(o) and o[0]=="HIRE" for o in market)
        native_hires+=hires
        if hires:last=hour
    hour=max(4,last,0)
    if hour>=len(cards) or not isinstance(cards[hour].get("market",[]),list):return None
    return cards,expected,hour,len(cards[hour].get("market",[])),native_hires


def _fib(n):
    a,b=1,1
    for _ in range(n):a,b=b,a+b
    return a


def _schedule(native,start,target,current_hire_ordinal):
    if type(current_hire_ordinal) is not int or current_hire_ordinal<0:return None
    dist=_distance(target); out={}; hire_cost=0
    for d in range(start,LAST_DAY+1):
        meta=_day_meta(native,d)
        if meta is None:return None
        _,expected,hour,slots,native_hires=meta
        initial=d==start; final=d==LAST_DAY
        add_slots=4 if initial else (1 if final else 2)
        if slots+add_slots>10:return None
        need=3 if initial or final else 4
        if hour+dist+need>23:return None
        # The official engine prices HIRE from hires_today, which resets each dawn.
        # The admission callback supplies the exact current-day ordinal. Future
        # days use the native route's authored HIRE count plus the existing day-18
        # expansion cushion; standing hand count is never a price proxy.
        idx=current_hire_ordinal if initial else native_hires+(4 if start<18<=d else 0)
        hire_cost+=_fib(idx)+(_fib(idx+1) if initial else 0)
        out[d]={"hour":hour,"expected":expected,"hire_ordinal":idx}
    return out,hire_cost,dist


def _eggs(start):
    # Engine GOOSE.first_yield_day == 4. PLACE stores placed_day=current day,
    # and end-of-day refresh creates the first harvestable yield for start+4.
    first=start+4
    return 0 if first>LAST_DAY else 4+2*(LAST_DAY-first)


def _econ(obs,native,start,target,current_hire_ordinal):
    prices=obs.get("market",{}).get("prices",{})
    egg,wheat=prices.get("EGG"),prices.get("WHEAT")
    if type(egg) is not int or type(wheat) is not int or min(egg,wheat)<=0:return None
    sched=_schedule(native,start,target,current_hire_ordinal)
    if sched is None:return None
    table,hires,dist=sched
    units=_eggs(start)
    revenue=units*max(1,(egg*4)//5)
    cost=GOOSE_COST+(LAST_DAY-start)*(wheat+WHEAT_BUFFER)+hires
    return {"schedule":table,"distance":dist,"eggs":units,"revenue":revenue,"cost":cost,"margin":revenue-cost}


def _storage(private,action):
    shed=private.get("shed") if isinstance(private,dict) else None
    invs=private.get("inventories") if isinstance(private,dict) else None
    if not isinstance(invs,list):return None
    n=_inv_total(shed)
    if n is None:return None
    for inv in invs:
        q=_inv_total(inv)
        if q is None:return None
        n+=q
    for o in action.get("market",[]):
        if o and o[0] in ("BUY_PRODUCT","BUY_ANIMAL"):
            if len(o)<3 or type(o[2]) is not int or o[2]<0:return None
            n+=o[2]
    return n


def _parent_spend(action,farm,obs):
    prices=obs.get("market",{}).get("prices",{})
    hires=farm.get("hires_today")
    unlocked=farm.get("unlocked_quadrants")
    if type(hires) is not int or hires<0 or not isinstance(unlocked,list):return None
    seeds={"WHEAT":10,"CARROT":20,"TOMATO":50,"STRAWBERRY":100,"MELON":80}
    animals={"GOOSE":300,"COW":400,"SHEEP":500}
    lands=(1000,2000,4000); li=max(0,len(unlocked)-1); total=0
    for o in action.get("market",[]):
        if not o or o[0]=="SELL":continue
        op=o[0]
        if op=="HIRE":total+=_fib(hires);hires+=1
        elif op=="BUY_LAND":
            if li>=len(lands):return None
            total+=lands[li];li+=1
        elif op in ("BUY_PRODUCT","BUY_ANIMAL","BUY_SEED"):
            if len(o)<3 or type(o[2]) is not int or o[2]<0:return None
            item,n=o[1],o[2]
            if op=="BUY_PRODUCT":
                p=prices.get(item)
                if type(p) is not int or p<=0:return None
                total+=n*(p+WHEAT_BUFFER)
            elif op=="BUY_ANIMAL":
                if item not in animals:return None
                total+=n*animals[item]
            else:
                if item not in seeds:return None
                total+=n*seeds[item]
        else:return None
    return total


def _put(result,actor,cmd,actual_hands):
    h=result.get("hands")
    if not isinstance(h,list):return False
    while len(h)<actual_hands:h.append(["PASS"])
    if actor<=0 or actor-1>=len(h):return False
    h[actor-1]=cmd
    return True


def _stable_state(s):
    return copy.deepcopy({k:v for k,v in s.items() if not k.startswith("_retry_")})


def _telemetry_delta(before):
    keys=set(before)|set(telemetry)
    return {k:telemetry.get(k,0)-before.get(k,0) for k in keys
            if telemetry.get(k,0)-before.get(k,0)>0}


def _undo_telemetry(delta):
    if not isinstance(delta,dict):return
    for k,n in delta.items():
        if type(n) is not int or n<=0:continue
        left=telemetry.get(k,0)-n
        if left>0:telemetry[k]=left
        else:telemetry.pop(k,None)


def _cache_retry(s,before,action,observation,configuration,out,telemetry_delta=None):
    s["_retry_before"]=copy.deepcopy(before)
    s["_retry_parent"]=copy.deepcopy(action)
    s["_retry_observation"]=copy.deepcopy(observation)
    s["_retry_cfg"]=_cfg_key(configuration)
    s["_retry_output"]=copy.deepcopy(out)
    s["_retry_telemetry_delta"]=dict(telemetry_delta or {})


def _state(player,step):
    s=STATE.get(player)
    if s is None or step<s.get("last",-1):
        s={"phase":"idle","last":-1};STATE[player]=s
    return s


def _request(action,obs,s):
    step=obs["step"]; day,hour=divmod(step,24)
    if step<144 or not MIN_DAY<=day<=MAX_DAY:return action
    player=obs["player"]; farm=obs["farms"][player]; private=obs["private"]
    if not isinstance(farm,dict):return action
    native=_native(player); meta=_day_meta(native,day) if native is not None else None
    rr=_rows(action)
    if meta is None or rr is None:return action
    _,expected,service_hour,_,_=meta
    if hour!=service_hour:return action
    market=rr[2]; farm_hands=farm.get("hands"); hires_today=farm.get("hires_today")
    if not isinstance(farm_hands,list) or type(hires_today) is not int or hires_today<0:return action
    parent_hires=sum(bool(o) and o[0]=="HIRE" for o in market)
    actor_base=len(farm_hands)+parent_hires
    hire_ordinal=hires_today+parent_hires
    if actor_base<expected:return action
    targets=_empty_coops(farm); count=_geese(farm,private)
    if not targets or count is None or count>=GOOSE_CAP:return action
    target=min(targets,key=lambda p:(_distance(p),p))
    econ=_econ(obs,native,day,target,hire_ordinal)
    if econ is None or econ["margin"]<PAYBACK_MARGIN:
        telemetry["no_payback"]+=1;return action
    if econ["schedule"][day]["hour"]!=hour or len(market)+4>10:return action
    store=_storage(private,action)
    if store is None or store+2>100:
        telemetry["capacity_block"]+=1;return action
    money=farm.get("money"); spend=_parent_spend(action,farm,obs)
    wheat=obs.get("market",{}).get("prices",{}).get("WHEAT")
    if not isinstance(money,(int,float)) or spend is None or type(wheat) is not int:return action
    need=spend+GOOSE_COST+wheat+WHEAT_BUFFER+_fib(hire_ordinal)+_fib(hire_ordinal+1)+CASH_RESERVE
    if money<need:
        telemetry["cash_block"]+=1;return action
    out=copy.deepcopy(action)
    out["market"] += [["BUY_ANIMAL","GOOSE",1],["BUY_PRODUCT","WHEAT",1],["HIRE"],["HIRE"]]
    s.update({"phase":"requested","target":target,"start":day,"schedule":econ["schedule"],"deploy_base":actor_base,"request_step":step})
    telemetry["commit_requests"]+=1
    return out


def _finish_deploy(action,obs,s,carrier,feeder):
    farm=obs["farms"][obs["player"]]; target=tuple(s["target"]); tile=farm["tiles"][target[1]][target[0]]
    if not isinstance(tile,dict) or tile.get("animal")!="GOOSE":s["phase"]="aborted";return action
    pos=[farm.get("farmer"),*(farm.get("hands") or [])]; actual=len(farm.get("hands") or [])
    if len(pos)<=feeder:return action
    out=copy.deepcopy(action)
    if not tile.get("fed_today",False):
        invs=obs["private"].get("inventories",[])
        if len(invs)<=feeder or not isinstance(invs[feeder],dict) or invs[feeder].get("WHEAT",0)<=0:return action
        cmd=["FEED"] if tuple(pos[feeder])==target else _walk(pos[feeder],target)
        return out if cmd is not None and _put(out,feeder,cmd,actual) else action
    if not tile.get("cared_today",False):
        actor=carrier if tuple(pos[carrier])==target else feeder
        cmd=["CARE"] if tuple(pos[actor])==target else _walk(pos[actor],target)
        return out if cmd is not None and _put(out,actor,cmd,actual) else action
    return action


def _deploy(action,obs,s):
    player=obs["player"]; farm=obs["farms"][player]; private=obs["private"]; target=tuple(s["target"])
    base=s["deploy_base"]; carrier,feeder=base+1,base+2
    pos=[farm.get("farmer"),*(farm.get("hands") or [])]; invs=private.get("inventories")
    if not isinstance(invs,list) or len(pos)<=feeder or len(invs)<=feeder:
        s["phase"]="aborted";telemetry["deploy_shortfall"]+=1;return action
    tile=farm["tiles"][target[1]][target[0]]
    if isinstance(tile,dict) and tile.get("animal")=="GOOSE":
        s["phase"]="active";telemetry["goose_confirmed"]+=1
        return _finish_deploy(action,obs,s,carrier,feeder)
    if not isinstance(tile,dict) or tile.get("kind")!="COOP" or "animal" in tile:
        s["phase"]="aborted";telemetry["target_drift"]+=1;return action
    out=copy.deepcopy(action); actual=len(farm.get("hands") or []); cmds={}
    for actor,item in ((carrier,"GOOSE"),(feeder,"WHEAT")):
        p,inv=pos[actor],invs[actor]
        if not isinstance(inv,dict):s["phase"]="aborted";return action
        if inv.get(item,0)>0:
            cmds[actor]=(["PLACE","GOOSE"] if item=="GOOSE" else ["FEED"]) if tuple(p)==target else _walk(p,target)
        else:
            shed=private.get("shed",{}); available=shed.get(item,0) if isinstance(shed,dict) else 0
            if type(available) is not int or available<=0:
                s["phase"]="aborted";telemetry["purchase_shortfall"]+=1;return action
            if _beside(p):cmds[actor]=["PICKUP",item,1]
            else:
                access=_nearest_access(p);cmds[actor]=_walk(p,access) if access is not None else None
        if cmds[actor] is None:s["phase"]="aborted";return action
    if not _put(out,carrier,cmds[carrier],actual) or not _put(out,feeder,cmds[feeder],actual):
        s["phase"]="aborted";return action
    telemetry["deploy_callbacks"]+=1
    return out


def _request_service(action,obs,s):
    day,hour=divmod(obs["step"],24)
    if day<=s["start"] or day>LAST_DAY or s.get("service_day")==day:return action
    slot=s.get("schedule",{}).get(day)
    if not isinstance(slot,dict) or hour!=slot.get("hour"):return action
    player=obs["player"];farm=obs["farms"][player];private=obs["private"];target=tuple(s["target"])
    tile=farm["tiles"][target[1]][target[0]]
    if not isinstance(tile,dict) or tile.get("animal")!="GOOSE":s["phase"]="aborted";return action
    rr=_rows(action)
    if rr is None:return action
    market=rr[2]; hands=farm.get("hands"); expected=slot.get("expected"); hires_today=farm.get("hires_today")
    if not isinstance(hands,list) or type(expected) is not int or type(hires_today) is not int or hires_today<0:return action
    parent_hires=sum(bool(o) and o[0]=="HIRE" for o in market)
    base=len(hands)+parent_hires
    hire_ordinal=hires_today+parent_hires
    planned_ordinal=slot.get("hire_ordinal")
    if base<expected or type(planned_ordinal) is not int or hire_ordinal>planned_ordinal:return action
    final=day==LAST_DAY; extra=1 if final else 2
    if len(market)+extra>10:return action
    store=_storage(private,action)
    if store is None or store+(0 if final else 1)>100:return action
    out=copy.deepcopy(action)
    if not final:out["market"].append(["BUY_PRODUCT","WHEAT",1])
    out["market"].append(["HIRE"])
    s["service_day"]=day;s["service_base"]=base;telemetry["service_hires"]+=1
    return out


def _service(action,obs,s):
    day=obs["step"]//24
    if s.get("service_day")!=day:return action
    player=obs["player"];farm=obs["farms"][player];private=obs["private"];base=s.get("service_base")
    if type(base) is not int:return action
    actor=base+1;pos=[farm.get("farmer"),*(farm.get("hands") or [])];invs=private.get("inventories")
    if not isinstance(invs,list) or len(pos)<=actor or len(invs)<=actor:return action
    target=tuple(s["target"]);tile=farm["tiles"][target[1]][target[0]]
    if not isinstance(tile,dict) or tile.get("animal")!="GOOSE":s["phase"]="aborted";return action
    p,inv=pos[actor],invs[actor]
    if not isinstance(inv,dict):return action
    final=day==LAST_DAY
    if tuple(p)!=target:
        if not final and inv.get("WHEAT",0)<=0:
            shed=private.get("shed",{});w=shed.get("WHEAT",0) if isinstance(shed,dict) else 0
            if type(w) is int and w>0 and _beside(p):cmd=["PICKUP","WHEAT",1]
            elif type(w) is int and w>0:
                access=_nearest_access(p);cmd=_walk(p,access) if access is not None else None
            else:cmd=None
        else:cmd=_walk(p,target)
    else:
        units,fed,cared=tile.get("yield_units"),tile.get("fed_today"),tile.get("cared_today")
        if type(units) is not int or type(fed) is not bool or type(cared) is not bool:return action
        if units>0:cmd=["HARVEST"];telemetry["harvest_requests"]+=1
        elif final:cmd=["PASS"]
        elif not fed:cmd=["FEED"] if inv.get("WHEAT",0)>0 else None
        elif not cared:cmd=["CARE"]
        else:cmd=["PASS"]
    if cmd is None:telemetry["service_shortfall"]+=1;return action
    out=copy.deepcopy(action)
    return out if _put(out,actor,cmd,len(farm.get("hands") or [])) else action


def apply_goose_capacity_economy(action,observation,configuration,*,enabled=False):
    if not enabled or not _cfg_ok(configuration) or not isinstance(observation,dict):return action
    step,player=observation.get("step"),observation.get("player")
    farms,private=observation.get("farms"),observation.get("private")
    if type(step) is not int or not 0<=step<720 or type(player) is not int or player not in (0,1):return action
    if not isinstance(farms,list) or len(farms)!=2 or not isinstance(private,dict) or _rows(action) is None:return action
    s=_state(player,step)
    if step==s.get("last"):
        same=(_strict_equal(action,s.get("_retry_parent"))
              and _strict_equal(observation,s.get("_retry_observation"))
              and _strict_equal(_cfg_key(configuration),s.get("_retry_cfg")))
        if same and "_retry_output" in s:
            telemetry["same_step_replay"]+=1
            return copy.deepcopy(s["_retry_output"])
        _undo_telemetry(s.get("_retry_telemetry_delta",{}))
        before=copy.deepcopy(s.get("_retry_before",_stable_state(s)))
        s.clear();s.update(before);s["last"]=step
        _cache_retry(s,before,action,observation,configuration,action,{})
        telemetry["same_step_changed"]+=1
        return copy.deepcopy(action)
    before=_stable_state(s)
    telemetry_before=Counter(telemetry)
    phase=s.get("phase","idle")
    if phase=="idle":out=_request(action,observation,s)
    elif phase=="requested":out=_deploy(action,observation,s)
    elif phase=="active":
        if step//24==s["start"]:
            b=s["deploy_base"];out=_finish_deploy(action,observation,s,b+1,b+2)
        else:
            req=_request_service(action,observation,s)
            out=req if req is not action else _service(action,observation,s)
    else:out=action
    s["last"]=step
    _cache_retry(s,before,action,observation,configuration,out,_telemetry_delta(telemetry_before))
    return out


def reset():
    STATE.clear();telemetry.clear()
