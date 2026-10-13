# SPDX-License-Identifier: Apache-2.0
"""Executable caller example; fixture replay and inference features stay separate."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]/'cloud-market-forecast'))
from forecast_market_mechanics import market_price,SHOPS,TOWN_CENTER_PRODUCTS
from adapter import infer_rival_flow,supply_scenarios,score_paired_plans

def main():
    # Only the redacted live_input enters inference. The evaluation-only seed,
    # rival actions and fill cap are deliberately not used by this example.
    fixture=json.loads((HERE/'fixtures.json').read_text())['fixtures'][0]
    live=fixture['live_input'];cfg=live['configuration']
    quote=lambda p,i:market_price(p,i,live['before']['market'].get('params'))
    history=infer_rival_flow(**live,quote=quote,shops=SHOPS,center_products=TOWN_CENTER_PRODUCTS)
    obs=live['after'];now=obs['step']
    scenarios=supply_scenarios(obs,cfg,'CARROT',now+1,[history])
    # A caller-provided, hypothetical own post-unit stock and two feasible sales.
    # These ten units are example inputs, NOT inferred production or actual stock.
    scores=score_paired_plans(obs,cfg,{'CARROT':10},{now:[['SELL','CARROT',10]]},
        {now+1:[['SELL','CARROT',10]]},scenarios,now+1,quote=quote,shops=SHOPS,center_products=TOWN_CENTER_PRODUCTS)
    print(json.dumps({'identified_carrot':history['products']['CARROT'],
                      'scenario_assumptions':scenarios,
                      'paired_receipt_vector':[{k:v for k,v in e.items() if k not in ('baseline','candidate')} for e in scores['evaluations']]},indent=2))
if __name__=='__main__':main()
