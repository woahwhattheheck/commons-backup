"""Actual source/CLI rehearsal, unchanged inputs, and reopened bundle checks."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import rehearse_change as demo
import secure_design as sd

HERE = Path(__file__).resolve().parent


def records():
    return sd.read_json(str(HERE / "fixtures" / "secure_design_records.json"))


class RehearsalTests(unittest.TestCase):
    def test_three_states_show_real_change_then_new_evidence(self):
        report = demo.run_rehearsal(records())
        stages = report["stages"]
        self.assertEqual([s["state"] for s in stages],
                         [sd.OBSERVED_PRACTICE, sd.TRACED_STALE, sd.OBSERVED_PRACTICE])
        self.assertEqual([s["requirement_version"] for s in stages], [1, 2, 2])
        self.assertEqual(stages[-1]["stale_evidence_ids"], ["EV-SD-SYN-06"])
        self.assertEqual(stages[-1]["current_evidence_ids"], ["EV-REHEARSAL-1"])
        self.assertTrue(all(s["json_round_trip_equal"] for s in stages))

    def test_input_is_not_mutated_and_repetition_is_deterministic(self):
        original = records()
        before = copy.deepcopy(original)
        first = demo.run_rehearsal(original)
        self.assertEqual(original, before)
        self.assertEqual(first, demo.run_rehearsal(original))

    def test_unrelated_unknown_and_stale_links_stay_visible(self):
        for stage in demo.run_rehearsal(records())["stages"]:
            rows = stage["assessment"]["links"]
            unknown = next(x for x in rows if x["decision_id"] == "DD-SYN-05")
            stale = next(x for x in rows if x["decision_id"] == "DD-SYN-01"
                         and x["requirement_id"] == "SEC-REQ-SYN-01")
            self.assertEqual(unknown["state"], sd.UNKNOWN)
            self.assertEqual(stale["state"], sd.TRACED_STALE)

    def test_bad_or_unobserved_link_is_refused(self):
        for rid, did in (("NOT-FOUND", "DD-SYN-02"), ("SEC-REQ-SYN-01", "DD-SYN-05")):
            with self.subTest(rid=rid), self.assertRaises(sd.SecureDesignError):
                demo.run_rehearsal(records(), rid, did)

    def test_future_citation_must_be_reconciled_first(self):
        p = records()
        p["evidence"].append(dict(p["evidence"][5], evidence_id="FUTURE", cites_requirement_version=2))
        with self.assertRaisesRegex(sd.SecureDesignError, "future-version"):
            demo.run_rehearsal(p)

    def test_generated_evidence_id_does_not_overwrite_prior_record(self):
        p = records()
        p["evidence"][0]["evidence_id"] = "EV-REHEARSAL-1"
        r = demo.run_rehearsal(p)
        self.assertEqual(r["stages"][-1]["current_evidence_ids"], ["EV-REHEARSAL-2"])
        self.assertEqual(len(r["stages"][-1]["assessment"]["evidence"]), len(p["evidence"]) + 1)

    def test_bundle_manifest_reopens_every_export(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bundle"
            demo.write_bundle(demo.run_rehearsal(records()), out)
            manifest = json.loads((out / "manifest.json").read_bytes())
            self.assertEqual(len(manifest["files"]), 13)
            self.assertEqual(len(list(out.iterdir())), 14)
            for entry in manifest["files"]:
                data = (out / entry["path"]).read_bytes()
                self.assertEqual(len(data), entry["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
            for stage in manifest["stages"]:
                report = json.loads((out / (stage["name"] + ".json")).read_bytes())
                self.assertEqual(sd.assess(*sd.load_records(report)), report)

    def test_existing_bundle_is_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bundle"
            report = demo.run_rehearsal(records())
            demo.write_bundle(report, out)
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            with self.assertRaises(FileExistsError):
                demo.write_bundle(report, out)
            self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_cli_normal_and_optimized_exports_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            outputs = []
            for name, options in (("normal", []), ("optimized", ["-O"])):
                out = Path(td) / name
                proc = subprocess.run([sys.executable, *options, str(HERE / "rehearse_change.py"),
                                       "--out-dir", str(out)], capture_output=True, text=True, timeout=15)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("requirement_changed: v2 TRACED_STALE", proc.stdout)
                outputs.append({p.name: p.read_bytes() for p in out.iterdir()})
            self.assertEqual(*outputs)

    def test_cli_refuses_an_existing_path_with_named_error(self):
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run([sys.executable, str(HERE / "rehearse_change.py"),
                                   "--out-dir", td], capture_output=True, text=True, timeout=15)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("ERROR:", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertEqual(list(Path(td).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
