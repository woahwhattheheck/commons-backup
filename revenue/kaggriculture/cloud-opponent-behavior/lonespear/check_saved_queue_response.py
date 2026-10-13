"""Check the existing queue consumer on six retained reached-state cases.

Recorded rival private state is an OFFLINE label here, never a runtime inference.
No full game, policy call, source download, or new seed is used by this command.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path

import engine_cases
import queue_response

CASE_SHA256 = '3850381a54e1fcaf0c83a7073fce53787cae03b6f246fc1027c4f6724d200077'
QUEUE_BLOB = 'b95dff0010cf70941cc96e7f416798d36a8aa57d'
ENGINE_SHA256 = 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e'
HERE = Path(__file__).resolve().parent


def blob(path):
    raw = Path(path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def validate(cases_path, queue_path, engine_path):
    packed = Path(cases_path).read_bytes()
    if hashlib.sha256(packed).hexdigest() != CASE_SHA256:
        raise ValueError('Use the six retained IRIS development cases')
    if blob(queue_path) != QUEUE_BLOB:
        raise ValueError('Queue comparator differs from this recorded consumer pin')
    if hashlib.sha256(Path(engine_path).read_bytes()).hexdigest() != ENGINE_SHA256:
        raise ValueError('Market engine differs from the retained input pin')
    cases = json.loads(gzip.decompress(packed))
    queue = engine_cases.load(queue_path, 'iris_queue_validation')
    mechanics = queue.load_market_engine(engine_path)
    cfg = json.loads((HERE/'base-frame.json').read_text())['configuration']
    summaries = []
    complete = []
    comparisons = 0
    for case in cases:
        own = case['own']; rival = 1-own
        post = case['post_unit_observation']
        privates = case['offline_post_unit_privates']
        originals = case['original_actions']
        no_feed = copy.deepcopy(originals[rival])
        no_feed['market'] = [['PASS'] if isinstance(o,list) and len(o)==3 and o[:2]==['BUY_PRODUCT','WHEAT'] else o
                             for o in no_feed['market']]
        scenarios = [dict(id='recorded-rival',provenance='Original retained development label; private is evaluation-only',
                          farm=post['farms'][rival], private=privates[rival], action=originals[rival]),
                     dict(id='no-feed-intervention',provenance='Named intervention on the same retained queue, not an observed opponent action',
                          farm=post['farms'][rival], private=privates[rival], action=no_feed)]
        result = queue_response.evaluate_wheat_response(queue.compare_queues,mechanics,
            observation=case['observation'],configuration=cfg,selected_action=originals[own],
            own_farm=post['farms'][own],own_private=privates[own],market=post['market'],
            scenarios=scenarios,retained_wheat=0)
        if result['status']!='complete_conditional' or result['action_selected']:
            raise ValueError('Expected an unselected complete conditional comparison')
        if result['proposal_action']!=case['proposed_actions'][own] or result['fallback_action']!=originals[own]:
            raise ValueError('The supplied actions differ from the retained cases')
        for row in result['comparison']['scenario_results']:
            expected = case if row['id']=='recorded-rival' else case['no_feed_control']
            for got_name,expected_name in [('baseline','baseline'),('proposed','candidate')]:
                got = row[got_name]; want = expected[expected_name]
                for actual_key,original_key,position in [('own_farm','farms',own),('rival_farm','farms',rival),
                        ('own_private','privates',own),('rival_private','privates',rival)]:
                    if got[actual_key]!=want[original_key][position]:
                        raise ValueError(f'{case["trace"]} {row["id"]} {actual_key} differs')
                    comparisons += 1
                if got['market']!=want['market']:
                    raise ValueError('Complete shared market differs')
                comparisons += 1
        observed = result['comparison']['scenario_results'][0]['delta']
        for name in ('own_cash','rival_cash','relative_cash'):
            if observed[name] != case[name+'_delta']:
                raise ValueError('Retained paired cash delta differs')
        summaries.append(dict(trace=case['trace'],step=case['step'],own=own,
            recorded_delta={n:observed[n] for n in ('own_cash','rival_cash','relative_cash')},
            no_feed_delta={n:result['comparison']['scenario_results'][1]['delta'][n]
                           for n in ('own_cash','rival_cash','relative_cash')},
            bounds=result['comparison']['bounds'],action_selected=False))
        complete.append(dict(trace=case['trace'],result=result))
    return dict(schema='titan.lonespear-saved-queue-consumer.v1',new_scored_games=0,
        retained_cases=len(cases),conditional_rows=len(cases)*2,whole_state_comparisons=comparisons,
        source_blobs={p.name:blob(p) for p in [HERE/'queue_response.py',HERE/'behavior.py',Path(queue_path)]},
        cases_sha256=CASE_SHA256,engine_sha256=ENGINE_SHA256,
        results=summaries),complete


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('cases','queue-source','engine-source','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Use a new result directory')
    summary,complete=validate(args.cases,args.queue_source,args.engine_source)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'QUEUE-CONSUMER.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    (args.output/'complete-comparisons.json.gz').write_bytes(gzip.compress(json.dumps(complete,sort_keys=True,separators=(',',':'),allow_nan=False).encode(),mtime=0))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
