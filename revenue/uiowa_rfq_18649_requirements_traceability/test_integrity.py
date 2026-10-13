"""Boundary regressions for UIOWA-042; all supplied records are fictional."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_trace import minimal
from trace import Example, TraceError, load

HERE = Path(__file__).resolve().parent


class IntegrityTests(unittest.TestCase):
    def state(self, payload):
        return Example(payload).results[0]["state"]

    def test_missing_acceptance_revision_is_not_assumed(self):
        p = minimal()
        del p["acceptances"][0]["criterion_revision"]
        self.assertEqual(self.state(p), "INCOMPLETE_ACCEPTANCE")

    def test_missing_criterion_revision_is_not_assumed(self):
        p = minimal()
        del p["criteria"][0]["revision"]
        e = Example(p)
        self.assertEqual(e.results[0]["revision"], "UNKNOWN")
        self.assertEqual(e.results[0]["state"], "BROKEN_LINK")

    def test_revision_types_never_coerce_into_a_pass(self):
        for value in (None, True, False, 1.0, 0, -1, "1", "UNKNOWN", [], {}):
            for section, key in (("criteria", "revision"), ("acceptances", "criterion_revision")):
                with self.subTest(section=section, value=value):
                    p = minimal()
                    p[section][0][key] = value
                    self.assertEqual(Example(p).verdict(), "NOT_ESTABLISHED")

    def test_future_acceptance_is_not_mislabeled_as_old(self):
        p = minimal()
        p["acceptances"][0]["criterion_revision"] = 2
        self.assertEqual(self.state(p), "BROKEN_LINK")

    def test_mixed_known_unknown_acceptances_remain_open(self):
        p = minimal()
        a = dict(p["acceptances"][0], acceptance_id="A2")
        del a["criterion_revision"]
        p["acceptances"].append(a)
        self.assertEqual(self.state(p), "INCOMPLETE_ACCEPTANCE")

    def test_current_and_future_acceptances_remain_open(self):
        p = minimal()
        p["acceptances"].append(dict(p["acceptances"][0], acceptance_id="A2", criterion_revision=8))
        self.assertEqual(self.state(p), "BROKEN_LINK")

    def test_real_old_revision_stays_old(self):
        p = minimal()
        p["criteria"][0]["revision"] = 3
        self.assertEqual(self.state(p), "ACCEPTED_AGAINST_SUPERSEDED_REVISION")

    def test_old_and_current_records_can_trace_without_deletion(self):
        p = minimal()
        p["criteria"][0]["revision"] = 2
        p["acceptances"].append(dict(p["acceptances"][0], acceptance_id="A2", criterion_revision=2))
        self.assertEqual(self.state(p), "TRACED")
        self.assertEqual(len(p["acceptances"]), 2)

    def test_self_cycle_with_a_clean_neighbor_stays_open(self):
        p = minimal()
        p["criteria"].append(dict(p["criteria"][0], criterion_id="C2", superseded_by="C2"))
        e = Example(p)
        self.assertEqual(e.results[1]["state"], "BROKEN_LINK")
        self.assertEqual(e.verdict(), "NOT_ESTABLISHED")

    def test_multi_node_cycle_is_not_retirement(self):
        p = minimal()
        p["criteria"][0]["superseded_by"] = "C2"
        p["criteria"].append(dict(p["criteria"][0], criterion_id="C2", superseded_by="C1"))
        self.assertTrue(all(r["state"] == "BROKEN_LINK" for r in Example(p).results))

    def test_cycle_upstream_also_stays_open(self):
        p = minimal()
        p["criteria"][0]["superseded_by"] = "C2"
        p["criteria"].append(dict(p["criteria"][0], criterion_id="C2", superseded_by="C2"))
        self.assertTrue(all(r["state"] == "BROKEN_LINK" for r in Example(p).results))

    def test_cross_request_successor_needs_reconciliation(self):
        p = minimal()
        p["requests"].append({"request_id": "R2", "revision": 1})
        p["criteria"][0]["superseded_by"] = "C2"
        p["criteria"].append({"criterion_id": "C2", "request_id": "R2", "revision": 1})
        self.assertEqual(self.state(p), "BROKEN_LINK")

    def test_orphan_in_each_section_blocks_only_packet_verdict(self):
        for section, key in (("implementations", "impl_id"), ("tests", "test_id"), ("acceptances", "acceptance_id")):
            with self.subTest(section=section):
                p = minimal()
                p[section].append(dict(p[section][0], **{key: "ORPHAN", "criterion_id": "MISSING"}))
                e = Example(p)
                self.assertEqual(e.results[0]["state"], "TRACED")
                self.assertEqual(e.verdict(), "NOT_ESTABLISHED")
                self.assertEqual(len(e.dangling_links()), 1)

    def test_orphan_cli_exit_agrees_with_verdict(self):
        p = minimal()
        p["tests"].append(dict(p["tests"][0], test_id="ORPHAN", criterion_id="MISSING"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.json"
            path.write_text(json.dumps(p))
            proc = subprocess.run([sys.executable, str(HERE / "trace.py"), "--input", str(path)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("NOT_ESTABLISHED", proc.stdout)

    def test_duplicate_ids_refused_in_every_section(self):
        for section in ("requests", "criteria", "implementations", "tests", "acceptances"):
            with self.subTest(section=section):
                p = minimal()
                p[section].append(copy.deepcopy(p[section][0]))
                with self.assertRaises(TraceError):
                    Example(p)

    def test_non_object_rows_and_non_array_sections_are_diagnosed(self):
        for section in ("requests", "criteria", "implementations", "tests", "acceptances"):
            for value in (None, 0, {}, "text", [None], [False], [[]]):
                with self.subTest(section=section, value=value):
                    p = minimal()
                    p[section] = value
                    with self.assertRaises(TraceError):
                        Example(p)

    def test_non_object_payload_is_diagnosed(self):
        for value in (None, 0, [], False, "text"):
            with self.subTest(value=value), self.assertRaises(TraceError):
                Example(value)

    def test_unknown_locator_does_not_close_any_link(self):
        for section, field in (("implementations", "ref"), ("tests", "ref"), ("acceptances", "evidence_ref")):
            for value in (None, "", " ", "UNKNOWN", " unknown "):
                with self.subTest(section=section, value=value):
                    p = minimal()
                    p[section][0][field] = value
                    self.assertEqual(Example(p).verdict(), "NOT_ESTABLISHED")

    def test_unknown_regression_coverage_is_not_evidence(self):
        p = minimal(style="maintenance_change", tests=[])
        p["criteria"][0]["covered_by_regression_ref"] = "UNKNOWN"
        self.assertEqual(self.state(p), "UNTESTED")

    def test_unknown_acceptance_role_or_date_is_incomplete(self):
        for field in ("accepted_by_role", "accepted_at"):
            for value in (None, "", "UNKNOWN"):
                with self.subTest(field=field, value=value):
                    p = minimal()
                    p["acceptances"][0][field] = value
                    self.assertEqual(self.state(p), "INCOMPLETE_ACCEPTANCE")

    def test_input_mutation_cannot_change_evaluated_packet(self):
        p = minimal()
        e = Example(p)
        before = e.as_dict()
        p["acceptances"].clear()
        self.assertEqual(e.as_dict(), before)

    def test_duplicate_json_members_are_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "duplicate.json"
            p.write_text('{"revision": 1, "revision": 2}')
            with self.assertRaises(TraceError):
                load(p)

    def test_nonfinite_json_is_diagnosed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "nan.json"
            p.write_text('{"revision": NaN}')
            with self.assertRaises(TraceError):
                load(p)

    def test_shape_error_cli_has_no_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "root.json"
            p.write_text('[]')
            proc = subprocess.run([sys.executable, str(HERE / "trace.py"), "--input", str(p)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
