# SPDX-License-Identifier: Apache-2.0
"""Create a test-only F1 native tree; never materializes the legacy router."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

RUNTIME = 'b952c9c228ecbde592bf3d2df01638677abb0d24'
DEPENDENCIES = {'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
                'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d'}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def transform(source):
    if blob(source) != RUNTIME:
        raise ValueError('native runtime drift; reconcile finalizer before composition')
    text = source.decode()
    changes = [
        ('    early_capital: bool = False\n',
         '    early_capital: bool = False\n    r04_fert_mix: bool = False\n'),
        ('    def __post_init__(self):\n',
         '    def __post_init__(self):\n'
         '        if type(self.r04_fert_mix) is not bool:\n'
         '            raise ValueError("r04_fert_mix requires bool")\n'
         '        if self.r04_fert_mix and self.consumer != "frozen":\n'
         '            raise ValueError("F1 requires native frozen consumer")\n'),
        ('        returned = self._early_capital_selected(obs, cfg or {}, returned)\n',
         '        returned = self._early_capital_selected(obs, cfg or {}, returned)\n'
         '        if self.features.r04_fert_mix:\n'
         '            from f1_spill import finish_spill\n'
         '            returned, post = finish_spill(self, obs, cfg or {}, returned, post)\n')]
    for old, new in changes:
        if text.count(old) != 1:
            raise ValueError('native seam not unique')
        text = text.replace(old, new, 1)
    compile(text, 'titan_runtime.py', 'exec')
    return text.encode()


def compose(source, output, enabled=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if type(enabled) is not bool or output.exists() or source == output or source in output.parents:
        raise ValueError('new sibling test directory and boolean flag required')
    data = (source/'titan_runtime.py').read_bytes()
    patched = transform(data)
    for name, expected in DEPENDENCIES.items():
        if blob((source/name).read_bytes()) != expected:
            raise ValueError('dependency drift: ' + name)
    config = json.loads((source/'TITAN-CONFIG.json').read_text())
    if 'r04_fert_mix' in config:
        raise ValueError('F1 already configured')
    config['r04_fert_mix'] = enabled
    helper = Path(__file__).with_name('f1_spill.py').read_bytes()
    shutil.copytree(source, output, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (output/'titan_runtime.py').write_bytes(patched)
    (output/'f1_spill.py').write_bytes(helper)
    (output/'TITAN-CONFIG.json').write_text(json.dumps(config, indent=2)+'\n')
    return {'input_runtime': blob(data), 'output_runtime': blob(patched),
            'helper': blob(helper), 'enabled': enabled,
            'dependencies': DEPENDENCIES}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('source'); ap.add_argument('output')
    ap.add_argument('--enabled', action='store_true'); args = ap.parse_args()
    print(json.dumps(compose(args.source, args.output, args.enabled), sort_keys=True))
