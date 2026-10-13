import copy
import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cpca_workshare", HERE / "workshare.py")
m = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(m)


def ev(state="UNKNOWN", ref="", sha=""):
    return {"state": state, "source_ref": ref, "sha256": sha}


def bound(name):
    return ev("SOURCE_BOUND", f"source:{name}", "a" * 64)


def base():
    return {
        "schema": m.SCHEMA,
        "opportunity_id": m.OPPORTUNITY_ID,
        "candidate_partner": {
            "name": "Example Healthcare Prime",
            "applicant_role": "PRIME",
            "relationship_state": "AWAITING_REPLY",
            "relationship_evidence": ev(),
        },
        "service_types": ["technical_assistance"],
        "ai_topics": ["AI Governance", "AI Implementation"],
        "tjlabs_scope": [
            "ai_governance_risk_control_matrix",
            "ai_implementation_assurance",
            "deterministic_evaluation_test_evidence",
        ],
        "partner_gate_evidence": {k: ev() for k in m.PARTNER_GATES},
        "tjlabs_evidence": {k: ev() for k in m.TJL_EVIDENCE},
    }


class Tests(unittest.TestCase):
    def test_awaiting_reply_is_draft_only(self):
        r = m.compile_packet(base())
        self.assertEqual(r["status"], "DRAFT_ONLY")
        self.assertFalse(r["authority_ceiling"]["external_submission_authorized"])

    def test_positive_interest_is_discussion_only(self):
        p = base()
        p["candidate_partner"]["relationship_state"] = "POSITIVE_INTEREST"
        r = m.compile_packet(p)
        self.assertEqual(r["status"], "PARTNER_DISCUSSION_READY")
        self.assertIn("POSITIVE_INTEREST_NOT_WRITTEN_TEAMING_AUTHORITY", r["reasons"])

    def test_written_authority_requires_relationship_evidence(self):
        p = base()
        p["candidate_partner"]["relationship_state"] = "WRITTEN_TEAMING_AUTHORITY"
        with self.assertRaises(m.WorkshareError):
            m.compile_packet(p)

    def test_written_authority_with_missing_gates_holds(self):
        p = base()
        p["candidate_partner"]["relationship_state"] = "WRITTEN_TEAMING_AUTHORITY"
        p["candidate_partner"]["relationship_evidence"] = bound("relationship")
        self.assertEqual(m.compile_packet(p)["status"], "HOLD_EVIDENCE")

    def test_all_bound_is_internal_review_only(self):
        p = base()
        p["candidate_partner"]["relationship_state"] = "WRITTEN_TEAMING_AUTHORITY"
        p["candidate_partner"]["relationship_evidence"] = bound("relationship")
        p["partner_gate_evidence"] = {k: bound(k) for k in m.PARTNER_GATES}
        p["tjlabs_evidence"] = {k: bound(k) for k in m.TJL_EVIDENCE}
        r = m.compile_packet(p)
        self.assertEqual(r["status"], "INTERNAL_TEAMING_REVIEW_READY")
        self.assertEqual(r["reasons"], [])
        self.assertTrue(all(v is False for v in r["authority_ceiling"].values()))

    def test_unknown_field_rejected(self):
        p = base()
        p["mint_partner"] = True
        with self.assertRaises(m.WorkshareError):
            m.compile_packet(p)

    def test_duplicate_scope_rejected(self):
        p = base()
        p["tjlabs_scope"].append(p["tjlabs_scope"][0])
        with self.assertRaises(m.WorkshareError):
            m.compile_packet(p)

    def test_scope_escalation_rejected(self):
        p = base()
        p["tjlabs_scope"] = ["three_client_references"]
        with self.assertRaises(m.WorkshareError):
            m.compile_packet(p)

    def test_bad_digest_rejected(self):
        p = base()
        p["partner_gate_evidence"]["three_client_references"] = ev(
            "SOURCE_BOUND", "source:x", "not-a-digest"
        )
        with self.assertRaises(m.WorkshareError):
            m.compile_packet(p)

    def test_order_invariant(self):
        p = base()
        p["service_types"] = ["group_training", "technical_assistance"]
        p["ai_topics"] = ["AI Implementation", "AI Governance"]
        p["tjlabs_scope"] = list(reversed(p["tjlabs_scope"]))
        a = m.compile_packet(p)
        q = copy.deepcopy(p)
        q["service_types"].reverse()
        q["ai_topics"].reverse()
        q["tjlabs_scope"].reverse()
        self.assertEqual(a, m.compile_packet(q))

    def test_verify_detects_tamper(self):
        p = base()
        r = m.compile_packet(p)
        self.assertTrue(m.verify(p, r))
        r2 = copy.deepcopy(r)
        r2["status"] = "INTERNAL_TEAMING_REVIEW_READY"
        self.assertFalse(m.verify(p, r2))

    def test_markdown_contains_hard_boundary(self):
        md = m.render_markdown(m.compile_packet(base()))
        self.assertIn("does **not** make the candidate a partner", md)
        self.assertIn("SmartSheet submission", md)


if __name__ == "__main__":
    unittest.main()
