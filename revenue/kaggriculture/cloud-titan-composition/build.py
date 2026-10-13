# SPDX-License-Identifier: MIT
"""Build a relocatable offline archive from an explicitly selected arm."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
def build(arm, destination):
    main = (HERE/'arms'/f'{arm}.py').read_text()
    # Arm wrappers normally reside one level below the archive root.
    main = main.replace('Path(__file__).resolve().parents[1]', 'Path(__file__).resolve().parent')
    files = {'main.py': main.encode(), 'controller.py': (HERE/'controller.py').read_bytes()}
    if arm.startswith('carrot_cap_sell_'):
        files['sell_adapter.py'] = (HERE/'sell_adapter.py').read_bytes()
        if arm.endswith('dated'):
            files['dated_sell_adapter.py'] = (HERE/'dated_sell_adapter.py').read_bytes()
        if arm.endswith('conserved'):
            files['conserved_sell_adapter.py'] = (HERE/'conserved_sell_adapter.py').read_bytes()
    for p in sorted((HERE/'vendor').rglob('*')):
        if p.is_file() and '__pycache__' not in str(p) and p.suffix != '.pyc':
            files[str(p.relative_to(HERE))] = p.read_bytes()
    for name in ('README.md', 'SOURCE-PINS.json', 'NOTICE.md',
                 'SOURCE-FREEZE.json', 'SELECTION.json', 'RESULTS.md'):
        files[name] = (HERE/name).read_bytes()
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w') as tar:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
            tar.addfile(info,io.BytesIO(data))
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(gzip.compress(raw.getvalue(),mtime=0))
    return {'arm':arm,'archive_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
            'size_bytes':destination.stat().st_size,'runtime_files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.arm,a.output),indent=2))
