# SPDX-License-Identifier: MIT
"""Build a relocatable offline agent archive without evaluation data or engine."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def build(output):
    files={'main.py':(HERE/'main.py').read_bytes()}
    for name in ('policy.py','flow.py','LICENSE','NOTICE','vendor/sorrel_adapter.py','vendor/LICENSE-APACHE-2.0.txt'):
        path=HERE/name;files[str(path.relative_to(ROOT))]=path.read_bytes()
    sell=HERE.parent/'cloud-titan-composition/vendor/sell'
    for path in sorted(sell.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
            files[str(path.relative_to(ROOT))]=path.read_bytes()
    manifest={name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}
    files['SOURCE-MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w') as tar:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.mode=0o644;info.size=len(data);info.mtime=0
            tar.addfile(info,io.BytesIO(data))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(gzip.compress(raw.getvalue(),mtime=0))
    return {'archive_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'size_bytes':output.stat().st_size,'files':manifest,
            'scope':'experimental T12 response; evaluation data and evaluator excluded'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(build(a.output),indent=2))
