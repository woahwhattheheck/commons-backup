import copy
import unittest

from acceptance import evaluate_fixture


def case(cid="c1", **kw):
    base = {
        "case_id": cid,
        "source_state": "FRESH",
        "risk": "NORMAL",
        "gold_route": "311-general",
        "approved_sources": [{"source_id":"src-1","version":"v7"}],
        "timeout_after_commit": False,
    }
    base.update(kw); return base


def result(cid="c1", **kw):
    base = {
        "case_id": cid,
        "disposition": "ANSWER",
        "route": "311-general",
        "citations": [{"source_id":"src-1","version":"v7"}],
        "canonical_case_id": cid,
        "effect_status": "NONE",
        "logical_effects": 0,
        "model_version": "model-1",
        "rule_version": "rules-1",
    }
    base.update(kw); return base


class AcceptanceTests(unittest.TestCase):
    def assertPass(self, cases, results):
        receipt = evaluate_fixture(cases, results)
        self.assertEqual("PASS", receipt["status"], receipt)

    def assertFail(self, cases, results):
        self.assertEqual("FAIL", evaluate_fixture(cases, results)["status"])

    def test_fresh_grounded_answer_passes(self):
        self.assertPass([case()], [result()])

    def test_missing_result_fails(self):
        self.assertFail([case()], [])

    def test_extra_result_fails(self):
        self.assertFail([], [result()])

    def test_duplicate_case_id_fails(self):
        self.assertFail([case(), case()], [result()])

    def test_duplicate_result_id_fails(self):
        self.assertFail([case()], [result(), result()])

    def test_route_mismatch_fails(self):
        self.assertFail([case()], [result(route="wrong")])

    def test_missing_model_version_fails(self):
        self.assertFail([case()], [result(model_version="")])

    def test_missing_rule_version_fails(self):
        self.assertFail([case()], [result(rule_version="")])

    def test_missing_canonical_id_fails(self):
        self.assertFail([case()], [result(canonical_case_id="")])

    def test_missing_citations_fails_answer(self):
        self.assertFail([case()], [result(citations=[])])

    def test_wrong_source_id_fails(self):
        self.assertFail([case()], [result(citations=[{"source_id":"src-X","version":"v7"}])])

    def test_wrong_source_version_fails(self):
        self.assertFail([case()], [result(citations=[{"source_id":"src-1","version":"v8"}])])

    def test_malformed_citation_fails(self):
        self.assertFail([case()], [result(citations=[{"source_id":"src-1"}])])

    def test_missing_approved_sources_fails_without_crash(self):
        self.assertFail([case(approved_sources=None)], [result()])

    def test_malformed_approved_source_fails_without_crash(self):
        self.assertFail([case(approved_sources=[{"source_id":"src-1"}])], [result()])

    def test_conflict_cannot_answer(self):
        self.assertFail([case(source_state="CONFLICT")], [result()])

    def test_stale_cannot_answer(self):
        self.assertFail([case(source_state="STALE")], [result()])

    def test_missing_source_cannot_answer(self):
        self.assertFail([case(source_state="MISSING")], [result()])

    def test_high_risk_cannot_answer(self):
        self.assertFail([case(risk="HIGH")], [result()])

    def test_emergency_cannot_answer(self):
        self.assertFail([case(risk="EMERGENCY")], [result()])

    def test_legal_cannot_answer(self):
        self.assertFail([case(risk="LEGAL")], [result()])

    def test_eligibility_cannot_answer(self):
        self.assertFail([case(risk="ELIGIBILITY")], [result()])

    def test_enforcement_cannot_answer(self):
        self.assertFail([case(risk="ENFORCEMENT")], [result()])

    def test_blocked_case_can_hold_without_answer_citations(self):
        self.assertPass([case(source_state="STALE")], [result(disposition="HOLD", citations=[])])

    def test_blocked_case_can_escalate(self):
        self.assertPass([case(risk="EMERGENCY", gold_route="911")], [result(disposition="ESCALATE", route="911", citations=[])])

    def test_hold_with_answer_citation_fails(self):
        self.assertFail([case(source_state="STALE")], [result(disposition="HOLD")])

    def test_timeout_unknown_effect_fails(self):
        self.assertFail([case(timeout_after_commit=True)], [result(effect_status="UNKNOWN")])

    def test_timeout_reconciled_applied_passes(self):
        self.assertPass([case(timeout_after_commit=True)], [result(effect_status="APPLIED", logical_effects=1)])

    def test_timeout_reconciled_not_applied_passes(self):
        self.assertPass([case(timeout_after_commit=True)], [result(effect_status="NOT_APPLIED")])

    def test_negative_effect_count_fails(self):
        self.assertFail([case()], [result(logical_effects=-1)])

    def test_boolean_effect_count_fails(self):
        self.assertFail([case()], [result(logical_effects=True)])

    def test_duplicate_group_one_effect_passes(self):
        cases = [case("a", duplicate_group="g"), case("b", duplicate_group="g")]
        results = [result("a", canonical_case_id="a", logical_effects=1), result("b", canonical_case_id="a", logical_effects=0)]
        self.assertPass(cases, results)

    def test_duplicate_group_two_effects_fails(self):
        cases = [case("a", duplicate_group="g"), case("b", duplicate_group="g")]
        results = [result("a", canonical_case_id="a", logical_effects=1), result("b", canonical_case_id="a", logical_effects=1)]
        self.assertFail(cases, results)

    def test_duplicate_group_disagreeing_canonical_fails(self):
        cases = [case("a", duplicate_group="g"), case("b", duplicate_group="g")]
        results = [result("a", canonical_case_id="a"), result("b", canonical_case_id="b")]
        self.assertFail(cases, results)

    def test_replay_same_receipt_passes(self):
        cases = [case("a"), case("b", replay_of="a")]
        r1 = result("a", canonical_case_id="a")
        r2 = result("b", canonical_case_id="a")
        self.assertPass(cases, [r1, r2])

    def test_replay_changed_route_fails(self):
        cases = [case("a"), case("b", replay_of="a", gold_route="different")]
        r1 = result("a", canonical_case_id="a")
        r2 = result("b", canonical_case_id="a", route="different")
        self.assertFail(cases, [r1, r2])

    def test_replay_changed_effect_count_fails(self):
        cases = [case("a"), case("b", replay_of="a")]
        r1 = result("a", canonical_case_id="a", logical_effects=0)
        r2 = result("b", canonical_case_id="a", logical_effects=1)
        self.assertFail(cases, [r1, r2])

    def test_invalid_disposition_fails(self):
        self.assertFail([case()], [result(disposition="MAYBE")])


if __name__ == "__main__":
    unittest.main()
