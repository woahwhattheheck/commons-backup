# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import build_productive_expansion as builder
import p01_productive_expansion_gate as gate
import publication_custody


def fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def noisy_day_factory(parent_hires=20, hand_noise=99):
    def native_day(native, day):
        return [{
            'market': [['HIRE'] for _ in range(parent_hires)],
            'hands': [['PASS'] for _ in range(hand_noise)],
        }]
    return native_day


def obs(hires_today=0, price=70, inventory=10000, rival_tiles=None):
    own = {'hires_today': hires_today, 'tiles': [[None]]}
    rival = {'hires_today': 0, 'tiles': [rival_tiles or [None]]}
    return {
        'player': 0,
        'step': 432,
        'farms': [own, rival],
        'market': {'inventory': {'TOMATO': inventory}, 'prices': {'TOMATO': price}},
    }


class ProductiveExpansionGate(unittest.TestCase):
    def test_first_two_fresh_day_hires_cost_two(self):
        self.assertEqual(gate.incremental_hire_cost(0, 0, 2, fib), 2)

    def test_same_action_parent_hire_shifts_only_same_day_append(self):
        self.assertEqual(gate.incremental_hire_cost(0, 1, 2, fib), 3)

    def test_fourth_same_day_hire_costs_fib_three(self):
        self.assertEqual(gate.incremental_hire_cost(3, 0, 1, fib), fib(3))
        self.assertEqual(fib(3), 3)

    def test_many_authored_future_hires_do_not_inflate_telemetry_floor(self):
        labor, by_day = gate.route_labor_cost_floor(
            obs(hires_today=0), object(), noisy_day_factory(parent_hires=30), fib
        )
        self.assertEqual(labor, 2)
        self.assertEqual(by_day, {18: 2})

    def test_future_days_are_not_consulted_by_telemetry_floor(self):
        calls = []
        def day18_only(native, day):
            calls.append(day)
            if day != 18:
                raise AssertionError('future conditional route spend is not floor telemetry')
            return [{'market': [], 'hands': []}]
        labor, by_day = gate.route_labor_cost_floor(
            obs(hires_today=0), object(), day18_only, fib
        )
        self.assertEqual(labor, 2)
        self.assertEqual(by_day, {18: 2})
        self.assertEqual(calls, [18])

    def test_large_standing_work_width_does_not_set_fibonacci_index(self):
        clean = gate.route_labor_cost_floor(
            obs(), object(), noisy_day_factory(parent_hires=0, hand_noise=0), fib
        )[0]
        noisy = gate.route_labor_cost_floor(
            obs(), object(), noisy_day_factory(parent_hires=0, hand_noise=200), fib
        )[0]
        self.assertEqual(clean, noisy)
        self.assertEqual(clean, 2)

    def test_current_hires_today_affects_only_day18_floor(self):
        labor, by_day = gate.route_labor_cost_floor(
            obs(hires_today=3), object(), noisy_day_factory(), fib
        )
        self.assertEqual(by_day, {18: fib(3) + fib(4)})
        self.assertEqual(by_day[18], 8)
        self.assertEqual(labor, 8)

    def test_flat_seventy_is_telemetry_only(self):
        record = gate.evaluate(
            obs(hires_today=0, price=70),
            object(),
            noisy_day_factory(),
            fib,
            lambda item, inv: 70,
        )
        self.assertIsNone(record['decision'])
        self.assertEqual(record['reason'], 'seed_purchase_completion_unproven')
        self.assertFalse(record['full_seed_purchase_authenticated'])
        self.assertEqual(record['labor_cost_floor'], 2)
        self.assertEqual(record['labor_cost_floor_by_day'], {18: 2})
        self.assertEqual(record['proven_land_cost_floor'], 4000)
        self.assertEqual(record['proven_min_seed_cost_floor'], 50)
        self.assertEqual(record['fixed_cost_floor'], 4050)
        self.assertEqual(record['unavoidable_cost_floor'], 4052)
        self.assertEqual(record['gross_revenue_upper_bound'], 5600)
        self.assertFalse(record['negative_payback_telemetry'])

    def test_high_observed_ordinal_cannot_reject_without_seed_completion_proof(self):
        record = gate.evaluate(
            obs(hires_today=15, price=70),
            object(),
            noisy_day_factory(),
            fib,
            lambda item, inv: 70,
        )
        self.assertIsNone(record['decision'])
        self.assertEqual(record['reason'], 'seed_purchase_completion_unproven')
        self.assertFalse(record['full_seed_purchase_authenticated'])
        self.assertTrue(record['negative_payback_telemetry'])
        self.assertEqual(record['labor_cost_floor'], 2584)
        self.assertEqual(record['fixed_cost_floor'], 4050)
        self.assertEqual(record['unavoidable_cost_floor'], 6634)
        self.assertEqual(record['gross_revenue_upper_bound'], 5600)

    def test_visible_rival_field_is_telemetry_not_decision_authority(self):
        curve = lambda item, inv: max(1, 130 - max(0, inv - 10000))
        clean = gate.evaluate(
            obs(price=130), object(), noisy_day_factory(), fib, curve
        )
        rival = {'crop': 'TOMATO', 'planted_day': 12, 'yield_units': 3}
        crowded = gate.evaluate(
            obs(price=130, rival_tiles=[rival]),
            object(),
            noisy_day_factory(),
            fib,
            curve,
        )
        self.assertEqual(crowded['visible_rival_field_projection'], 11)
        self.assertEqual(
            clean['gross_revenue_upper_bound'],
            crowded['gross_revenue_upper_bound'],
        )
        self.assertIsNone(clean['decision'])
        self.assertIsNone(crowded['decision'])
        self.assertGreater(
            clean['modeled_gross_visible_field'],
            crowded['modeled_gross_visible_field'],
        )

    def test_custom_curve_passthrough_is_identity_safe(self):
        record = gate.evaluate(
            obs(price=130),
            object(),
            noisy_day_factory(),
            fib,
            lambda item, inv: 129,
        )
        self.assertIsNone(record['decision'])
        self.assertEqual(record['reason'], 'custom_market_curve')

    def test_future_floor_quote_below_current_passthrough(self):
        def curve(item, inv):
            return 60 if inv < 10000 else 70
        record = gate.evaluate(
            obs(price=70), object(), noisy_day_factory(), fib, curve
        )
        self.assertIsNone(record['decision'])
        self.assertEqual(record['reason'], 'unsupported_market_curve')

    def test_town_drain_below_zero_is_included_in_gross_ceiling(self):
        def scarcity_curve(item, inv):
            return 70 + max(0, 1000 - inv)
        record = gate.evaluate(
            obs(hires_today=24, price=70, inventory=1000),
            object(),
            noisy_day_factory(),
            fib,
            scarcity_curve,
        )
        self.assertEqual(record['future_inventory_floor'], -3896)
        self.assertEqual(record['future_tomato_quote_ceiling'], 4966)
        self.assertEqual(record['gross_revenue_upper_bound'], 397280)
        self.assertEqual(record['labor_cost_floor'], 196418)
        self.assertEqual(record['unavoidable_cost_floor'], 200468)
        self.assertIsNone(record['decision'])
        self.assertEqual(record['reason'], 'seed_purchase_completion_unproven')

    def test_market_param_override_passthrough(self):
        observation = obs()
        observation['market']['params'] = {'TOMATO': {'base': 999}}
        record = gate.evaluate(
            observation, object(), noisy_day_factory(), fib, lambda item, inv: 70
        )
        self.assertIsNone(record['decision'])
        self.assertEqual(record['reason'], 'custom_market_params')

    def test_missing_hires_today_passthrough(self):
        observation = obs()
        observation['farms'][0].pop('hires_today')
        record = gate.evaluate(
            observation,
            object(),
            noisy_day_factory(),
            fib,
            lambda item, inv: 70,
        )
        self.assertIsNone(record['decision'])
        self.assertEqual(record['reason'], 'unsupported_route_state')

    def test_wrapper_is_structurally_telemetry_only(self):
        self.assertIn(b"record['decision'] is not None", builder.WRAPPER)
        self.assertNotIn(b"record['decision'] is False", builder.WRAPPER)
        self.assertNotIn(b"_V219_REPORT['p01_payback_rejects'] +=", builder.WRAPPER)
        self.assertIn(b'p01_gross_upper_bound', builder.WRAPPER)
        self.assertIn(b'p01_unavoidable_cost_floor', builder.WRAPPER)
        self.assertNotIn(b'p01_gate_accepts', builder.WRAPPER)


