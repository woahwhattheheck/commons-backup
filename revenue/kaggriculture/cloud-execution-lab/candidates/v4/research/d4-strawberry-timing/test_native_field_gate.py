# SPDX-License-Identifier: Apache-2.0
"""Independent census/receipt acceptance and false-PASS controls.

BERRY_ARTIFACT must name the exact downloaded artifact10175943272 ZIP.
"""
from __future__ import annotations
import copy
import os
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import native_field_gate as gate


class CensusTests(unittest.TestCase):
    def setUp(self):
        self.route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        self.route[370]['market'] = [['SELL', 'STRAWBERRY', 7]]

    def dates(self, now=360, checkpoints=(), cap=10, last=718):
        return gate.authored_dates(self.route, now, last, checkpoints, cap)

    def test_positive_and_purity(self):
        before = copy.deepcopy(self.route)
        self.assertEqual(self.dates(), [[370, 7]])
        self.assertEqual(self.route, before)

    def test_boundary_eight_is_not_beyond(self):
        self.assertEqual(self.dates(now=362), [])
        self.assertEqual(self.dates(now=361), [[370, 7]])

    def test_checkpoint_and_day_are_hard(self):
        self.assertEqual(self.dates(checkpoints=[375, 368]), [])
        self.assertEqual(self.dates(now=350), [])
        self.assertEqual(self.dates(checkpoints=[360, 350]), [[370, 7]])

    def test_live_cap_keeps_raw_empty_slots(self):
        self.route[370]['market'] = [[], ['SELL', 'STRAWBERRY', 7]]
        self.assertEqual(self.dates(cap=1), [])
        self.assertEqual(self.dates(cap=2), [[370, 7]])

    def test_minimum_one_live_order(self):
        self.assertEqual(self.dates(cap=0), [[370, 7]])
        self.assertEqual(self.dates(cap=-2), [[370, 7]])

    def test_terminal_and_short_route(self):
        self.assertEqual(self.dates(last=369), [])
        self.route = self.route[:370]
        self.assertEqual(self.dates(), [])

    def test_no_boolean_negative_or_requested_nonint(self):
        for qty in (True, False, -1, 0, '7', 7.0, None):
            self.route[370]['market'] = [['SELL', 'STRAWBERRY', qty]]
            self.assertEqual(self.dates(), [])

    def test_other_products_and_duplicate_sum(self):
        self.route[370]['market'] += [['SELL', 'STRAWBERRY', 3], ['SELL', 'MILK', 8]]
        self.assertEqual(self.dates(), [[370, 10]])

    def test_semantic_mutants_rejected(self):
        source = inspect.getsource(gate.authored_dates)
        variants = [
            ('eight_inclusive', 'now + 9', 'now + 8', 368, [], (), 10),
            ('compact_live_cap', 'rows[:max(1, int(cap))]', 'rows', 370,
             [[], ['SELL', 'STRAWBERRY', 7]], (), 1),
            ('cross_checkpoint', 'end = step - 1', 'end = end', 370, [], (369,), 10),
            ('accept_bool', "type(row[2]) is int", "isinstance(row[2], int)", 370,
             [['SELL', 'STRAWBERRY', True]], (), 10),
        ]
        for name, old, new, date, rows, checkpoints, cap in variants:
            route = [{'market': []} for _ in range(720)]
            route[date]['market'] = rows or [['SELL', 'STRAWBERRY', 7]]
            self.assertIn(old, source)
            namespace = {'ITEM': gate.ITEM}
            exec(compile(source.replace(old, new, 1), name, 'exec'), namespace)
            expected = gate.authored_dates(route, 360, 718, checkpoints, cap)
            self.assertEqual(expected, [])
            actual = namespace['authored_dates'](route, 360, 718, checkpoints, cap)
            with self.assertRaisesRegex(AssertionError, name):
                gate.require(actual == expected, name)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix='berry-contract-')
        cls.root = Path(cls.scratch.name)
        cls.artifact = Path(os.environ['BERRY_ARTIFACT'])
        cls.identity = gate.unpack(cls.artifact, cls.root)
        loader_path = cls.root/'checks/reference/evaluator/loader.py'
        cls.loader = gate.load(loader_path, 'berry_contract_loader')
        cls.engine, _ = cls.loader.get_engine(cls.root/'checks/reference/engine')

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def world(self, seat, stock, inventory=0, step=360, cap=10):
        S = self.loader.Struct
        cfg = S({k: v.get('default') if isinstance(v, dict) else v
                 for k, v in self.engine.specification['configuration'].items()})
        cfg.seed = 9922999
        cfg.maxMarketOrdersPerTurn = cap
        env = S(configuration=cfg, done=False, info={})
        state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        self.engine.interpreter(state, env)
        for s in state:
            s.observation.step = step
            s.observation.day, s.observation.hour = divmod(step, 24)
            s.action = {'farmer': ['PASS'], 'hands': [], 'market': []}
        state[seat].observation.private['shed']['STRAWBERRY'] = stock
        market = state[0].observation.market
        market['inventory']['STRAWBERRY'] = inventory
        self.engine._refresh_prices(market)
        return state, env

    def test_full_engine_receipt_is_filled_not_requested(self):
        for seat in (0, 1):
            state, env = self.world(seat, 3)
            state[seat].action['market'] = [['SELL', 'STRAWBERRY', 1000]]
            record = gate.MarketAudit(self.engine, seat).transition(state, env)
            self.assertEqual(record['post_units_stock'], 3)
            self.assertEqual(record['fill_units'], 3)
            expected = sum(self.engine.market_price('STRAWBERRY', n) for n in range(3))
            self.assertEqual(record['fill_cash'], expected)

    def test_no_fill_from_rival_or_empty_shed(self):
        for seat in (0, 1):
            state, env = self.world(seat, 0)
            state[1-seat].observation.private['shed']['STRAWBERRY'] = 9
            for s in state:
                s.action['market'] = [['SELL', 'STRAWBERRY', 9]]
            record = gate.MarketAudit(self.engine, seat).transition(state, env)
            self.assertEqual(record['fill_units'], 0)
            self.assertEqual(record['fill_cash'], 0)

    def test_floor_price_sales_fill_without_inventory_growth(self):
        for seat in (0, 1):
            state, env = self.world(seat, 4, inventory=100000, step=362)
            state[seat].action['market'] = [['SELL', 'STRAWBERRY', 100]]
            record = gate.MarketAudit(self.engine, seat).transition(state, env)
            self.assertEqual(record['fill_units'], 4)
            self.assertEqual(record['fill_cash'], 4)
            self.assertEqual(state[0].observation.market['inventory']['STRAWBERRY'], 100000)

    def test_raw_market_cap_and_same_item_duplicates(self):
        for seat in (0, 1):
            state, env = self.world(seat, 9, cap=2)
            state[seat].action['market'] = [[], ['SELL', 'STRAWBERRY', 2], ['SELL', 'STRAWBERRY', 9]]
            record = gate.MarketAudit(self.engine, seat).transition(state, env)
            self.assertEqual(record['fill_units'], 2)
            state, env = self.world(seat, 3, cap=2)
            state[seat].action['market'] = [['SELL', 'STRAWBERRY', 2], ['SELL', 'STRAWBERRY', 2]]
            self.assertEqual(gate.MarketAudit(self.engine, seat).transition(state, env)['fill_units'], 3)

    def test_drop_before_market_and_ghost_plant_demand_preserved(self):
        for seat in (0, 1):
            state, env = self.world(seat, 0)
            state[seat].observation.private['inventories'][0]['STRAWBERRY'] = 5
            state[seat].action = {'farmer': ['DROP'], 'hands': [],
                                  'market': [['SELL', 'STRAWBERRY', 5]]}
            rec = gate.MarketAudit(self.engine, seat).transition(state, env)
            self.assertEqual(rec['post_units_stock'], 5)
            self.assertEqual(rec['fill_units'], 5)
            state, env = self.world(seat, 0)
            f = state[0].observation.farms[seat]
            f['farmer'] = [0, 0]
            f['tiles'][0][0] = None
            state[seat].observation.private['seeds']['STRAWBERRY'] = 1
            state[seat].action = {'farmer': ['PLANT', 'STRAWBERRY'],
                                  'hands': [['PLANT', 'STRAWBERRY']], 'market': []}
            gate.MarketAudit(self.engine, seat).transition(state, env)
            self.assertIsNone(f['tiles'][0][0])
            self.assertEqual(state[seat].observation.private['seeds']['STRAWBERRY'], 1)

    def test_pass_through_corruption_rejected_by_pristine_transition(self):
        state, env = self.world(0, 3)
        state[0].action['market'] = [['SELL', 'STRAWBERRY', 3]]
        audit = gate.MarketAudit(self.engine, 0)
        def bad_commit(op, item, price, farm, private, market, capacity=100):
            return audit.commit(op, item, price+1, farm, private, market, capacity)
        audit.unit = bad_commit
        with self.assertRaisesRegex(AssertionError, 'instrumentation changed full'):
            audit.transition(state, env)
        self.assertIs(self.engine._process_market, audit.market)
        self.assertIs(self.engine._commit_unit, audit.commit)

    def test_source_identity_and_wrong_candidate(self):
        self.assertEqual(self.identity['changed'], [])
        self.assertEqual(len(self.identity['original_members']), 110)
        for name, expected in gate.ENGINE_BLOBS.items():
            self.assertEqual(gate.blob((self.root/'checks/reference/engine'/name).read_bytes()), expected)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(AssertionError, 'candidate SHA256'):
                gate.unpack(self.artifact, Path(d), self.root/'frozen_selected.py', '0'*64)

    def test_altered_artifact_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'bad.zip'
            p.write_bytes(self.artifact.read_bytes()+b'ALTERED')
            with self.assertRaisesRegex(AssertionError, 'artifact SHA256'):
                gate.unpack(p, Path(d)/'out')


