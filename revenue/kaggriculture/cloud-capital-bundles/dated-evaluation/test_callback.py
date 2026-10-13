# SPDX-License-Identifier: Apache-2.0
import copy, json, unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from pathlib import Path
from dated_callback import choose_dated
from probe_support import dependencies,scenario_family,HERE,BASE,load

class BoundaryTests(unittest.TestCase):
 def setUp(self):
  self.ctrl=NS(cur='base')
  self.offers=[NS(route_id='base'),NS(route_id='alt')]
  def seam(c,o,cfg,m,selector):
   c.cur=selector(self.offers,o);return {'after':c.cur}
  self.h=NS(choose_before_action=seam)
  self.f=NS(evaluate_scenarios=Mock(return_value={'complete':True,'rows':[1]}),as_cash_scenarios=Mock(return_value=[1]))
  self.rank=Mock(return_value='alt');self.rank.last_report={'selected':'alt'}
  self.d=NS(CashScenario=object,DatedSelector=Mock(return_value=self.rank))
 def call(self,**kw):
  return choose_dated(self.ctrl,{}, {},None,hazel=self.h,flow=self.f,date=self.d,scenarios=[1],**kw)
 def test_calls_existing_seam_once(self):
  r=self.call();self.assertEqual(self.ctrl.cur,'alt');self.assertTrue(r['changed']);self.rank.assert_called_once()
 def test_incomplete_retains_incumbent(self):
  self.f.evaluate_scenarios.return_value={'complete':False,'reason':'incomplete_budget','rows':[]}
  r=self.call();self.assertEqual(self.ctrl.cur,'base');self.d.DatedSelector.assert_not_called()
 def test_zero_budget_skips_model(self):
  r=self.call(seconds=0);self.assertEqual(r['model']['reason'],'quotation_budget');self.f.evaluate_scenarios.assert_not_called()
 def test_late_final_rank_retains_incumbent(self):
  with patch('dated_callback.time.perf_counter',side_effect=[0,0,2,2]):r=self.call(seconds=1)
  self.assertEqual(self.ctrl.cur,'base');self.assertTrue(r['late']);self.assertFalse(r['changed'])
 def test_cancellation_not_retried(self):
  self.f.evaluate_scenarios.side_effect=KeyboardInterrupt()
  with self.assertRaises(KeyboardInterrupt):self.call()
  self.assertEqual(self.ctrl.cur,'base')
 def test_no_parent_needed(self):
  self.assertFalse(hasattr(self.ctrl,'act'));self.call()

class ActualSourceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.h,cls.f,cls.d=dependencies()
  cls.m=load(BASE/'cloud-titan-composition/vendor/sell/mechanics.py','test_probe_mechanics')
  cls.p=load(BASE/'cloud-titan-composition/vendor/sell/reference/next-panel/vendor/arlene.py','test_probe_arlene')
  cls.row=json.loads((HERE/'sources/quote/evidence/saved-226-row.json').read_text())
 def observation(self):
  # This is the original recorded delivered observation, not a restored actor.
  return copy.deepcopy(self.row['observation']),copy.deepcopy(self.row['configuration'])
 def test_real_quote_and_dated_disagree_at_saved_state(self):
  obs,cfg=self.observation();ctrl=self.p.Agent();before=copy.deepcopy(ctrl.R)
  ctrl.act=Mock(side_effect=AssertionError('parent must not be called'))
  r=choose_dated(ctrl,obs,cfg,self.m,hazel=self.h,flow=self.f,date=self.d,scenarios=scenario_family('dated_two',self.f),seconds=2)
  self.assertEqual(ctrl.cur,self.h.MAIN);self.assertEqual(ctrl.R,before);ctrl.act.assert_not_called()
  cand=r['ranking']['candidates'][self.h.SHEEP]
  self.assertEqual(cand['worst_paired_gain'],-5042)
  self.assertEqual(r['outer']['marked_delta'],7517)
 def test_native_input_not_mutated(self):
  obs,cfg=self.observation();before=copy.deepcopy((obs,cfg));ctrl=self.p.Agent()
  choose_dated(ctrl,obs,cfg,self.m,hazel=self.h,flow=self.f,date=self.d,scenarios=scenario_family('dated_existing',self.f),seconds=2)
  self.assertEqual((obs,cfg),before)
 def test_outside_checkpoint_no_model(self):
  obs,cfg=self.observation();obs['step']=225;ctrl=self.p.Agent()
  with patch.object(self.f,'evaluate_scenarios',side_effect=AssertionError('no model')):
   r=choose_dated(ctrl,obs,cfg,self.m,hazel=self.h,flow=self.f,date=self.d,scenarios=(),seconds=2)
  self.assertIsNone(r['model']);self.assertEqual(ctrl.cur,self.h.MAIN)
 def test_missing_scenario_keeps_current(self):
  obs,cfg=self.observation();ctrl=self.p.Agent()
  r=choose_dated(ctrl,obs,cfg,self.m,hazel=self.h,flow=self.f,date=self.d,scenarios=(),seconds=2)
  self.assertFalse(r['changed']);self.assertFalse(r['model']['complete'])
 def test_budget_no_partial_ranking(self):
  obs,cfg=self.observation();ctrl=self.p.Agent()
  r=choose_dated(ctrl,obs,cfg,self.m,hazel=self.h,flow=self.f,date=self.d,scenarios=scenario_family('dated_two',self.f),max_units=1,seconds=2)
  self.assertIsNone(r['ranking']);self.assertFalse(r['changed'])
 def test_full_state_is_required_for_game_claim(self):
  # A fixture can exercise the seam; it does not reconstruct historical state.
  self.assertEqual(self.row['observation']['step'],226)
  self.assertEqual(self.row['seat'],0)

if __name__=='__main__':unittest.main(verbosity=2)
