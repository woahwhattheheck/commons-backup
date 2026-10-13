#!/usr/bin/env python3
"""Prepare a pinned Kaggriculture bundle and run the existing official-engine driver.

Owner-authored continuation: MIT OR CC-BY-4.0; see LICENSE.
Preparation alone may download files. Run phases use verified cached sources.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
PREFIX = Path('revenue/kaggriculture')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b'\n')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_manifest():
    return json.loads((HERE / 'manifest.json').read_text())


def verify_bytes(data, entry):
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if blob != entry['git_blob'] or digest(data) != entry['sha256']:
        raise ValueError('Source bytes differ: ' + entry['path'])
    return data


def write_once(path, data):
    path = Path(path)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Existing bytes differ; use another output directory: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def prepare(bundle, checkout=None, engine_cache=None):
    bundle = Path(bundle).resolve()
    manifest = read_manifest()
    for group, destination, local, repository, ref in (
        ('files', bundle / 'source', checkout, manifest['repository'], manifest['source_ref']),
        ('engine_files', bundle / 'engine', engine_cache, manifest['engine_repository'], manifest['engine_ref']),
    ):
        for entry in manifest[group]:
            rel = entry['path'] if group == 'files' else entry['name']
            target = destination / rel
            if target.exists():
                verify_bytes(target.read_bytes(), entry)
                continue
            if local is not None:
                data = (Path(local) / rel).read_bytes()
            else:
                url = f'https://raw.githubusercontent.com/{repository}/{ref}/{entry["path"]}'
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read()
            write_once(target, verify_bytes(data, entry))
    write_once(bundle / 'manifest.json', canonical(manifest) + b'\n')
    study = load(bundle / 'source' / PREFIX / 'cloud-market/study.py', 'handoff_study_prepare')
    original = (bundle / 'source' / PREFIX / '20260907-offline-agent/incumbent_20260907.py').read_text()
    compact = study.build_variant(original, study.VARIANTS['compact22'], 'incumbent_20260907.py')
    write_once(bundle / 'generated/compact22.py', compact.encode())
    return verify(bundle)


def verify(bundle):
    bundle = Path(bundle).resolve()
    manifest = read_manifest()
    if json.loads((bundle / 'manifest.json').read_text()) != manifest:
        raise ValueError('Bundle manifest differs from this handoff')
    for entry in manifest['files']:
        verify_bytes((bundle / 'source' / entry['path']).read_bytes(), entry)
    for entry in manifest['engine_files']:
        verify_bytes((bundle / 'engine' / entry['name']).read_bytes(), entry)
    study = load(bundle / 'source' / PREFIX / 'cloud-market/study.py', 'handoff_study_verify')
    original = (bundle / 'source' / PREFIX / '20260907-offline-agent/incumbent_20260907.py').read_text()
    expected = study.build_variant(original, study.VARIANTS['compact22'], 'incumbent_20260907.py').encode()
    if (bundle / 'generated/compact22.py').read_bytes() != expected:
        raise ValueError('Generated compact22 differs from frozen study definition')
    return {'source_files': len(manifest['files']), 'engine_files': len(manifest['engine_files']),
            'source_ref': manifest['source_ref'], 'manifest_sha256': digest(canonical(manifest)),
            'compact22_sha256': digest(expected)}


def ensure_development(report_path, candidate_hash, manifest_hash, opponents=None):
    data = Path(report_path).read_bytes()
    report = json.loads(data)
    contract = report['contract']
    roster = opponents or {'lean20':'lean20', 'euler28':'euler28', 'compact22':'compact22'}
    expected = len(read_manifest()['seeds']['development']) * 2 * len(roster)
    if (contract['phase'] != 'development' or contract['candidate_sha256'] != candidate_hash
            or contract['manifest_sha256'] != manifest_hash or not report.get('complete')
            or contract['seeds'] != read_manifest()['seeds']['development']
            or contract.get('opponents') != roster
            or set(report.get('replay_by_opponent', {})) != set(roster)
            or not all(report.get('replay_by_opponent', {}).values())
            or report['expected_games'] != expected or len(report['games']) != expected
            or any(g['status'] != 'complete' for g in report['games'])):
        raise ValueError('Validation requires a complete development report for these exact bytes and sources')
    return digest(data)


def extra_opponents(items, hash_items, output):
    expected = {}
    for item in hash_items:
        label, sep, value = item.partition('=')
        if not sep or label in expected:
            raise ValueError('Use distinct --opponent-sha256 NAME=HASH entries')
        expected[label] = value
    sources = {}
    for item in items:
        label, sep, path = item.partition('=')
        if (not sep or not label or not all(c.isalnum() or c == '_' for c in label)
                or label in sources or label in {'lean20', 'euler28', 'compact22', 'incumbent36'}):
            raise ValueError('Use distinct non-reserved --opponent NAME=FILE entries')
        data = Path(path).read_bytes()
        if digest(data) != expected.get(label):
            raise ValueError('Opponent differs from declared SHA-256: ' + label)
        sources[label] = data
    if set(expected) != set(sources):
        raise ValueError('Each additional opponent needs exactly one source and SHA-256')
    paths = {}
    for label, data in sources.items():
        path = Path(output) / 'opponents' / (label + '.py')
        write_once(path, data)
        paths[label] = path
    return paths


def published_tests(bundle, output):
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    verify(bundle)
    output.mkdir(parents=True, exist_ok=True)
    source = bundle / 'source' / PREFIX
    results = []
    with tempfile.TemporaryDirectory(prefix='kag-handoff-tests-') as temporary:
        study_root = Path(temporary)
        (study_root / 'peer').mkdir()
        for name in ('main.py', 'incumbent_20260907.py', 'evaluate.py', 'ECONOMICS.md'):
            shutil.copyfile(source / '20260907-offline-agent' / name, study_root / 'peer' / name)
        (study_root / 'engine').symlink_to(bundle / 'engine', target_is_directory=True)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                   KAG_EVAL_ENGINE_DIR=str(bundle / 'engine'), KAG_STUDY_ROOT=str(study_root))
        for rel in ('20260907-offline-agent/test_agent.py', 'cloud-eval/test_evaluator.py',
                    'cloud-market/test_study.py', 'cloud-market/test_behavior.py'):
            path = source / rel
            log = output / (rel.replace('/', '__') + '.log')
            with log.open('w') as stream:
                completed = subprocess.run([sys.executable, '-B', str(path)], cwd=path.parent,
                                           env=env, stdout=stream, stderr=subprocess.STDOUT)
            result = {'test': rel, 'exit_code': completed.returncode,
                      'log': log.name, 'log_sha256': digest(log.read_bytes())}
            results.append(result)
            print(json.dumps(result), flush=True)
    write_json(output / 'tests.json', results)
    return int(any(result['exit_code'] != 0 for result in results))


def run(args):
    bundle, output = args.bundle.resolve(), args.output.resolve()
    proof = verify(bundle)
    manifest = read_manifest()
    source = bundle / 'source' / PREFIX
    lean = source / 'cloud-market/main.py'
    candidate_data = (args.candidate or lean).read_bytes()
    candidate_hash = digest(candidate_data)
    expected_hash = args.candidate_sha256 or digest(lean.read_bytes())
    if candidate_hash != expected_hash:
        raise ValueError('Candidate differs from declared SHA-256')
    if args.phase == 'calibration' and candidate_data != lean.read_bytes():
        raise ValueError('Calibration reproduces the published lean20 loss cases')
    if args.phase == 'calibration' and (args.opponent or args.opponent_sha256):
        raise ValueError('Calibration uses the two published opponents only')
    output.mkdir(parents=True, exist_ok=True)
    candidate = output / 'candidate/main.py'
    write_once(candidate, candidate_data)
    study = load(source / 'cloud-market/study.py', 'handoff_study_run')
    ev = load(source / 'cloud-eval/evaluate.py', 'handoff_evaluator')
    loader = source / '20260907-offline-agent/evaluate.py'
    engine, engine_hashes = ev.get_engine(bundle / 'engine', loader)
    opponents = {'euler28': source / '20260907-offline-agent/main.py',
                 'compact22': bundle / 'generated/compact22.py'}
    if args.phase != 'calibration':
        opponents = {'lean20': lean, **opponents}
    opponents.update(extra_opponents(args.opponent, args.opponent_sha256, output))
    development_hash = None
    if args.phase == 'validation':
        if args.development_report is None:
            raise ValueError('Supply --development-report from selection before validation')
        development_hash = ensure_development(args.development_report, candidate_hash, proof['manifest_sha256'],
                                             {k: digest(p.read_bytes()) for k, p in opponents.items()})
        opponents['incumbent36'] = source / '20260907-offline-agent/incumbent_20260907.py'
    seeds = manifest['seeds'][args.phase]
    contract = {'schema_version': 1, 'phase': args.phase, 'candidate_sha256': candidate_hash,
                'manifest_sha256': proof['manifest_sha256'], 'source_ref': manifest['source_ref'],
                'engine_ref': manifest['engine_ref'], 'engine_sha256': engine_hashes,
                'handoff_sha256': digest(Path(__file__).read_bytes()),
                'opponents': {k: digest(p.read_bytes()) for k, p in opponents.items()},
                'seeds': seeds, 'seats': [0, 1], 'episode_steps': 720, 'agent_rng_seed': 20260907,
                'action_rpc_seconds': 1.0, 'game_seconds': 120.0,
                'python': sys.version, 'platform': platform.platform(),
                'runtime_image': os.environ.get('KAG_RUNTIME_IMAGE', 'unrecorded'),
                'development_report_sha256': development_hash}
    write_once(output / 'contract.json', canonical(contract) + b'\n')
    journal = study.Journal(output / 'games.jsonl', contract)
    for label, opponent in opponents.items():
        for seed in seeds:
            for seat in (0, 1):
                key = f'{label}/{seed}/{seat}'
                if key in journal.rows:
                    continue
                specs = [str(candidate), str(opponent)] if seat == 0 else [str(opponent), str(candidate)]
                row = ev.play(engine, specs, bundle / 'engine', loader, seed, seat)
                row['opponent'] = label
                journal.put(key, row)
                print(json.dumps({k: row[k] for k in ('opponent', 'seed', 'candidate_seat', 'status', 'scores', 'failure')}), flush=True)
    games = list(journal.rows.values())
    summary = {label: study.paired_summary([g for g in games if g['opponent'] == label]) for label in opponents}
    replays = {}
    replay_games = []
    for label, opponent in opponents.items():
        repeated = ev.play(engine, [str(candidate), str(opponent)], bundle / 'engine', loader, seeds[0], 0)
        original = journal.rows[f'{label}/{seeds[0]}/0']
        replays[label] = (original['status'] == repeated['status'] == 'complete'
                          and original['scores'] == repeated['scores']
                          and original['trace_sha256'] == repeated['trace_sha256'])
        repeated['opponent'] = label
        replay_games.append(repeated)
    calibration = None
    if args.phase == 'calibration':
        calibration = {}
        for label, expected in {'euler28': [45533, 45485], 'compact22': [65734, 64471]}.items():
            row = journal.rows[f'{label}/4421/1']
            calibration[label] = row['status'] == 'complete' and row['scores'] == expected
    expected_games = len(seeds) * 2 * len(opponents)
    complete = (len(games) == expected_games and all(g['status'] == 'complete' for g in games)
                and all(replays.values()) and (calibration is None or all(calibration.values())))
    report = {'contract': contract, 'expected_games': expected_games, 'complete': complete,
              'summary': summary, 'games': games, 'replay_by_opponent': replays, 'replay_games': replay_games,
              'known_loss_calibration': calibration,
              'qualification': 'Pinned official-interpreter experiment. Replays and calibration are not new holdouts. Scores are in-game coins, not hosted rank or money earned.'}
    write_json(output / 'report.json', report)
    print('SUMMARY ' + json.dumps({'complete': complete, 'summary': summary, 'replays': replays, 'calibration': calibration}), flush=True)
    return 0 if complete else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare_parser = sub.add_parser('prepare')
    prepare_parser.add_argument('--bundle', required=True, type=Path)
    prepare_parser.add_argument('--from-checkout', type=Path)
    prepare_parser.add_argument('--engine-cache', type=Path)
    verify_parser = sub.add_parser('verify')
    verify_parser.add_argument('--bundle', required=True, type=Path)
    tests_parser = sub.add_parser('tests')
    tests_parser.add_argument('--bundle', required=True, type=Path)
    tests_parser.add_argument('--output', required=True, type=Path)
    runner = sub.add_parser('run')
    runner.add_argument('--bundle', required=True, type=Path)
    runner.add_argument('--phase', choices=['calibration', 'smoke', 'development', 'validation'], required=True)
    runner.add_argument('--candidate', type=Path)
    runner.add_argument('--candidate-sha256')
    runner.add_argument('--opponent', action='append', default=[], help='Additional pinned standalone: NAME=FILE')
    runner.add_argument('--opponent-sha256', action='append', default=[], help='Expected SHA-256: NAME=HASH')
    runner.add_argument('--development-report', type=Path)
    runner.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(args.bundle, args.from_checkout, args.engine_cache)))
    elif args.command == 'verify':
        print(json.dumps(verify(args.bundle)))
    elif args.command == 'tests':
        return published_tests(args.bundle, args.output)
    else:
        return run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
