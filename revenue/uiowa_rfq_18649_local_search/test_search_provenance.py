"""Independent regressions for the retained UIOWA-127 search component."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import evidence_search as mod

REF = "a" * 40
CSV = 'evidence_id,service,source_type,source_name,locator,observation,evidence_state\nE-1,RIS,interview,Fictional note,Q12,"First line\nSecond café line",interview_only\n'


def blob(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def manifest(self, text=CSV, adapter="evidence_csv", **extra):
        raw = text.encode("utf-8")
        name = "records.csv" if adapter.endswith("csv") else "records.json"
        (self.root / name).write_bytes(raw)
        source = dict(adapter=adapter, local_file=name, upstream_path="evidence/" + name,
                      upstream_blob_sha=blob(raw), upstream_ref=REF, synthetic=True)
        source.update(extra)
        path = self.root / "manifest.json"
        path.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
        return path

    def extraction(self, status="partial", text="", warnings=None):
        source = b"source bytes\n"
        (self.root / "source.txt").write_bytes(source)
        payload = {"schema": "uiowa.document-extraction.v1",
                   "document": {"name": "source.txt", "sha256": hashlib.sha256(source).hexdigest(), "bytes": len(source)},
                   "status": status, "warnings": warnings or ["SOURCE_PARTIAL"],
                   "segments": [{"segment_id": "s1", "kind": "unreadable" if not text else "text",
                                 "locator": "page 1", "text": text, "heading_path": [],
                                 "warnings": ["OCR_REQUIRED"] if not text else []}]}
        raw = json.dumps(payload)
        return self.manifest(raw, "extraction", upstream_path="evidence/source.txt",
                             upstream_blob_sha=blob(source), local_blob_sha=blob(raw.encode()), source_local_file="source.txt")

    def test_changed_local_bytes_cannot_reuse_declared_blob(self):
        path = self.manifest()
        (self.root / "records.csv").write_text(CSV.replace("First", "Changed"), encoding="utf-8")
        with self.assertRaisesRegex(mod.SearchError, "digest|blob|SHA"):
            mod.load_manifest(path)

    def test_revision_is_required_instead_of_guessing_main(self):
        path = self.manifest(upstream_ref="main")
        with self.assertRaisesRegex(mod.SearchError, "revision|ref"):
            mod.load_manifest(path)

    def test_explicit_synthetic_boolean_required(self):
        path = self.manifest(synthetic="true")
        with self.assertRaisesRegex(mod.SearchError, "synthetic"):
            mod.load_manifest(path)

    def test_multiline_row_has_exact_physical_line_link(self):
        row = mod.load_manifest(self.manifest())[0]
        self.assertEqual(row["record_locator"], "lines 2-3")
        self.assertEqual(row["record_url"], f"https://github.com/woahwhattheheck/commons/blob/{REF}/evidence/records.csv#L2-L3")
        self.assertEqual(row["locator"], "Q12")
        self.assertEqual(row["original"]["observation"], "First line\nSecond café line")

    def test_record_link_does_not_invent_underlying_document(self):
        row = mod.load_manifest(self.manifest())[0]
        self.assertIsNone(row["underlying_source_url"])
        self.assertEqual(row["provenance"]["underlying_status"], "not_included")
        self.assertTrue(row["provenance"]["local_bytes_verified"])

    def test_extra_native_columns_survive(self):
        text = CSV.replace("evidence_state\n", "evidence_state,review_note\n").replace("interview_only\n", 'interview_only,"=not a formula in JSON"\n')
        row = mod.load_manifest(self.manifest(text))[0]
        self.assertEqual(row["original"]["review_note"], "=not a formula in JSON")

    def test_duplicate_csv_headers_rejected(self):
        text = CSV.replace("evidence_state\n", "evidence_state,evidence_id\n").replace("interview_only\n", "interview_only,E-2\n")
        with self.assertRaisesRegex(mod.SearchError, "header"):
            mod.load_manifest(self.manifest(text))

    def test_malformed_csv_width_rejected(self):
        with self.assertRaisesRegex(mod.SearchError, "column|width"):
            mod.load_manifest(self.manifest(CSV.replace("interview_only\n", "interview_only,extra\n")))

    def test_unreadable_segment_is_not_silently_dropped(self):
        records = mod.load_manifest(self.extraction())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record_type"], "extraction_diagnostic")
        self.assertEqual(records[0]["original_text"], "")
        self.assertIn("OCR_REQUIRED", records[0]["warnings"])
        self.assertTrue(mod.search(mod.build_index(records), "OCR_REQUIRED"))

    def test_document_warning_survives_on_readable_segment(self):
        row = mod.load_manifest(self.extraction(text="Readable fragment"))[0]
        self.assertIn("SOURCE_PARTIAL", row["warnings"])
        self.assertEqual(row["provenance"]["extraction_status"], "partial")

    def test_source_bytes_must_match_declared_upstream_blob(self):
        path = self.extraction(text="Readable fragment")
        (self.root / "source.txt").write_text("different source", encoding="utf-8")
        with self.assertRaisesRegex(mod.SearchError, "digest|blob|SHA"):
            mod.load_manifest(path)

    def test_extraction_json_and_source_have_separate_bindings(self):
        row = mod.load_manifest(self.extraction(text="Readable fragment"))[0]
        self.assertNotEqual(row["provenance"]["local_blob_sha"], row["upstream_blob_sha"])
        self.assertEqual(row["provenance"]["underlying_status"], "verified_source_bytes")

    def test_exact_snippet_preserves_newlines_and_offsets(self):
        rows = mod.load_manifest(self.manifest())
        hit = mod.search(mod.build_index(rows), "café")[0]
        exact = hit["snippet_exact"]
        self.assertEqual(exact["field"], "original_text")
        self.assertEqual(exact["text"], rows[0]["original_text"][exact["start"]:exact["end"]])
        self.assertIn("\n", exact["text"])
        self.assertNotIn("\n", hit["snippet"])

    def test_exact_unicode_casefold_span(self):
        row = mod._base("U-1", "observation", "", "Straße\nLater text", "x.csv", "b" * 40, "row 1", "https://example.test/x")
        row["original_text"] = row["text"]
        exact = mod.search(mod.build_index([row]), "STRASSE")[0]["snippet_exact"]
        self.assertEqual(exact["highlights"], [[0, 6]])

    def test_metadata_match_names_actual_matched_field(self):
        rows = mod.load_manifest(self.manifest())
        exact = mod.search(mod.build_index(rows), "RIS")[0]["snippet_exact"]
        self.assertEqual(exact["field"], "metadata")
        self.assertIn("RIS", exact["text"])

    def test_missing_link_is_diagnostic_not_silently_omitted(self):
        rows = mod.load_manifest(self.manifest())
        rows[0]["linked_ids"] = ["NOT-DELIVERED"]
        hit = mod.search(mod.build_index(rows), "café")[0]
        self.assertEqual(hit["link_diagnostics"], [{"code": "MISSING_LINKED_RECORD", "record_id": "NOT-DELIVERED"}])

    def test_changed_index_is_not_accepted_as_bound(self):
        index = mod.build_index(mod.load_manifest(self.manifest()))
        index["documents"][0]["original_text"] = "changed"
        with self.assertRaisesRegex(mod.SearchError, "digest"):
            mod.search(index, "café")

    def test_invalid_limits_are_not_python_slice_semantics(self):
        index = mod.build_index(mod.load_manifest(self.manifest()))
        for limit in (-1, 0, True, 101):
            with self.subTest(limit=limit), self.assertRaises(mod.SearchError):
                mod.search(index, "café", limit=limit)

    def test_parent_path_is_refused(self):
        path = self.manifest(local_file="../records.csv")
        with self.assertRaisesRegex(mod.SearchError, "path|root"):
            mod.load_manifest(path)

    def test_nonobject_manifest_is_controlled_error(self):
        path = self.root / "manifest.json"
        path.write_text("[]", encoding="utf-8")
        with self.assertRaises(mod.SearchError):
            mod.load_manifest(path)


if __name__ == "__main__":
    unittest.main()
