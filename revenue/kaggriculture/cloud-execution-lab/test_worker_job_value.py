# SPDX-License-Identifier: Apache-2.0
"""Fail-closed contracts for pure V5 worker-job valuation."""
from __future__ import annotations

import copy
import unittest

import worker_job_value


class WorkerJobValueTests(unittest.TestCase):
    def base(self):
        return dict(
            start_step=100,
            actions=[['EAST'], ['FEED'], ['WATER'], ['HARVEST'], ['WEST'], ['DROP']],
            available_unit_steps=6,
            payback_deadline_step=108,
            required_services={'FEED': 1, 'WATER': 1, 'HARVEST': 1, 'DROP': 1},
            input_requirements=[
                {'item': 'WHEAT', 'quantity': 1, 'needed_step': 101, 'consumer': 'FEED'},
            ],
            owned_inputs={},
            expected_outputs=[
                {'item': 'MILK', 'quantity': 2, 'produced_step': 103,
                 'sale_ready_step': 105},
            ],
            market_events=[
                {'kind': 'input', 'step': 100, 'slot': 4, 'item': 'WHEAT',
                 'quantity': 1, 'cost_upper': 3},
                {'kind': 'sale', 'step': 105, 'slot': 6, 'item': 'MILK',
                 'quantity': 2, 'receipt_floor': 12},
            ],
            free_market_slots={100: {4}, 105: {6}},
            starting_cash=10,
            reserved_cash=4,
            max_market_slots=10,
            minimum_gain=0,
        )

    def test_admits_only_complete_funded_realized_job(self):
        report = worker_job_value.evaluate_worker_job(**self.base())
        self.assertTrue(report['complete'])
        self.assertTrue(report['admitted'])
        self.assertEqual(report['reason'], 'strict_realized_payback')
        self.assertEqual(report['travel_steps'], 2)
        self.assertEqual(report['service_steps'], 4)
        self.assertEqual(report['input_cost'], 3.0)
        self.assertEqual(report['sale_receipt'], 12.0)
        self.assertEqual(report['net_gain'], 9.0)
        self.assertEqual(report['payback_step'], 105)
        self.assertEqual(report['minimum_cash'], 7.0)
        self.assertEqual(report['value_per_step'], 1.5)

    def test_same_step_input_purchase_is_too_late_for_unit_action(self):
        kwargs = self.base()
        kwargs['market_events'][0]['step'] = 101
        kwargs['free_market_slots'] = {101: {4}, 105: {6}}
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'required_input_not_available')

    def test_owned_input_can_cover_consumption_without_a_purchase(self):
        kwargs = self.base()
        kwargs['owned_inputs'] = {'WHEAT': 1}
        kwargs['market_events'] = kwargs['market_events'][1:]
        kwargs['free_market_slots'] = {105: {6}}
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['admitted'])
        self.assertEqual(report['input_cost'], 0.0)
        self.assertEqual(report['net_gain'], 12.0)

    def test_input_quantity_is_consumed_once_across_requirements(self):
        kwargs = self.base()
        kwargs['actions'][2] = ['FEED']
        kwargs['required_services'] = {'FEED': 2, 'HARVEST': 1, 'DROP': 1}
        kwargs['input_requirements'].append(
            {'item': 'WHEAT', 'quantity': 1, 'needed_step': 102, 'consumer': 'FEED'})
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'required_input_not_available')
        self.assertEqual(report['needed_step'], 102)
        self.assertEqual(report['required_quantity'], 2)
        self.assertEqual(report['available_quantity'], 1)

        kwargs['market_events'][0]['quantity'] = 2
        kwargs['market_events'][0]['cost_upper'] = 6
        kwargs['starting_cash'] = 20
        self.assertTrue(worker_job_value.evaluate_worker_job(**kwargs)['admitted'])

    def test_sale_before_explicit_drop_does_not_realize_output(self):
        kwargs = self.base()
        kwargs['market_events'][1]['step'] = 104
        kwargs['free_market_slots'] = {100: {4}, 104: {6}}
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertEqual(report['reason'], 'output_not_realized_in_sale')
        self.assertFalse(report['admitted'])

    def test_sale_quantity_is_consumed_once_across_output_certificates(self):
        kwargs = self.base()
        kwargs['expected_outputs'].append(
            {'item': 'MILK', 'quantity': 2, 'produced_step': 103,
             'sale_ready_step': 105})
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'output_not_realized_in_sale')
        self.assertEqual(report['item'], 'MILK')
        self.assertEqual(report['sale_ready_step'], 105)
        self.assertEqual(report['unmatched_quantity'], 2)

        kwargs['market_events'][1]['quantity'] = 4
        self.assertTrue(worker_job_value.evaluate_worker_job(**kwargs)['admitted'])

    def test_sale_receipt_must_be_fully_attributed_to_outputs(self):
        kwargs = self.base()
        kwargs['market_events'][1]['quantity'] = 3
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'sale_not_attributed_to_output')
        self.assertEqual(report['item'], 'MILK')
        self.assertEqual(report['unmatched_quantity'], 1)

        kwargs = self.base()
        kwargs['market_events'].append(
            {'kind': 'sale', 'step': 106, 'slot': 7, 'item': 'WHEAT',
             'quantity': 1, 'receipt_floor': 100})
        kwargs['free_market_slots'][106] = {7}
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'sale_not_attributed_to_output')
        self.assertEqual(report['item'], 'WHEAT')
        self.assertEqual(report['unmatched_quantity'], 1)

    def test_uncertified_market_slot_fails_closed(self):
        kwargs = self.base()
        kwargs['free_market_slots'] = {100: {4}, 105: {5}}
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'market_slot_not_certified_free')
        self.assertEqual((report['step'], report['slot']), (105, 6))

    def test_cash_reservation_is_never_financed_by_future_sale(self):
        kwargs = self.base()
        kwargs['starting_cash'] = 6
        kwargs['reserved_cash'] = 4
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'cash_reserve_breached')
        self.assertEqual(report['minimum_cash'], 3.0)

    def test_action_budget_and_required_service_are_hard_bounds(self):
        kwargs = self.base()
        kwargs['available_unit_steps'] = 5
        self.assertEqual(worker_job_value.evaluate_worker_job(**kwargs)['reason'],
                         'unit_action_budget_exceeded')
        kwargs = self.base()
        kwargs['required_services']['CARE'] = 1
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertEqual(report['reason'], 'required_service_missing')
        self.assertEqual(report['missing_service'], 'CARE')

    def test_output_certificate_must_bind_harvest_and_drop_rows(self):
        kwargs = self.base()
        kwargs['expected_outputs'][0]['produced_step'] = 102
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertFalse(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'invalid_input')

        kwargs = self.base()
        kwargs['expected_outputs'][0]['sale_ready_step'] = 104
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertFalse(report['complete'])
        self.assertEqual(report['reason'], 'invalid_input')

    def test_strict_gain_threshold_and_durable_payback(self):
        kwargs = self.base()
        kwargs['minimum_gain'] = 9
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'no_strict_realized_payback')

        kwargs = self.base()
        kwargs['market_events'] = [
            {'kind': 'sale', 'step': 105, 'slot': 2, 'item': 'MILK',
             'quantity': 2, 'receipt_floor': 12},
            {'kind': 'input', 'step': 100, 'slot': 4, 'item': 'WHEAT',
             'quantity': 1, 'cost_upper': 3},
        ]
        kwargs['free_market_slots'] = {100: {4}, 105: {2}}
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertTrue(report['admitted'])
        self.assertEqual(report['payback_step'], 105)

    def test_schema_ambiguity_returns_invalid_without_mutating_inputs(self):
        kwargs = self.base()
        snapshot = copy.deepcopy(kwargs)
        kwargs['market_events'][1].pop('receipt_floor')
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertFalse(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'invalid_input')
        self.assertNotEqual(kwargs, snapshot)  # the fixture mutation is visible only to this test

        valid = self.base()
        valid_snapshot = copy.deepcopy(valid)
        worker_job_value.evaluate_worker_job(**valid)
        self.assertEqual(valid, valid_snapshot)

    def test_boolean_numeric_evidence_is_rejected(self):
        kwargs = self.base()
        kwargs['starting_cash'] = True
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertFalse(report['complete'])
        self.assertEqual(report['reason'], 'invalid_input')


if __name__ == '__main__':
    unittest.main()
