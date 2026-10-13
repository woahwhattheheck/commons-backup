# SPDX-License-Identifier: Apache-2.0
"""Independent exact-tour, native transform, full-interpreter and custody gates.

Set TITAN_ROOT to the authenticated native package. No network or skipped tests.
WAYFINDER_CANDIDATE may select a deliberately mutated composed source for gates.
"""
from __future__ import annotations
from copy import deepcopy
import ast
import hashlib
import importlib.util
from itertools import permutations
import os
from pathlib import Path
import random
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import compose_work_route as composition

ROOT = Path(os.environ['TITAN_ROOT']).resolve()
SOURCE = (ROOT/'spatial_tempo.py').read_text()
if composition.blob(SOURCE.encode()) != composition.SOURCE_BLOB:
    raise RuntimeError('unexpected native source: require exact declared input')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'checks'))
import mechanics
import test_engine_semantics as semantics


def load_source(source, name):
    module = ModuleType(name)
    module.__file__ = str(ROOT/'spatial_tempo.py')
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


BASE = load_source(SOURCE, '_wayfinder_before')
CANDIDATE_SOURCE = (Path(os.environ['WAYFINDER_CANDIDATE']).read_text()
                    if 'WAYFINDER_CANDIDATE' in os.environ else composition.compose(SOURCE))
CAND = load_source(CANDIDATE_SOURCE, '_wayfinder_after')


def exhaustive(origin, goal, groups, length):
    """Literal original algorithm; no candidate distance, DP or route helper."""
    choices = []
    for order in permutations(range(len(groups))):
        q = origin
        trial = []
        for index in order:
            pos, acts = groups[index]
            trial += BASE.path(q, pos) + acts
            q = pos
        trial += BASE.path(q, goal)
        if len(trial) <= length:
            choices.append(trial)
    return min(choices, key=lambda a: sum(x[0] in BASE.MOVES for x in a)) if choices else None


def cases(seed=20260911, per_size=80):
    rng = random.Random(seed)
    grid = [(x, y) for x in range(10) for y in range(10)]
    for size in range(1, 7):
        for _ in range(per_size):
            points = rng.sample(grid, size)
            groups = [(p, [[rng.choice(sorted(BASE.WORK))] for _ in range(rng.randint(1, 3))])
                      for p in points]
            yield rng.choice(grid), rng.choice(grid), groups, rng.randrange(3, 100)


class ExactTourTests(unittest.TestCase):
    def test_01_random_full_action_reference(self):
        for origin, goal, groups, length in cases():
            with self.subTest(size=len(groups), origin=origin, goal=goal, length=length):
                self.assertEqual(CAND._minimum_work_trial(origin, goal, groups, length),
                                 exhaustive(origin, goal, groups, length))

    def test_02_all_site_labels_on_symmetric_tie_grid(self):
        # 720 labelings: value ties must follow input permutation order, not
        # geometric ordering, reverse order or the order states happen to settle.
        points = [(1, 1), (3, 1), (1, 2), (3, 2), (1, 3), (3, 3)]
        for ordering in permutations(points):
            groups = [(p, [['WATER'], ['CARE']]) for p in ordering]
            self.assertEqual(CAND._minimum_work_trial((2, 2), (2, 2), groups, 40),
                             exhaustive((2, 2), (2, 2), groups, 40))

    def test_03_feasibility_exact_boundary_all_sizes(self):
        for origin, goal, groups, _ in cases(391, 12):
            winner = exhaustive(origin, goal, groups, 1000)
            for length in (len(winner)-1, len(winner), len(winner)+1):
                self.assertEqual(CAND._minimum_work_trial(origin, goal, groups, length),
                                 exhaustive(origin, goal, groups, length))

    def test_04_input_and_work_identity_preserved(self):
        for origin, goal, groups, _ in cases(414, 6):
            before = deepcopy(groups)
            trial = CAND._minimum_work_trial(origin, goal, groups, 1000)
            self.assertEqual(groups, before)
            work = [a for a in trial if a[0] in BASE.WORK]
            original = [a for _, actions in groups for a in actions]
            self.assertEqual(sorted(map(id, work)), sorted(map(id, original)))
            # Preserve action-list alias shape of the actual old winning list.
            old = exhaustive(origin, goal, groups, 1000)
            self.assertEqual([[i for i, v in enumerate(trial) if v is a] for a in trial],
                             [[i for i, v in enumerate(old) if v is a] for a in old])

    def test_05_in_site_action_order_and_movement_endpoints(self):
        for n in range(1, 7):
            groups = [((i+1, 1), [['FEED'], ['CARE'], ['HARVEST'], ['COLLECT_FERTILIZER']])
                      for i in reversed(range(n))]
            origin, goal = (0, 0), (9, 9)
            trial = CAND._minimum_work_trial(origin, goal, groups, 1000)
            p = origin; seen = []
            for action in trial:
                if action[0] in BASE.WORK: seen.append((p, action))
                p = BASE.move(p, action, 10)
            self.assertEqual(p, goal)
            for site, actions in groups:
                self.assertEqual([a for pos, a in seen if pos == site], actions)
            self.assertEqual(trial, exhaustive(origin, goal, groups, 1000))

    def test_06_only_winning_paths_are_built(self):
        for origin, goal, groups, _ in cases(714, 3):
            with patch.object(CAND, 'path', wraps=CAND.path) as called:
                CAND._minimum_work_trial(origin, goal, groups, 1000)
                self.assertEqual(called.call_count, len(groups)+1)
            with patch.object(CAND, 'path', wraps=CAND.path) as called:
                self.assertIsNone(CAND._minimum_work_trial(origin, goal, groups, -1))
                self.assertEqual(called.call_count, 0)

    def test_07_native_bounds_and_zero_distance(self):
        for groups in ([], [((x, 0), [['WATER']]) for x in range(7)]):
            with self.assertRaises(ValueError):
                CAND._minimum_work_trial((0, 0), (0, 0), groups, 100)
        groups = [((2, 2), [['WATER'], ['CARE']])]
        self.assertEqual(CAND._minimum_work_trial((2, 2), (2, 2), groups, 2), groups[0][1])
        self.assertIsNone(CAND._minimum_work_trial((2, 2), (2, 2), groups, 1))


