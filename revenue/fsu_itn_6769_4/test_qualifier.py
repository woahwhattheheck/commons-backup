import copy
import json
import os
import tempfile
import unittest

from cli import publish_new, read_json_regular
from qualifier import (
    QualificationError,
    compile_qualification,
    loads_strict,
    normalized_source_sha256,
    verify_qualification,
)

AS_OF = "2026-09-13T10:50:00Z"
D = "a" * 64
E = "b" * 64
F = "c" * 64


def public_packet():
    return {
        "schema": "commons.fsu-itn-6769-4-source/v1",
        "opportunityId": "FSU-ITN-6769-4",
        "buyer": "Florida State University / RFxPremier",
        "solicitationId": "ITN 6769-4",
        "title": "Artificial Intelligence (AI) Systems and Services",
        "openAt": "2026-09-10T04:00:00Z",
        "closeAt": "2026-10-21T19:00:00Z",
        "deadlineSourceId": "fsu-public-portal",
        "sources": [
            {
                "id": "fsu-public-portal",
                "kind": "PUBLIC_PORTAL",
                "url": "https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=FSU",
                "capturedAt": "2026-09-13T10:31:56Z",
                "contentSha256": D,
                "controlling": False,
                "label": "FSU public event index",
            },
            {
                "id": "rfx-current",
                "kind": "PUBLIC_NOTICE",
                "url": "https://www.rfxpremier.org/current-solicitations/",
                "capturedAt": "2026-09-13T10:31:56Z",
                "contentSha256": E,
                "controlling": False,
                "label": "RFxPremier current solicitations",
            },
        ],
        "packetManifest": {
            "complete": False,
            "files": [],
            "addendaCheckedThrough": "2026-09-13T10:31:56Z",
            "authRequiredForFullPacket": True,
        },
        "serviceCategories": [],
        "mandatoryGates": [],
        "notes": "Public notice only. Full Jaggaer event redirects to authenticated login.",
    }


def complete_packet():
    p = public_packet()
    p["sources"].append(
        {
            "id": "itn-main",
            "kind": "CONTROLLING_ITN",
            "url": "https://app01.jaggaer.com/apps/Router/ViewSourcingEvent",
            "capturedAt": "2026-09-13T10:40:00Z",
            "contentSha256": F,
            "controlling": True,
            "label": "Controlling ITN",
        }
    )
    p["deadlineSourceId"] = "itn-main"
    p["packetManifest"] = {
        "complete": True,
        "files": [{"sourceId": "itn-main", "filename": "ITN-6769-4.pdf", "sha256": F}],
        "addendaCheckedThrough": "2026-09-13T10:40:00Z",
        "authRequiredForFullPacket": False,
    }
    p["serviceCategories"] = ["AI engineering services"]
    p["mandatoryGates"] = [
        {
            "id": "eligibility",
            "category": "eligibility",
            "requirement": "Respondent eligibility",
            "route": "BOTH",
            "state": "PROVEN",
            "sourceId": "itn-main",
            "evidenceSha256": D,
            "partnerEvidenceSha256": None,
        }
    ]
    return p


