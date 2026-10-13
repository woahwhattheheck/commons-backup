# SPDX-License-Identifier: Apache-2.0
"""Run the real absolute-score selector through pinned terminal engine actions.

Consumes existing PORT receipts and LARCH/POLY/PRISM/T15 sources. It does not
implement a policy, solve a new game, fetch source, or replay a full match.
The local feasibility callback is deliberately limited to these fixture queues.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import lzma
from pathlib import Path
import sys
import time
import unittest

BASE = Path(__file__).resolve().parent
ENGINE_HASHES = {
    'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}
DEPENDENCIES = {
    'terminal_utility.py': ('cloud-terminal-utility', '6734e0b37c9a6a78fb9cff8cd5bbd94d260054ab'),
    'score_endgame.py': ('cloud-score-endgame', '543ab5b4536a2b9605ee4c7c69aabfb637811760'),
    'full_support.py': ('cloud-full-support', 'b04f7bc4ff2137dee4b70ec6f10e7f02ccaebd06'),
    'weighted_selector.py': ('cloud-weighted-plan-selector', '2c21f8975a64961aec0b94fc6ea930318fec111b'),
    'selector.py': ('cloud-market-game-theory', '546b71188fd44dc47cac99623d1967bc81413da7'),
    'solver.py': ('cloud-market-game-theory', '3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3'),
}
ORIGINAL_SCORE_BLOB = 'd03fc481ea8a90044398fa7ed22b2f7753fca09d'
ARCHIVE_HASH = '936b72e34299abad42414265ef7f8e8d61367480b8b86f0e014c3d522f0e848a'
ARCHIVE_JSON_HASH = 'b37f7e29667119d7eb6054f0b6f41268c9668f8a0116ff43fb9edb83345453e0'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': sha256(raw),
            'git_blob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load supplied local source: ' + path.name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ExactDraw:
    """Enumerate each supported draw, not a statistical random experiment."""
    def __init__(self, value=0):
        self.value = value
        self.calls = []

    def randrange(self, denominator):
        if not 0 <= self.value < denominator:
            raise ValueError('Requested fixture draw is outside the exact range')
        self.calls.append({'denominator': denominator, 'draw': self.value})
        return self.value


class SaleFixtureFeasibility:
    """Current-own-state support for the retained sale-only terminal fixtures.

    Exact engine primitives apply PASS/DROP/PLACE/PICKUP in worker order. Other
    worker actions and any non-SELL market order return unknown. This is a test
    callback, not a replacement for the existing general projection/queue APIs.
    Full requested quantities, repeated products, order limits, and optional
    standing stock minima are checked; no rival-private input is available.
    """
    def __init__(self, engine, observation, configuration, reserved=None):
        self.engine = engine
        self.observation = deepcopy(observation)
        self.configuration = deepcopy(configuration)
        self.reserved = dict(reserved or {})
        self.calls = []

    def __call__(self, action):
        verdict = self.check(action)
        self.calls.append({'action_sha256': digest(action), 'verdict': verdict})
        return verdict

    def check(self, action):
        m, cfg, obs = self.engine, self.configuration, self.observation
        if not isinstance(action, dict):
            return None
        hands = action.get('hands', [])
        queue = action.get('market', [])
        if not isinstance(hands, list) or not isinstance(queue, list):
            return None
        if len(queue) > max(1, int(cfg.get('maxMarketOrdersPerTurn', 10))):
            return False
        farm, private = deepcopy(obs['farms'][obs['player']]), deepcopy(obs['private'])
        commands = [action.get('farmer', ['PASS']), *hands]
        if len(hands) > len(farm['hands']):
            return False
        for index, command in enumerate(commands):
            if not isinstance(command, list) or not command or command[0] not in {'PASS', 'DROP', 'PLACE', 'PICKUP'}:
                return None
            m._apply_unit_action(farm, private, index, command,
                                 int(cfg['boardSize']), int(obs['step']) // int(cfg['turnsPerDay']),
                                 int(cfg['turnsPerDay']), int(cfg['shedCapacity']))
        stock = deepcopy(private['shed'])
        for order in queue:
            if not order:
                continue
            parsed = m._parse_order(order)
            if parsed is None or parsed['type'] != 'SELL' or parsed['item'] not in m.PRODUCTS:
                return None
            product, count = parsed['item'], parsed['remaining']
            if count > stock.get(product, 0) - self.reserved.get(product, 0):
                return False
            stock[product] -= count
        return True


class Context:
    def __init__(self, args):
        self.sources = {}
        paths = {}
        for filename, (directory, expected) in DEPENDENCIES.items():
            path = args.source_dir / filename if args.source_dir else BASE.parent / directory / filename
            if filename == 'score_endgame.py' and args.score_file:
                path, expected = args.score_file, ORIGINAL_SCORE_BLOB
            record = identity(path)
            if record['git_blob'] != expected:
                raise ValueError('Dependency bytes differ from recorded input: ' + filename)
            paths[filename] = path
            self.sources[filename] = record
        for filename, expected in ENGINE_HASHES.items():
            if sha256((args.engine_dir / filename).read_bytes()) != expected:
                raise ValueError('Engine bytes differ: ' + filename)
        self.sources['evaluator'] = identity(args.engine_loader)
        if self.sources['evaluator']['sha256'] != 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e':
            raise ValueError('Expected the already-published engine loader')
        raw = args.receipts.read_bytes()
        if sha256(raw) != ARCHIVE_HASH:
            raise ValueError('Retained receipt archive differs')
        decoded = lzma.decompress(raw)
        if sha256(decoded) != ARCHIVE_JSON_HASH:
            raise ValueError('Retained receipt JSON differs')
        self.saved = json.loads(decoded)
        # The original selector imports its sibling solver by its existing name.
        load(paths['solver.py'], 'solver')
        self.terminal = load(paths['terminal_utility.py'], 'port_execution_terminal')
        self.score = load(paths['score_endgame.py'], 'port_execution_score')
        self.poly = load(paths['full_support.py'], 'port_execution_poly')
        self.weighted = load(paths['weighted_selector.py'], 'port_execution_weighted')
        self.selector = load(paths['selector.py'], 'port_execution_selector')
        self.ev = load(args.engine_loader, 'port_execution_evaluator')
        self.engine, self.engine_hashes = self.ev.get_engine(args.engine_dir)
        self.transitions = []
        self.decisions = []
        self.initializations = 0
        self.retry_documents = []

    def case(self, name, player):
        return next(c for c in self.saved['cases'] if c['name'] == name and c['player_index'] == player)

    def setup(self, case, scenario_id, carried=None):
        src = case['document']['source']
        cfg = self.ev.Struct({k: v.get('default') if isinstance(v, dict) else v
                              for k, v in self.engine.specification['configuration'].items()})
        cfg.seed = 0  # A constructed initialization, not a full game or held seed.
        env = self.ev.Struct(configuration=cfg, done=False, info={})
        state = [self.ev.Struct(observation=self.ev.Struct(), action={}, status='ACTIVE', reward=0)
                 for _ in range(2)]
        self.engine.interpreter(state, env)
        self.initializations += 1
        player, step = case['player_index'], src['step']
        for s in state:
            s.observation.step = step
            s.observation.day = step // cfg.turnsPerDay
            s.observation.hour = step % cfg.turnsPerDay
            s.observation.private['shed'] = deepcopy(src['own_shed'])
        rival = src['scenarios'][scenario_id]
        state[1-player].observation.private['shed'] = deepcopy(rival['shed'])
        farms = state[0].observation.farms
        farms[player]['money'] = src['initial_common_cash'] + src['initial_cash_lead']
        farms[1-player]['money'] = src['initial_common_cash']
        if carried is not None:
            state[player].observation.private['inventories'][0] = deepcopy(carried)
        state[1-player].action = {'farmer': ['PASS'], 'hands': [], 'market': deepcopy(rival['market'])}
        if carried is None:
            assert digest(state[player].observation) == case['document']['receipts'][0]['public_state_sha256']
        return state, env, cfg

    def policy(self, draw=0, max_pivots=128):
        rng = ExactDraw(draw)
        policy = self.score.make_score_selector(
            self.selector.WholePlanSelector, self.weighted.make_selector,
            self.terminal.build_table, self.poly.solve_full_table,
            self.poly.verify_certificate, rng=rng, max_pivots=max_pivots)
        return policy, rng

    def execute(self, state, env, player, action, case, scenario, purpose):
        before = deepcopy(state[player].observation)
        state[player].action = deepcopy(action)
        actions = deepcopy([s.action for s in state])
        self.engine.interpreter(state, env)
        cash = [state[0].observation.farms[p]['money'] for p in (player, 1-player)]
        statuses = [s.status for s in state]
        done = statuses == ['DONE', 'DONE']
        rewards = [state[p].reward for p in (player, 1-player)] if done else None
        if done:
            assert rewards == cash
        row = {'case': case, 'scenario': scenario, 'player_index': player, 'purpose': purpose,
               'step': before['step'], 'public_state_sha256': digest(before),
               'cash_before': [before['farms'][p]['money'] for p in (player, 1-player)],
               'own_action': actions[player], 'rival_action': actions[1-player],
               'cash_after': cash, 'statuses': statuses, 'rewards': rewards,
               'own_private_before': before['private'],
               'own_private_after': deepcopy(state[player].observation.private)}
        self.transitions.append(row)
        return row

    def choose(self, policy, observation, cfg, base, document, feasibility):
        initial = deepcopy((observation, cfg, base, document))
        start = time.perf_counter()
        result = policy.transform_terminal(observation, cfg, base, document=document, feasible=feasibility)
        elapsed = time.perf_counter() - start
        assert (observation, cfg, base, document) == initial
        record = {'observation_sha256': digest(observation), 'document_sha256': digest(document),
                  'base_action': deepcopy(base), 'returned_action': deepcopy(result),
                  'draws': policy.draws, 'provider_calls': policy.provider_calls,
                  'last_decision': deepcopy(policy.last_decision),
                  'absolute_result': deepcopy(policy.last_objective), 'elapsed_seconds': elapsed}
        self.decisions.append(record)
        return result

    def retry_document(self, case, carried):
        """Build genuine terminal receipts for a changed current parent action.

        The same queue alternatives gain farmer DROP and a final EGG sale.
        These new table-construction transitions are counted separately.
        """
        document = deepcopy(case['document'])
        document['receipts'] = []
        for plan_id in document['plan_ids']:
            queue = deepcopy(document['source']['plans'][plan_id])
            while len(queue) < 3:
                queue.append([])
            queue.append(['SELL', 'EGG', 1])
            action = {'farmer': ['DROP'], 'hands': [], 'market': queue}
            for scenario_id in document['scenario_ids']:
                state, env, _ = self.setup(case, scenario_id, carried=carried)
                outcome = self.execute(state, env, case['player_index'], action,
                                       'changed_parent_receipts', scenario_id, 'new_retry_table_input')
                old = next(r for r in case['document']['receipts']
                           if r['plan'] == plan_id and r['scenario'] == scenario_id)
                document['receipts'].append({
                    'plan': plan_id, 'scenario': scenario_id, 'own_cash': outcome['cash_after'][0],
                    'rival_cash': outcome['cash_after'][1], 'done': True,
                    'plan_sha256': digest(action), 'scenario_sha256': old['scenario_sha256'],
                    'public_state_sha256': outcome['public_state_sha256'], 'own_action': action,
                    'step': outcome['step'], 'official_rewards': outcome['rewards']})
        document['source']['kind'] = 'new_changed_parent_terminal_receipts'
        document['source']['added_carried_stock'] = carried
        document['source']['plans'] = {p: next(r['own_action']['market'] for r in document['receipts'] if r['plan'] == p)
                                       for p in document['plan_ids']}
        self.retry_documents.append(deepcopy(document))
        return document


CTX = None


class JoinedExecution(unittest.TestCase):
    def cases(self, name, draw=0, expected=None, max_pivots=128, retry=False):
        ctx = CTX
        for player in (0, 1):
            case = ctx.case(name, player)
            document = case['document']
            for scenario in document['scenario_ids']:
                with self.subTest(player=player, scenario=scenario, draw=draw):
                    state, env, cfg = ctx.setup(case, scenario)
                    obs = deepcopy(state[player].observation)
                    base = deepcopy(document['receipts'][0]['own_action'])
                    policy, rng = ctx.policy(draw, max_pivots)
                    callback = SaleFixtureFeasibility(ctx.engine, obs, cfg)
                    out = ctx.choose(policy, obs, cfg, base, document, callback)
                    if retry:
                        again = ctx.choose(policy, obs, cfg, base, document, callback)
                        self.assertEqual(out, again)
                        self.assertEqual(policy.draws, 1)
                        self.assertEqual(policy.provider_calls, 1)
                    plan = expected or document['baseline']
                    reference = next(r for r in document['receipts'] if r['plan'] == plan and r['scenario'] == scenario)
                    self.assertEqual(out, reference['own_action'])
                    actual = ctx.execute(state, env, player, out, name, scenario, 'selected_queue_execution')
                    self.assertEqual(actual['cash_after'], [reference['own_cash'], reference['rival_cash']])
                    self.assertEqual(actual['statuses'], reference['statuses'])
                    self.assertEqual(actual['own_private_after']['shed'], reference['remaining_shed'][0])
                    self.assertEqual(policy.draws, int(expected is not None))
                    if name == 'not_terminal':
                        self.assertEqual(policy.provider_calls, 0)
                        self.assertIsNone(actual['rewards'])
                    if expected is not None:
                        self.assertEqual(policy.active['plan']['id'], expected)
                        self.assertNotIn('__score_embedding_zero__', policy.active['plan']['id'])
                        self.assertEqual(len(policy.active['weights']), 3)
                        self.assertEqual(len(rng.calls), 1)

    def test_absolute_wins_for_varying_baseline(self):
        self.cases('varying_baseline', expected='wheat_first')

    def test_recovery_first_support_executes(self):
        self.cases('recover_from_losses', draw=0, expected='wheat_first')

    def test_recovery_second_support_executes(self):
        self.cases('recover_from_losses', draw=1, expected='milk_first')

    def test_protected_lead_keeps_complete_baseline(self):
        self.cases('protect_all_wins')

    def test_extra_rival_world_keeps_baseline(self):
        self.cases('omitted_rival_supply')

    def test_nonterminal_never_solves(self):
        self.cases('not_terminal')

    def test_identical_retry_keeps_one_draw_and_same_queue(self):
        self.cases('varying_baseline', expected='wheat_first', retry=True)

    def test_pivot_budget_keeps_executable_baseline(self):
        self.cases('varying_baseline', max_pivots=0)

    def test_changed_parent_retry_executes_current_drop_and_sale(self):
        ctx = CTX
        for player in (0, 1):
            with self.subTest(player=player):
                case = ctx.case('varying_baseline', player)
                old_document = deepcopy(case['document'])
                carried = {'EGG': 1}
                document = ctx.retry_document(case, carried)
                scenario = document['scenario_ids'][0]
                state, env, cfg = ctx.setup(case, scenario, carried=carried)
                obs = deepcopy(state[player].observation)
                # EGG remains carried under the old PASS action, hence the saved
                # old WHEAT/MILK receipts are unchanged. Bind the current observation.
                for receipt in old_document['receipts']:
                    receipt['public_state_sha256'] = digest(obs)
                policy, _ = ctx.policy()
                checker = SaleFixtureFeasibility(ctx.engine, obs, cfg)
                old_base = old_document['receipts'][0]['own_action']
                first = ctx.choose(policy, obs, cfg, old_base, old_document, checker)
                self.assertEqual(first['farmer'], ['PASS'])
                current_base = document['receipts'][0]['own_action']
                second = ctx.choose(policy, obs, cfg, current_base, document, checker)
                actual = ctx.execute(state, env, player, second, 'changed_parent_retry', scenario,
                                     'selected_queue_execution')
                reference = next(r for r in document['receipts'] if r['plan'] == document['baseline']
                                 and r['scenario'] == scenario)
                # Execute before assertions so a negative control retains its actual result.
                self.assertEqual(second, current_base)
                self.assertEqual(actual['cash_after'], [reference['own_cash'], reference['rival_cash']])
                self.assertEqual(actual['own_private_after']['inventories'][0].get('EGG', 0), 0)
                self.assertEqual(actual['own_private_after']['shed'].get('EGG', 0), 0)
                self.assertEqual(policy.last_decision['reason'], 'terminal_commitment_changed')
                self.assertEqual(policy.draws, 1)
                self.assertEqual(policy.provider_calls, 1)
                self.assertIsNone(policy.active)
                third = ctx.choose(policy, obs, cfg, current_base, document, checker)
                self.assertEqual(third, current_base)
                self.assertEqual(policy.draws, 1)

    def test_current_reservation_and_order_limit_precede_solver(self):
        ctx = CTX
        case = ctx.case('varying_baseline', 0)
        state, _, cfg = ctx.setup(case, 'wheat17')
        obs, document = deepcopy(state[0].observation), case['document']
        base = document['receipts'][0]['own_action']
        for reserve, limit in (({'WHEAT': 1}, cfg.maxMarketOrdersPerTurn), ({}, 1)):
            with self.subTest(reserve=reserve, limit=limit):
                config = deepcopy(cfg); config.maxMarketOrdersPerTurn = limit
                policy, _ = ctx.policy()
                out = ctx.choose(policy, obs, config, base, document,
                                 SaleFixtureFeasibility(ctx.engine, obs, config, reserve))
                self.assertEqual(out, base)
                self.assertEqual(policy.provider_calls, 0)
                self.assertEqual(policy.draws, 0)
        # A caller-supplied fallback is not made valid by this wrapper.
        # These are rejection-boundary checks; do not execute that fallback.

    def test_uncertain_current_feasibility_retires_without_redraw(self):
        ctx = CTX
        case = ctx.case('varying_baseline', 0)
        state, _, cfg = ctx.setup(case, 'wheat17')
        obs, doc = deepcopy(state[0].observation), case['document']
        base = doc['receipts'][0]['own_action']
        policy, _ = ctx.policy()
        first = ctx.choose(policy, obs, cfg, base, doc, SaleFixtureFeasibility(ctx.engine, obs, cfg))
        self.assertNotEqual(first, base)
        second = ctx.choose(policy, obs, cfg, base, doc, lambda action: None)
        self.assertEqual(second, base)
        self.assertEqual(policy.last_decision['reason'], 'terminal_continuation_unavailable')
        self.assertEqual((policy.draws, policy.provider_calls), (1, 1))
        self.assertIsNone(policy.active)

    def test_full_requested_stock_not_clipped_to_available(self):
        ctx = CTX
        case = ctx.case('varying_baseline', 0)
        state, _, cfg = ctx.setup(case, 'wheat17')
        checker = SaleFixtureFeasibility(ctx.engine, state[0].observation, cfg)
        exact = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'WHEAT', 1], ['SELL', 'WHEAT', 1]]}
        self.assertIs(checker(exact), True)
        excessive = deepcopy(exact); excessive['market'][1][2] = 2
        self.assertIs(checker(excessive), False)
        unsupported = deepcopy(exact); unsupported['market'][1] = ['BUY_PRODUCT', 'WHEAT', 1]
        self.assertIsNone(checker(unsupported))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', type=Path, help='Optional flat local cache of the named dependency files')
    p.add_argument('--engine-dir', type=Path, required=True)
    p.add_argument('--engine-loader', type=Path, required=True)
    p.add_argument('--receipts', type=Path, default=BASE / 'engine-cases.json.xz')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--score-file', type=Path, help='Optional exact original d03fc481 source for negative-control execution')
    p.add_argument('--only-retry', action='store_true', help='Execute only the real-engine changed-parent discriminator')
    a = p.parse_args(argv)
    global CTX
    try:
        CTX = Context(a)
        suite = (unittest.TestSuite([JoinedExecution('test_changed_parent_retry_executes_current_drop_and_sale')])
                 if a.only_retry else unittest.defaultTestLoader.loadTestsFromTestCase(JoinedExecution))
        log = io.StringIO()
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        report = {
            'schema': 'titan.absolute-execution.v1',
            'sources': CTX.sources, 'engine_sha256': CTX.engine_hashes,
            'input_archive_sha256': ARCHIVE_HASH, 'input_json_sha256': ARCHIVE_JSON_HASH,
            'tests': {'run': result.testsRun, 'failure_entries': len(result.failures),
                      'errors': len(result.errors), 'skipped': len(result.skipped),
                      'successful': result.wasSuccessful(), 'log': log.getvalue()},
            'execution_counts': {
                'selected_queue_transitions': sum(x['purpose'] == 'selected_queue_execution' for x in CTX.transitions),
                'new_retry_table_input_transitions': sum(x['purpose'] == 'new_retry_table_input' for x in CTX.transitions),
                'fixture_initializations': CTX.initializations,
                'selector_calls': len(CTX.decisions), 'new_full_games': 0},
            'decisions': CTX.decisions, 'transitions': CTX.transitions,
            'new_retry_documents': CTX.retry_documents,
            'scope': 'Actual joined selector/engine consumer on constructed states. No full game, calibrated rival probability, selected-policy change, or new solver.',
        }
        a.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        sys.stdout.write(log.getvalue())
        print(json.dumps(report['execution_counts']))
        return 0 if result.wasSuccessful() else 1
    except (OSError, ValueError, KeyError, ImportError) as exc:
        print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
