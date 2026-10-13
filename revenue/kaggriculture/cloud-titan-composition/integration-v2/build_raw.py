# SPDX-License-Identifier: MIT
"""Copy the accepted archive, changing only its raw-loader entrypoint."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
def build(output):
    source=HERE.parent/'artifacts/titan-selected.tar.gz'
    expected='5d3a2bf3878808679820ff7f5a5ca7533c41888366c5dcd358f15ff0213f1f10'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==expected
    files={}
    with tarfile.open(source) as t:
        for member in t.getmembers():
            if member.isfile():files[member.name]=t.extractfile(member).read()
    old=hashlib.sha256(files['main.py']).hexdigest()
    files['main.py']=(HERE/'raw_selected.py').read_bytes()
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w') as t:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
            t.addfile(info,io.BytesIO(data))
    output.write_bytes(gzip.compress(raw.getvalue(),mtime=0))
    return {'source_archive_sha256':expected,'raw_archive_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'changed_member':'main.py','old_entrypoint_sha256':old,
            'new_entrypoint_sha256':hashlib.sha256(files['main.py']).hexdigest(),
            'unchanged_members':len(files)-1,'policy_changed':False}

if __name__=='__main__':
    print(json.dumps(build(HERE/'titan-selected-raw.tar.gz'),indent=2))
