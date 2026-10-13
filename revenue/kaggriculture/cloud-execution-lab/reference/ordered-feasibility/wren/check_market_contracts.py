# SPDX-License-Identifier: Apache-2.0
"""Offline consumer checks against the pinned official market, not full games."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
SELLER = EVALUATOR = ENGINE = None
RECEIPTS = []


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fixture(*, step=17, seat=0, money=1000, shed=None, orders=None, **configuration):
    """Synthetic public farm + own private stock; no episode seed or replay."""
    config = dict(episodeSteps=720, turnsPerDay=24, shedCapacity=100,
                  boardSize=10, maxMarketOrdersPerTurn=10, farmHandCostMult=1)
    config.update(configuration)
    farms = [dict(money=money, hires_today=0, unlocked_quadrants=['NW'],
                  farmer=[4, 4], hands=[], tiles=[[None] * 10 for _ in range(10)])
             for _ in range(2)]
    private = dict(shed=copy.deepcopy(shed if shed is not None else {'CARROT': 1}),
                   seeds={}, inventories=[{}])
    obs = dict(step=step, day=step // config['turnsPerDay'],
               hour=step % config['turnsPerDay'], player=seat, private=private,
               farms=farms, market=dict(inventory={p: 10000 for p in ENGINE.PRODUCTS},
                                        prices={p: 0 for p in ENGINE.PRODUCTS}),
               town={'unlocked_shops': []})
    action = dict(farmer=['PASS'], hands=[], market=copy.deepcopy(orders or []))
    projection = dict(observed_step=step, end_step=step, stock_events=[], future_market={})
    return obs, config, action, projection


def ledger(case, reservations=None, contract=None):
    obs, config, action, projection = case
    return SELLER.ProjectionLedger(obs, config, action, obs['private']['shed'],
                                   projection, contract, reservations, 8)


def market_receipt(case, action=None, rival_orders=None):
    """Run unmodified _process_market on shared public state and separate privates."""
    obs, config, selected, _ = case
    seat = obs['player']
    farms, market = copy.deepcopy(obs['farms']), copy.deepcopy(obs['market'])
    state = []
    for player in range(2):
        private = (copy.deepcopy(obs['private']) if player == seat else
                   dict(shed={}, seeds={}, inventories=[{}]))
        current = (copy.deepcopy(selected if action is None else action) if player == seat
                   else dict(market=copy.deepcopy(rival_orders or [])))
        state.append(EVALUATOR.Struct(observation=EVALUATOR.Struct(
            farms=farms, market=market, private=private), action=current))
    ENGINE._process_market(state, EVALUATOR.Struct(configuration=EVALUATOR.Struct(config)))
    result = dict(step=obs['step'], seat=seat, orders=state[seat].action['market'],
                  rival_orders=copy.deepcopy(rival_orders or []),
                  own_cash=farms[seat]['money'], rival_cash=farms[1-seat]['money'],
                  shed=state[seat].observation.private['shed'],
                  seeds=state[seat].observation.private['seeds'],
                  hands=len(farms[seat]['hands']), hires_today=farms[seat]['hires_today'],
                  land=farms[seat]['unlocked_quadrants'])
    RECEIPTS.append(copy.deepcopy(result))
    return result


def transform(case, reservations=None, fallback=None):
    obs, config, action, projection = case
    seller = SELLER.SelectedActionSell()
    before = copy.deepcopy((case, reservations, fallback))
    result = seller.transform(obs, config, action, post_unit_shed=obs['private']['shed'],
                              projection=projection, reservations=reservations,
                              fallback_action=fallback)
    if (case, reservations, fallback) != before:
        raise AssertionError('Transform mutated caller-owned inputs')
    return result, seller.diagnostics


class MarketContractTests(unittest.TestCase):
    def test_terminal_stock_minimum_is_still_binding(self):
        for last in (6, 718):
            for seat in (0, 1):
                with self.subTest(last=last, seat=seat):
                    case = fixture(step=last, seat=seat, episodeSteps=last+2,
                                   shed={'CARROT': 1, 'WHEAT': 1},
                                   orders=[['SELL', 'WHEAT', 1], ['SELL', 'CARROT', 1]])
                    self.assertFalse(ledger(case, {'stock': {'WHEAT': 1}}).feasible(
                        'CARROT', ((last, 1),)))

    def test_terminal_conflict_returns_valid_fallback_in_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                case = fixture(step=718, seat=seat, shed={'CARROT': 1, 'WHEAT': 1},
                               orders=[['SELL', 'WHEAT', 1], ['SELL', 'CARROT', 1]])
                fallback = dict(farmer=['PASS'], hands=[], market=[[], ['SELL', 'CARROT', 1]])
                out, diagnostics = transform(case, {'stock': {'WHEAT': 1}}, fallback)
                receipt = market_receipt(case, out)
                self.assertEqual(out, fallback)
                self.assertEqual(diagnostics['status'], 'fallback')
                self.assertEqual((receipt['shed']['WHEAT'], receipt['own_cash']), (1, 1035))
                out['market'][1][2] = 99
                self.assertEqual(fallback['market'][1][2], 1)

    def test_nonterminal_conflict_already_uses_fallback(self):
        for seat in (0, 1):
            case = fixture(step=717, seat=seat, shed={'CARROT': 1, 'WHEAT': 1},
                           orders=[['SELL', 'WHEAT', 1], ['SELL', 'CARROT', 1]])
            fallback = dict(farmer=['PASS'], hands=[], market=[[], ['SELL', 'CARROT', 1]])
            out, diagnostics = transform(case, {'stock': {'WHEAT': 1}}, fallback)
            self.assertEqual(out, fallback)
            self.assertEqual(diagnostics['status'], 'fallback')
            self.assertEqual(market_receipt(case, out)['shed']['WHEAT'], 1)

    def test_terminal_excludes_post_final_salvage_and_capacity(self):
        case = fixture(step=718, orders=[['SELL', 'CARROT', 1]])
        case[3]['stock_events'] = [dict(step=718, phase='after_market', product='MILK', quantity_delta=101)]
        self.assertTrue(ledger(case).feasible('CARROT', ((718, 1),)))
        self.assertEqual(market_receipt(case)['shed']['CARROT'], 0)
        case[0].update(step=717, hour=21)
        case[3].update(observed_step=717, end_step=717)
        case[3]['stock_events'][0]['step'] = 717
        self.assertFalse(ledger(case).feasible('CARROT', ((717, 1),)))

    def test_final_deposit_cannot_restore_a_sold_stock_reservation(self):
        case = fixture(step=718, shed={'CARROT': 1, 'WHEAT': 1},
                       orders=[['SELL', 'WHEAT', 1], ['SELL', 'CARROT', 1]])
        case[3]['stock_events'] = [dict(step=718, phase='after_market', product='WHEAT', quantity_delta=1)]
        self.assertFalse(ledger(case, {'stock': {'WHEAT': 1}}).feasible('CARROT', ((718, 1),)))

    def test_cash_minima_respect_before_and_after_market(self):
        for step in (17, 718):
            case = fixture(step=step, money=0, orders=[['SELL', 'CARROT', 1]])
            before = {'cash': [dict(step=step, phase='before_market', minimum=1)]}
            after = {'cash': [dict(step=step, phase='after_market', minimum=1)]}
            too_high = {'cash': [dict(step=step, phase='after_market', minimum=2)]}
            self.assertFalse(ledger(case, before).feasible('CARROT', ((step, 1),)))
            self.assertTrue(ledger(case, after).feasible('CARROT', ((step, 1),)))
            # A cash lower bound is deliberately conservative, not exact receipts.
            self.assertFalse(ledger(case, too_high).feasible('CARROT', ((step, 1),)))
            self.assertEqual(market_receipt(case)['own_cash'], 35)

    def test_seed_store_is_separate_from_shed_capacity(self):
        for seat in (0, 1):
            case = fixture(seat=seat, shed={'CARROT': 2}, shedCapacity=2,
                           orders=[['BUY_SEED', 'TOMATO', 1], ['SELL', 'CARROT', 1]])
            self.assertTrue(ledger(case).feasible('CARROT', ((17, 1),)))
            result = market_receipt(case)
            self.assertEqual(result['seeds'], {'TOMATO': 1})
            self.assertEqual(result['shed']['CARROT'], 1)
            self.assertEqual(result['own_cash'], 985)

    def test_animal_purchase_uses_freed_shed_space_in_order(self):
        for seat in (0, 1):
            for sale_first in (False, True):
                orders = [['SELL', 'CARROT', 1], ['BUY_ANIMAL', 'GOOSE', 1]]
                if not sale_first:
                    orders.reverse()
                case = fixture(seat=seat, shed={'CARROT': 2}, shedCapacity=2, orders=orders)
                self.assertEqual(ledger(case).feasible('CARROT', ((17, 1),)), sale_first)
                result = market_receipt(case)
                self.assertEqual(result['shed'].get('GOOSE', 0), int(sale_first))
                self.assertEqual(result['own_cash'], 1035 - 300 * sale_first)

    def test_inherited_sell_funds_hire_without_reordering(self):
        for seat in (0, 1):
            case = fixture(seat=seat, money=0, shed={'CARROT': 2},
                           orders=[['SELL', 'CARROT', 1], ['HIRE'], ['SELL', 'CARROT', 1]])
            book = ledger(case)
            self.assertIsNone(book.market(17, 'CARROT', 0, 2))
            edited = book.market(17, 'CARROT', 1, 2)
            self.assertEqual(edited, [['SELL', 'CARROT', 1], ['HIRE'], []])
            self.assertTrue(book.feasible('CARROT', ((17, 1),)))
            action = copy.deepcopy(case[2]); action['market'] = edited
            result = market_receipt(case, action)
            self.assertEqual((result['hands'], result['own_cash']), (1, 34))
            case[2]['market'] = [['HIRE'], ['SELL', 'CARROT', 1]]
            self.assertFalse(ledger(case).feasible('CARROT', ((17, 1),)))
            self.assertEqual(market_receipt(case)['hands'], 0)

    def test_repeated_hire_prices_and_next_day_reset(self):
        for cash in (15, 16):
            case = fixture(money=cash, farmHandCostMult=2, orders=[['HIRE'], ['HIRE']])
            case[0]['farms'][0]['hires_today'] = 3
            self.assertEqual(ledger(case).feasible('CARROT', ((17, 0),)), cash == 16)
            self.assertEqual(market_receipt(case)['hands'], 2 if cash == 16 else 1)
        case = fixture(step=23, money=1)
        case[0]['farms'][0]['hires_today'] = 10
        case[3].update(end_step=24, future_market={24: [['HIRE']]})
        self.assertTrue(ledger(case).feasible('CARROT', ((23, 0),)))
        future = fixture(step=24, money=1, orders=[['HIRE']])
        self.assertEqual(market_receipt(future)['hands'], 1)

    def test_successive_land_prices(self):
        for cash in (2999, 3000):
            case = fixture(money=cash, orders=[['BUY_LAND'], ['BUY_LAND']])
            self.assertEqual(ledger(case).feasible('CARROT', ((17, 0),)), cash == 3000)
            result = market_receipt(case)
            self.assertEqual(len(result['land']), 3 if cash == 3000 else 2)

    def test_duplicate_sales_share_stock_and_keep_slots(self):
        case = fixture(shed={'CARROT': 4}, orders=[['SELL', 'CARROT', 3], [], ['SELL', 'CARROT', 3]])
        normalized = SELLER.normalize_selected(case[2], case[0]['private']['shed'], {})
        self.assertEqual(normalized['market'], [['SELL', 'CARROT', 3], [], ['SELL', 'CARROT', 1]])
        self.assertEqual(market_receipt(case, normalized)['shed']['CARROT'], 0)
        self.assertIsNone(ledger(case, {'market_slots': {17: [0]}}).market(17, 'CARROT', 3, 4))
        full = [[], ['SELL', 'CARROT', 1]]
        self.assertIsNone(SELLER.replace_sales(full, 'CARROT', 2, 2, 2))
        self.assertEqual(full, [[], ['SELL', 'CARROT', 1]])

    def test_product_buy_bounds_cover_actual_paired_units(self):
        for seat in (0, 1):
            orders = [['BUY_PRODUCT', 'WHEAT', 4]]
            case = fixture(seat=seat, money=1000, orders=orders)
            receipt = market_receipt(case, rival_orders=orders)
            total = 1000 - receipt['own_cash']
            self.assertEqual(receipt['shed'].get('WHEAT'), 4)
            bound = {'order_cost_bounds': [dict(step=17, slot=0, max_cash_cost=total)]}
            self.assertTrue(ledger(case, bound).feasible('CARROT', ((17, 0),)))
            with self.assertRaises(ValueError):
                ledger(case)
            low = {'order_cost_bounds': [dict(step=17, slot=0, max_cash_cost=0)]}
            self.assertFalse(ledger(case, low).feasible('CARROT', ((17, 0),)))
            case[0]['farms'][seat]['money'] = total
            self.assertTrue(ledger(case, bound).feasible('CARROT', ((17, 0),)))
            self.assertEqual(market_receipt(case, rival_orders=orders)['shed'].get('WHEAT'), 4)

    def test_missing_buy_bound_preserves_caller_fallback_and_inputs(self):
        case = fixture(orders=[['BUY_PRODUCT', 'WHEAT', 1], ['SELL', 'CARROT', 1]])
        fallback = dict(farmer=['PASS'], hands=[], market=[[], ['SELL', 'CARROT', 1]])
        out, diagnostics = transform(case, fallback=fallback)
        self.assertEqual(out, fallback)
        self.assertEqual(diagnostics['status'], 'fallback')
        self.assertNotIn('WHEAT', market_receipt(case, out)['shed'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab', type=Path, default=HERE.parent / 'cloud-execution-lab')
    parser.add_argument('--evaluator', type=Path, default=HERE.parent / 'cloud-eval/evaluate.py')
    parser.add_argument('--engine-cache', type=Path, required=True)
    parser.add_argument('--json-output', type=Path)
    args = parser.parse_args()
    global SELLER, EVALUATOR, ENGINE
    EVALUATOR = load_file('wren_existing_evaluator', args.evaluator)
    # Existing evaluator verifies all three pinned blobs before its offline loader.
    ENGINE, engine_hashes = EVALUATOR.get_engine(args.engine_cache, prepare=False)
    sys.path.insert(0, str(args.lab.resolve()))
    SELLER = load_file('wren_selected_action_sell', args.lab / 'selected_action_sell.py')
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MarketContractTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sources = {name: hashlib.sha256((args.lab / name).read_bytes()).hexdigest()
               for name in ('selected_action_sell.py', 'selected_sell_core.py', 'mechanics.py',
                            'reference/decision/decision.py')}
    report = dict(schema='titan.selected-market-checks.v1', engine_ref=EVALUATOR.ENGINE_REF,
                  sources=sources, engine_sha256=engine_hashes,
                  test_methods=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  successful=result.wasSuccessful(), official_market_cases=len(RECEIPTS),
                  game_panels=0, seeds_consumed=[], receipts=RECEIPTS)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: report[k] for k in ('test_methods', 'failures', 'errors',
                                            'successful', 'official_market_cases', 'game_panels')}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
