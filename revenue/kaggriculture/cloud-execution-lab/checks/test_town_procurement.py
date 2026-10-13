from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

import town_procurement as tp

ROOT = Path(__file__).resolve().parents[1]
ARLENE = ROOT/'reference/next-panel/vendor/arlene.py'


def obs(step, wheat, player=0):
    return {'step': step, 'player': player, 'private': {'shed': {'WHEAT': wheat}}}


def action(q=3, prefix=None):
    market=[] if prefix is None else [list(x) for x in prefix]
    market.append(['BUY_PRODUCT','WHEAT',q])
    return {'farmer':['PASS'],'hands':[],'market':market}


class TownProcurementUnitTests(unittest.TestCase):
    def setUp(self):
        tp.reset()

    def test_target_advances_existing_row_only(self):
        tp.observe(obs(200,10)); base=action(3)
        out,r=tp.apply(obs(200,10),base,{},completed=True)
        self.assertEqual(base['market'],[['BUY_PRODUCT','WHEAT',3]])
        self.assertEqual(out['market'],[['BUY_PRODUCT','WHEAT',6]])
        self.assertEqual(len(out['market']),len(base['market']))
        self.assertEqual(r['status'],'target_advanced')

    def test_full_receipt_suppresses_source_idempotently(self):
        tp.observe(obs(200,10)); tp.apply(obs(200,10),action(3),{},completed=True)
        rr=tp.observe(obs(201,16)); self.assertEqual(rr['confirmed_qty'],3)
        source=action(3)
        a,r1=tp.suppress_confirmed(obs(202,16),source); b,r2=tp.suppress_confirmed(obs(202,16),source)
        self.assertEqual(a['market'],[]); self.assertEqual(b['market'],[])
        self.assertEqual(r1['suppressed_qty'],3); self.assertEqual(r2['suppressed_qty'],3)

    def test_partial_receipt_suppresses_only_observed_extra(self):
        tp.observe(obs(200,10)); tp.apply(obs(200,10),action(3),{},completed=True)
        tp.observe(obs(201,14))
        out,r=tp.suppress_confirmed(obs(202,14),action(3))
        self.assertEqual(out['market'],[['BUY_PRODUCT','WHEAT',2]]); self.assertEqual(r['suppressed_qty'],1)

    def test_baseline_only_fill_never_suppresses(self):
        tp.observe(obs(200,10)); tp.apply(obs(200,10),action(3),{},completed=True); tp.observe(obs(201,13))
        out,r=tp.suppress_confirmed(obs(202,13),action(3))
        self.assertEqual(out['market'],[['BUY_PRODUCT','WHEAT',3]]); self.assertFalse(r['changed'])

    def test_target_requires_completed_and_unambiguous_unit_stage(self):
        tp.observe(obs(204,8)); base=action(3)
        out,r=tp.apply(obs(204,8),base,{},completed=False)
        self.assertIs(out,base); self.assertEqual(r['status'],'target_requires_completed_action')
        drop=action(3); drop['farmer']=['DROP']
        out,r=tp.apply(obs(204,8),drop,{},completed=True)
        self.assertIs(out,drop); self.assertEqual(r['status'],'target_unit_wheat_ambiguous')

    def test_target_quantity_drift_fails_closed(self):
        tp.observe(obs(204,8)); base=action(2)
        out,r=tp.apply(obs(204,8),base,{},completed=True)
        self.assertIs(out,base); self.assertEqual(r['status'],'target_quantity_drift')

    def test_unique_wheat_row_required(self):
        tp.observe(obs(204,8)); base=action(3); base['market'].append(['BUY_PRODUCT','WHEAT',1])
        out,r=tp.apply(obs(204,8),base,{},completed=True)
        self.assertIs(out,base); self.assertEqual(r['status'],'target_shape_drift')

    def test_missed_receipt_does_not_infer_late_fill(self):
        tp.observe(obs(204,8)); tp.apply(obs(204,8),action(3),{},completed=True)
        rr=tp.observe(obs(206,99)); self.assertEqual(rr['status'],'receipt_window_missed')
        out,r=tp.suppress_confirmed(obs(206,99),action(3))
        self.assertFalse(r['changed']); self.assertEqual(out['market'],[['BUY_PRODUCT','WHEAT',3]])

    def test_step_zero_resets_prior_episode(self):
        tp.observe(obs(200,10)); tp.apply(obs(200,10),action(3),{},completed=True); tp.observe(obs(201,16)); tp.observe(obs(0,13))
        out,r=tp.suppress_confirmed(obs(202,13),action(3)); self.assertFalse(r['changed'])

    def test_move_table_is_narrow(self):
        self.assertEqual(set(tp.MOVES),{200,204,220,252,272,276})
        for target,(source,qty) in tp.MOVES.items():
            self.assertEqual(source,target+2); self.assertEqual(target%4,0); self.assertGreater(qty,0)

    def test_target_respects_executable_prefix_and_wheat_sale_conflict(self):
        tp.observe(obs(220,9)); base=action(3, prefix=[["SELL","FERTILIZER",1]])
        out,r=tp.apply(obs(220,9),base,{"maxMarketOrdersPerTurn":1},completed=True)
        self.assertIs(out,base); self.assertEqual(r["status"],"target_wheat_inert_suffix")
        tp.reset(); tp.observe(obs(204,9))
        conflict={"farmer":["PASS"],"hands":[],"market":[["SELL","WHEAT",1],["BUY_PRODUCT","WHEAT",3]]}
        out,r=tp.apply(obs(204,9),conflict,{},completed=True)
        self.assertIs(out,conflict); self.assertEqual(r["status"],"target_wheat_sale_conflict")

    def test_entrypoint_fallback_reapplies_confirmed_suppression(self):
        import main; import titan_runtime as T
        tp.observe(obs(200,10)); tp.apply(obs(200,10),action(3),{},completed=True); tp.observe(obs(201,16))
        instance=SimpleNamespace(selected=action(3),features=SimpleNamespace(),town_procurement_enabled=True)
        first=main._entrypoint_fallback(instance,obs(202,16),{},T.deadline)
        second=main._entrypoint_fallback(instance,obs(202,16),{},T.deadline)
        self.assertEqual(first["market"],[]); self.assertEqual(second["market"],[])

    def test_feature_scope(self):
        import main
        data={'consumer':'frozen','seed':True,'funding':True,'terminal_route':False,'committed':True,
              'budget_seconds':1.0,'reserve_seconds':0.01,'terminal_history':False,'redundant_hire':True,
              'fourth_quadrant':False,'market_pressure':True,'committed_seed_retry':False,'operating_stock':True,
              'idle_fertilizer':True,'crop_release':True,'early_capital':True,'town_procurement':True}
        obj=main._new_instance(ROOT,data); self.assertTrue(obj.town_procurement_enabled)
        with self.assertRaises(ValueError): main._new_instance(ROOT,dict(data,consumer='ordered'))


class ExactArleneContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=ARLENE.read_bytes(); import hashlib
        blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if blob!='bdb9cf58148a3c7961c085f4902759537decabf6': raise AssertionError(blob)
        spec=importlib.util.spec_from_file_location('_tp_arlene',ARLENE)
        mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); cls.routes=mod.routes()

    def test_every_target_source_pair_is_route_invariant_existing_wheat(self):
        for target,(source,qty) in tp.MOVES.items():
            for rid,route in self.routes.items():
                for step in (target,source):
                    market=route[step].get('market') or []
                    hits=[r for r in market[:10] if isinstance(r,list) and len(r)>=3 and r[:2]==['BUY_PRODUCT','WHEAT']]
                    self.assertEqual(hits,[['BUY_PRODUCT','WHEAT',qty]],(rid,step,market))

    def test_opening_collision_outside_scope(self):
        self.assertNotIn(0,tp.MOVES)
        for route in self.routes.values(): self.assertEqual(route[0]['market'][0],['BUY_PRODUCT','WHEAT',13])

    def test_crop_repair_window_outside_scope(self):
        self.assertLess(max(source for source,_ in tp.SOURCE_TO_TARGET.items()),455)


if __name__=='__main__':
    unittest.main()
