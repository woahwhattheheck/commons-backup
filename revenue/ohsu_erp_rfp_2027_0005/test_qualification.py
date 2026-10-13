from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path

from revenue.ohsu_erp_rfp_2027_0005 import qualification as q

ROOT = Path(__file__).resolve().parents[2]
PROFILE = json.loads((Path(__file__).with_name("profile.json")).read_text(encoding="utf-8"))
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def facts(**overrides):
    base = {
        "schema": q.SCHEMA_FACTS,
        "route": "TEAMING",
        "controlling_pack_sha256": None,
        "requirements": [],
        "prime_commitment": {"status": "UNCONFIRMED", "evidence_sha256": None},
        "intent_receipt": None,
        "owner_reviewed": False,
    }
    base.update(overrides)
    return base


def req(rid, mandatory=True, state="SATISFIED", evidence=SHA_B):
    return {
        "requirement_id": rid,
        "mandatory": mandatory,
        "state": state,
        "evidence_sha256": evidence if state == "SATISFIED" else None,
    }


class QualificationTests(unittest.TestCase):
    def test_default_public_notice_holds_for_controlling_pack(self):
        p = q._compile_at(PROFILE, facts(), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "HOLD_CONTROLLING_PACK")
        self.assertIn("QUALIFY_PAID_TEAMING_ROUTE", p["next_actions"])
        self.assertEqual(p["workshare"]["fixed_price_usd"], 12500)
        self.assertEqual(p["workshare"]["commercial_status"], "PROPOSED_NOT_ACCEPTED")
        self.assertEqual(p["workshare"]["delivery_window_status"], "TO_NEGOTIATE")
        self.assertNotIn("delivery_window_business_days", p["workshare"])
        self.assertTrue(all(value is False for value in p["authority"].values()))

    def test_notice_deadline_tamper_is_rejected(self):
        bad = deepcopy(PROFILE)
        bad["proposal_due_date"] = "2026-10-25"
        with self.assertRaisesRegex(q.ContractError, "reviewed public notice"):
            q._compile_at(bad, facts(), dt.date(2026, 9, 13))

    def test_notice_scope_tamper_is_rejected(self):
        bad = deepcopy(PROFILE)
        bad["public_scope"].append("invented mandatory migration requirement")
        with self.assertRaises(q.ContractError):
            q._compile_at(bad, facts(), dt.date(2026, 9, 13))

    def test_pack_without_requirement_registry_holds(self):
        p = q._compile_at(PROFILE, facts(controlling_pack_sha256=SHA_A), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "HOLD_REQUIREMENT_REGISTRY")

    def test_requirements_forbidden_without_pack(self):
        with self.assertRaisesRegex(q.ContractError, "before controlling pack"):
            q._compile_at(PROFILE, facts(requirements=[req("R1")]), dt.date(2026, 9, 13))

    def test_missing_mandatory_requirement_holds(self):
        p = q._compile_at(PROFILE, facts(
            controlling_pack_sha256=SHA_A,
            requirements=[req("R1"), req("R2", state="MISSING")],
            owner_reviewed=True,
        ), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "HOLD_MANDATORY_REQUIREMENTS")
        self.assertIn("MANDATORY_MISSING:R2", p["blockers"])

    def test_unknown_mandatory_requirement_holds(self):
        p = q._compile_at(PROFILE, facts(
            controlling_pack_sha256=SHA_A,
            requirements=[req("R1", state="UNKNOWN")],
            owner_reviewed=True,
        ), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "HOLD_MANDATORY_REQUIREMENTS")

    def test_optional_missing_does_not_block(self):
        p = q._compile_at(PROFILE, facts(
            controlling_pack_sha256=SHA_A,
            requirements=[req("M1"), req("O1", mandatory=False, state="MISSING")],
            owner_reviewed=True,
        ), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "TEAMING_CANDIDATE")

    def test_teaming_requires_confirmed_prime_commitment(self):
        p = q._compile_at(PROFILE, facts(
            controlling_pack_sha256=SHA_A,
            requirements=[req("M1")],
            owner_reviewed=True,
        ), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "TEAMING_CANDIDATE")
        self.assertIn("NO_CONFIRMED_PRIME_TEAMING_COMMITMENT", p["blockers"])

    def test_confirmed_teaming_reaches_owner_review_not_submission_authority(self):
        p = q._compile_at(PROFILE, facts(
            controlling_pack_sha256=SHA_A,
            requirements=[req("M1")],
            owner_reviewed=True,
            prime_commitment={"status": "CONFIRMED", "evidence_sha256": SHA_C},
        ), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "READY_FOR_OWNER_TEAMING_REVIEW")
        self.assertFalse(p["authority"]["proposal_submission_authorized"])
        self.assertFalse(p["authority"]["teaming_commitment_accepted"])

    def test_prime_route_reaches_owner_review_not_eligibility_claim(self):
        p = q._compile_at(PROFILE, facts(
            route="PRIME",
            controlling_pack_sha256=SHA_A,
            requirements=[req("M1")],
            owner_reviewed=True,
        ), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "READY_FOR_OWNER_PRIME_REVIEW")
        self.assertFalse(p["authority"]["prime_eligibility_verified_by_ohsu"])

    def test_route_unknown_holds_after_requirement_review(self):
        p = q._compile_at(PROFILE, facts(
            route="UNKNOWN",
            controlling_pack_sha256=SHA_A,
            requirements=[req("M1")],
            owner_reviewed=True,
        ), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "HOLD_ROUTE_UNKNOWN")

    def test_owner_review_required(self):
        p = q._compile_at(PROFILE, facts(
            route="PRIME",
            controlling_pack_sha256=SHA_A,
            requirements=[req("M1")],
        ), dt.date(2026, 9, 13))
        self.assertEqual(p["status"], "HOLD_OWNER_REVIEW")

    def test_intent_date_without_receipt_holds_for_unknown_time(self):
        p = q._compile_at(PROFILE, facts(), dt.date(2026, 9, 16))
        self.assertEqual(p["status"], "HOLD_INTENT_TIME_UNVERIFIED")

    def test_after_intent_date_without_receipt_holds(self):
        p = q._compile_at(PROFILE, facts(), dt.date(2026, 9, 17))
        self.assertEqual(p["status"], "HOLD_INTENT_DEADLINE")

    def test_late_intent_receipt_demotes_ready(self):
        p = q._compile_at(PROFILE, facts(
            route="PRIME",
            controlling_pack_sha256=SHA_A,
            requirements=[req("M1")],
            owner_reviewed=True,
            intent_receipt={"provider_event_sha256": SHA_C, "submitted_date": "2026-09-17"},
        ), dt.date(2026, 9, 18))
        self.assertEqual(p["status"], "HOLD_INTENT_CHRONOLOGY")
        self.assertIn("INTENT_RECEIPT_DATE_AFTER_PUBLIC_INTENT_DATE", p["blockers"])

    def test_proposal_date_holds_for_unknown_time(self):
        f = facts(intent_receipt={"provider_event_sha256": SHA_C, "submitted_date": "2026-09-15"})
        p = q._compile_at(PROFILE, f, dt.date(2026, 9, 25))
        self.assertEqual(p["status"], "HOLD_DEADLINE_TIME_UNVERIFIED")

    def test_after_proposal_date_closed(self):
        p = q._compile_at(PROFILE, facts(), dt.date(2026, 9, 26))
        self.assertEqual(p["status"], "CLOSED_DEADLINE")

    def test_duplicate_requirement_id_rejected(self):
        with self.assertRaisesRegex(q.ContractError, "duplicate requirement_id"):
            q._compile_at(PROFILE, facts(
                controlling_pack_sha256=SHA_A,
                requirements=[req("M1"), req("M1")],
            ), dt.date(2026, 9, 13))

    def test_bool_int_alias_rejected(self):
        bad = facts(owner_reviewed=1)
        with self.assertRaisesRegex(q.ContractError, "must be bool"):
            q._compile_at(PROFILE, bad, dt.date(2026, 9, 13))

    def test_nonlower_sha_rejected(self):
        bad = facts(controlling_pack_sha256="A" * 64)
        with self.assertRaisesRegex(q.ContractError, "lowercase sha256"):
            q._compile_at(PROFILE, bad, dt.date(2026, 9, 13))

    def test_satisfied_requirement_requires_evidence(self):
        bad_req = req("M1")
        bad_req["evidence_sha256"] = None
        with self.assertRaisesRegex(q.ContractError, "SATISFIED requires"):
            q._compile_at(PROFILE, facts(controlling_pack_sha256=SHA_A, requirements=[bad_req]), dt.date(2026, 9, 13))

    def test_packet_changes_when_evidence_changes(self):
        a = q._compile_at(PROFILE, facts(
            route="PRIME", controlling_pack_sha256=SHA_A, requirements=[req("M1", evidence=SHA_B)], owner_reviewed=True,
        ), dt.date(2026, 9, 13))
        b = q._compile_at(PROFILE, facts(
            route="PRIME", controlling_pack_sha256=SHA_A, requirements=[req("M1", evidence=SHA_C)], owner_reviewed=True,
        ), dt.date(2026, 9, 13))
        self.assertNotEqual(a["facts_sha256"], b["facts_sha256"])
        self.assertNotEqual(a["packet_sha256"], b["packet_sha256"])

    def test_requirement_order_is_canonical(self):
        f1 = facts(controlling_pack_sha256=SHA_A, requirements=[req("B"), req("A")], owner_reviewed=True)
        f2 = facts(controlling_pack_sha256=SHA_A, requirements=[req("A"), req("B")], owner_reviewed=True)
        p1 = q._compile_at(PROFILE, f1, dt.date(2026, 9, 13))
        p2 = q._compile_at(PROFILE, f2, dt.date(2026, 9, 13))
        self.assertEqual(p1, p2)

    def test_duplicate_json_key_rejected(self):
        raw = b'{"schema":"x","schema":"y"}'
        with self.assertRaisesRegex(q.ContractError, "duplicate JSON key"):
            q._parse_strict_json(raw, "fixture")

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(q.ContractError, "non-finite"):
            q._parse_strict_json(b'{"x":NaN}', "fixture")

    def test_cli_compile_stdout_only(self):
        envelope = {"schema": q.SCHEMA_INPUT, "notice": PROFILE, "facts": facts()}
        proc = subprocess.run(
            [sys.executable, "-m", "revenue.ohsu_erp_rfp_2027_0005.qualification", "compile"],
            input=json.dumps(envelope).encode(), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        packet = json.loads(proc.stdout)
        self.assertEqual(packet["status"], "HOLD_CONTROLLING_PACK")

    def test_cli_bad_duplicate_key_fails_controlled(self):
        proc = subprocess.run(
            [sys.executable, "-m", "revenue.ohsu_erp_rfp_2027_0005.qualification", "compile"],
            input=b'{"schema":"x","schema":"y"}', cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn(b"HOLD:", proc.stderr)
        self.assertNotIn(b"Traceback", proc.stderr)

    def test_current_compile_uses_process_clock_surface_only(self):
        self.assertEqual(q.compile_current.__code__.co_argcount, 2)
        self.assertNotIn("as_of", q.compile_current.__code__.co_varnames)

    def test_returned_packet_mutation_does_not_poison_later_compile(self):
        first = q._compile_at(PROFILE, facts(), dt.date(2026, 9, 13))
        first["workshare"]["fixed_price_usd"] = 0
        first["authority"]["proposal_submission_authorized"] = True
        second = q._compile_at(PROFILE, facts(), dt.date(2026, 9, 13))
        self.assertEqual(second["workshare"]["fixed_price_usd"], 12500)
        self.assertFalse(second["authority"]["proposal_submission_authorized"])


if __name__ == "__main__":
    unittest.main()
