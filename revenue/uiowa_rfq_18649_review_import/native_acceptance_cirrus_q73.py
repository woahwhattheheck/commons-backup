"""Exercise the real UIOWA-124 parent workflow; never skip missing dependencies.

Run from any directory with this file's absolute path, or discover with unittest.
The test fixtures are synthetic and confer no University or commercial authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REHEARSAL = Path(__file__).resolve().with_name("native_rehearsal.py")
REVIEW = ROOT / "revenue/uiowa_rfq_18649_review_cycle/review.py"


def files_at(directory: Path) -> dict[str, bytes]:
    return {str(p.relative_to(directory)): p.read_bytes()
            for p in sorted(directory.rglob("*")) if p.is_file()}


def read_json(path: Path):
    return json.loads(path.read_bytes())


class NativeRehearsalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="uiowa124-native-integration-")
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.scratch = Path(cls.workspace.name)
        cls.outputs = {}
        cls.processes = {}
        for label, flags, seed in (("normal", [], "17"), ("optimized", ["-O"], "29")):
            out = cls.scratch / label
            env = dict(os.environ, PYTHONHASHSEED=seed)
            run = subprocess.run(
                [sys.executable, *flags, str(REHEARSAL), "--out", str(out)],
                cwd=cls.scratch, env=env, capture_output=True, text=True,
                timeout=60, check=False,
            )
            if run.returncode != 0:
                raise RuntimeError(f"real {label} rehearsal failed ({run.returncode}): {run.stderr}")
            cls.outputs[label] = out
            cls.processes[label] = run
        cls.normal = cls.outputs["normal"]
        cls.bundle = cls.normal / "native-bundle"
        cls.prepared = read_json(cls.normal / "preparation.json")

    def verify(self, bundle: Path, optimized: bool = False):
        return subprocess.run(
            [sys.executable, *(["-O"] if optimized else []), str(REVIEW), "verify", str(bundle)],
            cwd=self.scratch, capture_output=True, text=True, timeout=60, check=False,
        )

    def test_public_cli_receipts_match_written_receipts(self):
        for label, out in self.outputs.items():
            with self.subTest(mode=label):
                run = self.processes[label]
                self.assertEqual(run.stderr, "")
                receipt = read_json(out / "receipt.json")
                self.assertEqual(json.loads(run.stdout), receipt)
                self.assertIs(receipt["real_parent_compiler"], True)
                self.assertIs(receipt["native_bundle_verified"], True)
                self.assertIs(receipt["synthetic"], True)

    def test_optimized_and_hash_seed_parity_covers_every_file(self):
        normal = files_at(self.normal)
        self.assertEqual(normal, files_at(self.outputs["optimized"]))
        self.assertEqual(len(normal), 15)
        self.assertEqual(len(files_at(self.bundle)), 11)

    def test_native_cli_regenerates_both_bundles(self):
        for label, out in self.outputs.items():
            with self.subTest(mode=label):
                run = self.verify(out / "native-bundle", label == "optimized")
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn("REGENERATED_EXACTLY", run.stdout)
                self.assertEqual(run.stderr, "")

    def test_duplicate_multiline_comment_retains_both_source_rows(self):
        mapped = {m["record"]["comment_id"]: m for m in self.prepared["mapped"]}
        row = mapped["CSV-SYN-C1"]["record"]
        self.assertEqual(row["values"]["comment_text"],
                         'Please clarify this title.\nKeep the quoted word "illustrative".')
        self.assertEqual({o["record_number"] for o in row["occurrences"]}, {1, 3})
        source_digest = hashlib.sha256((self.normal / "comments.csv").read_bytes()).hexdigest()
        for occurrence in row["occurrences"]:
            self.assertEqual(occurrence["sha256"], source_digest)
            self.assertGreater(occurrence["line_end"], occurrence["line_start"])
        self.assertEqual(mapped["CSV-SYN-C1"]["reviewer_role"], "Fictional practitioner role")

    def test_unresolved_references_remain_explicit(self):
        unresolved = {r["comment_id"]: r for r in self.prepared["staged"]["unresolved"]}
        self.assertEqual(set(unresolved), {"CSV-SYN-C3", "CSV-SYN-C4"})
        self.assertEqual(unresolved["CSV-SYN-C3"]["diagnostics"][0]["code"], "UNKNOWN_FINDING")
        self.assertEqual(unresolved["CSV-SYN-C4"]["diagnostics"][0]["code"], "VERSION_MISMATCH")
        self.assertEqual(self.prepared["summary"]["native_open_comments"], 2)

    def test_csv_supplied_accept_never_becomes_an_import_decision(self):
        self.assertEqual(len(self.prepared["cycle"]["comments"]), 2)
        for comment in self.prepared["cycle"]["comments"]:
            self.assertEqual(comment["decision"], "OPEN")
            self.assertEqual(comment["proposed_changes"], [])
            self.assertEqual(comment["source_ids"], [])
            self.assertEqual(comment["owner_role"], "UNASSIGNED")
        for mapped in self.prepared["mapped"]:
            self.assertEqual(mapped["record"]["values"]["supplied_decision"], "ACCEPT")
            self.assertTrue(mapped["record"]["values"]["extra_context"].startswith("SYNTHETIC"))

    def test_synthetic_disposition_changes_only_title_and_keeps_disagreement(self):
        audit = read_json(self.bundle / "audit.json")
        old = read_json(self.bundle / "original-draft.json")
        new = read_json(self.bundle / "revised-draft.json")
        self.assertEqual(len(audit["changes"]), 1)
        self.assertEqual(audit["changes"][0]["field"], "title")
        self.assertEqual(new["findings"][0]["title"], "Clarified illustrative review target")
        self.assertEqual(old["findings"][0]["statement"], new["findings"][0]["statement"])
        self.assertEqual(old["findings"][0]["source_ids"], new["findings"][0]["source_ids"])
        self.assertEqual(audit["source_changes"], [])
        self.assertEqual(audit["compiler_status_changes"], [])
        self.assertEqual((self.bundle / "original-report.json").read_bytes(),
                         (self.bundle / "revised-report.json").read_bytes())
        self.assertEqual(len(new["unresolved"]), 1)
        self.assertEqual(new["unresolved"][0]["decision"], "UNRESOLVED")
        self.assertEqual(new["unresolved"][0]["comment"], "Keep this disagreement explicitly unresolved.")
        self.assertTrue(all(v is False for v in new["authority"].values()))
        original_text = {c["id"]: c["comment"] for c in self.prepared["cycle"]["comments"]}
        for response in audit["responses"]:
            self.assertEqual(response["comment"], original_text[response["id"]])

    def test_modified_response_is_rejected_by_native_regeneration(self):
        out = self.scratch / "tampered-response"
        shutil.copytree(self.bundle, out)
        (out / "responses.md").write_text("invented response\n", encoding="utf-8")
        run = self.verify(out)
        self.assertEqual(run.returncode, 2)
        self.assertIn("bundle regeneration mismatch: responses.md", run.stderr)

    def test_extra_bundle_artifact_is_rejected(self):
        out = self.scratch / "extra-artifact"
        shutil.copytree(self.bundle, out)
        (out / "unexpected.txt").write_text("not generated\n", encoding="utf-8")
        run = self.verify(out, optimized=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("bundle file set differs", run.stderr)

    def test_existing_rehearsal_output_is_not_overwritten(self):
        before = files_at(self.normal)
        run = subprocess.run(
            [sys.executable, "-O", str(REHEARSAL), "--out", str(self.normal)],
            cwd=self.scratch, capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(run.returncode, 2)
        self.assertIn("File exists", run.stderr)
        self.assertEqual(files_at(self.normal), before)

    def test_rehashed_semantically_changed_report_is_rejected(self):
        out = self.scratch / "changed-report"
        shutil.copytree(self.bundle, out)
        report = read_json(out / "original-report.json")
        report["status_counts"] = {"READY": 12}
        unsigned = {k: v for k, v in report.items() if k != "receipt_sha256"}
        encode = lambda value: (json.dumps(value, sort_keys=True, ensure_ascii=False,
                                           separators=(",", ":"), allow_nan=False) + "\n").encode()
        report["receipt_sha256"] = hashlib.sha256(encode(unsigned)).hexdigest()
        (out / "original-report.json").write_bytes(encode(report))
        run = self.verify(out, optimized=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("report semantic recompile mismatch", run.stderr)


if __name__ == "__main__":
    unittest.main()
