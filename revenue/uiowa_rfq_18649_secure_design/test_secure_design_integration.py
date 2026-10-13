"""Executed JSON round-trip, flow-scope and unknown-preservation regressions.

ZZ-MERIDIAN-H6K9 / GPT-6 Astra Pro. Uses the existing assessment engine only.
The original CINDER suite is retained unchanged in test_secure_design.py.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import secure_design as s

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "secure_design_records.json"


def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def result(records):
    return s.assess(*s.load_records(records))


def link(report, decision="DD-SYN-01", requirement="SEC-REQ-SYN-01"):
    return next(row for row in report["links"]
                if row["decision_id"] == decision and row["requirement_id"] == requirement)


def cli(*args):
    return subprocess.run([sys.executable, str(HERE / "secure_design.py"), *map(str, args)],
                          capture_output=True, text=True, timeout=15)


class RoundTripTests(unittest.TestCase):
    def test_complete_assessment_round_trip_preserves_every_state_and_record(self):
        before = result(payload())
        after = result(json.loads(json.dumps(before)))
        self.assertEqual(before, after)
        self.assertEqual(before["counts"]["by_state"], {
            s.OBSERVED_PRACTICE: 2, s.TRACED_STALE: 1,
            s.DOCUMENTED_INTENT: 2, s.UNKNOWN: 1})

    def test_global_intent_keeps_absent_ids_absent(self):
        evidence = s.Evidence({"evidence_id": "GLOBAL", "kind": "written_standard",
                               "statement": "Fictional general design policy."}, index=0)
        restored = s.Evidence(json.loads(json.dumps(evidence.to_dict())), index=0)
        self.assertEqual(restored.to_dict(), evidence.to_dict())
        self.assertEqual(restored.decision_id, "")
        self.assertEqual(restored.requirement_id, "")

    def test_unattributed_practice_keeps_its_category(self):
        p = payload()
        r = result(p)
        restored = result(json.loads(json.dumps(r)))
        self.assertEqual(link(restored, "DD-SYN-03", "SEC-REQ-SYN-03")
                         ["evidence_naming_requirement_but_no_decision"][0]["evidence_id"],
                         "EV-SD-SYN-07")
        self.assertEqual(link(restored, "DD-SYN-03", "SEC-REQ-SYN-03")["state"],
                         s.DOCUMENTED_INTENT)

    def test_orphan_evidence_is_retained_without_creating_a_trace(self):
        p = payload()
        p["evidence"].append({"evidence_id": "ORPHAN", "kind": "design_decision_record",
                              "requirement_id": "UNKNOWN-REQ", "decision_id": "UNKNOWN-DD",
                              "cites_requirement_version": 1, "statement": "Fictional orphan."})
        before = result(p)
        self.assertIn("ORPHAN", [e["evidence_id"] for e in before["evidence"]])
        self.assertEqual(result(before), before)
        self.assertEqual(before["counts"], result(payload())["counts"])

    def test_forged_derived_state_is_not_read_as_source_evidence(self):
        r = result(payload())
        r["links"][0]["state"] = s.OBSERVED_PRACTICE
        r["counts"]["by_state"] = {s.OBSERVED_PRACTICE: 6}
        self.assertEqual(result(r), result(payload()))

    def test_cli_export_can_be_the_next_input(self):
        with tempfile.TemporaryDirectory() as td:
            first, second = Path(td) / "first.json", Path(td) / "second.json"
            a = cli("--records", FIXTURE, "--json-out", first)
            b = cli("--records", first, "--json-out", second)
            self.assertEqual(a.returncode, 0, a.stderr)
            self.assertEqual(b.returncode, 0, b.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())


class UnknownAndShapeTests(unittest.TestCase):
    def test_missing_and_null_boundary_remain_unknown(self):
        for fields in ({}, {"crosses_trust_boundary": None}):
            with self.subTest(fields=fields):
                f = s.DataFlow({"flow_id": "F-UNKNOWN", **fields})
                self.assertIsNone(f.crosses_trust_boundary)
                self.assertIsNone(s.DataFlow(f.to_dict()).crosses_trust_boundary)

    def test_unknown_boundary_is_visible_in_both_documents(self):
        p = payload()
        p["data_flows"][0].pop("crosses_trust_boundary")
        p["data_flows"][-1]["crosses_trust_boundary"] = None
        r = result(p)
        self.assertIn("trust boundary UNKNOWN", s.render_evidence_chain(r))
        row = next(x for x in s.render_worksheet(r).splitlines() if "FLOW-SYN-05` |" in x)
        self.assertIn("UNKNOWN", row)
        self.assertNotIn("| no |", row)

    def test_false_stays_false_instead_of_unknown(self):
        f = s.DataFlow({"flow_id": "F", "crosses_trust_boundary": False})
        self.assertIs(f.crosses_trust_boundary, False)
        self.assertIs(s.DataFlow(f.to_dict()).crosses_trust_boundary, False)

    def test_non_boolean_boundary_is_not_interpreted_by_truthiness(self):
        for value in ("false", "true", "", 0, 1, [], {}):
            with self.subTest(value=value), self.assertRaises(s.SecureDesignError):
                s.DataFlow({"flow_id": "F", "crosses_trust_boundary": value})

    def test_null_required_statements_and_ids_are_not_strings(self):
        for collection, field in (("requirements", "statement"), ("evidence", "statement"),
                                  ("evidence", "evidence_id")):
            with self.subTest(collection=collection, field=field):
                p = payload()
                p[collection][0][field] = None
                with self.assertRaises(s.SecureDesignError):
                    result(p)

    def test_wrong_text_types_are_refused_not_stringified(self):
        for value in (False, 42, [], {}):
            p = payload()
            p["evidence"][0]["decision_id"] = value
            with self.subTest(value=value), self.assertRaises(s.SecureDesignError):
                result(p)

    def test_record_collections_and_rows_report_named_errors(self):
        for collection in ("requirements", "design_decisions", "data_flows", "evidence"):
            for value in (None, {}, "bad", [None], ["bad"]):
                with self.subTest(collection=collection, value=value):
                    with self.assertRaises(s.SecureDesignError) as caught:
                        result({collection: value})
                    self.assertIn(collection, str(caught.exception))

    def test_direct_record_construction_refuses_non_objects(self):
        for constructor in (s.Requirement, s.DesignDecision, s.DataFlow,
                            lambda p: s.Evidence(p, index=0)):
            with self.subTest(constructor=constructor), self.assertRaises(s.SecureDesignError):
                constructor(None)

    def test_malformed_reference_collections_are_refused(self):
        for collection, key in (("requirements", "ssdf_references"),
                                ("requirements", "applies_to_flows"),
                                ("requirements", "change_history"),
                                ("design_decisions", "governing_requirements")):
            for value in (None, "R1", [None], [" "]):
                p = payload()
                p[collection][0][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(s.SecureDesignError):
                    result(p)

    def test_duplicate_governing_reference_cannot_double_count_link(self):
        p = payload()
        p["design_decisions"][0]["governing_requirements"].append(" SEC-REQ-SYN-01 ")
        with self.assertRaises(s.SecureDesignError):
            result(p)

    def test_cli_bad_input_keeps_existing_output_and_has_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / "bad.json", Path(td) / "previous.json"
            source.write_text('{"evidence": [null]}', encoding="utf-8")
            output.write_bytes(b"preserve me")
            proc = cli("--records", source, "--json-out", output)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("evidence[0]", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertEqual(output.read_bytes(), b"preserve me")

    def test_cli_missing_input_has_named_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            proc = cli("--records", Path(td) / "absent.json")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("absent.json", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)


class FlowAndExportTests(unittest.TestCase):
    def test_wrong_flow_current_artifact_is_not_observed_practice(self):
        p = payload()
        p["evidence"][5]["flow_id"] = "FLOW-SYN-03"
        row = link(result(p), "DD-SYN-02", "SEC-REQ-SYN-02")
        self.assertEqual(row["state"], s.UNKNOWN)
        self.assertEqual(row["evidence_observed_practice"], [])
        self.assertEqual(row["evidence_flow_mismatch"][0]["evidence_id"], "EV-SD-SYN-06")
        self.assertIn("Reconcile", row["next_step"])

    def test_wrong_flow_stale_artifact_does_not_make_a_stale_trace(self):
        p = payload()
        p["evidence"][2]["flow_id"] = "FLOW-SYN-03"
        row = link(result(p))
        self.assertEqual(row["state"], s.DOCUMENTED_INTENT)
        self.assertEqual(row["evidence_stale_trace"], [])
        self.assertEqual(len(row["evidence_flow_mismatch"]), 1)

    def test_valid_current_evidence_survives_a_contradictory_artifact(self):
        p = payload()
        wrong = dict(p["evidence"][5], evidence_id="EV-CONTRADICT", flow_id="FLOW-SYN-03")
        p["evidence"].append(wrong)
        row = link(result(p), "DD-SYN-02", "SEC-REQ-SYN-02")
        self.assertEqual(row["state"], s.OBSERVED_PRACTICE)
        self.assertEqual(len(row["evidence_observed_practice"]), 1)
        self.assertEqual(len(row["evidence_flow_mismatch"]), 1)
        self.assertIn("EV-CONTRADICT", row["next_step"])

    def test_flow_scoped_intent_does_not_become_global_intent(self):
        p = payload()
        p["evidence"] = [{"evidence_id": "POLICY-F3", "kind": "written_standard",
                           "flow_id": "FLOW-SYN-03", "statement": "Fictional F3 policy."}]
        report = result(p)
        self.assertEqual(link(report)["state"], s.UNKNOWN)
        self.assertEqual(link(report, "DD-SYN-03", "SEC-REQ-SYN-03")["state"],
                         s.DOCUMENTED_INTENT)
        self.assertEqual(link(report)["evidence_flow_mismatch"], [])

    def test_unattributed_other_flow_is_not_a_contradiction_or_trace(self):
        row = link(result(payload()), "DD-SYN-01", "SEC-REQ-SYN-03")
        self.assertEqual(row["evidence_naming_requirement_but_no_decision"], [])
        self.assertEqual(row["evidence_flow_mismatch"], [])

    def test_csv_keeps_future_unattributed_and_mismatch_evidence_ids(self):
        p = payload()
        p["evidence"].append(dict(p["evidence"][2], evidence_id="FUTURE", cites_requirement_version=9))
        p["evidence"].append(dict(p["evidence"][2], evidence_id="WRONG-FLOW", flow_id="FLOW-SYN-03"))
        r = result(p)
        rows = s.to_csv_rows(r)
        row = next(dict(zip(rows[0], x)) for x in rows[1:] if x[0] == "DD-SYN-01" and x[1] == "SEC-REQ-SYN-01")
        self.assertIn("FUTURE", row["future_version_artifacts"])
        self.assertIn("WRONG-FLOW", row["flow_mismatch_artifacts"])
        self.assertIn("EV-SD-SYN-09", row["unattributed_artifacts"])
        self.assertIn("WRONG-FLOW", s.render_evidence_chain(r))
        self.assertEqual(result(r), r)

    def test_requirement_revision_demotes_current_trace_until_revisited(self):
        p = payload()
        p["requirements"][1]["current_version"] = 2
        before = result(p)
        self.assertEqual(link(before, "DD-SYN-02", "SEC-REQ-SYN-02")["state"], s.TRACED_STALE)
        new = dict(p["evidence"][5], evidence_id="REVISITED", cites_requirement_version=2)
        p["evidence"].append(new)
        after = result(p)
        row = link(after, "DD-SYN-02", "SEC-REQ-SYN-02")
        self.assertEqual(row["state"], s.OBSERVED_PRACTICE)
        self.assertEqual(len(row["evidence_stale_trace"]), 1)
        self.assertEqual(result(after), after)


if __name__ == "__main__":
    unittest.main()
