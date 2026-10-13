# SPDX-License-Identifier: Apache-2.0
"""Execute the real final-action boundary with a deterministic choice fixture.

This isolates terminal action/receipt binding; it does not run PORT's receipt
builder, an optimizer, a production controller or the game engine. Supply the
actual LARCH source via --runtime. Existing PORT joined-engine work is separate.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

METHOD = None
BASE = {'farm': [['PASS']], 'hands': [['PASS']],
        'market': [['SELL', 'WHEAT', 1], ['HIRE']], 'memory': {'v': 1}}
ALT = deepcopy(BASE)
ALT['market'][0] = ['SELL', 'WHEAT', 2]
OBS = {'step': 718, 'player': 0}
CFG = {'episodeSteps': 720}


def compile_boundary(path):
    text = path.read_text(encoding='utf-8')
    tree = ast.parse(text)
    matches = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == 'transform_terminal']
    if len(matches) != 1:
        raise ValueError('Expected exactly one production transform_terminal')
    node = deepcopy(matches[0])
    ast.fix_missing_locations(node)
    env = {'deepcopy': deepcopy, 'json': json, 'hashlib': hashlib,
           # Fixtures start AFTER PORT compilation and finite-table readiness.
           'build_table': lambda doc: deepcopy(doc),
           'embedding': lambda table: () if table.get('terminal') else None}
    support = [deepcopy(n) for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == '_terminal_context']
    exec(compile(ast.Module(body=support+[node], type_ignores=[]), str(path), 'exec'), env)
    body = path.read_bytes()
    return env['transform_terminal'], {
        'runtime_sha256': hashlib.sha256(body).hexdigest(),
        'boundary_ast_sha256': hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest(),
        'scope': 'real production method with deterministic choice and compiled-receipt fixtures; no solver/controller/engine execution'}


def document(base=BASE, alternative=ALT, *, alt_id='alternative', player=0):
    return {'terminal': True, 'plan_ids': ['baseline', alt_id],
            'scenario_ids': ['fixture-0', 'fixture-1'],
            'receipts': [[{'step': 718, 'own_action': deepcopy(action)} for _ in range(2)]
                         for action in (base, alternative)]}


class ChoiceFixture:
    """Match the selector's one-commitment branch; never re-solve an active key."""
    def __init__(self):
        self.active = None
        self.completed = set()
        self.draws = 0
        self.last_decision = {}
    def choose(self, key, plans, deltas, *, feasible):
        if self.active is not None:
            if self.active['key'] != key:
                raise ValueError('Finish the committed window before another lot')
            return deepcopy(self.active)
        if key in self.completed:
            return None
        if not all(feasible(p) is True for p in plans):
            return None
        self.draws += 1
        self.active = {'key': key, 'plan': deepcopy(plans[1]), 'plan_index': 1}
        return deepcopy(self.active)
    def _fallback(self, key, reason):
        self.completed.add(key)
        self.last_decision = {'key': key, 'reason': reason}
        return None
    def transform(self, base=BASE, doc=None, verdict=True, observation=OBS):
        return METHOD(self, deepcopy(observation), CFG, deepcopy(base),
                      document=document() if doc is None else doc,
                      feasible=lambda action: verdict)


class RetryTests(unittest.TestCase):
    def begin(self):
        s = ChoiceFixture()
        self.assertEqual(s.transform(), ALT)
        self.assertEqual(s.draws, 1)
        return s

    def test_first_selection_unchanged(self):
        s = self.begin()
        self.assertEqual(s.active['plan']['id'], 'alternative')

    def test_identical_retry_keeps_one_draw(self):
        s = self.begin()
        self.assertEqual(s.transform(), ALT)
        self.assertEqual(s.draws, 1)

    def test_changed_farmer_does_not_return_old_farmer(self):
        s = self.begin()
        base, alternative = deepcopy(BASE), deepcopy(ALT)
        base['farm'] = alternative['farm'] = [['DROP']]
        self.assertEqual(s.transform(base, document(base, alternative)), base)
        self.assertIsNone(s.active)
        self.assertEqual(s.draws, 1)

    def test_changed_hand_does_not_return_old_hand(self):
        s = self.begin()
        base, alternative = deepcopy(BASE), deepcopy(ALT)
        base['hands'] = alternative['hands'] = [['PLACE', 'WOOL', 1]]
        self.assertEqual(s.transform(base, document(base, alternative)), base)

    def test_changed_purchase_does_not_return_old_purchase(self):
        s = self.begin()
        base, alternative = deepcopy(BASE), deepcopy(ALT)
        base['market'][1] = alternative['market'][1] = ['BUY_SEED', 'WHEAT', 1]
        self.assertEqual(s.transform(base, document(base, alternative)), base)

    def test_changed_parent_metadata_is_preserved(self):
        s = self.begin()
        base, alternative = deepcopy(BASE), deepcopy(ALT)
        base['memory'] = alternative['memory'] = {'v': 2}
        self.assertEqual(s.transform(base, document(base, alternative)), base)

    def test_reused_id_cannot_supply_stale_action(self):
        s = self.begin()
        alternative = deepcopy(ALT)
        alternative['market'][0][2] = 3
        self.assertEqual(s.transform(BASE, document(BASE, alternative)), BASE)

    def test_removed_plan_does_not_return_unlisted_action(self):
        s = self.begin()
        self.assertEqual(s.transform(BASE, document(alt_id='replacement')), BASE)

    def test_invalidated_key_does_not_redraw_when_old_document_returns(self):
        s = self.begin()
        base, alternative = deepcopy(BASE), deepcopy(ALT)
        base['farm'] = alternative['farm'] = [['DROP']]
        s.transform(base, document(base, alternative))
        self.assertEqual(s.transform(), BASE)
        self.assertEqual(s.draws, 1)

    def test_current_feasibility_failure_still_preserves_fallback(self):
        s = self.begin()
        self.assertEqual(s.transform(verdict=None), BASE)
        self.assertIsNone(s.active)
        self.assertEqual(s.draws, 1)

    def test_other_position_same_behavior(self):
        s = ChoiceFixture()
        ob = {'step': 718, 'player': 1}
        self.assertEqual(s.transform(observation=ob), ALT)
        base, alternative = deepcopy(BASE), deepcopy(ALT)
        base['market'][1] = alternative['market'][1] = []
        self.assertEqual(s.transform(base, document(base, alternative), observation=ob), base)

    def test_return_and_inputs_are_detached(self):
        s = self.begin()
        doc = document()
        original = deepcopy(doc)
        out = s.transform(BASE, doc)
        out['market'][0][2] = 200
        self.assertEqual(doc, original)
        self.assertEqual(s.active['plan']['action'], ALT)

    def test_nonterminal_does_not_draw(self):
        s = ChoiceFixture()
        self.assertEqual(s.transform(observation={'step': 717, 'player': 0}), BASE)
        self.assertEqual(s.draws, 0)


def main():
    global METHOD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    METHOD, evidence = compile_boundary(args.runtime)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RetryTests))
    evidence.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                    passed=result.wasSuccessful(), solver_calls=0, engine_calls=0, full_games=0,
                    failing_tests=[case.id() for case, _ in result.failures])
    if args.report:
        args.report.write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    return not result.wasSuccessful()

if __name__ == '__main__':
    raise SystemExit(main())
