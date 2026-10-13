"""Verify saved coverage and cash arithmetic, without pricing or simulation."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from pathlib import Path
from exhaustive_cash_scan import canonical,prepare,path_at


def verify(scan:Path,s):
    run=json.loads((scan/'RUN.json').read_text())
    if not run['complete']:raise ValueError('Incomplete scan')
    expected={o.route_id:{(r['step'],r['slot']):r for r in o.orders} for o in s.offers}
    seen=set();settlements=0;cash_rows=0;groups={};invalid=0
    for shard in run['shards']:
        p=scan/'shards'/shard['file']
        if hashlib.sha256(p.read_bytes()).hexdigest()!=shard['sha256']:raise ValueError('Shard changed')
        count=0
        with gzip.open(p,'rt') as source:
            for line in source:
                record=json.loads(line);i=record['index'];count+=1
                if i in seen:raise ValueError('Repeated cell')
                seen.add(i)
                if record['path']!=list(path_at(i,s.shop_names,5)):raise ValueError('Wrong scenario identity')
                key=''.join('1' if name=='YARN_STORE' else '0' for name in record['path'])
                if key!=record['wool_signature']:raise ValueError('Wrong projected class')
                if [r['route_id'] for r in record['rows']]!=list(s.ids):raise ValueError('Wrong route order')
                for r in record['rows']:
                    orders=expected[r['route_id']]
                    values={};receipts=spend=0.0
                    for step,slot,delta,qty in r['settlements']:
                        if (step,slot) in values:raise ValueError('Repeated settlement')
                        order=orders[(step,slot)]['order']
                        if order[0] not in ('SELL','BUY_PRODUCT') or order[2]!=qty:raise ValueError('Wrong trade binding')
                        if (order[0]=='SELL' and delta<0) or (order[0]=='BUY_PRODUCT' and delta>0):raise ValueError('Wrong sign')
                        values[(step,slot)]=delta
                        if order[0]=='SELL':receipts+=delta
                        else:spend-=delta
                    cash=minimum=r['initial_cash'];fixed=0.0;first=None
                    for key_,order in sorted(orders.items()):
                        if order['order'][0] in ('SELL','BUY_PRODUCT'):
                            delta=values.pop(key_)
                        else:delta=order['delta'];fixed-=delta
                        cash+=delta;minimum=min(cash,minimum)
                        if cash<0 and first is None:first=list(key_)
                    if values:raise ValueError('Foreign dynamic settlement')
                    if (cash,minimum,first,receipts,spend,fixed)!=(r['final_marked_cash'],r['minimum_marked_cash'],r['first_negative'],r['own_receipts'],r['own_product_spend'],r['fixed_costs']):raise ValueError('Cash reconciliation failed')
                    if r['rival_receipts'] or r['rival_product_spend']:raise ValueError('Unrequested rival flow')
                    settlements+=len(r['settlements']);cash_rows+=1
                gain=record['rows'][1]['final_marked_cash']-record['rows'][0]['final_marked_cash']
                if gain!=record['paired_own_cash_change']:raise ValueError('Wrong paired gain')
                g=groups.setdefault(key,{'min':gain,'max':gain,'count':0})
                g['min']=min(g['min'],gain);g['max']=max(g['max'],gain);g['count']+=1
        if count!=shard['count'] or count!=shard['stop']-shard['start']:raise ValueError('Short shard')
    if seen!=set(range(8**5)):raise ValueError('Missing exact shop-identity cell')
    reported=json.loads((scan/'SUMMARY.json').read_text())
    for key,g in groups.items():
        want=reported['groups'][key]
        if (g['min'],g['max'],g['count'])!=(want['min_gain'],want['max_gain'],want['count']):raise ValueError('Summary mismatch')
    return {'complete':True,'identity_cells':len(seen),'cash_records_reconciled':cash_rows,
            'settlements_reconciled':settlements,'classes':len(groups),
            'sign_crossing_classes':[key for key,g in sorted(groups.items()) if g['min']<0<g['max']],
            'pricing_calls':0,'actor_calls':0,'engine_calls':0,'new_games':0,
            'scope':'saved source/order/quantity/cash/coverage verification, not an independent pricing model'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--scan',type=Path,required=True)
    ap.add_argument('--osprey-root',type=Path,required=True);ap.add_argument('--amber-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    s=prepare(a.osprey_root,a.amber_root);result=verify(a.scan,s)
    a.output.write_bytes(canonical(result)+b'\n');print(json.dumps(result,indent=2))
