# SPDX-License-Identifier: Apache-2.0
"""Build an offline research archive around the unchanged selected SELL bytes."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
SELECTED_SHA='5d3a2bf3878808679820ff7f5a5ca7533c41888366c5dcd358f15ff0213f1f10'


def build():
    source=HERE.parents[1]/'cloud-titan-composition/artifacts/titan-selected.tar.gz'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==SELECTED_SHA
    members={}
    with tarfile.open(source,'r:gz') as archive:
        for info in archive.getmembers():
            if info.isfile():members[info.name]=archive.extractfile(info).read()
    members['SELECTED-SOURCE-MAIN.py']=members['main.py']
    for name in ('main.py','liquidity_cycle.py','market_math.py','cycle_quotes.py'):
        members[name]=(HERE/name).read_bytes()
    members['t11_policy.py']=members['main.py']
    members['main.py']=(HERE/'raw_main.py').read_bytes()
    members['T11-NOTICE.md']=(HERE/'NOTICE.md').read_bytes()
    members['LICENSE']=(HERE/'LICENSE').read_bytes()
    members['T11-README.md']=(HERE/'README.md').read_bytes()
    members['T11-SOURCE-FREEZE.json']=(HERE/'SOURCE-FREEZE.json').read_bytes()
    output=HERE/'artifacts/t11-liquidity-research.tar.gz'
    output.parent.mkdir(exist_ok=True)
    with output.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as zipped:
        with tarfile.open(fileobj=zipped,mode='w') as archive:
            for name,data in sorted(members.items()):
                info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
                archive.addfile(info,io.BytesIO(data))
    receipt={'archive':str(output.relative_to(HERE)),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
             'bytes':output.stat().st_size,'selected_source_archive_sha256':SELECTED_SHA,
             'members':{name:hashlib.sha256(data).hexdigest() for name,data in members.items()},
             'selection':'research; frozen SELL remains the production default'}
    (HERE/'ARTIFACT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='members'},indent=2))


if __name__=='__main__':build()
