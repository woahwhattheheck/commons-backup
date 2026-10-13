"""Trace-bound market and automatic-deposit diagnostics; no policy invocation.

For each retained day boundary, apply only the recorded unit actions, official
market function, and automatic inventory deposit to copies of that turn's two
observations. No game initialization or new seed is used. The next recorded
private state is a check, never a runtime input. Terminal liquidation is checked
against actual official market fills rather than merely requested SELL totals.
"""
from __future__ import annotations
import argparse
import collections
import copy
import gzip
import importlib.util
import json
from pathlib import Path
from typing import Any
from audit_throughput import sha256


class Struct(dict):
    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def load_engine(root: Path):
    loader_path = root / 'candidate/checks/reference/evaluator/loader.py'
    engine_path = root / 'vm/engine/engine'
    # Require all input bytes to exist, so the preserved loader never fetches.
    for name in ('kaggriculture.py', 'kaggriculture.json', 'utils.py'):
        if not (engine_path / name).is_file():
            raise ValueError(f'Missing frozen engine input: {name}')
    spec = importlib.util.spec_from_file_location('throughput_preserved_loader', loader_path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load preserved engine loader')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine, hashes = module.get_engine(engine_path)
    return engine, hashes, sha256(loader_path)


def apply_units(engine: Any, farm: dict, private: dict, action: dict, cfg: dict, step: int):
    """Exact official atomic PLANT preflight and ordered unit dispatch."""
    action = action if isinstance(action, dict) else {}
    hands = action.get('hands', [])
    hands = hands if isinstance(hands, list) else []
    acts = [action.get('farmer', ['PASS']), *hands]
    demand = collections.Counter(a[1] for a in acts
                                 if isinstance(a, list) and len(a) >= 2 and a[0] == 'PLANT')
    blocked = {p for p, n in demand.items() if n > private.get('seeds', {}).get(p, 0)}
    day_length = max(1, int(cfg.get('turnsPerDay', 24)))
    for idx, a in enumerate(acts):
        if isinstance(a, list) and len(a) >= 2 and a[0] == 'PLANT' and a[1] in blocked:
            a = ['PASS']
        engine._apply_unit_action(farm, private, idx, a, int(cfg.get('boardSize', 10)),
                                  step // day_length, day_length, int(cfg.get('shedCapacity', 100)))


def audit_pair(engine: Any, rows: list[dict]) -> dict:
    """Replay observable deterministic phases for one original paired turn."""
    rows = sorted(rows, key=lambda r: r['seat'])
    if [r['seat'] for r in rows] != [0, 1]:
        raise ValueError('Exactly one recorded request per seat is required')
    step = rows[0]['step']
    cfg = rows[0]['configuration']
    if rows[1]['step'] != step or rows[1]['configuration'] != cfg:
        raise ValueError('Mismatched recorded turn or configuration')
    if rows[0]['observation']['farms'] != rows[1]['observation']['farms']:
        raise ValueError('Players do not share the same recorded public farms')
    farms = copy.deepcopy(rows[0]['observation']['farms'])
    market = copy.deepcopy(rows[0]['observation']['market'])
    state = []
    for row in rows:
        seat = row['seat']
        obs = copy.deepcopy(row['observation'])
        obs['farms'], obs['market'] = farms, market
        action = copy.deepcopy(row['response']['action'])
        apply_units(engine, farms[seat], obs['private'], action, cfg, step)
        state.append(Struct(observation=Struct(obs), action=action, status='ACTIVE', reward=0))
    engine._process_market(state, Struct(configuration=Struct(cfg)))
    automatic = (step + 1) % max(1, int(cfg.get('turnsPerDay', 24))) == 0
    losses = []
    if automatic:
        for seat, s in enumerate(state):
            private = s.observation.private
            shed_before = dict(private['shed'])
            carried = collections.Counter()
            for inv in private['inventories']:
                carried.update({p: n for p, n in inv.items() if n > 0})
            engine._drop_inventories_to_shed(private, int(cfg.get('shedCapacity', 100)))
            lost = {p: n - (private['shed'].get(p, 0) - shed_before.get(p, 0))
                    for p, n in carried.items()
                    if n > private['shed'].get(p, 0) - shed_before.get(p, 0)}
            losses.append({'seat': seat, 'carried': dict(carried), 'lost': lost,
                           'shed_used_before': sum(shed_before.values())})
            # The official end-of-day operation resets workers after deposit.
            private['inventories'] = [{}]
    return {'step': step, 'automatic_deposit': automatic, 'losses': losses,
            'privates': [s.observation.private for s in state],
            'money': [f['money'] for f in farms]}


def audit_boundaries(root: Path, output: Path) -> dict:
    summary = json.loads((root / 'FINAL-SUMMARY.json').read_text())
    engine, hashes, loader_hash = load_engine(root)
    all_games = []
    losses = collections.Counter()
    boundary_count = mismatches = 0
    for item in summary['games']:
        report_path = (root / item['report']).resolve()
        if not report_path.is_relative_to(root.resolve()):
            raise ValueError('Report escapes the input directory')
        if sha256(report_path) != item['report_sha256']:
            raise ValueError('Report hash differs from retained summary')
        report = json.loads(report_path.read_text())
        trace_path = (report_path.parent / report['trace_file']).resolve()
        if not trace_path.is_relative_to(root.resolve()):
            raise ValueError('Trace escapes the input directory')
        if sha256(trace_path) != report['trace_file_sha256']:
            raise ValueError('Trace hash differs from retained report')
        records = json.loads(gzip.decompress(trace_path.read_bytes()))
        by_step = collections.defaultdict(list)
        for row in records:
            by_step[row['step']].append(row)
        game, checks = report['game'], []
        own = game['candidate_seat']
        for step in sorted(by_step):
            cfg = by_step[step][0]['configuration']
            terminal = step == int(cfg.get('episodeSteps', 720)) - 2
            if (step + 1) % max(1, int(cfg.get('turnsPerDay', 24))) != 0 and not terminal:
                continue
            audited = audit_pair(engine, by_step[step])
            if audited['automatic_deposit']:
                boundary_count += 1
                next_rows = sorted(by_step[step + 1], key=lambda r: r['seat'])
                matched = all(audited['privates'][seat] == next_rows[seat]['observation']['private']
                              and audited['money'][seat] == next_rows[seat]['observation']['farms'][seat]['money']
                              for seat in (0, 1))
                mismatches += not matched
                own_loss = audited['losses'][own]
                losses.update(own_loss['lost'])
                checks.append({'step': step, 'both_private_and_cash_match_next': matched,
                               'own_automatic_deposit': own_loss})
            if terminal:
                inv = audited['privates'][own]
                terminal_result = {'step': step, 'money': audited['money'],
                                   'money_matches_report': audited['money'] == game['scores'],
                                   'remaining_shed': {p: n for p, n in inv['shed'].items() if n > 0},
                                   'remaining_held': [{p: n for p, n in i.items() if n > 0}
                                                      for i in inv['inventories']]}
        all_games.append({'seed': game['seed'], 'seat': own, 'opponent': game['opponent'],
                          'report_sha256': sha256(report_path), 'trace_sha256': sha256(trace_path),
                          'boundaries': checks, 'terminal': terminal_result})
        print(json.dumps({'seed': game['seed'], 'seat': own,
                          'boundary_checks': len(checks), 'terminal': terminal_result}), flush=True)
    result = {'scope': 'Offline trace-bound market/automatic-deposit diagnostics; zero new games, zero policy calls.',
              'operation': summary['operation'], 'archive_sha256': summary['archive_sha256'],
              'engine_files_sha256': hashes, 'loader_sha256': loader_hash,
              'games_read': len(all_games), 'automatic_boundaries': boundary_count,
              'next_state_mismatches': mismatches, 'own_automatic_lost_products': dict(losses),
              'terminal_score_mismatches': sum(not g['terminal']['money_matches_report'] for g in all_games),
              'games': all_games}
    output.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit_boundaries(args.bundle_dir, args.output)
