"""Real component integration, never a mock replacement for the delivery calculator."""
import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
r = importlib.import_module("revenue.uiowa_rfq_18649_timestamps.rehearse_delivery")


class DeliveryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = r.rehearse()

    def test_original_native_metrics_unchanged(self):
        self.assertTrue(self.report["checks"]["original_fixture_metric_identity"])
        m = self.report["native_original_report"]["metrics"]
        self.assertEqual(m["change_lead_time"]["median"], 11.0)
        self.assertEqual(m["change_lead_time"]["mean"], 14.875)
        self.assertEqual(m["deployment_frequency"]["deployments_per_week"], 4.0)
        self.assertEqual(m["failed_deployment_recovery_time"]["median"], 3.0)

    def test_mixed_offset_identity(self):
        self.assertTrue(self.report["checks"]["mixed_offset_metric_identity"])

    def test_real_dst_recovery_and_lead(self):
        self.assertTrue(self.report["checks"]["dst_lead_one_hour"])
        self.assertTrue(self.report["checks"]["dst_recovery_one_hour"])
        m = self.report["native_dst_report"]["metrics"]
        self.assertEqual(m["failed_deployment_recovery_time"]["coverage"]["used"], 1)

    def test_ambiguous_recovery_not_given_to_calculator(self):
        self.assertTrue(self.report["checks"]["ambiguous_recovery_blocks_conversion"])
        self.assertEqual(self.report["ambiguous_recovery_diagnostics"][0]["normalization"]["code"], "ambiguous_local_time")

    def test_explicit_revision_guard_and_module_cleanup(self):
        with self.assertRaises(r.InputError):
            r.rehearse("0" * 40)
        self.assertNotIn("_uiowa129_real_delivery_calculator", sys.modules)

    def test_rehearsal_cli(self):
        result = subprocess.run([sys.executable, str(Path(r.__file__))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "passed")
        # Receipt coverage now includes the DST input, not only the calculator
        # and the ordinary deployment fixture. Assert exact identities, not a count.
        self.assertEqual(set(report["dependency_blobs"]), {
            "uiowa_rfq_18649_delivery_metrics/calculator.py",
            "uiowa_rfq_18649_delivery_metrics/fixtures/synthetic_deployments.csv",
            "uiowa_rfq_18649_timestamps/fixtures/delivery_dst.csv",
        })
        self.assertTrue(all(report["checks"].values()))


if __name__ == "__main__":
    unittest.main()
