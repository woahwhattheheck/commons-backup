"""Actual whole-queue consumer checks; no scored game or policy invocation."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import engine_cases
import queue_response

HERE=Path(__file__).resolve().parent
KAG=HERE.parents[1]
QUEUE=Path(os.environ.get('TITAN_QUEUE_SOURCE', KAG/'cloud-market-queue-delta/queue_delta.py'))
ENGINE=Path(os.environ.get('TITAN_ENGINE', KAG/'cloud-policy-portfolio/vendor/engine'))


class QueueResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue=engine_cases.load(QUEUE, 'iris_existing_queue_delta')
        cls.mechanics=cls.queue.load_market_engine(ENGINE/'kaggriculture.py')
        cls.base=json.loads((HERE/'base-frame.json').read_text())

    def make_case(self, own=0):
        obs=copy.deepcopy(self.base['observation'])
        obs.update(day=29,hour=1,step=697,player=own)
        rival=1-own
        tiles=[dict(kind='PASTURE',animal='COW') for _ in range(9)]
        tiles += [dict(kind='PLANT',crop='WHEAT') for _ in range(20)]
        tiles += [dict(kind='WEED') for _ in range(71)]
        obs['farms'][rival].update(money=1000.0,hires_today=6,hands=[[4,4] for _ in range(6)],
                                  tiles=[tiles[i:i+10] for i in range(0,100,10)],
                                  unlocked_quadrants=['NW','NE','SW','SE'])
        private=copy.deepcopy(obs['private']);private['shed']['WHEAT']=50
        action={'farmer':['PASS'],'hands':[], 'market':[['SELL','WHEAT',50]]}
        scenarios=[]
        for name,stock,order in [('buyer',0,['BUY_PRODUCT','WHEAT',15]),('seller',50,['SELL','WHEAT',50])]:
            rp=copy.deepcopy(obs['private']);rp['inventories']=[{} for _ in range(7)];rp['shed']['WHEAT']=stock
            scenarios.append(dict(id=name,provenance='Manufactured correlated scenario, not observed rival stock',
                farm=copy.deepcopy(obs['farms'][rival]),private=rp,
                action={'market':[['HIRE'] for _ in range(5)]+[order]}))
        return dict(observation=obs,configuration=copy.deepcopy(self.base['configuration']),
            selected_action=action,own_farm=copy.deepcopy(obs['farms'][own]),
            own_private=private,market=copy.deepcopy(obs['market']),scenarios=scenarios,retained_wheat=0)

    def run_case(self, args, compare=None):
        return queue_response.evaluate_wheat_response(compare or self.queue.compare_queues,self.mechanics,**args)

    def test_buyer_and_seller_are_compared_without_automatic_selection(self):
        for own in (0,1):
            args=self.make_case(own);result=self.run_case(args)
            self.assertEqual(result['status'],'complete_conditional')
            self.assertFalse(result['action_selected'])
            self.assertEqual(result['fallback_action'],args['selected_action'])
            self.assertIsNotNone(result['proposal_action'])
            rows=result['comparison']['scenario_results']
            self.assertGreater(rows[0]['delta']['own_cash'],0)
            self.assertLess(rows[1]['delta']['own_cash'],0)
            self.assertLess(result['comparison']['bounds']['relative_cash']['min'],0)
            self.assertGreater(result['comparison']['bounds']['relative_cash']['max'],0)

    def test_exact_direct_comparator_equivalence(self):
        for own in (0,1):
            args=self.make_case(own);result=self.run_case(args)
            direct=self.queue.compare_queues(self.mechanics,step=697,seat=own,
                own_farm=args['own_farm'],own_private=args['own_private'],market=args['market'],
                baseline_action=args['selected_action'],proposed_action=result['proposal_action'],
                scenarios=args['scenarios'],configuration=args['configuration'])
            a=copy.deepcopy(result['comparison']);b=copy.deepcopy(direct)
            a.pop('elapsed_seconds');b.pop('elapsed_seconds')
            self.assertEqual(a,b)

    def test_one_existing_comparator_call_and_unchanged_inputs(self):
        args=self.make_case();original=copy.deepcopy(args);calls=[]
        def observed(*a,**kw):
            calls.append(kw)
            return self.queue.compare_queues(*a,**kw)
        result=self.run_case(args,observed)
        self.assertEqual(len(calls),1)
        self.assertEqual(args,original)
        self.assertEqual(calls[0]['baseline_action']['farmer'],calls[0]['proposed_action']['farmer'])
        self.assertEqual(calls[0]['baseline_action']['hands'],calls[0]['proposed_action']['hands'])
        self.assertEqual(result['proposal_action']['market'][0],['PASS'])
        self.assertEqual(result['proposal_action']['market'][6],['SELL','WHEAT',50])

    def test_expired_deadline_exposes_no_candidate(self):
        args=self.make_case();args['deadline']=time.monotonic()-1
        result=self.run_case(args)
        self.assertEqual(result['status'],'unknown')
        self.assertEqual(result['comparison']['reason'],'deadline')
        self.assertIsNone(result['proposal_action']);self.assertIsNone(result['comparison']['bounds'])
        self.assertEqual(result['fallback_action'],args['selected_action'])

    def test_partial_real_execution_is_not_a_ranking(self):
        args=self.make_case();args['deadline']=1.0
        ticks=[0]
        def clock():
            ticks[0]+=1
            return 0.0 if ticks[0]<=22 else 2.0
        with patch.object(self.queue.time,'monotonic',side_effect=clock):
            result=self.run_case(args)
        self.assertEqual(result['status'],'unknown')
        self.assertEqual(len(result['comparison']['scenario_results']),1)
        self.assertIsNone(result['comparison']['bounds'])
        self.assertIsNone(result['proposal_action'])
        self.assertEqual(result['fallback_action'],args['selected_action'])

    def test_scenario_work_and_order_bounds_are_forwarded(self):
        for name,value,reason in [('max_scenarios',1,'scenario_budget'),('max_unit_steps',0,'unit_work_budget'),('max_orders_budget',1,'order_budget')]:
            args=self.make_case();args[name]=value
            result=self.run_case(args)
            self.assertEqual(result['comparison']['reason'],reason)
            self.assertIsNone(result['proposal_action'])

    def test_reservation_leaves_original_complete_action(self):
        args=self.make_case();args['retained_wheat']=1
        result=self.run_case(args)
        self.assertEqual(result['status'],'unchanged')
        self.assertIsNone(result['comparison'])
        self.assertEqual(result['fallback_action'],args['selected_action'])

    def test_public_unknown_does_not_call_comparator(self):
        args=self.make_case();del args['observation']['farms'][1]['money']
        def unreachable(*a,**kw):raise AssertionError('Comparator was reached')
        result=self.run_case(args,unreachable)
        self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['comparison'])

    def test_incomplete_scenario_preserves_whole_fallback(self):
        args=self.make_case();args['scenarios'][0].pop('private')
        result=self.run_case(args)
        self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['proposal_action'])
        self.assertIsNone(result['comparison']['bounds'])
        self.assertEqual(result['fallback_action'],args['selected_action'])

    def test_detached_results(self):
        args=self.make_case();original=copy.deepcopy(args);result=self.run_case(args)
        result['comparison']['scenario_results'][0]['baseline']['rival_private']['shed']['WHEAT']=999
        result['proposal_action']['market'][6][2]=999
        result['fallback_action']['market'][0][2]=999
        self.assertEqual(args,original)

    def test_selected_non_sale_queue_and_public_negative_remain_unchanged(self):
        for mode in ('mixed','late','cash','staff'):
            args=self.make_case()
            if mode=='mixed':args['selected_action']['market'].append(['HIRE'])
            elif mode=='late':args['observation']['hour']=3
            elif mode=='cash':args['observation']['farms'][1]['money']=40
            else:args['observation']['farms'][1]['hands']=[[4,4] for _ in range(11)]
            result=self.run_case(args)
            self.assertEqual(result['status'],'unchanged')
            self.assertIsNone(result['comparison']);self.assertIsNone(result['proposal_action'])

    def test_comparison_cancellation_is_not_swallowed(self):
        args=self.make_case()
        class Cancelled(BaseException):pass
        def cancelled(*a,**kw):raise Cancelled()
        with self.assertRaises(Cancelled):self.run_case(args,cancelled)


if __name__=='__main__':unittest.main(verbosity=2)
