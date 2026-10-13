import copy
import unittest

import poc_acceptance as a


def fixture():
    return {
        "records": [
            {"record_id": "open-1", "version": "v1", "handling": "OPEN_FOR_SYNTHETIC_POC", "text": "The archive opened its reading room in 1970."},
            {"record_id": "review-1", "version": "v3", "handling": "REVIEW_REQUIRED", "text": "Synthetic donor note requiring human review."},
        ],
        "cases": [
            {"case_id": "answer", "expected_disposition": "ANSWER", "allowed_record_ids": ["open-1"], "required_citation_ids": ["open-1"]},
            {"case_id": "unknown", "expected_disposition": "ABSTAIN", "allowed_record_ids": ["open-1"], "required_citation_ids": []},
            {"case_id": "review", "expected_disposition": "REVIEW", "allowed_record_ids": ["review-1"], "required_citation_ids": []},
            {"case_id": "answer-replay", "expected_disposition": "ANSWER", "allowed_record_ids": ["open-1"], "required_citation_ids": ["open-1"], "replay_of": "answer"},
        ],
    }


def base_result(fx, cid, disposition, *, citations=None, retrieved=None, review=False, answer=""):
    snapshot = a.corpus_snapshot(fx["records"])
    return {
        "case_id": cid,
        "disposition": disposition,
        "answer": answer,
        "citations": [] if citations is None else citations,
        "retrieved_record_ids": [] if retrieved is None else retrieved,
        "corpus_snapshot_sha256": snapshot,
        "model_version": "synthetic-model-1",
        "prompt_version": "prompt-1",
        "policy_version": "policy-1",
        "human_review_required": review,
    }


def passing_results(fx):
    cite = a.citation_for(fx["records"][0])
    answer = base_result(fx, "answer", "ANSWER", citations=[cite], retrieved=["open-1"], answer="1970")
    unknown = base_result(fx, "unknown", "ABSTAIN", retrieved=["open-1"])
    review = base_result(fx, "review", "REVIEW", retrieved=["review-1"], review=True)
    replay = copy.deepcopy(answer); replay["case_id"] = "answer-replay"
    return [answer, unknown, review, replay]


class AcceptanceTests(unittest.TestCase):
    def assertPass(self, fx, results):
        receipt = a.evaluate_fixture(fx, results)
        self.assertEqual("PASS", receipt["status"], receipt)

    def assertFail(self, fx, results):
        self.assertEqual("FAIL", a.evaluate_fixture(fx, results)["status"])

    def test_passing_fixture(self):
        fx = fixture(); self.assertPass(fx, passing_results(fx))

    def test_missing_result_fails(self):
        fx = fixture(); self.assertFail(fx, passing_results(fx)[:-1])

    def test_extra_result_fails(self):
        fx = fixture(); rows = passing_results(fx); rows.append(base_result(fx, "extra", "ABSTAIN")); self.assertFail(fx, rows)

    def test_duplicate_result_fails(self):
        fx = fixture(); rows = passing_results(fx); rows.append(copy.deepcopy(rows[0])); self.assertFail(fx, rows)

    def test_duplicate_case_fails(self):
        fx = fixture(); fx["cases"].append(copy.deepcopy(fx["cases"][0])); self.assertFail(fx, passing_results(fx))

    def test_wrong_disposition_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["disposition"] = "ABSTAIN"; rows[0]["citations"] = []; self.assertFail(fx, rows)

    def test_unknown_disposition_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["disposition"] = "MAYBE"; self.assertFail(fx, rows)

    def test_corpus_snapshot_drift_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["corpus_snapshot_sha256"] = "0" * 64; self.assertFail(fx, rows)

    def test_missing_model_version_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["model_version"] = ""; self.assertFail(fx, rows)

    def test_missing_prompt_version_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["prompt_version"] = ""; self.assertFail(fx, rows)

    def test_missing_policy_version_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["policy_version"] = ""; self.assertFail(fx, rows)

    def test_answer_requires_citation(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["citations"] = []; self.assertFail(fx, rows)

    def test_wrong_citation_version_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["citations"][0]["version"] = "v2"; self.assertFail(fx, rows)

    def test_wrong_citation_hash_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["citations"][0]["text_sha256"] = "f" * 64; self.assertFail(fx, rows)

    def test_citation_outside_allowed_set_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["citations"] = [a.citation_for(fx["records"][1])]; self.assertFail(fx, rows)

    def test_retrieval_escape_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["retrieved_record_ids"].append("review-1"); self.assertFail(fx, rows)

    def test_duplicate_retrieval_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["retrieved_record_ids"] = ["open-1", "open-1"]; self.assertFail(fx, rows)

    def test_abstain_cannot_carry_answer_citations(self):
        fx = fixture(); rows = passing_results(fx); rows[1]["citations"] = [a.citation_for(fx["records"][0])]; self.assertFail(fx, rows)

    def test_review_required_source_cannot_answer(self):
        fx = fixture(); rows = passing_results(fx); rows[2]["disposition"] = "ANSWER"; rows[2]["human_review_required"] = False; rows[2]["citations"] = [a.citation_for(fx["records"][1])]; self.assertFail(fx, rows)

    def test_review_requires_boolean_true(self):
        fx = fixture(); rows = passing_results(fx); rows[2]["human_review_required"] = False; self.assertFail(fx, rows)

    def test_review_must_not_emit_final_answer(self):
        fx = fixture(); rows = passing_results(fx); rows[2]["answer"] = "secret"; self.assertFail(fx, rows)

    def test_non_review_cannot_claim_pending_review(self):
        fx = fixture(); rows = passing_results(fx); rows[0]["human_review_required"] = True; self.assertFail(fx, rows)

    def test_replay_route_drift_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[3]["retrieved_record_ids"] = []; self.assertFail(fx, rows)

    def test_replay_policy_drift_fails(self):
        fx = fixture(); rows = passing_results(fx); rows[3]["policy_version"] = "policy-2"; self.assertFail(fx, rows)

    def test_duplicate_record_fails(self):
        fx = fixture(); fx["records"].append(copy.deepcopy(fx["records"][0])); self.assertFail(fx, passing_results(fixture()))

    def test_invalid_handling_state_fails(self):
        fx = fixture(); fx["records"][0]["handling"] = "PUBLIC"; self.assertFail(fx, passing_results(fixture()))


if __name__ == "__main__":
    unittest.main()
