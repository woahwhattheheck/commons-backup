# SPDX-License-Identifier: Apache-2.0
"""Fresh-process official-file/evaluator parity on one initial observation.

No full game or consumed seed panel is replayed by this packaging check.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def child(mode,road,snapshot):
    data=json.loads(Path(snapshot).read_text());start=time.perf_counter()
    if road=='official':
        official=load(HERE.parent.parent/'cloud-pack/official.py','parity_official')
        name={'adaptive':'main.py','fixed':'fixed_main.py','static':'static_main.py'}[mode]
        fn=official.make_agent(HERE/name)
    else:
        module=load(HERE/'evaluation_entry.py','parity_evaluation')
        fn=getattr(module,mode)
    action=fn(data['observation'],data['configuration'])
    action.pop('__adaptive_evaluation__',None)
    return {'action':action,'cold_seconds':time.perf_counter()-start}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--engine-dir');p.add_argument('--child',nargs=3)
    a=p.parse_args()
    if a.child:
        print(json.dumps(child(*a.child)));raise SystemExit
    sys.path.insert(0,str(HERE.parent))
    from dependencies import official_engine
    ev,engine,hashes=official_engine(a.engine_dir)
    cfg=ev.Struct({k:v.get('default') if isinstance(v,dict) else v for k,v in engine.specification['configuration'].items()})
    cfg.seed=0;env=ev.Struct(configuration=cfg,done=False,info={})
    state=[ev.Struct(observation=ev.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(state,env);state[0].observation.step=0
    rows=[]
    with tempfile.TemporaryDirectory(prefix='t15-entrypoint-') as tmp:
        snapshot=Path(tmp)/'initial.json';snapshot.write_text(json.dumps({'observation':state[0].observation,'configuration':cfg}))
        for mode in ('adaptive','fixed','static'):
            calls={road:json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--child',mode,road,str(snapshot)]))
                   for road in ('official','evaluation')}
            assert calls['official']['action']==calls['evaluation']['action']
            rows.append({'mode':mode,'calls':calls,'parity':True})
    result={'constructed_initial_observations':1,'fresh_process_calls':6,'engine':hashes,'rows':rows}
    (HERE/'ENTRYPOINT-VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'parity':True,'calls':6,'max_cold_seconds':max(r['calls'][road]['cold_seconds'] for r in rows for road in r['calls'])}))
