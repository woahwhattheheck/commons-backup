# SPDX-License-Identifier: Apache-2.0
"""Reconstruct the v1 reached decision from retained causal windows only."""
import gzip
import json
from pathlib import Path

from dependencies import HERE,load,receipt_source,official_engine
from history_streams import bounded_history_streams
from tables import receipt_table
from solver import solve_table
from engine_cases import verify_table


def case(engine_dir):
    path=HERE/'results/development/mixed-9872019-sell-0.json.gz'
    game=json.loads(gzip.decompress(path.read_bytes()))
    event=game['activation_events'][0]
    saved=event['metadata']['activation'];window=saved['window'];prediction=saved['prediction']
    now,end=window['now'],window['end'];item=window['item']
    flow=load(HERE.parent/'cloud-market-response/flow.py','t15_causal_flow')
    history=flow.FlowHistory();records={}
    for prior in prediction['windows']:
        lag=prior['lag'];values=dict(prior['stream'])
        for t in range(prior['training_start'],prior['training_end']+1):
            q=values.get(t+lag*24,0)
            assert t<now
            if t in records:assert records[t]==q
            records[t]=q
    for t,q in sorted(records.items()):history.add(flow.FlowInterval(t,item,q,q,q,q,'identified'))
    historical,_=history.scenarios(item,now,end)
    chosen=bounded_history_streams(historical,32-window['learned_start'])
    assert chosen
    observation=event['observation'];source=receipt_source()
    model=source.MarketPath(item,observation['market']['inventory'][item],observation['market'].get('params'),
                           observation['town']['unlocked_shops'],{},now,end)
    plans=window['plans'];streams=[(name,tuple(tuple(x) for x in orders),alignment)
                                  for name,orders,alignment in saved['streams']+chosen]
    deltas,receipts=receipt_table(model,plans,window['quantity'],streams)
    answer=solve_table(deltas)
    context={'item':item,'quantity':window['quantity'],'inventory':observation['market']['inventory'][item],
             'shops':observation['town']['unlocked_shops'],'now':now,'end':end,
             'plans':[p['sales'] for p in plans],'streams':streams,'table':deltas}
    ev,engine,hashes=official_engine(engine_dir)
    verified=verify_table(ev,engine,context)
    result={'source':str(path.relative_to(HERE)),'observed_step':now,
            'latest_training_step':max(records),'original_history_columns':len(saved['streams'])-window['learned_start'],
            'retained_history_columns':chosen,'original_solution':saved['commitment']['solution'],
            'corrected_solution':answer,'corrected_receipts':receipts,'engine_sha256':hashes,
            'official':verified,'interpretation':'The v1 endpoint gain is retained. This corrected causal table does not support promotion of that timing choice.'}
    output=HERE/'results/reached-causal-case.json.gz'
    output.write_bytes(gzip.compress((json.dumps(result,indent=2)+'\n').encode(),mtime=0))
    print(json.dumps({k:result[k] for k in ('observed_step','latest_training_step','original_history_columns','retained_history_columns','original_solution','corrected_solution')}))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--engine-dir',required=True);a=p.parse_args();case(a.engine_dir)
