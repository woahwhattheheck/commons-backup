"""Development-only near-clone diagnostic. Does not repeat the primary panel."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import panel


def reusable_baseline(previous: dict, frozen: dict) -> list[dict]:
    old = previous['frozen']
    fields = ('schema', 'panel', 'seeds', 'source', 'infrastructure', 'opponent')
    if any(old.get(field) != frozen.get(field) for field in fields):
        raise ValueError('Baseline differs in source, infrastructure or panel')
    if old['adapters']['original'] != frozen['adapters']['original']:
        raise ValueError('Baseline original adapter differs')
    rows = [dict(row) for row in previous['games'] if row['arm'] == 'baseline']
    panel.summarize(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kg-root', type=Path, default=panel.KG)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-new-games', type=int, default=0)
    parser.add_argument('--freeze-only', action='store_true')
    parser.add_argument('--baseline-report', type=Path)
    args = parser.parse_args()
    if args.max_new_games < 0:
        parser.error('--max-new-games must be nonnegative')
    kg, runtime, engine_dir, output = (p.resolve() for p in
                                      (args.kg_root, args.runtime, args.engine_dir, args.output))
    package = ROOT / 'barnyard-v7'
    wrapper = Path(__file__).with_name('no_preempt.py')
    if not (runtime / 'controls.json').exists():
        panel.prepare(kg, runtime)
    evaluator = panel.load(kg / 'cloud-eval/evaluate.py', 't07_nearclone_evaluator')
    panel.adapter(kg, package / 'main.py', runtime / 'nearclone-original.py')
    panel.adapter(kg, wrapper, runtime / 'nearclone-off.py')
    frozen = {'schema': 'titan.t07.nearclone.v1', 'panel': 'development-nearclone',
              'seeds': panel.SEEDS['development'], 'source': panel.source_tree(package),
              'wrapper_sha256': panel.digest(wrapper), 'driver_sha256': panel.digest(Path(__file__)),
              'panel_driver_sha256': panel.digest(Path(panel.__file__)),
              'infrastructure': panel.control_identity(kg, runtime, engine_dir, evaluator),
              'adapters': {name: panel.digest(runtime / ('nearclone-' + name + '.py'))
                           for name in ('original', 'off')},
              'arms': {'baseline': 'unchanged V7', 'candidate': 'V7 with _PREEMPT_ENABLED=False'},
              'opponent': 'unchanged V7',
              'limits': 'Exploratory two-seed ablation after primary panel. No held seeds or promotion.'}
    freeze_path = output.with_suffix('.freeze.json')
    if freeze_path.exists() and json.loads(freeze_path.read_text()) != frozen:
        raise ValueError('Frozen experiment differs; preserve this run and use a new output')
    if not freeze_path.exists():
        panel.write_json(freeze_path, frozen)
    if args.freeze_only:
        print(json.dumps({'freeze_sha256': panel.digest(freeze_path)}))
        return
    report = {'frozen': frozen, 'freeze_sha256': panel.digest(freeze_path), 'games': []}
    if output.exists():
        report = json.loads(output.read_text())
        if report['frozen'] != frozen or report['freeze_sha256'] != panel.digest(freeze_path):
            raise ValueError('Report differs from frozen experiment')
    elif args.baseline_report:
        report['games'] = reusable_baseline(json.loads(args.baseline_report.read_text()), frozen)
        report['baseline_receipt_sha256'] = panel.digest(args.baseline_report)
        report['baseline_reuse_note'] = 'Preserves failed wrapper attempt separately; only unchanged baseline rows reused.'
    panel.summarize(report['games'])
    completed = {panel.key(row) for row in report['games']}
    engine, _ = evaluator.get_engine(engine_dir)
    count = 0
    for seed in frozen['seeds']:
        for seat in (0, 1):
            for arm in ('baseline', 'candidate'):
                if (arm, seed, 'barnyard-v7', seat) in completed:
                    continue
                target = runtime / ('nearclone-original.py' if arm == 'baseline' else 'nearclone-off.py')
                rival = runtime / 'nearclone-original.py'
                specs = [str(target), str(rival)] if seat == 0 else [str(rival), str(target)]
                trace = output.parent / (output.stem + '-traces') / f'{arm}-{seed}-barnyard-v7-{seat}.jsonl.gz'
                with panel.trace_game(engine, trace):
                    row = evaluator.play(engine, specs, engine_dir, evaluator.LOADER, seed, seat)
                row.update(arm=arm, opponent='barnyard-v7', full_trace=str(trace),
                           full_trace_sha256=panel.digest(trace))
                report['games'].append(row)
                report['summary'] = panel.summarize(report['games'])
                panel.write_json(output, report)
                print(json.dumps({k: row[k] for k in ('arm', 'seed', 'candidate_seat', 'status', 'scores', 'failure')}), flush=True)
                count += 1
                if args.max_new_games and count >= args.max_new_games:
                    return
    print(json.dumps(report['summary']), flush=True)


if __name__ == '__main__':
    main()
