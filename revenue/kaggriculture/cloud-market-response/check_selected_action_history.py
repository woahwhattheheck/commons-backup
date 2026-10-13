# SPDX-License-Identifier: Apache-2.0
"""Native boundary checks for the selected-action -> fill -> T12 history join.

Pass existing source paths; this script fetches no files. Optional trace intake
consumes saved own observations/actions through an existing own-unit snapshot
helper, without actor calls, market replay, or new complete games.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ENGINE_HASHES = {
    'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}
D = None
COUNTS = Counter()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def make_bridge(**kwargs):
    ledger = kwargs.pop('ledger', D.fills.ObservedFillLedger())
    history = kwargs.pop('history', D.flow.FlowHistory())
    return D.subject.SelectedActionHistory(ledger=ledger, history=history,
        interval_type=D.flow.FlowInterval, infer=D.sorrel.infer_rival_flow,
        mechanics=D.engine, **kwargs)


def fixture(*, step=1, player=0, stock=None, market=None, shops=()):
    farm = {'money': 100000, 'tiles': [[None for _ in range(10)] for _ in range(10)],
            'farmer': [4, 4], 'hands': [], 'unlocked_quadrants': ['NW'], 'hires_today': 0}
    obs = {'step': step, 'day': step//24, 'hour': step%24, 'player': player,
           'farms': [deepcopy(farm), deepcopy(farm)],
           'market': {'inventory': {p: 10000 for p in D.engine.PRODUCTS}, 'prices': {}},
           'town': {'unlocked_shops': list(shops)},
           'private': {'shed': deepcopy(stock or {}), 'seeds': {}, 'inventories': [{}]}}
    obs['market']['inventory'].update(market or {})
    D.engine._refresh_prices(obs['market'])
    cfg = {'turnsPerDay': 24, 'maxMarketOrdersPerTurn': 10, 'shedCapacity': 100,
           'townShopSellInterval': 4, 'townCenterSellInterval': 24,
           'boardSize': 10, 'farmHandCostMult': 1, 'episodeSteps': 720}
    return obs, cfg


def action(queue):
    return {'farmer': ['PASS'], 'hands': [], 'market': deepcopy(queue)}


def market_after(obs, cfg, own, *, rival=(), rival_stock=None, deposits=()):
    """Execute the pinned market/town functions, not a replacement simulator."""
    farms, market, town = deepcopy(obs['farms']), deepcopy(obs['market']), deepcopy(obs['town'])
    player = obs['player']
    private = [None, None]
    private[player] = deepcopy(obs['private'])
    private[1-player] = {'shed': deepcopy(rival_stock or {}), 'seeds': {}, 'inventories': [{}]}
    acts = [None, None]; acts[player] = deepcopy(own); acts[1-player] = action(rival)
    state = [NS(observation=NS(farms=farms, market=market, town=town, private=private[i]),
                action=acts[i]) for i in range(2)]
    env = NS(configuration=NS(**cfg))
    receipts = Counter()
    original = D.engine._commit_unit
    def capture(op, item, price, farm, own_private, shared, capacity):
        ok = original(op, item, price, farm, own_private, shared, capacity)
        if ok and op == 'SELL':
            receipts[('own' if own_private is private[player] else 'rival', item)] += 1
        return ok
    with patch.object(D.engine, '_commit_unit', side_effect=capture):
        D.engine._process_market(state, env)
    COUNTS['native_market_calls'] += 1
    D.engine._town_consume(env, state, obs['step'])
    after = deepcopy(obs)
    after['private'] = private[player]
    after['market'] = market
    # The ledger's EOD inference is exercised with native ordered deposits.
    if deposits:
        after['private']['inventories'] = deepcopy(list(deposits))
        D.engine._drop_inventories_to_shed(after['private'], cfg['shedCapacity'])
        COUNTS['native_deposit_calls'] += 1
    after['step'] += 1
    after['day'], after['hour'] = divmod(after['step'], cfg['turnsPerDay'])
    return after, receipts


def join(obs, cfg, own, after, *, inventories=(), bridge=None):
    b = bridge or make_bridge()
    with patch.object(D.engine, 'interpreter', side_effect=AssertionError('runtime invoked engine')):
        b.record(obs, cfg, own, post_unit_shed=obs['private']['shed'],
                 post_unit_inventories=inventories)
        result = b.observe(after)
    return b, result


def interval(result, product):
    return next(r for r in result['intervals'] if r['product'] == product)


class SelectedHistoryTests(unittest.TestCase):
    def test_01_native_clipped_and_repeated_sales_both_positions(self):
        for player in (0, 1):
            for own_queue in ([['SELL', 'MILK', 99]],
                              [['SELL', 'MILK', 2], ['SELL', 'MILK', 99]],
                              [[], ['HIRE'], ['SELL', 'MILK', '99']]):
                obs, cfg = fixture(player=player, stock={'MILK': 5})
                own = action(own_queue)
                after, receipts = market_after(obs, cfg, own,
                    rival=[['SELL', 'MILK', 3]], rival_stock={'MILK': 3})
                b, result = join(obs, cfg, own, after)
                self.assertEqual(result['own_sale_units']['MILK'], 5)
                self.assertEqual(receipts['own', 'MILK'], 5)
                self.assertEqual(interval(result, 'MILK')['lower'], 3)
                self.assertTrue(interval(result, 'MILK')['exact'])
                self.assertEqual(b.history.records['MILK'][1].lower, 3)
                self.assertIsNone(result['cash_receipts'])

    def test_02_no_sale_is_observed_zero_not_missing(self):
        obs, cfg = fixture(stock={})
        own = action([['SELL', 'MILK', 99]])
        after, _ = market_after(obs, cfg, own)
        b, result = join(obs, cfg, own, after)
        self.assertEqual(result['own_sale_units']['MILK'], 0)
        self.assertTrue(interval(result, 'MILK')['exact'])
        self.assertEqual(b.history.records['MILK'][1].lower, 0)

    def test_03_floor_sale_remains_censored_in_rival_history(self):
        obs, cfg = fixture(stock={'WOOL': 5}, market={'WOOL': 20000})
        own = action([['SELL', 'WOOL', 5]])
        after, receipts = market_after(obs, cfg, own,
            rival=[['SELL', 'WOOL', 3]], rival_stock={'WOOL': 3})
        b, result = join(obs, cfg, own, after)
        self.assertEqual(receipts['own', 'WOOL'], 5)
        self.assertEqual(result['own_sale_units']['WOOL'], 5)
        r = interval(result, 'WOOL')
        self.assertEqual((r['lower'], r['upper'], r['reason']), (0, 100, 'floor_censored'))
        self.assertFalse(r['exact'])
        self.assertEqual(b.history.predict('WOOL', 25, now=2)['support'], 0)

    def test_04_operating_round_trip_is_not_a_rival_sale(self):
        obs, cfg = fixture(stock={})
        own = action([['BUY_PRODUCT', 'WHEAT', 1], ['SELL', 'WHEAT', 1]])
        after, _ = market_after(obs, cfg, own)
        b, result = join(obs, cfg, own, after)
        self.assertEqual(result['fill_status'], 'ambiguous')
        self.assertNotIn('WHEAT', result['own_sale_units'])
        self.assertNotIn('WHEAT', b.history.records)
        self.assertEqual(result['excluded']['WHEAT'], 'operating_product_buy_sell_ambiguity')
        self.assertTrue(interval(result, 'MILK')['exact'])

    def test_05_slot_limit_and_malformed_orders_reuse_ledger_parser(self):
        obs, cfg = fixture(stock={'MILK': 9})
        cfg['maxMarketOrdersPerTurn'] = 5
        own = action([['SELL', 'MILK', 'bad'], None, ['BUY_SEED', 'WHEAT', 1],
                      ['SELL', 'MILK', 2], ['SELL', 'MILK', -4], ['SELL', 'MILK', 7]])
        after, receipts = market_after(obs, cfg, own)
        _, result = join(obs, cfg, own, after)
        self.assertEqual(receipts['own', 'MILK'], 2)
        self.assertEqual(result['own_sale_units']['MILK'], 2)
        self.assertEqual(interval(result, 'MILK')['lower'], 0)

    def test_06_native_slot_floor_one_when_config_is_zero(self):
        obs, cfg = fixture(stock={'MILK': 4})
        cfg['maxMarketOrdersPerTurn'] = 0
        own = action([['SELL', 'MILK', 1], ['SELL', 'MILK', 3]])
        after, _ = market_after(obs, cfg, own)
        _, result = join(obs, cfg, own, after)
        self.assertEqual(result['own_sale_units']['MILK'], 1)

    def test_07_same_step_replacement_uses_final_binding(self):
        obs, cfg = fixture(stock={'MILK': 5})
        b = make_bridge()
        b.record(obs, cfg, action([['SELL', 'MILK', 5]]), post_unit_shed={'MILK': 5})
        own = action([['SELL', 'MILK', 2]])
        final = b.record(obs, cfg, own, post_unit_shed={'MILK': 5})
        after, _ = market_after(obs, cfg, own)
        result = b.observe(after)
        self.assertEqual(result['own_sale_units']['MILK'], 2)
        self.assertEqual(result['binding']['action_sha256'], final['action_sha256'])

    def test_08_shared_ledger_result_is_consumed_without_a_second_call(self):
        obs, cfg = fixture(stock={'MILK': 4})
        own = action([['SELL', 'MILK', 3]])
        ledger = D.fills.ObservedFillLedger(); b = make_bridge(ledger=ledger)
        binding = ledger.record(obs, cfg, own, post_unit_shed={'MILK': 4})
        b.bind(obs, cfg, own, binding)
        after, _ = market_after(obs, cfg, own)
        result = ledger.observe(after)
        with patch.object(ledger, 'record', side_effect=AssertionError('duplicate record')), \
             patch.object(ledger, 'observe', side_effect=AssertionError('duplicate observe')):
            out = b.observe(after, fill_result=result)
        self.assertEqual(out['own_sale_units']['MILK'], 3)

    def test_09_same_step_pending_and_duplicate_reads_do_not_train(self):
        obs, cfg = fixture(stock={}); own = action([]); b = make_bridge()
        b.record(obs, cfg, own, post_unit_shed={})
        self.assertEqual(b.observe(obs)['status'], 'pending')
        self.assertEqual(b.history.identified, 0)
        after, _ = market_after(obs, cfg, own)
        b.observe(after); count = b.history.identified
        self.assertEqual(b.observe(after)['reason'], 'no_pending_action')
        self.assertEqual(b.history.identified, count)

    def test_10_wrong_player_does_not_consume_pending(self):
        obs, cfg = fixture(stock={}); own = action([]); b = make_bridge()
        b.record(obs, cfg, own, post_unit_shed={})
        after, _ = market_after(obs, cfg, own)
        wrong = deepcopy(after); wrong['player'] = 1
        self.assertEqual(b.observe(wrong)['reason'], 'different_player')
        self.assertEqual(b.observe(after)['status'], 'recorded')

    def test_11_gap_does_not_fabricate_zero(self):
        obs, cfg = fixture(stock={}); own = action([]); b = make_bridge()
        b.record(obs, cfg, own, post_unit_shed={})
        after, _ = market_after(obs, cfg, own); after['step'] = 3; after['hour'] = 3
        self.assertEqual(b.observe(after)['reason'], 'nonadjacent_observation')
        self.assertFalse(b.history.records)

    def test_12_clock_fallback_and_invalid_clock(self):
        obs, cfg = fixture(stock={}); own = action([])
        after, _ = market_after(obs, cfg, own)
        del obs['step']; del after['step']
        b, out = join(obs, cfg, own, after)
        self.assertEqual(out['binding']['step'], 1)
        self.assertEqual(out['observed_at'], 2)
        obs, cfg = fixture(stock={}); b = make_bridge()
        b.record(obs, cfg, own, post_unit_shed={})
        after, _ = market_after(obs, cfg, own); after['hour'] = 99
        self.assertEqual(b.observe(after)['reason'], 'invalid_observation')
        self.assertFalse(b.history.records)

    def test_13_no_day_boundary_inventory_evidence_is_unknown(self):
        obs, cfg = fixture(step=23, stock={}); own = action([])
        after, _ = market_after(obs, cfg, own)
        b, result = join(obs, cfg, own, after, inventories=None)
        self.assertEqual(result['fill_reason'], 'after_market_deposits_unknown')
        self.assertFalse(b.history.records)

    def test_14_ordered_native_deposits_reconcile_before_town_inference(self):
        obs, cfg = fixture(step=23, stock={'MILK': 98}); own = action([['SELL', 'MILK', 3]])
        deposits = [{'MILK': 2, 'WOOL': 6}, {'CARROT': 2}]
        after, _ = market_after(obs, cfg, own, deposits=deposits)
        self.assertEqual(after['private']['shed'], {'MILK': 97, 'WOOL': 3})
        b, result = join(obs, cfg, own, after, inventories=deposits)
        self.assertEqual(result['own_sale_units']['MILK'], 3)
        self.assertEqual(interval(result, 'MILK')['lower'], 0)

    def test_15_duplicate_old_shops_not_newly_revealed_shops(self):
        name = next(iter(D.engine.SHOPS))
        obs, cfg = fixture(step=24, stock={}, shops=[name, name]); own = action([])
        after, _ = market_after(obs, cfg, own)
        after['town']['unlocked_shops'].append(name)
        _, result = join(obs, cfg, own, after)
        self.assertTrue(all(r['lower'] == r['upper'] == 0 for r in result['intervals']))

    def test_16_budget_exhaustion_is_not_a_zero_history_sample(self):
        obs, cfg = fixture(stock={}); own = action([['BUY_PRODUCT', 'WHEAT', 99]])
        after, _ = market_after(obs, cfg, own)
        b = make_bridge(ledger=D.fills.ObservedFillLedger(max_states=1))
        _, result = join(obs, cfg, own, after, bridge=b)
        self.assertEqual(result['fill_reason'], 'state_budget_exceeded')
        self.assertFalse(b.history.records)

    def test_17_contradictory_own_snapshot_does_not_train(self):
        obs, cfg = fixture(stock={'MILK': 1}); own = action([])
        after, _ = market_after(obs, cfg, own); after['private']['shed']['MILK'] = 0
        b, result = join(obs, cfg, own, after)
        self.assertEqual(result['fill_reason'], 'observed_shed_not_explained')
        self.assertFalse(b.history.records)

    def test_18_changed_market_parameters_exclude_transition(self):
        obs, cfg = fixture(stock={}); own = action([])
        after, _ = market_after(obs, cfg, own); after['market']['params'] = {'MILK': {'base': 2}}
        b, result = join(obs, cfg, own, after)
        self.assertEqual(result['reason'], 'market_parameters_changed')
        self.assertFalse(b.history.records)

    def test_19_missing_product_excludes_whole_transition(self):
        obs, cfg = fixture(stock={}); own = action([])
        after, _ = market_after(obs, cfg, own); after['market']['inventory'].pop('MILK')
        b, result = join(obs, cfg, own, after)
        self.assertEqual(result['reason'], 'incomplete_market_observation')
        self.assertFalse(b.history.records)

    def test_20_caller_mutation_and_result_mutation_do_not_change_history(self):
        obs, cfg = fixture(stock={'MILK': 5}); own = action([['SELL', 'MILK', 3]])
        after, _ = market_after(obs, cfg, own); original = deepcopy((obs, cfg, own, after))
        b = make_bridge(); b.record(obs, cfg, own, post_unit_shed=obs['private']['shed'])
        self.assertEqual((obs, cfg, own, after), original)
        obs['market']['inventory']['MILK'] = 1; own['market'][0][2] = 99; cfg['shedCapacity'] = 1
        out = b.observe(after); self.assertEqual(out['own_sale_units']['MILK'], 3)
        interval(out, 'MILK')['lower'] = 999
        self.assertEqual(b.history.records['MILK'][1].lower, 0)

    def test_21_wrong_binding_is_not_consumed(self):
        obs, cfg = fixture(stock={}); own = action([]); b = make_bridge()
        binding = b.record(obs, cfg, own, post_unit_shed={})
        after, _ = market_after(obs, cfg, own)
        actual = b.ledger.observe(after); wrong = deepcopy(actual)
        wrong['binding']['action_sha256'] = '0'*64
        self.assertEqual(b.observe(after, fill_result=wrong)['reason'], 'fill_binding_mismatch')
        self.assertFalse(b.history.records)
        self.assertEqual(b.observe(after, fill_result=actual)['status'], 'recorded')
        with self.assertRaises(ValueError): b.bind(obs, cfg, own, binding)

    def test_22_period_and_actor_cannot_mix(self):
        obs, cfg = fixture(stock={}); own = action([]); b = make_bridge()
        with self.assertRaises(ValueError): b.record(obs, dict(cfg, turnsPerDay=12), own, post_unit_shed={})
        b.record(obs, cfg, own, post_unit_shed={})
        with self.assertRaises(ValueError): b.record(dict(obs, player=1), cfg, own, post_unit_shed={})
        with self.assertRaises(ValueError): b.bind(obs, cfg, own, {'status':'recorded'})

    def test_23_completed_windows_only_and_no_future_sample(self):
        b = make_bridge()
        for step, quantity in ((1, 2), (25, 3), (49, 4)):
            obs, cfg = fixture(step=step, stock={}); own = action([])
            after, _ = market_after(obs, cfg, own, rival=[['SELL','MILK',quantity]], rival_stock={'MILK':quantity})
            join(obs, cfg, own, after, bridge=b)
        p = b.history.window_prediction('MILK', 73, 73)
        self.assertTrue(p['ready']); self.assertEqual(p['support'], 3)
        self.assertEqual((p['lower'], p['point'], p['upper']), (2,3,4))
        self.assertTrue(all(w['training_end'] < 73 for w in p['windows']))
        self.assertEqual(b.history.window_prediction('MILK', 73, 74)['support'], 0)

    def test_24_runtime_never_calls_native_unit_market_or_controller(self):
        obs, cfg = fixture(stock={}); own = action([])
        after, _ = market_after(obs, cfg, own)
        with patch.object(D.engine, 'interpreter', side_effect=AssertionError('engine called')), \
             patch.object(D.engine, '_process_market', side_effect=AssertionError('market called')), \
             patch.object(D.engine, '_apply_unit_action', side_effect=AssertionError('unit called')):
            b, result = join(obs, cfg, own, after)
        self.assertEqual(result['status'], 'recorded')
        self.assertTrue(b.history.records)


def consume_trace(path, unit_cases):
    """New bridge replay only. Retained expected actions are inputs, not rerun."""
    raw = Path(path).read_bytes()
    decoded = gzip.decompress(raw) if str(path).endswith('.gz') else raw
    rows = [json.loads(line) for line in decoded.splitlines() if line.strip()]
    sys.path.insert(0, str(Path(unit_cases).resolve().parent))
    try:
        cases = load(unit_cases, '_cedar_existing_native_unit_cases')
    finally:
        sys.path.pop(0)
    b = make_bridge()
    results, statuses, interval_kinds = [], Counter(), Counter()
    times = []
    for index, row in enumerate(rows[:-1]):
        next_row = rows[index+1]
        obs, cfg, chosen = row['observation'], row['configuration'], row['expected_action']
        assert row['step'] == obs['step'] and next_row['step'] == row['step']+1
        before = deepcopy((obs, cfg, chosen, next_row['observation']))
        # Existing helper stops native interpreter at the first market call.
        # Neither actual rival action nor a game seed is supplied to the helper.
        cfg = dict(cfg); cfg.pop('seed', None)
        snapshot = cases.own_unit_snapshot(D.engine, obs, cfg, chosen)
        COUNTS['retained_native_unit_snapshots'] += 1
        start = time.perf_counter()
        with patch.object(D.engine, 'interpreter', side_effect=AssertionError('bridge engine call')):
            b.record(obs, cfg, chosen, post_unit_shed=snapshot['private']['shed'],
                     post_unit_inventories=snapshot['private']['inventories'])
            result = b.observe(next_row['observation'])
        times.append(time.perf_counter()-start)
        assert before == (obs, row['configuration'], chosen, next_row['observation'])
        assert all(r['step'] < next_row['observation']['step'] for r in result['intervals'])
        statuses[result['status']+':'+result['reason']] += 1
        for r in result['intervals']:
            interval_kinds[r['reason']] += 1
        results.append(result)
    summary = {'records':len(rows), 'adjacent_transitions_consumed':len(results),
               'statuses':dict(statuses), 'interval_kinds':dict(interval_kinds),
               'history_identified':b.history.identified, 'history_censored':b.history.censored,
               'latest_training_step':max(b.history.last.values(),default=None),
               'mean_bridge_seconds':sum(times)/len(times), 'max_bridge_seconds':max(times),
               'actor_calls':0, 'native_market_replays':0, 'complete_games':0,
               'input_sha256':hashlib.sha256(decoded).hexdigest(),
               'final_phase_support': {p:b.history.window_prediction(p, rows[-1]['step'], rows[-1]['step'])['support']
                                       for p in D.engine.PRODUCTS if p not in ('WHEAT','FERTILIZER')}}
    return {'summary':summary, 'transitions':results}


def main():
    global D
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-loader',type=Path,required=True)
    parser.add_argument('--engine-cache',type=Path,required=True)
    parser.add_argument('--flow',type=Path,default=HERE/'flow.py')
    parser.add_argument('--fills',type=Path,default=HERE.parent/'cloud-observed-fills'/'observed_fills.py')
    parser.add_argument('--sorrel',type=Path,default=HERE/'vendor'/'sorrel_adapter.py')
    parser.add_argument('--subject',type=Path,default=HERE/'selected_action_history.py')
    parser.add_argument('--trace-input',type=Path)
    parser.add_argument('--unit-cases',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for name, expected in ENGINE_HASHES.items():
        assert hashlib.sha256((args.engine_cache/name).read_bytes()).hexdigest()==expected, name
    loader=load(args.engine_loader,'_cedar_native_loader')
    engine, hashes=loader.get_engine(args.engine_cache)
    D=NS(engine=engine, flow=load(args.flow,'_cedar_existing_flow'),
         fills=load(args.fills,'_cedar_existing_fills'),
         sorrel=load(args.sorrel,'_cedar_existing_sorrel'),
         subject=load(args.subject,'_cedar_selected_history'))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SelectedHistoryTests))
    report={'schema':'titan.selected-action-history.validation.v1',
            'tests':{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
                     'skips':len(result.skipped),'success':result.wasSuccessful()},
            'engine_hashes':hashes,'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (args.subject,args.flow,args.fills,args.sorrel,Path(__file__))},
            'counts':dict(COUNTS)}
    if result.wasSuccessful() and args.trace_input:
        if not args.unit_cases: parser.error('--trace-input requires --unit-cases')
        report['retained_trace']=consume_trace(args.trace_input,args.unit_cases)
        report['counts']=dict(COUNTS)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='retained_trace'},indent=2))
    if 'retained_trace' in report: print(json.dumps(report['retained_trace']['summary'],indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__': raise SystemExit(main())
