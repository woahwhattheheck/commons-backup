import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import casmi_2026 as C


class CasmiQualifyTests(unittest.TestCase):
    def test_default_holds(self):
        packet = C.qualify()
        self.assertEqual(packet["decision"], C.QUALIFY_HOLD)
        self.assertIn("kaggle_terms_accepted", packet["missing"])
        self.assertFalse(packet["authority"]["kaggle_submit"])
        self.assertFalse(packet["authority"]["cash"])
        self.assertEqual(packet["facts"]["prize_is"], "PUBLIC_FACT_NOT_CASH")
        self.assertEqual(packet["facts"]["prize_pool_usd"], 50000)
        self.assertTrue(packet["packet_sha256"])

    def test_partial_evidence_still_holds(self):
        packet = C.qualify({"kaggle_terms_accepted": True, "owner_team_name": "tjlabs"})
        self.assertEqual(packet["decision"], C.QUALIFY_HOLD)
        self.assertEqual(packet["missing"], ["owner_submission_authorized"])

    def test_truthy_string_is_not_acceptance(self):
        packet = C.qualify(
            {
                "kaggle_terms_accepted": "true",
                "owner_team_name": "tjlabs",
                "owner_submission_authorized": "yes",
            }
        )
        self.assertEqual(packet["decision"], C.QUALIFY_HOLD)

    def test_internal_ready_does_not_authorize_submit(self):
        packet = C.qualify(
            {
                "kaggle_terms_accepted": True,
                "owner_team_name": "tjlabs",
                "owner_submission_authorized": True,
            }
        )
        self.assertEqual(packet["decision"], "INTERNAL_READY_NOT_SUBMITTED")
        self.assertEqual(packet["missing"], [])
        self.assertFalse(packet["authority"]["kaggle_submit"])
        self.assertFalse(packet["authority"]["prize_claim"])


class CasmiSpectrumTests(unittest.TestCase):
    def test_valid_demo(self):
        out = C.parse_spectrum(
            {"spectrum_id": "syn-1", "precursor_mz": 181.07, "peaks": [[80.0, 10.0], [181.07, 100.0]]}
        )
        self.assertEqual(out["kind"], "DEMO_CAPABILITY")
        self.assertEqual(out["n_peaks"], 2)
        self.assertTrue(out["not_a_submission"])

    def test_missing_fields_fail_closed(self):
        with self.assertRaises(ValueError):
            C.parse_spectrum({"spectrum_id": "x"})

    def test_bad_peak_fail_closed(self):
        with self.assertRaises(ValueError):
            C.parse_spectrum(
                {"spectrum_id": "x", "precursor_mz": 100, "peaks": [[-1, 1]]}
            )

    def test_empty_peaks_fail_closed(self):
        with self.assertRaises(ValueError):
            C.parse_spectrum({"spectrum_id": "x", "precursor_mz": 100, "peaks": []})


class CasmiCliTests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "casmi_2026.py"), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_qualify_cli(self):
        proc = self._run("--qualify")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        packet = json.loads(proc.stdout)
        self.assertEqual(packet["decision"], C.QUALIFY_HOLD)

    def test_demo_cli(self):
        rec = json.dumps(
            {"spectrum_id": "cli", "precursor_mz": 100.0, "peaks": [[50.0, 1.0]]}
        )
        proc = self._run("--demo-spectrum", rec)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["kind"], "DEMO_CAPABILITY")


if __name__ == "__main__":
    unittest.main()
