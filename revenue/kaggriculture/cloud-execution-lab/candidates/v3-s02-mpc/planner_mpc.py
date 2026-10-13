# SPDX-License-Identifier: Apache-2.0
"""Receding-horizon planner over the exact Kaggriculture interpreter."""
from __future__ import annotations
import copy, os, time
from types import SimpleNamespace

ENGINE_DIR = os.environ.get("TITAN_MPC_ENGINE", "/tmp/v25/engine")
_ENGINE = None
_STATS = {"turns": 0, "plan_s": [], "timeouts": 0, "errors": 0, "used_alt": 0}

def _engine():
    global _ENGINE
    if _ENGINE is None:
        import importlib.util, sys
        path = os.path.join(ENGINE_DIR, "kaggriculture.py")
        spec = importlib.util.spec_from_file_location("_mpc_kaggriculture", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_mpc_kaggriculture"] = mod
        spec.loader.exec_module(mod)
        _ENGINE = mod
    return _ENGINE

def legal_pass(obs):
    farm = obs["farms"][int(obs["player"])]
    n_hands = len(farm.get("hands") or [])
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(n_hands)], "market": []}

def _as_dict(obj):
    if isinstance(obj, dict):
        return {k: _as_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_as_dict(v) for v in obj]
    return obj

def _obs_dict(observation):
    if isinstance(observation, dict):
        return _as_dict(observation)
    if hasattr(observation, "toDict"):
        return _as_dict(observation.toDict())
    return _as_dict(dict(observation))

class _Obs(dict):
    def __getattr__(self, key):
        try: return self[key]
        except KeyError as e: raise AttributeError(key) from e
    def __setattr__(self, key, value): self[key] = value

class _Cfg(dict):
    def __getattr__(self, key):
        try: return self[key]
        except KeyError as e: raise AttributeError(key) from e
    def __setattr__(self, key, value): self[key] = value

def _wrap_obs(d):
    o = _Obs()
    for k,v in d.items(): o[k]=v
    return o

def _make_env(cfg, seed=0):
    env = SimpleNamespace()
    raw = copy.deepcopy(cfg) if cfg else {}
    if not isinstance(raw, dict): raw = dict(raw)
    for k,v in (("episodeSteps",720),("turnsPerDay",24),("boardSize",10),
                ("shedCapacity",100),("weedSpawnChance",0.005),
                ("townShopUnlockInterval",3),("maxMarketOrdersPerTurn",10),
                ("startingMoney",3000)):
        raw.setdefault(k,v)
    env.configuration = _Cfg(raw)
    env.done = False
    env.info = {"seed": int(seed or 0)}
    return env

def split_public_private(obs):
    keys = ("farms","market","town","day","hour","step")
    pub = {k: copy.deepcopy(obs[k]) for k in keys if k in obs}
    priv = copy.deepcopy(obs.get("private") or _engine()._new_private())
    return pub, priv, int(obs["player"])

