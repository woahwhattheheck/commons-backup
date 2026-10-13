from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
HERE = Path(__file__).resolve().parent
LAB = HERE.parents[3]
spec = importlib.util.spec_from_file_location("h3s420_compose", HERE / "compose_current_h3s420.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
FIXTURE = '''\
import copy
HORIZON = 8
from selected_sell_core import optimize_lot, joint_plan_metrics, shared_slot_ledger

def event_aware_horizon(now):
    return now + HORIZON

class FrozenSelected:
    def __init__(self):
        self.planned = {'MILK': [(420, 4), (421, 2)]}
        self.diagnostics = {}
        self.new_choices = 0
    def cash_reserve(self, obs, config, base, end):
        return 0
    def transform(self, obs, config, base):
        now = int(obs['step'])
        end = event_aware_horizon(now)
        current = {'MILK': int(base.get('base_sell', 0)) + sum(q for t,q in self.planned.get('MILK',[]) if t<=now)}
        budget=self.cash_reserve(obs,config,base,end)
        best=None;options=[]
        self.new_choices += 1
        best=('MILK', ((now, 7), (now+1, 3)), {'accepted': True})
        if best:
            item,plan,info=best
            selected_plans={item:plan}
            for selected_item,selected_plan in selected_plans.items():
                current[selected_item]=dict(selected_plan).get(now,0)
                self.planned[selected_item]=[(t,q) for t,q in selected_plan if t>now and q>0]
            self.diagnostics['chosen']=info
        out=copy.deepcopy(base)
        out['sell_now'] = current['MILK']
        out['planned_after'] = copy.deepcopy(self.planned)
        return out
'''
STUB='''\
import sys, types
m=types.ModuleType("selected_sell_core")
m.optimize_lot=m.joint_plan_metrics=m.shared_slot_ledger=lambda *a,**k: None
sys.modules["selected_sell_core"]=m
'''
def load_transformed(source=FIXTURE):
    ns={}; exec(STUB,ns); exec(mod._rewrite_source(source),ns); return ns
class Tests(unittest.TestCase):
    def test_disabled_compose_is_byte_identity(self):
        raw=b"abc\n"; self.assertIs(mod.compose(raw,enabled=False),raw)
    def test_horizon_is_shadowed_to_three(self):
        ns=load_transformed(); self.assertEqual(ns['HORIZON'],3); self.assertEqual(ns['event_aware_horizon'](100),103)
    def test_step_419_still_selects_a_new_plan(self):
        ns=load_transformed(); obj=ns['FrozenSelected'](); got=obj.transform({'step':419},{},{'base_sell':1}); self.assertEqual(obj.new_choices,1); self.assertEqual(got['sell_now'],7); self.assertFalse(obj.diagnostics['h3s420']['new_plan_suppressed'])
    def test_step_420_suppresses_only_new_plan_selection(self):
        ns=load_transformed(); obj=ns['FrozenSelected'](); got=obj.transform({'step':420},{},{'base_sell':1}); self.assertEqual(obj.new_choices,0); self.assertTrue(obj.diagnostics['h3s420']['new_plan_suppressed']); self.assertEqual(got['sell_now'],5)
    def test_future_preexisting_commitment_is_not_erased(self):
        ns=load_transformed(); obj=ns['FrozenSelected'](); got=obj.transform({'step':420},{},{'base_sell':0}); self.assertEqual(got['planned_after']['MILK'],[(420,4),(421,2)]); got2=obj.transform({'step':421},{},{'base_sell':0}); self.assertEqual(got2['sell_now'],6)
    def test_base_sale_is_preserved_after_threshold(self):
        ns=load_transformed(); obj=ns['FrozenSelected'](); got=obj.transform({'step':500},{},{'base_sell':9}); self.assertEqual(got['sell_now'],15)
    def test_missing_import_marker_rejected(self):
        with self.assertRaisesRegex(ValueError,"import marker"): mod._rewrite_source(FIXTURE.replace(mod._IMPORT_MARKER,""))
    def test_duplicate_transform_marker_rejected(self):
        with self.assertRaisesRegex(ValueError,"end marker"): mod._rewrite_source(FIXTURE.replace(mod._BLOCK_END,mod._BLOCK_END*2))
    def test_baseline_pins_remain_backward_compatible(self):
        self.assertEqual(mod.FROZEN_SELECTED_GIT_BLOB,'fc7baf5c179818a55037f6a61d92984d81d1a21c'); self.assertEqual(mod.SCHEDULER_GIT_BLOB,'a483b24dd72b580d7d8811636b54d2d44f391575')
    def test_exact_loom4_postimages_are_authenticated(self):
        self.assertEqual(set(mod.FROZEN_SELECTED_INPUTS),{'fc7baf5c179818a55037f6a61d92984d81d1a21c','ef090f6731c2d1ee648e2caaf3e215641b006518','4a5d3d5f4bed04acf73c7339e41fed56badf34c9'}); self.assertEqual(set(mod.SCHEDULER_INPUTS),{'a483b24dd72b580d7d8811636b54d2d44f391575','eb289f87adebb7dc7e90046bfbec31a307cb5aaa','b29d1e9887f517506c5b3d858baa9bda5848e73f'}); self.assertEqual(mod.authenticate_git_blobs('4a5d3d5f4bed04acf73c7339e41fed56badf34c9','b29d1e9887f517506c5b3d858baa9bda5848e73f'),('captrace+livepath','captrace+spindle'))
    def test_unknown_combined_postimage_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"explicit rebase"): mod.authenticate_git_blobs('0'*40,mod.SCHEDULER_GIT_BLOB)
        with self.assertRaisesRegex(ValueError,"explicit rebase"): mod.authenticate_git_blobs(mod.FROZEN_SELECTED_GIT_BLOB,'f'*40)
    def test_unrelated_peer_spans_survive_rewrite(self):
        decorated=FIXTURE.replace('def event_aware_horizon(now):','def represented_shed_event():\n    return "peer-byte"\n\ndef event_aware_horizon(now):'); rewritten=mod._rewrite_source(decorated); self.assertIn('def represented_shed_event():\n    return "peer-byte"',rewritten); self.assertIn("if now < H3S420_SUPPRESS_NEW_PLANS_AFTER",rewritten)
    def test_contract_threshold_is_420(self):
        self.assertEqual(mod.SUPPRESS_NEW_PLANS_AFTER,420); self.assertEqual(mod.BASELINE_HORIZON,3)
    def test_exact_pinned_native_source_rewrites(self):
        raw=(LAB/'frozen_selected.py').read_bytes()
        self.assertEqual(mod.git_blob(raw),mod.FROZEN_SELECTED_GIT_BLOB)
        rewritten=mod.compose(raw,enabled=True)
        compile(rewritten,'<source-real-h3s420>','exec')
        self.assertIn(b'H3S420_BASELINE_HORIZON = 3',rewritten)
        self.assertIn(b'if now < H3S420_SUPPRESS_NEW_PLANS_AFTER:',rewritten)
    def test_terminal_copy_before_optimizer_does_not_confuse_boundary(self):
        decorated=FIXTURE.replace(
            '        budget=self.cash_reserve(obs,config,base,end)\n',
            '        if now < 0:\n            out=copy.deepcopy(base)\n            return out\n'
            '        budget=self.cash_reserve(obs,config,base,end)\n')
        self.assertEqual(decorated.count(mod._BLOCK_END),2)
        rewritten=mod._rewrite_source(decorated)
        self.assertEqual(rewritten.count(mod._BLOCK_END),2)
        self.assertIn('if now < H3S420_SUPPRESS_NEW_PLANS_AFTER:',rewritten)
if __name__=='__main__': unittest.main()
