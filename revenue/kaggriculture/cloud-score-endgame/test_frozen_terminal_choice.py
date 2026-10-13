# SPDX-License-Identifier: Apache-2.0
"""Focused source-bound controls for the frozen-choice stress consumer."""
from copy import deepcopy
from fractions import Fraction
import argparse
import gzip
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import check_frozen_terminal_choice as check
import terminal_input_cases as cases
import terminal_inputs as ti

ENGINE=REPORTS=PAYLOADS=EXECUTED=None
COUNTS={'native_reference_transitions':0,'valid_consumer_market_calls':0}


def raw_and_report():
    r=deepcopy(REPORTS['reports'][0]);return PAYLOADS[r['input_sha256']],r


def rewritten(raw, report, change):
    payload=json.loads(raw);change(payload);data=json.dumps(payload).encode()
    report['input_sha256']=check.sha(data)
    return data,report


class FrozenChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if any(value is None for value in (ENGINE, REPORTS, PAYLOADS, EXECUTED)):
            raise unittest.SkipTest("Supply the retained input and native engine paths to this CLI")

    def reject_before_market(self, raw, report):
        with patch.object(ti,'market_cell',side_effect=AssertionError('Unexpected market execution')):
            with self.assertRaises(ValueError):check.compare_frozen(ENGINE,report,raw)

    def test_input_hash_mismatch(self):
        raw,r=raw_and_report();r['input_sha256']='0'*64;self.reject_before_market(raw,r)

    def test_schema_mismatch(self):
        raw,r=raw_and_report();raw,r=rewritten(raw,r,lambda p:p.update(schema='outcome-index'))
        self.reject_before_market(raw,r)

    def test_nonterminal_input(self):
        raw,r=raw_and_report();raw,r=rewritten(raw,r,lambda p:p['observation'].update(step=717))
        self.reject_before_market(raw,r)

    def test_game_seed_excluded(self):
        raw,r=raw_and_report();raw,r=rewritten(raw,r,lambda p:p['configuration'].update(seed=1))
        self.reject_before_market(raw,r)

    def test_changed_original_action(self):
        raw,r=raw_and_report();r['original_action']['market']=[];self.reject_before_market(raw,r)

    def test_incomplete_prior_family(self):
        raw,r=raw_and_report();r['packet']['complete']=False;self.reject_before_market(raw,r)

    def test_outcome_based_prior_result_not_consumed(self):
        raw,r=raw_and_report();r['recorded_rival_outcome_used']=True;self.reject_before_market(raw,r)

    def test_changed_selected_unit_stage(self):
        raw,r=raw_and_report();r['choices']['cash_pareto']['action']['farmer']=['PASS']
        self.reject_before_market(raw,r)

    def test_choice_outside_frozen_plan_set(self):
        raw,r=raw_and_report();r['choices']['cash_pareto']['action']['market']=[]
        self.reject_before_market(raw,r)

    def test_post_unit_state_binding(self):
        raw,r=raw_and_report();r['packet']['source']['observation_and_post_units_sha256']='0'*64
        self.reject_before_market(raw,r)

    def test_missing_or_misbound_old_receipt(self):
        for variant in ('missing','binding'):
            raw,r=raw_and_report()
            if variant=='missing':r['packet']['document']['receipts'].pop(0)
            else:r['packet']['document']['receipts'][0]['public_state_sha256']='0'*64
            with self.subTest(variant=variant):self.reject_before_market(raw,r)

    def test_actual_valid_consumer_and_detachment(self):
        raw,r=raw_and_report();before=deepcopy(r);out=check.compare_frozen(ENGINE,r,raw)
        COUNTS['valid_consumer_market_calls']+=out['native_market_calls']
        expected=EXECUTED['records'][0]
        self.assertEqual(out,expected);self.assertEqual(r,before)
        out['frozen_action']['market']=[];out['rows'][0]['scenario']['shed']={'WOOL':999}
        self.assertEqual(r,before)

    def test_nine_worst_stress_pairs_match_full_native_terminal(self):
        for record in EXECUTED['records']:
            if not record['choice_changed']:continue
            payload=json.loads(PAYLOADS[record['input_sha256']])
            obs,cfg=payload['observation'],payload['configuration'];player=obs['player']
            row=min(record['rows'],key=lambda x:Fraction(x['margin_change']))
            pairs=[]
            for action,expected in [(record['original_action'],row['baseline']),
                                    (record['frozen_action'],row['candidate'])]:
                state,env=cases.make_state(obs,cfg,action,row['scenario'])
                ENGINE.interpreter(state,env);COUNTS['native_reference_transitions']+=1
                self.assertEqual([s.status for s in state],['DONE','DONE'])
                actual={'own_cash':state[player].reward,'rival_cash':state[1-player].reward}
                self.assertEqual(actual,expected);pairs.append(actual)
            self.assertEqual(check._margin(pairs[1])-check._margin(pairs[0]),Fraction(row['margin_change']))


def main():
    global ENGINE,REPORTS,PAYLOADS,EXECUTED
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reports',type=Path,required=True);p.add_argument('--payload-zip',type=Path,required=True)
    p.add_argument('--executed',type=Path,required=True);p.add_argument('--loader',type=Path,required=True)
    p.add_argument('--engine-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();REPORTS=json.loads(a.reports.read_bytes());EXECUTED=json.loads(a.executed.read_bytes())
    spec=importlib.util.spec_from_file_location('_cross_test_engine',a.loader);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    ENGINE,hashes=mod.get_engine(a.engine_dir)
    with zipfile.ZipFile(a.payload_zip) as archive:
        PAYLOADS={r['input_sha256']:gzip.decompress(archive.read('runtime/'+r['input_sha256']+'.json.gz')) for r in REPORTS['reports']}
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FrozenChoiceTests))
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
            'counts':COUNTS,'engine_hashes':hashes,'log':stream.getvalue()}
    with a.output.open('x') as output:json.dump(report,output,indent=2);output.write('\n')
    print(stream.getvalue(),end='');print(json.dumps(COUNTS));raise SystemExit(not result.wasSuccessful())


if __name__=='__main__':main()
