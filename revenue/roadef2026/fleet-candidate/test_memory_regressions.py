"""Peak-only controls usable unchanged against the original and corrected method.

These do not assert the newly introduced coverage metadata: each negative result
reflects a changed observable RSS peak, rather than a missing new attribute.
"""
import unittest
import test_memory_sampling as fixtures
from test_memory_sampling import Proc, fields, actor

class PeakRegressions(unittest.TestCase):
    setUp = fixtures.SamplingTests.setUp
    tearDown = fixtures.SamplingTests.tearDown
    put = fixtures.SamplingTests.put
    virtual = fixtures.SamplingTests.virtual
    run_method = fixtures.SamplingTests.run_method

    def outer(self):
        self.self_path.write_text(fields(8000,1,100,[8000,100]))
        self.put(8000,1,100,[8000,100])
        (self.root/'100/status').unlink()

    def test_outer_procfs_missing_native_pid_is_not_zero(self):
        self.outer();self.put(9000,8000,300,[9000,200])
        self.assertEqual(self.run_method(actor([Proc(200)])).peak_sampled_rss_kib,400)

    def test_unrelated_namespace_number_is_not_counted(self):
        self.outer();self.put(100,1,900000);self.put(200,77,800000,[200,200])
        self.put(9000,8000,300,[9000,200])
        self.assertEqual(self.run_method(actor([Proc(200)])).peak_sampled_rss_kib,400)

    def test_nested_child_resolves_in_parent_namespace(self):
        self.outer();self.put(9000,8000,300,[9000,200,1])
        self.assertEqual(self.run_method(actor([Proc(200)])).peak_sampled_rss_kib,400)

    def test_unreadable_supervisor_does_not_create_zero_peak(self):
        self.self_path.unlink();(self.root/'100/status').unlink()
        self.assertIsNone(self.run_method(actor()).peak_sampled_rss_kib)

    def test_unreadable_active_leader_is_not_partial_peak(self):
        self.put(200,100,None)
        self.assertIsNone(self.run_method(actor([Proc(200)])).peak_sampled_rss_kib)

    def test_repeated_reference_does_not_duplicate_rss(self):
        self.put(200,100,300);p=Proc(200)
        self.assertEqual(self.run_method(actor([p,p],p)).peak_sampled_rss_kib,400)

    def test_incomplete_sample_cannot_raise_old_complete_peak(self):
        self.put(200,100,1000)
        self.assertEqual(self.run_method(actor([Proc(200),Proc(300)],peak=700)).peak_sampled_rss_kib,700)

    def test_native_complete_positive_control(self):
        self.put(200,100,300);self.put(300,100,500)
        self.assertEqual(self.run_method(actor([Proc(200)],Proc(300))).peak_sampled_rss_kib,900)

    def test_dead_leader_and_descendants_remain_excluded(self):
        self.put(200,100,300);self.put(300,200,500);self.put(400,100,600)
        self.assertEqual(self.run_method(actor([Proc(200),Proc(400,0)])).peak_sampled_rss_kib,400)

    def test_missing_child_preserves_higher_old_peak(self):
        self.assertEqual(self.run_method(actor([Proc(200)],peak=900)).peak_sampled_rss_kib,900)

if __name__=='__main__': unittest.main(verbosity=2)
