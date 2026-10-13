#!/usr/bin/env python3
"""Source-bound passive-town price baseline for TITAN V4 (research only)."""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, math, sys, types
from pathlib import Path
from statistics import fmean
from types import SimpleNamespace

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
LAST_ACTION = 718
TERMINAL_OBS = 719
CONFIG = {"boardSize":10,"startingMoney":3000,"turnsPerDay":24,"episodeSteps":720,
          "shedCapacity":100,"weedSpawnChance":0.005,"townShopSellInterval":4,
          "townCenterSellInterval":24,"townShopUnlockInterval":3}


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()


def load_engine(path):
    path=Path(path); data=path.read_bytes(); actual=git_blob(data)
    if actual != ENGINE_BLOB: raise ValueError(f"engine Git blob mismatch: {actual}")
    try: import kaggle_environments.utils  # noqa:F401
    except ModuleNotFoundError:
        pkg=sys.modules.setdefault("kaggle_environments",types.ModuleType("kaggle_environments"))
        util=types.ModuleType("kaggle_environments.utils")
        util.resolve_episode_seed=lambda env:int(getattr(env,"info",{}).get("seed",0))
        pkg.utils=util; sys.modules["kaggle_environments.utils"]=util
    spec=importlib.util.spec_from_file_location("titan_passive_engine",path)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    need=("PRODUCTS","SHOPS","TOWN_CENTER_PRODUCTS","MAX_SHOP_INSTANCES","MARKET_PARAMS",
          "_new_farm","_new_private","_new_market","_new_town","_town_consume","_end_of_day","market_price")
    missing=[n for n in need if not hasattr(mod,n)]
    if missing: raise ValueError(f"engine missing symbols: {missing}")
    return mod


def world(engine,seed):
    farms=[engine._new_farm(CONFIG["boardSize"],CONFIG["startingMoney"]) for _ in range(2)]
    priv=[engine._new_private() for _ in range(2)]
    market,town=engine._new_market(),engine._new_town(); states=[]
    for p in range(2):
        obs=SimpleNamespace(player=p,farms=farms,market=market,town=town,private=priv[p])
        states.append(SimpleNamespace(observation=obs))
    return states,SimpleNamespace(configuration=dict(CONFIG),info={"seed":int(seed)})


