import pathlib
import sys
import unittest

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from opencv_perception import analyze_pair
from prooflens import decide


def scene(*, change=False, shift=0):
    image = np.full((480, 640, 3), 180, dtype=np.uint8)
    for x in range(40, 620, 60):
        cv2.line(image, (x, 30), (x, 450), (30, 30, 30), 2)
    for y in range(40, 460, 60):
        cv2.line(image, (30, y), (610, y), (30, 30, 30), 2)
    cv2.putText(image, "PROOFLENS", (150, 235), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (10, 10, 10), 3, cv2.LINE_AA)
    cv2.circle(image, (100, 100), 35, (220, 60, 60), -1)
    if change:
        cv2.rectangle(image, (420, 300), (560, 410), (20, 20, 20), -1)
    if shift:
        matrix = np.float32([[1, 0, shift], [0, 1, shift]])
        image = cv2.warpAffine(image, matrix, (640, 480), borderMode=cv2.BORDER_REFLECT101)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


class OpenCVPerceptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        major = int(cv2.__version__.split(".", 1)[0])
        if major < 5:
            raise AssertionError(f"competition tests require OpenCV 5+, found {cv2.__version__}")

    def test_identical_pair_is_deterministic(self):
        payload = scene()
        first = analyze_pair(payload, payload, source_ref="synthetic:identical")
        second = analyze_pair(payload, payload, source_ref="synthetic:identical")
        self.assertEqual(first, second)
        self.assertEqual(first["changed_fraction"], 0.0)
        self.assertEqual(decide(first).decision, "NO_ACTION")

    def test_localized_change_requests_review(self):
        result = analyze_pair(scene(), scene(change=True), source_ref="synthetic:changed")
        self.assertGreater(result["changed_fraction"], 0.01)
        self.assertEqual(decide(result).decision, "REQUEST_HUMAN_REVIEW")

    def test_small_camera_translation_is_alignment_candidate(self):
        result = analyze_pair(scene(), scene(shift=4), source_ref="synthetic:jitter")
        self.assertGreaterEqual(result["alignment_confidence"], 0.25)
        self.assertGreater(result["quality_score"], 0.55)

    def test_bad_bytes_fail_closed(self):
        with self.assertRaises(ValueError):
            analyze_pair(b"not an image", scene(), source_ref="synthetic:bad")

    def test_aspect_ratio_mismatch_fails_closed(self):
        other = np.full((300, 300, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".png", other)
        self.assertTrue(ok)
        with self.assertRaisesRegex(ValueError, "aspect ratios"):
            analyze_pair(scene(), encoded.tobytes(), source_ref="synthetic:aspect")

    def test_source_ref_changes_event_identity(self):
        payload = scene()
        left = analyze_pair(payload, payload, source_ref="synthetic:a")
        right = analyze_pair(payload, payload, source_ref="synthetic:b")
        self.assertNotEqual(left["event_id"], right["event_id"])


if __name__ == "__main__":
    unittest.main()
