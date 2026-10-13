#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parents[2]
WF1_SOURCE = SOURCE_ROOT / 'candidates/v4/repairs/gameplay/wf1-wheat-fertilize'

PINS = {
    'r04_wheat_fert.py': 'b35a30431f64c1d6b40d1d599190338a9d50b555',
    'wf1_current_adapter.py': '5b8f4c0144ce43ae449373a6a188ce03409a16ee',
    'WF1-CURRENT-NATIVE-FIELD-RECEIPT.json': 'e703d88cd40bb5af96aabaaa4327c1b7a81380aa',
}


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_blob(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    actual = git_blob_sha(data)
    if actual != expected:
        raise ValueError(f'{path.name} blob mismatch: {actual} != {expected}')
    return data


def materialize(runtime: Path, output: Path, *, expected_main_blob: str,
                expected_config_blob: str, source_root: Path = SOURCE_ROOT) -> dict:
    runtime = runtime.resolve()
    output = output.resolve()
    if runtime == output or runtime in output.parents:
        raise ValueError('output must differ from runtime and not be nested under it')
    main_path = runtime / 'main.py'
    config_path = runtime / 'TITAN-CONFIG.json'
    if not main_path.is_file() or not config_path.is_file():
        raise FileNotFoundError('runtime must contain main.py and TITAN-CONFIG.json')
    if git_blob_sha(main_path.read_bytes()) != expected_main_blob:
        raise ValueError('baseline main.py identity mismatch')
    if git_blob_sha(config_path.read_bytes()) != expected_config_blob:
        raise ValueError('baseline TITAN-CONFIG.json identity mismatch')
    if output.exists():
        raise FileExistsError(output)

    wf1 = source_root / 'candidates/v4/repairs/gameplay/wf1-wheat-fertilize'
    source_bytes = {name: require_blob(wf1 / name, blob) for name, blob in PINS.items()}
    receipt = json.loads(source_bytes['WF1-CURRENT-NATIVE-FIELD-RECEIPT.json'])
    summary = receipt.get('summary', {})
    validation = receipt.get('validation', {})
    if not (validation.get('complete_cells') == 8
            and validation.get('game_failures') == 0
            and summary.get('positive_margin_cells') == 8
            and summary.get('negative_margin_cells') == 0):
        raise ValueError('retained WF1 field receipt no longer matches admitted evidence')

    shutil.copytree(runtime, output)
    (output / 'r04_wheat_fert.py').write_bytes(source_bytes['r04_wheat_fert.py'])
    (output / 'wf1_current_adapter.py').write_bytes(source_bytes['wf1_current_adapter.py'])
    (output / 'wf1_v5_entry.py').write_bytes((HERE / 'entry.py').read_bytes())

    manifest = {
        'schema': 'titan.v5.wf1-current-native/v1',
        'baseline': {
            'main_git_blob': expected_main_blob,
            'config_git_blob': expected_config_blob,
            'main_sha256': sha256(main_path),
            'config_sha256': sha256(config_path),
        },
        'component': {
            'ordering': 'after_parent_main_agent',
            'donor_git_blob': PINS['r04_wheat_fert.py'],
            'adapter_git_blob': PINS['wf1_current_adapter.py'],
            'evidence_git_blob': PINS['WF1-CURRENT-NATIVE-FIELD-RECEIPT.json'],
            'field_summary': summary,
        },
    }
    (output / 'WF1-V5-MATERIALIZATION.json').write_text(
        json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + '\n',
        encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-main-git-blob', required=True)
    parser.add_argument('--expected-config-git-blob', required=True)
    args = parser.parse_args()
    result = materialize(args.runtime, args.output,
                         expected_main_blob=args.expected_main_git_blob,
                         expected_config_blob=args.expected_config_git_blob)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
