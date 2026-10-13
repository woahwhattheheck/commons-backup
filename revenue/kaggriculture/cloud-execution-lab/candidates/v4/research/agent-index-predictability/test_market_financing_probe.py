"""Source-pinned real-interpreter tests. No hosted games or policy EV is asserted."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest

import market_financing_probe as p

HERE = Path(__file__).resolve().parent
DEFAULT_LAB = HERE.parents[3] if len(HERE.parents) > 3 else Path.cwd()
LAB = Path(os.environ.get('TITAN_FINANCING_LAB', str(DEFAULT_LAB)))
PRESSURE = Path(os.environ.get('TITAN_FINANCING_PRESSURE',
    str(LAB.parent / 'cloud-opponent-league/lark-responsive/pressure_priority.py')))


class FinancingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = p.load_context(LAB, PRESSURE)

    def check_delta(self, result, own, rival, margin):
        self.assertEqual(result['delta']['own']['final_cash'], own)
        self.assertEqual(result['delta']['rival']['final_cash'], rival)
        self.assertEqual(result['delta_cash_margin'], margin)
        self.assertEqual(result['delta_cash_margin'], result['delta_sale_margin'] +
                         result['delta_spend_effect'] + result['delta_other_effect'])
        for arm in ('parent', 'candidate'):
            for who in ('own', 'rival'):
                row = result[arm][who]
                self.assertEqual(row['other_cash'], 0)
                self.assertEqual(row['final_cash'], row['initial_cash'] + row['sales'] - row['spend'])
                self.assertEqual(row['reward'], row['final_cash'])
                self.assertEqual(row['status'], 'DONE')

    def test_01_land_threshold_flips_terminal_winner_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                r = p.pressure_pair(self.ctx, seat=seat)
                self.check_delta(r, 6, 998, -992)
                self.assertEqual(r['parent']['own']['final_cash'], 310)
                self.assertEqual(r['parent']['rival']['final_cash'], 0)
                self.assertEqual(r['candidate']['own']['final_cash'], 316)
                self.assertEqual(r['candidate']['rival']['final_cash'], 998)
                self.assertEqual(r['delta_sale_margin'], 8)
                self.assertEqual(r['delta_spend_effect'], -1000)
                self.assertEqual(r['parent']['rival']['assets']['quadrants'], ['NW', 'NE'])
                self.assertEqual(r['candidate']['rival']['assets']['quadrants'], ['NW'])

    def test_02_cow_threshold(self):
        for seat in (0, 1):
            r = p.pressure_pair(self.ctx, rival=[['SELL', 'MILK', 2], ['BUY_ANIMAL', 'COW', 1]],
                                cash=(0, 82), seat=seat)
            self.check_delta(r, 6, 398, -392)
            self.assertEqual(r['parent']['rival']['assets']['shed']['COW'], 1)
            self.assertEqual(r['candidate']['rival']['assets']['shed']['COW'], 0)

    def test_03_hire_threshold_and_worker_custody(self):
        cost = self.ctx.engine._hire_cost(13, 1)
        self.assertEqual(cost, 377)
        for seat in (0, 1):
            r = p.pressure_pair(self.ctx, rival=[['SELL', 'MILK', 2], ['HIRE']],
                                cash=(0, cost - 318), seat=seat, hires=13)
            self.check_delta(r, 6, 375, -369)
            self.assertEqual(r['parent']['rival']['assets']['hands'], 14)
            self.assertEqual(r['candidate']['rival']['assets']['hands'], 13)

    def test_04_partial_seed_fill_not_only_atomic_buys(self):
        for seat in (0, 1):
            r = p.pressure_pair(self.ctx, rival=[['SELL', 'MILK', 2], ['BUY_SEED', 'WHEAT', 40]],
                                cash=(0, 82), seat=seat)
            self.check_delta(r, 6, 8, -2)
            self.assertEqual(r['parent']['rival']['assets']['seeds']['WHEAT'], 40)
            self.assertEqual(r['candidate']['rival']['assets']['seeds']['WHEAT'], 39)
            self.assertEqual(r['delta_spend_effect'], -10)

    def test_05_buy_product_partial_fill(self):
        s, env = p.fixture(self.ctx, stock=(0, 0), cash=(0, 100000))
        s[1].action['market'] = [['BUY_PRODUCT', 'FERTILIZER', 40]]
        cost = p.run_action(self.ctx, s, env, 0, s[0].action)['rival']['spend']
        for seat in (0, 1):
            r = p.pressure_pair(self.ctx, rival=[['SELL', 'MILK', 2], ['BUY_PRODUCT', 'FERTILIZER', 40]],
                                cash=(0, cost - 318), seat=seat)
            self.assertLess(r['delta_cash_margin'], 0)
            self.assertEqual(r['parent']['rival']['assets']['shed']['FERTILIZER'], 40)
            self.assertEqual(r['candidate']['rival']['assets']['shed']['FERTILIZER'], 39)
            self.assertEqual(r['delta_sale_margin'], 8)

    def test_06_sale_only_control_is_positive(self):
        for seat in (0, 1):
            r = p.pressure_pair(self.ctx, rival=[['SELL', 'MILK', 2]], cash=(0, 0), seat=seat)
            self.check_delta(r, 6, -2, 8)
            self.assertEqual(r['delta_spend_effect'], 0)

    def test_07_cash_rich_rival_keeps_purchase(self):
        r = p.pressure_pair(self.ctx, cash=(0, 100000))
        self.check_delta(r, 6, -2, 8)
        self.assertEqual(r['parent']['rival']['assets']['quadrants'], r['candidate']['rival']['assets']['quadrants'])

    def test_08_cash_poor_rival_never_purchases(self):
        r = p.pressure_pair(self.ctx, cash=(0, 0))
        self.check_delta(r, 6, -2, 8)
        self.assertEqual(r['parent']['rival']['assets']['quadrants'], ['NW'])
        self.assertEqual(r['candidate']['rival']['assets']['quadrants'], ['NW'])

    def test_09_one_raw_slot_and_engine_clamp_are_identity(self):
        for cap in (1, 0, -1):
            for seat in (0, 1):
                r = p.pressure_pair(self.ctx, cap=cap, seat=seat)
                self.assertFalse(r['changed'])
                self.check_delta(r, 0, 0, 0)
                self.assertEqual(r['parent']['poststate_sha256'], r['candidate']['poststate_sha256'])

    def test_10_two_ten_and_twelve_raw_slots_keep_counterexample(self):
        for cap in (2, 10, 12):
            for seat in (0, 1):
                self.check_delta(p.pressure_pair(self.ctx, cap=cap, seat=seat), 6, 998, -992)

    def test_11_rival_dead_suffix_cannot_purchase(self):
        rows = [['SELL', 'MILK', 2]] + [[] for _ in range(9)] + [['BUY_LAND']]
        for seat in (0, 1):
            short = p.pressure_pair(self.ctx, rival=rows, cap=10, seat=seat)
            long = p.pressure_pair(self.ctx, rival=rows, cap=12, seat=seat)
            self.check_delta(short, 6, -2, 8)
            self.check_delta(long, 6, 998, -992)

    def test_12_floor_lockstep_changes_inventory_but_not_sale_claim(self):
        for seat in (0, 1):
            r = p.pressure_pair(self.ctx, inventory=10075, cash=(0, 0),
                                rival=[['SELL', 'MILK', 2]], seat=seat)
            self.check_delta(r, 2, 0, 2)
            self.assertEqual(r['parent']['own']['sales'], 2)
            self.assertEqual(r['candidate']['own']['sales'], 4)
            self.assertNotEqual(r['parent']['poststate_sha256'], r['candidate']['poststate_sha256'])

    def test_13_flat_floor_declines_pressure_compaction(self):
        r = p.pressure_pair(self.ctx, inventory=11000)
        self.assertFalse(r['changed'])
        self.check_delta(r, 0, 0, 0)

    def test_14_partial_stock_preserves_authored_quantities(self):
        rows = [[], ['SELL', 'MILK', 5]]
        for seat in (0, 1):
            r = p.pressure_pair(self.ctx, own=rows, rival=[['SELL', 'MILK', 5]],
                                stock=(3, 3), cash=(0, 0), seat=seat)
            self.assertEqual(r['candidate_action']['market'], [rows[1], []])
            for arm in ('parent', 'candidate'):
                for who in ('own', 'rival'):
                    fills = sum(x['ok'] for x in r[arm][who]['events'] if x['op'] == 'SELL')
                    self.assertEqual(fills, 3)
            self.assertGreaterEqual(r['delta_cash_margin'], 0)

    def test_15_zero_fill_is_not_fake_revenue(self):
        r = p.pressure_pair(self.ctx, stock=(0, 2))
        self.assertTrue(r['changed'])
        self.check_delta(r, 0, 0, 0)
        self.assertEqual(r['parent']['own']['sales'], 0)

    def test_16_own_economic_barrier_is_identity(self):
        for barrier in (['HIRE'], ['BUY_LAND'], ['BUY_SEED', 'WHEAT', 1]):
            r = p.pressure_pair(self.ctx, own=[[], ['SELL', 'MILK', 2], barrier])
            self.assertFalse(r['changed'])
            self.check_delta(r, 0, 0, 0)

    def test_17_input_state_env_and_candidate_untouched(self):
        state, env = p.fixture(self.ctx)
        state[0].action['market'] = [[], ['SELL', 'MILK', 2]]
        state[1].action['market'] = [['SELL', 'MILK', 2], ['BUY_LAND']]
        action = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'MILK', 2], []]}
        before = copy.deepcopy((state, env, action))
        p.compare_actions(self.ctx, state, env, 0, action)
        self.assertEqual((state, env, action), before)

    def test_18_wrappers_restore_even_when_engine_raises(self):
        engine = self.ctx.engine
        names = ('_commit_unit', '_do_hire', '_do_buy_land')
        original = {name: getattr(engine, name) for name in names}
        def boom(*args, **kwargs):
            raise RuntimeError('intentional test failure')
        state, env = p.fixture(self.ctx)
        state[0].action['market'] = [['SELL', 'MILK', 1]]
        engine._commit_unit = boom
        try:
            with self.assertRaisesRegex(RuntimeError, 'intentional'):
                p.run_action(self.ctx, state, env, 0, state[0].action)
            self.assertIs(engine._commit_unit, boom)
            self.assertIs(engine._do_hire, original['_do_hire'])
            self.assertIs(engine._do_buy_land, original['_do_buy_land'])
        finally:
            for name, fn in original.items():
                setattr(engine, name, fn)

    def test_19_instrumentation_matches_unwrapped_whole_interpreter(self):
        operations = [['HIRE'], ['BUY_LAND'], ['BUY_ANIMAL', 'COW', 1],
                      ['BUY_PRODUCT', 'FERTILIZER', 40], ['BUY_SEED', 'WHEAT', 40], ['SELL', 'MILK', 1]]
        for seat in (0, 1):
            for step in (23, 718):
                for op in operations:
                    state, env = p.fixture(self.ctx, cash=(2000, 2000), seat=seat, step=step)
                    state[seat].action['market'] = [['SELL', 'MILK', 2]]
                    state[1 - seat].action['market'] = [op]
                    recorded = p.run_action(self.ctx, state, env, seat, state[seat].action)
                    direct, direct_env = copy.deepcopy((state, env))
                    self.ctx.engine.interpreter(direct, direct_env)
                    self.assertEqual(recorded['poststate_sha256'], p.digest(p.snapshot(direct)))
                    self.assertEqual(recorded['own']['other_cash'], 0)
                    self.assertEqual(recorded['rival']['other_cash'], 0)

    def test_20_source_pins_and_global_import_restoration(self):
        names = ('kaggle_environments', 'kaggle_environments.utils', 'kag_eval_existing_loader')
        absent = object()
        before = {name: sys.modules.get(name, absent) for name in names}
        ctx = p.load_context(LAB, PRESSURE)
        self.assertEqual({k: v['git_blob'] for k, v in ctx.sources.items()}, p.PINS)
        for name in names:
            self.assertIs(sys.modules.get(name, absent), before[name])

    def test_21_wrong_missing_sources_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in p.PINS:
                src = LAB / name if name.startswith('reference/') else PRESSURE.with_name(name)
                out = root / name
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, out)
            pressure = root / 'pressure_priority.py'
            pressure.write_bytes(pressure.read_bytes() + b'\n# invalid source copy\n')
            with self.assertRaisesRegex(p.ProbeError, 'source pin mismatch'):
                p.load_context(root, pressure)
            pressure.unlink()
            with self.assertRaises(OSError):
                p.load_context(root, pressure)

    def test_22_output_protection_atomic_report_and_nan_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'report.json'
            p.write_report(out, {'value': 1})
            before = out.read_bytes()
            with self.assertRaises(p.ProbeError):
                p.write_report(out, {'value': 2}, [out])
            with self.assertRaises(ValueError):
                p.write_report(out, {'value': float('nan')})
            self.assertEqual(out.read_bytes(), before)
            with self.assertRaises(p.ProbeError):
                p.write_report(Path(d) / 'file.py', {})
            p.write_report(out, {'value': 3})
            self.assertEqual(json.loads(out.read_bytes()), {'value': 3})
            self.assertEqual(list(Path(d).iterdir()), [out])

    def test_23_bad_cli_inputs_preserve_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'report.json'
            out.write_text('old\n')
            with contextlib.redirect_stderr(io.StringIO()):
                code = p.main(['--lab', d, '--pressure', str(PRESSURE), '--output', str(out)])
            self.assertEqual(code, 2)
            self.assertEqual(out.read_text(), 'old\n')
            before = (LAB / 'reference/engine/kaggriculture.json').read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                code = p.main(['--lab', str(LAB), '--pressure', str(PRESSURE),
                               '--output', str(LAB / 'reference/engine/kaggriculture.json')])
            self.assertEqual(code, 2)
            self.assertEqual((LAB / 'reference/engine/kaggriculture.json').read_bytes(), before)

    def test_24_declared_stress_grid_and_operation_controls(self):
        r = p.panel(self.ctx)
        self.assertEqual(r['counts'], {'pairs': 2220, 'changed': 1380, 'cash_negative': 168,
            'cash_zero': 1336, 'cash_positive': 716, 'sale_margin_negative': 0,
            'spend_changed': 174, 'terminal_new_losses': 108,
            'thresholds_skipped_negative_initial_cash': 300})
        self.assertEqual(r['panel_design']['declared_grid_slots'], 2520)
        self.assertEqual(r['counts']['pairs'] + r['counts']['thresholds_skipped_negative_initial_cash'],
                         r['panel_design']['declared_grid_slots'])
        self.assertEqual(set(r['by_operation']), {'HIRE', 'LAND', 'COW', 'SEED', 'INPUT'})
        self.assertTrue(all(x['negative'] > 0 for x in r['by_operation'].values()))
        self.assertEqual(r['land_flip_both_seats']['0']['delta_cash_margin'], -992)
        self.assertEqual(r['land_flip_both_seats']['1']['delta_cash_margin'], -992)
        self.assertEqual(len(r['result_stream_sha256']), 64)


    def test_25_known_broken_variants_are_rejected(self):
        source = Path(p.__file__).read_text()
        variants = (
            ('sales-not-cash', "cash_margin = delta['own']['final_cash'] - delta['rival']['final_cash']", "cash_margin = sale_margin", 'test_01_land_threshold_flips_terminal_winner_both_seats'),
            ('spend-sign', "spend_effect = delta['rival']['spend'] - delta['own']['spend']", "spend_effect = -delta['rival']['spend'] - delta['own']['spend']", 'test_01_land_threshold_flips_terminal_winner_both_seats'),
            ('mutates-input', 'trial, trial_env = copy.deepcopy((state, env))', 'trial, trial_env = state, env', 'test_17_input_state_env_and_candidate_untouched'),
            ('omits-spending', "spend = -sum(event['cash_delta'] for event in own_events if event['op'] != 'SELL')", 'spend = 0.0', 'test_01_land_threshold_flips_terminal_winner_both_seats'),
            ('accepts-wrong-source', 'if actual != expected:', 'if False:', 'test_21_wrong_missing_sources_fail_before_execution'),
            ('leaks-engine-wrappers', 'setattr(e, name, original)', 'pass', 'test_18_wrappers_restore_even_when_engine_raises'),
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, old, new, target in variants:
                self.assertEqual(source.count(old), 1, name)
                changed = source.replace(old, new)
                compile(changed, name, 'exec')
                (root / 'market_financing_probe.py').write_text(changed)
                (root / 'test_market_financing_probe.py').write_bytes(Path(__file__).read_bytes())
                shutil.rmtree(root / '__pycache__', ignore_errors=True)
                for optimized in (False, True):
                    with self.subTest(mutant=name, optimized=optimized):
                        cmd = [sys.executable] + (['-O'] if optimized else [])
                        cmd += ['-m', 'unittest', 'test_market_financing_probe.FinancingTests.' + target]
                        env = dict(os.environ, PYTHONPATH=str(root),
                                   TITAN_FINANCING_LAB=str(LAB.resolve()),
                                   TITAN_FINANCING_PRESSURE=str(PRESSURE.resolve()))
                        run = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=15)
                        self.assertEqual(run.returncode, 1, (name, run.stderr))
                        self.assertIn('Ran 1 test', run.stderr)
                        self.assertIn('FAILED', run.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
