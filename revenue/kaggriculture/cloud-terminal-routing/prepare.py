"""Prepare the existing pinned source-pack actors and this T05 native entry."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    if runtime.exists():
        raise FileExistsError(f'Use a new cloud runtime directory: {runtime}')
    panel = HERE.parent / 'cloud-frontier-policy/next-panel'
    subprocess.run([sys.executable, str(panel / 'prepare.py'),
                    '--runtime', str(runtime)], check=True, stdout=subprocess.DEVNULL)
    spec = importlib.util.spec_from_file_location('t05_existing_pack', HERE.parent / 'cloud-pack/pack.py')
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    adapter = runtime / 't05-adapter.py'
    pack.write_adapter(adapter, HERE / 'main.py')
    prefix = ('import sys\n' + f'sys.path.insert(0, {str(panel)!r})\n'
              'from offline import restrict\nrestrict()\n')
    adapter.write_text(prefix + adapter.read_text())
    manifest_path = runtime / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['files']['t05-adapter.py'] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    manifest['t05_freeze'] = json.loads((HERE / 'FREEZE.json').read_text())
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'runtime': str(runtime), 'candidate': str(adapter)}, indent=2))


if __name__ == '__main__':
    main()
