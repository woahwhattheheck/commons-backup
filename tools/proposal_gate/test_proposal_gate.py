import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import proposal_gate as pg


class ProposalGateTests(unittest.TestCase):
    def test_missing_mandatory_evidence_blocks(self):
        reqs = [{
            "id": "FIN-1", "section": "Vendor", "type": "mandatory",
            "statement": "Provide financial evidence", "evidence": ["financials"],
            "response": "Attached.",
        }]
        result = pg.evaluate(reqs, [])
        self.assertEqual(result[0].disposition, "BLOCKED")
        self.assertFalse(pg.summarize(result)["submission_ready"])

    def test_owner_gate_blocks_even_with_evidence(self):
        reqs = [{
            "id": "SIG-1", "section": "Cover", "type": "mandatory",
            "statement": "Authorized signature", "evidence": ["signature"],
            "response": "Signed.", "owner_gate": True,
        }]
        evidence = [{"id": "signature", "status": "available"}]
        result = pg.evaluate(reqs, evidence)
        self.assertEqual(result[0].disposition, "BLOCKED")
        self.assertIn("SIG-1", pg.summarize(result)["owner_gates"])

    def test_placeholder_is_not_a_response(self):
        reqs = [{
            "id": "A-1", "section": "A", "type": "mandatory",
            "statement": "Describe architecture", "evidence": [],
            "response": "[TBD — insert architecture]",
        }]
        result = pg.evaluate(reqs, [])
        self.assertEqual(result[0].disposition, "BLOCKED")

    def test_scored_gap_is_at_risk_not_hard_block(self):
        reqs = [{
            "id": "REF-1", "section": "Vendor", "type": "scored",
            "statement": "References where available", "evidence": ["refs"],
            "response": "See references.",
        }]
        result = pg.evaluate(reqs, [])
        self.assertEqual(result[0].disposition, "AT_RISK")
        self.assertTrue(pg.summarize(result)["submission_ready"])

    def test_ready_payload_and_renderers(self):
        reqs = [{
            "id": "A-1", "section": "Architecture", "type": "mandatory",
            "statement": "Describe scalability", "evidence": ["arch"],
            "response": "Horizontal workers with bounded queues.",
        }]
        evidence = [{"id": "arch", "status": "available"}]
        result = pg.evaluate(reqs, evidence)
        summary = pg.summarize(result)
        self.assertTrue(summary["submission_ready"])
        self.assertTrue(summary["stage_ready"])
        self.assertEqual(summary["stage"], "submission")
        self.assertEqual(summary["readiness_percent"], 100.0)
        self.assertIn("**READY**", pg.render_markdown(reqs, result))
        self.assertIn("[TBD", pg.render_skeleton(reqs))
        self.assertIn("Horizontal workers", pg.render_draft(reqs))

    def test_duplicate_requirement_rejected(self):
        reqs = [
            {"id": "X", "statement": "one", "evidence": []},
            {"id": "X", "statement": "two", "evidence": []},
        ]
        with self.assertRaises(ValueError):
            pg.evaluate(reqs, [])

    def test_award_only_missing_is_deferred_for_submission(self):
        reqs = [{
            "id": "INS-1", "section": "Award", "type": "mandatory",
            "stage": "award", "statement": "Provide professional-liability certificate",
            "evidence": ["coi"], "response": "Certificate required before award execution.",
        }]
        result = pg.evaluate(reqs, [], stage="submission")
        self.assertEqual(result[0].disposition, "DEFERRED")
        self.assertFalse(result[0].controlling)
        summary = pg.summarize(result)
        self.assertTrue(summary["submission_ready"])
        self.assertTrue(summary["stage_ready"])
        self.assertEqual(summary["readiness_percent"], 100.0)
        self.assertEqual(summary["deferred_requirements"], ["INS-1"])
        self.assertIn("DEFERRED", pg.render_markdown(reqs, result))

    def test_award_only_missing_blocks_at_award(self):
        reqs = [{
            "id": "INS-1", "type": "mandatory", "stage": "award",
            "statement": "Provide professional-liability certificate",
            "evidence": ["coi"], "response": "Certificate required before award execution.",
        }]
        result = pg.evaluate(reqs, [], stage="award")
        self.assertEqual(result[0].disposition, "BLOCKED")
        summary = pg.summarize(result)
        self.assertFalse(summary["stage_ready"])
        self.assertTrue(summary["submission_ready"])
        self.assertEqual(summary["blocking_requirements"], ["INS-1"])

    def test_submission_requirement_controls_both_stages(self):
        reqs = [{
            "id": "SIG-1", "type": "mandatory", "statement": "Signed cover page",
            "evidence": ["signature"], "response": "Signed cover page attached.",
        }]
        for stage in pg.VALID_STAGES:
            with self.subTest(stage=stage):
                result = pg.evaluate(reqs, [], stage=stage)
                self.assertEqual(result[0].disposition, "BLOCKED")
                summary = pg.summarize(result)
                self.assertFalse(summary["submission_ready"])
                self.assertFalse(summary["stage_ready"])

    def test_award_owner_gate_does_not_block_submission_but_blocks_award(self):
        reqs = [{
            "id": "CONTRACT-1", "type": "mandatory", "stage": "award",
            "statement": "Authorized contract approval", "evidence": ["terms"],
            "response": "Terms reviewed.", "owner_gate": True,
        }]
        evidence = [{"id": "terms", "status": "available"}]
        submission = pg.summarize(pg.evaluate(reqs, evidence, stage="submission"))
        self.assertTrue(submission["submission_ready"])
        self.assertTrue(submission["stage_ready"])
        self.assertEqual(submission["owner_gates"], [])
        award = pg.summarize(pg.evaluate(reqs, evidence, stage="award"))
        self.assertTrue(award["submission_ready"])
        self.assertFalse(award["stage_ready"])
        self.assertEqual(award["owner_gates"], ["CONTRACT-1"])

    def test_stage_must_be_exact_supported_string(self):
        bad_requirement_stages = [True, 1, 1.0, None, "award ", "contract"]
        for bad in bad_requirement_stages:
            with self.subTest(requirement_stage=bad):
                reqs = [{
                    "id": "X", "statement": "x", "evidence": [],
                    "response": "x", "stage": bad,
                }]
                with self.assertRaises(ValueError):
                    pg.evaluate(reqs, [])
        for bad in [True, 1, 1.0, None, "submission ", "contract"]:
            with self.subTest(target_stage=bad):
                with self.assertRaises(ValueError):
                    pg.evaluate([], [], stage=bad)

    def test_no_stage_payload_preserves_submission_defaults(self):
        reqs = [{
            "id": "A-1", "type": "mandatory", "statement": "Answer",
            "evidence": [], "response": "done",
        }]
        result = pg.evaluate(reqs, [])
        self.assertEqual(result[0].requirement_stage, "submission")
        self.assertEqual(result[0].target_stage, "submission")
        self.assertTrue(result[0].controlling)
        summary = pg.summarize(result)
        self.assertEqual(summary["stage"], "submission")
        self.assertTrue(summary["submission_ready"])
        self.assertTrue(summary["stage_ready"])

    def test_mandatory_not_applicable_is_not_a_waiver(self):
        reqs = [{
            "id": "INS-1", "type": "mandatory",
            "statement": "Provide required insurance certificate",
            "evidence": ["coi"], "response": "Certificate supplied.",
        }]
        evidence = [{"id": "coi", "status": "not_applicable"}]
        result = pg.evaluate(reqs, evidence)
        self.assertEqual(result[0].disposition, "BLOCKED")
        self.assertEqual(result[0].evidence_status, "not_applicable")
        self.assertEqual(result[0].missing_evidence, ("coi",))
        self.assertIn("without waiver authority", " ".join(result[0].notes))
        summary = pg.summarize(result)
        self.assertFalse(summary["submission_ready"])
        self.assertFalse(summary["stage_ready"])

    def test_award_not_applicable_is_deferred_then_blocks(self):
        reqs = [{
            "id": "INS-1", "type": "mandatory", "stage": "award",
            "statement": "Provide required insurance certificate",
            "evidence": ["coi"], "response": "Certificate required before contracting.",
        }]
        evidence = [{"id": "coi", "status": "not_applicable"}]
        submission = pg.evaluate(reqs, evidence, stage="submission")
        self.assertEqual(submission[0].disposition, "DEFERRED")
        self.assertTrue(pg.summarize(submission)["stage_ready"])
        award = pg.evaluate(reqs, evidence, stage="award")
        self.assertEqual(award[0].disposition, "BLOCKED")
        self.assertFalse(pg.summarize(award)["stage_ready"])
        self.assertTrue(pg.summarize(award)["submission_ready"])

    def test_scored_not_applicable_is_at_risk(self):
        reqs = [{
            "id": "REF-1", "type": "scored", "statement": "Provide references",
            "evidence": ["refs"], "response": "References described.",
        }]
        result = pg.evaluate(reqs, [{"id": "refs", "status": "not_applicable"}])
        self.assertEqual(result[0].disposition, "AT_RISK")
        self.assertEqual(result[0].evidence_status, "not_applicable")
        self.assertTrue(pg.summarize(result)["stage_ready"])

    def test_empty_requirement_universe_fails_closed(self):
        for stage in pg.VALID_STAGES:
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(ValueError, "at least one requirement"):
                    pg.evaluate([], [], stage=stage)
        with self.assertRaisesRegex(ValueError, "empty requirement universe"):
            pg.summarize([])

    def test_cli_check_tracks_target_stage_and_report(self):
        reqs = {"requirements": [{
            "id": "INS-1", "type": "mandatory", "stage": "award",
            "statement": "COI before award", "evidence": ["coi"],
            "response": "Required before contracting.",
        }]}
        ev = {"evidence": []}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            req_path = root / "req.json"
            ev_path = root / "ev.json"
            report_path = root / "report.json"
            req_path.write_text(json.dumps(reqs), encoding="utf-8")
            ev_path.write_text(json.dumps(ev), encoding="utf-8")
            self.assertEqual(
                pg.main([str(req_path), str(ev_path), "--stage", "submission", "--check"]),
                0,
            )
            self.assertEqual(
                pg.main([
                    str(req_path), str(ev_path), "--stage", "award",
                    "--json-out", str(report_path), "--check",
                ]),
                2,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["stage"], "award")
            self.assertEqual(report["summary"]["stage"], "award")
            self.assertFalse(report["summary"]["stage_ready"])
            self.assertTrue(report["summary"]["submission_ready"])


if __name__ == "__main__":
    unittest.main()
