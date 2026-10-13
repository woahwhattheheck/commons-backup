"""Receipt-binding regressions, separate from actual public-source replay."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normalize_barnyard as subject
from normalize import SourceError, digest


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.nb = {"nbformat": 4, "cells": [{"cell_type": "code", "source": "%%writefile main.py\nx=1\n"}]}
        self.pull = {"metadata": {"ref": "romanrozen/strong-barnyard-economist", "id": 129253091,
                                  "isPrivate": False, "currentVersionNumber": 7, "author": "Fixture"},
                     "blob": {"source": json.dumps(self.nb)}}
        self.stage()

    def stage(self):
        rows = []
        for name, value, url in (("barnyard-pull.json", self.pull, subject.PULL_URL),
                                 ("barnyard-v7-download", self.nb, subject.FIXED_URL)):
            data = json.dumps(value).encode()
            (self.root / name).write_bytes(data)
            rows.append({"path": name, "status": 200, "requested_url": url, "final_url": url,
                         "bytes": len(data), "sha256": digest(data)})
        self.receipt = {"run_id": "fixture", "run_attempt": "1", "requests": rows}
        self.save_receipt()

    def save_receipt(self):
        (self.root / "INTAKE.json").write_text(json.dumps(self.receipt))

    def test_binding_and_normalization_without_execution(self):
        r = subject.bind_intake(self.root)
        self.assertTrue(r["cell_sources_equal"])
        self.assertEqual(r["cell_count"], 1)
        self.assertEqual(r["version_number_observed"], 7)
        self.assertEqual(r["fixed_download_script_version_id"], 341074820)
        # A synthetic source pin is scoped only to this fixture, not the real replay.
        with patch.object(subject, "MAIN_SHA256", digest(b"x=1\n")):
            out = self.root / "out"
            result = subject.normalize_intake(self.root, out)
        self.assertEqual((out / "main.py").read_bytes(), b"x=1\n")
        self.assertFalse(result["execution_performed"])
        self.assertTrue((out / "provenance/BINDING.json").exists())

    def test_recorded_bytes_cannot_drift(self):
        with (self.root / "barnyard-v7-download").open("ab") as f:
            f.write(b" ")
        with self.assertRaisesRegex(SourceError, "bytes differ"):
            subject.bind_intake(self.root)

    def test_latest_version_and_visibility_not_inferred(self):
        for field, value in (("currentVersionNumber", 8), ("currentVersionNumber", True),
                             ("isPrivate", True), ("isPrivate", 0), ("id", 0), ("ref", "other/notebook")):
            with self.subTest(field=field, value=value):
                old = self.pull["metadata"][field]
                self.pull["metadata"][field] = value; self.stage()
                with self.assertRaises(SourceError): subject.bind_intake(self.root)
                self.pull["metadata"][field] = old
        self.stage()

    def test_cell_difference_is_not_hidden_by_source_title(self):
        changed = copy.deepcopy(self.nb)
        changed["cells"][0]["source"] += "y=2\n"
        self.pull["blob"]["source"] = json.dumps(changed); self.stage()
        with self.assertRaisesRegex(SourceError, "differ at cell 0"):
            subject.bind_intake(self.root)

    def test_transport_identity_and_duplicate_record(self):
        self.receipt["requests"][1]["final_url"] = "https://example.test/other"
        self.save_receipt()
        with self.assertRaisesRegex(SourceError, "response identity"):
            subject.bind_intake(self.root)
        self.stage()
        self.receipt["requests"].append(self.receipt["requests"][0]); self.save_receipt()
        with self.assertRaisesRegex(SourceError, "exactly one"):
            subject.bind_intake(self.root)

    def test_unreviewed_source_pin_leaves_no_package(self):
        out = self.root / "out"
        with self.assertRaisesRegex(SourceError, "source pin"):
            subject.normalize_intake(self.root, out)
        self.assertFalse(out.exists())

    def test_existing_output_not_removed_after_failed_normalization(self):
        out = self.root / "out"; out.mkdir(); (out / "keep").write_text("retained")
        with self.assertRaises(FileExistsError):
            subject.normalize_intake(self.root, out)
        self.assertEqual((out / "keep").read_text(), "retained")


if __name__ == "__main__":
    unittest.main()
