"""New fixed-flow scope tests; no AMBER mechanics suite or game-panel rerun."""
from __future__ import annotations
import argparse, copy, dataclasses, hashlib, json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cash_scope_audit import cash_products, inspect_cash_projection
from exhaustive_cash_scan import prepare, spec_for, path_at, canonical

STATE=None

class DimensionTests(unittest.TestCase):
    def offer(self,*orders):
        return SimpleNamespace(route_id='test',orders=[{'step':300,'slot':i,'order':o,'delta':0}
                                                      for i,o in enumerate(orders)])
    def audit(self,offers,rivals=None,products=('WOOL',),obs=None):
        s=STATE
        f=s.td.scenario_family(obs or s.obs,s.cfg,s.rules,products=products)
        return inspect_cash_projection(f,s.rules,offers,rival_orders=rivals)
    def test_wool_only_cash_uses_two_classes(self):
        r=self.audit([self.offer(['SELL','WOOL',3])])
        self.assertTrue(r['sufficient_for_fixed_flow_cash']);self.assertEqual(r['cash_signature_classes'],2)
    def test_mixed_cash_splits_wool_projection(self):
        r=self.audit([self.offer(['SELL','WOOL',3],['SELL','WHEAT',3])])
        self.assertFalse(r['sufficient_for_fixed_flow_cash']);self.assertIn('WHEAT',r['omitted_cash_products'])
    def test_zero_quantity_is_not_receipt_exposure(self):
        r=self.audit([self.offer(['SELL','WOOL',3],['SELL','WHEAT',0])])
        self.assertEqual(r['cash_relevant_products'],['WOOL']);self.assertTrue(r['sufficient_for_fixed_flow_cash'])
    def test_rival_cash_expands_closure(self):
        r=self.audit([self.offer(['SELL','WOOL',3])],{301:[['SELL','MILK',2]]})
        self.assertFalse(r['sufficient_for_fixed_flow_cash']);self.assertIn('MILK',r['cash_relevant_products'])
    def test_fixed_cost_uses_existing_offer_not_new_product(self):
        r=self.audit([self.offer(['BUY_ANIMAL','SHEEP',2],['HIRE'])])
        self.assertEqual(r['cash_relevant_products'],[]);self.assertEqual(r['cash_signature_classes'],1)
    def test_fertilizer_has_no_shop_demand_dimension(self):
        r=self.audit([self.offer(['BUY_PRODUCT','FERTILIZER',2])])
        self.assertTrue(r['sufficient_for_fixed_flow_cash']);self.assertEqual(r['cash_signature_classes'],1)
    def test_full_product_projection_is_sufficient_fixed_flow_only(self):
        r=self.audit(STATE.offers,products=STATE.rules.products)
        self.assertTrue(r['sufficient_for_fixed_flow_cash'])
        self.assertFalse(r['public_observations_interchangeable']);self.assertIsNone(r['probabilities'])
    def test_no_remaining_draws_removes_future_partition_issue(self):
        obs=copy.deepcopy(STATE.obs);obs['town']['unlocked_shops']=['BAKERY']*8
        r=self.audit(STATE.offers,obs=obs)
        self.assertTrue(r['sufficient_for_fixed_flow_cash']);self.assertEqual(r['cash_signature_sequences'],1)
    def test_malformed_quantities_rejected(self):
        for q in (True,-1,1.5,'1'):
            with self.subTest(q=q),self.assertRaises(ValueError):
                self.audit([self.offer(['SELL','WOOL',q])])
    def test_unknown_cash_product_rejected(self):
        with self.assertRaises(ValueError):self.audit([self.offer(['SELL','NOT_A_PRODUCT',1])])
    def test_dictionary_offer_and_order_are_not_mutated(self):
        o={'route_id':'x','orders':[{'order':['SELL','WOOL',3]}]};old=copy.deepcopy(o)
        self.audit([o]);self.assertEqual(o,old)
    def test_closure_is_in_source_product_order(self):
        o=self.offer(['SELL','WOOL',3],['SELL','MILK',2],['SELL','WOOL',1])
        self.assertEqual(cash_products([o],{},STATE.rules.products),('MILK','WOOL'))

class JoinedCashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s=STATE; n=len(s.family.unlock_after_steps)
        cls.specs=[spec_for(s,(name,)*n,'homogeneous-'+name) for name in s.shop_names]
        # Only static routes and existing quote/flow/rank consumers are used.
        before=canonical(s.raw)
        cls.result=s.rq.compare_saved_input(s.raw,cls.specs,s.deps,max_units=1_000_000,
                                           seconds=None,retain_trace=True)
        assert before==canonical(s.raw)
        cls.by={row[0]['scenario']:row for row in cls.result['flow']['rows']}
    def test_same_wool_schedule_does_not_imply_same_cash(self):
        s=STATE; n=len(s.family.unlock_after_steps)
        a=s.td.build_schedule(s.obs,s.cfg,s.rules,future_shops=['PET_CAFE']*n,products=['WOOL'])
        b=s.td.build_schedule(s.obs,s.cfg,s.rules,future_shops=['PIZZA_SHOP']*n,products=['WOOL'])
        self.assertEqual(a.rows,b.rows)
        ar=self.by['homogeneous-PET_CAFE'];br=self.by['homogeneous-PIZZA_SHOP']
        ag=ar[1]['final_marked_cash']-ar[0]['final_marked_cash']
        bg=br[1]['final_marked_cash']-br[0]['final_marked_cash']
        self.assertEqual((ag,bg),(-16964,-4868));self.assertEqual(bg-ag,12096)
    def test_all_no_yarn_schedules_equal_but_seven_cash_vectors_distinct(self):
        s=STATE;n=len(s.family.unlock_after_steps)
        rows=set();cash=set()
        for name in s.shop_names:
            if name=='YARN_STORE':continue
            rows.add(s.td.build_schedule(s.obs,s.cfg,s.rules,future_shops=[name]*n,products=['WOOL']).rows)
            a,b=self.by['homogeneous-'+name];cash.add((a['final_marked_cash'],b['final_marked_cash']))
        self.assertEqual((len(rows),len(cash)),(1,7))
    def test_actual_offers_need_eight_cash_classes(self):
        r=inspect_cash_projection(STATE.family,STATE.rules,STATE.offers)
        self.assertEqual((r['projected_signature_sequences'],r['cash_signature_sequences']),(32,32768))
        self.assertEqual(len(r['cash_relevant_products']),8)
        self.assertEqual(len(r['split_groups'][0]['cash_distinct_subgroups']),7)
    def test_peer_date_still_owns_ranking_and_receipts_reconcile(self):
        self.assertTrue(self.result['complete']);self.assertEqual(self.result['reconciled_route_scenarios'],16)
        self.assertEqual(self.result['ranking']['selected'],STATE.ids[0])
        self.assertEqual(self.result['actor_calls'],0);self.assertFalse(self.result['live_route_applied'])
    def test_same_wool_class_can_reverse_existing_date_choice(self):
        s=STATE
        specs=[spec_for(s,path_at(i,s.shop_names,len(s.family.unlock_after_steps)),'index-'+str(i))
               for i in (3584,20260)]
        report=s.rq.compare_saved_input(s.raw,specs,s.deps,max_units=1_000_000,seconds=None)
        self.assertEqual(report['individual_rankings'][0]['selected'],s.ids[1])
        self.assertEqual(report['individual_rankings'][1]['selected'],s.ids[0])
        self.assertEqual(report['ranking']['selected'],s.ids[0])
        a,b=[path_at(i,s.shop_names,len(s.family.unlock_after_steps)) for i in (3584,20260)]
        ar=s.td.build_schedule(s.obs,s.cfg,s.rules,future_shops=a,products=['WOOL'])
        br=s.td.build_schedule(s.obs,s.cfg,s.rules,future_shops=b,products=['WOOL'])
        self.assertEqual(ar.rows,br.rows)
        self.assertEqual([rows[1]['final_marked_cash']-rows[0]['final_marked_cash']
                          for rows in report['flow']['rows']],[2319,-1174])

    def test_cash_projection_refinement_preserves_observation_distinction(self):
        s=STATE
        family=s.td.scenario_family(s.obs,s.cfg,s.rules,products=cash_products(s.offers,{},s.rules.products))
        r=inspect_cash_projection(family,s.rules,s.offers)
        self.assertTrue(r['sufficient_for_fixed_flow_cash'])
        self.assertEqual(r['projected_signature_sequences'],32768)
        self.assertFalse(r['public_observations_interchangeable'])

    def test_declared_rival_products_cannot_be_hidden_by_own_only_closure(self):
        # This exact source's own scheduled program never sells TOMATO.
        s=STATE
        own=cash_products(s.offers,{},s.rules.products)
        paired=cash_products(s.offers,{300:[['SELL','TOMATO',1]]},s.rules.products)
        self.assertNotIn('TOMATO',own);self.assertIn('TOMATO',paired)
        self.assertEqual(set(paired),set(s.rules.products))

    def test_unknown_future_remains_declared_scenario_not_probability(self):
        self.assertTrue(all('not a prediction' in x['description'] for x in self.specs))
        r=inspect_cash_projection(STATE.family,STATE.rules,STATE.offers)
        self.assertIsNone(r['probabilities']);self.assertFalse(r['physical_feasibility_established'])
    def test_no_price_reconstruction_inputs_are_existing_peer_rows(self):
        for group in self.result['flow']['rows']:
            for row in group:
                self.assertEqual(row['rival_receipts'],0)
                self.assertEqual(row['rival_product_spend'],0)
                self.assertEqual(row['initial_cash'],8)
                self.assertEqual(row['minimum_marked_cash'],8)
                self.assertEqual(row['final_marked_cash'],8+row['own_receipts']-row['own_product_spend']-row['fixed_costs'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--osprey-root',type=Path,required=True)
    parser.add_argument('--amber-root',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();STATE=prepare(args.osprey_root,args.amber_root)
    suite=unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    names=[str(t) for subsuite in suite for t in subsuite]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    record={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'test_names':names,'scope':'12 dimension tests and 9 new joined cash-scope tests',
            'new_games':0,'actor_calls':0,'source_pins':STATE.deps.pins,
            'audit_sha256':hashlib.sha256(Path(__file__).with_name('cash_scope_audit.py').read_bytes()).hexdigest()}
    args.report.write_text(json.dumps(record,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