class QualificationTests(unittest.TestCase):
    def test_public_notice_fails_closed(self):
        out = compile_qualification(public_packet(), as_of=AS_OF)
        self.assertEqual(out["receipt"]["disposition"], "HOLD_RAW_PACKET_REQUIRED")
        self.assertIn("CONTROLLING_ITN_NOT_ACQUIRED", out["receipt"]["reasons"])
        self.assertFalse(any(out["receipt"]["authority"].values()))

    def test_public_notice_cannot_smuggle_gate(self):
        p = public_packet()
        p["mandatoryGates"] = [
            {
                "id": "fake",
                "category": "eligibility",
                "requirement": "fake",
                "route": "BOTH",
                "state": "PROVEN",
                "sourceId": "fsu-public-portal",
                "evidenceSha256": D,
                "partnerEvidenceSha256": None,
            }
        ]
        out = compile_qualification(p, as_of=AS_OF)
        self.assertEqual(out["receipt"]["disposition"], "HOLD_RAW_PACKET_REQUIRED")
        self.assertTrue(any(x.startswith("GATE_NOT_BOUND_TO_CONTROLLING_SOURCE") for x in out["receipt"]["reasons"]))

    def test_public_notice_cannot_be_marked_controlling(self):
        p = public_packet()
        p["sources"][0]["controlling"] = True
        with self.assertRaises(QualificationError):
            compile_qualification(p, as_of=AS_OF)

    def test_complete_requires_out_of_band_trust_root(self):
        out = compile_qualification(complete_packet(), as_of=AS_OF)
        self.assertEqual(out["receipt"]["disposition"], "HOLD_SOURCE_PACKET_TRUST_ROOT_REQUIRED")

    def test_complete_proven_can_prime_review_only_with_exact_trust_root(self):
        p = complete_packet()
        trusted = normalized_source_sha256(p, as_of=AS_OF)
        out = compile_qualification(p, as_of=AS_OF, expected_source_packet_sha256=trusted)
        self.assertEqual(out["receipt"]["disposition"], "PRIME_READY_FOR_OWNER_REVIEW")

    def test_wrong_trust_root_holds(self):
        p = complete_packet()
        out = compile_qualification(p, as_of=AS_OF, expected_source_packet_sha256="d" * 64)
        self.assertEqual(out["receipt"]["disposition"], "HOLD_SOURCE_PACKET_TRUST_ROOT_MISMATCH")

    def test_partner_cure_routes_to_team_review(self):
        p = complete_packet()
        p["mandatoryGates"][0]["state"] = "PARTNER_CURABLE"
        p["mandatoryGates"][0]["evidenceSha256"] = None
        p["mandatoryGates"][0]["partnerEvidenceSha256"] = E
        trusted = normalized_source_sha256(p, as_of=AS_OF)
        out = compile_qualification(p, as_of=AS_OF, expected_source_packet_sha256=trusted)
        self.assertEqual(out["receipt"]["disposition"], "TEAMING_READY_FOR_OWNER_REVIEW")

    def test_missing_gate_holds(self):
        p = complete_packet()
        p["mandatoryGates"][0]["state"] = "MISSING"
        p["mandatoryGates"][0]["evidenceSha256"] = None
        trusted = normalized_source_sha256(p, as_of=AS_OF)
        out = compile_qualification(p, as_of=AS_OF, expected_source_packet_sha256=trusted)
        self.assertEqual(out["receipt"]["disposition"], "HOLD_MANDATORY_EVIDENCE_MISSING")

    def test_hard_fail_no_bid(self):
        p = complete_packet()
        p["mandatoryGates"][0]["state"] = "FAIL"
        p["mandatoryGates"][0]["evidenceSha256"] = None
        trusted = normalized_source_sha256(p, as_of=AS_OF)
        out = compile_qualification(p, as_of=AS_OF, expected_source_packet_sha256=trusted)
        self.assertEqual(out["receipt"]["disposition"], "NO_BID_MANDATORY_GATE_FAILED")

    def test_closed_deadline_no_bid_requires_current_trusted_complete_packet(self):
        p = complete_packet()
        current = "2026-10-21T19:00:00Z"
        p["packetManifest"]["addendaCheckedThrough"] = "2026-10-21T18:59:00Z"
        trusted = normalized_source_sha256(p, as_of=current)
        out = compile_qualification(p, as_of=current, expected_source_packet_sha256=trusted)
        self.assertEqual(out["receipt"]["disposition"], "NO_BID_DEADLINE_CLOSED")

    def test_future_capture_rejected(self):
        p = public_packet()
        p["sources"][0]["capturedAt"] = "2026-09-14T00:00:00Z"
        with self.assertRaises(QualificationError):
            compile_qualification(p, as_of=AS_OF)

    def test_bool_not_int_alias(self):
        p = public_packet()
        p["packetManifest"]["complete"] = 1
        with self.assertRaises(QualificationError):
            compile_qualification(p, as_of=AS_OF)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(QualificationError):
            loads_strict('{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(QualificationError):
            loads_strict('{"a":NaN}')

    def test_unknown_field_rejected(self):
        p = public_packet()
        p["oops"] = True
        with self.assertRaises(QualificationError):
            compile_qualification(p, as_of=AS_OF)

    def test_lookalike_host_rejected(self):
        p = public_packet()
        p["sources"][0]["url"] = "https://evil.example/?next=https://bids.sciquest.com"
        with self.assertRaises(QualificationError):
            compile_qualification(p, as_of=AS_OF)

    def test_order_invariant_sources(self):
        p = public_packet()
        q = copy.deepcopy(p)
        q["sources"].reverse()
        self.assertEqual(compile_qualification(p, as_of=AS_OF), compile_qualification(q, as_of=AS_OF))

    def test_receipt_tamper_fails_verify(self):
        p = public_packet()
        out = compile_qualification(p, as_of=AS_OF)
        receipt = copy.deepcopy(out["receipt"])
        receipt["disposition"] = "PRIME_READY_FOR_OWNER_REVIEW"
        self.assertFalse(verify_qualification(p, receipt, as_of=AS_OF))
        self.assertTrue(verify_qualification(p, out["receipt"], as_of=AS_OF))

    def test_create_exclusive_publication(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "receipt.json")
            publish_new(path, b"{}")
            with self.assertRaises(FileExistsError):
                publish_new(path, b"{}")

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source = os.path.join(td, "source.json")
            link = os.path.join(td, "link.json")
            with open(source, "w", encoding="utf-8") as handle:
                json.dump(public_packet(), handle)
            os.symlink(source, link)
            with self.assertRaises(QualificationError):
                read_json_regular(link)


if __name__ == "__main__":
    unittest.main()
