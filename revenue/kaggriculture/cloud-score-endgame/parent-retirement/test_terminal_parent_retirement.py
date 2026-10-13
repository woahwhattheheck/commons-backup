# SPDX-License-Identifier: Apache-2.0
"""Exercise terminal parent continuity through the real score/selector pipeline.

Uses local, pinned dependency files and retained constructed PORT cases. No
network requests, policy games, source mutations, or opponent-state inference.
The feasibility check below is intentionally limited to these SELL-only cases.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import lzma
from pathlib import Path
import sys
import unittest

PINS = {
    'terminal_utility.py': '6734e0b37c9a6a78fb9cff8cd5bbd94d260054ab',
    'full_support.py': ('b04f7bc4ff2137dee4b70ec6f10e7f02ccaebd06',
                        '7f7e2e9d62a655e24219490e9c54ab23019f1520'),
    'weighted_selector.py': '2c21f8975a64961aec0b94fc6ea930318fec111b',
    'selector.py': '546b71188fd44dc47cac99623d1967bc81413da7',
    'solver.py': '3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3',
    'engine-cases.json.xz': 'e4860101cf420cc8a9f75d1d273d98e0159e7599',
}
ENGINE_PINS = {
    'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}
COUNTS = Counter()
RECEIPTS = []

def identity(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'git_blob': hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load local source: '+str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class ExactDraw:
    def __init__(self, index=0):
        self.index = index
        self.calls = 0
    def randrange(self, n):
        self.calls += 1
        if not 0 <= self.index < n:
            raise AssertionError('Fixture draw outside the exact support')
        return self.index

def choose_instance(index=0, tie_break='baseline'):
    return SCORE.make_score_selector(
        T15.WholePlanSelector, PRISM.make_selector, PORT.build_table,
        POLY.solve_full_table, POLY.verify_certificate,
        rng=ExactDraw(index), tie_break=tie_break)

def world(label='varying_baseline', player=0, scenario=None):
    case = next(c for c in CASES['cases'] if c['name'] == label and c['player_index'] == player)
    doc = deepcopy(case['document'])
    source = doc['source']
    scenario = scenario or doc['scenario_ids'][0]
    cfg = EV.Struct({k: v.get('default') if isinstance(v, dict) else v
                     for k, v in ENGINE.specification['configuration'].items()})
    cfg.seed = 0  # Constructed-state initialization, not a scored-game seed.
    env = EV.Struct(configuration=cfg, done=False, info={})
    state = [EV.Struct(observation=EV.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    ENGINE.interpreter(state, env)
    COUNTS['initializations'] += 1
    step = source['step']
    for actor in state:
        actor.observation.update(step=step, day=step//cfg.turnsPerDay, hour=step%cfg.turnsPerDay)
        actor.observation.private['shed'] = deepcopy(source['own_shed'])
    state[1-player].observation.private['shed'] = deepcopy(source['scenarios'][scenario]['shed'])
    farms = state[0].observation.farms
    farms[player]['money'] = source['initial_common_cash'] + source['initial_cash_lead']
    farms[1-player]['money'] = source['initial_common_cash']
    base = deepcopy(next(r['own_action'] for r in doc['receipts'] if r['plan'] == doc['baseline']))
    return {'document': doc, 'observation': deepcopy(state[player].observation),
            'configuration': cfg, 'base': base, 'state': state, 'env': env,
            'player': player, 'scenario': scenario, 'label': label}

def own_feasible(w, action):
    """Exact unit application + stock conservation for this fixture's SELLs.

    No actual rival action, stock or outcome enters this callback. It is NOT a
    general funding or horizon validator and is not delivered as production.
    """
    obs, cfg, player = w['observation'], w['configuration'], w['player']
    farm = deepcopy(obs['farms'][player]); private = deepcopy(obs['private'])
    if not isinstance(action, dict) or len(action.get('hands', [])) > len(farm['hands']):
        return False
    units = [action.get('farmer', ['PASS'])] + action.get('hands', [])
    for idx, command in enumerate(units):
        if command not in (['PASS'], ['DROP']):
            return False
        ENGINE._apply_unit_action(farm, private, idx, command, cfg.boardSize,
                                  obs['day'], cfg.turnsPerDay, cfg.shedCapacity)
    queue = action.get('market', [])
    if not isinstance(queue, list) or len(queue) > cfg.maxMarketOrdersPerTurn:
        return False
    stock = dict(private['shed'])
    for order in queue:
        if not order:
            continue
        if (not isinstance(order, list) or len(order) != 3 or order[0] != 'SELL'
                or type(order[2]) is not int or order[2] < 0):
            return False
        item, quantity = order[1:]
        if stock.get(item, 0) < quantity:
            return False
        stock[item] = stock.get(item, 0) - quantity
    return True

def call(selected, w, base=None, document=None, feasible=None):
    obs, cfg = deepcopy(w['observation']), deepcopy(w['configuration'])
    action = deepcopy(w['base'] if base is None else base)
    doc = deepcopy(w['document'] if document is None else document)
    before = deepcopy((obs, cfg, action, doc))
    answer = selected.transform_terminal(obs, cfg, action, document=doc,
                                        feasible=feasible or (lambda a: own_feasible(w, a)))
    if (obs, cfg, action, doc) != before:
        raise AssertionError('The terminal selector changed caller input')
    COUNTS['selector_calls'] += 1
    return answer

def execute(w, action, note):
    player, scenario = w['player'], w['scenario']
    source = w['document']['source']
    rival = {'farmer': ['PASS'], 'hands': [], 'market': deepcopy(source['scenarios'][scenario]['market'])}
    state, env = deepcopy((w['state'], w['env']))
    state[player].action = deepcopy(action); state[1-player].action = rival
    before = [state[0].observation.farms[i]['money'] for i in (player, 1-player)]
    ENGINE.interpreter(state, env)
    COUNTS['official_action_transitions'] += 1
    cash = [state[0].observation.farms[i]['money'] for i in (player, 1-player)]
    rewards = [state[i].reward for i in (player, 1-player)]
    RECEIPTS.append({'test': note, 'case': w['label'], 'player': player, 'scenario': scenario,
                     'observation': deepcopy(w['observation']), 'configuration': dict(w['configuration']),
                     'selected_action': deepcopy(action), 'evaluation_only_rival_action': rival,
                     'cash_before': before, 'cash_after': cash, 'rewards': rewards,
                     'status': [s.status for s in state]})
    return cash, rewards

class ParentRetirement(unittest.TestCase):
    def assert_retired(self, edit):
        for player in (0, 1):
            with self.subTest(player=player):
                w = world(player=player); s = choose_instance()
                first = call(s, w)
                self.assertNotEqual(first, w['base'])
                changed = deepcopy(w['base']); edit(changed)
                self.assertEqual(call(s, w, changed), changed)
                self.assertIsNone(s.active, 'Changed parent returned early without retiring the original draw')
                self.assertIsNone(s.last_objective)
                self.assertIn(('terminal-score', player, 718), s.completed)
                self.assertEqual(call(s, w), w['base'])
                self.assertEqual((s.draws, s.provider_calls), (1, 1))

    def test_changed_farmer_retires(self):
        self.assert_retired(lambda a: a.update(farmer=['DROP']))

    def test_changed_hands_retires(self):
        self.assert_retired(lambda a: a.update(hands=[['PASS']]))

    def test_added_purchase_retires(self):
        self.assert_retired(lambda a: a['market'].append(['HIRE', 1]))

    def test_changed_sale_quantity_retires(self):
        self.assert_retired(lambda a: a['market'][1].__setitem__(2, 1))

    def test_reordered_sale_queue_retires(self):
        self.assert_retired(lambda a: a['market'].reverse())

    def test_changed_metadata_retires(self):
        self.assert_retired(lambda a: a.update(diagnostic='new parent'))

    def test_changed_noop_layout_retires(self):
        self.assert_retired(lambda a: a['market'].pop(0))

    def test_restored_input_does_not_revive_old_choice(self):
        w = world(); s = choose_instance(); first = call(s, w)
        changed = deepcopy(w['base']); changed['farmer'] = ['DROP']
        call(s, w, changed)
        later = call(s, w)
        self.assertNotEqual(later, first, 'Old complete choice was revived after an unsupported retry')
        self.assertEqual(later, w['base'])
        self.assertEqual((s.draws, s.provider_calls), (1, 1))

    def test_identical_retries_keep_one_choice(self):
        w = world(); s = choose_instance(); first = call(s, w)
        for _ in range(5): self.assertEqual(call(s, w), first)
        self.assertEqual((s.draws, s.provider_calls), (1, 1))

    def test_mapping_key_order_does_not_change_parent(self):
        w = world(); s = choose_instance(); first = call(s, w)
        reordered = dict(reversed(list(w['base'].items())))
        self.assertEqual(call(s, w, reordered), first)
        self.assertIsNotNone(s.active)
        self.assertEqual(s.draws, 1)

    def test_first_uncommitted_mismatch_does_not_poison_retry(self):
        w = world(); s = choose_instance(); changed = deepcopy(w['base']); changed['farmer'] = ['DROP']
        self.assertEqual(call(s, w, changed), changed)
        self.assertEqual((s.draws, s.provider_calls), (0, 0))
        self.assertEqual(s.completed, set())
        self.assertNotEqual(call(s, w), w['base'])
        self.assertEqual((s.draws, s.provider_calls), (1, 1))

    def test_caller_mutation_cannot_change_stored_parent(self):
        w = world(); s = choose_instance(); parent = deepcopy(w['base'])
        first = s.transform_terminal(w['observation'], w['configuration'], parent,
                                     document=w['document'], feasible=lambda a: own_feasible(w,a))
        COUNTS['selector_calls'] += 1
        parent['farmer'] = ['DROP']
        self.assertEqual(call(s, w), first)  # stored parent was detached
        self.assertEqual(call(s, w, parent), parent)
        self.assertIsNone(s.active)
        self.assertEqual(call(s, w), w['base'])

    def test_source_label_only_does_not_retire(self):
        w = world(); s = choose_instance(); first = call(s, w)
        doc = deepcopy(w['document']); doc['source']['diagnostic'] = 'new label, same facts'
        self.assertEqual(call(s, w, document=doc), first)
        self.assertEqual((s.draws, s.provider_calls), (1, 1))

    def test_changed_observation_still_retires(self):
        w = world(); s = choose_instance(); call(s, w)
        changed = deepcopy(w); changed['observation']['farms'][0]['money'] += 1
        self.assertEqual(call(s, changed), changed['base'])
        self.assertIsNone(s.active)
        self.assertEqual(call(s, w), w['base'])

    def test_cancellation_is_not_swallowed(self):
        class Stop(BaseException): pass
        err = Stop('controlled boundary cancellation')
        def interrupted(_): raise err
        w = world(); s = choose_instance()
        with self.assertRaises(Stop) as got: call(s, w, feasible=interrupted)
        self.assertIs(got.exception, err)
        self.assertEqual((s.draws, s.provider_calls), (0, 0))

    def test_nonterminal_call_keeps_existing_other_key(self):
        w = world(); s = choose_instance(); first = call(s, w)
        other = world('not_terminal'); self.assertEqual(call(s, other), other['base'])
        self.assertEqual(call(s, w), first)
        self.assertEqual((s.draws, s.provider_calls), (1, 1))

    def test_recorded_absolute_decisions_remain_unchanged(self):
        for player in (0, 1):
            for label, expected in [('varying_baseline','selected'),('protect_all_wins','baseline_optimal'),
                                    ('omitted_rival_supply','baseline_optimal')]:
                with self.subTest(player=player,label=label):
                    w=world(label,player);s=choose_instance();out=call(s,w)
                    result=SCORE.solve_absolute(w['document'],PORT.build_table,POLY.solve_full_table,POLY.verify_certificate)
                    self.assertEqual(result['status'],expected)
                    self.assertEqual(out==w['base'],expected=='baseline_optimal')

class NativeExecution(unittest.TestCase):
    def test_initial_selected_queue_rewards_match_retained_cases(self):
        for player in (0,1):
            for scenario in ('wheat17','milk2_wheat3'):
                with self.subTest(player=player,scenario=scenario):
                    w=world('varying_baseline',player,scenario);s=choose_instance();action=call(s,w)
                    target=next(r for r in w['document']['receipts'] if r['plan']=='wheat_first' and r['scenario']==scenario)
                    cash,rewards=execute(w,action,self.id())
                    self.assertEqual(cash,[target['own_cash'],target['rival_cash']]);self.assertEqual(cash,rewards)

    def test_retired_retry_executes_the_supplied_baseline(self):
        for player in (0,1):
            for scenario in ('wheat17','milk2_wheat3'):
                with self.subTest(player=player,scenario=scenario):
                    w=world('varying_baseline',player,scenario);s=choose_instance();call(s,w)
                    changed=deepcopy(w['base']);changed['farmer']=['DROP'];call(s,w,changed)
                    action=call(s,w);cash,rewards=execute(w,action,self.id())
                    target=next(r for r in w['document']['receipts'] if r['plan']==w['document']['baseline'] and r['scenario']==scenario)
                    self.assertEqual(cash,[target['own_cash'],target['rival_cash']]);self.assertEqual(cash,rewards)
                    self.assertEqual(action,w['base']);self.assertEqual((s.draws,s.provider_calls),(1,1))

    def test_mixed_support_actions_execute_without_redraw(self):
        for player in (0,1):
            for draw,plan_id in ((0,'wheat_first'),(1,'milk_first')):
                with self.subTest(player=player,draw=draw):
                    w=world('recover_from_losses',player,'milk2_wheat3');s=choose_instance(draw)
                    action=call(s,w);self.assertEqual(call(s,w),action)
                    cash,rewards=execute(w,action,self.id())
                    target=next(r for r in w['document']['receipts'] if r['plan']==plan_id and r['scenario']=='milk2_wheat3')
                    self.assertEqual(cash,[target['own_cash'],target['rival_cash']]);self.assertEqual(cash,rewards)
                    self.assertEqual((s.draws,s.provider_calls),(1,1))

def main():
    global SCORE, PORT, POLY, PRISM, T15, EV, ENGINE, CASES
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--dependencies',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();dep=a.dependencies.resolve()
    for name,pin in PINS.items():
        actual=identity(dep/name)['git_blob']
        if actual not in (pin if isinstance(pin,tuple) else (pin,)):
            raise ValueError('Dependency source differs: '+name)
    for name,pin in ENGINE_PINS.items():
        if identity(dep/'engine'/name)['sha256']!=pin:raise ValueError('Engine source differs: '+name)
    if identity(dep/'peer/evaluate.py')['sha256']!='cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e':
        raise ValueError('Evaluator source differs')
    sys.path.insert(0,str(dep))
    SCORE=load(a.source.resolve(),'port_under_test')
    PORT=load(dep/'terminal_utility.py','port_receipts')
    POLY=load(dep/'full_support.py','poly_solver')
    PRISM=load(dep/'weighted_selector.py','prism_weights')
    T15=load(dep/'selector.py','t15_selector')
    EV=load(dep/'peer/evaluate.py','port_engine_loader');ENGINE,hashes=EV.get_engine(dep/'engine')
    CASES=json.loads(lzma.decompress((dep/'engine-cases.json.xz').read_bytes()))
    log=io.StringIO();suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (ParentRetirement,NativeExecution)])
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    report={'schema':'port.terminal-parent-retirement.v1','source':identity(a.source),
            'dependency_git_blobs':{name:identity(dep/name)['git_blob'] for name in PINS},'engine_sha256':hashes,
            'tests':{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'successful':result.wasSuccessful()},
            'counts':dict(COUNTS),'new_full_games':0,'log':log.getvalue(),'native_receipts':RECEIPTS}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    a.report.with_suffix('.log').write_text(log.getvalue());print(log.getvalue())
    print(json.dumps({k:v for k,v in report.items() if k not in ('native_receipts','log','dependency_git_blobs','engine_sha256')}))
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
