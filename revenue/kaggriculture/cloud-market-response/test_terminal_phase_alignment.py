# SPDX-License-Identifier: MIT
"""Pure clock/provenance tests for the offline phase experiment."""
from copy import deepcopy
import unittest
from check_terminal_phase_alignment import map_reference_family, training_steps


class PhaseAlignmentTests(unittest.TestCase):
    def test_final_hour_reference(self):
        self.assertEqual(training_steps(718,24,23,5),(719,[599,623,647,671,695]))

    def test_same_hour_reference(self):
        self.assertEqual(training_steps(718,24,22,5),(718,[598,622,646,670,694]))

    def test_new_period_uses_explicit_configuration(self):
        self.assertEqual(training_steps(58,10,9,3),(59,[29,39,49]))

    def test_incomplete_early_history_is_rejected(self):
        with self.assertRaises(ValueError):training_steps(22,24,23,5)

    def test_bad_integer_fields_are_not_coerced(self):
        for args in [(True,24,23,5),(718,24.0,23,5),(718,24,24,5),(718,24,-1,5),(718,24,23,0)]:
            with self.subTest(args=args),self.assertRaises(ValueError):training_steps(*args)

    def test_mapping_keeps_actual_training_timestamps(self):
        family={'now':719,'ready':True,'scenarios':[{'id':'one','origin':{'now':719,
                'witnesses':[{'training_start':695,'training_end':695,'lag':1}]}}]}
        original=deepcopy(family)
        mapped=map_reference_family(family,718,719)
        self.assertEqual(family,original)
        self.assertEqual(mapped['now'],718)
        self.assertEqual(mapped['reference_step'],719)
        self.assertEqual(mapped['scenarios'][0]['origin']['witnesses'],family['scenarios'][0]['origin']['witnesses'])
        self.assertEqual(mapped['scenarios'][0]['origin']['target_step'],718)
        self.assertEqual(mapped['scenarios'][0]['origin']['reference_step'],719)

    def test_future_witness_is_rejected(self):
        f={'scenarios':[{'origin':{'now':719,'witnesses':[{'training_start':718,'training_end':718}]}}]}
        with self.assertRaises(ValueError):map_reference_family(f,718,719)

    def test_origin_mismatch_is_rejected(self):
        f={'scenarios':[{'origin':{'now':717,'witnesses':[]}}]}
        with self.assertRaises(ValueError):map_reference_family(f,718,719)

    def test_not_ready_is_not_filled(self):
        f={'now':719,'ready':False,'status':'insufficient_joint_history','scenarios':[]}
        mapped=map_reference_family(f,718,719)
        self.assertFalse(mapped['ready']);self.assertEqual(mapped['scenarios'],[])


if __name__=='__main__':unittest.main(verbosity=2)