class CompositionTests(unittest.TestCase):
    def test_08_idempotence_and_byte_exact_restore(self):
        result = composition.compose(SOURCE)
        self.assertEqual(composition.compose(result), result)
        restored = result.replace(composition.HELPER, '', 1).replace(composition.NEW, composition.OLD, 1)
        self.assertEqual(restored, SOURCE)

    def test_09_peer_method_survives(self):
        marker = '        # Compare exact own-unit mechanics; no invented future state.'
        source = SOURCE.replace(marker, marker+'\n        # Peer receipt preserved.')
        result = composition.compose(source)
        self.assertIn('# Peer receipt preserved.', result)
        self.assertEqual(result.replace(composition.HELPER, '', 1).replace(composition.NEW, composition.OLD, 1), source)

    def test_10_primitive_and_caller_drift_fail_closed(self):
        for before, after in [
            ('abs(a[0]-b[0])+abs(a[1]-b[1])', 'max(abs(a[0]-b[0]),abs(a[1]-b[1]))'),
            ("WORK={'WATER'", "WORK={'EAST','WATER'"),
            ('from itertools import permutations', 'from itertools import permutations as other'),
            ('1<=len(groups)<=6', '1<=len(groups)<=7'),
            ('if saved>0 and self._same_work_state', 'if saved>=0 and self._same_work_state'),
            ('tasks.append((p,list(a)))', 'tasks.append((p,list(reversed(a))))'),
        ]:
            self.assertIn(before, SOURCE)
            with self.subTest(before=before), self.assertRaises(ValueError):
                composition.compose(SOURCE.replace(before, after, 1))

    def test_11_mixed_or_changed_helper_fails_closed(self):
        result = composition.compose(SOURCE)
        for source in (SOURCE.replace(composition.OLD, composition.NEW),
                       result.replace('states={(1<<i,i)', 'states={(2<<i,i)'),
                       result+composition.HELPER,
                       result.replace(composition.NEW, composition.OLD)):
            with self.assertRaises(ValueError):
                composition.compose(source)

    def test_12_entire_native_guard_and_commit_tail_unchanged(self):
        result = composition.compose(SOURCE)
        for source in (SOURCE, result):
            self.assertIn('if saved>0 and self._same_work_state(obs,i,sequence,trial):best=trial', source)
        self.assertEqual(result.split('            extra=None\n', 1)[1], SOURCE.split('            extra=None\n', 1)[1])


class NativeTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        semantics.EngineSemantics.setUpClass()
        cls.fixture_engine = semantics.EngineSemantics()
        cls.engine = cls.fixture_engine.engine

    def fixture(self, size=6, seat=0, actor=0, species='CARROT', tempo=False):
        state, env = self.fixture_engine.fixture(step=24, cash=100000)
        farm = state[0].observation.farms[seat]
        farm['farmer'] = [2, 2]
        farm['hands'] = [[4, 4]]
        if actor:
            farm['farmer'], farm['hands'][0] = [4, 4], [2, 2]
        private = state[seat].observation.private
        private['inventories'] = [{}, {}]
        private['shed']['WHEAT'] = 20
        private['inventories'][actor] = {'WHEAT': 6}
        points = [(1, 1), (3, 3), (3, 1), (1, 3), (1, 2), (3, 2)][:size]
        if species == 'CARROT':
            for x, y in points:
                farm['tiles'][y][x] = mechanics._new_plant('CARROT', 0, 24)
            work = ['WATER']
        else:
            for x, y in points:
                farm['tiles'][y][x] = self.engine._new_animal(species)
            work = ['CARE']
        groups = [(p, [list(work)]) for p in points]
        sequence = []; pos = (2, 2)
        for p, acts in groups:
            sequence += BASE.path(pos, p)+acts; pos = p
        sequence += BASE.path(pos, (2, 2))
        # Test only complete legal native 24-slot windows.
        if len(sequence)>24:
            points = [(1,1),(3,1),(1,2),(3,2),(1,3),(3,3)][:size]
            for x,y in points:
                farm['tiles'][y][x] = mechanics._new_plant('CARROT', 0, 24)
            sequence=[];pos=(2,2)
            for p in points:
                sequence += BASE.path(pos,p)+[['WATER']];pos=p
            sequence += BASE.path(pos,(2,2))
        self.assertLessEqual(len(sequence),24)
        sequence += [['PASS']]*(24-len(sequence))
        route = [{'farmer':['PASS'],'hands':[['PASS']],'market':[]} for _ in range(720)]
        for step, action in enumerate(sequence,24):
            BASE.set_unit(route[step],actor,deepcopy(action))
        return state, env, route

    def compare(self, state, env, route, seat, *, pathing=True, tempo=False, veto=False):
        obs = deepcopy(state[seat].observation)
        arms=[]
        for module in (BASE,CAND):
            controller=SimpleNamespace(R={'case':deepcopy(route)},cur='case')
            owner=module.SpatialTempo(mechanics,pathing=pathing,tempo=tempo)
            owner.configure(env.configuration)
            if veto:
                # Explicit veto seam control. Full-state agreement uses real
                # mechanics in all other cases; this is not an engine oracle.
                owner._same_work_state=lambda *args:False
            selected=deepcopy(route[24])
            result=owner.transform(deepcopy(obs),selected,controller)
            arms.append((result,controller.R,owner.events,owner.plans,owner.edits,owner.active))
        self.assertEqual(arms[0],arms[1])
        self.assertEqual(state[seat].observation,obs)
        return arms

    def test_13_actual_transform_both_seats_actors_and_sizes(self):
        for n in range(1,7):
            for seat in (0,1):
                for actor in (0,1):
                    state,env,route=self.fixture(n,seat,actor)
                    arms=self.compare(state,env,route,seat)
                    if n>=3:
                        self.assertTrue(arms[0][2], 'constructed pathing must engage')

    def test_14_default_off_and_veto_no_route_change(self):
        for seat in (0,1):
            for actor in (0,1):
                state,env,route=self.fixture(6,seat,actor)
                for pathing,veto in ((False,False),(True,True)):
                    arms=self.compare(state,env,route,seat,pathing=pathing,veto=veto)
                    self.assertEqual(arms[1][1]['case'],route)
                    self.assertEqual(arms[1][2],[])

    def test_15_full_interpreter_day_state_equivalence(self):
        # These are 48 complete-day constructed trajectories, not ladder games.
        calls=0
        for n in range(1,7):
            for seat in (0,1):
                for actor in (0,1):
                    state,env,route=self.fixture(n,seat,actor)
                    arms=self.compare(state,env,route,seat)
                    left,right=deepcopy(state),deepcopy(state)
                    le,re=deepcopy(env),deepcopy(env)
                    for step in range(24,48):
                        for states,environment,arm in ((left,le,arms[0]),(right,re,arms[1])):
                            for s in states:
                                s.observation.step=step;s.observation.day=step//24;s.observation.hour=step%24
                                s.action={'farmer':['PASS'],'hands':[],'market':[]}
                            states[seat].action=deepcopy(arm[1]['case'][step])
                            self.engine.interpreter(states,environment);calls+=1
                        self.assertEqual(left,right)
                        self.assertEqual(le,re)
        self.assertEqual(calls,1152)

    def test_16_existing_tempo_and_raw_market_prefix_unchanged(self):
        for seat in (0,1):
            state,env,route=self.fixture(4,seat,0)
            route[24]['market']=[['SELL','MILK',1],[],['SELL','WHEAT',0]]
            arms=self.compare(state,env,route,seat,tempo=True)
            self.assertEqual(arms[0][0]['market'],route[24]['market'])
            self.assertEqual(arms[1][1]['case'][24]['market'],route[24]['market'])

    def test_17_live_safety_guard_not_bypassed(self):
        # The native own-unit simulation rejects an observed weed. This checks
        # the real existing guard in both sources, not a substitute transition.
        state,env,route=self.fixture(4)
        obs=state[0].observation
        farm=obs.farms[0];farm['farmer']=[1,1];farm['tiles'][1][1]={'kind':'WEED'}
        for module in (BASE,CAND):
            owner=module.SpatialTempo(mechanics)
            self.assertFalse(owner._same_work_state(obs,0,[['WATER']],[['WATER']]))


if __name__=='__main__':
    unittest.main(verbosity=2)
