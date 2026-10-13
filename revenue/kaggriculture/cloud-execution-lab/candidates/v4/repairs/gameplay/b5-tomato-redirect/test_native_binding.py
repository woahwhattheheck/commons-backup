# SPDX-License-Identifier: Apache-2.0
"""Actual native class/finalizer/config acceptance; test hooks are labeled, not games."""
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import compose_native as C
import test_discarded_fertilizer as E
if os.environ.get('TOMATO_COMPOSER'):
    C=E.load(Path(os.environ['TOMATO_COMPOSER']),'mutant_native_composer')


class NativeBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.dir=Path(cls.tmp.name)
        cls.off=cls.dir/'off';cls.on=cls.dir/'on'
        cls.off_report=C.compose(E.ROOT,cls.off)
        cls.on_report=C.compose(E.ROOT,cls.on,enabled=True)
        sys.path.insert(0,str(cls.on))
        cls.r=E.load(cls.on/'titan_runtime.py','titan_runtime')
        cls.main=E.load(cls.on/'main.py','native_b5_main')
        cls.engine,cls.S,_=E.authenticated_engine()

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(cls.on));cls.tmp.cleanup()

    def report(self, agent):
        self.assertIn('tomato_discard_salvage',agent.diagnostics)
        return agent.diagnostics['tomato_discard_salvage']

    def instance(self, enabled=True):
        agent=self.main._new_instance(self.on,{'tomato_discard_salvage':enabled})
        agent.diagnostics={'status':'completed'}
        agent.consumer=SimpleNamespace(selected_post_units=None,selected_post_units_binding=None)
        return agent

    def test_real_main_factory_uses_config_not_module_constant(self):
        self.r.B5_TOMATO_FERTILIZER=True
        off=self.main._new_instance(self.off,json.loads((self.off/'TITAN-CONFIG.json').read_text()))
        on=self.main._new_instance(self.on,json.loads((self.on/'TITAN-CONFIG.json').read_text()))
        self.assertIs(off.features.tomato_discard_salvage,False)
        self.assertIs(on.features.tomato_discard_salvage,True)
        for value in (1,'true',None,[]):
            with self.assertRaises(ValueError):self.r.Features(tomato_discard_salvage=value)
        with self.assertRaises(TypeError):self.r.Features(r04_b5_tomato_fertilizer=True)

    def test_real_finalizer_sees_late_sell_and_preserves_input(self):
        agent=self.instance()
        s,env=E.fixture(self.engine,self.S)
        def late(obs,cfg,a):
            out=deepcopy(a);out['market']=[['SELL','WHEAT',1]];return out
        agent._early_capital_selected=late
        out=agent._finish_production(s[0].observation,s[0].action,env.configuration)
        self.assertEqual(out['farmer'],['PASS'])
        self.assertFalse(self.report(agent)['changed'])
        self.assertEqual(out['market'],[['SELL','WHEAT',1]])

    def test_real_finalizer_clears_stale_snapshot_and_binds_returned_action(self):
        agent=self.instance()
        s,env=E.fixture(self.engine,self.S)
        obs=s[0].observation
        agent.consumer.selected_post_units=deepcopy((obs.farms[0],obs.private))
        agent.consumer.selected_post_units_binding=(obs.step,0,['PASS'],[])
        remembered=[]
        agent.history=SimpleNamespace(diagnostics={},remember=lambda *args:remembered.append(deepcopy(args)))
        agent.post=deepcopy(obs)
        agent.selected=deepcopy(s[0].action)
        out=agent._finish_production(obs,s[0].action,env.configuration)
        self.assertEqual(out['farmer'],['FERTILIZE'])
        self.assertIsNone(agent.post)
        self.assertIsNone(agent.consumer.selected_post_units)
        self.assertIsNone(agent.consumer.selected_post_units_binding)
        self.assertEqual(remembered[-1][2],out)
        self.assertIsNone(remembered[-1][3])
        self.assertEqual(agent.selected,out)
        self.assertIsNot(agent.selected,out)
        self.assertFalse(self.report(agent)['observed_fill'])
        self.assertIsNone(agent._selected_snapshot(obs,out))
        # Run that actual finalizer return, not a separately invoked helper.
        s[0].action=out
        E.transition(self.engine,s,env)
        self.assertEqual(s[0].observation.farms[0]['tiles'][0][0]['yield_units'],2)

    def test_off_does_not_import_or_call_optional_helper(self):
        agent=self.instance(False);s,e=E.fixture(self.engine,self.S)
        import discarded_fertilizer_tomato as helper
        with patch.object(helper,'apply_discarded_fertilizer',side_effect=AssertionError('must not run')):
            self.assertIs(agent._finish_production(s[0].observation,s[0].action,e.configuration),s[0].action)
        self.assertNotIn('tomato_discard_salvage',agent.diagnostics)

    def test_deadline_fallback_does_not_run_optional_transform(self):
        agent=self.instance();agent.diagnostics['status']='deadline_fallback'
        s,e=E.fixture(self.engine,self.S)
        import discarded_fertilizer_tomato as helper
        with patch.object(helper,'apply_discarded_fertilizer',side_effect=AssertionError('must not run')):
            self.assertIs(agent._finish_production(s[0].observation,s[0].action,e.configuration),s[0].action)
        self.assertEqual(self.report(agent)['reason'],'no_optional_work_on_fallback')

    def test_active_plan_crop_stock_capital_and_history_are_protected(self):
        s,e=E.fixture(self.engine,self.S)
        for key in ('plans','sale_obligation','crop_intent','_sale_proposal','_crop_preparation','_crop_repair'):
            agent=self.instance();agent.spatial=SimpleNamespace(**{key:{'active':True}})
            self.assertIs(agent._tomato_discard_selected(s[0].observation,e.configuration,s[0].action),s[0].action)
        for pending in ({'plans':{1:{}}},{'previous':{'plans':{1:{}}}},['bad'],{'previous':['bad']}):
            agent=self.instance();agent.spatial=SimpleNamespace(_pending=pending)
            self.assertIs(agent._tomato_discard_selected(s[0].observation,e.configuration,s[0].action),s[0].action)
        agent=self.instance();agent.quadrant=object()
        self.assertIs(agent._tomato_discard_selected(s[0].observation,e.configuration,s[0].action),s[0].action)
        agent=self.r.TitanAgent(self.r.Features(tomato_discard_salvage=True,terminal_history=True,history_hypotheses={}))
        agent.diagnostics={'status':'completed'}
        self.assertIs(agent._tomato_discard_selected(s[0].observation,e.configuration,s[0].action),s[0].action)

    def test_empty_pending_spatial_record_does_not_make_key_dead(self):
        agent=self.instance();agent.spatial=SimpleNamespace(_pending={'plans':{},'previous':{'plans':{}}})
        s,e=E.fixture(self.engine,self.S)
        out=agent._tomato_discard_selected(s[0].observation,e.configuration,s[0].action)
        self.assertEqual(out['farmer'],['FERTILIZE'])

    def test_nonfrozen_and_terminal_consumers_do_not_activate(self):
        s,e=E.fixture(self.engine,self.S)
        for kwargs in ({'consumer':'ordered'},{'consumer':'parent'},{'terminal_route':True}):
            a=self.r.TitanAgent(self.r.Features(tomato_discard_salvage=True,**kwargs))
            a.diagnostics={'status':'completed'}
            self.assertIs(a._tomato_discard_selected(s[0].observation,e.configuration,s[0].action),s[0].action)

    def test_composer_preserves_all_unrelated_runtime_bytes(self):
        base=C.verify_input(E.ROOT)
        for name in base['runtime']:
            if name=='titan_runtime.py':continue
            self.assertEqual((E.ROOT/name).read_bytes(),(self.off/name).read_bytes(),name)
        cfg=json.loads((self.on/'TITAN-CONFIG.json').read_text());cfg.pop(C.FEATURE)
        self.assertEqual(cfg,json.loads((E.ROOT/'TITAN-CONFIG.json').read_text()))
        self.assertEqual(self.off_report['entrypoint_sha256'],self.on_report['entrypoint_sha256'])

    def test_bad_input_and_existing_output_refuse_before_write(self):
        dest=self.dir/'must_not_exist'
        with self.assertRaises(ValueError):C.compose(self.on,dest)
        self.assertFalse(dest.exists())
        with self.assertRaises(ValueError):C.compose(E.ROOT,self.on)
        with self.assertRaises(ValueError):C.compose(E.ROOT,E.ROOT/'accidental-child')
        with self.assertRaises(TypeError):C.compose(E.ROOT,dest,enabled=1)
        with self.assertRaises(ValueError):C.once('abc abc','abc','x')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path);a=p.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeBinding))
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skips':len(result.skipped),'optimized':not __debug__,'scope':'actual native class/finalizer and config, controlled hook fixtures; not field games',
        'engine_calls':E.RECEIPT['engine_calls'],'off':NativeBinding.off_report,'on':NativeBinding.on_report}
    if a.report:a.report.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,sort_keys=True));raise SystemExit(0 if result.wasSuccessful() else 1)
