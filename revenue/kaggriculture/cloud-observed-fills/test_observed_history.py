# SPDX-License-Identifier: Apache-2.0
"""Actual adaptive Agent history boundary, existing fills and official market.

The Agent class and inference functions are compiled verbatim from the supplied
source files. The parent and history sink are explicit boundary harnesses; no
full adaptive-agent gameplay, hidden state, new seed or policy score is claimed.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import time
import unittest

ROOT = Path(__file__).resolve().parent
PATHS = {}
ENGINE = LOADER = FILLS = SORREL = None
REPORT = {'market_cases': [], 'witnesses': []}
EXPECTED_ENGINE = {
    'kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def history_functions(path):
    parsed = ast.parse(path.read_text(), filename=str(path))
    nodes = [n for n in parsed.body if isinstance(n, ast.FunctionDef)
             and n.name in ('town_units', 'infer_rival_flow')]
    if len(nodes) != 2:
        raise ValueError('Expected the two original flow inference functions')
    ns = {'BUYABLE': {'WHEAT', 'FERTILIZER'}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return SimpleNamespace(**ns)


def action(*orders, farmer=('PASS',)):
    return {'farmer': list(farmer), 'hands': [], 'market': deepcopy(list(orders))}


def make_agent(path):
    """Verbatim Agent with named parent/recorder, actual fills/infer/quote."""
    class Parent:
        def __init__(self):
            self.last_packet = None
            self.action = action()
            self.calls = 0
            self.error = None
        def act(self, obs, cfg):
            self.calls += 1
            if self.error is not None:
                raise self.error
            return deepcopy(self.action)
    class History:
        def __init__(self): self.rows = []
        def add(self, row): self.rows.append(row)
    captured = []
    def infer(*args, **kwargs):
        result = SORREL.infer_rival_flow(*args, **kwargs)
        captured.append({'orders': deepcopy(args[2]), 'sale_receipts': deepcopy(kwargs.get('own_sale_units')),
                         'buy_receipts': deepcopy(kwargs.get('own_buy_units')), 'result': deepcopy(result)})
        return result
    sale = SimpleNamespace(optimize_lot=lambda **kw: ((), {}),
                           PRODUCTS=set(ENGINE.PRODUCTS),
                           _sell=lambda o, item=None: isinstance(o, list) and len(o) >= 3
                           and o[0] == 'SELL' and (item is None or o[1] == item))
    ns = dict(deepcopy=deepcopy, RLock=RLock, fills=FILLS, sale=sale,
              integrated=SimpleNamespace(IntegratedSelectedAgent=Parent),
              flow=SimpleNamespace(FlowHistory=History, FlowInterval=lambda *row: row),
              sorrel=SimpleNamespace(infer_rival_flow=infer), math=SimpleNamespace(m=ENGINE))
    parsed = ast.parse(path.read_text(), filename=str(path))
    nodes = [n for n in parsed.body if isinstance(n, ast.ClassDef) and n.name == 'Agent'
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name)
             and t.id in ('_OPTIMIZE_LOT', '_CAPTURE_LOCK') for t in n.targets)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    agent = ns['Agent'](mode='baseline')
    return agent, captured


def market_case(seat=0, *, shed=None, carry=None, orders=(), rival_orders=(),
                rival_shed=None, money=1000, step=17, capacity=100, slots=10,
                farmer=('PASS',), floor=False, shops=()):
    e, S = ENGINE, LOADER.Struct
    cfg = S(boardSize=10, shedCapacity=capacity, maxMarketOrdersPerTurn=slots,
            farmHandCostMult=1, turnsPerDay=24)
    farms = [e._new_farm(10, money) for _ in range(2)]
    privates = [e._new_private() for _ in range(2)]
    privates[seat]['shed'].update(shed or {})
    privates[seat]['inventories'][0].update(carry or {})
    privates[1-seat]['shed'].update(rival_shed or {})
    market = e._new_market()
    if floor: market['inventory']['STRAWBERRY'] = 20000
    town = {'unlocked_shops': list(shops)}
    own = action(*orders, farmer=farmer)
    states = [S(observation=S(player=i, step=step, day=step//24, hour=step%24,
                              farms=farms, private=privates[i], market=market, town=town),
                action=own if i == seat else action(*rival_orders), status='ACTIVE', reward=0)
              for i in (0, 1)]
    before = deepcopy(states[seat].observation)
    e._apply_unit_action(farms[seat], privates[seat], 0, own['farmer'], 10, step//24, 24, capacity)
    post = deepcopy(states[seat].observation)
    packet = {'projection': {'observed_step': step}, 'post_unit_observation': post}
    env = S(configuration=cfg, done=False, info={})
    e._process_market(states, env)
    e._town_consume(env, states, step)
    if (step+1) % 24 == 0:
        e._drop_inventories_to_shed(privates[seat], capacity)
    after = deepcopy(states[seat].observation)
    after.update(step=step+1, day=(step+1)//24, hour=(step+1)%24)
    REPORT['market_cases'].append({'seat': seat, 'step': step, 'orders': deepcopy(own['market']),
        'rival_orders': deepcopy(list(rival_orders)), 'before_shed': deepcopy(before['private']['shed']),
        'post_unit_shed': deepcopy(post['private']['shed']), 'next_shed': deepcopy(after['private']['shed']),
        'own_cash': farms[seat]['money'], 'rival_cash': farms[1-seat]['money']})
    return before, after, own, packet, cfg


def exercise(case, *, packet_kind='current', runtime=None):
    before, after, own, packet, cfg = deepcopy(case)
    if packet_kind == 'missing': packet = None
    elif packet_kind == 'stale':
        packet['projection']['observed_step'] -= 1
        packet['post_unit_observation']['step'] -= 1
        packet['post_unit_observation']['private']['shed'] = {}
    elif packet_kind == 'other_actor':
        packet['post_unit_observation']['player'] = 1-before['player']
    agent, captured = make_agent(runtime or PATHS['runtime'])
    agent.parent.action = own
    agent.parent.last_packet = packet
    output = agent.act(before, cfg)
    if output != own or agent.parent.calls != 1:
        raise AssertionError('History change altered action or invoked parent again')
    start = time.perf_counter()
    agent.observe(after, cfg)
    latency = (time.perf_counter()-start)*1000
    return agent, captured, latency


class ObservedHistoryTests(unittest.TestCase):
    def test_missing_post_unit_preserves_requests_not_false_rival(self):
        for seat in (0, 1):
            case = market_case(seat, carry={'EGG':3}, orders=[['SELL','EGG',3]], farmer=('DROP',))
            _, rows, _ = exercise(case, packet_kind='missing')
            self.assertEqual(rows[-1]['orders'], case[2]['market'])
            self.assertEqual(rows[-1]['sale_receipts'], {})
            self.assertEqual(rows[-1]['result']['products']['EGG']['rival_sale_units_range'], [0,3])

    def test_stale_packet_not_reused(self):
        for seat in (0, 1):
            case = market_case(seat, carry={'EGG':3}, orders=[['SELL','EGG',3]], farmer=('DROP',))
            _, rows, _ = exercise(case, packet_kind='stale')
            self.assertEqual(rows[-1]['sale_receipts'], {})
            self.assertEqual(rows[-1]['result']['products']['EGG']['rival_sale_units_range'], [0,3])

    def test_actual_post_unit_sale_identifies_zero_rival(self):
        for seat in (0, 1):
            case = market_case(seat, carry={'EGG':3}, orders=[['SELL','EGG',3]], farmer=('DROP',))
            agent, rows, ms = exercise(case)
            self.assertEqual(rows[-1]['sale_receipts'], {'EGG':3})
            self.assertEqual(rows[-1]['result']['products']['EGG']['rival_sale_units_range'], [0,0])
            self.assertIsNone(agent.last_fill['cash_receipts'])
            REPORT['witnesses'].append({'case':'current_post_unit_drop_sale','seat':seat,
                'sale_receipts':rows[-1]['sale_receipts'],'rival_range':[0,0],'history_ms':ms})

    def test_buy_request_and_observed_fill_reach_flow(self):
        for seat in (0, 1):
            case = market_case(seat, orders=[['BUY_PRODUCT','WHEAT',2]])
            _, rows, _ = exercise(case)
            self.assertEqual(rows[-1]['orders'], case[2]['market'])
            self.assertEqual(rows[-1]['buy_receipts'], {'WHEAT':2})
            self.assertEqual(rows[-1]['result']['products']['WHEAT']['rival_net_market_flow_range'], [0,0])

    def test_unknown_buy_is_a_range_not_exact_zero(self):
        case = market_case(orders=[['BUY_PRODUCT','WHEAT',2]])
        _, rows, _ = exercise(case, packet_kind='missing')
        self.assertEqual(rows[-1]['buy_receipts'], {})
        self.assertEqual(rows[-1]['result']['products']['WHEAT']['own_buy_units_range'], [0,2])
        self.assertEqual(rows[-1]['result']['products']['WHEAT']['rival_net_market_flow_range'], [-2,0])

    def test_round_trip_stays_unknown(self):
        for money in (0, 1000):
            case = market_case(orders=[['BUY_PRODUCT','WHEAT',1],['SELL','WHEAT',1]], money=money)
            agent, rows, _ = exercise(case)
            self.assertEqual(agent.last_fill['status'], 'ambiguous')
            self.assertEqual(rows[-1]['buy_receipts'], {})
            self.assertEqual(rows[-1]['sale_receipts'], {})
            self.assertEqual(rows[-1]['result']['products']['WHEAT']['rival_net_market_flow_range'], [-1,1])

    def test_duplicate_slots_preserved_and_exact_counts_aggregate(self):
        case = market_case(shed={'EGG':3}, orders=[['SELL','EGG',2],['HIRE'],['SELL','EGG',2]])
        _, rows, _ = exercise(case)
        self.assertEqual(rows[-1]['orders'], case[2]['market'])
        self.assertEqual(rows[-1]['sale_receipts'], {'EGG':3})

    def test_slots_beyond_limit_never_become_fills(self):
        case = market_case(shed={'EGG':3}, orders=[['HIRE'],['SELL','EGG',3]], slots=1)
        _, rows, _ = exercise(case)
        self.assertEqual(rows[-1]['orders'], case[2]['market'])
        self.assertEqual(rows[-1]['sale_receipts'], {'EGG':0})
        self.assertEqual(rows[-1]['result']['products']['EGG']['rival_sale_units_range'], [0,0])

    def test_eod_carried_stock_is_not_a_market_purchase(self):
        for seat in (0, 1):
            case = market_case(seat, step=23, shed={'EGG':2}, carry={'EGG':4}, orders=[['SELL','EGG',2]])
            _, rows, _ = exercise(case)
            self.assertEqual(rows[-1]['sale_receipts'], {'EGG':2})
            self.assertEqual(rows[-1]['result']['products']['EGG']['rival_sale_units_range'], [0,0])

    def test_eod_missing_inventories_remains_unknown(self):
        case = market_case(step=23, shed={'EGG':2}, carry={'EGG':4}, orders=[['SELL','EGG',2]])
        case[3]['post_unit_observation']['private'].pop('inventories')
        agent, rows, _ = exercise(case)
        self.assertEqual(agent.last_fill['reason'], 'after_market_deposits_unknown')
        self.assertEqual(rows[-1]['sale_receipts'], {})

    def test_floor_sale_not_market_supply_receipt(self):
        for seat in (0, 1):
            case = market_case(seat, shed={'STRAWBERRY':3}, orders=[['SELL','STRAWBERRY',3]], floor=True)
            _, rows, _ = exercise(case)
            self.assertEqual(rows[-1]['sale_receipts'], {'STRAWBERRY':3})
            row=rows[-1]['result']['products']['STRAWBERRY']
            self.assertEqual(row['own_market_supply_units_range'], [0,3])
            self.assertTrue(row['floor_nonadmission_possible'])

    def test_actual_rival_still_identified(self):
        for seat in (0, 1):
            case=market_case(seat,shed={'EGG':3},orders=[['SELL','EGG',3]],
                             rival_shed={'EGG':2},rival_orders=[['SELL','EGG',2]])
            _,rows,_=exercise(case)
            self.assertEqual(rows[-1]['result']['products']['EGG']['rival_sale_units_range'],[2,2])

    def test_observe_retries_do_not_duplicate_history(self):
        case=market_case(shed={'EGG':1},orders=[['SELL','EGG',1]])
        agent,rows,_=exercise(case)
        count=len(agent.history.rows)
        agent.observe(case[1],case[4])
        self.assertEqual(len(rows),1)
        self.assertEqual(len(agent.history.rows),count)

    def test_same_step_waits_for_adjacent_observation(self):
        case=market_case(shed={'EGG':1},orders=[['SELL','EGG',1]])
        agent,rows=make_agent(PATHS['runtime'])
        agent.parent.action=case[2];agent.parent.last_packet=case[3]
        agent.act(case[0],case[4]);agent.observe(case[0],case[4])
        self.assertFalse(rows)
        agent.observe(case[1],case[4]);self.assertEqual(len(rows),1)

    def test_nonadjacent_and_other_actor_do_not_enter_history(self):
        for field,value in (('step',30),('player',1)):
            case=market_case()
            case[1][field]=value
            agent,rows,_=exercise(case)
            self.assertFalse(rows);self.assertFalse(agent.history.rows)

    def test_wrong_actor_post_unit_packet_is_not_accepted(self):
        case=market_case(shed={'EGG':3},orders=[['SELL','EGG',3]])
        _,rows,_=exercise(case,packet_kind='other_actor')
        self.assertEqual(rows[-1]['sale_receipts'],{})

    def test_snapshot_contradiction_uses_requested_bounds(self):
        case=market_case(shed={'EGG':3},orders=[['SELL','EGG',3]])
        case[1]['private']['shed']['EGG']=1
        agent,rows,_=exercise(case)
        self.assertEqual(agent.last_fill['reason'],'observed_shed_not_explained')
        self.assertEqual(rows[-1]['sale_receipts'],{})

    def test_correlated_ambiguous_product_not_partly_summed(self):
        Agent=make_agent(PATHS['runtime'])[0].__class__
        rows={'status':'ambiguous','orders':[
            {'type':'SELL','item':'EGG','fill_min':1,'fill_max':1},
            {'type':'SELL','item':'EGG','fill_min':0,'fill_max':2},
            {'type':'SELL','item':'MILK','fill_min':2,'fill_max':2}]}
        self.assertEqual(Agent._exact_fills(rows,'SELL'),{'MILK':2})

    def test_configuration_and_final_action_are_detached(self):
        case=market_case(shed={'EGG':3},orders=[['SELL','EGG',3]])
        agent,rows=make_agent(PATHS['runtime'])
        agent.parent.action=case[2];agent.parent.last_packet=case[3]
        original=deepcopy(case)
        output=agent.act(case[0],case[4]);output['market'][0][2]=999
        case[2]['market'][0][2]=999;case[3]['post_unit_observation']['private']['shed']['EGG']=999
        current_cfg=deepcopy(case[4]);current_cfg['shedCapacity']=1
        agent.observe(case[1],current_cfg)
        self.assertEqual(rows[-1]['orders'],original[2]['market'])
        self.assertEqual(rows[-1]['sale_receipts'],{'EGG':3})
        self.assertEqual(REPORT['market_cases'][-1]['orders'],original[2]['market'])

    def test_invalid_queue_never_retries_the_parent(self):
        case=market_case()
        case[2]['market']=[['SELL','EGG','invalid']]
        agent,rows,_=exercise(case)
        self.assertEqual(agent.parent.calls,1)
        self.assertEqual(agent.last_flow['reason'],'invalid_flow_inputs')

    def test_terminal_market_does_not_invent_final_deposit(self):
        case=market_case(step=718,shed={'EGG':1},carry={'EGG':3},orders=[['SELL','EGG',2]])
        _,rows,_=exercise(case)
        self.assertEqual(rows[-1]['sale_receipts'],{'EGG':1})

    def test_funding_uncertainty_budget_remains_unknown(self):
        case=market_case(capacity=100,orders=[['BUY_PRODUCT','WHEAT',100],['BUY_PRODUCT','FERTILIZER',100]])
        agent,rows,_=exercise(case)
        self.assertEqual(agent.last_fill['status'],'unknown')
        self.assertIn(agent.last_fill['reason'],('state_budget_exceeded','transition_budget_exceeded'))
        self.assertEqual(rows[-1]['buy_receipts'],{})

    def test_records_final_transform_queue_not_parent_queue(self):
        case=market_case(shed={'EGG':3},orders=[['SELL','EGG',1]])
        agent,rows=make_agent(PATHS['runtime'])
        case[3]['arrival_contract']=None
        agent.parent.action=action(['SELL','EGG',3]);agent.parent.last_packet=case[3]
        # Explicit action-stage harness: it selects the already engine-executed
        # final action, without claiming a recourse optimization in this fixture.
        agent._parent_action.__globals__['sale'].ProjectionLedger=lambda *a: object()
        agent.transformer=SimpleNamespace(selector=SimpleNamespace(active={'key':'test'}),
            counts={'projection_fallbacks':0,'admissions':0}, last={'reason':'test_action_stage'},
            transform=lambda *a,**kw:deepcopy(case[2]))
        self.assertEqual(agent.act(case[0],case[4]),case[2])
        agent.observe(case[1],case[4])
        self.assertEqual(agent.parent.calls,1)
        self.assertEqual(rows[-1]['orders'],case[2]['market'])
        self.assertEqual(rows[-1]['sale_receipts'],{'EGG':1})

    def test_wrong_actor_read_does_not_consume_pending_evidence(self):
        case=market_case(shed={'EGG':2},orders=[['SELL','EGG',2]])
        agent,rows=make_agent(PATHS['runtime'])
        agent.parent.action=case[2];agent.parent.last_packet=case[3]
        agent.act(case[0],case[4])
        wrong=deepcopy(case[1]);wrong['player']=1
        agent.observe(wrong,case[4]);self.assertFalse(rows)
        agent.observe(case[1],case[4])
        self.assertEqual(rows[-1]['sale_receipts'],{'EGG':2})

    def test_second_actor_has_independent_history_and_fills(self):
        case=market_case(shed={'EGG':2},orders=[['SELL','EGG',2]])
        left,lrows=make_agent(PATHS['runtime']);right,rrows=make_agent(PATHS['runtime'])
        left.parent.action=case[2];left.parent.last_packet=case[3]
        left.act(case[0],case[4]);left.observe(case[1],case[4])
        self.assertTrue(lrows);self.assertFalse(rrows)
        self.assertIsNone(right.fill_ledger);self.assertIsNone(right.previous)

    def test_no_packet_boundary_does_not_require_fill_import_or_player(self):
        agent,rows=make_agent(PATHS['runtime'])
        namespace=agent._parent_action.__globals__;namespace.pop('fills')
        observation={'step':650,'private':{'shed':{}},'market':{'inventory':{}}}
        self.assertEqual(agent.act(observation,{}),action())
        self.assertEqual(agent.parent.calls,1)

    def test_known_town_consumption_remains_original_inference(self):
        for seat in (0,1):
            case=market_case(seat,step=20,shed={'EGG':3},orders=[['SELL','EGG',3]],shops=['BAKERY'])
            _,rows,_=exercise(case)
            self.assertEqual(rows[-1]['result']['products']['EGG']['rival_sale_units_range'],[0,0])

    def test_parent_exception_propagates_once_and_capture_is_restored(self):
        agent,_=make_agent(PATHS['runtime'])
        failure=TypeError('parent body witness');agent.parent.error=failure
        with self.assertRaises(TypeError) as caught:agent.act({'step':17}, {})
        self.assertIs(caught.exception,failure)
        self.assertEqual(agent.parent.calls,1)
        self.assertIs(agent._parent_action.__globals__['sale'].optimize_lot,agent.original)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--original-runtime',type=Path)
    parser.add_argument('--fills',type=Path,required=True)
    parser.add_argument('--flow-adapter',type=Path,required=True)
    parser.add_argument('--engine-loader',type=Path,required=True)
    parser.add_argument('--engine-cache',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    PATHS.update(vars(args))
    global ENGINE,LOADER,FILLS,SORREL
    hashes={n:hashlib.sha256((args.engine_cache/n).read_bytes()).hexdigest() for n in EXPECTED_ENGINE}
    if hashes!=EXPECTED_ENGINE:raise SystemExit('Existing engine cache has a different source pin')
    LOADER=load_module(args.engine_loader,'history_existing_loader')
    ENGINE,actual=LOADER.get_engine(args.engine_cache)
    if actual!=EXPECTED_ENGINE:raise SystemExit('Loader source hashes differ')
    FILLS=load_module(args.fills,'history_actual_fills')
    SORREL=history_functions(args.flow_adapter)
    if args.original_runtime:
        # One actual engine transition per seat is reused by both runtime versions.
        for seat in (0,1):
            case=market_case(seat,carry={'EGG':3},orders=[['SELL','EGG',3]],farmer=('DROP',))
            for kind in ('missing','stale','current'):
                _,old,_=exercise(case,packet_kind=kind,runtime=args.original_runtime)
                _,new,_=exercise(case,packet_kind=kind)
                REPORT['witnesses'].append({'case':'drop_sale','seat':seat,'packet':kind,
                    'original_rival_range':old[-1]['result']['products']['EGG']['rival_sale_units_range'],
                    'corrected_rival_range':new[-1]['result']['products']['EGG']['rival_sale_units_range']})
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ObservedHistoryTests))
    REPORT.update(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        skipped=len(result.skipped),success=result.wasSuccessful(),full_games=0,
        engine_sha256=hashes,market_executions=len(REPORT['market_cases']),
        sources={key:hashlib.sha256(value.read_bytes()).hexdigest() for key,value in PATHS.items()
                 if isinstance(value,Path) and value.is_file() and key!='report'})
    flow_nodes=[n for n in ast.parse(args.flow_adapter.read_text()).body
                if isinstance(n,ast.FunctionDef) and n.name in ('town_units','infer_rival_flow')]
    REPORT['flow_function_ast_sha256']=hashlib.sha256(ast.dump(
        ast.Module(body=flow_nodes,type_ignores=[]),include_attributes=False).encode()).hexdigest()
    args.report.write_text(json.dumps(REPORT,sort_keys=True,indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
