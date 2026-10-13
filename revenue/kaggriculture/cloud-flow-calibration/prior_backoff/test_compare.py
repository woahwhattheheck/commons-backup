# SPDX-License-Identifier: MIT
"""Integration checks over actual recorded, pre-outcome forecast snapshots."""
import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import compare
from backoff import predict_event

OUTPUT=CALIBRATION=None


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=CALIBRATION/'calibration.py'
        spec=importlib.util.spec_from_file_location('quill_compare_test_calibration',p)
        cls.cal=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.cal)
        cls.rows=json.loads(gzip.decompress((OUTPUT/'lonespear.outcomes.json.gz').read_bytes()))
        cls.warm=next(r for r in cls.rows if r['forecast']['support']>=3)
        cls.censored=next(r for r in cls.rows if r['label'] is None)
        cls.results=json.loads((OUTPUT/'results.json').read_text())

    def test_real_warm_formula(self):
        f=self.warm['forecast']
        for expert in ('model','same_phase'):
            raw=f['model_probability'] if expert=='model' else f['expert_probabilities'][expert]
            expected=(1-f['unknown_mass'])*raw+f['unknown_mass']*f['prior_rate_control']
            self.assertEqual(predict_event(f,expert=expert)['probability'],expected)

    def test_forecast_and_original_scores_unchanged(self):
        original=deepcopy(self.warm);before=deepcopy(original)
        r=compare.augment([original],self.cal,'cok-v10','development-transfer')[0]
        self.assertEqual(original,before);self.assertEqual(r['forecast'],before['forecast'])
        for key,score in before['scores'].items():self.assertEqual(r['scores'][key],score)

    def test_censored_outcomes_have_no_loss(self):
        r=compare.augment([self.censored],self.cal,'cok-v10','development-transfer')[0]
        self.assertIsNone(r['label']);self.assertEqual(r['scores'],{})
        self.assertEqual(set(r['backoff']),{'model','same_phase'})

    def test_reporting_labels_cannot_change_prediction(self):
        a=compare.augment([self.warm],self.cal,'family-a','design')[0]
        b=compare.augment([self.warm],self.cal,'family-b','transfer')[0]
        self.assertEqual(a['forecast'],b['forecast']);self.assertEqual(a['backoff'],b['backoff'])
        self.assertEqual(a['scores'],b['scores'])

    def test_duplicate_outcome_rejected(self):
        with self.assertRaises(ValueError):compare.augment([self.warm,self.warm],self.cal,'family','split')

    def test_losses_match_actual_frozen_probability(self):
        r=compare.augment([self.warm],self.cal,'family','split')[0]
        for expert in ('model','same_phase'):
            p=r['backoff'][expert]['probability'];score=r['scores']['backoff_'+expert]
            self.assertEqual(score['prediction'],p)
            self.assertEqual(score['brier'],(p-r['label'])**2)

    def test_original_sources_and_new_freeze_retained(self):
        inputs=self.results['inputs']
        self.assertEqual(inputs['assessment_blob'],'765874398a98603e48109f5c92db86461bc0290f')
        self.assertEqual(inputs['calibration_blob'],'75e67d65583ab83847b95dee426ff3a49dee1c87')
        self.assertEqual(inputs['flow_blob'],'7b3c1c383e98ce1eb5bf539caddf0ab4351f8633')
        self.assertEqual(inputs['backoff_sha256'],hashlib.sha256(Path(__file__).with_name('backoff.py').read_bytes()).hexdigest())
        self.assertEqual(inputs['backoff_sha256'],inputs['freeze']['source_sha256'])

    def test_existing_transfer_label_accounting_and_cash(self):
        transfer=self.results['transfer']['all']
        self.assertEqual(transfer['windows'],transfer['identified']+transfer['censored'])
        self.assertEqual(len(self.results['transfer_games']),6)
        for g in self.results['transfer_games']:
            self.assertTrue(g['member'].startswith('development-v'))
            self.assertEqual(g['rows'],719);self.assertEqual(g['checks']['cash_residual'],0)
        for name in ('model','prior_rate_control','backoff_model','backoff_same_phase'):
            self.assertEqual(transfer['scores'][name]['n'],transfer['identified'])
        self.assertEqual(self.results['new_games'],0)


def main():
    global OUTPUT,CALIBRATION
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assessment-output',type=Path,required=True)
    p.add_argument('--calibration-dir',type=Path,default=Path(__file__).resolve().parents[1])
    args=p.parse_args();OUTPUT=args.assessment_output;CALIBRATION=args.calibration_dir
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ComparisonTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
