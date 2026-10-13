# SPDX-License-Identifier: MIT
"""Changed-path tests for joining the existing T12 history, not a new predictor."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from joint_terminal_history import build_joint_terminal_scenarios as build

# Works in repository layout; --flow supports an exact external source cache.
def load_flow(path):
    spec = importlib.util.spec_from_file_location('_joint_history_flow', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

FLOW = None
NOW = 718


def history(rows=None, minimum=3, window=5):
    h = FLOW.FlowHistory(minimum=minimum, window=window)
    rows = rows or {1:{'CARROT':10,'WOOL':1}, 2:{'CARROT':1,'WOOL':10},
                    3:{'CARROT':5,'WOOL':5}}
    for lag in sorted(rows, reverse=True):
        for p,q in rows[lag].items():
            if q is not None:
                h.add(FLOW.FlowInterval(NOW-24*lag,p,q,q,q,q,'identified'))
    return h


def template(slots=('CARROT',None,'WOOL'), name='explicit-order'):
    return {'id':name,'origin':'constructed finite slot hypothesis','slots':list(slots)}


def run(h=None, products=('CARROT','WOOL'), **kw):
    kw.setdefault('slot_templates',[template()])
    return build(h or history(), products, NOW, **kw)


class JointHistoryTests(unittest.TestCase):
    def test_same_lag_vectors_not_independent_quantiles(self):
        r=run();self.assertTrue(r['ready']);self.assertEqual(r['joint_support'],3)
        self.assertEqual({tuple(s['shed'][p] for p in ('CARROT','WOOL')) for s in r['scenarios']},
                         {(10,1),(1,10),(5,5)})
        self.assertNotIn({'CARROT':10,'WOOL':10},[s['shed'] for s in r['scenarios']])

    def test_disjoint_individual_support_is_not_joint_support(self):
        h=history({i:{'CARROT':i} if i<=3 else {'WOOL':i} for i in range(1,7)},window=6)
        r=run(h);self.assertFalse(r['ready']);self.assertEqual(r['product_support'],{'CARROT':3,'WOOL':3})
        self.assertEqual(r['joint_support'],0);self.assertEqual(r['scenarios'],[])

    def test_only_intersection_counts_towards_minimum(self):
        h=history({1:{'CARROT':1},2:{'CARROT':2,'WOOL':2},3:{'CARROT':3,'WOOL':3},4:{'WOOL':4}})
        r=run(h);self.assertEqual(r['joint_support'],2);self.assertFalse(r['ready'])

    def test_censored_window_is_excluded_not_filled_with_zero(self):
        h=history({2:{'CARROT':1,'WOOL':2},3:{'CARROT':3,'WOOL':4}})
        h.add(FLOW.FlowInterval(694,'CARROT',0,100,0,2,'floor_censored'))
        h.add(FLOW.FlowInterval(694,'WOOL',2,2,2,2,'identified'))
        self.assertFalse(run(h)['ready']);self.assertEqual(run(h)['joint_support'],2)

    def test_zero_is_known_and_preserves_slot(self):
        h=history({i:{'CARROT':0,'WOOL':2} for i in (1,2,3)})
        r=run(h);self.assertEqual(len(r['scenarios']),1)
        self.assertEqual(r['scenarios'][0]['market'],[[],[],['SELL','WOOL',2]])
        self.assertEqual(r['scenarios'][0]['shed'],{'WOOL':2})

    def test_dedup_retains_whole_history_witnesses(self):
        h=history({i:{'CARROT':0,'WOOL':2} for i in (1,2,3)})
        r=run(h,slot_templates=[template(),template(name='another-label')])
        self.assertEqual(len(r['scenarios']),1)
        w=r['scenarios'][0]['origin']['witnesses'];self.assertEqual(len(w),6)
        self.assertEqual({x['lag'] for x in w},{1,2,3})
        self.assertTrue(all(x['training_start']==NOW-24*x['lag'] for x in w))

    def test_future_interval_never_joins_an_earlier_decision(self):
        h=history();before=run(h)
        for p in ('CARROT','WOOL'):
            h.add(FLOW.FlowInterval(718,p,40,40,40,40,'identified'))
        self.assertEqual(run(h),before)

    def test_no_templates_means_unidentified_order_not_assumed_order(self):
        self.assertEqual(run(slot_templates=None)['status'],'slot_order_unidentified')

    def test_operating_products_are_never_inferred_even_with_rows(self):
        h=history({i:{'CARROT':2,'WHEAT':7} for i in (1,2,3)})
        r=run(h,products=('CARROT','WHEAT'),slot_templates=[template(('CARROT','WHEAT'))])
        self.assertEqual(r['status'],'unobserved_stock_unspecified')
        self.assertEqual(r['observed_products'],['CARROT']);self.assertEqual(r['unobserved_products'],['WHEAT'])

    def test_explicit_unknown_zero_retains_provenance(self):
        r=run(products=('CARROT','WOOL','WHEAT','FERTILIZER'),
              unobserved_lots=[{'id':'quiet','origin':'explicit unobserved quiet hypothesis',
                                'stock':{'WHEAT':0,'FERTILIZER':0}}])
        self.assertTrue(r['ready']);self.assertIsNone(r['scenario_probabilities'])
        self.assertTrue(all(s['origin']['slot_order_identified'] is False for s in r['scenarios']))
        self.assertTrue(all(s['origin']['witnesses'][0]['unobserved_lot']=='quiet' for s in r['scenarios']))

    def test_completion_requires_all_unknown_fields(self):
        with self.assertRaises(ValueError):
            run(products=('CARROT','WOOL','WHEAT','FERTILIZER'),
                unobserved_lots=[{'id':'bad','origin':'fixture','stock':{'WHEAT':0}}])

    def test_completion_cannot_override_identified_quantity(self):
        with self.assertRaises(ValueError):
            run(unobserved_lots=[{'id':'bad','origin':'fixture','stock':{'CARROT':0}}])

    def test_additional_unknowns_are_explicit(self):
        r=run(unobserved_products=['WOOL'],unobserved_lots=[{'id':'hyp','origin':'fixture','stock':{'WOOL':7}}])
        self.assertTrue(r['ready']);self.assertEqual(r['observed_products'],['CARROT'])
        self.assertTrue(all(s['shed']['WOOL']==7 for s in r['scenarios']))

    def test_no_identified_product_is_not_a_history_model(self):
        r=build(history(),['WHEAT','FERTILIZER'],NOW)
        self.assertEqual(r['status'],'no_identified_products')

    def test_joint_capacity_not_per_product_capacity(self):
        h=history({i:{'CARROT':60,'WOOL':60} for i in (1,2,3)})
        r=run(h);self.assertEqual(r['status'],'joint_capacity_exceeded');self.assertEqual(r['scenarios'],[])

    def test_bad_later_completion_does_not_return_earlier_subset(self):
        r=run(products=('CARROT','WOOL','WHEAT'),
              slot_templates=[template(('CARROT',None,'WOOL','WHEAT'))],
              unobserved_lots=[{'id':'zero','origin':'fixture','stock':{'WHEAT':0}},
                               {'id':'full','origin':'fixture','stock':{'WHEAT':100}}])
        self.assertEqual(r['status'],'joint_capacity_exceeded');self.assertEqual(r['scenarios'],[])

    def test_omitted_positive_product_is_not_silently_dropped(self):
        r=run(slot_templates=[template(('CARROT',))]);self.assertEqual(r['status'],'unrepresented_positive_product')
        self.assertFalse(r['ready']);self.assertEqual(r['scenarios'],[])

    def test_scenario_budget_returns_no_optimized_subset(self):
        r=run(max_scenarios=2);self.assertEqual(r['status'],'scenario_limit')
        self.assertEqual(r['scenarios'],[]);self.assertEqual(r['unique_scenarios_at_least'],3)

    def test_exact_budget_is_complete(self):
        r=run(max_scenarios=3);self.assertTrue(r['ready']);self.assertEqual(len(r['scenarios']),3)

    def test_stale_history_is_not_ready(self):
        h=history({i:{'CARROT':1,'WOOL':2} for i in (6,7,8)})
        self.assertFalse(run(h)['ready'])

    def test_deterministic_detached_and_json_serializable(self):
        h=history();t=[template()];before=deepcopy(t)
        a=run(h,slot_templates=t);b=run(h,slot_templates=t)
        self.assertEqual(a,b);json.dumps(a,allow_nan=False);self.assertEqual(t,before)
        a['scenarios'][0]['market'][0][2]=900
        self.assertEqual(run(h,slot_templates=t),b)

    def test_slot_template_duplicates_rejected(self):
        with self.assertRaises(ValueError):run(slot_templates=[template(('WOOL','WOOL'))])

    def test_malformed_and_nonfinite_quantities_rejected(self):
        for val in (True,-1,1.5,float('nan'),'3'):
            with self.subTest(value=str(val)),self.assertRaises(ValueError):
                run(products=('CARROT','WOOL','WHEAT'),
                    unobserved_lots=[{'id':'x','origin':'fixture','stock':{'WHEAT':val}}])

    def test_boundary_parameters(self):
        for kw in ({'now':True},{'capacity':0},{'max_orders':0},{'max_scenarios':33}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                now=kw.pop('now',NOW);build(history(),['CARROT','WOOL'],now,**kw)

    def test_incompatible_upstream_window_cannot_pass(self):
        h=history();original=h.window_prediction
        def altered(p,now,end):
            r=original(p,now,end);r['windows'][0]['training_end']=now
            return r
        with patch.object(h,'window_prediction',side_effect=altered):
            r=run(h);self.assertFalse(r['ready']);self.assertEqual(r['status'],'incompatible_history_window')

    def test_empty_joint_vector_is_explicit_quiet_scenario(self):
        r=run(history({i:{'CARROT':0,'WOOL':0} for i in (1,2,3)}))
        self.assertTrue(r['ready']);self.assertEqual(r['scenarios'][0]['shed'],{})
        self.assertEqual(r['scenarios'][0]['market'],[[],[],[]])


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flow',type=Path,default=Path(__file__).with_name('flow.py'))
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();FLOW=load_flow(args.flow)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(JointHistoryTests))
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'successful':result.wasSuccessful(),'full_games':0,'new_game_seeds':0}
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
