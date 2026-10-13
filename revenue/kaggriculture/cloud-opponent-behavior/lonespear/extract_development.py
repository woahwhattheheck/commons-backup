"""Decode six preselected SELL/lonespear development traces, not held panels."""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import json
import lzma
from pathlib import Path

import engine_cases

REF='5be6099f5ab2b3a20855bdee1e1e42f336eab678'
ARCHIVE_SHA='f26238195253c10d087f8e47cc92b4fe47e3b429c6fee398b165747f5fdad133'
NAMES=[f'{phase}/sell-lonespear-{seed}-seat{seat}.jsonl.gz'
       for seed,phase in [(9881001,'development-v2'),(9881019,'development-v3'),(9881037,'development-v3')]
       for seat in (0,1)]


def extract(portfolio: Path, output: Path):
    artifacts=portfolio/'revision2/artifacts'
    manifest=json.loads((artifacts/'MANIFEST.json').read_text())
    item=next(a for a in manifest['archives'] if a['name']=='full-traces.xz')
    parts=[]
    for part in item['parts']:
        raw=(artifacts/part['name']).read_bytes()
        if len(raw)!=part['bytes'] or hashlib.sha256(raw).hexdigest()!=part['sha256']:
            raise ValueError('Retained trace part differs')
        parts.append(raw)
    raw=base64.b64decode(b''.join(parts),validate=True)
    if hashlib.sha256(raw).hexdigest()!=ARCHIVE_SHA or item['sha256']!=ARCHIVE_SHA:
        raise ValueError('Trace archive differs from PR9975')
    payload=json.loads(lzma.decompress(raw))
    codec_path=portfolio/'evidence.py'
    if hashlib.sha256(codec_path.read_bytes()).hexdigest()!='22f207a7338f0b54bf7ee3c0c5bf4477d9d88c7ed8d56e6f58d81e29a463a313':
        raise ValueError('Original trace codec differs from PR9975')
    codec=engine_cases.load(codec_path,'iris_existing_trace_codec')
    output.mkdir(parents=True,exist_ok=False)
    results=[]
    for name in NAMES:
        member=payload['members'][name]
        current=None; checked=hashlib.sha256(); count=0
        dest=output/Path(name).name
        with dest.open('wb') as target:
            with gzip.GzipFile(fileobj=target,mode='wb',mtime=0,filename='') as zipped:
                for patch in payload['streams'][member['semantic_sha256']]:
                    current=codec.apply(current,patch)
                    data=codec.encoded(current)+b'\n'
                    checked.update(data);zipped.write(data);count+=1
        if checked.hexdigest()!=member['semantic_sha256'] or count!=member['rows'] or count!=719:
            raise ValueError('Original semantic trace does not reconstruct')
        results.append(dict(original_member=name,**member,decoded_file=dest.name,
                            decoded_gzip_sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
    report=dict(source_ref=REF,archive_sha256=ARCHIVE_SHA,selected_split='development',
                selection='SELL controls, three original development seeds, both seats; no outcome filter',
                original_games_reexecuted=0,codec_sha256=hashlib.sha256(codec_path.read_bytes()).hexdigest(),
                traces=results)
    (output/'INPUTS.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--portfolio',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(extract(a.portfolio,a.output),indent=2))
