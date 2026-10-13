"""Selected-action hiring stage over the pinned official engine, not new games.

T10_SOURCEPACK supplies the retained verified engine/Arlene closure.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import labor_capital as labor
from test_engine import BASE, ENGINE, PASS, Script, observation
from test_forecast_fork import NestedParent, load_file


class NoCurrentCall:
    def act(self, obs):
        raise AssertionError('the selected-action stage called the live parent')

    def __copy__(self):
        raise AssertionError('explicit factory must own the continuation')


class CountedScript(Script):
    def __init__(self, actions):
        super().__init__(actions)
        self.calls = 0

    def act(self, obs):
        self.calls += 1
        return super().act(obs)


class SelectedActionTests(unittest.TestCase):
    def test_transform_never_calls_current_parent(self):
        selected = dict(PASS, market=[['HIRE']])
        actor = labor.HiringAgent(NoCurrentCall(), ENGINE,
                                  fork_parent=lambda: Script({}).act)
        result = actor.transform(observation(22), selected)
        self.assertEqual(result['market'], [labor.NO_ORDER])
        self.assertEqual(actor.last_decision['selected'], 'omit_hire_suffix_1')
        self.assertEqual(actor.last_decision['control_cash'], 99)

    def test_act_keeps_exactly_one_actual_parent_call(self):
        parent = CountedScript({22: dict(PASS, market=[['HIRE']])})
        actor = labor.HiringAgent(parent, ENGINE)
        result = actor.act(observation(22))
        self.assertEqual(parent.calls, 1)
        self.assertEqual(result['market'], [labor.NO_ORDER])
        self.assertEqual(actor.counts, {'omit_hire_suffix_1': 1})

    def test_no_options_keep_exact_object_and_request_no_fork(self):
        selected = dict(PASS, market=[['BUY_SEED', 'CARROT', 1]], metadata={'tag': [1]})
        def forbidden():
            raise AssertionError('no forecast is needed')
        actor = labor.HiringAgent(NoCurrentCall(), ENGINE, fork_parent=forbidden)
        self.assertIs(actor.transform(observation(22), selected), selected)
        self.assertEqual(actor.last_decision, {'selected': 'baseline', 'evaluated': 0})
        self.assertFalse(actor.counts)

    def test_no_evaluated_gain_keeps_supplied_action_identity(self):
        selected = dict(PASS, market=[['HIRE']])
        actor = labor.HiringAgent(NoCurrentCall(), ENGINE,
                                  fork_parent=lambda: Script({}).act,
                                  configuration={'farmHandCostMult': 0})
        self.assertIs(actor.transform(observation(22), selected), selected)
        self.assertEqual(actor.last_decision['selected'], 'baseline')
        self.assertEqual(actor.last_decision['control_cash'], 100)

    def test_supply_preserves_workers_nonhire_slots_and_metadata(self):
        selected = {'farmer': ['WEST'], 'hands': [['EAST']],
                    'market': [['BUY_SEED', 'CARROT', 1], ['HIRE'],
                               ['SELL', 'EGG', 1], ['HIRE']],
                    'metadata': {'stage': ['chosen']}}
        obs = observation(22)
        obs.private['shed']['EGG'] = 1
        saved = copy.deepcopy((obs, selected))
        actor = labor.HiringAgent(NoCurrentCall(), ENGINE,
                                  fork_parent=lambda: Script({}).act)
        result = actor.transform(obs, selected)
        self.assertEqual(result['market'], [['BUY_SEED', 'CARROT', 1], labor.NO_ORDER,
                                            ['SELL', 'EGG', 1], labor.NO_ORDER])
        self.assertEqual(result['farmer'], selected['farmer'])
        self.assertEqual(result['hands'], selected['hands'])
        self.assertEqual(result['metadata'], selected['metadata'])
        self.assertEqual((obs, selected), saved)
        self.assertIsNot(result, selected)
        self.assertIsNot(result['metadata'], selected['metadata'])

    def test_explicit_forks_snapshot_already_selected_nested_owner(self):
        parent = NestedParent({22: dict(PASS, market=[['HIRE'], ['HIRE']])})
        obs = observation(22)
        selected = parent.act(obs)
        before = copy.deepcopy((parent.state, obs, selected))
        forks = []
        def factory():
            fork = parent.fork()
            forks.append(fork)
            return fork.act
        actor = labor.HiringAgent(parent, ENGINE, fork_parent=factory)
        actor.transform(obs, selected)
        self.assertEqual((parent.state, obs, selected), before)
        self.assertEqual(parent.state['calls'], 1)
        self.assertEqual(len(forks), 3)
        self.assertTrue(all(p.state['steps'] == [22, 23] for p in forks))
        self.assertEqual(len({id(p.state) for p in forks}), 3)

    def test_factory_failure_preserves_supplied_action_and_current_call_count(self):
        obs = observation(22)
        parent = NestedParent({22: dict(PASS, market=[['HIRE']])})
        selected = parent.act(obs)
        before = copy.deepcopy((parent.state, obs, selected))
        def broken():
            raise LookupError('caller-owned fork failure')
        actor = labor.HiringAgent(parent, ENGINE, fork_parent=broken)
        with self.assertRaisesRegex(LookupError, 'caller-owned fork failure'):
            actor.transform(obs, selected)
        self.assertEqual((parent.state, obs, selected), before)

    def test_forecast_failure_never_reselects_current_action(self):
        obs = observation(21)
        parent = NestedParent({21: dict(PASS, market=[['HIRE']])}, fail_step=22)
        selected = parent.act(obs)
        before = copy.deepcopy((parent.state, obs, selected))
        actor = labor.HiringAgent(parent, ENGINE, fork_parent=lambda: parent.fork().act)
        with self.assertRaisesRegex(RuntimeError, 'forecast failure'):
            actor.transform(obs, selected)
        self.assertEqual((parent.state, obs, selected), before)

    def test_order_cap_does_not_turn_ignored_hires_into_candidates(self):
        selected = dict(PASS, market=[['BUY_SEED', 'CARROT', 1], ['HIRE']])
        actor = labor.HiringAgent(NoCurrentCall(), ENGINE,
                                  configuration={'maxMarketOrdersPerTurn': 1})
        self.assertIs(actor.transform(observation(22), selected), selected)
        self.assertEqual(actor.last_decision['evaluated'], 0)

    def test_repeated_selected_action_does_not_share_mutable_forecasts(self):
        selected = dict(PASS, market=[['HIRE']])
        owner = NestedParent()
        actor = labor.HiringAgent(owner, ENGINE, fork_parent=lambda: owner.fork().act)
        first = actor.transform(observation(22), selected)
        first_decision = copy.deepcopy(actor.last_decision)
        second = actor.transform(observation(22), selected)
        self.assertEqual(first, second)
        self.assertEqual(first_decision, actor.last_decision)
        self.assertEqual(owner.state['calls'], 0)
        self.assertEqual(actor.counts, {'omit_hire_suffix_1': 2})

    def test_both_entrypoints_agree_in_modes_positions_and_cash_regimes(self):
        checked = 0
        for mode in ('reserve', 'timed'):
            for seat in (0, 1):
                for money in (0, 1, 20, 100, 233):
                    with self.subTest(mode=mode, seat=seat, money=money):
                        obs = observation(22, money=money, seat=seat)
                        obs.private['shed']['EGG'] = 2
                        selected = dict(PASS, market=[['HIRE'], ['BUY_SEED', 'CARROT', 1],
                                                     ['SELL', 'EGG', 2], ['HIRE']])
                        parents = [CountedScript({22: selected}) for _ in range(2)]
                        direct = labor.HiringAgent(parents[0], ENGINE, mode=mode)
                        staged = labor.HiringAgent(parents[1], ENGINE, mode=mode)
                        want = direct.act(copy.deepcopy(obs))
                        supply = parents[1].act(copy.deepcopy(obs))
                        got = staged.transform(copy.deepcopy(obs), supply)
                        self.assertEqual(want, got)
                        self.assertEqual(direct.last_decision, staged.last_decision)
                        self.assertEqual(direct.counts, staged.counts)
                        self.assertEqual([p.calls for p in parents], [1, 1])
                        checked += 1
        self.assertEqual(checked, 20)

    def test_current_selected_action_not_parent_tape_is_evaluated(self):
        # No tape can supply this cash/seed choice: the live parent is forbidden.
        obs = observation(718, money=20)
        selected = dict(PASS, market=[['BUY_SEED', 'CARROT', 1], ['HIRE']])
        actor = labor.HiringAgent(NoCurrentCall(), ENGINE,
                                  fork_parent=lambda: Script({}).act)
        result = actor.transform(obs, selected)
        self.assertIs(result, selected)  # The hire was unfunded; no cash gain.
        self.assertEqual(actor.last_decision['control_cash'], 0)
        self.assertEqual(actor.last_decision['candidate_cash'], {'omit_hire_suffix_1': 0})

    def test_existing_keel_owner_can_supply_its_selected_action_and_factory(self):
        default = Path(__file__).resolve().parents[1] / 'cloud-service-labor-composition/composition.py'
        path = Path(os.environ.get('T10_COMPOSITION_SOURCE', str(default)))
        composition = load_file(path, 't10_selected_keel')
        arlene = load_file(BASE / 'cloud-frontier-policy/next-panel/vendor/arlene.py',
                           't10_selected_arlene')
        owner = composition.Composition(arlene, labor, None, ENGINE,
                                        service=False, labor=False)
        obs = observation(22)
        selected = owner.act(obs)
        state = copy.deepcopy(owner.base.__dict__)
        stage = labor.HiringAgent(owner, ENGINE, fork_parent=owner.fork_parent)
        result = stage.transform(obs, selected)
        expected_parent = arlene.Agent()
        expected = labor.HiringAgent(expected_parent, ENGINE).act(copy.deepcopy(obs))
        self.assertEqual(result, expected)
        self.assertEqual(owner.parent_calls, 1)
        self.assertEqual(owner.calls, 1)
        self.assertEqual(owner.base.__dict__, state)


if __name__ == '__main__':
    unittest.main()
