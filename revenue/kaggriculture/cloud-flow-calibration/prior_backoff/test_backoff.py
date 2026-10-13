# SPDX-License-Identifier: MIT
"""Dependency-free checks of the fixed prior-backoff callable."""
from copy import deepcopy
import math
import unittest
from backoff import predict_event


def fixture():
    return {'ticket':'fixed', 'prior_rate_control':.02, 'unknown_mass':.25,
            'support':4, 'model_probability':.8, 'expert_probabilities':{'same_phase':1.,'zero':0.}}


class BackoffTests(unittest.TestCase):
    def test_fixed_weighted_equation(self):
        r=predict_event(fixture()); self.assertAlmostEqual(r['probability'],.605)
        self.assertEqual(r['backoff_mass'],.25); self.assertEqual(r['source_probability'],.8)

    def test_same_phase_equation(self):
        self.assertAlmostEqual(predict_event(fixture(),expert='same_phase')['probability'],.755)

    def test_prior_exclusive_when_cold(self):
        f=fixture(); f.update(unknown_mass=1.,support=0,expert_probabilities={'zero':0.})
        for expert in ('model','same_phase'):
            r=predict_event(f,expert=expert); self.assertEqual(r['probability'],.02)
            self.assertIsNone(r['source_probability']); self.assertEqual(r['event_interval'],[0,1])

    def test_missing_expert_not_zero_evidence(self):
        r=predict_event(fixture(),expert='unavailable')
        self.assertEqual(r['probability'],.02); self.assertEqual(r['backoff_mass'],1.)

    def test_known_extremes_remain_interior(self):
        for p in (0.,1.):
            f=fixture(); f['model_probability']=p
            r=predict_event(f); self.assertTrue(0<r['probability']<1)
            self.assertTrue(math.isfinite(-math.log(r['probability'])))

    def test_output_within_unknown_event_interval(self):
        for prior in (.001,.1,.5,.9,.999):
            for p in (0,.25,.7,1):
                for u in (.01,.25,.5,1):
                    f=fixture(); f.update(prior_rate_control=prior,model_probability=p,unknown_mass=u)
                    r=predict_event(f); lo,hi=r['event_interval']
                    self.assertLess(lo,r['probability']); self.assertLess(r['probability'],hi)

    def test_input_not_mutated(self):
        f=fixture(); before=deepcopy(f); predict_event(f)
        self.assertEqual(f,before)

    def test_outcome_and_future_metadata_ignored(self):
        f=fixture(); poisoned=deepcopy(f)
        poisoned.update(label=1,actual_rival_quantity=999,next_cash=1e10,seed=1234)
        self.assertEqual(predict_event(f),predict_event(poisoned))

    def test_repeat_is_identical_and_has_no_learning(self):
        f=fixture(); first=predict_event(f)
        for _ in range(10):self.assertEqual(first,predict_event(f))
        self.assertEqual(first['recommended_alpha'],0)

    def test_invalid_probabilities_and_support(self):
        for field in ('prior_rate_control','unknown_mass','model_probability'):
            for v in (float('nan'),float('inf'),True,-.1,1.1,'0.5'):
                f=fixture(); f[field]=v
                with self.assertRaises(ValueError):predict_event(f)
        for v in (0,1):
            f=fixture();f['prior_rate_control']=v
            with self.assertRaises(ValueError):predict_event(f)
        for v in (-1,True,1.5):
            f=fixture();f['support']=v
            with self.assertRaises(ValueError):predict_event(f)
        f=fixture();f['unknown_mass']=0
        with self.assertRaises(ValueError):predict_event(f)

    def test_schema_and_expert_validation(self):
        for f in (None,{},[],{'ticket':'x'}):
            with self.assertRaises(ValueError):predict_event(f)
        for expert in (None,'',5):
            with self.assertRaises(ValueError):predict_event(fixture(),expert=expert)
        f=fixture();f['expert_probabilities']=[]
        with self.assertRaises(ValueError):predict_event(f)


if __name__=='__main__':
    unittest.main(verbosity=2)
