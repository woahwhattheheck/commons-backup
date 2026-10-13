"""Regression fixtures execute the pinned official engine, not a mock engine."""
import copy
import importlib.util
import os
from pathlib import Path
import random
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import terminal as policy


class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('t05_test_ev', HERE.parent / 'cloud-eval/evaluate.py')
        cls.ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ev)
        cache = Path(os.environ['T05_ENGINE_DIR'])
        cls.engine, _ = cls.ev.get_engine(cache)

    def state(self, step=698):
        E = self.engine
        cfg = self.ev.Struct({k: v.get('default') if isinstance(v, dict) else v
                              for k, v in E.specification['configuration'].items()})
        cfg.seed = 123
        env = self.ev.Struct(configuration=cfg, done=False, info={})
        state = [self.ev.Struct(observation=self.ev.Struct(), action={}, status='ACTIVE', reward=0)
                 for _ in range(2)]
        E.interpreter(state, env)
        for row in state:
            row.observation.step = step
            row.observation.day = step // 24
            row.observation.hour = step % 24
        return state, env

    def advance(self, state, env, action):
        state[0].action = action
        state[1].action = {}
        self.engine.interpreter(state, env)
        for s in state:
            s.observation.step += 1

    def test_prefix_and_opening_actions_are_exact_parent(self):
        parent = {'farmer': ['PASS'], 'hands': [], 'market': [['HIRE'], ['BUY_PRODUCT', 'FERTILIZER', 10]]}
        for step in (0, 433, 695, 696, 697, 719):
            state, env = self.state(step)
            self.assertIs(policy.overlay(state[0].observation, parent, env.configuration), parent)

    def test_final_drop_sells_before_done(self):
        state, env = self.state(718)
        state[0].observation.private['inventories'][0] = {'WOOL': 3}
        before = state[0].observation.farms[0]['money']
        act = policy.overlay(state[0].observation, {}, env.configuration)
        self.assertEqual(act['farmer'], ['DROP'])
        self.assertIn(['SELL', 'WOOL', 3], act['market'])
        self.advance(state, env, act)
        self.assertEqual(state[0].status, 'DONE')
        self.assertGreater(state[0].reward, before)
        self.assertEqual(state[0].observation.private['inventories'][0], {})

    def test_carried_goods_without_final_drop_have_no_reward(self):
        state, env = self.state(718)
        state[0].observation.private['inventories'][0] = {'WOOL': 3}
        before = state[0].observation.farms[0]['money']
        self.advance(state, env, {'farmer': ['PASS'], 'market': [['SELL', 'WOOL', 3]]})
        self.assertEqual(state[0].reward, before)
        self.assertEqual(state[0].observation.private['inventories'][0], {'WOOL': 3})

    def test_locked_access_is_usable_and_input_is_unchanged(self):
        state, env = self.state(717)
        obs = state[0].observation
        obs.farms[0]['farmer'] = [6, 5]
        obs.private['inventories'][0] = {'WOOL': 2}
        before = copy.deepcopy(obs)
        action = policy.overlay(obs, {}, env.configuration)
        self.assertEqual(action['farmer'], ['WEST'])
        self.assertEqual(obs, before)
        self.advance(state, env, action)
        self.assertEqual(obs.farms[0]['farmer'], [5, 5])
        self.assertEqual(obs.farms[0]['tiles'][5][5], 'LOCKED')
        action = policy.overlay(obs, {}, env.configuration)
        self.advance(state, env, action)
        self.assertGreater(state[0].reward, 3000)

    def test_capacity_admission_prefers_valuable_later_worker(self):
        invs = [{'WHEAT': 100}, {'WOOL': 100}]
        actions, projected = policy.joint_deposits(invs, [0, 1], {}, 100, {'WHEAT': 1, 'WOOL': 200})
        self.assertEqual(actions[0], ['PASS'])
        self.assertEqual(actions[1], ['DROP'])
        self.assertEqual(projected, {'WOOL': 100})

    def test_selective_place_preserves_overflow_instead_of_drop_loss(self):
        state, env = self.state(718)
        obs = state[0].observation
        obs.private['shed']['WHEAT'] = 98
        obs.private['inventories'][0] = {'WHEAT': 10, 'WOOL': 4}
        actions, projected = policy.joint_deposits(obs.private['inventories'], [0], obs.private['shed'], 100, {'WHEAT': 1, 'WOOL': 200})
        self.assertEqual(actions[0], ['PLACE', 'WOOL', 2])
        self.engine._apply_unit_action(obs.farms[0], obs.private, 0, actions[0], 10, 29, 24, 100)
        self.assertEqual(obs.private['shed'], projected)
        self.assertEqual(obs.private['inventories'][0], {'WHEAT': 10, 'WOOL': 2})

    def test_projected_joint_deposits_match_official_worker_order(self):
        rng = random.Random(27413)
        for _ in range(20):
            state, env = self.state()
            obs = state[0].observation
            farm = obs.farms[0]
            farm['hands'] = [[4, 5], [5, 4]]
            obs.private['inventories'] = [{k: rng.randrange(0, 9) for k in ('WOOL', 'WHEAT', 'COW')} for _ in range(3)]
            obs.private['shed']['EGG'] = rng.randrange(80, 101)
            actions, projected = policy.joint_deposits(obs.private['inventories'], range(3), obs.private['shed'], 100, {'WOOL': 200, 'WHEAT': 25})
            for i in range(3):
                self.engine._apply_unit_action(farm, obs.private, i, actions[i], 10, 29, 24, 100)
            self.assertEqual(obs.private['shed'], projected)
            self.assertLessEqual(sum(projected.values()), 100)

    def test_immediate_final_day_water_is_not_discarded(self):
        state, env = self.state(715)
        obs = state[0].observation
        plant = self.engine._new_plant('CARROT', 26, 24)
        obs.farms[0]['tiles'][4][4] = plant
        obs.market['prices']['CARROT'] = 100
        action = policy.overlay(obs, {}, env.configuration)
        self.assertEqual(action['farmer'], ['WATER'])
        self.advance(state, env, action)
        action = policy.overlay(obs, {}, env.configuration)
        self.assertEqual(action['farmer'], ['HARVEST'])
        self.advance(state, env, action)
        self.assertEqual(obs.private['inventories'][0]['CARROT'], 2)
        self.advance(state, env, policy.overlay(obs, {}, env.configuration))
        self.assertEqual(obs.private['inventories'][0], {})
        self.assertGreater(obs.farms[0]['money'], 3000)

    def test_decay_and_water_forecasts_match_official_actions(self):
        for mode in (0, 1, 2):
            for elapsed in (0, 1, 2, 3):
                state, env = self.state(710)
                obs = state[0].observation
                tile = self.engine._new_plant('WHEAT', 25, 24)
                tile.update(yield_units=4, max_lifespan_step=710)
                obs.farms[0]['tiles'][4][4] = tile
                obs.private['inventories'][0] = {'FERTILIZER': 2}
                job = policy.Job((4, 4), 'crop', mode)
                # Force a mature water-eligible tile for the transition oracle.
                result = policy.forecast_job(job, tile, 710, 710 + elapsed, 29, {'FERTILIZER': 2})
                if result is None:
                    continue
                ops, delta = result
                for step in range(710, 710 + elapsed):
                    self.engine._decay_plants(obs.farms[0], step)
                for step, action in enumerate(ops, 710 + elapsed):
                    self.engine._apply_unit_action(obs.farms[0], obs.private, 0, action, 10, 29, 24, 100)
                    self.engine._decay_plants(obs.farms[0], step)
                self.assertEqual(obs.private['inventories'][0].get('WHEAT', 0), delta['WHEAT'])
                self.assertEqual(obs.private['inventories'][0].get('FERTILIZER', 0), 2 + delta.get('FERTILIZER', 0))

    def test_expired_plant_is_not_a_future_harvest(self):
        tile = self.engine._new_plant('CARROT', 20, 24)
        tile.update(yield_units=1, max_lifespan_step=698)
        self.assertIsNone(policy.forecast_job(policy.Job((4, 4), 'crop'), tile, 698, 699, 29, {}))

    def test_joint_routes_reserve_each_resource_once(self):
        state, env = self.state(713)
        obs = state[0].observation
        farm = obs.farms[0]
        farm['hands'] = [[4, 4], [5, 4]]
        farm['tiles'][4][4] = self.engine._new_animal('COW', 0)
        farm['tiles'][4][4].update(yield_units=6, fertilizer_available=True)
        routes, evaluations = policy.assign_routes(farm, [{}, {}, {}], 713, 718, 29,
                                                   {'MILK': 160, 'FERTILIZER': 100}, 100)
        groups = [job.group for route in routes for job in route]
        self.assertEqual(len(groups), len(set(groups)))
        self.assertEqual(len(groups), 2)
        for evaluation in evaluations:
            self.assertLessEqual(713 + evaluation[1] - 1, 718)

    def test_doomed_collection_and_nonpaying_care_are_omitted(self):
        state, env = self.state(717)
        obs = state[0].observation
        farm = obs.farms[0]
        farm['farmer'] = [0, 0]
        farm['tiles'][0][0] = self.engine._new_animal('COW', 0)
        farm['tiles'][0][0].update(yield_units=6, fertilizer_available=True)
        action = policy.overlay(obs, {}, env.configuration)
        self.assertIn(action['farmer'][0], ['EAST', 'SOUTH'])
        self.assertNotIn(action['farmer'][0], ['HARVEST', 'CARE', 'FEED'])


    def test_inherited_routes_require_visible_resources_and_deduplicate(self):
        state, env = self.state(698)
        farm = state[0].observation.farms[0]
        farm['hands'] = [[4, 4]]
        farm['tiles'][4][4] = self.engine._new_plant('CARROT', 26, 24)
        tape = [{'farmer': [op], 'hands': [[op]]}
                for op in ('FERTILIZE', 'WATER', 'HARVEST', 'HARVEST')]
        routes = policy.inherited_routes(farm, tape, 29)
        self.assertEqual(routes, [[policy.Job((4, 4), 'crop', 2)], []])
        farm['tiles'][4][4] = None
        self.assertEqual(policy.inherited_routes(farm, tape, 29), [[], []])

    def test_persistent_planner_executes_return_then_actual_deposit(self):
        state, env = self.state(717)
        obs = state[0].observation
        obs.farms[0]['farmer'] = [6, 5]
        obs.private['inventories'][0] = {'WOOL': 2}
        planner = policy.Planner()
        action = planner.act(obs, {}, env.configuration, own_future_actions=[])
        self.assertEqual(action['farmer'], ['WEST'])
        self.advance(state, env, action)
        action = planner.act(obs, {}, env.configuration, own_future_actions=[])
        self.assertEqual(action['farmer'], ['DROP'])
        self.advance(state, env, action)
        self.assertGreater(state[0].reward, 3000)
        parent = {'farmer': ['PASS']}
        self.assertIs(planner.act(obs, parent, env.configuration), parent)
        self.assertIsNone(planner.queues)

    def test_native_empty_globals_loader_matches_parent_initial_action(self):
        spec = importlib.util.spec_from_file_location(
            't05_native_test', HERE.parent / 'cloud-pack/official.py')
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        candidate = native.make_agent(HERE / 'main.py')
        parent = native.make_agent(
            HERE.parent / 'cloud-frontier-policy/next-panel/vendor/arlene.py')
        state, env = self.state(0)
        self.assertIsNone(env.configuration.seed)
        observation = state[0].observation
        expected = parent(copy.deepcopy(observation), copy.deepcopy(env.configuration))
        actual = candidate(copy.deepcopy(observation), copy.deepcopy(env.configuration))
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
