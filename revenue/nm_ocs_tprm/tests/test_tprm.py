import copy
import unittest

from revenue.nm_ocs_tprm.tprm import (
    ValidationError,
    compile_assessment,
    compile_portfolio,
    verify_assessment_packet,
    verify_portfolio_packet,
)


def assessment(tenant="county-a", vendor="vendor-1"):
    return {
        "schema": "tjlabs.nm-ocs-tprm.assessment.v1",
        "tenant": {"tenant_id": tenant, "display_name": tenant},
        "vendor": {"vendor_id": vendor, "display_name": vendor},
        "factors": {
            "data_sensitivity": 3,
            "privilege": 2,
            "criticality": 2,
            "internet_exposure": 1,
        },
        "controls": [
            {
                "framework": "NIST-CSF-2.0",
                "control_id": "GV.SC-04",
                "status": "SATISFIED",
                "evidence_sha256": "1" * 64,
                "note": "Evidence is present; this is not a compliance certification.",
            },
            {
                "framework": "NIST-CSF-2.0",
                "control_id": "GV.SC-05",
                "status": "UNKNOWN",
                "evidence_sha256": None,
                "note": "Awaiting buyer-approved evidence.",
            },
        ],
        "monitoring_events": [
            {
                "event_id": "evt-1",
                "observed_at": "2026-09-17T00:00:00Z",
                "kind": "VULNERABILITY",
                "severity": 3,
                "evidence_sha256": "2" * 64,
                "summary": "Synthetic high-severity observation for test coverage.",
            }
        ],
        "assessment": {
            "as_of": "2026-09-17T01:00:00Z",
            "review_id": "review-1",
            "policy_id": "reference-v1",
        },
    }


class AssessmentTests(unittest.TestCase):
    def test_deterministic_and_verifies(self):
        a = compile_assessment(assessment())
        b = compile_assessment(copy.deepcopy(assessment()))
        self.assertEqual(a, b)
        self.assertTrue(verify_assessment_packet(a))
        self.assertEqual(a["reference_tier"], "TIER_1")
        self.assertFalse(a["authority"]["compliance_claimed"])
        self.assertFalse(a["authority"]["submission_authorized"])

    def test_input_order_does_not_change_receipt(self):
        x = assessment()
        extra = {
            "framework": "CIS",
            "control_id": "1.1",
            "status": "GAP",
            "evidence_sha256": "3" * 64,
            "note": "Synthetic gap.",
        }
        x["controls"].append(extra)
        y = copy.deepcopy(x)
        y["controls"].reverse()
        self.assertEqual(
            compile_assessment(x)["receipt_sha256"],
            compile_assessment(y)["receipt_sha256"],
        )

    def test_tamper_breaks_verification(self):
        packet = compile_assessment(assessment())
        packet["reference_tier"] = "TIER_3"
        self.assertFalse(verify_assessment_packet(packet))

    def test_satisfied_requires_evidence(self):
        x = assessment()
        x["controls"][0]["evidence_sha256"] = None
        with self.assertRaises(ValidationError):
            compile_assessment(x)

    def test_duplicate_control_rejected(self):
        x = assessment()
        x["controls"].append(copy.deepcopy(x["controls"][0]))
        with self.assertRaises(ValidationError):
            compile_assessment(x)

    def test_duplicate_event_rejected(self):
        x = assessment()
        x["monitoring_events"].append(copy.deepcopy(x["monitoring_events"][0]))
        with self.assertRaises(ValidationError):
            compile_assessment(x)

    def test_future_event_rejected(self):
        x = assessment()
        x["monitoring_events"][0]["observed_at"] = "2026-09-18T00:00:00Z"
        with self.assertRaises(ValidationError):
            compile_assessment(x)

    def test_fractional_future_event_rejected_by_instant(self):
        x = assessment()
        x["assessment"]["as_of"] = "2026-09-17T00:00:00Z"
        x["monitoring_events"][0]["observed_at"] = "2026-09-17T00:00:00.500000Z"
        with self.assertRaises(ValidationError):
            compile_assessment(x)

    def test_non_integer_factor_rejected_even_when_bool(self):
        x = assessment()
        x["factors"]["privilege"] = True
        with self.assertRaises(ValidationError):
            compile_assessment(x)

    def test_non_finite_rejected(self):
        x = assessment()
        x["factors"]["privilege"] = float("nan")
        with self.assertRaises(ValidationError):
            compile_assessment(x)

    def test_unexpected_key_rejected(self):
        x = assessment()
        x["tenant"]["secret"] = "cross-tenant-leak"
        with self.assertRaises(ValidationError):
            compile_assessment(x)


class PortfolioTests(unittest.TestCase):
    def test_same_vendor_across_tenants_is_isolated(self):
        p = {
            "schema": "tjlabs.nm-ocs-tprm.portfolio.v1",
            "portfolio_id": "portfolio-1",
            "assessments": [
                assessment("county-a", "shared-vendor"),
                assessment("tribe-b", "shared-vendor"),
            ],
        }
        packet = compile_portfolio(p)
        self.assertTrue(verify_portfolio_packet(packet))
        self.assertEqual(len(packet["tenant_roots"]), 2)
        self.assertNotEqual(
            packet["tenant_roots"][0]["tenant_root_sha256"],
            packet["tenant_roots"][1]["tenant_root_sha256"],
        )
        self.assertFalse(packet["authority"]["cross_tenant_data_merge_authorized"])

    def test_duplicate_vendor_within_tenant_rejected(self):
        p = {
            "schema": "tjlabs.nm-ocs-tprm.portfolio.v1",
            "portfolio_id": "portfolio-1",
            "assessments": [assessment(), assessment()],
        }
        with self.assertRaises(ValidationError):
            compile_portfolio(p)

    def test_portfolio_tamper_rejected(self):
        p = {
            "schema": "tjlabs.nm-ocs-tprm.portfolio.v1",
            "portfolio_id": "portfolio-1",
            "assessments": [assessment()],
        }
        packet = compile_portfolio(p)
        packet["tenant_roots"][0]["assessment_receipts"][0] = "0" * 64
        self.assertFalse(verify_portfolio_packet(packet))

    def test_empty_portfolio_rejected(self):
        with self.assertRaises(ValidationError):
            compile_portfolio(
                {
                    "schema": "tjlabs.nm-ocs-tprm.portfolio.v1",
                    "portfolio_id": "p",
                    "assessments": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
