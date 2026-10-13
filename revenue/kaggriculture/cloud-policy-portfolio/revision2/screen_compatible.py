# SPDX-License-Identifier: Apache-2.0
"""Prespecified conditional validation intake; no terminal labels or tuning."""
import copy
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from runtime import load


def screen(seed, opponent):
    ev = load(ROOT/'vendor/cloud-eval/evaluate.py','t14_r2_conditional_screen')
    engine, _ = ev.get_engine(ROOT/'vendor/engine')
    original = engine.interpreter
    evidence = {'seed':seed,'opponent':opponent,'seat':0,'terminal_label':None,
                'full_game':False,'observed_through_step':226}
    def stop(state,env):
        if state[0].observation.get('farms') and int(state[0].observation['step']) == 226:
            obs = copy.deepcopy(dict(state[0].observation))
            evidence['observation'] = obs
            evidence['target'] = 'YARN_STORE' in obs['town']['unlocked_shops']
            evidence['configuration'] = {k:v for k,v in env.configuration.items() if k!='seed'}
            # Full original horizon was supplied; no shortened-episode policy.
            # Step226 has been requested, but is never executed in the engine.
            raise StopIteration('T14 source checkpoint intake')
        return original(state,env)
    engine.interpreter = stop
    result = ev.play(engine,[str(HERE/'controls.py')+'::sell',str(HERE/'controls.py')+'::'+opponent],
        ROOT/'vendor/engine',ev.LOADER,seed,0,startup_timeout=1,action_timeout=1)
    if result.get('failure',{}).get('error') != 'StopIteration: T14 source checkpoint intake':
        evidence.update(target=False,intake_error=result.get('failure'))
    evidence['runtime'] = result['actors']
    return evidence


def main():
    destination = HERE/'results/conditional-intake.json'
    if destination.exists():
        raise FileExistsError(destination)
    rows = []; chosen = {}
    for opponent, first in [('arlene',9881300),('apex',9881310),('lonespear',9881320),('cok',9881330)]:
        for seed in range(first,first+10):
            row = screen(seed,opponent);rows.append(row)
            if row.get('target'):
                chosen[opponent] = seed
            destination.write_text(json.dumps({'schema':'t14.conditional-intake.v1',
                'scope':'First early-YARN source-compatible seed per opponent, at most ten; no cash/outcome criterion.',
                'selected':chosen,'all_searched':rows,'complete':False},indent=2)+'\n')
            print(opponent,seed,row.get('target'),flush=True)
            if row.get('target'):break
    report = json.loads(destination.read_text());report['complete']=True
    destination.write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':main()
