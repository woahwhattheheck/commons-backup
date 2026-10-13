# SPDX-License-Identifier: Apache-2.0
"""Run with TITAN_ENGINE_DIR and TITAN_V4_OVERLAY pointing to pinned sources."""
import copy
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

import eod_market_externality as probe


class ExternalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine_dir = Path(os.environ['TITAN_ENGINE_DIR'])
        cls.overlay_dir = Path(os.environ['TITAN_V4_OVERLAY'])
        cls.h = probe.Harness(cls.engine_dir, cls.overlay_dir)
        cls.pins_before = copy.deepcopy(cls.h.sources)

    def certificate_args(self, cell):
        market = self.h.engine._new_market()
        market['inventory'][cell['product']] = cell['public_inventory']
        self.h.engine._refresh_prices(market)
        return (self.h.engine, {'market': market}, cell['parent_action'],
                cell['candidate_action'], {'shedCapacity': 100, 'maxMarketOrdersPerTurn': 10})

    def test_source_pins_and_full_engine(self):
        self.assertEqual(set(self.h.sources), set(probe.PINS))
        self.assertEqual(self.h.sources['kaggriculture.py']['bytes'], 40356)
        self.assertTrue(callable(self.h.engine.interpreter))
        self.assertEqual(tuple(self.h.engine.PRODUCTS), self.h.constants.PRODUCTS)
        for name, entry in self.h.sources.items():
            self.assertEqual(entry['git_blob'], probe.PINS[name])

    def test_near_floor_subsidy_both_seats(self):
        for seat in (0, 1):
            c = self.h.pair(seat=seat)
            self.assertEqual(c['observed_price'], 1)
            self.assertEqual((c['delta_own'], c['delta_rival'], c['delta_margin']), (15, 131, -116))
            self.assertEqual(c['private_equal'], [True, True])
            self.assertFalse(c['market_equal'])
            self.assertFalse(c['certificate']['certified'])

    def test_single_unit_floor_is_safe_before_rival_first_withdrawal(self):
        for seat in (0, 1):
            c = self.h.pair(seat=seat, quantity=1)
            self.assertTrue(c['certificate']['certified'])
            self.assertEqual((c['delta_own'], c['delta_rival'], c['delta_margin']), (1, 0, 1))
            self.assertTrue(c['market_equal'])

    def test_exact_quantity_boundary_and_one_below(self):
        for inventory, expected in ((10499, False), (10500, True)):
            c = self.h.pair(inventory=inventory)
            self.assertEqual(c['certificate']['certified'], expected)
            self.assertEqual(c['certificate']['rows'][0]['withdrawal_bound'], 7)
        c = self.h.pair(inventory=10500)
        self.assertEqual((c['delta_own'], c['delta_rival']), (8, 0))

    def test_raw_prior_slots_are_not_filtered_out(self):
        c = self.h.pair(inventory=10500, slot=1)
        self.assertEqual(c['parent_action']['market'], [[]])
        self.assertFalse(c['certificate']['certified'])
        self.assertEqual(c['certificate']['rows'][0]['withdrawal_bound'], 107)
        self.assertFalse(c['market_equal'])
        deep = self.h.pair(inventory=11400, slot=9, rival_kind='roundtrip')
        self.assertTrue(deep['certificate']['certified'])
        self.assertEqual(deep['certificate']['rows'][0]['withdrawal_bound'], 907)
        self.assertEqual((deep['delta_own'], deep['delta_rival']), (8, 0))

    def test_nonbuyable_products_cannot_have_rival_withdrawals(self):
        for product in ('MILK', 'STRAWBERRY'):
            for rival_kind in ('sell100', 'buy100'):
                c = self.h.pair(product=product, inventory=12000, slot=9, rival_kind=rival_kind)
                self.assertTrue(c['certificate']['certified'])
                self.assertEqual(c['certificate']['rows'][0]['withdrawal_bound'], 0)
                self.assertEqual(c['delta_rival'], 0)
        # BUY_PRODUCT MILK is an explicit nonexecuting control, NOT purchase engagement.
        c = self.h.pair(product='MILK', inventory=12000, rival_kind='buy100')
        self.assertEqual(c['off_cash'], [1000000, 1000000])

    def test_mixed_vector_and_all_or_nothing_slot_budget(self):
        args = {'inventory': 11400, 'quantity': 8,
                'shed': {'FERTILIZER': 50, 'MILK': 50},
                'cargo': [{'FERTILIZER': 8}, {'MILK': 2}]}
        c = self.h.pair(**args)
        self.assertEqual(c['candidate_action']['market'], [['SELL', 'FERTILIZER', 8], ['SELL', 'MILK', 2]])
        self.assertEqual(c['private_equal'], [True, True])
        self.assertFalse(c['certificate']['certified'])  # MILK's default quote is not floor.
        full = self.h.pair(slot=9, **args)
        self.assertFalse(full['active'])
        self.assertEqual(full['delta_margin'], 0)

    def test_certificate_rejects_malformed_or_noncomposed_inputs(self):
        base = self.certificate_args(self.h.pair(inventory=11400))
        corruptions = [
            (3, lambda x: x['market'][0].__setitem__(2, True)),
            (3, lambda x: x['market'][0].__setitem__(2, 0)),
            (3, lambda x: x['market'][0].__setitem__(2, 101)),
            (3, lambda x: x['market'][0].__setitem__(1, [])),
            (3, lambda x: x['farmer'].__setitem__(0, 'HARVEST')),
            (3, lambda x: x['market'].extend([['SELL', 'FERTILIZER', 1]])),
            (4, lambda x: x.__setitem__('shedCapacity', True)),
            (4, lambda x: x.__setitem__('maxMarketOrdersPerTurn', 11)),
            (1, lambda x: x['market']['inventory'].__setitem__('FERTILIZER', '11400')),
        ]
        for index, mutate in corruptions:
            args = [base[0], *copy.deepcopy(base[1:])]
            mutate(args[index])
            self.assertFalse(probe.floor_envelope(*args)['certified'])
        args = [base[0], *copy.deepcopy(base[1:])]
        args[2]['market'] = [['BUY_PRODUCT', 'FERTILIZER', 1]]
        args[3]['market'].insert(0, ['BUY_PRODUCT', 'FERTILIZER', 1])
        self.assertEqual(probe.floor_envelope(*args)['reason'], 'nonneutral_prefix')

    def test_entire_envelope_not_only_endpoints(self):
        c = self.h.pair(inventory=10500)
        args = list(self.certificate_args(c))
        queried = []
        def price(product, inventory, params=None):
            queried.append(inventory)
            return 3 if inventory == 10497 else 1
        args[0] = types.SimpleNamespace(PRODUCTS=self.h.engine.PRODUCTS, market_price=price)
        self.assertFalse(probe.floor_envelope(*args)['certified'])
        self.assertEqual(queried, list(range(10500, 10492, -1)))

    def test_observed_price_is_not_trusted(self):
        c = self.h.pair(inventory=10000)
        args = [self.h.engine, *copy.deepcopy(self.certificate_args(c)[1:])]
        args[1]['market']['prices']['FERTILIZER'] = 1
        self.assertFalse(probe.floor_envelope(*args)['certified'])

    def test_module_bindings_restored_after_success_and_failure(self):
        sentinel = types.ModuleType('externality_sentinel')
        key = '_externality_test_binding_'
        sys.modules[key] = sentinel
        try:
            with self.assertRaises(RuntimeError):
                with probe.module_bindings({key: self.h.constants}):
                    self.assertIs(sys.modules[key], self.h.constants)
                    raise RuntimeError('intentional')
            self.assertIs(sys.modules[key], sentinel)
        finally:
            sys.modules.pop(key, None)

    def test_wrong_source_pin_is_hard_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('r04_eod_capacity_rescue.py', 'h3c_goose_eod_cap_rescue.py'):
                shutil.copyfile(self.overlay_dir / name, root / name)
            path = root / 'r04_eod_capacity_rescue.py'
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'source pin mismatch'):
                probe.Harness(self.engine_dir, root)

    def test_failed_cli_preserves_old_output_and_returns_two(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'report.json'
            output.write_text('old-output', encoding='utf-8')
            command = [sys.executable, '-B'] + (['-O'] if sys.flags.optimize else [])
            command += [str(Path(probe.__file__)), '--engine-dir', str(self.engine_dir),
                        '--overlay-dir', temp, '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(), 'old-output')
            self.assertEqual(result.stdout, '')

    def test_six_semantic_mutants_rejected(self):
        source = inspect.getsource(probe.floor_envelope)
        changes = {
            'current_quote_only': ('cap * slot + quantity - 1 if product in BUYABLE_PRODUCTS else 0', '0'),
            'ignore_prior_raw_slots': ('cap * slot + quantity - 1', 'quantity - 1'),
            'ignore_concurrent_quantity': ('cap * slot + quantity - 1', 'cap * slot'),
            'fert_not_buyable': ('product in BUYABLE_PRODUCTS', "product in ('WHEAT',)"),
            'trust_observed_quote': ('engine.market_price(product, inventory - d, market.get(\'params\'))', "market['prices'][product]"),
            'floor_two': ("== 1 for row in rows", "<= 2 for row in rows"),
        }
        cells = [self.h.pair(inventory=10493), self.h.pair(inventory=10500, slot=1),
                 self.h.pair(inventory=10492, quantity=1)]
        for name, (old, new) in changes.items():
            with self.subTest(mutant=name):
                self.assertIn(old, source)
                ns = dict(vars(probe))
                exec(compile(source.replace(old, new), '<deliberately-broken-certificate>', 'exec'), ns)
                false_certificates = [c for c in cells if ns['floor_envelope'](*self.certificate_args(c))['certified']
                                      and (not c['market_equal'] or c['delta_rival'] != 0)]
                self.assertTrue(false_certificates, name)

    def test_complete_declared_grid_has_no_certificate_false_positive(self):
        report = probe.run_matrix(self.h)
        self.assertEqual(report['cells'], 1080)
        self.assertEqual(report['negative_margin_cells'], 80)
        self.assertEqual(report['certified_cells'], 460)
        self.assertEqual(report['worst_delta_margin'], -314)
        self.assertEqual(report['certified_false_positives'], 0)
        self.assertEqual({c['seat'] for c in report['cases']}, {0, 1})
        self.assertTrue(all(c['delta_margin'] == c['delta_own'] - c['delta_rival'] for c in report['cases']))
        for cell in report['cases']:
            if cell['certificate']['certified']:
                self.assertTrue(cell['market_equal'])
                self.assertEqual(cell['delta_rival'], 0)
                self.assertEqual(cell['delta_margin'], cell['quantity'])

    def test_sources_not_mutated(self):
        fresh = probe.Harness(self.engine_dir, self.overlay_dir)
        self.assertEqual(fresh.sources, self.pins_before)


if __name__ == '__main__':
    unittest.main()
