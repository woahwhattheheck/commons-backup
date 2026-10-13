import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core

SHA = "a" * 40


def run_capture(run_id=1, *, attempt=1, repo="acme/widgets", head=SHA, status="completed", conclusion="success"):
    return {"schema": core.RUN_SCHEMA, "run": {"id": run_id, "run_attempt": attempt, "repository": repo, "head_sha": head, "status": status, "conclusion": conclusion}}


def step(number=1, *, name="test", status="completed", conclusion="success"):
    return {"number": number, "name": name, "status": status, "conclusion": conclusion}


def job(job_id=11, *, name="test", status="completed", conclusion="success", runner_id=55, steps=None):
    return {"id": job_id, "name": name, "status": status, "conclusion": conclusion, "runner_id": runner_id, "steps": list(steps or [])}


def jobs_capture(jobs, *, run_id=1, attempt=1, repo="acme/widgets", head=SHA):
    return {"schema": core.JOBS_SCHEMA, "run_id": run_id, "run_attempt": attempt, "repository": repo, "head_sha": head, "jobs": list(jobs)}


class ClassificationTests(unittest.TestCase):
    def classify(self, run=None, jobs=None):
        return core.classify_case(run or run_capture(), jobs if jobs is not None else jobs_capture([job(steps=[step()])]))

    def test_all_seven_states_and_safety_flags(self):
        green = self.classify()
        self.assertEqual(green["classification"], "EXECUTED_GREEN"); self.assertTrue(green["github_actions_green"])
        failed = self.classify(run_capture(conclusion="failure"), jobs_capture([job(conclusion="failure", steps=[step(conclusion="failure")])]))
        self.assertEqual(failed["classification"], "EXECUTED_NON_GREEN")
        interrupted = self.classify(run_capture(conclusion="cancelled"), jobs_capture([job(conclusion="cancelled", steps=[step()])]))
        self.assertEqual(interrupted["classification"], "EXECUTION_INTERRUPTED")
        unassigned = self.classify(run_capture(conclusion="failure"), jobs_capture([job(conclusion="failure", runner_id=0)]))
        self.assertEqual(unassigned["classification"], "NOT_EXECUTED_RUNNER_UNASSIGNED")
        assigned = self.classify(run_capture(conclusion="failure"), jobs_capture([job(conclusion="failure", runner_id=77)]))
        self.assertEqual(assigned["classification"], "NOT_EXECUTED_AFTER_ASSIGNMENT")
        pending = self.classify(run_capture(status="queued", conclusion=None), jobs_capture([job(status="queued", conclusion=None, runner_id=0)]))
        self.assertEqual(pending["classification"], "PENDING_EXECUTION")
        inconclusive = self.classify(jobs=jobs_capture([job(steps=[])]))
        self.assertEqual(inconclusive["classification"], "INCONCLUSIVE_TERMINAL")
        for row in (green, failed, interrupted, unassigned, assigned, pending, inconclusive):
            self.assertFalse(row["source_regression_proven"])
            self.assertEqual(row["github_actions_green"], row["classification"] == "EXECUTED_GREEN")

    def test_contradictions_fail_closed(self):
        cases = [
            (run_capture(), jobs_capture([job(steps=[step(conclusion="failure")])]), "JOB_SUCCESS_WITH_NON_GREEN_STEP:11"),
            (run_capture(), jobs_capture([job(conclusion="cancelled", steps=[step()])]), "RUN_SUCCESS_WITH_NON_GREEN_JOB:11"),
            (run_capture(conclusion="cancelled"), jobs_capture([job(status="queued", conclusion=None, runner_id=0)]), "TERMINAL_RUN_HAS_NONTERMINAL_JOB:11"),
            (run_capture(conclusion="failure"), jobs_capture([]), "TERMINAL_RUN_WITHOUT_JOBS"),
            (run_capture(conclusion="failure"), jobs_capture([job(conclusion="success", steps=[])]), "JOB_SUCCESS_WITHOUT_EXECUTED_STEP:11"),
        ]
        for run, jobs, reason in cases:
            with self.subTest(reason=reason):
                row = self.classify(run, jobs)
                self.assertEqual(row["classification"], "INCONCLUSIVE_TERMINAL")
                self.assertIn(reason, row["reasons"])

    def test_strict_schema_types_binding_and_uniqueness(self):
        with self.assertRaises(core.EvidenceError): self.classify(run_capture(True), jobs_capture([]))
        with self.assertRaises(core.EvidenceError): self.classify(jobs=jobs_capture([], head="b" * 40))
        bad = run_capture(); bad["run"]["extra"] = 1
        with self.assertRaises(core.EvidenceError): self.classify(bad, jobs_capture([]))
        with self.assertRaises(core.EvidenceError): self.classify(jobs=jobs_capture([job(4), job(4)]))
        with self.assertRaises(core.EvidenceError): self.classify(jobs=jobs_capture([job(4, steps=[step(1), step(1, name="again")])]))

    def test_strict_json_rejects_duplicate_and_nonfinite(self):
        with self.assertRaises(core.EvidenceError): core.loads_strict(b'{"a":1,"a":2}', label="x")
        with self.assertRaises(core.EvidenceError): core.loads_strict(b'{"a":NaN}', label="x")


class ReceiptTests(unittest.TestCase):
    def test_order_independent_burst_receipt_and_verify(self):
        a = (run_capture(2, repo="z/repo", conclusion="failure"), jobs_capture([job(conclusion="failure", runner_id=0)], run_id=2, repo="z/repo"))
        b = (run_capture(1, repo="a/repo", conclusion="failure"), jobs_capture([job(conclusion="failure", runner_id=0)], run_id=1, repo="a/repo"))
        first, second = core.compile_receipt([a, b]), core.compile_receipt([b, a])
        self.assertEqual(first, second)
        self.assertTrue(first["aggregate"]["descriptive_not_executed_burst"])
        self.assertFalse(first["aggregate"]["billing_cause_inferred"])
        self.assertTrue(core.verify_receipt(first, [a, b])["valid"])

    def test_duplicate_identity_rejected(self):
        case = (run_capture(), jobs_capture([job(steps=[step()])]))
        with self.assertRaises(core.EvidenceError): core.compile_receipt([case, case])

    def test_tamper_and_rehashed_tamper_both_fail(self):
        case = (run_capture(), jobs_capture([job(steps=[step()])]))
        original = core.compile_receipt([case])
        tampered = {**original, "runs": [dict(original["runs"][0])]}
        tampered["runs"][0]["classification"] = "EXECUTED_NON_GREEN"
        first = core.verify_receipt(tampered, [case])
        self.assertIn("SUPPLIED_RECEIPT_DIGEST_MISMATCH", first["reason_codes"])
        projection = dict(tampered); projection.pop("receipt_sha256")
        tampered["receipt_sha256"] = core.digest(projection)
        second = core.verify_receipt(tampered, [case])
        self.assertNotIn("SUPPLIED_RECEIPT_DIGEST_MISMATCH", second["reason_codes"])
        self.assertIn("RECEIPT_RECOMPUTE_MISMATCH", second["reason_codes"])


if __name__ == "__main__": unittest.main(verbosity=2)
