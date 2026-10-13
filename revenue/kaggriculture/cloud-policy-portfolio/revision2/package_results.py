# SPDX-License-Identifier: Apache-2.0
"""Package existing revision2 evidence; never execute a game or refit a policy."""
import base64
import hashlib
import json
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0,str(ROOT))
from package_evidence import archive


def package(trace_archive):
    output = HERE/'artifacts';output.mkdir(exist_ok=True)
    receipts = list((HERE/'results').rglob('*.json'))
    runtime = [p for p in (ROOT/'vendor').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    runtime += [ROOT/name for name in ('runtime.py','features.py','controls.py','selected.py','main.py',
                                       'model.json','LICENSE','NOTICE.md','SOURCE-PINS.json')]
    runtime += [p for p in HERE.rglob('*') if p.is_file() and not set(p.relative_to(HERE).parts)&{'artifacts','results','__pycache__'}]
    archives = {'receipts.tar.xz':archive(receipts,ROOT),
                'runtime.tar.xz':archive(runtime,ROOT),'full-traces.xz':trace_archive.read_bytes()}
    manifest = {'schema_version':1,'encoding':'concatenated base64 text parts','archives':[]}
    for name,raw in archives.items():
        item = {'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'parts':[]}
        data = base64.b64encode(raw)
        for index,start in enumerate(range(0,len(data),160000)):
            chunk = data[start:start+160000];part = name+f'.part{index:03d}.b64'
            (output/part).write_bytes(chunk)
            item['parts'].append({'name':part,'bytes':len(chunk),'sha256':hashlib.sha256(chunk).hexdigest()})
        manifest['archives'].append(item)
    (output/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'decode.py').write_bytes((ROOT/'artifacts/decode.py').read_bytes())
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace-archive',type=Path,required=True)
    print(json.dumps(package(parser.parse_args().trace_archive),indent=2))
