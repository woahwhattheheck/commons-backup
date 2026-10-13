# SPDX-License-Identifier: Apache-2.0
"""Exercise shared-prefix reuse using the existing RILL retained source package.

No network, new game, seed bank or policy selection. The natural check restores
one already-recorded actor prefix and compares new modeled tails with the saved
RILL report; original models are not run again.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent

def load(name, path):
    raw = Path(path).read_bytes()
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    exec(compile(raw, str(path), 'exec'), mod.__dict__)
    return mod

def blob(path):
    raw=Path(path).read_bytes()
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def setup(root):
    root=Path(root).resolve()
    original=root/'TITAN-KESTREL-replay-deadline-PR10113/physical_replay.py'
    oracle_path=root/'titan-joint-sell-tail-value-evidence-20260907/dependencies/oracle.py'
    assert blob(original)=='e299275048d241602541e3329631f169e4de7634'
    assert blob(oracle_path)=='49640c27862d3d132c828fbafc6a8b4957527736'
    tree=root/'TITAN-DELVE-funded-seed-evidence/source/tree/revenue/kaggriculture'
    ev=load('osprey_prefix_evaluator',tree/'cloud-eval/evaluate.py')
    engine,hashes=ev.get_engine(root/'TITAN-DELVE-funded-seed-evidence/engine/engine',prepare=False)
    report=json.loads((root/'work/reached-final.json').read_text())
    assert hashes==report['validation']['engine_sha256']
    return SimpleNamespace(root=root,engine=engine,engine_hashes=hashes,
        original=load('osprey_prefix_original',original),
        current=load('osprey_prefix_current',HERE/'physical_replay.py'),
        oracle=load('osprey_prefix_oracle',oracle_path), reference=report,
        obs=report['validation']['input_row']['observation'],
        cfg=report['validation']['configuration'])

def natural(c, *, seconds=180):
    r=c.root
    rt=r/'original-runtime/revenue/kaggriculture'
    sys.path[:0]=[str(rt/'cloud-integration-differentials'),str(rt/'cloud-execution-lab')]
    restore=load('osprey_prefix_restore',r/'work/revenue/kaggriculture/cloud-capital-physical-replay/reached_integrated.py')
    tail=load('osprey_prefix_tail',r/'titan-joint-sell-tail-value-evidence-20260907/source/sell_tail_value.py')
    factory=load('osprey_prefix_factory',rt/'cloud-integration-differentials/funded_main.py')
    random.seed(restore.ACTOR_SEED)
    actor=factory.make_agent(funded=False)
    raw=gzip.decompress((r/'TITAN-TRACE-DELVE-control-inputs/candidate-inputs.jsonl.gz').read_bytes())
    rows=[json.loads(line) for line in raw.splitlines()]
    row,receipt=restore.restore_prefix(actor,rows)
    before=restore.state_digest(actor)
    input_before=deepcopy(row)
    facade=tail.SellRouteView(actor,row['configuration'])
    def fork(view):
        return tail.SellRouteView(restore.fork_integrated(view.scheduler),view.configuration)
    scenarios={name:c.oracle.Scenario(**{
        key:({int(step):val for step,val in value.items()} if key!='label' else value)
        for key,value in scenario.items()}) for name,scenario in c.reference['replay']['scenarios'].items()}
    result=c.current.replay_routes(facade,(restore.MAIN,restore.SHEEP),row['observation'],row['configuration'],
        c.engine,c.oracle.simulate_bundle,scenarios=scenarios,end_step=718,
        fork_controller=fork,limits=c.current.ReplayLimits(seconds=seconds,decisions=1972),reuse_scenario_prefixes=True)
    expected={(v['offered_route'],v['scenario_id']):v for v in c.reference['replay']['cases']}
    comparisons=[]
    for case in result['cases']:
        key=case['offered_route'],case['scenario_id']
        # JSON normalizes only integer object keys in action maps, as stored by RILL.
        same=json.loads(json.dumps(case,sort_keys=True))==expected[key]
        comparisons.append({'route':key[0],'scenario':key[1],'same_complete_case':same,
            'status':case['status'],'final_cash':case.get('final_cash')})
    report={'source_blob':blob(HERE/'physical_replay.py'),'reference_blob':blob(c.root/'TITAN-KESTREL-replay-deadline-PR10113/physical_replay.py'),
        'engine_sha256':c.engine_hashes,'restoration':receipt,'comparisons':comparisons,
        'actor_unchanged':restore.state_digest(actor)==before,'input_unchanged':row==input_before,
        'new_games':0,'scenario_panel':'existing RILL PR10220 conditional development case, not a game panel',
        'replay':result}
    if not (result['complete'] and all(v['same_complete_case'] for v in comparisons)
            and report['actor_unchanged'] and report['input_unchanged']):
        report['validation_failed']=True
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rill-evidence',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=180)
    a=p.parse_args()
    if a.output.exists():p.error('Choose a new output file; retained evidence is unchanged')
    result=natural(setup(a.rill_evidence),seconds=a.seconds)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='replay'},indent=2),flush=True)
    print(json.dumps({k:result['replay'][k] for k in ('complete','decisions_executed','wall_seconds','prefix_reuse')},indent=2),flush=True)
    return int(bool(result.get('validation_failed')))

if __name__=='__main__':raise SystemExit(main())
