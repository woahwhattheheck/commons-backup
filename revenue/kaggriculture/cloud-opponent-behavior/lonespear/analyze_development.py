"""Analyze original development traces and paired one-turn response cases.

Reconstructs inventory for OFFLINE receipt attribution only. Neither private
rival inventories nor recorded rival actions are inputs to behavior.predict.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import copy
import gzip
import hashlib
import json
from pathlib import Path

import behavior
import engine_cases
from extract_development import REF, ARCHIVE_SHA, NAMES


def encoded(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def after_units(engine, observation, private, actions):
    obs=copy.deepcopy(observation); priv=copy.deepcopy(private)
    for player,action in enumerate(actions):
        commands=[action.get('farmer',['PASS']),*action.get('hands',[])]
        demand=Counter(c[1] for c in commands if len(c)>1 and c[0]=='PLANT')
        blocked={p for p,q in demand.items() if q>priv[player]['seeds'].get(p,0)}
        for index,command in enumerate(commands):
            if len(command)>1 and command[0]=='PLANT' and command[1] in blocked:
                command=['PASS']
            engine._apply_unit_action(obs['farms'][player],priv[player],index,command,10,obs['day'],24,100)
    return obs,priv


def count_feed(orders):
    return sum(o[2] for o in orders if isinstance(o,list) and len(o)==3 and o[:2]==['BUY_PRODUCT','WHEAT'])


def one_trace(path,engine):
    with gzip.open(path,'rt') as f:
        rows=[json.loads(line) for line in f]
    private=[engine._new_private(),engine._new_private()]
    counts=Counter(); errors=[]; telemetry=[]; candidates=[]; partial_cases=[]; checked=hashlib.sha256()
    for index,row in enumerate(rows):
        checked.update(encoded(row)+b'\n')
        obs=row['observation']; own=row['candidate_seat']; rival=1-own
        if private[own]!=obs['private']:
            raise ValueError(f'Original own-private checkpoint differs: {path.name}:{index}')
        prediction=behavior.predict(obs,actor=rival)
        n=sum(o==['HIRE'] for o in row['actions'][rival]['market'])
        if prediction['status']!='known' or prediction['hire_requests']!=n:
            errors.append(dict(step=index,kind='request',prediction=prediction,label=n))
        post,post_private=after_units(engine,obs,private,row['actions'])
        actual=engine_cases.run_market(engine,post,post_private,row['actions'])
        if actual['after_cash']!=row['post_cash']:
            raise ValueError(f'Original cash transition differs: {path.name}:{index}')
        fills=sum(r['op']=='HIRE' and r['player']==rival and r['filled'] for r in actual['receipts'])
        feed=sum(r['op']=='BUY_PRODUCT' and r['item']=='WHEAT' and r['player']==rival and r['filled'] for r in actual['receipts'])
        requested_feed=count_feed(row['actions'][rival]['market'])
        counts.update(rows=1,hire_requests=n,hire_request_turns=int(n>0),hire_fills=fills,
                      feed_request_units=requested_feed,feed_filled_units=feed,
                      feed_request_turns=int(requested_feed>0),feed_partial_turns=int(feed<requested_feed),
                      hire_and_feed_turns=int(n>0 and requested_feed>0))
        if fills!=prediction['hire_prefix_fills']:
            errors.append(dict(step=index,kind='fill',prediction=prediction['hire_prefix_fills'],actual=fills))
        if not 0<=requested_feed<=prediction['feed_request_units']['upper']:
            errors.append(dict(step=index,kind='feed_interval',actual=requested_feed))
        if feed<requested_feed:
            partial_cases.append(dict(trace=path.name,step=index,actor=rival,prediction=prediction,
                requested=requested_feed,filled=feed,observation=obs,post_unit_observation=post,
                offline_post_unit_privates=post_private,actions=row['actions'],market_receipt=actual))
        hist=None
        if index+1<len(rows):
            hist=behavior.observed_fill(obs,rows[index+1]['observation'],actor=rival)
            if hist['status']=='known':
                counts['public_fill_checks']+=1
                if hist['fills']!=fills:
                    errors.append(dict(step=index,kind='public_fill',actual=fills,public=hist['fills']))
        telemetry.append(dict(step=index,actor=rival,prediction=prediction,
                              recorded_requests=n,actual_fills=fills,
                              recorded_feed_units=requested_feed,actual_feed_units=feed,
                              public_fill=hist))
        # One common reached decision chosen during development inspection; all three seeds/both seats.
        if index==697:
            proposal=behavior.propose_delayed_wheat_sale(row['actions'][own],prediction,
                       shed_wheat=post_private[own]['shed'].get('WHEAT',0),retained_wheat=0)
            if not proposal['changed']:
                raise ValueError('Chosen development discriminator did not activate')
            proposed=copy.deepcopy(row['actions']);proposed[own]=proposal['action']
            alternate=engine_cases.run_market(engine,post,post_private,proposed)
            delta=[alternate['after_cash'][i]-actual['after_cash'][i] for i in (0,1)]
            # A named no-feed intervention preserves all other recorded market text.
            no_feed=copy.deepcopy(row['actions'])
            no_feed[rival]['market']=[['PASS'] if isinstance(o,list) and len(o)==3 and o[:2]==['BUY_PRODUCT','WHEAT'] else o for o in no_feed[rival]['market']]
            no_feed_candidate=copy.deepcopy(no_feed);no_feed_candidate[own]=proposal['action']
            nf0=engine_cases.run_market(engine,post,post_private,no_feed)
            nf1=engine_cases.run_market(engine,post,post_private,no_feed_candidate)
            # Public predicate negatives use the same actual observation and no policy call.
            negatives=[]
            for name in ('late_hour','cash_threshold','already_staffed'):
                neg=copy.deepcopy(obs)
                if name=='late_hour':neg['hour']=3
                elif name=='cash_threshold':neg['farms'][rival]['money']=40
                else:neg['farms'][rival]['hands']=[[4,4]]*prediction['target_hands']
                pred=behavior.predict(neg,actor=rival)
                attempt=behavior.propose_delayed_wheat_sale(row['actions'][own],pred,
                              shed_wheat=post_private[own]['shed'].get('WHEAT',0),retained_wheat=0)
                negatives.append(dict(condition=name,prediction=pred,changed=attempt['changed']))
            candidates.append(dict(trace=path.name,step=index,own=own,
                observation=obs,post_unit_observation=post,offline_post_unit_privates=post_private,
                original_actions=row['actions'],proposed_actions=proposed,proposal=proposal,
                baseline=actual,candidate=alternate,own_cash_delta=delta[own],
                rival_cash_delta=delta[rival],relative_cash_delta=delta[own]-delta[rival],
                private_result_equal=actual['privates']==alternate['privates'],
                market_inventory_equal=actual['market']['inventory']==alternate['market']['inventory'],
                no_feed_control=dict(baseline=nf0,candidate=nf1,
                    cash_deltas=[nf1['after_cash'][i]-nf0['after_cash'][i] for i in (0,1)]),
                public_negative_controls=negatives))
        private=actual['privates']
        if (index+1)%24==0:
            for priv in private:
                engine._drop_inventories_to_shed(priv,100)
                priv['inventories']=[{}]
    return dict(trace=path.name,semantic_sha256=checked.hexdigest(),counts=dict(counts),
                mismatches=errors,telemetry=telemetry,cases=candidates,partial_feed_cases=partial_cases)


def analyze(inputs,output,evaluator,engine_cache):
    ev=engine_cases.load(evaluator,'iris_behavior_evaluator');engine,hashes=ev.get_engine(engine_cache)
    index=json.loads((inputs/'INPUTS.json').read_text())
    if index.get('source_ref')!=REF or index.get('archive_sha256')!=ARCHIVE_SHA or sorted(i['original_member'] for i in index['traces'])!=sorted(NAMES):
        raise ValueError('Analysis expects exactly the preselected development records')
    output.mkdir(parents=True,exist_ok=False)
    reports=[];cases=[];partial_cases=[]
    for item in index['traces']:
        path=inputs/item['decoded_file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['decoded_gzip_sha256']:
            raise ValueError('Selected original trace changed')
        report=one_trace(path,engine)
        if report['semantic_sha256']!=item['semantic_sha256']:
            raise ValueError('Analysis trace does not match original manifest')
        data=b''.join(encoded(r)+b'\n' for r in report.pop('telemetry'))
        name=path.name.replace('.jsonl.gz','-public-predictions.jsonl.gz')
        (output/name).write_bytes(gzip.compress(data,mtime=0))
        report.update(telemetry=name,telemetry_sha256=hashlib.sha256((output/name).read_bytes()).hexdigest())
        cases.extend(report.pop('cases'));partial_cases.extend(report.pop('partial_feed_cases'));reports.append(report)
        print(json.dumps(dict(trace=report['trace'],counts=report['counts'],mismatches=len(report['mismatches']))),flush=True)
    totals=Counter()
    for report in reports:totals.update(report['counts'])
    summaries=[{k:case[k] for k in ('trace','step','own','own_cash_delta','rival_cash_delta','relative_cash_delta',
                 'private_result_equal','market_inventory_equal')} for case in cases]
    summary=dict(schema='titan.lonespear-behavior-analysis.v1',source_ref=behavior.SOURCE_REF,
        source_sha256=behavior.SOURCE_SHA256,input_ref=index['source_ref'],engine_ref=ev.ENGINE_REF,
        engine_sha256=hashes,counts=dict(totals),records=reports,paired_market_cases=summaries,
        new_scored_games=0,seeds_consumed=0,independent_development_seeds=3,
        source_files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(behavior.__file__),Path(engine_cases.__file__),Path(__file__))},
        partial_feed_events=[{k:c[k] for k in ('trace','step','actor','requested','filled')} for c in partial_cases],
        interpretation='Recorded development-state analysis; paired turn interventions, not full-game outcomes or a policy promotion.')
    (output/'RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n')
    (output/'cases.json.gz').write_bytes(gzip.compress(encoded(cases),mtime=0))
    (output/'partial-feed.json.gz').write_bytes(gzip.compress(encoded(partial_cases),mtime=0))
    print(json.dumps(summaries,indent=2))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('inputs','output','evaluator','engine'):
        p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();report=analyze(a.inputs,a.output,a.evaluator,a.engine)
    raise SystemExit(int(any(r['mismatches'] for r in report['records'])))
