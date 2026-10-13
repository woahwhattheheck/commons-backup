# SPDX-License-Identifier: Apache-2.0
"""Fresh-process source/archive parity through the pinned official file loader."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time

from dependencies import HERE,load,official_engine


def worker(entry,kind,payload):
    obj=json.loads(Path(payload).read_text())
    started=time.perf_counter()
    if kind=='raw':
        official=load(HERE.parent/'cloud-pack/official.py','t15_official_file')
        act=official.make_agent(entry)
    else:
        act=load(Path(entry),'t15_direct_file').agent
    loaded=time.perf_counter()
    action=act(obj['observation'],obj['configuration'])
    finished=time.perf_counter()
    print(json.dumps({'action':action,'load_seconds':loaded-started,
                     'first_call_seconds':finished-loaded,'total_seconds':finished-started}))


def verify(engine_dir):
    archive=HERE/'artifacts/t15-market-game-theory.tar.gz'
    ev,engine,hashes=official_engine(engine_dir)
    cfg=ev.Struct({k:v.get('default') if isinstance(v,dict) else v for k,v in engine.specification['configuration'].items()});cfg.seed=0
    state=[ev.Struct(observation=ev.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(state,ev.Struct(configuration=cfg,done=False,info={}))
    records=[]
    with tempfile.TemporaryDirectory(prefix='t15-package-') as directory:
        root=Path(directory)
        with tarfile.open(archive,'r:gz') as tar:tar.extractall(root,filter='data')
        expected=json.loads((HERE/'ARTIFACT.json').read_text())
        for name,digest in expected['members'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
        for seat in (0,1):
            obs=state[seat].observation;obs['step']=0;obs['remainingOverageTime']=0
            payload=root/f'observation-{seat}.json';payload.write_text(json.dumps({'observation':obs,'configuration':cfg}))
            rows=[]
            for entry,kind in ((HERE/'main.py','import'),(HERE/'main.py','raw'),(root/'main.py','raw')):
                result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(entry),kind,str(payload)],
                                      cwd=root,capture_output=True,text=True,check=True,timeout=15)
                rows.append(json.loads(result.stdout))
            assert rows[0]['action']==rows[1]['action']==rows[2]['action']
            assert max(r['first_call_seconds'] for r in rows)<1
            records.append({'seat':seat,'equal_actions':True,'calls':rows})
    result={'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'members_verified':len(expected['members']),
            'cases':records,'method':'Two constructed initial observations; no episode replay or new held seed.',
            'official_loader_sha256':hashlib.sha256((HERE.parent/'cloud-pack/official.py').read_bytes()).hexdigest()}
    (HERE/'ARCHIVE-VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'members':result['members_verified'],'both_seats_equal':True,
                     'max_archive_first_seconds':max(r['calls'][2]['first_call_seconds'] for r in records)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine-dir');p.add_argument('--worker',nargs=3)
    a=p.parse_args()
    if a.worker:worker(*a.worker)
    else:verify(a.engine_dir)
