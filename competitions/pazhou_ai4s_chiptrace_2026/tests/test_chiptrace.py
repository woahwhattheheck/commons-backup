import csv
import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("chiptrace", HERE / "chiptrace.py")
ct = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["chiptrace"] = ct
SPEC.loader.exec_module(ct)


class ChipTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_demo_is_deterministic_and_detects_review(self):
        a = self.root / "a"
        b = self.root / "b"
        ba, ra = ct.generate_demo(a)
        bb, rb = ct.generate_demo(b)
        self.assertEqual(ba.read_bytes(), bb.read_bytes())
        self.assertEqual(ra.read_bytes(), rb.read_bytes())
        report1 = ct.analyze(ba, ra)
        report2 = ct.analyze(ba, ra)
        self.assertEqual(report1, report2)
        self.assertEqual(report1["overall_state"], "REVIEW")
        states = {x["channel"]: x["state"] for x in report1["channel_assessments"]}
        self.assertEqual(states["barrier_index"], "REVIEW")
        self.assertEqual(states["oxygen_index"], "REVIEW")
        self.assertTrue(ct.verify_report(report1))

    def test_receipt_detects_tamper(self):
        b, r = ct.generate_demo(self.root)
        report = ct.analyze(b, r)
        self.assertTrue(ct.verify_report(report))
        report["overall_state"] = "SUPPORTED"
        self.assertFalse(ct.verify_report(report))

    def test_html_carries_scope_disclaimer_and_receipt(self):
        b, r = ct.generate_demo(self.root)
        report = ct.analyze(b, r)
        page = ct.render_html(report)
        self.assertIn("Research QC only", page)
        self.assertIn(report["receipt_sha256"], page)
        self.assertIn("does not establish biological efficacy", page)

    def test_unknown_or_identity_column_is_fail_closed(self):
        p = self.root / "bad.csv"
        p.write_text(
            "run_id,replicate_id,time_s,channel,value,unit,source,modality,patient_id\n"
            "r,x,0,c,1,u,s,m,P123\n",
            encoding="utf-8",
        )
        with self.assertRaises(ct.ContractError):
            ct.load_csv(p)

    def test_duplicate_observation_is_rejected(self):
        p = self.root / "dup.csv"
        header = ",".join(ct.REQUIRED_COLUMNS)
        row = "r,x,0,c,1,u,s,m"
        p.write_text(header + "\n" + row + "\n" + row + "\n", encoding="utf-8")
        with self.assertRaises(ct.ContractError):
            ct.load_csv(p)

    def test_unit_mismatch_is_rejected(self):
        b, r = ct.generate_demo(self.root)
        rows = list(csv.reader(r.read_text(encoding="utf-8").splitlines()))
        rows[1][5] = "wrong_unit"
        bad = self.root / "bad_run.csv"
        with bad.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerows(rows)
        with self.assertRaises(ct.ContractError):
            ct.analyze(b, bad)

    def test_small_run_is_insufficient_evidence(self):
        b, r = ct.generate_demo(self.root)
        obs = ct.load_csv(r)
        one_channel = [x for x in obs if x.channel == "flow_index"][:3]
        small = self.root / "small.csv"
        ct.write_csv(small, one_channel)
        report = ct.analyze(b, small)
        self.assertEqual(report["overall_state"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(report["channel_assessments"][0]["state"], "INSUFFICIENT_EVIDENCE")

    def test_nonfinite_value_is_rejected(self):
        p = self.root / "nan.csv"
        p.write_text(
            ",".join(ct.REQUIRED_COLUMNS) + "\n" + "r,x,0,c,nan,u,s,m\n",
            encoding="utf-8",
        )
        with self.assertRaises(ct.ContractError):
            ct.load_csv(p)

    def test_missingness_signal_is_observable(self):
        b, r = ct.generate_demo(self.root)
        report = ct.analyze(b, r)
        missing = [x["metrics"]["missing_fraction"] for x in report["channel_assessments"]]
        self.assertGreater(max(missing), 0.0)

    def test_report_roundtrip_json_verifies(self):
        b, r = ct.generate_demo(self.root)
        report = ct.analyze(b, r)
        encoded = json.dumps(report, sort_keys=True)
        decoded = json.loads(encoded)
        self.assertTrue(ct.verify_report(decoded))


if __name__ == "__main__":
    unittest.main()
