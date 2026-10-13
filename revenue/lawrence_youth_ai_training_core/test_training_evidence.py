import copy
import unittest

from training_evidence import (
    CONTRACT,
    EvidenceError,
    HOLD,
    READY,
    compile_participant_evidence,
    loads_strict,
    verify_receipt,
)

AS_OF = "2026-09-13T10:00:00Z"
H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64

PLAN = {
    "contract": CONTRACT,
    "program_id": "lawrence-ai-core",
    "program_version": "v1",
    "curriculum": [
        {
            "module_id": "ai-fundamentals",
            "title": "AI Fundamentals and Responsible Use",
            "topics": ["ai-systems", "responsible-ai"],
            "required_labs": ["lab-source-check"],
            "required_assessments": ["assess-fundamentals"],
            "min_assessment_score": 75,
        },
        {
            "module_id": "applied-genai",
            "title": "Applied Generative AI and Prompt Engineering",
            "topics": ["prompt-engineering", "genai"],
            "required_labs": ["lab-prompt-eval"],
            "required_assessments": ["assess-genai"],
            "min_assessment_score": 80,
        },
        {
            "module_id": "data-security",
            "title": "Data, Cybersecurity, and Workplace AI",
            "topics": ["data-analytics", "cybersecurity"],
            "required_labs": ["lab-data-safety"],
            "required_assessments": ["assess-data-security"],
            "min_assessment_score": 80,
        },
    ],
    "credential_tracks": [
        {
            "track_id": "ai900",
            "credential_name": "Microsoft Azure AI Fundamentals",
            "required_modules": ["ai-fundamentals", "applied-genai", "data-security"],
        }
    ],
    "employer_projects": [
        {
            "project_id": "employer-project-1",
            "title": "Employer-defined AI workflow proof",
            "required_modules": ["ai-fundamentals", "applied-genai", "data-security"],
            "acceptance_checks": ["problem-framing", "source-citation", "privacy-safety", "reproducible-result"],
        }
    ],
    "as_of": AS_OF,
}

EVIDENCE = {
    "contract": CONTRACT,
    "participant_token": "learner_demo_001",
    "program_id": "lawrence-ai-core",
    "program_version": "v1",
    "module_events": [
        {"event_id": "m1", "module_id": "ai-fundamentals", "completed_at": AS_OF},
        {"event_id": "m2", "module_id": "applied-genai", "completed_at": AS_OF},
        {"event_id": "m3", "module_id": "data-security", "completed_at": AS_OF},
    ],
    "assessment_events": [
        {"event_id": "a1", "assessment_id": "assess-fundamentals", "module_id": "ai-fundamentals", "score": 92, "recorded_at": AS_OF},
        {"event_id": "a2", "assessment_id": "assess-genai", "module_id": "applied-genai", "score": 89, "recorded_at": AS_OF},
        {"event_id": "a3", "assessment_id": "assess-data-security", "module_id": "data-security", "score": 91, "recorded_at": AS_OF},
    ],
    "lab_events": [
        {"event_id": "l1", "lab_id": "lab-source-check", "module_id": "ai-fundamentals", "status": "PASS", "artifact_sha256": H1, "recorded_at": AS_OF},
        {"event_id": "l2", "lab_id": "lab-prompt-eval", "module_id": "applied-genai", "status": "PASS", "artifact_sha256": H2, "recorded_at": AS_OF},
        {"event_id": "l3", "lab_id": "lab-data-safety", "module_id": "data-security", "status": "PASS", "artifact_sha256": H3, "recorded_at": AS_OF},
    ],
    "credential_events": [
        {"event_id": "c1", "track_id": "ai900", "status": "VERIFIED_EXTERNAL", "evidence_sha256": H1, "recorded_at": AS_OF},
    ],
    "employer_project_events": [
        {
            "event_id": "p1",
            "project_id": "employer-project-1",
            "status": "ACCEPTED",
            "acceptance_checks": ["problem-framing", "source-citation", "privacy-safety", "reproducible-result"],
            "artifact_sha256": H2,
            "recorded_at": AS_OF,
        }
    ],
}


