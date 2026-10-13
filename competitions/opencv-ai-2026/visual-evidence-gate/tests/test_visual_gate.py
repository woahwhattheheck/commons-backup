from __future__ import annotations

import base64
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import aws_lambda
import evaluate
import visual_gate as g


class VisualEvidenceGateTests(unittest.TestCase):
    def _trace(self, hazard="none", **kwargs):
        return g.compile_trace(g.synthetic_scene(hazard=hazard), observed_ms=1000, now_ms=1100, **kwargs)

    def test_synthetic_scene_deterministic(self):
        a = g.synthetic_scene(hazard="left")
        b = g.synthetic_scene(hazard="left")
        self.assertTrue(np.array_equal(a, b))
        self.assertFalse(np.array_equal(a, g.synthetic_scene(hazard="right")))

    def test_clear_changes_to_capture_next_frame(self):
        t = self._trace("none")
        self.assertEqual(t["perception"]["visual_class"], "CLEAR")
        self.assertEqual(t["decision"]["tool_plan"], "CAPTURE_NEXT_FRAME")
        self.assertTrue(g.verify_trace(t))

    def test_left_changes_to_left_inspection(self):
        t = self._trace("left")
        self.assertEqual(t["perception"]["visual_class"], "HAZARD_LEFT")
        self.assertEqual(t["decision"]["tool_plan"], "INSPECT_LEFT_ZONE")

    def test_right_changes_to_right_inspection(self):
        t = self._trace("right")
        self.assertEqual(t["perception"]["visual_class"], "HAZARD_RIGHT")
        self.assertEqual(t["decision"]["tool_plan"], "INSPECT_RIGHT_ZONE")

    def test_center_forces_human_approval(self):
        t = self._trace("center")
        self.assertEqual(t["perception"]["visual_class"], "HAZARD_CENTER")
        self.assertEqual(t["decision"]["decision"], "HUMAN_APPROVAL_REQUIRED")
        self.assertEqual(t["decision"]["tool_plan"], "NO_ACTION")

    def test_unsafe_action_class_forces_human_approval(self):
        t = self._trace("left", requested_action_class="PHYSICAL_ACTUATION")
        self.assertEqual(t["decision"]["decision"], "HUMAN_APPROVAL_REQUIRED")
        self.assertEqual(t["decision"]["reason"], "UNSAFE_OR_UNKNOWN_ACTION_CLASS")
        self.assertFalse(t["decision"]["physical_actuation_authorized"])

    def test_stale_evidence_holds(self):
        ev = g.evidence(g.detect(g.synthetic_scene(hazard="left"), observed_ms=1000))
        out = g.decide(ev, now_ms=1000 + g.MAX_AGE_MS + 1)
        self.assertEqual(out["decision"], "HOLD_EVIDENCE")
        self.assertEqual(out["tool_plan"], "NO_ACTION")

    def test_future_evidence_holds(self):
        ev = g.evidence(g.detect(g.synthetic_scene(hazard="left"), observed_ms=2000))
        out = g.decide(ev, now_ms=1999)
        self.assertEqual(out["decision"], "HOLD_EVIDENCE")

    def test_digest_tamper_holds(self):
        ev = g.evidence(g.detect(g.synthetic_scene(hazard="left"), observed_ms=1000))
        ev["hazard_ppm"] += 1
        out = g.decide(ev, now_ms=1100)
        self.assertEqual(out["decision"], "HOLD_EVIDENCE")

    def test_unknown_key_holds(self):
        ev = g.evidence(g.detect(g.synthetic_scene(hazard="left"), observed_ms=1000))
        ev["trust_me"] = True
        out = g.decide(ev, now_ms=1100)
        self.assertEqual(out["decision"], "HOLD_EVIDENCE")

    def test_wrong_detector_generation_holds(self):
        ev = g.evidence(g.detect(g.synthetic_scene(hazard="left"), observed_ms=1000))
        ev["detector"] = "caller-v999"
        unsigned = {k: ev[k] for k in ev if k != "evidence_sha256"}
        ev["evidence_sha256"] = g.digest_obj(unsigned)
        out = g.decide(ev, now_ms=1100)
        self.assertEqual(out["decision"], "HOLD_EVIDENCE")

    def test_trace_digest_tamper_fails_verification(self):
        t = self._trace("right")
        t["decision"]["tool_plan"] = "DO_DANGEROUS_THING"
        self.assertFalse(g.verify_trace(t))

    def test_authority_is_all_false(self):
        for hazard in ("none", "left", "center", "right"):
            t = self._trace(hazard)
            self.assertFalse(any(t["authority"].values()))
            self.assertFalse(t["decision"]["physical_actuation_authorized"])

    def test_frame_type_and_size_rejected(self):
        with self.assertRaises(g.GateError):
            g.detect(np.zeros((10, 10), dtype=np.uint8), observed_ms=0)
        with self.assertRaises(g.GateError):
            g.synthetic_scene(width=20, height=20)

    def test_bad_synthetic_hazard_rejected(self):
        with self.assertRaises(g.GateError):
            g.synthetic_scene(hazard="person")

    def test_local_runtime_truth_does_not_forge_opencv5(self):
        t = self._trace("left")
        actual_major = int(cv2.__version__.split(".")[0])
        self.assertEqual(t["runtime_truth"]["opencv5_execution_evidenced"], actual_major >= 5)

    def test_evaluation_suite_expected_behavior(self):
        result = evaluate.run_suite()
        self.assertEqual(result["synthetic_cases"], 4)
        self.assertEqual(result["passed"], 4)
        self.assertEqual(result["success_ppm"], 1_000_000)
        self.assertFalse(result["claims"]["natural_video_accuracy_measured"])
        self.assertEqual(result["claims"]["opencv5_runtime_evidenced"], g.opencv5_runtime_evidenced())
        self.assertFalse(result["claims"]["aws_runtime_evidenced"])

    def test_lambda_shape_executes_same_gate_without_aws_claim(self):
        frame = g.synthetic_scene(hazard="right")
        ok, encoded = cv2.imencode(".png", frame)
        self.assertTrue(bool(ok))
        event = {
            "image_base64": base64.b64encode(encoded.tobytes()).decode("ascii"),
            "observed_ms": 1000,
            "now_ms": 1100,
            "requested_action_class": "ADVISORY",
        }
        out = aws_lambda.handler(event)
        self.assertEqual(out["statusCode"], 200)
        self.assertEqual(out["body"]["decision"]["tool_plan"], "INSPECT_RIGHT_ZONE")
        self.assertFalse(out["aws_truth"]["deployment_evidenced"])

    def test_lambda_rejects_bad_event_shape(self):
        out = aws_lambda.handler({"image_base64": "x", "observed_ms": 1})
        self.assertEqual(out["statusCode"], 400)

    def test_lambda_rejects_invalid_base64_and_decode(self):
        bad = {"image_base64": "!!!!", "observed_ms": 1, "now_ms": 2, "requested_action_class": "ADVISORY"}
        self.assertEqual(aws_lambda.handler(bad)["statusCode"], 400)
        bad["image_base64"] = base64.b64encode(b"not-an-image").decode("ascii")
        self.assertEqual(aws_lambda.handler(bad)["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
