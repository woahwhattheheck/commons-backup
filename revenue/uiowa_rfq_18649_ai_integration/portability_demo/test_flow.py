"""One end-to-end regression for the preserved-source integration."""
import contextlib
import copy
import io
import json
import unittest

from run_demo import main, verify


class PortabilityFlow(unittest.TestCase):
    def test_fixed_corpus_response_boundary_and_assessor_bridge(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(len(report["runs"]), 8)
        self.assertEqual(sum(r["summary"]["items"] for r in report["runs"]), 40)
        self.assertEqual(report["comparison"]["alpha_human_review"], 2)
        self.assertEqual(report["comparison"]["beta_human_review"], 3)
        self.assertEqual(sum(r["summary"]["degraded"] for r in report["runs"]), 30)
        late = report["late_response_example"]
        self.assertTrue(late["startup_probe"]["conformant"])
        self.assertTrue(late["guarded_startup_probe"]["conformant"])
        self.assertFalse(late["unchanged_caller_without_guard"]["needs_human_review"])
        self.assertTrue(late["unchanged_caller_with_guard"]["needs_human_review"])
        for alt in report["assessment"]["cases"][0]["alternatives"]:
            self.assertEqual(alt["status"], "unknown")
            self.assertEqual(alt["checks"]["portability:adapter_swap"], "supported_by_inputs")
            self.assertEqual(alt["checks"]["degraded_mode"], "unknown")
        verify(report)
        altered = copy.deepcopy(report)
        altered["corpus"][0]["doc_id"] = "different-population"
        with self.assertRaises(ValueError):
            verify(altered)
        print("8 toy runs / 40 outcomes; human queues alpha=2 beta=3; faults=30/30 review; "
              "late NaN guarded; assessor UNKNOWN; edited population rejected")


if __name__ == "__main__":
    unittest.main()
