# SPDX-License-Identifier: Apache-2.0
"""Read-only CF1 observer primitives; not another game driver or policy.

Pass the full pre-call observation and the actual returned action. Never compact,
trim, pad or reconstruct command rows for this observer. The pinned interpreter
counts even nonexistent actors' PLANT rows before checking actor positions.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

HELPER_BLOB = 'ef6ab6e795375cf84c5dc7d0bcd43f979bbd0af8'
SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
ARCHIVE_SHA256 = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'git_blob': hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}


def verify_parent(root):
    """Authenticate all 109 source-map members, not just the common b952 runtime.

    This checks the known b567 archive's source map and runtime bytes, not a live
    Git ref or proof that a caller really executed them. Extra files are listed.
    """
    root = Path(root).resolve()
    source = root/'SOURCE.json'
    if identity(source)['sha256'] != SOURCE_SHA256:
        raise ValueError('Parent SOURCE.json is not the pinned b567 source map')
    manifest = json.loads(source.read_text())['runtime']
    if len(manifest) != 109:
        raise ValueError('Unexpected runtime-map size')
    checked = {}
    for relative, entry in sorted(manifest.items()):
        path = (root/relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Source-map member escapes parent root')
        actual = identity(path)
        if actual['bytes'] != entry['bytes'] or actual['sha256'] != entry['sha256']:
            raise ValueError('Parent dependency mismatch: '+relative)
        checked[relative] = actual
    extras = sorted(str(p.relative_to(root)) for p in root.rglob('*')
                    if p.is_file() and p.suffix in ('.py', '.json')
                    and str(p.relative_to(root)) not in manifest and p != source)
    return {'source_sha256': SOURCE_SHA256, 'archive_sha256': ARCHIVE_SHA256,
            'members_verified': len(checked), 'runtime': checked, 'extra_source_files': extras}


def verify_helper(path):
    actual = identity(path)
    if actual['git_blob'] != HELPER_BLOB:
        raise ValueError('CF1 helper does not match the pinned original')
    return actual


def raw_action_facts(action, observation):
    """Describe input custody, including possible raw surplus-PLANT interference.

    A potential blocker is not a claim that the live tile permits PLANT. The
    official interpreter remains the authority for physical execution.
    """
    if not isinstance(action, dict) or not isinstance(observation, dict):
        raise ValueError('Action and observation must be mappings')
    seat = observation.get('player')
    farms = observation.get('farms')
    if type(seat) is not int or seat not in (0, 1) or not isinstance(farms, list) or len(farms) != 2:
        raise ValueError('Expected an exact two-seat observation')
    farm, private = farms[seat], observation.get('private')
    if not isinstance(farm, dict) or not isinstance(private, dict):
        raise ValueError('Missing full own farm/private observation')
    hands, commands = farm.get('hands'), action.get('hands', [])
    inventories, seeds = private.get('inventories'), private.get('seeds', {})
    if not isinstance(hands, list) or not isinstance(commands, list) or not isinstance(inventories, list) or not isinstance(seeds, dict):
        raise ValueError('Malformed actor or seed vectors')
    rows = [action.get('farmer', ['PASS']), *commands]
    raw, live = Counter(), Counter()
    for index, row in enumerate(rows):
        if isinstance(row, list) and len(row) >= 2 and row[0] == 'PLANT':
            if not isinstance(row[1], str):
                raise ValueError('Non-string PLANT crop: do not normalize invalid rows')
            raw[row[1]] += 1
            if index <= len(hands):
                live[row[1]] += 1
    blockers = []
    for crop, demand in sorted(live.items()):
        available = seeds.get(crop, 0)
        if type(available) is not int or available < 0:
            raise ValueError('Malformed seed count')
        if 0 < demand <= available < raw[crop]:
            blockers.append({'crop': crop, 'live_demand': demand,
                             'raw_demand': raw[crop], 'available': available})
    return {'public_hands': len(hands), 'returned_hand_rows': len(commands),
            'inventory_rows': len(inventories),
            'complete_vectors': len(commands) == len(hands) == len(inventories)-1,
            'surplus_hand_rows': deepcopy(commands[len(hands):]),
            'raw_plant_demand': dict(raw), 'live_plant_demand': dict(live),
            'potential_surplus_plant_blockers': blockers,
            'input_sha256': hashlib.sha256(encoded([action, observation])).hexdigest()}


def probe_decision(helper, action, observation, configuration):
    """Call existing helper on copies; return its real decision/return line.

    Source authentication belongs to verify_helper() before loading. Return-line
    numbers are meaningful only with that exact helper hash. Do not include this
    tracing overhead in parent-policy latency measurements.
    """
    a, obs, cfg = deepcopy((action, observation, configuration))
    before = encoded([a, obs, cfg])
    fn = helper.apply_cow_fert_salvage
    old_trace = sys.gettrace()
    if old_trace is not None:
        raise RuntimeError('Observer cannot replace an existing trace hook')
    line = None

    def trace(frame, event, arg):
        nonlocal line
        if frame.f_code is fn.__code__:
            if event == 'return':
                line = frame.f_lineno
            return trace
        return None

    sys.settrace(trace)
    try:
        proposed = fn(a, obs, cfg, enabled=True)
    finally:
        sys.settrace(old_trace)
    if encoded([a, obs, cfg]) != before:
        raise ValueError('Helper mutated the supplied vectors')
    if fn(a, obs, cfg, enabled=False) is not a or encoded([a, obs, cfg]) != before:
        raise ValueError('OFF did not preserve exact parent identity and inputs')
    changed = proposed != a
    if not changed and proposed is not a:
        raise ValueError('No-match copied the parent instead of preserving identity')
    return {'helper_return_line': line, 'changed': changed,
            'input_sha256': hashlib.sha256(before).hexdigest(),
            'proposal': deepcopy(proposed) if changed else None}
