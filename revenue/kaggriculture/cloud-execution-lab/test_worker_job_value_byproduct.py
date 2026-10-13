# SPDX-License-Identifier: Apache-2.0
"""V5 worker-value contracts for certified saleable byproducts."""
from __future__ import annotations

import copy
import unittest

import worker_job_value


class WorkerJobValueByproductTests(unittest.TestCase):
    def livestock_job(self):
        return dict(
            start_step=100,
            actions=[
                ['EAST'], ['FEED'], ['HARVEST'], ['DROP'],
                ['COLLECT_FERTILIZER'], ['DROP'],
            ],
            available_unit_steps=6,
            payback_deadline_step=108,
            required_services={
                'FEED': 1, 'HARVEST': 1, 'COLLECT_FERTILIZER': 1, 'DROP': 2,
            },
            input_requirements=[
                {'item': 'WHEAT', 'quantity': 1, 'needed_step': 101,
                 'consumer': 'FEED'},
            ],
            owned_inputs={},
            expected_outputs=[
                # Omitted producer preserves the original HARVEST contract.
                {'item': 'MILK', 'quantity': 2, 'produced_step': 102,
                 'sale_ready_step': 103},
                # Fertilizer value is admitted only from an authored collection.
                {'item': 'FERTILIZER', 'quantity': 1,
                 'producer': 'COLLECT_FERTILIZER', 'produced_step': 104,
                 'sale_ready_step': 105},
            ],
            market_events=[
                {'kind': 'input', 'step': 100, 'slot': 4, 'item': 'WHEAT',
                 'quantity': 1, 'cost_upper': 3},
                {'kind': 'sale', 'step': 103, 'slot': 6, 'item': 'MILK',
                 'quantity': 2, 'receipt_floor': 12},
                {'kind': 'sale', 'step': 105, 'slot': 7, 'item': 'FERTILIZER',
                 'quantity': 1, 'receipt_floor': 5},
            ],
            free_market_slots={100: {4}, 103: {6}, 105: {7}},
            starting_cash=10,
            reserved_cash=4,
            max_market_slots=10,
            minimum_gain=0,
        )

    def test_mixed_product_and_fertilizer_receipts_share_one_payback(self):
        report = worker_job_value.evaluate_worker_job(**self.livestock_job())
        self.assertTrue(report['complete'])
        self.assertTrue(report['admitted'])
        self.assertEqual(report['reason'], 'strict_realized_payback')
        self.assertEqual(report['input_cost'], 3.0)
        self.assertEqual(report['sale_receipt'], 17.0)
        self.assertEqual(report['net_gain'], 14.0)
        self.assertEqual(report['payback_step'], 103)
        self.assertEqual(report['service_counts']['COLLECT_FERTILIZER'], 1)
        self.assertEqual(report['service_steps'], 5)
        self.assertEqual(report['travel_steps'], 1)

    def test_collection_certificate_requires_collection_at_exact_step(self):
        kwargs = self.livestock_job()
        kwargs['actions'][4] = ['CARE']
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertFalse(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'invalid_input')

    def test_collection_certificate_binds_exact_engine_item(self):
        kwargs = self.livestock_job()
        fertilizer = kwargs['expected_outputs'][1]
        fertilizer['item'] = 'MILK'
        kwargs['market_events'][2]['item'] = 'MILK'
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertFalse(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'invalid_input')

    def test_collection_certificate_binds_exact_one_unit_quantity(self):
        kwargs = self.livestock_job()
        fertilizer = kwargs['expected_outputs'][1]
        fertilizer['quantity'] = 2
        kwargs['market_events'][2]['quantity'] = 2
        kwargs['market_events'][2]['receipt_floor'] = 10
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertFalse(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'invalid_input')

    def test_collection_step_cannot_back_multiple_output_certificates(self):
        kwargs = self.livestock_job()
        fertilizer = kwargs['expected_outputs'][1]
        kwargs['expected_outputs'].append(copy.deepcopy(fertilizer))
        kwargs['market_events'][2]['quantity'] = 2
        kwargs['market_events'][2]['receipt_floor'] = 10
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertFalse(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'invalid_input')

    def test_non_materializing_service_cannot_claim_sale_provenance(self):
        kwargs = self.livestock_job()
        fertilizer = kwargs['expected_outputs'][1]
        fertilizer['producer'] = 'FEED'
        fertilizer['produced_step'] = 101
        report = worker_job_value.evaluate_worker_job(**kwargs)
        self.assertFalse(report['complete'])
        self.assertFalse(report['admitted'])
        self.assertEqual(report['reason'], 'invalid_input')

    def test_helper_does_not_mutate_mixed_certificate(self):
        kwargs = self.livestock_job()
        snapshot = copy.deepcopy(kwargs)
        worker_job_value.evaluate_worker_job(**kwargs)
        self.assertEqual(kwargs, snapshot)


if __name__ == '__main__':
    unittest.main()
