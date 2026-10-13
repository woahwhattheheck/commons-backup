# SPDX-License-Identifier: Apache-2.0
"""Source-bound scratch composer for ONE B5 companion, never a production writer.

No legacy R04 materializer. Input is the authenticated native artifact snapshot;
output must not exist. A later combined-stack source requires explicit rebase and
new tests, not a fuzzy replacement or a stale full-runtime transplant.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
SOURCE_SHA = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
RUNTIME_SHA = 'da391af2dbdec0f6e4a25749ed539cdd39578ace8861c0e225b5fbfef90d75a8'
HELPER_SHA = '2f80797ba423220fc449e918d7f36526b4e0a17aa9a135130cce4e0caee6da00'
FEATURE = 'tomato_discard_salvage'

METHOD = '''    def _tomato_discard_selected(self, obs, cfg, selected):
        """Optional free-input proposal after market guards, before commitments."""
        if not self.features.tomato_discard_salvage:
            return selected
        reason = None
        if self.diagnostics.get('status') != 'completed':
            reason = 'no_optional_work_on_fallback'
        elif self.features.consumer != 'frozen' or self.features.terminal_route:
            reason = 'unsupported_consumer'
        elif self.features.terminal_history or self.quadrant is not None:
            reason = 'protected_terminal_or_capital_lifecycle'
        spatial = self.spatial
        if reason is None and spatial is not None:
            if any(getattr(spatial, k, None) for k in (
                    'plans', 'sale_obligation', 'crop_intent', '_sale_proposal',
                    '_crop_preparation', '_crop_repair')):
                reason = 'protected_spatial_or_input_lifecycle'
            pending = getattr(spatial, '_pending', None)
            if pending and (not isinstance(pending, dict)
                    or pending.get('plans')
                    or not isinstance(pending.get('previous') or {}, dict)
                    or (pending.get('previous') or {}).get('plans')):
                reason = 'protected_pending_spatial_lifecycle'
        if reason is not None:
            self.diagnostics['tomato_discard_salvage'] = {
                'changed': False, 'reason': reason, 'observed_fill': False}
            return selected
        from discarded_fertilizer_tomato import apply_discarded_fertilizer
        proposed, report = apply_discarded_fertilizer(obs, selected, cfg, enabled=True)
        self.diagnostics['tomato_discard_salvage'] = report
        return proposed

'''


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_input(source):
    source = Path(source).resolve()
    if digest(source/'SOURCE.json') != SOURCE_SHA:
        raise ValueError('native SOURCE.json differs from the authenticated artifact')
    manifest = json.loads((source/'SOURCE.json').read_text())
    for name, data in manifest['runtime'].items():
        path = source/name
        if not path.is_file() or path.is_symlink() or digest(path) != data['sha256']:
            raise ValueError('native member differs or is missing: '+name)
    if digest(source/'titan_runtime.py') != RUNTIME_SHA:
        raise ValueError('native runtime differs')
    return manifest


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('unique native anchor missing or ambiguous: '+old[:70])
    return source.replace(old, new, 1)


def compose(source, destination, *, enabled=False):
    if type(enabled) is not bool:
        raise TypeError('enabled must be a bool')
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or source == destination or source in destination.parents:
        raise ValueError('destination must be new and outside input')
    manifest = verify_input(source)
    helper = HERE/'discarded_fertilizer_tomato.py'
    if digest(helper) != HELPER_SHA:
        raise ValueError('helper changed; revalidate and explicitly update its pin')
    runtime = (source/'titan_runtime.py').read_text()
    runtime = once(runtime, '    early_capital: bool = False\n',
                   '    early_capital: bool = False\n    tomato_discard_salvage: bool = False\n')
    runtime = once(runtime, '    def __post_init__(self):\n',
        '    def __post_init__(self):\n'
        "        if type(self.tomato_discard_salvage) is not bool:\n"
        "            raise ValueError('tomato_discard_salvage must be a bool')\n")
    runtime = once(runtime, '    def _seed_selected(self, obs, cfg, selected):\n',
                   METHOD+'    def _seed_selected(self, obs, cfg, selected):\n')
    anchor = '        returned = self._early_capital_selected(obs, cfg or {}, returned)\n'
    runtime = once(runtime, anchor, anchor +
        '        before_tomato = returned\n'
        '        returned = self._tomato_discard_selected(obs, cfg or {}, returned)\n'
        '        tomato_changed = returned is not before_tomato\n'
        '        if tomato_changed:\n'
        '            # No protected lifecycle may be active. Never rebind a\n'
        '            # pre-FERTILIZE snapshot or invent an observed input fill.\n'
        '            post = None\n'
        '            self.post = None\n'
        '            self.consumer.selected_post_units = None\n'
        '            self.consumer.selected_post_units_binding = None\n')
    runtime = once(runtime, "            self.diagnostics['history'] = self.history.diagnostics\n        return returned\n",
        "            self.diagnostics['history'] = self.history.diagnostics\n"
        '        if tomato_changed:\n'
        '            # Outer entrypoint cancellation may only reuse these fully\n'
        '            # finalized bytes after the lifecycle calls completed.\n'
        '            self.selected = deepcopy(returned)\n'
        '        return returned\n')
    compile(runtime, 'composed_titan_runtime.py', 'exec')
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (destination/'titan_runtime.py').write_text(runtime)
    shutil.copyfile(helper,destination/helper.name)
    config_path = destination/'TITAN-CONFIG.json'
    if enabled:
        cfg = json.loads(config_path.read_text())
        if FEATURE in cfg:
            raise ValueError('unexpected preexisting experimental config key')
        cfg[FEATURE] = True
        config_path.write_text(json.dumps(cfg,indent=2,sort_keys=True)+'\n')
    for name in ('titan_runtime.py','discarded_fertilizer_tomato.py','TITAN-CONFIG.json'):
        manifest['runtime'][name] = {'bytes':(destination/name).stat().st_size,
            'sha256':digest(destination/name),'source_path':'B5 companion experiment/'+name}
    # The ancestor manifest remains evidence, not this candidate's release status.
    manifest['experimental_b5_companion'] = {'enabled':enabled,
        'original_donor_recovered':False,'field_strength':'UNMEASURED',
        'input_source_sha256':SOURCE_SHA,'helper_sha256':HELPER_SHA,
        'source_owner':'SOLANUM-2863','production_promotion':False}
    (destination/'SOURCE.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return {'enabled':enabled,'input_manifest_sha256':SOURCE_SHA,
            'helper_sha256':HELPER_SHA,'runtime_sha256':digest(destination/'titan_runtime.py'),
            'config_sha256':digest(config_path),'entrypoint_sha256':digest(destination/'main.py'),
            'input_members_verified':len(manifest['runtime'])-1}


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
    p.add_argument('--enabled',action='store_true');a=p.parse_args()
    print(json.dumps(compose(a.source,a.destination,enabled=a.enabled),sort_keys=True))
