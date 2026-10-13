#!/usr/bin/env python3
"""Bind an existing full step-zero observation to its retained trace.

Configuration is explicitly defined from the pinned engine specification;
the recorded trace does not retain a configuration or expected SciPy action.
Only bytes are decoded. No engine or agent is imported or initialized.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import lzma
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE_SHA = 'f26238195253c10d087f8e47cc92b4fe47e3b429c6fee398b165747f5fdad133'
STREAM = 'a06b27785b24b116951a2ccd5792f34299b37394ca1861c55010a4febc29006b'
FIXTURE_SHA = 'aded0f1ce01a727d9e85be7e7dc86b3cfd2831adbbe8e47e0e7422fe2554d893'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def prepare():
    fixture = ROOT / 'cloud-opponent-frontier/runtime/fixtures/initial-observation.json'
    raw = fixture.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA:
        raise ValueError('Retained first-observation fixture changed')
    observation = json.loads(raw)
    parts = sorted((ROOT / 'cloud-policy-portfolio/revision2/artifacts').glob('full-traces.xz.part*.b64'))
    packed = b''.join(base64.b64decode(path.read_bytes()) for path in parts)
    if hashlib.sha256(packed).hexdigest() != ARCHIVE_SHA:
        raise ValueError('Original development archive differs')
    data = json.loads(lzma.decompress(packed))
    first = data['streams'][STREAM][0][0][2]
    if first['observation'] != observation or observation['step'] != 0:
        raise ValueError('Fixture is not the unchanged retained first observation')
    specification = ROOT / 'cloud-execution-lab/reference/engine/kaggriculture.json'
    body = specification.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
    if blob != 'b354d06b742fe48402513792253f1a5c29366b20':
        raise ValueError('Pinned official configuration specification changed')
    configuration = {key: value.get('default') if isinstance(value, dict) else value
                     for key, value in json.loads(body)['configuration'].items()}
    configuration['seed'] = None
    return {'observation': observation, 'configuration': configuration,
            'provenance': {
                'kind': 'retained development first-input workload',
                'fixture_path': str(fixture.relative_to(ROOT)), 'fixture_sha256': FIXTURE_SHA,
                'observation_sha256': hashlib.sha256(canonical(observation)).hexdigest(),
                'archive_sha256': ARCHIVE_SHA, 'archive_bytes': len(packed),
                'original_member': 'development-v2/sell-lonespear-9881001-seat0.jsonl.gz',
                'stream_key': STREAM, 'first_patch_value': 'streams[stream_key][0][0][2]',
                'first_row_sha256': hashlib.sha256(canonical(first)).hexdigest(),
                'observation_origin': 'SELL candidate facing lonespear-greedy, step0/player0',
                'target': 'unchanged WIDEFIELD lonespear-v18-scipy',
                'configuration_origin': 'explicit pinned engine defaults; not retained trace configuration',
                'configuration_spec_blob': blob,
                'configuration_sha256': hashlib.sha256(canonical(configuration)).hexdigest(),
                'expected_scipy_action': 'not retained; compare returned actions across scheduling cohorts',
                'original_failed_cell_input': False,
                'limits': 'Isolated first-action contention probe; not original concurrent candidate+opponent games'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result['provenance'], indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
