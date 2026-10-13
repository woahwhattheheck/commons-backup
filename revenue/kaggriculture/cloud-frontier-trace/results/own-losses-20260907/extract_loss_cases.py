"""Extract two public loss witnesses from existing frontier-trace outputs (offline).

Run analyze.py and moments.py first into INPUT using {episode}-trace.json and
{episode}-moments.json, retaining episode-{episode}-replay.json. No agent code or
network is used. Replay lookahead is evidence for offline study, never runtime input.
"""
import argparse, collections, gzip, hashlib, json, sys
from pathlib import Path
TRACE = Path(__file__).resolve().parents[2]
# When run from the study scratch directory, pass --parser-dir explicitly.

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')

def build(inp, out, parser_dir):
    sys.path.insert(0,str(parser_dir))
    import analyze, summarize
    out.mkdir(parents=True,exist_ok=True)
    result={'scope':'Two selected PUBLIC competitive losses; offline recorded-action study',
        'parser_ref':'256b71ffbf960f944715179bc93baa1851003a6f',
        'own_submission_id':56074364,'own_archive_sha256':'79b407d699b5fd39e7b396de8b6fc79b2bc2fb99f427f7e2e7ecd25fbc71fb0b',
        'episodes':[]}
    action_signatures=[]
    selected=[0,24,34,129,144,265,268,272,276,280,480,481,503,504,505,718]
    for eid,rival in [(106468976,56077421),(106492506,56078905)]:
        replay,source=analyze.load_replay(inp/f'episode-{eid}-replay.json')
        trace=json.loads((inp/f'{eid}-trace.json').read_text())
        moments=json.loads((inp/f'{eid}-moments.json').read_text())
        assert source['transport_sha256']==trace['source']['transport_sha256']
        assert trace['transition_statuses']=={'RECONCILED':719}
        summary=summarize.summarize(trace)
        seats=[]
        for seat in [0,1]:
            s=summary['seats'][seat];assert s['cash_identity_residual']==0
            labor=collections.Counter();floor=collections.Counter();buys=collections.Counter()
            for row in moments['labor_by_day']:
                if row['seat']==seat:labor.update({k:v for k,v in row.items() if k not in ('seat','day')})
            for row in trace['transitions']:
                for e in row['audit']['events']:
                    if e['seat']!=seat or e['kind']!='trade' or not e['success']:continue
                    if e['op']=='SELL' and e['quoted_price']==1:floor[e['item']]+=1
                    if e['op']=='BUY_PRODUCT':buys[e['item']]-=e['cash_delta']
            seats.append({k:s[k] for k in ['seat','opening_cash','terminal_cash','gross_sales','spending','cash_identity_residual','sales','feed_consumed','totals']} | {'labor':dict(labor),'floor_price_sales_units':dict(floor),'product_buy_costs':dict(buys)})
        cases=[];witnesses=[]
        for step in selected:
            row=trace['transitions'][step];before=analyze.observations(replay['steps'][step]);after=analyze.observations(replay['steps'][step+1])
            assert row['action_step']==step and row['actions']==[s['action'] for s in analyze.frame_rows(replay['steps'][step+1])]
            cases.append({'action_step':step,'shops_before':before[0]['town']['unlocked_shops'],
                'market_before':before[0]['market'],'market_after':after[0]['market'],
                'farms_before':[analyze.farm_snapshot(f) for f in before[0]['farms']],
                'farms_after':row['farms_after'],'private_before':[o['private'] for o in before],
                'actions':row['actions'],'audit':row['audit']})
            witnesses.append({'action_step':step,'raw_frame_before':replay['steps'][step], 'raw_frame_after':replay['steps'][step+1]})
        witness=f'{eid}-raw-cases.json.gz'
        (out/witness).write_bytes(gzip.compress(json.dumps(witnesses,separators=(',',':'),ensure_ascii=False).encode(),mtime=0))
        (out/f'{eid}-cases.json.gz').write_bytes(gzip.compress(json.dumps(cases,separators=(',',':'),ensure_ascii=False).encode(),mtime=0))
        result['episodes'].append({'episode_id':eid,'visibility':'PUBLIC','rival_submission_id':rival,'own_seat':1,'rival_seat':0,
            'players':trace['players'],'retrieval':json.loads((inp/f'{eid}-retrieval.json').read_text()),
            'source':trace['source'],'engine_ref':trace['engine_ref'],'transition_statuses':trace['transition_statuses'],
            'seats':seats,'daily':trace['daily'],'installs_by_step':[s['installs_by_step'] for s in summary['seats']],
            'witness_file':witness,'selected_action_steps':selected})
        action_signatures.append([{k:r['actions'][1].get(k) for k in ('farmer','hands')} for r in trace['transitions']])
    result['own_unit_actions_equal_all_719_steps']=action_signatures[0]==action_signatures[1]
    (out/'observed-results.json.gz').write_bytes(gzip.compress(json.dumps(result,separators=(',',':'),ensure_ascii=False).encode(),mtime=0))
    write(out/'manifest.json',{'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.name!='manifest.json'},'runtime_use':'No future replay state, actions, prices, or shop draws may be runtime agent inputs.'})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--parser-dir',type=Path,default=TRACE)
    a=p.parse_args();build(a.input,a.output,a.parser_dir)
