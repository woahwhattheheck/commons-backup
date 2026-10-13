#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose scheduler-prefix with fail-closed represented market executability.

This is a source-only V4 materializer.  It first executes the exact canonical
scheduler-prefix materializer from captured bytes, then changes only
SellScheduler.receipt_profile(): represented BUY_PRODUCT / BUY_ANIMAL / HIRE
state is admitted only when physical execution is provable from the bound
one-player prestate.  Ambiguous arrival state makes the feasibility predicate
fail closed rather than silently undercounting capacity.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

RAW_SCHEDULER_GIT_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
PREFIX_MATERIALIZER_GIT_BLOB = "f36e9120ea07c861a7eca5821a5306c6dbfa4613"

CLASS_ANCHOR = "\n\nclass SellScheduler:\n"
STRICT_HEAD_OLD = """\
        now=int(obs['step']);cap=int(config.get('shedCapacity',100))
        # Re-run the current unit stage without a shed cap only for feasibility.
"""
STRICT_HEAD_NEW = """\
        if not isinstance(obs,dict) or not isinstance(config,dict):
            return lambda _plan: False
        now_value=obs.get('step')
        cap_value=config.get('shedCapacity',100)
        turns_value=config.get('turnsPerDay',24)
        mult_value=config.get('farmHandCostMult',1)
        market_cap_value=config.get('maxMarketOrdersPerTurn',10)
        if type(now_value) is not int or now_value<0:
            return lambda _plan: False
        if type(cap_value) is not int or cap_value<0:
            return lambda _plan: False
        if type(turns_value) is not int or turns_value<=0:
            return lambda _plan: False
        if type(mult_value) is not int or mult_value<0:
            return lambda _plan: False
        if type(market_cap_value) is not int:
            return lambda _plan: False
        now=now_value;cap=cap_value
        # Re-run the current unit stage without a shed cap only for feasibility.
"""

PROFILE_INIT_OLD = """\
        profile=[]
        route=self.controller.R[self.controller.cur]
"""
PROFILE_INIT_NEW = """\
        profile=[]
        transition_state={'funding_exact':True,'market_exact':True}
        route=self.controller.R[self.controller.cur]
"""

PHYSICAL_BLOCK_OLD = """\
            market_action=base if t==now else (route[t] if t<len(route) else parent.PASS)
            orders=_engine_market_prefix(market_action,config)
            for o in orders:
                if not o:continue
                if o[0]=='SELL' and o[1]!=item:
                    p['shed'][o[1]]=max(0,p['shed'].get(o[1],0)-int(o[2]))
                elif o[0] in ('BUY_PRODUCT','BUY_ANIMAL') and len(o)>2:
                    p['shed'][o[1]]=p['shed'].get(o[1],0)+int(o[2])
                elif o[0]=='HIRE':
                    f['hands'].append(m._spawn_hand(f,len(f['tiles'])));p['inventories'].append({})
"""
PHYSICAL_BLOCK_NEW = """\
            market_action=base if t==now else (route[t] if t<len(route) else parent.PASS)
            orders=_engine_market_prefix(market_action,config)
            physical=_represented_market_physical_transition(
                f,p,obs.get('market'),orders,config,item,transition_state)
            if not physical.get('resolved',False):
                return lambda _plan: False
            # The next market index/turn is not source-bound to the same public
            # inventory because the rival row/town transition is unavailable.
            transition_state['market_exact']=False
"""

