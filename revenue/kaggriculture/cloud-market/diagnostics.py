"""Read-only game economics observer and exact-replay diagnostic export.

The upstream interpreter is called unchanged. Counters describe requested
operations, not assumed successful trades. Daily values are post-refresh state.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import study


class ObservedEngine:
    def __init__(self, engine):
        self.engine = engine
        self.specification = engine.specification
        self.units = [Counter(), Counter()]
        self.orders = [Counter(), Counter()]
        self.peak_hands = [0, 0]
        self.days = []

    def interpreter(self, state, env):
        initialized = bool(state[0].observation.get('farms'))
        if initialized:
            for seat, entry in enumerate(state):
                action = entry.action if isinstance(entry.action, dict) else {}
                unit_actions = [action.get('farmer', ['PASS'])]
                hands = action.get('hands', [])
                if isinstance(hands, list): unit_actions.extend(hands)
                for op in unit_actions:
                    if isinstance(op, list) and op and isinstance(op[0], str):
                        self.units[seat][op[0]] += 1
                orders = action.get('market', [])
                if isinstance(orders, list):
                    for op in orders:
                        if isinstance(op, list) and op and isinstance(op[0], str):
                            self.orders[seat][op[0]] += 1
        result = self.engine.interpreter(state, env)
        obs = state[0].observation
        for seat, farm in enumerate(obs.farms):
            self.peak_hands[seat] = max(self.peak_hands[seat], len(farm.get('hands', [])))
        step = obs.get('step', -1)
        finished = all(s.status == 'DONE' for s in state)
        if not initialized or (step + 1) % env.configuration.turnsPerDay == 0 or finished:
            farms = []
            for seat, farm in enumerate(obs.farms):
                species = Counter()
                held_yield = 0
                pending_care = 0
                for row in farm['tiles']:
                    for tile in row:
                        if isinstance(tile, dict) and 'animal' in tile:
                            species[tile['animal']] += 1
                            held_yield += tile.get('yield_units', 0)
                            pending_care += tile.get('pending_care_bonus', 0)
                private = state[seat].observation.private
                stored = Counter(private.get('shed', {}))
                for inv in private.get('inventories', []): stored.update(inv)
                farms.append(dict(money=farm['money'], animals=dict(species),
                                  land_quadrants=len(farm['unlocked_quadrants']),
                                  stored_and_carried_items=dict(stored),
                                  unharvested_animal_yield=held_yield, pending_care_bonus=pending_care))
            self.days.append(dict(step=step if initialized else -1, day=obs.day,
                                  farms=farms, prices=copy.deepcopy(obs.market['prices']),
                                  inventory=copy.deepcopy(obs.market['inventory'])))
        return result

    def report(self):
        return dict(unit_operation_requests=[dict(c) for c in self.units],
                    market_order_requests=[dict(c) for c in self.orders],
                    peak_actual_hands=self.peak_hands, daily=self.days,
                    counter_semantics='Requested operations, not proof of successful execution. Daily snapshots follow refresh; stored items exclude seed stock.')


def export(root):
    root = Path(root).resolve()
    ev = study.evaluator()
    study.verify_peer(root)
    engine, _ = ev.get_engine(root/'engine', root/'peer/evaluate.py')
    validation = json.loads((root/'validation.json').read_text())
    selection = json.loads((root/'selection.json').read_text())
    candidate = root/'selected_main.py'
    if study.digest(candidate.read_bytes()) != selection['candidate_sha256']:
        raise ValueError('Selected artifact bytes changed')
    rivals = dict(euler28=root/'peer/main.py', compact22=root/'generated/frozen_compact22.py',
                  incumbent36=root/'peer/incumbent_20260907.py', starter='official_starter')
    records = []
    # Both positions per opponent, on the already-evaluated first validation seed.
    # This is instrumentation equivalence, not an additional independent holdout.
    seed = study.VALIDATION_SEEDS[0]
    for name, source in rivals.items():
        for seat in (0, 1):
            instrumented = ObservedEngine(engine)
            pair = [str(candidate),str(source)] if seat==0 else [str(source),str(candidate)]
            row = ev.play(instrumented,pair,root/'engine',root/'peer/evaluate.py',seed,seat)
            original = next(r for r in validation['games'] if r['opponent']==name and r['seed']==seed and r['candidate_seat']==seat)
            matches = (row['status']==original['status']=='complete' and row['scores']==original['scores']
                       and row['trace_sha256']==original['trace_sha256'])
            row.update(opponent=name,instrumentation_matches_original=matches,economics=instrumented.report())
            records.append(row)
    report = dict(candidate_sha256=selection['candidate_sha256'], validation_contract=study.digest(study.canonical(validation['contract'])),
                  games=records, all_traces_match=all(r['instrumentation_matches_original'] for r in records))
    study.write_json(root/'diagnostics.json',report)
    if not report['all_traces_match']: raise RuntimeError('Instrumentation changed a game outcome/trace')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    export(parser.parse_args().root)
