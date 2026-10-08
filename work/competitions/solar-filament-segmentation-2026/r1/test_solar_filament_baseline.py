import unittest
import numpy as np

from solar_filament_baseline import connected_components, panoptic_quality, segment_dark_filaments


class SolarFilamentBaselineTests(unittest.TestCase):
    def test_perfect_panoptic_quality(self):
        truth = np.zeros((12, 12), dtype=np.int32)
        truth[2:5, 2:9] = 1
        truth[7:10, 4:10] = 2
        r = panoptic_quality(truth.copy(), truth)
        self.assertEqual(r.pq, 1.0)
        self.assertEqual((r.tp, r.fp, r.fn), (2, 0, 0))
        self.assertEqual(r.fragmentation_count, 0)
        self.assertEqual(r.overmerge_count, 0)

    def test_fragmentation_is_visible(self):
        truth = np.zeros((10, 14), dtype=np.int32)
        truth[3:7, 2:12] = 1
        pred = np.zeros_like(truth)
        pred[3:7, 2:6] = 1
        pred[3:7, 8:12] = 2
        r = panoptic_quality(pred, truth)
        self.assertGreaterEqual(r.fragmentation_count, 1)
        self.assertLess(r.pq, 1.0)

    def test_overmerge_is_visible(self):
        truth = np.zeros((10, 16), dtype=np.int32)
        truth[3:7, 2:6] = 1
        truth[3:7, 10:14] = 2
        pred = np.zeros_like(truth)
        pred[3:7, 2:14] = 1
        r = panoptic_quality(pred, truth)
        self.assertGreaterEqual(r.overmerge_count, 1)
        self.assertLess(r.pq, 1.0)

    def test_dark_filament_baseline_detects_synthetic_structure(self):
        image = np.ones((64, 64), dtype=np.float32)
        image[28:34, 10:54] = 0.05
        image += np.linspace(0, 0.1, 64, dtype=np.float32)[None, :]
        pred = segment_dark_filaments(image, dark_quantile=0.16, min_area=20)
        self.assertGreater(pred.max(), 0)
        self.assertGreater(np.count_nonzero(pred[28:34, 10:54]), 120)

    def test_component_labels_are_deterministic(self):
        mask = np.zeros((8, 12), dtype=bool)
        mask[1:3, 1:4] = True
        mask[5:7, 8:11] = True
        a = connected_components(mask, min_area=1)
        b = connected_components(mask, min_area=1)
        self.assertTrue(np.array_equal(a, b))
        self.assertEqual(set(np.unique(a)), {0, 1, 2})


if __name__ == "__main__":
    unittest.main()
