from __future__ import annotations

import copy
import math
import unittest

import cv2
import numpy as np

from gaugeproof.core import Calibration, InspectionDecision, analyze_frame, inspect_sequence
from gaugeproof.receipt import compile_receipt, verify_receipt
from gaugeproof.synthetic import render_gauge, render_sequence


CAL = Calibration(135.0, 405.0, 0.0, 100.0, "psi")


class GaugeProofTests(unittest.TestCase):
    def assertReadingNear(self, expected: float, *, delta: float = 2.0, **kwargs) -> None:
        image = render_gauge(expected, CAL, **kwargs)
        reading = analyze_frame(image, CAL)
        self.assertTrue(reading.accepted, reading)
        self.assertIsNotNone(reading.value)
        self.assertAlmostEqual(float(reading.value), expected, delta=delta)

    def test_reads_synthetic_gauge_across_arc(self) -> None:
        for value in (5.0, 25.0, 50.0, 75.0, 95.0):
            with self.subTest(value=value):
                self.assertReadingNear(value)

    def test_reads_off_center_gauge(self) -> None:
        self.assertReadingNear(61.0, center=(280, 245), radius=180)

    def test_blur_fails_closed(self) -> None:
        reading = analyze_frame(render_gauge(50.0, CAL, blur_sigma=9.0), CAL)
        self.assertFalse(reading.accepted)
        self.assertEqual(reading.reason, "image_blurred")

    def test_glare_fails_closed(self) -> None:
        reading = analyze_frame(render_gauge(50.0, CAL, glare=True), CAL)
        self.assertFalse(reading.accepted)
        self.assertIn(reading.reason, {"excessive_glare", "dial_occluded_or_incomplete", "pointer_low_contrast"})

    def test_heavy_occlusion_refuses(self) -> None:
        reading = analyze_frame(render_gauge(50.0, CAL, occlusion_fraction=0.70), CAL)
        self.assertFalse(reading.accepted)

    def test_second_pointer_is_ambiguous(self) -> None:
        reading = analyze_frame(render_gauge(30.0, CAL, second_pointer_value=70.0), CAL)
        self.assertFalse(reading.accepted)
        self.assertEqual(reading.reason, "pointer_ambiguous")

    def test_stable_temporal_sequence_accepts(self) -> None:
        frames = render_sequence([49.5, 50.0, 50.4, 49.9, 50.2], CAL)
        result = inspect_sequence(frames, CAL)
        self.assertEqual(result.decision, InspectionDecision.ACCEPT_READING)
        self.assertFalse(result.side_effects_authorized)
        self.assertAlmostEqual(float(result.value), 50.0, delta=1.0)

    def test_temporal_disagreement_escalates(self) -> None:
        frames = render_sequence([20.0, 20.5, 78.0, 79.0, 80.0], CAL)
        result = inspect_sequence(frames, CAL)
        self.assertEqual(result.decision, InspectionDecision.ESCALATE_HUMAN)
        self.assertIsNone(result.value)
        self.assertFalse(result.side_effects_authorized)

    def test_too_many_rejected_frames_reinspect(self) -> None:
        good = render_gauge(50.0, CAL)
        bad = render_gauge(50.0, CAL, blur_sigma=9.0)
        result = inspect_sequence([good, good, good, bad, bad, bad], CAL)
        self.assertEqual(result.decision, InspectionDecision.REINSPECT)

    def test_receipt_is_deterministic_and_tamper_evident(self) -> None:
        frames = render_sequence([49.5, 50.0, 50.4], CAL)
        r1, a1 = compile_receipt(frames, CAL)
        r2, a2 = compile_receipt(frames, CAL)
        self.assertEqual(r1, r2)
        self.assertEqual(a1, a2)
        self.assertTrue(verify_receipt(r1))
        self.assertFalse(r1["authority"]["equipment_control_authorized"])
        tampered = copy.deepcopy(r1)
        tampered["inspection"]["decision"] = "ACCEPT_READING" if r1["inspection"]["decision"] != "ACCEPT_READING" else "ESCALATE_HUMAN"
        self.assertFalse(verify_receipt(tampered))

    def test_receipt_rejects_authority_escalation_even_if_rehashed_absent(self) -> None:
        frames = render_sequence([50.0, 50.1, 49.9], CAL)
        receipt, _ = compile_receipt(frames, CAL)
        receipt["authority"]["equipment_control_authorized"] = True
        self.assertFalse(verify_receipt(receipt))

    def test_receipt_authority_schema_is_exact(self) -> None:
        frames = render_sequence([50.0, 50.1, 49.9], CAL)
        receipt, _ = compile_receipt(frames, CAL)
        receipt["authority"]["maintenance_completion_asserted"] = True
        self.assertFalse(verify_receipt(receipt))
        receipt2, _ = compile_receipt(frames, CAL)
        receipt2["authority"]["extra_authority"] = False
        self.assertFalse(verify_receipt(receipt2))

    def test_nonfinite_calibration_fails(self) -> None:
        with self.assertRaises(ValueError):
            Calibration(135.0, math.inf, 0.0, 100.0, "psi").validate()
        with self.assertRaises(ValueError):
            Calibration(135.0, 405.0, float("nan"), 100.0, "psi").validate()

    def test_malformed_images_fail(self) -> None:
        with self.assertRaises(ValueError):
            analyze_frame(np.zeros((10, 10), dtype=np.uint8), CAL)
        with self.assertRaises(ValueError):
            analyze_frame(np.zeros((256, 256), dtype=np.float32), CAL)
        with self.assertRaises(ValueError):
            analyze_frame(np.zeros((256, 256, 2), dtype=np.uint8), CAL)

    def test_pointer_outside_calibration_refuses(self) -> None:
        narrow = Calibration(180.0, 300.0, 0.0, 100.0, "psi")
        # Build with a wider calibration, then interpret under a narrow one.
        image = render_gauge(5.0, CAL)
        reading = analyze_frame(image, narrow)
        self.assertFalse(reading.accepted)
        self.assertEqual(reading.reason, "pointer_outside_calibration")

    def test_input_bytes_affect_receipt_identity(self) -> None:
        frames = render_sequence([50.0, 50.0, 50.0], CAL)
        r1, _ = compile_receipt(frames, CAL)
        mutated = [f.copy() for f in frames]
        mutated[0][0, 0] ^= 1
        r2, _ = compile_receipt(mutated, CAL)
        self.assertNotEqual(r1["frame_evidence"][0]["input_sha256"], r2["frame_evidence"][0]["input_sha256"])
        self.assertNotEqual(r1["receipt_sha256"], r2["receipt_sha256"])


if __name__ == "__main__":
    unittest.main()
