#!/usr/bin/env python3
"""Validate compact seller-recovery claims and, optionally, the full evidence ZIP."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json_bytes(data: bytes):
    return json.loads(data.decode('utf-8'))


def inspect_report(report: dict) -> None:
    rows = report['records']
    count = report['calls_per_actor']
    if len(rows) != count or [r['step'] for r in rows] != list(range(count)):
        raise ValueError('incomplete ordered execution')
    n = report['cancel_step']
    if not 0 <= n < count:
        raise ValueError('invalid cancellation step')
    fallback_equal = rows[n]['reference_action'] == rows[n]['affected_action']
    action_diffs = [r['step'] for r in rows[n + 1:]
                    if r['reference_action'] != r['affected_action']]
    route_equal = all(r['reference_route'] == r['affected_route'] for r in rows)
    for row in rows:
        if row['actions_equal'] != (row['reference_action'] == row['affected_action']):
            raise ValueError('action comparison contradicts full actions')
        state_equal = row['reference_state_sha256'] == row['affected_state_sha256']
        if state_equal == bool(row['different_state_fields']):
            raise ValueError('state summary contradicts complete-state digest')
        if row['step'] < n and (not row['actions_equal'] or row['different_state_fields']):
            raise ValueError('different prefix before injection')
    if fallback_equal != report['fallback_equals_uninterrupted_action']:
        raise ValueError('fallback headline mismatch')
    if action_diffs != report['later_action_differences']:
        raise ValueError('action-difference headline mismatch')
    if route_equal != report['all_routes_equal']:
        raise ValueError('route headline mismatch')
    if report['continuity_preserved'] != (fallback_equal and not action_diffs):
        raise ValueError('continuity headline mismatch')
    if report['new_games'] != 0 or report['engine_interpreter_calls'] != 0:
        raise ValueError('incorrect evidence category')
    if any(e['parent_calls'] != count for e in report['actual_parent_events']):
        raise ValueError('parent-call correspondence mismatch')


def validate_compact(summary: dict, pins: dict) -> None:
    if summary['schema'] != 'titan-seller-recovery-current-checkpoint-v1':
        raise ValueError('unexpected summary schema')
    cp = summary['checkpoint']
    if cp['archive_sha256'] != pins['archive_sha256']:
        raise ValueError('archive pin mismatch')
    if cp['source_manifest_sha256'] != pins['source_manifest_sha256']:
        raise ValueError('source-manifest pin mismatch')
    if cp['runtime_files'] != 78 or cp['archive_bytes'] != 290630:
        raise ValueError('current package size/count mismatch')
    treatments = summary['execution']['treatments']
    expected = {
        'baseline': (450, [451, 453], False, 1),
        'restored': (450, [], True, 0),
        'negative': (447, [449, 453], False, 1),
    }
    if set(treatments) != set(expected):
        raise ValueError('unexpected treatment set')
    for name, (step, diffs, continuity, rc) in expected.items():
        t = treatments[name]
        if (t['cancel_step'], t['through'], t['calls_per_actor']) != (step, 718, 719):
            raise ValueError(f'{name} execution boundary mismatch')
        if t['later_action_differences'] != diffs or t['continuity_preserved'] is not continuity:
            raise ValueError(f'{name} result mismatch')
        if t['expected_require_continuity_exit'] != rc:
            raise ValueError(f'{name} exit mismatch')
        if not t['fallback_equals_uninterrupted_action'] or not t['all_routes_equal']:
            raise ValueError(f'{name} lost fallback or route identity')
        if t['features'].get('redundant_hire') is not False:
            raise ValueError(f'{name} did not exercise current default feature state')
    if summary['execution']['actual_agent_calls'] != 4314:
        raise ValueError('agent-call total mismatch')
    if summary['execution']['actual_parent_calls'] != 4314:
        raise ValueError('parent-call total mismatch')
    if summary['execution']['actual_transform_calls'] != 4311:
        raise ValueError('transform-call total mismatch')
    if summary['execution']['new_games'] != 0 or summary['execution']['engine_interpreter_calls'] != 0:
        raise ValueError('compact evidence category mismatch')


def validate_evidence(path: Path, summary: dict, pins: dict) -> None:
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts for n in names):
            raise ValueError('unsafe evidence member path')
        manifest = load_json_bytes(zf.read('MANIFEST.json'))
        expected_names = set(manifest['members'])
        if names != expected_names | {'MANIFEST.json'}:
            raise ValueError('evidence inventory mismatch')
        for name, meta in manifest['members'].items():
            data = zf.read(name)
            if len(data) != meta['bytes'] or digest_bytes(data) != meta['sha256']:
                raise ValueError(f'evidence member mismatch: {name}')
        archive = zf.read('canonical/titan-current.tar.gz')
        if len(archive) != summary['checkpoint']['archive_bytes'] or digest_bytes(archive) != pins['archive_sha256']:
            raise ValueError('canonical archive bytes mismatch')
        for name, wanted in pins['sha256'].items():
            data = zf.read('runtime/' + name)
            if digest_bytes(data) != wanted:
                raise ValueError(f'current runtime pin mismatch: {name}')
        encoded = zf.read('inputs/candidate-inputs.jsonl.gz')
        if digest_bytes(encoded) != summary['prior_discriminator']['input_reused_unchanged_sha256']:
            raise ValueError('retained encoded input mismatch')
        with gzip.GzipFile(fileobj=__import__('io').BytesIO(encoded)) as f:
            decoded = f.read()
        receipt = load_json_bytes(zf.read('inputs/ORIGINAL-INPUT-RECEIPT.json'))
        if digest_bytes(decoded) != receipt['input_jsonl_sha256']:
            raise ValueError('retained decoded input mismatch')
        for name in ('baseline', 'restored', 'negative'):
            data = zf.read(f'results/{name}.json')
            if digest_bytes(data) != summary['execution']['treatments'][name]['report_sha256']:
                raise ValueError(f'{name} report digest mismatch')
            report = load_json_bytes(data)
            inspect_report(report)
            if report['source_pins'] != pins:
                raise ValueError(f'{name} source pins mismatch')
    print('FULL_PASS: compact receipt, source pins, manifest, archive, inputs and three 719-call reports agree')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--summary', type=Path, default=Path(__file__).with_name('CURRENT-RESULTS.json'))
    ap.add_argument('--pins', type=Path, default=Path(__file__).with_name('CURRENT-SOURCE-PINS.json'))
    ap.add_argument('--evidence', type=Path)
    args = ap.parse_args()
    summary = json.loads(args.summary.read_text())
    pins = json.loads(args.pins.read_text())
    validate_compact(summary, pins)
    if args.evidence:
        validate_evidence(args.evidence, summary, pins)
    else:
        print('COMPACT_PASS: current checkpoint receipt and treatment boundaries agree')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
