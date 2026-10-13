from __future__ import annotations

import unittest
from datetime import date

from closeout import deadline_for, evaluate


def inv(eid: str, *, sensitivity="confidential", received="yes", location="authorized_private_vault", digest="sha256:test"):
    return {
        "evidence_id": eid,
        "source_owner": "Synthetic owner",
        "custodian": "Synthetic custodian",
        "description": "Synthetic fixture",
        "sensitivity": sensitivity,
        "received": received,
        "custody_location": location,
        "authorized_purpose": "RFQ 18649 assessment preparation",
        "received_date": "2026-11-01" if received == "yes" else "",
        "last_verified_date": "2026-11-20",
        "digest": digest if received == "yes" else "",
        "derived_copies": "0",
        "planned_disposition": "destroyed",
        "confirmation_ref": "",
        "exception_ref": "",
        "notes": "fictional",
    }


def disp(eid: str, action="destroyed", action_date="2026-12-10", exception=""):
    return {
        "evidence_id": eid,
        "action": action,
        "action_date": action_date,
        "method": "synthetic secure disposal record",
        "performed_by": "operator-a",
        "verified_by": "operator-b",
        "verification_artifact": f"CONF-{eid}",
        "exception_or_instruction_ref": exception,
        "notes": "fictional",
    }


class CloseoutTests(unittest.TestCase):
    def setUp(self):
        self.engagement = {
            "engagement_id": "SYNTH-18649",
            "completion_date": "2026-11-20",
            "closeout_days": 30,
            "primary_requirement_locator_status": "work_order_pending_primary_locator",
        }

    def test_deadline_is_exactly_30_calendar_days(self):
        self.assertEqual(deadline_for(self.engagement).isoformat(), "2026-12-20")

    def test_complete_packet_passes_with_locator_warning(self):
        report = evaluate(
            self.engagement,
            [inv("E-001"), inv("E-002", sensitivity="internal")],
            [disp("E-001"), disp("E-002", action="returned", action_date="2026-12-15")],
            date(2026, 12, 21),
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["protected_accounted_count"], 2)
        self.assertTrue(any("pending locator" in w for w in report["warnings"]))

    def test_overdue_unaccounted_protected_evidence_fails(self):
        report = evaluate(self.engagement, [inv("E-001")], [], date(2026, 12, 21))
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("deadline has passed" in e for e in report["errors"]))

    def test_retained_exception_requires_written_reference(self):
        report = evaluate(
            self.engagement,
            [inv("E-001")],
            [disp("E-001", action="retained_by_instruction", action_date="2026-12-15", exception="")],
            date(2026, 12, 21),
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("written exception" in e for e in report["errors"]))

    def test_restricted_public_repo_is_rejected(self):
        report = evaluate(
            self.engagement,
            [inv("E-001", sensitivity="restricted", location="public_repo:github.com/woahwhattheheck/commons")],
            [disp("E-001")],
            date(2026, 12, 21),
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("public repository" in e for e in report["errors"]))

    def test_never_received_credential_is_safe(self):
        record = inv("E-CRD", sensitivity="credential", received="no", location="", digest="")
        never = disp("E-CRD", action="never_received", action_date="")
        never["performed_by"] = ""
        never["verified_by"] = ""
        never["verification_artifact"] = ""
        report = evaluate(self.engagement, [record], [never], date(2026, 12, 21))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["protected_received_count"], 0)

    def test_received_credential_is_rejected(self):
        report = evaluate(
            self.engagement,
            [inv("E-CRD", sensitivity="credential")],
            [disp("E-CRD")],
            date(2026, 12, 21),
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("credential material must not be ingested" in e for e in report["errors"]))

    def test_extra_disposition_kind_is_recorded_without_failing(self):
        report = evaluate(
            self.engagement,
            [inv("E-001"), inv("E-002")],
            [
                disp("E-001"),
                disp("E-002", action="archived_offsite", action_date="2026-12-15"),
            ],
            date(2026, 12, 10),
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["action_counts"].get("archived_offsite"), 1)
        self.assertTrue(any("archived_offsite" in w for w in report["warnings"]))
        self.assertFalse(any("unsupported" in e for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
