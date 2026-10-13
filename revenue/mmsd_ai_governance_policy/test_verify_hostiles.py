import copy
import math
import unittest

from revenue.mmsd_ai_governance_policy.engine import canonical_bytes, compile_report, sha256, verify_report

H = "1" * 64
V = "2" * 64


def system():
    return {
        "system_id": "sys-1",
        "system_kind": "GENERATIVE",
        "deployment": "INTERNAL",
        "data_class": "PUBLIC",
        "external_processing": "NO",
        "provider_training": "NO",
        "physical_influence": "NONE",
        "human_override": "YES",
        "monitoring": "YES",
        "validation_evidence_sha256": V,
        "public_records_status": "APPLIES",
        "retention_status": "DEFINED",
        "vendor_change_notice": "YES",
        "incident_plan": "YES",
        "manual_fallback": "YES",
        "evidence_sha256": H,
    }


def packet():
    return {
        "schema": "commons-ai-governance-inventory/v1",
        "inventory_id": "inv",
        "inventory_generation": 1,
        "systems": [system()],
    }


class VerifyHostileReportTests(unittest.TestCase):
    def _report(self):
        return compile_report(packet())

    def test_float_in_report_returns_false_not_exception(self):
        report = self._report()
        report["systems"][0]["overall_risk"] = 1.0
        self.assertFalse(verify_report(packet(), report))

    def test_nonfinite_float_in_report_returns_false_not_exception(self):
        report = self._report()
        report["systems"][0]["overall_risk"] = math.nan
        self.assertFalse(verify_report(packet(), report))

    def test_bytearray_in_report_returns_false_not_exception(self):
        report = self._report()
        report["systems"][0]["holds"] = bytearray(b"x")
        self.assertFalse(verify_report(packet(), report))

    def test_non_string_nested_key_in_report_returns_false_not_exception(self):
        report = self._report()
        report["systems"][0][1] = "hostile"
        self.assertFalse(verify_report(packet(), report))

    def test_oversized_integer_in_report_returns_false_not_exception(self):
        report = self._report()
        report["systems"][0]["overall_risk"] = 10 ** 5000
        self.assertFalse(verify_report(packet(), report))

    def test_valid_report_roundtrip_stays_true(self):
        p = packet()
        report = compile_report(p)
        self.assertTrue(verify_report(copy.deepcopy(p), copy.deepcopy(report)))

    def test_valid_shape_tamper_stays_false(self):
        p = packet()
        report = compile_report(p)
        report["state"] = "HOLD_SUPPLIED_ROWS"
        self.assertFalse(verify_report(p, report))

    def test_resealed_semantic_tamper_stays_false(self):
        p = packet()
        report = compile_report(p)
        report["systems"][0]["overall_risk"] = 4
        candidate = {k: v for k, v in report.items() if k != "receipt_sha256"}
        report["receipt_sha256"] = sha256(canonical_bytes(candidate))
        self.assertFalse(verify_report(p, report))

    def test_malformed_packet_stays_false(self):
        p = packet()
        report = compile_report(p)
        p["inventory_generation"] = 1.0
        self.assertFalse(verify_report(p, report))

    def test_oversized_generation_stays_false_not_exception(self):
        p = packet()
        report = compile_report(p)
        p["inventory_generation"] = 10 ** 5000
        self.assertFalse(verify_report(p, report))


if __name__ == "__main__":
    unittest.main()
