from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusionmeter.calibrate import fit_certificate
from fusionmeter.core import FusionMeterError, MeterSample, OutOfDomainError, canonical_json, predict, sha256_json
from fusionmeter.readiness import evaluate_readiness
from fusionmeter.synthetic_fixture import build_rows


class FusionMeterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.training, cls.validation = build_rows()
        cls.fixture_certificate = json.loads((ROOT / "fixtures/synthetic_certificate.json").read_text())
        payload = {"training": cls.training, "validation": cls.validation}
        cls.source_sha = hashlib.sha256(canonical_json(payload).encode()).hexdigest()

    def test_certificate_rebuild_is_deterministic(self):
        a = fit_certificate(self.training, self.validation, source_sha256=self.source_sha)
        b = fit_certificate(self.training, self.validation, source_sha256=self.source_sha)
        self.assertEqual(canonical_json(a), canonical_json(b))
        self.assertEqual(a, self.fixture_certificate)

    def test_synthetic_certificate_cannot_claim_field_authority(self):
        sample = MeterSample.from_mapping(self.validation[0]["sample"])
        result = predict(self.fixture_certificate, sample)
        self.assertEqual(result["authority"], "DEMONSTRATION_ONLY")
        self.assertEqual(result["evidence_class"], "SYNTHETIC")
        self.assertIn("not GUM", result["screening_uncertainty_semantics"])

    def test_prediction_receipt_is_stable(self):
        sample = MeterSample.from_mapping(self.validation[1]["sample"])
        first = predict(self.fixture_certificate, sample)
        second = predict(self.fixture_certificate, sample)
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])
        body = dict(first)
        digest = body.pop("receipt_sha256")
        self.assertEqual(digest, sha256_json(body))

    def test_out_of_domain_pressure_refuses(self):
        value = copy.deepcopy(self.validation[0]["sample"])
        value["pressure_kgf_cm2"] = 85.0001
        with self.assertRaises(OutOfDomainError):
            predict(self.fixture_certificate, MeterSample.from_mapping(value))

    def test_out_of_domain_temperature_refuses(self):
        value = copy.deepcopy(self.validation[0]["sample"])
        value["temperature_c"] = 29.999
        with self.assertRaises(OutOfDomainError):
            predict(self.fixture_certificate, MeterSample.from_mapping(value))

    def test_sensor_fault_refuses(self):
        value = copy.deepcopy(self.validation[0]["sample"])
        value["sensor_health"] = False
        with self.assertRaisesRegex(FusionMeterError, "sensor health"):
            predict(self.fixture_certificate, MeterSample.from_mapping(value))

    def test_impossible_plr_refuses(self):
        value = copy.deepcopy(self.validation[0]["sample"])
        value["permanent_loss_kpa"] = value["primary_dp_kpa"]
        with self.assertRaisesRegex(FusionMeterError, "permanent-loss ratio"):
            MeterSample.from_mapping(value)

    def test_certificate_tamper_refuses(self):
        cert = copy.deepcopy(self.fixture_certificate)
        cert["coefficients"][0] += 0.01
        sample = MeterSample.from_mapping(self.validation[0]["sample"])
        with self.assertRaisesRegex(FusionMeterError, "certificate_sha256 mismatch"):
            predict(cert, sample)

    def test_unknown_sample_field_refuses(self):
        value = copy.deepcopy(self.validation[0]["sample"])
        value["secret_liquid_rate"] = 123.0
        with self.assertRaisesRegex(FusionMeterError, "unknown sample fields"):
            MeterSample.from_mapping(value)

    def test_fit_requires_independent_validation_volume(self):
        with self.assertRaisesRegex(FusionMeterError, "at least 6"):
            fit_certificate(self.training, self.validation[:5], source_sha256=self.source_sha)

    def test_checked_in_readiness_is_blocked(self):
        readiness = json.loads((ROOT / "readiness.json").read_text())
        result = evaluate_readiness(self.fixture_certificate, readiness)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("representative POC" in item for item in result["blockers"]))
        self.assertTrue(any("human" in item.lower() for item in result["blockers"]))

    def test_even_synthetic_low_error_does_not_release(self):
        cert = copy.deepcopy(self.fixture_certificate)
        self.assertLess(cert["validation"]["p95_abs_error_pct"], 3.0)
        readiness = {
            "schema_version": 1, "measured_total_pressure_drop_psi": 10.0, "continuous_run_hours": 1000, "availability_fraction": 1.0,
            "reference_system_traceable": True, "validation_runs_blinded": True, "aga3_alignment_reviewed": True,
            "online_transmission_tested": True, "hazardous_area_design_reviewed": True, "poc_support_owner_confirmed": True,
            "experience_field_human_authored": True, "ip_rights_reviewed": True, "challenge_agreement_reviewed": True,
            "substantive_human_contribution_confirmed": True,
        }
        result = evaluate_readiness(cert, readiness)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("representative POC calibration certificate is absent", result["blockers"])

    def test_release_requires_full_pressure_temperature_envelope(self):
        cert = copy.deepcopy(self.fixture_certificate)
        cert["evidence_class"] = "REPRESENTATIVE_POC"
        cert["validation"]["count"] = 60
        cert["validation"]["repeatability_p95_pct"] = 2.0
        cert["domain"]["pressure_kgf_cm2"]["min"] = 61.0
        readiness = {
            "schema_version": 1, "measured_total_pressure_drop_psi": 10.0, "continuous_run_hours": 720, "availability_fraction": 0.999,
            "reference_system_traceable": True, "validation_runs_blinded": True, "aga3_alignment_reviewed": True,
            "online_transmission_tested": True, "hazardous_area_design_reviewed": True, "poc_support_owner_confirmed": True,
            "experience_field_human_authored": True, "ip_rights_reviewed": True, "challenge_agreement_reviewed": True,
            "substantive_human_contribution_confirmed": True,
        }
        result = evaluate_readiness(cert, readiness)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("pressure_kgf_cm2" in item for item in result["blockers"]))

    def test_readiness_rejects_nonfinite_numeric_evidence(self):
        cert = copy.deepcopy(self.fixture_certificate)
        readiness = json.loads((ROOT / "readiness.json").read_text())
        readiness["measured_total_pressure_drop_psi"] = "nan"
        readiness["availability_fraction"] = "nan"
        result = evaluate_readiness(cert, readiness)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("pressure drop" in item for item in result["blockers"]))
        self.assertTrue(any("availability" in item for item in result["blockers"]))

    def test_readiness_rejects_tampered_certificate(self):
        cert = copy.deepcopy(self.fixture_certificate)
        cert["evidence_class"] = "REPRESENTATIVE_POC"
        cert["validation"]["count"] = 60
        cert["validation"]["repeatability_p95_pct"] = 2.0
        readiness = {
            "schema_version": 1, "measured_total_pressure_drop_psi": 10.0, "continuous_run_hours": 720, "availability_fraction": 1.0,
            "reference_system_traceable": True, "validation_runs_blinded": True, "aga3_alignment_reviewed": True,
            "online_transmission_tested": True, "hazardous_area_design_reviewed": True, "poc_support_owner_confirmed": True,
            "experience_field_human_authored": True, "ip_rights_reviewed": True, "challenge_agreement_reviewed": True,
            "substantive_human_contribution_confirmed": True,
        }
        result = evaluate_readiness(cert, readiness)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("certificate invalid" in item for item in result["blockers"]))

    def test_readiness_requires_repeatability_not_only_accuracy(self):
        cert = copy.deepcopy(self.fixture_certificate)
        cert["evidence_class"] = "REPRESENTATIVE_POC"
        cert["validation"]["count"] = 60
        cert["validation"]["p95_abs_error_pct"] = 2.0
        cert["validation"]["repeatability_p95_pct"] = None
        body = dict(cert)
        body.pop("certificate_sha256")
        cert["certificate_sha256"] = sha256_json(body)
        readiness = {
            "schema_version": 1, "measured_total_pressure_drop_psi": 10.0, "continuous_run_hours": 720, "availability_fraction": 1.0,
            "reference_system_traceable": True, "validation_runs_blinded": True, "aga3_alignment_reviewed": True,
            "online_transmission_tested": True, "hazardous_area_design_reviewed": True, "poc_support_owner_confirmed": True,
            "experience_field_human_authored": True, "ip_rights_reviewed": True, "challenge_agreement_reviewed": True,
            "substantive_human_contribution_confirmed": True,
        }
        result = evaluate_readiness(cert, readiness)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("repeated-condition" in item for item in result["blockers"]))

    def test_cli_readiness_exits_blocked(self):
        proc = subprocess.run([sys.executable, "-m", "fusionmeter.cli", "readiness", "fixtures/synthetic_certificate.json", "readiness.json"], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn('"status":"BLOCKED"', proc.stdout)


if __name__ == "__main__":
    unittest.main()
