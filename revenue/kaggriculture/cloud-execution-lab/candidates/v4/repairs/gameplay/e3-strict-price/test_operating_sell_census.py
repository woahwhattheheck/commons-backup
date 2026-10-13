# SPDX-License-Identifier: Apache-2.0
"""Synthetic tooling checks; full-engine episodes are separate evidence."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import operating_sell_census as c

CFG = {'maxMarketOrdersPerTurn':10,'turnsPerDay':24}
CELL = {'seed':2027,'seat':0,'opponent':'official_starter'}

def action(market=None):
    return {'farmer':['PASS'],'hands':[],'market':market or []}

def record(step=0, market=None):
    r=c.Recorder(2027,0);r.begin({'step':step,'player':0},CFG)
    for s in 'ABC':r.capture(s,action(market),CFG,{'status':'completed'})
    return r.finish(action(market),CFG,{'status':'completed'})

class PrefixTests(unittest.TestCase):
    def test_preserves_falsey_slot(self):
        a=action([[],['SELL','WHEAT',3]])
        self.assertEqual(c.prefix(a,{'maxMarketOrdersPerTurn':1}),[[]])
    def test_tail_poison_is_inert(self):
        a=action([[],['SELL','WHEAT',True]])
        self.assertEqual(c.target_rows(c.prefix(a,{'maxMarketOrdersPerTurn':1})),[])
    def test_zero_negative_clamp(self):
        for cap in (0,-1,-10):
            self.assertEqual(c.prefix(action([['PASS'],['PASS']]),{'maxMarketOrdersPerTurn':cap}),[['PASS']])
    def test_nonint_cap_rejected(self):
        for cap in (True,1.0,'1',None):
            with self.subTest(cap=cap),self.assertRaises(ValueError):c.prefix(action(),{'maxMarketOrdersPerTurn':cap})
    def test_independent_snapshot(self):
        a=action([[],['SELL','WHEAT',3]]);s=c.prefix(a,CFG)
        a['market'][1][2]=100;self.assertEqual(s[1][2],3)
    def test_raw_indices_and_zero(self):
        self.assertEqual(c.target_rows([[],['SELL','FERTILIZER',4],['SELL','WHEAT',0]]),
                         [{'market_index':1,'product':'FERTILIZER','qty':4}])
    def test_bad_target_quantity_rejected(self):
        for qty in (True,1.0,'1',None,-1):
            with self.subTest(qty=qty),self.assertRaises(ValueError):c.target_rows([['SELL','WHEAT',qty]])
    def test_missing_market_rejected(self):
        with self.assertRaises(ValueError):c.prefix({},CFG)

class RecorderTests(unittest.TestCase):
    def test_captures_at_stage_not_after_mutation(self):
        r=c.Recorder(2027,0);r.begin({'step':0,'player':0},CFG)
        a=action([['SELL','WHEAT',4]]);d={'operating_stock':{'why':[1]}}
        r.capture('A',a,CFG,d);a['market'][0][2]=1;d['operating_stock']['why'].append(2)
        self.assertEqual(r.current['stages']['A']['market'][0][2],4)
        self.assertEqual(r.current['stages']['A']['diagnostics']['operating_stock']['why'],[1])
    def test_missing_stage_is_not_zero(self):
        r=c.Recorder(2027,0);r.begin({'step':0,'player':0},CFG)
        out=r.finish(action(),CFG,{'status':'completed'})
        self.assertFalse(out['stage_complete'])
    def test_duplicate_stage_is_incomplete(self):
        r=c.Recorder(2027,0);r.begin({'step':0,'player':0},CFG)
        for s in 'AABC':r.capture(s,action(),CFG,{})
        self.assertFalse(r.finish(action(),CFG,{'status':'completed'})['stage_complete'])
    def test_fallback_does_not_certify(self):
        r=c.Recorder(2027,0);r.begin({'step':0,'player':0},CFG)
        for s in 'ABC':r.capture(s,action(),CFG,{})
        self.assertFalse(r.finish(action(),CFG,{'status':'deadline_fallback'})['stage_complete'])
    def test_fresh_callback_clears_prior_stages(self):
        r=c.Recorder(2027,0);r.begin({'step':0,'player':0},CFG);r.capture('A',action(),CFG,{})
        r.begin({'step':1,'player':0},CFG);self.assertEqual(r.current['stages'],{})
    def test_seat_calendar_types(self):
        for seat in (True,2,'0'):
            with self.subTest(seat=seat),self.assertRaises(ValueError):c.Recorder(2027,seat)
        r=c.Recorder(2027,0)
        with self.assertRaises(ValueError):r.begin({'step':0,'player':1},CFG)
    def test_original_bound_calls_once_same_identity(self):
        agent=c.CensusAgent.__new__(c.CensusAgent);agent.recorder=c.Recorder(2027,0)
        agent.recorder.begin({'step':0,'player':0},CFG)
        calls=[]
        class Instance:
            diagnostics={'status':'completed'}
            def _operating_stock_selected(self,o,cfg,a):calls.append(('op',self,a));return a
            def _feed_stock_selected(self,o,cfg,a):calls.append(('feed',self,a));return a
        i=Instance();agent.attach(i);a=action([['SELL','WHEAT',3]])
        self.assertIs(i._operating_stock_selected({},CFG,a),a)
        self.assertIs(i._feed_stock_selected({},CFG,a),a)
        self.assertEqual([x[0] for x in calls],['op','feed'])
        self.assertTrue(all(x[1] is i and x[2] is a for x in calls))
    def test_entrypoint_return_same_object(self):
        a=action([['SELL','WHEAT',1]]);agent=c.CensusAgent.__new__(c.CensusAgent)
        agent.recorder=c.Recorder(2027,0);agent.last_instance=None
        i=types.SimpleNamespace(diagnostics={'status':'completed'})
        def actual(obs,cfg):
            for s in 'ABC':agent.recorder.capture(s,a,cfg,i.diagnostics)
            return a
        agent.main=types.SimpleNamespace(agent=actual,_INSTANCE=i)
        import io
        agent.stream=io.BytesIO()
        self.assertIs(agent({'step':0,'player':0},CFG),a)
        self.assertEqual(json.loads(agent.stream.getvalue())['stages']['D']['market'],a['market'])

class SummaryTests(unittest.TestCase):
    def test_complete_zero(self):
        s=c.summarize_records([record()],[CELL],1)
        self.assertTrue(s['complete']);self.assertEqual(s['census_decision'],'NO_RESIDUAL_ON_EXECUTED_CELLS')
    def test_residual_is_not_port_authority(self):
        s=c.summarize_records([record(market=[[],['SELL','FERTILIZER',5]])],[CELL],1)
        self.assertEqual(s['final_residual_rows'],1);self.assertEqual(s['final_residual_unique_steps'],1)
        self.assertEqual(s['rows'][-1]['market_index'],1)
        self.assertEqual(s['census_decision'],'RESIDUAL_PRESENT_NOT_PORT_AUTHORITY')
    def test_missing_cell_and_callback_block_zero(self):
        s=c.summarize_records([record()],[CELL,dict(CELL,seat=1)],2)
        self.assertFalse(s['complete']);self.assertEqual(s['expected_callbacks'],4)
    def test_empty_observations_not_false_green(self):
        self.assertFalse(c.summarize_records([],[CELL],1)['complete'])
    def test_duplicate_callback_rejected(self):
        with self.assertRaises(ValueError):c.summarize_records([record(),record()],[CELL],1)
    def test_forged_complete_missing_stage_blocked(self):
        r=record();del r['stages']['A']
        self.assertFalse(c.summarize_records([r],[CELL],1)['complete'])
    def test_forged_fallback_complete_blocked(self):
        r=record();r['status']='deadline_fallback'
        self.assertFalse(c.summarize_records([r],[CELL],1)['complete'])
    def test_wrong_stage_order_blocked(self):
        r=record();r['stage_order']=['B','A','C','D']
        self.assertFalse(c.summarize_records([r],[CELL],1)['complete'])
    def test_row_evidence_conflict_rejected(self):
        r=record(market=[['SELL','WHEAT',2]]);r['stages']['D']['rows'][0]['qty']=3
        with self.assertRaises(ValueError):c.summarize_records([r],[CELL],1)
    def test_bool_metadata_rejected(self):
        r=record();r['seat']=False
        with self.assertRaises(ValueError):c.summarize_records([r],[CELL],1)
    def test_calendar_mismatch_rejected(self):
        r=record();r['hour']=1
        with self.assertRaises(ValueError):c.summarize_records([r],[CELL],1)
    def test_reductions_do_not_lose_increases(self):
        r=record(market=[['SELL','WHEAT',2]])
        r['stages']['D']['market'][0][2]=3;r['stages']['D']['rows'][0]['qty']=3
        s=c.summarize_records([r],[CELL],1)
        self.assertEqual(s['net_reductions']['C->D']['WHEAT']['units'],-1)
    def test_panel_seed_seat_alias_and_duplicate(self):
        for cells in ([CELL,CELL],[dict(CELL,seat=False)],[]):
            with self.subTest(cells=cells),self.assertRaises(ValueError):
                c.validate_panel({'provenance':'fixture','cells':cells})

class CustodyTests(unittest.TestCase):
    def test_pins_and_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'x.py';p.write_bytes(b'x=1\n');pins={'x.py':c.blob(p.read_bytes())}
            self.assertIn('x.py',c.check_pins(root,pins));p.write_bytes(b'x=2\n')
            with self.assertRaises(ValueError):c.check_pins(root,pins)
    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'a').write_bytes(b'x');(root/'b').symlink_to(root/'a')
            with self.assertRaises(ValueError):c.fingerprint(root/'b')
    def test_duplicate_json_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.json'
            for text in ('{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}'):
                p.write_text(text)
                with self.subTest(text=text),self.assertRaises(ValueError):c.read_json(p)
    def test_stale_real_artifact_pin_is_rejected(self):
        old=Path('/mnt/data/titan_execution/seed-retry-runtime')
        if old.exists():
            with self.assertRaises(ValueError):c.check_pins(old,c.PINS)
        else:
            # This portable test still exercises every protected filename.
            with tempfile.TemporaryDirectory() as td:
                root=Path(td)
                for name in c.PINS:(root/name).write_bytes(b'old\n')
                with self.assertRaises(ValueError):c.check_pins(root,c.PINS)

if __name__=='__main__':unittest.main()