class TrainingEvidenceTests(unittest.TestCase):
    def compile(self, plan=None, evidence=None, as_of=AS_OF):
        return compile_participant_evidence(
            copy.deepcopy(PLAN if plan is None else plan),
            copy.deepcopy(EVIDENCE if evidence is None else evidence),
            trusted_as_of=as_of,
        )

    def test_ready_fixture(self):
        receipt = self.compile()
        self.assertEqual(receipt["state"], READY)
        self.assertEqual(receipt["reasons"], [])
        self.assertTrue(verify_receipt(receipt))
        self.assertTrue(all(v is False for v in receipt["authority"].values()))

    def test_deterministic(self):
        self.assertEqual(self.compile(), self.compile())

    def test_missing_lab_holds(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["lab_events"] = evidence["lab_events"][:-1]
        receipt = self.compile(evidence=evidence)
        self.assertEqual(receipt["state"], HOLD)
        self.assertIn("INCOMPLETE_TRAINING_EVIDENCE", receipt["reasons"])

    def test_low_assessment_holds(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["assessment_events"][1]["score"] = 79
        receipt = self.compile(evidence=evidence)
        self.assertEqual(receipt["state"], HOLD)

    def test_missing_credential_holds(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["credential_events"] = []
        receipt = self.compile(evidence=evidence)
        self.assertEqual(receipt["state"], HOLD)
        self.assertIn("NO_VERIFIED_CREDENTIAL_TRACK", receipt["reasons"])

    def test_missing_employer_acceptance_holds(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["employer_project_events"] = []
        receipt = self.compile(evidence=evidence)
        self.assertEqual(receipt["state"], HOLD)
        self.assertIn("NO_ACCEPTED_EMPLOYER_PROJECT", receipt["reasons"])

    def test_plan_clock_is_not_caller_replayable(self):
        plan = copy.deepcopy(PLAN)
        plan["as_of"] = "2026-09-12T10:00:00Z"
        with self.assertRaises(EvidenceError):
            self.compile(plan=plan)

    def test_future_event_rejected(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["module_events"][0]["completed_at"] = "2026-09-14T10:00:00Z"
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_unknown_plan_field_rejected(self):
        plan = copy.deepcopy(PLAN)
        plan["payment_authorized"] = True
        with self.assertRaises(EvidenceError):
            self.compile(plan=plan)

    def test_unknown_evidence_field_rejected(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["eligible"] = True
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_unknown_event_field_rejected(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["assessment_events"][0]["grader_notes"] = "looks good"
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_duplicate_event_id_rejected_cross_type(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["lab_events"][0]["event_id"] = "m1"
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_assessment_module_binding(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["assessment_events"][0]["module_id"] = "applied-genai"
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_lab_module_binding(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["lab_events"][0]["module_id"] = "applied-genai"
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_conflicting_duplicate_module_completion(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["module_events"].append({
            "event_id": "m4",
            "module_id": "ai-fundamentals",
            "completed_at": "2026-09-12T10:00:00Z",
        })
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_bad_credential_status_rejected(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["credential_events"][0]["status"] = "SELF_REPORTED"
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_bad_project_check_set_rejected(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["employer_project_events"][0]["acceptance_checks"].pop()
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_receipt_tamper_fails(self):
        receipt = self.compile()
        receipt["state"] = HOLD
        self.assertFalse(verify_receipt(receipt))

    def test_receipt_extra_field_fails_closed(self):
        receipt = self.compile()
        receipt["revenue"] = 100000
        with self.assertRaises(EvidenceError):
            verify_receipt(receipt)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(EvidenceError):
            loads_strict('{"a":1,"a":2}')

    def test_nan_json_rejected(self):
        with self.assertRaises(EvidenceError):
            loads_strict('{"a":NaN}')

    def test_float_scores_rejected(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["assessment_events"][0]["score"] = 92.0
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_boolean_scores_rejected(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["assessment_events"][0]["score"] = True
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_participant_token_is_opaque(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["participant_token"] = "person@example.com"
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_hashes_are_strict_lowercase(self):
        evidence = copy.deepcopy(EVIDENCE)
        evidence["lab_events"][0]["artifact_sha256"] = "A" * 64
        with self.assertRaises(EvidenceError):
            self.compile(evidence=evidence)

    def test_module_ids_unique(self):
        plan = copy.deepcopy(PLAN)
        plan["curriculum"][1]["module_id"] = plan["curriculum"][0]["module_id"]
        with self.assertRaises(EvidenceError):
            self.compile(plan=plan)

    def test_lab_ids_globally_unique(self):
        plan = copy.deepcopy(PLAN)
        plan["curriculum"][1]["required_labs"] = ["lab-source-check"]
        with self.assertRaises(EvidenceError):
            self.compile(plan=plan)

    def test_track_must_reference_known_module(self):
        plan = copy.deepcopy(PLAN)
        plan["credential_tracks"][0]["required_modules"] = ["missing-module"]
        with self.assertRaises(EvidenceError):
            self.compile(plan=plan)

    def test_project_must_reference_known_module(self):
        plan = copy.deepcopy(PLAN)
        plan["employer_projects"][0]["required_modules"] = ["missing-module"]
        with self.assertRaises(EvidenceError):
            self.compile(plan=plan)


if __name__ == "__main__":
    unittest.main()
