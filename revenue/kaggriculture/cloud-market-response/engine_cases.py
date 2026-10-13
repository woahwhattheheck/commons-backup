# SPDX-License-Identifier: MIT
"""Discriminating actual-engine SELL queue cases, not mock engine outcomes."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import policy


def run(engine_dir):
    spec = importlib.util.spec_from_file_location('t12_case_evaluator', HERE.parent/'cloud-eval/evaluate.py')
    ev = importlib.util.module_from_spec(spec); spec.loader.exec_module(ev)
    engine, hashes = ev.get_engine(engine_dir)
    results = []
    for item in policy.frozen_module().PRODUCTS:
        lo, hi = 10000, 20000
        while engine.market_price(item, hi) > 1:
            hi *= 2
        while lo < hi:
            mid = (lo+hi)//2
            if engine.market_price(item, mid) > 1: lo = mid+1
            else: hi = mid
        for inventory in (9800, 10000, lo-1, lo):
            for alignment in ('paired','before','after'):
                for duplicate in (False, True):
                    own_slot, rival_slot = ((1,0) if alignment=='before' else
                                           (0,1) if alignment=='after' else (0,0))
                    own = [['PASS']]*own_slot + [['SELL',item,7]]
                    rival = [['PASS']]*rival_slot + [['SELL',item,5]]
                    if duplicate:
                        own += [[], ['SELL',item,4]]
                        rival += [[], ['SELL',item,9]]
                    stocks = [{item:10}, {item:11}]
                    inv = {p:inventory if p==item else 10000 for p in engine.PRODUCTS}
                    farms = [ev.Struct(money=0), ev.Struct(money=0)]
                    market = ev.Struct(inventory=copy.deepcopy(inv), prices={p:0 for p in inv})
                    state = [ev.Struct(observation=ev.Struct(market=market,farms=farms,
                                private=ev.Struct(shed=copy.deepcopy(stocks[s]))),
                                action={'market':[own,rival][s]}) for s in (0,1)]
                    env = ev.Struct(configuration=ev.Struct(shedCapacity=100,maxMarketOrdersPerTurn=10))
                    expected = policy.sorrel.simulate_sell_turn(inv,own,rival,stocks[0],stocks[1],engine.market_price)
                    engine._process_market(state,env)
                    actual_cash = [f.money for f in farms]
                    actual_stock = [s.observation.private.shed for s in state]
                    assert actual_cash == expected['cash']
                    assert actual_stock == expected['stock']
                    assert market.inventory == expected['inventory']
                    results.append({'product':item,'inventory':inventory,'alignment':alignment,
                                    'duplicate_orders':duplicate,'cash':actual_cash,
                                    'market_supply':expected['market_supply_units'],
                                    'stock':actual_stock})
    output = {'case_count':len(results), 'engine_sha256':hashes,
              'sorrel_sha256':hashlib.sha256((HERE/'vendor/sorrel_adapter.py').read_bytes()).hexdigest(),
              'passed':True,'cases':results}
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--engine-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    result=run(a.engine_dir);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'case_count':result['case_count']}))
