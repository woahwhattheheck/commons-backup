# SPDX-License-Identifier: Apache-2.0
"""Reproducible T15 standalone using the existing exact licensed dependencies."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RUNTIME=('solver.py','selector.py','tables.py','dependencies.py','history_streams.py',
         'runtime.py','main.py','pure.py','LICENSE','NOTICE.md','SOURCE-FREEZE.json','DEPENDENCIES.json')

SHIM='''# SPDX-License-Identifier: Apache-2.0
_module=None
def agent(observation,configuration=None):
    global _module
    if _module is None:
        import importlib.util
        from pathlib import Path
        root=Path(globals().get('__file__') or (configuration or {}).get('__raw_path__')).resolve().parent
        path=root/'revenue/kaggriculture/cloud-market-game-theory/{entry}'
        spec=importlib.util.spec_from_file_location('t15_packaged_entry',path)
        _module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_module)
    return _module.agent(observation,configuration)
'''


def build():
    members={'main.py':SHIM.replace('{entry}','main.py').encode(),'pure.py':SHIM.replace('{entry}','pure.py').encode()}
    for name in RUNTIME:
        path=HERE/name;members[str(path.relative_to(ROOT))]=path.read_bytes()
    vendor=HERE.parent/'cloud-titan-composition/vendor/sell'
    for path in vendor.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            members[str(path.relative_to(ROOT))]=path.read_bytes()
    t12=HERE.parent/'cloud-market-response'
    for name in ('policy.py','flow.py','vendor/sorrel_adapter.py','vendor/league_variants.py',
                 'LICENSE','NOTICE','vendor/LICENSE-APACHE-2.0.txt'):
        path=t12/name;members[str(path.relative_to(ROOT))]=path.read_bytes()
    dependency=json.loads((HERE/'DEPENDENCIES.json').read_text())
    for path,digest in dependency.items():
        data=members['revenue/kaggriculture/'+path]
        assert hashlib.sha256(data).hexdigest()==digest,path
    output=io.BytesIO()
    with gzip.GzipFile(fileobj=output,mode='wb',mtime=0,filename='') as gz:
        with tarfile.open(fileobj=gz,mode='w') as tar:
            for name,data in sorted(members.items()):
                info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644
                info.uid=info.gid=info.mtime=0;info.uname=info.gname=''
                tar.addfile(info,io.BytesIO(data))
    directory=HERE/'artifacts';directory.mkdir(exist_ok=True)
    path=directory/'t15-market-game-theory.tar.gz';path.write_bytes(output.getvalue())
    receipt={'archive':str(path.relative_to(HERE)),'bytes':path.stat().st_size,
             'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
             'members':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(members.items())}}
    (HERE/'ARTIFACT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='members'}))


if __name__=='__main__':build()