class ReportContractTests(unittest.TestCase):
    """Synthetic reports exercise validation only, not reported game evidence."""
    def report(self):
        members = {'frozen_selected.py': 'a'*64, **{str(i): 'b'*64 for i in range(109)}}
        rows = [{'step': i, 'action_sha256': 'c'*64, 'state_sha256': 'd'*64,
                 'status': 'completed', 'fill_units': 0, 'fill_cash': 0} for i in range(719)]
        identity = {'original_members': members, 'materialized_members': dict(members),
                    'original_manifest_sha256': gate.sha(gate.encoded(members)),
                    'materialized_manifest_sha256': gate.sha(gate.encoded(members)), 'changed': []}
        return {'seed': 17, 'seat': 0, 'callbacks': 719, 'fallbacks': 0,
                'official_transitions_including_shadow': 1438, 'identity': identity,
                'bank': [100, 40], 'margin': 60, 'rows': rows,
                'strawberry': {'filled_units': 0, 'realized_receipts': 0},
                'action_trace_sha256': gate.sha(gate.encoded([r['action_sha256'] for r in rows])),
                'state_trace_sha256': gate.sha(gate.encoded([r['state_sha256'] for r in rows]))}

    def test_clean_negative_and_real_margin_arithmetic(self):
        left, right = self.report(), self.report()
        self.assertEqual(gate.compare(left, right)['action_changes'], [])
        right['bank'] = [101, 43]
        right['margin'] = 58
        result = gate.compare(left, right)
        self.assertEqual((result['delta_own'], result['delta_rival'], result['delta_margin']),
                         (1, 3, -2))

    def test_incomplete_and_duplicate_step_rejected(self):
        for mutation in ('truncate', 'duplicate'):
            r = self.report()
            if mutation == 'truncate':
                r['rows'].pop()
            else:
                r['rows'][33]['step'] = 32
            with self.assertRaises(AssertionError):
                gate.validate_report(r)

    def test_false_receipts_and_deadline_summary_rejected(self):
        for field in ('filled_units', 'realized_receipts', 'fallbacks'):
            r = self.report()
            if field == 'fallbacks':
                r['rows'][10]['status'] = 'deadline_fallback'
            else:
                r['strawberry'][field] = 1000
            with self.assertRaises(AssertionError):
                gate.validate_report(r)

    def test_deadline_contaminated_pair_rejected(self):
        left, right = self.report(), self.report()
        for r in (left, right):
            r['rows'][10]['status'] = 'deadline_fallback'
            r['fallbacks'] = 1
        with self.assertRaisesRegex(AssertionError, 'deadline-contaminated'):
            gate.compare(left, right)

    def test_trace_digest_and_margin_mismatch_rejected(self):
        for field in ('action_trace_sha256', 'state_trace_sha256', 'margin'):
            r = self.report()
            r[field] = 0
            with self.assertRaises(AssertionError):
                gate.validate_report(r)

    def test_extra_source_mutation_and_false_delta_rejected(self):
        for field in ('foreign', 'misreported'):
            r = self.report()
            identity = r['identity']
            name = '0' if field == 'foreign' else 'frozen_selected.py'
            identity['materialized_members'][name] = 'e'*64
            identity['materialized_manifest_sha256'] = gate.sha(gate.encoded(identity['materialized_members']))
            with self.assertRaises(AssertionError):
                gate.validate_report(r)

    def test_nonfinite_and_unpaired_seat_rejected(self):
        r = self.report()
        r['extra_receipt'] = float('nan')
        with self.assertRaises(ValueError):
            gate.validate_report(r)
        left, right = self.report(), self.report()
        right['seat'] = 1
        right['bank'] = [40, 100]
        with self.assertRaisesRegex(AssertionError, 'unpaired'):
            gate.compare(left, right)


if __name__ == '__main__':
    unittest.main()