def instantiate_state(obs, cfg, rival_private=None):
    eng = _engine()
    pub, own_priv, player = split_public_private(obs)
    rival = 1-player
    farms = copy.deepcopy(pub["farms"])
    market = copy.deepcopy(pub["market"])
    town = copy.deepcopy(pub.get("town") or {"unlocked_shops": []})
    step = int(pub.get("step", int(obs.get("day",0))*24 + int(obs.get("hour",0))))
    day = int(pub.get("day", step//24)); hour = int(pub.get("hour", step%24))
    privs=[None,None]
    privs[player]=copy.deepcopy(own_priv)
    privs[rival]=copy.deepcopy(rival_private) if rival_private is not None else eng._new_private()
    states=[]
    for i in range(2):
        o=_wrap_obs({"player":i,"step":step,"day":day,"hour":hour,"farms":farms,"market":market,"town":town,"private":privs[i]})
        states.append(SimpleNamespace(observation=o, action={}, status="ACTIVE", reward=0))
    return states

def step_engine(states, env, joint_actions):
    eng=_engine()
    for i,s in enumerate(states):
        s.action=copy.deepcopy(joint_actions[i])
    eng.interpreter(states, env)
    step=int(states[0].observation.get("step",0))+1
    for s in states:
        s.observation["step"]=step
        s.observation.step=step
    return states

def _norm_action(act, obs, player=None):
    if not isinstance(act, dict):
        return legal_pass(obs)
    farm=obs["farms"][int(obs["player"] if player is None else player)]
    n_hands=len(farm.get("hands") or [])
    farmer=act.get("farmer") or ["PASS"]
    if not isinstance(farmer, list): farmer=["PASS"]
    hands=list(act.get("hands") or [])
    while len(hands)<n_hands: hands.append(["PASS"])
    hands=hands[:n_hands]
    return {"farmer":list(farmer),"hands":[list(h) if isinstance(h,list) else ["PASS"] for h in hands],"market":list(act.get("market") or [])}

def _vary_hire(action, delta, cfg):
    out=copy.deepcopy(action)
    market=list(out.get("market") or [])
    hires=[i for i,o in enumerate(market) if o and o[0]=="HIRE"]
    max_orders=int(cfg.get("maxMarketOrdersPerTurn",10))
    if delta>0:
        if len(market)<max_orders: market.append(["HIRE"])
        elif [] in market: market[market.index([])]=["HIRE"]
        else: return None
    elif delta<0:
        if not hires: return None
        del market[hires[-1]]
    out["market"]=market
    return out

def _vary_sale(action, mode):
    out=copy.deepcopy(action)
    market=list(out.get("market") or [])
    sells=[i for i,o in enumerate(market) if o and o[0]=="SELL" and len(o)>2]
    if not sells: return None
    i0=sells[0]
    if mode=="drop": market[i0]=[]
    elif mode=="half":
        q=max(0,int(market[i0][2])//2)
        market[i0]=[] if q<=0 else [market[i0][0], market[i0][1], q]
    elif mode=="drop_last": market[sells[-1]]=[]
    out["market"]=market
    return out

def _vary_harvest(action, obs):
    out=copy.deepcopy(action)
    farm=obs["farms"][int(obs["player"])]
    fx,fy=farm["farmer"][0], farm["farmer"][1]
    tiles=farm["tiles"]
    tile=tiles[fy][fx] if fy<len(tiles) and fx<len(tiles[0]) else None
    cur=out.get("farmer") or ["PASS"]
    if isinstance(tile, dict) and (tile.get("kind")=="PLANT" or "animal" in tile or tile.get("kind") in ("COOP","PASTURE")):
        if cur!=["HARVEST"]:
            out["farmer"]=["HARVEST"]; return out
    if cur and cur[0]=="HARVEST":
        out["farmer"]=["PASS"]; return out
    return None

def generate_candidates(canonical, obs, cfg, limit=8):
    cands=[copy.deepcopy(canonical)]; seen={repr(cands[0])}; variants=[]
    for d in (1,-1):
        v=_vary_hire(canonical,d,cfg)
        if v: variants.append(v)
    for mode in ("drop","half","drop_last"):
        v=_vary_sale(canonical,mode)
        if v: variants.append(v)
    v=_vary_harvest(canonical,obs)
    if v: variants.append(v)
    extra=copy.deepcopy(canonical)
    if extra.get("market"):
        extra["market"]=list(extra["market"])[:-1]; variants.append(extra)
    for v in variants:
        k=repr(v)
        if k in seen: continue
        seen.add(k); cands.append(v)
        if len(cands)>=limit: break
    return cands

def _cash(states, player):
    return float(states[0].observation["farms"][player]["money"])

def _obs_for_player(states, player):
    s=states[player].observation
    return {"player":player,"step":int(s.get("step",0)),"day":int(s.get("day",0)),
            "hour":int(s.get("hour",0)),"farms":s["farms"],"market":s["market"],
            "town":s.get("town") or {"unlocked_shops":[]},"private":s["private"]}

def _rival_titan_action(obs_for_rival, cfg, shadow):
    if not shadow: return legal_pass(obs_for_rival)
    try: return _norm_action(shadow(obs_for_rival, cfg), obs_for_rival)
    except Exception: return legal_pass(obs_for_rival)

def rollout(obs, cfg, own_action, horizon, rival_mode, last_rival_action, shadow, deadline):
    player=int(obs["player"]); rival=1-player
    env=_make_env(cfg, seed=int(cfg.get("seed") or 0))
    states=instantiate_state(obs, cfg)
    persist=copy.deepcopy(last_rival_action) if last_rival_action else legal_pass(_obs_for_player(states, rival))
    for t in range(horizon):
        if time.perf_counter()>=deadline: raise TimeoutError("plan budget")
        own_obs=_obs_for_player(states, player); riv_obs=_obs_for_player(states, rival)
        a_own=_norm_action(own_action, own_obs) if t==0 else legal_pass(own_obs)
        if rival_mode=="pass":
            a_riv=legal_pass(riv_obs)
        elif rival_mode=="repeat":
            a_riv=_norm_action(persist, riv_obs, player=rival)
        elif rival_mode=="titan":
            if t==0:
                a_riv=_rival_titan_action(riv_obs, cfg, shadow); persist=a_riv
            else:
                a_riv=_norm_action(persist, riv_obs, player=rival)
        else:
            a_riv=legal_pass(riv_obs)
        joint=[None,None]; joint[player]=a_own; joint[rival]=a_riv
        step_engine(states, env, joint)
        if states[0].status=="DONE": break
    return _cash(states, player)

def score_candidate(obs, cfg, action, horizon, last_rival, shadow, deadline):
    cashes=[]
    for mode in ("repeat","titan","pass"):
        if time.perf_counter()>=deadline: break
        try: cashes.append(rollout(obs,cfg,action,horizon,mode,last_rival,shadow,deadline))
        except TimeoutError: raise
        except Exception: continue
    if not cashes: return float("-inf")
    mean=sum(cashes)/len(cashes); down=min(cashes)
    return mean - max(0.0, mean-down)

class Planner:
    def __init__(self, canonical_fn, horizon=12, budget_s=0.6):
        self.canonical_fn=canonical_fn
        self.horizon=int(horizon)
        self.budget_s=float(budget_s)
        self.last_rival=None
        self.shadow=None
        self.enabled=os.environ.get("TITAN_MPC","1") not in ("0","false","False","")

    def _shadow(self):
        if self.shadow is None:
            try:
                from canonical_main import _new_instance
                from pathlib import Path
                import json
                root=Path(__file__).resolve().parent
                self.shadow=_new_instance(root, json.loads((root/"TITAN-CONFIG.json").read_text()))
            except Exception:
                self.shadow=False
        return None if self.shadow is False else self.shadow

    def act(self, observation, configuration=None):
        cfg=dict(configuration or {})
        t0=time.perf_counter()
        canonical=self.canonical_fn(observation, configuration)
        if not self.enabled: return canonical
        try:
            obs=_obs_dict(observation)
            if "step" not in obs or obs["step"] is None:
                obs["step"]=int(obs.get("day",0))*int(cfg.get("turnsPerDay",24))+int(obs.get("hour",0))
            deadline=t0+self.budget_s
            cands=generate_candidates(canonical, obs, cfg, limit=8)
            best, best_score=canonical, float("-inf")
            shadow=self._shadow()
            for cand in cands:
                if time.perf_counter()>=deadline:
                    _STATS["timeouts"]+=1; break
                sc=score_candidate(obs,cfg,cand,self.horizon,self.last_rival,shadow,deadline)
                if sc>best_score:
                    best_score=sc; best=cand
            self.last_rival=legal_pass(obs)
            elapsed=time.perf_counter()-t0
            _STATS["turns"]+=1; _STATS["plan_s"].append(elapsed)
            if best!=canonical: _STATS["used_alt"]+=1
            try:
                with open(os.environ.get("TITAN_MPC_LOG","/tmp/v25/mpc_times.jsonl"),"a") as fh:
                    fh.write('{"h":%s,"s":%.6f,"alt":%s}\n'%(self.horizon,elapsed,int(best!=canonical)))
            except Exception:
                pass
            return best
        except TimeoutError:
            _STATS["timeouts"]+=1; _STATS["turns"]+=1; _STATS["plan_s"].append(time.perf_counter()-t0)
            return canonical
        except Exception:
            _STATS["errors"]+=1; _STATS["turns"]+=1; _STATS["plan_s"].append(time.perf_counter()-t0)
            return canonical

def stats():
    times=_STATS["plan_s"]
    if not times: return dict(_STATS, max=None, p50=None)
    srt=sorted(times)
    return {"turns":_STATS["turns"],"timeouts":_STATS["timeouts"],"errors":_STATS["errors"],
            "used_alt":_STATS["used_alt"],"max":srt[-1],"p50":srt[len(srt)//2],"n":len(srt)}
