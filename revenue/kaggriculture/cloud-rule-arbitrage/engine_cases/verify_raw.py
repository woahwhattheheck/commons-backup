# SPDX-License-Identifier: Apache-2.0
"""Repeat actual pinned file-loader/archive parity on retained development data."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

HERE=Path(__file__).resolve().parent
RUNNER="""import importlib.util,json,sys,time
mode,p,loader=sys.argv[1:]
path=loader if mode=='official' else p
spec=importlib.util.spec_from_file_location('candidate',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
f=m.make_agent(p) if mode=='official' else m.agent
rows=json.load(sys.stdin);results=[];timings=[]
for o in rows:
 start=time.perf_counter();results.append(f(o,{}));timings.append(time.perf_counter()-start)
print(json.dumps({'actions':results,'seconds':timings}))
"""


def main():
    official=HERE.parents[1]/'cloud-pack/official.py'
    data=json.loads(gzip.decompress((HERE/'results/development-recovered/cycle-9832001-arlene-0.json.gz').read_bytes()))
    fixtures=[r['own_observation'] for r in data['cycle_signature_events'][:4]]
    archive_path=HERE/'artifacts/t11-liquidity-research.tar.gz'
    with tempfile.TemporaryDirectory() as directory:
        target=Path(directory)
        with tarfile.open(archive_path) as archive:
            archive.extractall(target,filter='data')
        results=[]
        for mode,path in (('import',HERE/'main.py'),('official',HERE/'raw_main.py'),('official',target/'main.py')):
            run=subprocess.run([sys.executable,'-c',RUNNER,mode,str(path),str(official)],
                input=json.dumps(fixtures),text=True,capture_output=True,check=True,cwd=target)
            results.append(json.loads(run.stdout))
        assert results[0]['actions']==results[1]['actions']==results[2]['actions']
    artifact=json.loads((HERE/'ARTIFACT.json').read_text())
    freeze=json.loads((HERE/'SOURCE-FREEZE.json').read_text())
    assert all(hashlib.sha256((HERE/n).read_bytes()).hexdigest()==h for n,h in freeze['files'].items())
    assert artifact['members']['t11_policy.py']==freeze['files']['main.py']
    receipt={'cases':len(fixtures),'official_file_loader_action_parity':True,
        'source_archive_action_parity':True,'all_frozen_sources_unchanged':True,
        'mode_call_seconds':[r['seconds'] for r in results],
        'archive_sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        'official_loader_sha256':hashlib.sha256(official.read_bytes()).hexdigest(),
        'raw_adapter_sha256':hashlib.sha256((HERE/'raw_main.py').read_bytes()).hexdigest(),
        'method':'Three fresh independent processes; unchanged pinned official file loader; identical retained DEVELOPMENT observations and full action equality. No new games or held replay.'}
    (HERE/'ARCHIVE-VALIDATION.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()
