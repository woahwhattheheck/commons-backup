# SPDX-License-Identifier: Apache-2.0
"""Source-defined one-turn event macro library for TITAN S05.

Macros are exact canonical route rows, not invented multi-turn fragments.  A
macro may be proposed only at its exact source step and only when a live-state
predicate can certify the event from the player's legal observation.  After a
single action is emitted, the next observation must satisfy the macro's
postcondition or the commitment is discarded.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FAMILIES = ("reset", "unlock", "hire", "escape", "maturity", "pickup_drop", "settlement")
DECISION_STEPS = (226, 360, 433)
MAX_MACROS = 2000
MAX_SHOP_INSTANCES = 8
ANIMALS = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}
CROPS = {
    "WHEAT": {"first_yield_day": 2, "ongoing": False},
    "CARROT": {"first_yield_day": 2, "ongoing": False},
    "TOMATO": {"first_yield_day": 8, "ongoing": True},
    "STRAWBERRY": {"first_yield_day": 10, "ongoing": True},
    "MELON": {"first_yield_day": 10, "ongoing": False},
}


def _load(path: str | Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm_action(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "farmer": copy.deepcopy(row.get("farmer") or ["PASS"]),
        "hands": copy.deepcopy(row.get("hands") or []),
        "market": copy.deepcopy(row.get("market") or []),
    }


def _units(action):
    return [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]


def _ops(action):
    return [a[0] for a in _units(action) if isinstance(a, list) and a]


def _market_ops(action):
    return [a[0] for a in action.get("market", []) if isinstance(a, list) and a]


def _family_steps(step: int, action: dict[str, Any]) -> tuple[str, ...]:
    unit_ops = set(_ops(action)); market_ops = set(_market_ops(action)); out = []
    # EOD is after transition t when (t + 1) % turnsPerDay == 0.  Default
    # generator marks the 24-step source boundary; predicate rechecks runtime cfg.
    if (step + 1) % 24 == 0:
        out.extend(("reset", "unlock", "escape"))
    if "HIRE" in market_ops:
        out.append("hire")
    if "HARVEST" in unit_ops:
        out.append("maturity")
    if unit_ops.intersection({"PICKUP", "DROP"}):
        out.append("pickup_drop")
    if step == 718:
        out.append("settlement")
    return tuple(out)


def build_library(route_path: str | Path) -> list[dict[str, Any]]:
    route_mod = _load(route_path, "s05_routes")
    routes = route_mod.routes()
    grouped: dict[tuple, dict[str, Any]] = {}
    for route_id in sorted(routes):
        for step, row in enumerate(routes[route_id]):
            action = _norm_action(row)
            for family in _family_steps(step, action):
                encoded = json.dumps(action, sort_keys=True, separators=(",", ":"))
                key = (family, step, encoded)
                if key not in grouped:
                    grouped[key] = {
                        "family": family,
                        "step": step,
                        "action": action,
                        "routes": [],
                        "layer": "canonical_route_action_before_runtime_transforms",
                    }
                grouped[key]["routes"].append(route_id)
    library = []
    for key, macro in sorted(grouped.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])):
        macro["routes"] = sorted(macro["routes"])
        identity = json.dumps(macro, sort_keys=True, separators=(",", ":")).encode()
        macro["id"] = hashlib.sha256(identity).hexdigest()[:20]
        library.append(macro)
    if len(library) > MAX_MACROS:
        raise ValueError(f"macro cap exceeded: {len(library)} > {MAX_MACROS}")
    return library


def library_sha256(library) -> str:
    return hashlib.sha256((json.dumps(library, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


def index_library(library):
    out = defaultdict(list)
    for macro in library:
        for route in macro["routes"]:
            out[(route, int(macro["step"]))].append(macro)
    return out


def _cfg(cfg, key, default):
    value = (cfg or {}).get(key, default)
    if isinstance(value, dict):
        value = value.get("default", default)
    return value


def _step(obs, cfg):
    if obs.get("step") is not None:
        return int(obs["step"])
    turns = max(1, int(_cfg(cfg, "turnsPerDay", 24)))
    return int(obs.get("day", 0)) * turns + int(obs.get("hour", 0))


def _farm_private(obs):
    player = int(obs.get("player", 0)); farms = obs.get("farms") or []
    if not (0 <= player < len(farms)) or not isinstance(obs.get("private"), dict):
        return None, None
    return farms[player], obs["private"]


def _positions(farm):
    return [list(farm.get("farmer") or []), *[list(x or []) for x in farm.get("hands", [])]]


def _shed_adjacent(pos, board_size):
    if len(pos) < 2: return False
    half = board_size // 2
    return tuple(pos[:2]) in {(half-1,half-1),(half,half-1),(half-1,half),(half,half)}


def _fib(n):
    a,b=1,1
    for _ in range(int(n)): a,b=b,a+b
    return a


def _hire_exact(action, farm, cfg):
    orders = action.get("market") or []
    # To make cash feasibility source-closed, reject HIRE rows with earlier
    # market operations that can change money before a HIRE.
    money=float(farm.get("money",0)); hires=int(farm.get("hires_today",0)); mult=int(_cfg(cfg,"farmHandCostMult",1))
    seen_hire=False
    for order in orders[:int(_cfg(cfg,"maxMarketOrdersPerTurn",10))]:
        if not order: continue
        if order[0] == "HIRE":
            seen_hire=True; cost=mult*_fib(hires)
            if money < cost: return False, {"reason":"insufficient_hire_cash","cost":cost,"money":money}
            money-=cost; hires+=1
        elif not seen_hire:
            # Any earlier SELL/BUY can change cash in source-dependent ways.
            return False, {"reason":"cash_changing_prefix_before_hire"}
    return seen_hire, {"expected_hires_today":hires,"expected_money_upper_bound":money}


def _pickup_drop_exact(action, farm, private, cfg):
    board=int(_cfg(cfg,"boardSize",10)); cap=int(_cfg(cfg,"shedCapacity",100)); positions=_positions(farm)
    invs=copy.deepcopy(private.get("inventories") or []); shed=copy.deepcopy(private.get("shed") or {})
    if len(invs) < len(positions): return False,{"reason":"inventory_actor_mismatch"}
    active=False
    # Exactness guard: other unit ops in the same row could change actor position,
    # tile or inventory before/around a shed event in ways this small projector does not model.
    if any(op not in {"PASS","PICKUP","DROP"} for op in _ops(action)):
        return False,{"reason":"mixed_unit_row"}
    for i,a in enumerate(_units(action)):
        if not a or a[0] == "PASS": continue
        if not _shed_adjacent(positions[i],board): return False,{"reason":"not_shed_adjacent","actor":i}
        if a[0] == "PICKUP":
            if len(a)<2: return False,{"reason":"malformed_pickup"}
            item=a[1]; n=int(a[2]) if len(a)>=3 else 1
            if n<=0 or int(shed.get(item,0)) < n: return False,{"reason":"pickup_quantity_unavailable","actor":i,"item":item}
            shed[item]=int(shed.get(item,0))-n; invs[i][item]=int(invs[i].get(item,0))+n; active=True
        elif a[0] == "DROP":
            if not invs[i]: return False,{"reason":"empty_drop","actor":i}
            current=sum(max(0,int(v)) for v in shed.values())
            expected=sum(max(0,int(v)) for v in invs[i].values())
            if expected<=0: return False,{"reason":"empty_drop","actor":i}
            room=max(0,cap-current)
            # DROP discards overflow after filling the shed, so this remains exact.
            for item,n0 in list(invs[i].items()):
                n=max(0,int(n0)); take=min(n,room)
                if take: shed[item]=int(shed.get(item,0))+take; room-=take
            invs[i]={}; active=True
    return active,{"expected_shed":shed,"expected_inventories":invs}


def _maturity_exact(action, farm, private, cfg, step):
    positions=_positions(farm); tiles=farm.get("tiles") or []; day=step//max(1,int(_cfg(cfg,"turnsPerDay",24)))
    active=False
    for i,a in enumerate(_units(action)):
        if not a or a[0] != "HARVEST": continue
        if i>=len(positions) or len(positions[i])<2: return False,{"reason":"missing_actor","actor":i}
        x,y=map(int,positions[i][:2])
        if not (0<=y<len(tiles) and 0<=x<len(tiles[y])): return False,{"reason":"position_oob","actor":i}
        tile=tiles[y][x]
        if not isinstance(tile,dict) or int(tile.get("yield_units",0))<=0: return False,{"reason":"no_harvestable_yield","actor":i}
        if tile.get("kind") == "PLANT":
            crop=tile.get("crop"); cd=CROPS.get(crop)
            if not cd or day-int(tile.get("planted_day",day)) < int(cd["first_yield_day"]):
                return False,{"reason":"immature_crop","actor":i,"crop":crop}
        elif "animal" not in tile:
            return False,{"reason":"not_harvestable_tile","actor":i}
        active=True
    return active,{"harvests":sum(1 for a in _units(action) if a and a[0]=="HARVEST")}


def _escape_exact(action, farm, private, cfg, step):
    turns=max(1,int(_cfg(cfg,"turnsPerDay",24)))
    if (step+1)%turns: return False,{"reason":"not_end_of_day"}
    endangered=[]; tiles=farm.get("tiles") or []
    for y,row in enumerate(tiles):
        for x,tile in enumerate(row):
            if isinstance(tile,dict) and "animal" in tile and not tile.get("fed_today",False) and int(tile.get("consecutive_unfed",0))>=1:
                endangered.append((x,y))
    if not endangered: return False,{"reason":"no_endangered_animals"}
    positions=_positions(farm); invs=copy.deepcopy(private.get("inventories") or [])
    covered=set()
    for i,a in enumerate(_units(action)):
        if not a or a[0] != "FEED" or i>=len(positions) or i>=len(invs): continue
        pos=tuple(positions[i][:2])
        if pos not in endangered or int(invs[i].get("WHEAT",0))<1: continue
        invs[i]["WHEAT"]-=1; covered.add(pos)
    if len(covered)!=len(set(endangered)):
        return False,{"reason":"uncovered_escape_risk","endangered":endangered,"covered":sorted(covered)}
    return True,{"endangered":endangered,"covered":sorted(covered)}


def precondition(macro, obs, cfg=None):
    cfg=cfg or {}; step=_step(obs,cfg)
    if step != int(macro["step"]): return False,{"reason":"wrong_step","expected":macro["step"],"actual":step}
    farm,private=_farm_private(obs)
    if farm is None: return False,{"reason":"missing_player_state"}
    family=macro["family"]; action=macro["action"]; turns=max(1,int(_cfg(cfg,"turnsPerDay",24)))
    if family=="reset":
        ok=(step+1)%turns==0
        return ok,{"next_day":step//turns+1}
    if family=="unlock":
        next_day=step//turns+1; interval=max(1,int(_cfg(cfg,"townShopUnlockInterval",3))); shops=list((obs.get("town") or {}).get("unlocked_shops") or [])
        ok=(step+1)%turns==0 and next_day>0 and next_day%interval==0 and len(shops)<MAX_SHOP_INSTANCES
        return ok,{"shops_before":len(shops),"next_day":next_day}
    if family=="hire": return _hire_exact(action,farm,cfg)
    if family=="pickup_drop": return _pickup_drop_exact(action,farm,private,cfg)
    if family=="maturity": return _maturity_exact(action,farm,private,cfg,step)
    if family=="escape": return _escape_exact(action,farm,private,cfg,step)
    if family=="settlement":
        slots=int(_cfg(cfg,"maxMarketOrdersPerTurn",10))
        ok=step==718 and len(action.get("market") or [])<=slots
        return ok,{"market_rows":len(action.get("market") or []),"slot_limit":slots}
    return False,{"reason":"unknown_family"}


def revalidate(macro, prior_info, prior_obs, next_obs, cfg=None):
    cfg=cfg or {}; family=macro["family"]
    if not isinstance(next_obs,dict): return False,{"reason":"missing_next_observation"}
    if family=="settlement":
        # A terminal action may not receive another live observation.
        return True,{"terminal":True}
    expected=int(macro["step"])+1
    if next_obs.get("step") is not None and int(next_obs["step"]) != expected:
        return False,{"reason":"unexpected_next_step","expected":expected,"actual":next_obs.get("step")}
    farm,private=_farm_private(next_obs)
    if farm is None: return False,{"reason":"missing_next_player_state"}
    if family=="reset":
        board=int(_cfg(cfg,"boardSize",10)); half=board//2; spawn=[half-1,half-1]
        ok=(list(farm.get("farmer") or [])==spawn and not (farm.get("hands") or []) and int(farm.get("hires_today",0))==0 and (private.get("inventories") or [])==[{}])
        return ok,{"spawn":spawn}
    if family=="unlock":
        before=int(prior_info.get("shops_before",-1)); after=len(list((next_obs.get("town") or {}).get("unlocked_shops") or []))
        return after==before+1,{"before":before,"after":after}
    if family=="hire":
        expected_hires=int(prior_info.get("expected_hires_today",-1))
        return int(farm.get("hires_today",-2))==expected_hires,{"expected_hires_today":expected_hires,"actual":farm.get("hires_today")}
    if family=="pickup_drop":
        before=prior_obs.get('private',{}).get('inventories') or []
        expected=prior_info.get('expected_inventories') or []
        actual=private.get('inventories') or []
        changed=[i for i,(a,b) in enumerate(zip(before,expected)) if a!=b]
        ok=bool(changed) and all(i<len(actual) and actual[i]==expected[i] for i in changed)
        return ok,{"target_actors":changed,"inventories_match":ok}
    # Harvest/escape are intentionally revalidated from structural event effect
    # rather than re-simulating unrelated unit actions in the same route row.
    if family=="maturity": return True,{"structural_revalidation":"next_step_only"}
    if family=="escape": return True,{"structural_revalidation":"next_step_only"}
    return False,{"reason":"unknown_family"}


def prefix_compatible_routes(routes, current, now):
    base=routes[current]
    return tuple(sorted(k for k,rows in routes.items() if k!=current and len(rows)>now and len(base)>now and all(base[t]==rows[t] for t in range(now))))

WEIGHTS={"escape":100,"settlement":100,"maturity":20,"pickup_drop":12,"hire":8,"unlock":2,"reset":1}

def score_route(route_id, step, obs, cfg, idx):
    fired=[]
    for macro in idx.get((route_id,step),()):
        ok,info=precondition(macro,obs,cfg)
        if ok: fired.append((macro,info))
    return sum(WEIGHTS[m["family"]] for m,_ in fired), fired


def rank_prefix_beam(routes,current,step,obs,cfg,idx):
    candidates=(current,*prefix_compatible_routes(routes,current,step))
    rows=[]
    for route in candidates:
        score,fired=score_route(route,step,obs,cfg,idx)
        rows.append({"route":route,"score":score,"macros":[m["id"] for m,_ in fired]})
    rows.sort(key=lambda r:(-r["score"], r["route"]))
    best=rows[0] if rows else {"route":current,"score":0,"macros":[]}
    current_row=next((r for r in rows if r["route"]==current),best)
    # A prior recommendation exists only for a strict score improvement.
    changed=best["route"]!=current and best["score"]>current_row["score"]
    return {"current":current,"winner":best["route"],"changed_recommendation":changed,"rows":rows}

def execution_preserved(macro, returned):
    """Whether the runtime-returned action still contains this route macro event.

    This is a post-transform admission gate. It is deliberately stricter than
    semantic equivalence: exact macro execution must remain visibly represented.
    """
    action=macro['action']; fam=macro['family']
    if not isinstance(returned,dict): return False
    ru=_units(returned); mu=_units(action)
    if fam in ('pickup_drop','maturity','escape'):
        if fam=='pickup_drop' and ru != mu:
            return False
        targets={'pickup_drop':{'PICKUP','DROP'},'maturity':{'HARVEST'},'escape':{'FEED'}}[fam]
        for i,a in enumerate(mu):
            if a and a[0] in targets:
                if i>=len(ru) or list(ru[i])!=list(a): return False
        return True
    if fam=='hire':
        want=sum(1 for o in action.get('market',[]) if o and o[0]=='HIRE')
        got=sum(1 for o in returned.get('market',[]) if o and o[0]=='HIRE')
        return want>0 and got==want
    # reset/unlock are engine boundaries independent of route transform;
    # settlement remains the exact terminal boundary even when SELL is optimized.
    return fam in ('reset','unlock','settlement')