CANDIDATE_HELPER = r'''
def _represented_market_physical_transition(farm,private,market,orders,config,target_item,state):
    """Mutate only source-provable represented physical market effects."""
    def unresolved(reason):
        return {'resolved':False,'reason':reason}
    if not isinstance(farm,dict) or not isinstance(private,dict) or not isinstance(state,dict):
        return unresolved('bad_state')
    shed=private.get('shed');inventories=private.get('inventories')
    hands=farm.get('hands');tiles=farm.get('tiles')
    if not isinstance(shed,dict) or not isinstance(inventories,list):
        return unresolved('bad_private')
    if not isinstance(hands,list) or not isinstance(tiles,list):
        return unresolved('bad_farm')
    cap=config.get('shedCapacity',100) if isinstance(config,dict) else None
    mult=config.get('farmHandCostMult',1) if isinstance(config,dict) else None
    if type(cap) is not int or cap<0:return unresolved('bad_shed_capacity')
    if type(mult) is not int or mult<0:return unresolved('bad_hire_mult')
    for value in shed.values():
        if type(value) is not int or value<0:return unresolved('bad_shed_count')
    if len(inventories)!=1+len(hands):return unresolved('inventory_actor_mismatch')
    money=farm.get('money')
    if isinstance(money,bool) or not isinstance(money,(int,float)) or not math.isfinite(float(money)) or money<0:
        return unresolved('bad_money')
    if type(state.get('funding_exact')) is not bool or type(state.get('market_exact')) is not bool:
        return unresolved('bad_transition_state')
    if not isinstance(orders,list):return unresolved('bad_orders')
    def shed_total():return sum(shed.values())
    for row_index,order in enumerate(orders):
        quote_exact=state['market_exact']
        # Even an empty own slot can be paired with a rival market row, so only
        # the first current-prefix quote is authenticated by this prestate.
        state['market_exact']=False
        if not order:continue
        if not isinstance(order,(list,tuple)) or not isinstance(order[0],str):
            return unresolved(f'bad_order:{row_index}')
        op=order[0]
        if op=='SELL':
            if len(order)<3:return unresolved(f'bad_sell:{row_index}')
            item,qty=order[1],order[2]
            if not isinstance(item,str):return unresolved(f'bad_sell_item:{row_index}')
            if type(qty) is not int:return unresolved(f'coerced_sell_qty:{row_index}')
            if qty<=0 or item not in m.PRODUCTS:continue
            available=shed.get(item,0)
            if type(available) is not int or available<0:return unresolved(f'bad_sell_stock:{row_index}')
            sold=min(qty,available)
            if sold<=0:continue
            if item!=target_item:shed[item]=available-sold
            # SELL credit is deliberately not added. The unchanged money remains
            # a sound lower bound, so later fixed-cost effects may use pre-SALE
            # cash without trusting unproved receipts.
            state['funding_exact']=False
            continue
        if op=='BUY_PRODUCT':
            if len(order)<3:return unresolved(f'bad_buy_product:{row_index}')
            item,qty=order[1],order[2]
            if not isinstance(item,str):return unresolved(f'bad_buy_product_item:{row_index}')
            if type(qty) is not int:return unresolved(f'coerced_buy_product_qty:{row_index}')
            if qty<=0:continue
            if item not in ('WHEAT','FERTILIZER'):continue
            if shed_total()>=cap:continue
            money=farm.get('money')
            if isinstance(money,bool) or not isinstance(money,(int,float)) or not math.isfinite(float(money)) or money<0:
                return unresolved(f'bad_money:{row_index}')
            if not quote_exact:
                if state['funding_exact'] and money<1:continue
                return unresolved(f'buy_product_quote_unknown:{row_index}')
            if not isinstance(market,dict) or not isinstance(market.get('inventory'),dict):
                return unresolved(f'bad_market:{row_index}')
            inv=market['inventory'].get(item)
            if type(inv) is not int:return unresolved(f'bad_market_item_inventory:{row_index}')
            try:price=m.market_price(item,inv-1,market.get('params'))
            except Exception:return unresolved(f'bad_market_price:{row_index}')
            if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(float(price)) or price<1:
                return unresolved(f'bad_market_quote:{row_index}')
            if money<price:
                if state['funding_exact']:continue
                return unresolved(f'buy_product_funding_unknown:{row_index}')
            farm['money']=money-price;shed[item]=shed.get(item,0)+1
            if qty>1:
                # After the first lockstep unit, the rival commit can change the
                # next quote. Capacity or exact sub-floor cash can still prove a
                # deterministic stop; uncertain SELL credit cannot.
                if shed_total()>=cap:continue
                if state['funding_exact'] and farm['money']<1:continue
                return unresolved(f'buy_product_tail_unknown:{row_index}')
            continue
        if op=='BUY_ANIMAL':
            if len(order)<3:return unresolved(f'bad_buy_animal:{row_index}')
            item,qty=order[1],order[2]
            if not isinstance(item,str):return unresolved(f'bad_buy_animal_item:{row_index}')
            if type(qty) is not int:return unresolved(f'coerced_buy_animal_qty:{row_index}')
            if qty<=0 or item not in m.ANIMALS:continue
            if shed_total()>=cap:continue
            spec=m.ANIMALS.get(item);cost=spec.get('cost') if isinstance(spec,dict) else None
            if type(cost) is not int or cost<0:return unresolved(f'bad_animal_cost:{row_index}')
            for _ in range(qty):
                if shed_total()>=cap:break
                if farm['money']<cost:
                    if state['funding_exact']:break
                    return unresolved(f'buy_animal_funding_unknown:{row_index}')
                farm['money']-=cost;shed[item]=shed.get(item,0)+1
            continue
        if op=='HIRE':
            hires=farm.get('hires_today')
            if type(hires) is not int or hires<0:return unresolved(f'bad_hires_today:{row_index}')
            try:cost=m._hire_cost(hires,mult)
            except Exception:return unresolved(f'bad_hire_cost:{row_index}')
            if type(cost) is not int or cost<0:return unresolved(f'bad_hire_cost:{row_index}')
            if farm['money']<cost:
                if state['funding_exact']:continue
                return unresolved(f'hire_funding_unknown:{row_index}')
            farm['money']-=cost;farm['hires_today']=hires+1
            farm['hands'].append(m._spawn_hand(farm,len(farm['tiles'])))
            private['inventories'].append({})
            continue
        if op in ('BUY_SEED','BUY_LAND'):
            # Their exact debit is outside this physical-arrival seam. Zero is a
            # sound lower bound, so unmodeled spending cannot fund a later effect.
            state['funding_exact']=False
            farm['money']=0
            continue
    return {'resolved':True,'reason':'ok'}
'''


