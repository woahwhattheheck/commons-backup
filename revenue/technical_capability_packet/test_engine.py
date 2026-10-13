from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import unittest

from revenue.technical_capability_packet.engine import (
    ContractError,
    compile_packet,
    load_json_strict,
    render_markdown,
    verify_report,
)

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "synthetic_request.json"
NOW = datetime(2026, 9, 14, 1, 0, 0, tzinfo=timezone.utc)


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class EngineTests(unittest.TestCase):
    def test_fixture_ready_with_optional_unsupported_visible(self):
        report = compile_packet(fixture(), as_of=NOW)
        self.assertEqual(report["readiness"], "READY_FOR_OWNER_SEND_REVIEW")
        by_id = {row["requirement_id"]: row for row in report["requirements"]}
        self.assertEqual(by_id["production"]["status"], "UNSUPPORTED")
        self.assertEqual([row["asset_id"] for row in report["selected_proof"]], ["public-core", "public-demo"])
        self.assertEqual(report["paid_next_step"]["status"], "PROPOSED_NOT_ACCEPTED")
        self.assertEqual(
            report["authority"],
            {
                "outbound_authorized": False,
                "buyer_acceptance_claimed": False,
                "payment_claimed": False,
                "revenue_recognition_authorized": False,
                "proposal_status": "PROPOSED_NOT_ACCEPTED",
            },
        )

    def test_markdown_preserves_authority_ceiling_and_limitations(self):
        md = render_markdown(compile_packet(fixture(), as_of=NOW))
        self.assertIn("PROPOSED_NOT_ACCEPTED", md)
        self.assertIn("not buyer acceptance", md)
        self.assertIn("Limitation:", md)
        self.assertIn("Explicitly unsupported: buyer_production_deployment", md)

    def test_mandatory_unsupported_holds(self):
        p = fixture()
        p["request"]["requirements"][-1]["mandatory"] = True
        report = compile_packet(p, as_of=NOW)
        self.assertEqual(report["readiness"], "HOLD_FOR_EVIDENCE")

    def test_partial_mandatory_holds_and_missing_is_explicit(self):
        p = fixture()
        p["request"]["requirements"][0]["required_claims"].append("missing_capability")
        report = compile_packet(p, as_of=NOW)
        row = next(r for r in report["requirements"] if r["requirement_id"] == "automation")
        self.assertEqual(row["status"], "PARTIAL")
        self.assertEqual(row["missing_claims"], ["missing_capability"])
        self.assertEqual(report["readiness"], "HOLD_FOR_EVIDENCE")

    def test_stale_proof_is_not_usable(self):
        p = fixture()
        p["proof_assets"][0]["expires_at"] = "2026-09-14T00:59:59Z"
        report = compile_packet(p, as_of=NOW)
        row = next(r for r in report["requirements"] if r["requirement_id"] == "automation")
        self.assertEqual(row["status"], "NEEDS_EVIDENCE")
        self.assertIn("python_automation", row["stale_only_claims"])
        self.assertEqual(report["readiness"], "HOLD_FOR_EVIDENCE")

    def test_expired_request_holds_even_when_proof_is_current(self):
        p = fixture()
        p["request"]["expires_at"] = "2026-09-14T00:59:59Z"
        report = compile_packet(p, as_of=NOW)
        self.assertFalse(report["request_live"])
        self.assertEqual(report["readiness"], "HOLD_FOR_EVIDENCE")

    def test_naive_as_of_is_rejected(self):
        with self.assertRaises(ContractError):
            compile_packet(fixture(), as_of=datetime(2026, 9, 14, 1, 0, 0))

    def test_buyer_bound_asset_cannot_transplant(self):
        p = fixture()
        p["proof_assets"][0]["scope"] = "BUYER_BOUND"
        p["proof_assets"][0]["buyer_id"] = "different-buyer"
        p["proof_assets"][0]["opportunity_id"] = p["opportunity_id"]
        with self.assertRaises(ContractError):
            compile_packet(p, as_of=NOW)

    def test_public_asset_cannot_smuggle_buyer_binding(self):
        p = fixture()
        p["proof_assets"][0]["buyer_id"] = p["buyer_id"]
        with self.assertRaises(ContractError):
            compile_packet(p, as_of=NOW)

    def test_duplicate_uri_and_digest_aliases_are_rejected(self):
        p = fixture()
        p["proof_assets"][1]["uri"] = p["proof_assets"][0]["uri"]
        with self.assertRaises(ContractError):
            compile_packet(p, as_of=NOW)
        p = fixture()
        p["proof_assets"][1]["sha256"] = p["proof_assets"][0]["sha256"]
        with self.assertRaises(ContractError):
            compile_packet(p, as_of=NOW)

    def test_missing_limitations_rejected(self):
        p = fixture()
        p["proof_assets"][0]["limitations"] = []
        with self.assertRaises(ContractError):
            compile_packet(p, as_of=NOW)

    def test_proof_cannot_claim_known_unsupported_fact(self):
        p = fixture()
        p["proof_assets"][0]["claims"].append("buyer_production_deployment")
        with self.assertRaises(ContractError):
            compile_packet(p, as_of=NOW)

    def test_at_least_one_mandatory_requirement_is_required(self):
        p = fixture()
        for req in p["request"]["requirements"]:
            req["mandatory"] = False
        with self.assertRaises(ContractError):
            compile_packet(p, as_of=NOW)

    def test_asset_order_does_not_change_receipt(self):
        p = fixture()
        a = compile_packet(p, as_of=NOW)
        p["proof_assets"] = list(reversed(p["proof_assets"]))
        p["request"]["requirements"] = list(reversed(p["request"]["requirements"]))
        b = compile_packet(p, as_of=NOW)
        self.assertEqual(a, b)

    def test_request_digest_is_stable_when_only_offer_changes(self):
        a = compile_packet(fixture(), as_of=NOW)
        p = fixture()
        p["next_step"]["amount_minor"] += 1
        b = compile_packet(p, as_of=NOW)
        self.assertEqual(a["request_sha256"], b["request_sha256"])
        self.assertNotEqual(a["state_sha256"], b["state_sha256"])

    def test_minimal_cover_prefers_one_asset_and_lexical_tie(self):
        p = fixture()
        p["proof_assets"].append({
            "asset_id": "aaa-combined",
            "generation": 1,
            "kind": "PUBLIC_REPORT",
            "uri": "https://example.com/combined-a",
            "sha256": "3" * 64,
            "observed_at": "2026-09-13T19:00:00Z",
            "expires_at": "2030-09-13T19:00:00Z",
            "claims": ["python_automation", "deterministic_receipts", "buyer_readable_export"],
            "limitations": ["Synthetic combined proof for deterministic cover testing only."],
            "scope": "PUBLIC_REUSABLE",
            "buyer_id": None,
            "opportunity_id": None,
        })
        p["proof_assets"].append({
            "asset_id": "zzz-combined",
            "generation": 1,
            "kind": "PUBLIC_REPORT",
            "uri": "https://example.com/combined-z",
            "sha256": "4" * 64,
            "observed_at": "2026-09-13T19:00:00Z",
            "expires_at": "2030-09-13T19:00:00Z",
            "claims": ["python_automation", "deterministic_receipts", "buyer_readable_export"],
            "limitations": ["Synthetic combined proof for deterministic cover testing only."],
            "scope": "PUBLIC_REUSABLE",
            "buyer_id": None,
            "opportunity_id": None,
        })
        report = compile_packet(p, as_of=NOW)
        self.assertEqual([x["asset_id"] for x in report["selected_proof"]], ["aaa-combined"])

    def test_report_tamper_fails_verification(self):
        p = fixture()
        report = compile_packet(p, as_of=NOW)
        tampered = deepcopy(report)
        tampered["paid_next_step"]["amount_minor"] += 1
        verification = verify_report(p, tampered, current_as_of=NOW)
        self.assertEqual(verification["verdict"], "STALE_OR_DRIFTED")
        self.assertFalse(verification["historical_receipt_valid"])

    def test_request_replay_with_new_generation_fails_exact_history(self):
        p = fixture()
        report = compile_packet(p, as_of=NOW)
        changed = fixture()
        changed["request"]["generation"] = 2
        verification = verify_report(changed, report, current_as_of=NOW)
        self.assertEqual(verification["verdict"], "STALE_OR_DRIFTED")
        self.assertFalse(verification["historical_exact"])

    def test_exact_time_report_verifies_as_current(self):
        p = fixture()
        report = compile_packet(p, as_of=NOW)
        verification = verify_report(p, report, current_as_of=NOW)
        self.assertEqual(verification["verdict"], "CURRENT_VERIFIED")
        self.assertTrue(verification["historical_receipt_valid"])
        self.assertTrue(verification["historical_exact"])
        self.assertTrue(verification["current_same_state"])

    def test_future_dated_report_never_verifies_as_current(self):
        p = fixture()
        future = datetime(2026, 9, 14, 1, 0, 1, tzinfo=timezone.utc)
        report = compile_packet(p, as_of=future)
        current = compile_packet(p, as_of=NOW)
        self.assertEqual(report["state_sha256"], current["state_sha256"])
        verification = verify_report(p, report, current_as_of=NOW)
        self.assertTrue(verification["historical_receipt_valid"])
        self.assertTrue(verification["historical_exact"])
        self.assertTrue(verification["current_same_state"])
        self.assertEqual(verification["verdict"], "STALE_OR_DRIFTED")

    def test_verification_rechecks_currentness(self):
        p = fixture()
        p["request"]["expires_at"] = "2026-09-14T01:00:01Z"
        report = compile_packet(p, as_of=NOW)
        later = datetime(2026, 9, 14, 1, 0, 2, tzinfo=timezone.utc)
        verification = verify_report(p, report, current_as_of=later)
        self.assertEqual(verification["verdict"], "STALE_OR_DRIFTED")
        self.assertFalse(verification["current_request_live"])

    def test_duplicate_json_keys_and_nonfinite_numbers_rejected(self):
        with self.assertRaises(ContractError):
            load_json_strict(b'{"a":1,"a":2}')
        with self.assertRaises(ContractError):
            load_json_strict(b'{"a":NaN}')


if __name__ == "__main__":
    unittest.main()