def simulate(engine,seed):
    states,env=world(engine,seed); obs=states[0].observation; rows=[]
    for step in range(TERMINAL_OBS+1):
        rows.append({"seed":int(seed),"step":step,"terminal":step==TERMINAL_OBS,
                     "shops":tuple(obs.town["unlocked_shops"]),
                     "inventory":{p:int(obs.market["inventory"][p]) for p in engine.PRODUCTS},
                     "price":{p:int(obs.market["prices"][p]) for p in engine.PRODUCTS}})
        if step==TERMINAL_OBS: break
        engine._town_consume(env,states,step)
        if (step+1)%CONFIG["turnsPerDay"]==0: engine._end_of_day(states,env,step//24)
    return rows


def envelope(engine):
    products=tuple(engine.PRODUCTS); lo={p:engine.MARKET_PARAMS[p]["I0"] for p in products}; hi=dict(lo)
    rates={p:(min((2 if len(g)==1 else 1) if p in g else 0 for g in engine.SHOPS.values()),
              max((2 if len(g)==1 else 1) if p in g else 0 for g in engine.SHOPS.values())) for p in products}
    shops=0; out=[]
    for step in range(TERMINAL_OBS+1):
        out.append({"step":step,"shops":shops,"products":{p:{"min_inventory":lo[p],"max_inventory":hi[p],
                    "min_price":engine.market_price(p,hi[p]),"max_price":engine.market_price(p,lo[p])} for p in products}})
        if step==TERMINAL_OBS: break
        if step%CONFIG["townShopSellInterval"]==0:
            for p in products: hi[p]-=shops*rates[p][0]; lo[p]-=shops*rates[p][1]
        if step%CONFIG["townCenterSellInterval"]==0:
            for p in engine.TOWN_CENTER_PRODUCTS: hi[p]-=1; lo[p]-=1
        if (step+1)%24==0 and ((step//24)+1)%CONFIG["townShopUnlockInterval"]==0:
            shops=min(engine.MAX_SHOP_INSTANCES,shops+1)
    return out


def q(xs,p):
    xs=sorted(xs); return xs[int(math.floor((len(xs)-1)*p))] if xs else None


def analyze(engine,paths,bounds):
    curves=[]; crossings=[]; product_summary={}
    for step in range(TERMINAL_OBS+1):
        for product in engine.PRODUCTS:
            iv=[x[step]["inventory"][product] for x in paths]; px=[x[step]["price"][product] for x in paths]
            b=bounds[step]["products"][product]
            curves.append({"step":step,"product":product,"inventory_min":min(iv),"inventory_p05":q(iv,.05),
                "inventory_p50":q(iv,.5),"inventory_mean":fmean(iv),"inventory_p95":q(iv,.95),"inventory_max":max(iv),
                "price_min":min(px),"price_p05":q(px,.05),"price_p50":q(px,.5),"price_mean":fmean(px),
                "price_p95":q(px,.95),"price_max":max(px),**{f"envelope_{k}":v for k,v in b.items()}})
    for product in engine.PRODUCTS:
        prm=engine.MARKET_PARAMS[product]; i0,t=int(prm["I0"]),int(prm["T"]); hits=[]; beyond=[]
        for path in paths:
            a=next((r["step"] for r in path if i0-r["inventory"][product]>=t),None)
            z=next((r["step"] for r in path if i0-r["inventory"][product]>t),None)
            crossings.append({"seed":path[0]["seed"],"product":product,"first_at_T":a,"first_beyond_T":z,
                              "actionable_at_T":a is not None and a<=LAST_ACTION})
            if a is not None:hits.append(a)
            if z is not None:beyond.append(z)
        product_summary[product]={"I0":i0,"T":t,"base_price":int(prm["base"]),"seeds_crossing_at_T":len(hits),
            "first_at_T_step_min":min(hits) if hits else None,"first_at_T_step_p50":q(hits,.5),
            "first_at_T_step_p95":q(hits,.95),"first_at_T_step_max":max(hits) if hits else None,
            "first_beyond_T_step_min":min(beyond) if beyond else None,"first_beyond_T_step_p50":q(beyond,.5),
            "terminal_inventory_p50":q([x[-1]["inventory"][product] for x in paths],.5),
            "terminal_price_p50":q([x[-1]["price"][product] for x in paths],.5)}
    return curves,crossings,product_summary


def classify(engine,observation,bounds=None):
    step=int(observation.get("step",observation.get("day",0)*24+observation.get("hour",0)))
    if not 0<=step<=TERMINAL_OBS:return {"status":"UNSUPPORTED_STEP","products":{}}
    bounds=bounds or envelope(engine); inv=observation.get("market",{}).get("inventory",{}); out={}
    for p in engine.PRODUCTS:
        v=inv.get(p); b=bounds[step]["products"][p]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v): status="INVALID_INVENTORY"
        elif v<b["min_inventory"]: status="BELOW_PASSIVE_ENVELOPE"
        elif v>b["max_inventory"]: status="ABOVE_PASSIVE_ENVELOPE"
        else: status="WITHIN_PASSIVE_ENVELOPE"
        out[p]={"status":status,"inventory":v,"passive_min_inventory":b["min_inventory"],"passive_max_inventory":b["max_inventory"]}
    return {"status":"OK","step":step,"products":out}


def write_csv(path,rows):
    rows=list(rows)
    with Path(path).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def run(engine_path,out_dir,seed_start=1,seed_count=100):
    engine=load_engine(engine_path); seeds=range(seed_start,seed_start+seed_count); paths=[simulate(engine,s) for s in seeds]
    bounds=envelope(engine)
    for path in paths:
        for row,b in zip(path,bounds):
            for p in engine.PRODUCTS:
                if not b["products"][p]["min_inventory"]<=row["inventory"][p]<=b["products"][p]["max_inventory"]:
                    raise AssertionError(f"sample escaped envelope seed={row['seed']} step={row['step']} product={p}")
    curves,crossings,products=analyze(engine,paths,bounds); out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"curves.csv",curves);write_csv(out/"crossings.csv",crossings)
    shops=[]
    for path in paths:
        n=0
        for row in path:
            while n<len(row["shops"]):shops.append({"seed":row["seed"],"visible_step":row["step"],"unlock_index":n+1,"shop":row["shops"][n]});n+=1
    write_csv(out/"shop_paths.csv",shops)
    receipt={"kind":"titan-v4-passive-town-baseline","engine_git_blob":ENGINE_BLOB,"seed_start":seed_start,"seed_count":seed_count,
             "last_actionable_step":LAST_ACTION,"terminal_observation_step":TERMINAL_OBS,"config":CONFIG,"products":products,
             "limits":["pass/pass baseline only; not a policy forecast","sample quantiles are distinct from exact passive envelope","step719 is terminal-only"]}
    (out/"summary.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n");return receipt


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--engine",required=True);ap.add_argument("--out-dir",required=True)
    ap.add_argument("--seed-start",type=int,default=1);ap.add_argument("--seed-count",type=int,default=100);a=ap.parse_args(argv)
    print(json.dumps(run(a.engine,a.out_dir,a.seed_start,a.seed_count),sort_keys=True))
if __name__=="__main__":main()
