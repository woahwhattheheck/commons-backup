"""Prepare reviewed sources and the exact frozen artifact; no network/downloads."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = '79b407d699b5fd39e7b396de8b6fc79b2bc2fb99f427f7e2e7ecd25fbc71fb0b'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    pack_path = HERE.parent.parent/'cloud-pack/pack.py'
    spec = importlib.util.spec_from_file_location('existing_pack', pack_path)
    pack = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pack
    spec.loader.exec_module(pack)
    archive = HERE.parent/'export/submission.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_SHA
    pack.verify(HERE.parent/'export', extract_to=runtime/'frozen')
    shutil.copytree(HERE/'vendor/apex', runtime/'apex', dirs_exist_ok=True)
    command = ['g++','-O3','-std=c++17','-Wall','-Wextra','-pedantic',
               '-shared','-fPIC','-Isource/include','-o','agent.so',
               'source/policy.cpp','submission_bridge.cpp']
    result = subprocess.run(command, cwd=runtime/'apex', capture_output=True, text=True, check=True)
    (runtime/'compile.txt').write_text(result.stdout+result.stderr)
    targets = {'frozen':runtime/'frozen/main.py','arlene':HERE/'vendor/arlene.py',
               'apex':runtime/'apex/main.py',
               'kaito':HERE.parent/'vendor/kaito_v43.py',
               'igor':HERE.parent/'vendor/igor_multiroute.py'}
    for name, path in targets.items():
        adapter = runtime/(name+'-adapter.py')
        pack.write_adapter(adapter, path)
        prefix = ('import sys\n' + f'sys.path.insert(0, {str(HERE)!r})\n'
                  'from offline import restrict\nrestrict()\n')
        adapter.write_text(prefix+adapter.read_text())
    manifest = {'archive_sha256':ARCHIVE_SHA,'compiler':subprocess.check_output(['g++','--version'],text=True),
                'compile_command':command,'network':'seccomp denies socket/network and exec syscalls before policy loading; fails closed',
                'environment':'Existing evaluator starts each actor with PATH, private HOME, LANG, PYTHONHASHSEED, PYTHONDONTWRITEBYTECODE only.',
                'files':{str(p.relative_to(runtime)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in runtime.rglob('*') if p.is_file()}}
    (runtime/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__ == '__main__':
    main()
