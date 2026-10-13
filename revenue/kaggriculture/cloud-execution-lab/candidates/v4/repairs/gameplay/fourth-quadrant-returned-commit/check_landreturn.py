# SPDX-License-Identifier: Apache-2.0
"""Independent real-interpreter checks for the native paid-land lifecycle.

Requires a complete, locally available authenticated b567 source package. Never
fetches data or runs the historical evaluator's hand-truncating play() function.
The controller is an explicit deterministic authored-row reader; economic
admission deliberately selects a generated proposal, not a claim of field EV.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

from compose import compose, git_blob, PREIMAGE

PINS = {
    'fourth_quadrant.py': PREIMAGE,
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
COUNTS = {'interpreter_calls': 0, 'authored_controller_calls': 0,
          'receipt_matrix_cells': 0, 'continuation_worlds': 0}
WITNESSES = []


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def from_bytes(name, source):
    module = types.ModuleType(name)
    exec(compile(source, '<' + name + '>', 'exec'), module.__dict__)
    return module


def action(market=None, farmer=None, hands=None):
    return {'farmer': farmer or ['PASS'], 'hands': hands or [], 'market': market or []}


def world(seat=0, money=10000, step=264, cap=10):
    cfg = L.Struct()
    for key, value in E.specification['configuration'].items():
        cfg[key] = value.get('default') if isinstance(value, dict) else value
    cfg.update(seed=91811, maxMarketOrdersPerTurn=cap, weedChance=0)
    env = L.Struct(configuration=cfg, done=False, info={})
    state = [L.Struct(observation=L.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    E.interpreter(state, env); COUNTS['interpreter_calls'] += 1
    farm = state[seat].observation.farms[seat]
    farm['money'] = 10000
    E._do_buy_land(farm, 10); E._do_buy_land(farm, 10)
    farm['money'] = money
    for s in state:
        s.observation.step = step
        s.observation.day = step // 24
        s.observation.hour = step % 24
    return state, env


def tick(state, env, seat, own, other=None):
    state[seat].action = copy.deepcopy(own)
    state[1-seat].action = copy.deepcopy(other or action())
    E.interpreter(state, env); COUNTS['interpreter_calls'] += 1
    for s in state:
        s.observation.step += 1
    return copy.deepcopy(state[seat].observation)


class RowController:
    """A named collaborator, not the full runtime/production seller."""
    def __init__(self, rows=None):
        self.R = {'r': rows or [action() for _ in range(720)]}
        self.cur = 'r'

    def act(self, observation):
        COUNTS['authored_controller_calls'] += 1
        return copy.deepcopy(self.R[self.cur][observation['step']])


def installed(module, observation, cfg, rows=None):
    ctl = RowController(rows)
    q = module.FourthQuadrant(E, lambda m, obs, config, routes, options: options[0] if options else None)
    q.configure(cfg); q.install(ctl)
    return q, ctl


def pending(module, selected, cap=10, step=264):
    q = module.FourthQuadrant(E, None)
    q.configure({'maxMarketOrdersPerTurn': cap})
    q.pending = {'start': step, 'crop': 'CARROT', 'tiles': [(5, 5)], 'workers': 1, 'cost': 100}
    q.selected = copy.deepcopy(selected)
    return q


class LandReturnTests(unittest.TestCase):
    def test_complete_generated_bundle_is_admitted_and_observed(self):
        for seat in (0, 1):
            state, env = world(seat)
            obs = copy.deepcopy(state[seat].observation)
            q, ctl = installed(M, obs, env.configuration)
            chosen = ctl.act(obs)
            self.assertIsNotNone(q.pending)
            self.assertIn(['BUY_LAND'], chosen['market'])
            q.finish(obs, copy.deepcopy(chosen))
            self.assertIsNotNone(q.plan)
            after = tick(state, env, seat, chosen)
            self.assertIn('SE', after['farms'][seat]['unlocked_quadrants'])
            outgoing = ctl.act(after)
            self.assertFalse(q.disabled)
            self.assertTrue(outgoing['hands'])
            q.finish(after, outgoing)
            self.assertEqual(q.generation, 1)
            self.assertEqual(len(q.events), 1)

    def test_initial_land_removed_with_same_hire_count_rejects(self):
        for seat in (0, 1):
            state, env = world(seat)
            obs = copy.deepcopy(state[seat].observation)
            q, ctl = installed(M, obs, env.configuration)
            chosen = ctl.act(obs)
            returned = copy.deepcopy(chosen)
            returned['market'][0] = ['PASS']
            before = copy.deepcopy((obs, chosen, returned))
            q.finish(obs, returned)
            self.assertIsNone(q.plan)
            self.assertEqual(q.generation, 0)
            self.assertEqual((obs, chosen, returned), before)
            after = tick(state, env, seat, returned)
            self.assertNotIn('SE', after['farms'][seat]['unlocked_quadrants'])
            self.assertEqual(ctl.act(after), action())
            self.assertIsNone(q.pending)

    def test_executable_prefix_and_full_unit_matrix(self):
        for seat in (0, 1):
            state, _ = world(seat)
            obs = copy.deepcopy(state[seat].observation)
            for cap in (0, -1, 1, 2, 3, 10, '2'):
                n = max(1, int(cap))
                selected = action([['BUY_LAND']] + [['PASS'] for _ in range(n-1)])
                variants = []
                dead = copy.deepcopy(selected); dead['market'].append(['HIRE'])
                variants.append(('dead_hire', dead, True))
                dead = copy.deepcopy(selected); dead['market'].append(['BUY_SEED', 'CARROT', 9])
                variants.append(('dead_seed', dead, True))
                dead = copy.deepcopy(selected); dead['market'].append(None)
                variants.append(('dead_invalid', dead, True))
                land = copy.deepcopy(selected); land['market'][0] = ['PASS']
                variants.append(('land_removed', land, False))
                shifted = copy.deepcopy(selected); shifted['market'].insert(0, [])
                variants.append(('empty_slot_shift', shifted, False))
                units = copy.deepcopy(selected); units['farmer'] = ['EAST']
                variants.append(('unit_changed', units, False))
                extra = copy.deepcopy(selected); extra['hands'] = [['PLANT', 'WHEAT']]
                variants.append(('extra_plant', extra, False))
                metadata = copy.deepcopy(selected); metadata['diagnostic'] = 'irrelevant'
                variants.append(('metadata', metadata, True))
                for name, returned, expected in variants:
                    with self.subTest(seat=seat, cap=cap, name=name):
                        COUNTS['receipt_matrix_cells'] += 1
                        q = pending(M, selected, cap)
                        untouched = copy.deepcopy((obs, selected, returned))
                        q.finish(obs, returned)
                        self.assertEqual(q.plan is not None, expected)
                        self.assertEqual(q.generation, int(expected))
                        self.assertEqual((obs, selected, returned), untouched)
                        self.assertIsNone(q.pending); self.assertIsNone(q.selected)

    def test_engine_dead_suffix_is_identical_even_at_zero_cap(self):
        for seat in (0, 1):
            for cap in (0, -1, 1, 3, 10):
                a, env_a = world(seat, cap=cap)
                b, env_b = copy.deepcopy((a, env_a))
                selected = action([['BUY_LAND']] + [[] for _ in range(max(1, cap)-1)])
                returned = copy.deepcopy(selected)
                returned['market'] += [['HIRE'], ['BUY_SEED', 'CARROT', 5]]
                q = pending(M, selected, cap)
                q.finish(copy.deepcopy(a[seat].observation), returned)
                self.assertIsNotNone(q.plan)
                tick(a, env_a, seat, selected)
                tick(b, env_b, seat, returned)
                self.assertEqual([x.observation for x in a], [x.observation for x in b])
                self.assertEqual([(x.status, x.reward) for x in a], [(x.status, x.reward) for x in b])

    def test_extra_nonexistent_plant_changes_real_actor_admission(self):
        for seat in (0, 1):
            a, env_a = world(seat)
            a[seat].observation.private['seeds']['WHEAT'] = 1
            b, env_b = copy.deepcopy((a, env_a))
            selected = action(farmer=['PLANT', 'WHEAT'])
            returned = action(farmer=['PLANT', 'WHEAT'], hands=[['PLANT', 'WHEAT']])
            q = pending(M, selected)
            q.finish(copy.deepcopy(a[seat].observation), returned)
            self.assertIsNone(q.plan)
            tick(a, env_a, seat, selected); tick(b, env_b, seat, returned)
            self.assertIsInstance(a[seat].observation.farms[seat]['tiles'][4][4], dict)
            self.assertIsNone(b[seat].observation.farms[seat]['tiles'][4][4])

    def test_observed_unfilled_purchase_aborts_before_next_optional_action(self):
        for seat in (0, 1):
            state, env = world(seat, money=500)
            obs = copy.deepcopy(state[seat].observation)
            q, ctl = installed(M, obs, env.configuration)
            first = ctl.act(obs); q.finish(obs, first)
            self.assertIsNotNone(q.plan)
            after = tick(state, env, seat, first)
            self.assertNotIn('SE', after['farms'][seat]['unlocked_quadrants'])
            self.assertEqual(len(after['farms'][seat]['hands']), 1)
            outgoing = ctl.act(after)
            self.assertIsNone(q.plan)
            self.assertTrue(q.disabled)
            self.assertEqual(q.events[-1]['kind'], 'bundle_aborted')
            self.assertEqual(outgoing, action())
            self.assertEqual(q.generation, 2)

    def test_delayed_purchase_displaced_after_initial_admission(self):
        for seat in (0, 1):
            state, env = world(seat)
            rows = [action() for _ in range(720)]
            rows[264] = action([['HIRE']])
            obs = copy.deepcopy(state[seat].observation)
            q, ctl = installed(M, obs, env.configuration, rows)
            first = ctl.act(obs)
            self.assertNotIn(['BUY_LAND'], first['market'])
            q.finish(obs, first)
            self.assertIsNotNone(q.plan)
            after = tick(state, env, seat, first)
            second = ctl.act(after)
            self.assertIn(['BUY_LAND'], second['market'])
            second['market'] = [['PASS'] if o == ['BUY_LAND'] else o for o in second['market']]
            q.finish(after, second)
            after = tick(state, env, seat, second)
            self.assertNotIn('SE', after['farms'][seat]['unlocked_quadrants'])
            self.assertEqual(len(after['farms'][seat]['hands']), 2)
            self.assertEqual(ctl.act(after), rows[266])
            self.assertIsNone(q.plan)
            self.assertTrue(q.disabled)

    def test_observed_land_check_runs_without_worker_entry(self):
        state, _ = world()
        obs = copy.deepcopy(state[0].observation); obs['step'] += 1
        q = pending(M, action()); q.plan = q.pending; q.pending = None
        variant = {'worker_days': [], 'bundle': {'land': {'step': 264}, 'target_quadrant': 'SE'}}
        rows = [action() for _ in range(720)]
        self.assertFalse(q._physical_match(obs, rows, variant))
        obs['farms'][0]['unlocked_quadrants'].append('SE')
        self.assertFalse(q._physical_match(obs, rows, variant))
        obs['farms'][0]['tiles'][5][5] = None
        self.assertTrue(q._physical_match(obs, rows, variant))

    def test_before_and_at_purchase_no_premature_land_rejection(self):
        state, _ = world()
        q = pending(M, action()); q.plan = q.pending; q.pending = None
        variant = {'worker_days': [], 'bundle': {'land': {'step': 266}, 'target_quadrant': 'SE'}}
        for now in (264, 265, 266):
            obs = copy.deepcopy(state[0].observation); obs['step'] = now
            self.assertTrue(q._physical_match(obs, [action() for _ in range(720)], variant))

    def test_land_acquired_does_not_skip_existing_worker_guard(self):
        state, env = world()
        obs = copy.deepcopy(state[0].observation)
        q, ctl = installed(M, obs, env.configuration)
        first = ctl.act(obs); q.finish(obs, first)
        after = tick(state, env, 0, first)
        after['farms'][0]['hands'][0] = [9, 9]
        self.assertEqual(ctl.act(after), action())
        self.assertTrue(q.disabled)

    def test_reconstruction_preserves_committed_acquisition_check(self):
        state, env = world(money=500)
        obs = copy.deepcopy(state[0].observation)
        q, ctl = installed(M, obs, env.configuration)
        first = ctl.act(obs); q.finish(obs, first)
        after = tick(state, env, 0, first)
        fresh = RowController(); q.install(fresh)
        self.assertEqual(fresh.act(after), action())
        self.assertTrue(q.disabled)

    def test_rejected_pending_does_not_leak_into_repeated_or_next_callback(self):
        state, env = world()
        obs = copy.deepcopy(state[0].observation)
        q, ctl = installed(M, obs, env.configuration)
        first = ctl.act(obs)
        q.finish(obs, action())
        q.finish(obs, first)
        self.assertIsNone(q.plan)
        self.assertEqual(ctl.act(obs), action())
        self.assertIsNone(q.pending)
        self.assertEqual(q.generation, 0)

    def test_none_malformed_and_bad_configuration_fail_closed_clear_pending(self):
        state, _ = world(); obs = copy.deepcopy(state[0].observation)
        for returned in (None, [], {}, {'farmer': None}, {'hands': None}, {'market': None}, {'market': 'HIRE'}):
            with self.subTest(returned=returned):
                q = pending(M, action([['BUY_LAND']]))
                q.finish(obs, returned)
                self.assertIsNone(q.plan); self.assertIsNone(q.pending); self.assertIsNone(q.selected)
        for cap in (None, float('nan'), float('inf'), 'bad'):
            with self.subTest(cap=repr(cap)):
                q = pending(M, action([['BUY_LAND']]), cap)
                q.finish(obs, action([['BUY_LAND']]))
                self.assertIsNone(q.plan); self.assertIsNone(q.pending); self.assertIsNone(q.selected)

    def test_bad_step_consumes_pending_without_overwriting_committed_plan(self):
        for obs in ({}, {'step': None}, {'step': float('nan')}, {'step': float('inf')}, {'step': 'bad'}):
            q = pending(M, action())
            previous = {'existing': True}; q.plan = previous
            q.finish(obs, action())
            self.assertIs(q.plan, previous)
            self.assertIsNone(q.pending); self.assertIsNone(q.selected)

    def test_disabled_and_no_admission_route_output_is_unchanged(self):
        state, env = world()
        obs = copy.deepcopy(state[0].observation)
        rows = [action([['SELL', 'MILK', 1]], hands=[['PASS']]) for _ in range(720)]
        for disabled in (False, True):
            q = M.FourthQuadrant(E, None); q.configure(env.configuration); q.disabled = disabled
            ctl = RowController(rows); q.install(ctl)
            for now in (264, 265, 287, 288, 500, 718):
                obs['step'] = now
                outgoing = ctl.act(obs); q.finish(obs, outgoing)
                self.assertEqual(outgoing, rows[now])
                self.assertIsNone(q.plan); self.assertEqual(q.events, [])

    def test_two_player_instances_are_independent(self):
        state, _ = world()
        q0 = pending(M, action([['BUY_LAND']]))
        q1 = pending(M, action([['BUY_LAND']]))
        q0.finish(copy.deepcopy(state[0].observation), action([['PASS']]))
        q1.finish(copy.deepcopy(state[1].observation), action([['BUY_LAND']]))
        self.assertIsNone(q0.plan); self.assertIsNotNone(q1.plan)
        self.assertEqual(q0.events, []); self.assertEqual(len(q1.events), 1)

    def test_funded_full_current_day_has_identical_actions_and_states(self):
        for seat in (0, 1):
            a, env_a = world(seat)
            b, env_b = copy.deepcopy((a, env_a))
            qa, ca = installed(ORIGINAL, copy.deepcopy(a[seat].observation), env_a.configuration)
            qb, cb = installed(M, copy.deepcopy(b[seat].observation), env_b.configuration)
            for _ in range(24):
                oa = copy.deepcopy(a[seat].observation); ob = copy.deepcopy(b[seat].observation)
                aa, ab = ca.act(oa), cb.act(ob)
                self.assertEqual(aa, ab)
                qa.finish(oa, aa); qb.finish(ob, ab)
                tick(a, env_a, seat, aa); tick(b, env_b, seat, ab)
                self.assertEqual(a, b)
                self.assertEqual(qa.events, qb.events)
            COUNTS['continuation_worlds'] += 1

    def test_unfilled_land_finite_49_callback_witness(self):
        for seat in (0, 1):
            a, env_a = world(seat, money=500)
            b, env_b = copy.deepcopy((a, env_a))
            qa, ca = installed(ORIGINAL, copy.deepcopy(a[seat].observation), env_a.configuration)
            qb, cb = installed(M, copy.deepcopy(b[seat].observation), env_b.configuration)
            differences = []
            for _ in range(49):
                oa = copy.deepcopy(a[seat].observation); ob = copy.deepcopy(b[seat].observation)
                aa, ab = ca.act(oa), cb.act(ob)
                if aa != ab: differences.append(oa['step'])
                qa.finish(oa, aa); qb.finish(ob, ab)
                tick(a, env_a, seat, aa); tick(b, env_b, seat, ab)
            old, new = a[seat].observation, b[seat].observation
            self.assertNotIn('SE', old.farms[seat]['unlocked_quadrants'])
            self.assertNotIn('SE', new.farms[seat]['unlocked_quadrants'])
            self.assertEqual(old.farms[seat]['tiles'], new.farms[seat]['tiles'])
            self.assertEqual(old.private['shed'], new.private['shed'])
            self.assertEqual(old.private['seeds'], new.private['seeds'])
            self.assertEqual(old.farms[1-seat], new.farms[1-seat])
            self.assertGreater(new.farms[seat]['money'], old.farms[seat]['money'])
            self.assertTrue(qb.disabled)
            self.assertEqual(differences[0], 265)
            WITNESSES.append({'seat': seat, 'callbacks': 49, 'first_difference': differences[0],
                'original_cash': old.farms[seat]['money'], 'repaired_cash': new.farms[seat]['money'],
                'delta_cash': new.farms[seat]['money']-old.farms[seat]['money'],
                'difference_count': len(differences), 'scope': 'constructed_unfunded_bundle_not_field_EV'})
            COUNTS['continuation_worlds'] += 1

    def test_composer_source_drift_and_preserved_nonmethods(self):
        original = (PACKAGE / 'fourth_quadrant.py').read_bytes()
        expected = compose(original)
        for bad in (original + b'\n', original.replace(b"'NW'", b"'ZZ'", 1), expected):
            with self.assertRaises(ValueError): compose(bad)
        def outside(source):
            tree = ast.parse(source)
            for cls in tree.body:
                if isinstance(cls, ast.ClassDef) and cls.name == 'FourthQuadrant':
                    cls.body = [n for n in cls.body if not isinstance(n, ast.FunctionDef)
                                or n.name not in {'finish', '_physical_match', '_returned_commit_matches'}]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(outside(original), outside(expected))
        self.assertEqual(ORIGINAL.proposals.__code__.co_code, M.proposals.__code__.co_code)

    def test_cli_exclusive_output_and_exact_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out.py'
            cmd = [sys.executable] + (['-O'] if sys.flags.optimize else []) + [str(Path(__file__).with_name('compose.py')),
                   str(PACKAGE / 'fourth_quadrant.py'), str(out)]
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(out.read_bytes(), compose((PACKAGE / 'fourth_quadrant.py').read_bytes()))
            old = out.read_bytes()
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(out.read_bytes(), old)
            out.unlink(); out.symlink_to(PACKAGE / 'fourth_quadrant.py')
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(git_blob((PACKAGE / 'fourth_quadrant.py').read_bytes()), PREIMAGE)


def main():
    global PACKAGE, L, E, M, ORIGINAL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--target-source', type=Path, help='Negative-control source; normal target is compose(native).')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    PACKAGE = args.package.resolve()
    for name, pin in PINS.items():
        file = PACKAGE / name
        if not file.is_file() or git_blob(file.read_bytes()) != pin:
            parser.exit(2, 'missing or mismatched pinned dependency: ' + name + '\n')
    L = load_module('landreturn_pinned_loader', PACKAGE / 'checks/reference/evaluator/loader.py')
    E, _ = L.get_engine(PACKAGE / 'checks/reference/engine')
    source = (PACKAGE / 'fourth_quadrant.py').read_bytes()
    ORIGINAL = from_bytes('landreturn_original', source)
    candidate = args.target_source.read_bytes() if args.target_source else compose(source)
    M = from_bytes('landreturn_test_target', candidate)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LandReturnTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'source_pins': PINS, 'target_blob': git_blob(candidate), 'optimization': sys.flags.optimize,
              'test_blob': git_blob(Path(__file__).read_bytes()),
              'composer_blob': git_blob(Path(__file__).with_name('compose.py').read_bytes()),
              'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'counts': COUNTS, 'witnesses': WITNESSES,
              'scope': 'actual native FourthQuadrant/proposals + pinned full interpreter; authored-row controller and admission chooser; not full Titan/economic admission/field promotion'}
    if args.receipt:
        args.receipt.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
