"""Dependency-free behavioral regression for the UIOWA-056 offline assessor."""
import copy
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from components import InputError, assess, bundle, json_bytes, load, safe_cell
from example import example


class ComponentTests(unittest.TestCase):
    def setUp(self):
        self.doc = example()

    def row(self, cid="C01", doc=None):
        return next(x for x in assess(doc or self.doc)["components"] if x["component_id"] == cid)

    def advisory(self, cid, doc=None):
        return next(x for x in assess(doc or self.doc)["advisories"] if x["component_id"] == cid)

    def test_support_states_and_inventory(self):
        result = assess(self.doc)
        self.assertEqual(result["summary"]["support_counts"],
                         {"supported": 3, "unsupported": 1, "ending_soon": 1, "unknown": 2})
        self.assertEqual(self.row("C04")["inventory_evidence_quality"], "stale")
        self.assertEqual(self.row("C05")["support_state"], "unknown")

    def test_support_end_is_inclusive(self):
        c = self.doc["components"][0]
        for end, expected in [("2026-09-18", "unsupported"), ("2026-09-19", "ending_soon"),
                              ("2026-12-18", "ending_soon"), ("2026-12-19", "supported")]:
            with self.subTest(end=end):
                c["support"]["ends_on"] = end
                self.assertEqual(self.row()["support_state"], expected)

    def test_freshness_threshold_is_inclusive(self):
        e = self.doc["evidence"][0]
        now = date.fromisoformat(self.doc["as_of"])
        e["observed_on"] = (now - timedelta(days=120)).isoformat()
        self.assertEqual(self.row()["support_state"], "supported")
        e["observed_on"] = (now - timedelta(days=121)).isoformat()
        self.assertEqual(self.row()["support_state"], "unknown")

    def test_missing_support_is_unknown(self):
        self.doc["components"][0]["support"]["evidence"] = []
        self.assertEqual(self.row()["support_state"], "unknown")

    def test_conflicting_support_needs_reconciliation(self):
        self.doc["components"][0]["support"]["state"] = "unsupported"
        self.assertEqual(self.row()["support_state"], "unknown")
        r = next(x for x in assess(self.doc)["roadmap"] if x["component_id"] == "C01")
        self.assertIn("reconcile_conflicting_support_record", r["reasons"])

    def test_presence_and_unsupported_do_not_mean_exposure(self):
        self.assertEqual(self.row()["advisory_record_count"], 0)
        self.assertEqual(self.advisory("C02")["qualified_reported_exposure"], "unknown")
        self.assertNotIn("vulnerable", self.row("C02"))
        self.assertIn("No advisory records does not mean no vulnerabilities", assess(self.doc)["limitations"])

    def test_unsupported_claims_not_affected_and_exposure_are_unknown(self):
        a = self.advisory("C03")
        self.assertEqual(a["reported_applicability"], "not_affected")
        self.assertEqual(a["qualified_applicability"], "unknown")
        self.assertEqual(a["reported_exposure"], "confirmed")
        self.assertEqual(a["qualified_reported_exposure"], "unknown")

    def test_closure_needs_current_scoped_evidence(self):
        self.assertEqual(self.advisory("C04")["record_disposition"], "unverified_closure")
        self.assertEqual(self.advisory("C07")["record_disposition"], "documented_closure")
        self.doc["as_of"] = "2027-01-10"
        self.assertEqual(self.advisory("C07")["record_disposition"], "unverified_closure")

    def test_current_exception_retains_reported_exposure(self):
        a = self.advisory("C06")
        self.assertEqual(a["record_disposition"], "recorded_exception_current")
        self.assertEqual(a["qualified_reported_exposure"], "confirmed")
        self.assertFalse(a["overdue"])
        self.assertEqual(self.advisory("C03")["record_disposition"], "expired_exception")

    def test_exception_expiry_and_owner_boundaries(self):
        a = self.doc["components"][5]["advisories"][0]
        a["exception_until"] = "2026-09-19"
        self.assertEqual(self.advisory("C06")["record_disposition"], "recorded_exception_current")
        a["owner_role"] = None
        self.assertEqual(self.advisory("C06")["record_disposition"], "unverified_exception")
        a["exception_until"] = "2026-09-18"
        self.assertEqual(self.advisory("C06")["record_disposition"], "expired_exception")

    def test_exposure_conflict_is_not_hidden_by_closure(self):
        a = self.doc["components"][6]["advisories"][0]
        a["exposure"] = "confirmed"
        r = self.advisory("C07")
        self.assertTrue(r["conflicting_records"])
        self.assertEqual(r["record_disposition"], "documented_closure")
        m = next(x for x in assess(self.doc)["roadmap"] if x["component_id"] == "C07")
        self.assertEqual(m["priority"], 1)

    def test_active_exposure_priority(self):
        a = self.doc["components"][5]["advisories"][0]
        a["disposition"], a["exception_until"], a["disposition_evidence"] = "open", None, []
        m = next(x for x in assess(self.doc)["roadmap"] if x["component_id"] == "C06")
        self.assertEqual(m["priority"], 1)
        self.assertIn("review_reported_exposure", m["reasons"])

    def test_shared_effort_not_multiplied_unknown_not_zero(self):
        result = assess(self.doc)
        self.assertEqual(result["summary"]["maintenance_item_count"], 5)
        self.assertEqual(result["summary"]["unestimated_item_count"], 1)
        self.assertEqual(result["summary"]["known_effort_low_days"], 9)
        self.assertEqual(result["summary"]["known_effort_high_days"], 16)
        r = [x for x in result["roadmap"] if x["component_id"] == "C02"]
        self.assertEqual(len(r), 1)
        self.assertEqual(len(r[0]["service_ids"]), 2)

    def test_due_today_not_overdue(self):
        self.doc["components"][1]["advisories"][0]["due_on"] = "2026-09-19"
        self.assertFalse(self.advisory("C02")["overdue"])

    def test_input_not_mutated_and_output_not_aliased(self):
        before = copy.deepcopy(self.doc)
        result = assess(self.doc)
        result["evidence"][0]["component_ids"].append("NO")
        result["components"][0]["service_ids"].append("NO")
        self.assertEqual(before, self.doc)

    def test_deterministic_payload_and_hashes(self):
        a, b = bundle(self.doc), bundle(copy.deepcopy(self.doc))
        self.assertEqual(a, b)
        manifest = json.loads(a["manifest.json"])
        self.assertEqual(set(manifest["files"]), set(a) - {"manifest.json"})
        for name, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256(a[name]).hexdigest(), digest)
        self.assertEqual(hashlib.sha256(json_bytes(self.doc)).hexdigest(), manifest["canonical_input_sha256"])

    def test_empty_inventory_is_not_health_claim(self):
        self.doc["components"], self.doc["evidence"] = [], []
        r = assess(self.doc)
        self.assertEqual(r["summary"]["component_count"], 0)
        self.assertIn("not a vulnerability scan", r["limitations"])
        self.assertEqual(len(list(csv.reader(io.StringIO(bundle(self.doc)["components.csv"].decode())))), 1)

    def test_csv_and_markdown_active_content_is_text(self):
        for text in ["=SUM(A1)", " +1", "\t@TEST", "\r-5", "\n=1"]:
            with self.subTest(text=text):
                self.assertEqual(safe_cell(text), "'" + text)
        self.doc["components"][0]["name"] = "=HYPERLINK(\"fictional\")"
        self.doc["components"][0]["owner_role"] = "<script>x</script>|`test`\nrow"
        files = bundle(self.doc)
        rows = list(csv.DictReader(io.StringIO(files["components.csv"].decode())))
        self.assertTrue(rows[0]["name"].startswith("'="))
        self.assertNotIn("<script>", files["summary.md"].decode())
        self.assertIn("&#124;", files["summary.md"].decode())

    def test_bad_records_rejected(self):
        mutations = [
            lambda d: d.update(extra=True),
            lambda d: d.update(horizon_days=True),
            lambda d: d.update(as_of="2026-02-30"),
            lambda d: d["components"].append(copy.deepcopy(d["components"][0])),
            lambda d: d["components"][0].update(services=["UNKNOWN"]),
            lambda d: d["components"][0].update(inherited="yes"),
            lambda d: d["components"][0].update(last_update_on="2027-01-01"),
            lambda d: d["components"][0]["maintenance"].update(effort_low_days=True),
            lambda d: d["components"][0]["maintenance"].update(effort_low_days=3),
            lambda d: d["components"][0]["maintenance"].update(effort_low_days=None),
            lambda d: d["components"][0]["maintenance"].update(effort_high_days=float("inf")),
            lambda d: d["evidence"][0].update(observed_on="2026-12-01"),
            lambda d: d["evidence"][0].update(component_ids=["UNKNOWN"]),
            lambda d: d["evidence"][0].update(kind="closure"),
            lambda d: d["components"][0]["support"].update(evidence=[d["evidence"][1]["id"]]),
            lambda d: d["components"][0]["support"].update(evidence=d["components"][1]["support"]["evidence"]),
            lambda d: d["components"][1]["advisories"][0].update(exception_until="2026-12-01"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                d = copy.deepcopy(self.doc)
                mutate(d)
                with self.assertRaises(InputError):
                    assess(d)

    def test_disposition_scope_and_timeline(self):
        c = self.doc["components"][6]
        other = copy.deepcopy(c["advisories"][0])
        other["id"] = "OTHER-ADVISORY"
        c["advisories"].append(other)
        with self.assertRaisesRegex(InputError, "advisory scope"):
            assess(self.doc)
        c["advisories"].pop()
        closure = next(x for x in self.doc["evidence"] if x["kind"] == "closure")
        closure["observed_on"] = "2026-08-01"
        with self.assertRaisesRegex(InputError, "predates"):
            assess(self.doc)

    def test_json_duplicates_nonfinite_and_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input.json"
            for raw in [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'\xff', b' ' * (4*1024*1024+1)]:
                with self.subTest(length=len(raw)):
                    p.write_bytes(raw)
                    with self.assertRaises(InputError):
                        load(p)

    def test_real_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p, out = root / "input.json", root / "report"
            p.write_bytes(json_bytes(self.doc))
            command = [sys.executable, str(Path(__file__).with_name("components.py")), str(p), "--out", str(out)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = bundle(self.doc)
            self.assertEqual({x.name: x.read_bytes() for x in out.iterdir()}, expected)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual({x.name: x.read_bytes() for x in out.iterdir()}, expected)
            p.write_text('{"schema_version":"bad"}')
            command[-1] = str(root / "invalid")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertFalse((root / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
