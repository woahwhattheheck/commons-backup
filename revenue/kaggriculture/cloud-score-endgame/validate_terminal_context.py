# SPDX-License-Identifier: Apache-2.0
"""Execute the terminal-context witness with existing native/consumer source.

Uses POLY's retained constructed lead-33 fixture, not private development data.
No new game, hidden state reconstruction, or controller construction occurs.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--producer-dir',type=Path,required=True)
    parser.add_argument('--consumers',type=Path,required=True)
    parser.add_argument('--engine-dir',type=Path,required=True)
    parser.add_argument('--expect',choices=('original','bound'),required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.producer_dir))
    import terminal_input_cases as cases
    import test_terminal_inputs as fixtures
    import terminal_inputs as inputs
    deps=cases.dependencies(args.consumers/'engine_loader.py',args.engine_dir,
                            args.consumers,args.consumers/'full_support.py')
    deps.score=cases.load(args.runtime,'_anchor_native_subject')
    fixtures.DEPS=deps
    records=[]; calls=0
    for player in (0,1):
        obs,cfg,base,scenarios=fixtures.fixture(player,33)
        packet=fixtures.packet(obs,cfg,base,scenarios)
        picked,actor=cases.choose(deps,obs,cfg,base,packet)
        first_objective=deepcopy(actor.last_objective)
        assert picked!=base and first_objective['value']=='1'
        changed=deepcopy(obs);changed['farms'][player]['money']-=3
        updated=fixtures.packet(changed,cfg,base,scenarios)
        allowed={inputs.fingerprint(p['action']) for p in updated['plans']}
        retried=actor.transform_terminal(changed,cfg,base,document=updated['document'],
                    feasible=lambda action:inputs.fingerprint(action) in allowed)
        fresh=deps.score.solve_absolute(updated['document'],deps.terminal.build_table,
                         deps.core.solve_full_table,deps.core.verify_certificate)
        assert fresh['value']=='1/2'
        assert (actor.provider_calls,actor.draws)==(1,1)
        if args.expect=='bound':
            assert retried==base and actor.active is None and actor.last_objective is None
            again=actor.transform_terminal(obs,cfg,base,document=packet['document'],
                                            feasible=lambda action:True)
            assert again==base and (actor.provider_calls,actor.draws)==(1,1)
        else:
            assert retried==picked and actor.last_objective['value']=='1'
        native=[]
        for label,current,output in [('initial',obs,picked),('retry',changed,retried)]:
            for scenario in scenarios:
                state,env=cases.make_state(current,cfg,output,scenario)
                deps.engine.interpreter(state,env);calls+=1
                assert all(s.status=='DONE' for s in state)
                matches=[r for r in (packet if label=='initial' else updated)['document']['receipts']
                         if r['own_action']==output and r['scenario']==scenario['id']]
                assert matches and all([r['own_cash'],r['rival_cash']]==
                    [state[player].reward,state[1-player].reward] for r in matches)
                native.append({'phase':label,'scenario':scenario['id'],'action':output,
                    'cash':[state[player].reward,state[1-player].reward],
                    'margin':state[player].reward-state[1-player].reward,
                    'statuses':[s.status for s in state]})
        records.append({'player':player,'observation':obs,'updated_observation':changed,
            'configuration':cfg,'base_action':base,'scenarios':scenarios,
            'initial_document':packet['document'],'updated_document':updated['document'],
            'first_selection':picked,'retry_selection':retried,'first_objective':first_objective,
            'after_retry_objective':deepcopy(actor.last_objective),
            'fresh_updated_solution':fresh,'last_decision':actor.last_decision,
            'provider_calls':actor.provider_calls,'draws':actor.draws,'native':native})
    report={'schema':'titan.terminal-context.native.v1','expected_behavior':args.expect,
        'runtime_sha256':hashlib.sha256(args.runtime.read_bytes()).hexdigest(),
        'validation_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'engine_hashes':deps.engine_hashes,'counts':dict(fixtures.COUNTS),
        'full_terminal_interpreter_transitions':calls,'records':records,'full_games':0,
        'game_seeds':0,'scope':'constructed terminal continuity; fallback is not a claimed economic improvement'}
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
