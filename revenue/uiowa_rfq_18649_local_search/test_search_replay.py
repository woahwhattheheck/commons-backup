"""Real-parent extraction replay and malformed-input integration regressions."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import evidence_search as mod
from search_provenance import git_blob

HERE = Path(__file__).resolve().parent
REV = "adeeefe4910b3d1c8aa54628053c60efcdb5bbfe"


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(HERE / "fixtures", self.root / "fixtures")
        self.manifest = self.root / "fixtures" / "manifest.json"

    def test_actual_extractor_to_verified_index_to_result(self):
        extractor = HERE.parent / "uiowa_rfq_18649_document_extraction" / "extract.py"
        source = self.root / "sample.txt"
        shutil.copyfile(HERE / "fixtures" / "source-sample.txt", source)
        out = self.root / "extracted.json"
        result = subprocess.run([sys.executable, str(extractor), str(source), "-o", str(out)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(out.read_text())
        self.assertEqual(payload["status"], "ok")
        manifest = {"sources": [{"adapter": "extraction", "local_file": out.name,
                    "local_blob_sha": git_blob(out.read_bytes()), "source_local_file": source.name,
                    "upstream_path": "revenue/uiowa_rfq_18649_document_extraction/fixtures/sample.txt",
                    "upstream_blob_sha": git_blob(source.read_bytes()), "upstream_ref": REV, "synthetic": True}]}
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest))
        rows = mod.load_manifest(path)
        self.assertEqual(len(rows), 4)
        hit = mod.search(mod.build_index(rows), "independent review before merge", limit=1)[0]
        original = next(x for x in payload["segments"] if x["segment_id"] == "text-0002")
        self.assertEqual(hit["original"], original)
        self.assertEqual(hit["locator"], original["locator"])
        self.assertEqual(hit["snippet_exact"]["text"], original["text"])
        self.assertTrue(hit["provenance"]["local_bytes_verified"])

    def test_cli_bad_limit_returns_structured_error_without_traceback(self):
        index = self.root / "index.json"
        index.write_text(json.dumps(mod.build_index(mod.load_manifest(self.manifest))))
        result = subprocess.run([sys.executable, str(HERE / "evidence_search.py"), "query", str(index), "review", "--limit", "-1"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["status"], "error")
        self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        self.manifest.write_text('{"sources": [], "sources": []}')
        with self.assertRaisesRegex(mod.SearchError, "duplicate JSON key"):
            mod.load_manifest(self.manifest)

    def test_nonfinite_json_is_refused(self):
        self.manifest.write_text('{"sources": [], "extra": NaN}')
        with self.assertRaisesRegex(mod.SearchError, "nonfinite"):
            mod.load_manifest(self.manifest)

    def test_symlink_cannot_escape_manifest_root(self):
        original = self.root / "fixtures" / "evidence.csv"
        outside = self.root / "outside.csv"
        original.rename(outside)
        original.symlink_to(outside)
        with self.assertRaisesRegex(mod.SearchError, "outside root"):
            mod.load_manifest(self.manifest)

    def test_saved_index_is_detached_from_mutable_input_records(self):
        rows = mod.load_manifest(self.manifest)
        index = mod.build_index(rows)
        rows[0]["original_text"] = "MUTATION"
        self.assertNotIn("MUTATION", json.dumps(index))
        self.assertTrue(mod.search(index, "review"))

    def test_native_original_extra_field_is_searchable(self):
        rows = mod.load_manifest(self.manifest)
        rows[0]["original"]["review_note"] = "uniqueextraquasar"
        hit = mod.search(mod.build_index(rows), "uniqueextraquasar", limit=1)[0]
        self.assertEqual(hit["record_id"], rows[0]["record_id"])
        self.assertEqual(hit["snippet_exact"]["field"], "original")

    def test_legacy_index_is_explicitly_unbound(self):
        index = mod.build_index(mod.load_manifest(self.manifest))
        index.pop("content_digest")
        self.assertEqual(mod.search(index, "review", limit=1)[0]["index_integrity"], "legacy_unbound")

    def test_invalid_posting_frequency_does_not_reach_logarithm(self):
        index = mod.build_index(mod.load_manifest(self.manifest))
        index.pop("content_digest")
        first = next(iter(index["postings"]))
        rid = next(iter(index["postings"][first]))
        index["postings"][first][rid] = 0
        with self.assertRaisesRegex(mod.SearchError, "frequency"):
            mod.search(index, first)

    def test_original_confidence_and_limitation_are_returned_unchanged(self):
        rows = mod.load_manifest(self.manifest)
        hit = next(x for x in mod.search(mod.build_index(rows), "propagation", limit=20) if x["record_id"] == "F-002")
        self.assertEqual(hit["original"]["confidence"], "moderate")
        self.assertIn("not proof", hit["original"]["limitation"])
        self.assertEqual(hit["linked_ids"], ["E-004", "E-005", "E-006"])
        self.assertEqual(hit["link_diagnostics"], [])


if __name__ == "__main__":
    unittest.main()