class ProductiveExpansionPublication(unittest.TestCase):
    def _receipt(self):
        return {'schema': 'test', 'candidate_archive_sha256': 'abc'}

    def test_preexisting_receipt_reservation_leaves_no_orphan_tar(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); out=root/'out'; tar=root/'candidate.tar.gz'; receipt=root/'out-manifest.json'
            receipt.write_text('sentinel')
            with self.assertRaises(FileExistsError):
                builder._publish({'main.py': b'x'}, b'archive', self._receipt(), out, tar, receipt)
            self.assertFalse(tar.exists())
            self.assertFalse(out.exists())
            self.assertEqual(receipt.read_text(), 'sentinel')

    def test_archive_receipt_alias_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); out=root/'out'; shared=root/'same'
            with self.assertRaisesRegex(ValueError, 'must be distinct'):
                builder._publish({'main.py': b'x'}, b'archive', self._receipt(), out, shared, shared)
            self.assertFalse(shared.exists())
            self.assertFalse(out.exists())

    def test_shared_publication_failure_rolls_back_output_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); out=root/'out'; tar=root/'candidate.tar.gz'; receipt=root/'out-manifest.json'
            with patch.object(publication_custody, 'publish_exclusive', side_effect=OSError('injected shared publication failure')) as shared:
                with self.assertRaisesRegex(OSError, 'injected shared publication failure'):
                    builder._publish({'main.py': b'x'}, b'archive', self._receipt(), out, tar, receipt)
            shared.assert_called_once()
            self.assertFalse(tar.exists())
            self.assertFalse(receipt.exists())
            self.assertFalse(out.exists())

    def test_foreign_output_tree_replacement_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); out=root/'out'; tar=root/'candidate.tar.gz'; receipt=root/'out-manifest.json'
            def replace_tree_and_fail(_pairs):
                shutil.rmtree(out)
                out.mkdir()
                (out/'FOREIGN').write_text('keep', encoding='utf-8')
                raise OSError('injected shared publication failure')
            with patch.object(publication_custody, 'publish_exclusive', side_effect=replace_tree_and_fail):
                with self.assertRaisesRegex(OSError, 'injected shared publication failure'):
                    builder._publish({'main.py': b'x'}, b'archive', self._receipt(), out, tar, receipt)
            self.assertEqual((out/'FOREIGN').read_text(encoding='utf-8'), 'keep')
            self.assertFalse(tar.exists())
            self.assertFalse(receipt.exists())

    def test_foreign_archive_replacement_during_failed_pair_write_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); out=root/'out'; tar=root/'candidate.tar.gz'; receipt=root/'out-manifest.json'
            original = publication_custody._write_all
            writes = 0
            def replace_archive_then_fail(fd, payload):
                nonlocal writes
                writes += 1
                if writes == 2:
                    tar.unlink()
                    tar.write_bytes(b'foreign')
                    raise OSError('injected second write failure')
                return original(fd, payload)
            with patch.object(publication_custody, '_write_all', side_effect=replace_archive_then_fail):
                with self.assertRaisesRegex(OSError, 'injected second write failure'):
                    builder._publish({'main.py': b'x'}, b'archive', self._receipt(), out, tar, receipt)
            self.assertEqual(tar.read_bytes(), b'foreign')
            self.assertFalse(receipt.exists())
            self.assertFalse(out.exists())

    def test_same_inode_payload_mutation_before_verify_rejects_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); out=root/'out'; tar=root/'candidate.tar.gz'; receipt=root/'out-manifest.json'
            original = publication_custody._verify_final
            verifies = 0
            def mutate_archive_before_verify(item):
                nonlocal verifies
                verifies += 1
                if verifies == 1:
                    inode = item.path.stat().st_ino
                    with item.path.open('r+b') as handle:
                        handle.seek(0)
                        handle.write(b'foreign')
                        handle.flush()
                    self.assertEqual(item.path.stat().st_ino, inode)
                return original(item)
            with patch.object(publication_custody, '_verify_final', side_effect=mutate_archive_before_verify):
                with self.assertRaisesRegex(OSError, 'digest mismatch'):
                    builder._publish({'main.py': b'x'}, b'archive', self._receipt(), out, tar, receipt)
            self.assertFalse(tar.exists())
            self.assertFalse(receipt.exists())
            self.assertFalse(out.exists())

    def test_success_delegates_pair_to_shared_publication_custody(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); out=root/'out'; tar=root/'candidate.tar.gz'; receipt=root/'out-manifest.json'
            original = publication_custody.publish_exclusive
            with patch.object(publication_custody, 'publish_exclusive', wraps=original) as shared:
                builder._publish({'main.py': b'x'}, b'archive', self._receipt(), out, tar, receipt)
            shared.assert_called_once()
            self.assertEqual(tar.read_bytes(), b'archive')
            self.assertEqual((out/'main.py').read_bytes(), b'x')
            self.assertEqual(json_load(receipt)['schema'], 'test')


def json_load(path):
    import json
    return json.loads(path.read_text())


if __name__ == '__main__':
    unittest.main()