class MaterializationError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise MaterializationError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def _prefix_namespace(prefix_bytes: bytes) -> dict:
    if git_blob_sha(prefix_bytes) != PREFIX_MATERIALIZER_GIT_BLOB:
        raise MaterializationError("scheduler-prefix materializer Git blob mismatch")
    namespace = {"__name__": "_bound_scheduler_prefix_materializer"}
    exec(compile(prefix_bytes.decode("utf-8"), "<bound-scheduler-prefix>", "exec"), namespace)
    if namespace.get("SOURCE_GIT_BLOB") != RAW_SCHEDULER_GIT_BLOB:
        raise MaterializationError("scheduler-prefix source pin drift")
    if namespace.get("ENGINE_GIT_BLOB") != ENGINE_GIT_BLOB:
        raise MaterializationError("scheduler-prefix engine pin drift")
    if not callable(namespace.get("materialize")):
        raise MaterializationError("scheduler-prefix materialize() missing")
    return namespace


def transform_prefixed(source: str) -> str:
    if source.count("def _engine_market_prefix(") != 1:
        raise MaterializationError("canonical scheduler-prefix helper missing/ambiguous")
    if "def _represented_market_physical_transition(" in source:
        raise MaterializationError("represented physical helper already present")
    out = _replace_once(source, CLASS_ANCHOR, "\n\n" + CANDIDATE_HELPER.strip("\n") + CLASS_ANCHOR,
                        "SellScheduler helper insertion")
    out = _replace_once(out, STRICT_HEAD_OLD, STRICT_HEAD_NEW, "receipt strict config")
    out = _replace_once(out, PROFILE_INIT_OLD, PROFILE_INIT_NEW, "transition state init")
    out = _replace_once(out, PHYSICAL_BLOCK_OLD, PHYSICAL_BLOCK_NEW, "receipt physical transition")
    if out.count("def _represented_market_physical_transition(") != 1:
        raise MaterializationError("represented helper cardinality drift")
    if out.count("orders=_engine_market_prefix(market_action,config)") != 2:
        raise MaterializationError("scheduler-prefix consumer cardinality drift")
    if "p['shed'][o[1]]=p['shed'].get(o[1],0)+int(o[2])" in out:
        raise MaterializationError("phantom purchase projection survived")
    if "f['hands'].append(m._spawn_hand(f,len(f['tiles'])));p['inventories'].append({})" in out:
        raise MaterializationError("phantom HIRE projection survived")
    ast.parse(out, filename="<v4-represented-physical-transition>")
    return out


def materialize(source_bytes: bytes, engine_bytes: bytes, prefix_bytes: bytes) -> bytes:
    if git_blob_sha(source_bytes) != RAW_SCHEDULER_GIT_BLOB:
        raise MaterializationError("raw scheduler Git blob mismatch")
    if git_blob_sha(engine_bytes) != ENGINE_GIT_BLOB:
        raise MaterializationError("official engine Git blob mismatch")
    prefix = _prefix_namespace(prefix_bytes)
    prefixed = prefix["materialize"](source_bytes, engine_bytes)
    return transform_prefixed(prefixed.decode("utf-8")).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--prefix-materializer", type=Path, required=True)
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    engine_bytes = args.engine.read_bytes()
    prefix_bytes = args.prefix_materializer.read_bytes()
    candidate = materialize(source_bytes, engine_bytes, prefix_bytes)
    resolved = {args.source.resolve(strict=False), args.engine.resolve(strict=False),
                args.prefix_materializer.resolve(strict=False)}
    if args.output.resolve(strict=False) in resolved:
        raise MaterializationError("output must not alias a bound input")
    with args.output.open("xb") as stream:
        stream.write(candidate)
    if args.source.read_bytes() != source_bytes:
        raise MaterializationError("raw scheduler changed during materialization")
    if args.engine.read_bytes() != engine_bytes:
        raise MaterializationError("engine changed during materialization")
    if args.prefix_materializer.read_bytes() != prefix_bytes:
        raise MaterializationError("scheduler-prefix materializer changed during materialization")
    if args.output.read_bytes() != candidate:
        raise MaterializationError("output readback mismatch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())