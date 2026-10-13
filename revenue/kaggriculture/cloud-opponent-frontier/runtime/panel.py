"""T07 public-opponent comparison using the existing pinned official engine.

No download, notebook execution, Kaggle write, or replacement game logic.
Source adaptation and license/lineage review precede use of --candidate.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
KG = HERE.parents[1]
ARLENE_SHA = '1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4'
SEEDS = {'development': [9770001, 9770019], 'held': [9770101, 9770119]}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f'Cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def source_tree(root: Path) -> dict[str, str]:
    """Hash actual dependency bytes, including precompiled libraries, not just entry."""
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not any(x in ('.git', '__pycache__') for x in p.parts)
            and p.suffix != '.pyc'}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def adapter(kg: Path, target: Path, output: Path) -> None:
    pack = load(kg / 'cloud-pack/pack.py', 't07_existing_pack')
    pack.write_adapter(output, target.resolve(strict=True))
    guard = kg / 'cloud-frontier-policy/next-panel'
    output.write_text('import sys\n' + f'sys.path.insert(0, {str(guard)!r})\n'
                      'from offline import restrict\nrestrict()\n' + output.read_text())


def prepare(kg: Path, runtime: Path) -> dict:
    """Prepare intact controls through the already licensed file-loader contract."""
    vendor = kg / 'cloud-frontier-policy/next-panel/vendor'
    if digest(vendor / 'arlene.py') != ARLENE_SHA:
        raise ValueError('Arlene control differs from the T07 source pin')
    runtime.mkdir(parents=True, exist_ok=True)
    shutil.copytree(vendor / 'apex', runtime / 'apex', dirs_exist_ok=True)
    command = ['g++', '-O3', '-std=c++17', '-Wall', '-Wextra', '-pedantic',
               '-shared', '-fPIC', '-Isource/include', '-o', 'agent.so',
               'source/policy.cpp', 'submission_bridge.cpp']
    result = subprocess.run(command, cwd=runtime / 'apex', check=True,
                            capture_output=True, text=True)
    (runtime / 'compile.txt').write_text(result.stdout + result.stderr)
    adapter(kg, vendor / 'arlene.py', runtime / 'arlene-adapter.py')
    adapter(kg, runtime / 'apex/main.py', runtime / 'apex-adapter.py')
    info = {'compiler': subprocess.check_output(['g++', '--version'], text=True),
            'compile_command': command, 'arlene_sha256': ARLENE_SHA,
            'apex_source': source_tree(vendor / 'apex'),
            'apex_library_sha256': digest(runtime / 'apex/agent.so')}
    write_json(runtime / 'controls.json', info)
    return info


def control_identity(kg: Path, runtime: Path, engine_dir: Path, ev) -> dict:
    vendor = kg / 'cloud-frontier-policy/next-panel/vendor'
    if digest(vendor / 'arlene.py') != ARLENE_SHA:
        raise ValueError('Arlene control differs from the T07 source pin')
    for name, expected in source_tree(vendor / 'apex').items():
        if digest(runtime / 'apex' / name) != expected:
            raise ValueError(f'Apex runtime differs from preserved source: {name}')
    return {'engine_ref': ev.ENGINE_REF, 'engine': ev.verify_sources(engine_dir),
            'evaluator_sha256': digest(Path(ev.__file__)),
            'loader_sha256': digest(ev.LOADER),
            'official_loader_sha256': digest(kg / 'cloud-pack/official.py'),
            'pack_sha256': digest(kg / 'cloud-pack/pack.py'),
            'adapters': {name: digest(runtime / (name + '-adapter.py')) for name in ('arlene', 'apex')},
            'upstream': source_tree(kg / 'cloud-pack/upstream'),
            'guard_sha256': digest(kg / 'cloud-frontier-policy/next-panel/offline.py'),
            'arlene_sha256': digest(vendor / 'arlene.py'),
            'apex_source': source_tree(vendor / 'apex'),
            'apex_runtime': source_tree(runtime / 'apex')}


def key(row: dict) -> tuple:
    return row['arm'], row['seed'], row['opponent'], row['candidate_seat']


def outcome(row: dict) -> str:
    if row['status'] != 'complete':
        return 'FAILED'
    seat = row['candidate_seat']
    margin = row['scores'][seat] - row['scores'][1 - seat]
    return 'W' if margin > 0 else 'L' if margin < 0 else 'T'


def summarize(rows: list[dict]) -> dict:
    indexed = {key(r): r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError('Duplicate arm/seed/opponent/seat rows')
    counts = {}
    for arm in sorted({r['arm'] for r in rows}):
        for opponent in sorted({r['opponent'] for r in rows}):
            selected = [r for r in rows if r['arm'] == arm and r['opponent'] == opponent]
            counts[f'{arm}/{opponent}'] = dict(Counter(outcome(r) for r in selected))
    pairs = []
    for row in rows:
        if row['arm'] != 'candidate':
            continue
        base = indexed.get(('baseline', row['seed'], row['opponent'], row['candidate_seat']))
        if base is None:
            continue
        record = {'seed': row['seed'], 'opponent': row['opponent'],
                  'seat': row['candidate_seat'], 'baseline': outcome(base),
                  'candidate': outcome(row), 'cash_delta': None, 'margin_delta': None}
        if 'FAILED' not in (record['baseline'], record['candidate']):
            s = row['candidate_seat']
            record['cash_delta'] = row['scores'][s] - base['scores'][s]
            record['margin_delta'] = record['cash_delta'] - (row['scores'][1-s] - base['scores'][1-s])
        pairs.append(record)
    return {'counts': counts, 'paired': pairs,
            'flips': dict(Counter(p['baseline'] + '->' + p['candidate'] for p in pairs)),
            'max_action_seconds': max((a.get('max_call_seconds', 0)
                                       for r in rows for a in r.get('actors', [])), default=0)}


@contextmanager
def trace_game(engine, path: Path):
    """Preserve actual observations/actions, including losses; never feed traces back."""
    original = engine.interpreter
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', encoding='utf-8') as stream:
        def recorded(state, env):
            before = json.loads(json.dumps(state))
            result = original(state, env)
            stream.write(json.dumps({'before': before, 'after': state},
                                    separators=(',', ':'), allow_nan=False) + '\n')
            return result
        engine.interpreter = recorded
        try:
            yield
        finally:
            engine.interpreter = original


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kg-root', type=Path, default=KG)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--engine-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--panel', choices=SEEDS, default='development')
    p.add_argument('--candidate', type=Path)
    p.add_argument('--candidate-root', type=Path)
    p.add_argument('--baseline-report', type=Path)
    p.add_argument('--freeze-only', action='store_true')
    p.add_argument('--max-new-games', type=int, default=0, help='0 runs all remaining games')
    args = p.parse_args()
    kg, runtime, output = args.kg_root.resolve(), args.runtime.resolve(), args.output.resolve()
    engine_dir = args.engine_dir.resolve()
    if args.max_new_games < 0:
        p.error('--max-new-games must be nonnegative')
    if args.candidate and not args.candidate_root:
        p.error('--candidate-root must include the complete reviewed dependency closure')
    if args.panel == 'held' and not args.candidate:
        p.error('Held baseline is run only after an opponent source has been frozen')
    if not (runtime / 'controls.json').exists():
        prepare(kg, runtime)
    ev = load(kg / 'cloud-eval/evaluate.py', 't07_existing_evaluator')
    identity = control_identity(kg, runtime, engine_dir, ev)
    candidate = None
    if args.candidate:
        root, entry = args.candidate_root.resolve(strict=True), args.candidate.resolve(strict=True)
        if not entry.is_relative_to(root):
            p.error('--candidate must be inside --candidate-root')
        if output.is_relative_to(root) or runtime.is_relative_to(root):
            p.error('Write results/runtime outside the frozen candidate source tree')
        candidate = {'entry': str(entry.relative_to(root)), 'files': source_tree(root)}
        adapter(kg, entry, runtime / 'candidate-adapter.py')
        candidate['adapter_sha256'] = digest(runtime / 'candidate-adapter.py')
    frozen = {'schema': 'titan.t07.panel.v1', 'panel': args.panel, 'seeds': SEEDS[args.panel],
              'controls': identity, 'candidate': candidate,
              'driver_sha256': digest(Path(__file__))}
    freeze_path = output.with_suffix('.freeze.json')
    if freeze_path.exists():
        if json.loads(freeze_path.read_text()) != frozen:
            raise ValueError('Frozen source/panel differs; preserve this run and use a new output')
    else:
        write_json(freeze_path, frozen)
    if args.freeze_only:
        print(json.dumps({'freeze': str(freeze_path), 'sha256': digest(freeze_path)}))
        return
    report = {'freeze_sha256': digest(freeze_path), 'frozen': frozen, 'games': []}
    if output.exists():
        report = json.loads(output.read_text())
        if report['frozen'] != frozen or report['freeze_sha256'] != digest(freeze_path):
            raise ValueError('Report identity differs from the frozen source')
    elif args.baseline_report:
        base = json.loads(args.baseline_report.read_text())
        if (base['frozen']['controls'] != identity or base['frozen']['panel'] != args.panel
                or base['frozen']['seeds'] != frozen['seeds']):
            raise ValueError('Baseline report is not paired to these controls/panel/seeds')
        report['games'] = [dict(row) for row in base['games'] if row['arm'] == 'baseline']
        report['baseline_receipt_sha256'] = digest(args.baseline_report)
    summarize(report['games'])  # Reject duplicate rows before consuming another game.
    completed = {key(row) for row in report['games']}
    engine, _ = ev.get_engine(engine_dir)
    arms = ['baseline', 'candidate'] if candidate else ['baseline']
    new_games = 0
    for seed in frozen['seeds']:
        for opponent in ('arlene', 'apex'):
            for seat in (0, 1):
                for arm in arms:
                    if (arm, seed, opponent, seat) in completed:
                        continue
                    entry = runtime / ('candidate-adapter.py' if arm == 'candidate' else 'arlene-adapter.py')
                    rival = runtime / (opponent + '-adapter.py')
                    specs = [str(entry), str(rival)] if seat == 0 else [str(rival), str(entry)]
                    trace = output.parent / (output.stem + '-traces') / f'{arm}-{seed}-{opponent}-{seat}.jsonl.gz'
                    with trace_game(engine, trace):
                        row = ev.play(engine, specs, engine_dir, ev.LOADER, seed, seat)
                    row.update(arm=arm, opponent=opponent,
                               full_trace=str(trace), full_trace_sha256=digest(trace))
                    report['games'].append(row)
                    report['summary'] = summarize(report['games'])
                    write_json(output, report)
                    print(json.dumps({k: row[k] for k in ('arm', 'seed', 'opponent', 'candidate_seat', 'status', 'scores', 'failure')}), flush=True)
                    new_games += 1
                    if args.max_new_games and new_games >= args.max_new_games:
                        return
    print(json.dumps(report.get('summary', summarize(report['games']))), flush=True)


if __name__ == '__main__':
    main()
