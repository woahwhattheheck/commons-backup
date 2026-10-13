import json
import tempfile
import unittest
from pathlib import Path

import assess_security_events as mod

ROOT = Path(__file__).parent
FIXTURE = ROOT / "fixtures" / "synthetic_events.json"


class SecurityEventAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = mod.load_records(FIXTURE)
        cls.by_id = {r["event_id"]: mod.assess(r) for r in cls.records}

    def test_monitoring_is_not_security_review(self):
        item = self.by_id["ESS-MON-001"]
        self.assertEqual(item.primary_status, "MONITORING_SIGNAL_NOT_SECURITY_REVIEW")
        self.assertEqual(item.review_state, "MONITORING_PATH")

    def test_complete_review_to_action_chain(self):
        item = self.by_id["IAM-SEC-002"]
        self.assertEqual(item.review_state, "REVIEW_EVIDENCED")
        self.assertEqual(item.escalation_state, "ESCALATION_EVIDENCED")
        self.assertEqual(item.action_state, "ACTION_EVIDENCED")
        self.assertEqual(item.primary_status, "REVIEW_TO_ACTION_EVIDENCED")

    def test_collection_without_review_stays_missing_evidence(self):
        item = self.by_id["ESS-SEC-003"]
        self.assertEqual(item.primary_status, "SECURITY_REVIEW_EVIDENCE_MISSING")
        self.assertIn("review owner missing", item.evidence_gaps)

    def test_unknown_relevance_is_not_fabricated_finding(self):
        item = self.by_id["RIS-UNK-004"]
        self.assertEqual(item.primary_status, "UNKNOWN_SECURITY_RELEVANCE")
        self.assertIn("security relevance is not established", item.evidence_gaps)

    def test_open_action_is_not_closed(self):
        item = self.by_id["IAM-SEC-005"]
        self.assertEqual(item.action_state, "ACTION_OPEN")
        self.assertEqual(item.primary_status, "ACTION_OPEN")

    def test_summary_is_counts_not_score(self):
        values = list(self.by_id.values())
        s = mod.summary(values)
        self.assertEqual(s["event_count"], 5)
        self.assertEqual(s["security_relevant_count"], 3)
        self.assertEqual(s["monitoring_only_count"], 1)
        self.assertEqual(s["unknown_relevance_count"], 1)
        self.assertIn("not maturity scores", s["interpretation"])

    def test_duplicate_event_ids_fail_closed(self):
        payload = json.loads(FIXTURE.read_text())
        payload["events"].append(dict(payload["events"][0]))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "dup.json"
            p.write_text(json.dumps(payload))
            with self.assertRaisesRegex(mod.EvidenceError, "duplicate event_id"):
                mod.load_records(p)

    def test_credential_like_key_is_rejected(self):
        record = dict(self.records[0])
        record["retained_context"] = dict(record["retained_context"])
        record["retained_context"]["api_key"] = "fictional-but-forbidden"
        with self.assertRaisesRegex(mod.EvidenceError, "out of scope"):
            mod.validate_record(record)

    def test_inconsistent_timeline_fails_closed(self):
        record = json.loads(json.dumps(self.records[1]))
        record["reviewed_at"] = "2026-09-15T14:00:00Z"
        with self.assertRaisesRegex(mod.EvidenceError, "timeline is inconsistent"):
            mod.validate_record(record)


if __name__ == "__main__":
    unittest.main()
