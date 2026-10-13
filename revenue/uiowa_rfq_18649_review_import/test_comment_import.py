"""Executed regression cases for CSV staging, identity, provenance and replay."""
import copy
import csv
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("uiowa124_comment_import", ROOT / "comment_import.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def row(**kwargs):
    result = dict(comment_id="C-01", reviewer_role="Practitioner", comment_text="Check this statement.",
                  finding_id="FND-01", report_version="draft-1", finding_namespace="assessment")
    result.update(kwargs)
    return result


def csv_bytes(rows, columns=None, bom=False):
    columns = columns or list(rows[0])
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = stream.getvalue().encode("utf-8")
    return (b"\xef\xbb\xbf" + raw) if bom else raw


def catalog(*extra):
    return {"findings": [dict(finding_id="FND-01", namespace="assessment", report_version="draft-1",
                             locator="report.json#/findings/0", source_label="SYNTHETIC"), *extra]}


def stage(rows, cat=None, prior=None):
    return m.stage_comments(csv_bytes(rows), "review-round-1", "comments.csv", cat or catalog(), prior)


class TestCommentImport(unittest.TestCase):
    def test_multiline_unicode_quotes_crlf_preserved(self):
        text = '  Two lines, "quoted"\r\nRésumé — Δ\n=SUM(A1:A2)  '
        result = stage([row(comment_text=text, extra_note="NA")])
        ready = result["ready"][0]
        self.assertEqual(ready["values"]["comment_text"], text)
        self.assertEqual(ready["values"]["extra_note"], "NA")
        occurrence = ready["occurrences"][0]
        self.assertEqual((occurrence["record_number"], occurrence["line_start"], occurrence["line_end"]), (1, 2, 4))
        self.assertEqual(ready["target"]["source_label"], "SYNTHETIC")

    def test_logical_record_differs_from_physical_line(self):
        result = stage([row(comment_text="a\nb"), row(comment_id="C-02")])
        o = result["ready"][1]["occurrences"][0]
        self.assertEqual((o["record_number"], o["line_start"], o["line_end"]), (2, 4, 4))

    def test_bom_source_hash_is_raw_bytes(self):
        import hashlib
        raw = csv_bytes([row()], bom=True)
        result = m.stage_comments(raw, "s", "export.csv", catalog())
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["source"]["encoding"], "utf-8-sig")
        self.assertEqual(result["summary"]["ready"], 1)

    def test_missing_comment_id_retains_entire_row(self):
        result = stage([row(comment_id="", comment_text="Keep me", owner_notes="Unknown")])
        self.assertEqual(result["summary"]["unkeyed_rows"], 1)
        self.assertEqual(result["unkeyed_rows"][0]["values"]["owner_notes"], "Unknown")
        self.assertEqual(result["summary"]["ready"], 0)

    def test_empty_role_is_explicit(self):
        result = stage([row(reviewer_role="")])
        self.assertEqual(result["unresolved"][0]["diagnostics"], [{"code": "MISSING_VALUE", "field": "reviewer_role"}])

    def test_missing_text_is_not_silently_discarded(self):
        self.assertEqual(stage([row(comment_text=" \n ")])["summary"]["unresolved"], 1)

    def test_unknown_finding_not_guessed(self):
        r = stage([row(finding_id="FND-1")])
        self.assertEqual(r["unresolved"][0]["diagnostics"][0]["code"], "UNKNOWN_FINDING")

    def test_wrong_version_does_not_bind_current(self):
        r = stage([row(report_version="draft-2")])
        self.assertEqual(r["unresolved"][0]["diagnostics"][0]["code"], "VERSION_MISMATCH")

    def test_no_revision_is_unknown(self):
        r = stage([row(report_version="")])
        self.assertEqual(r["summary"]["ready"], 0)

    def test_ambiguous_unqualified_namespace(self):
        extra = dict(finding_id="FND-01", namespace="another", report_version="draft-1")
        r = stage([row(finding_namespace="")], catalog(extra))
        self.assertEqual(r["unresolved"][0]["diagnostics"][0]["code"], "AMBIGUOUS_FINDING")
        self.assertEqual(len(r["unresolved"][0]["diagnostics"][0]["candidates"]), 2)

    def test_namespace_disambiguates_without_joining_lookalikes(self):
        extra = dict(finding_id="FND-01", namespace="another", report_version="draft-1")
        r = stage([row()], catalog(extra))
        self.assertEqual(r["ready"][0]["target"]["namespace"], "assessment")

    def test_duplicate_catalog_candidates_are_not_merged(self):
        r = stage([row()], catalog(catalog()["findings"][0]))
        self.assertEqual(r["summary"]["unresolved"], 1)

    def test_whitespace_reference_requires_explicit_correction(self):
        r = stage([row(finding_id=" FND-01 ")])
        self.assertEqual(r["unresolved"][0]["diagnostics"][0]["code"], "REFERENCE_WHITESPACE")
        self.assertEqual(r["unresolved"][0]["values"]["finding_id"], " FND-01 ")

    def test_same_import_is_byte_deterministic(self):
        a = stage([row()])
        b = stage([row()], prior=a["state"])
        self.assertEqual(m.canonical(a), m.canonical(b))

    def test_input_and_prior_not_mutated(self):
        cat = catalog()
        a = stage([row()], cat)
        snapshot = copy.deepcopy(a)
        saved_cat = copy.deepcopy(cat)
        stage([row(comment_text="Changed")], cat, a["state"])
        self.assertEqual(a, snapshot)
        self.assertEqual(cat, saved_cat)

    def test_identical_duplicate_has_two_source_occurrences(self):
        r = stage([row(), row()])
        self.assertEqual(r["summary"]["ready"], 1)
        self.assertEqual(len(r["ready"][0]["occurrences"]), 2)

    def test_conflicting_duplicate_keeps_both_and_no_ready(self):
        r = stage([row(), row(comment_text="different")])
        self.assertEqual(r["summary"]["ready"], 0)
        self.assertEqual(len(r["unresolved"][0]["variants"]), 2)
        self.assertEqual(r["unresolved"][0]["diagnostics"][0]["code"], "COMMENT_CONTENT_CONFLICT")

    def test_conflicting_reimport_does_not_overwrite(self):
        first = stage([row()])
        second = stage([row(comment_text="revision")], prior=first["state"])
        self.assertEqual(second["summary"]["ready"], 0)
        self.assertEqual(len(second["state"]["comments"][0]["variants"]), 2)
        third = stage([row()], prior=second["state"])
        self.assertEqual(third["summary"]["unresolved"], 1)

    def test_moved_row_keeps_history_without_content_conflict(self):
        first = stage([row()])
        second = stage([row(comment_id="C-00"), row()], prior=first["state"])
        c = next(r for r in second["ready"] if r["comment_id"] == "C-01")
        self.assertEqual(len(c["occurrences"]), 2)
        self.assertEqual({o["record_number"] for o in c["occurrences"]}, {1, 2})

    def test_same_comment_id_different_source_is_not_equivalence(self):
        first = stage([row()])
        r = m.stage_comments(csv_bytes([row(comment_text="different team")]), "other-source", "other.csv", catalog(), first["state"])
        self.assertEqual(r["summary"]["ready"], 2)
        self.assertEqual(len({x["import_key"] for x in r["ready"]}), 2)

    def test_catalog_revision_change_rechecks_preserved_comments(self):
        first = stage([row()])
        r = stage([row()], {"findings": []}, first["state"])
        self.assertEqual(r["summary"]["ready"], 0)
        self.assertEqual(r["summary"]["unresolved"], 1)

    def test_unknown_columns_and_formula_text_remain_in_json(self):
        r = stage([row(review_decision="=1+1", supplied_status="APPROVED", extra="")])
        self.assertEqual(r["ready"][0]["values"]["supplied_status"], "APPROVED")
        self.assertNotIn("decision", r["ready"][0])
        self.assertEqual(json.loads(json.dumps(r))["ready"][0]["values"]["review_decision"], "=1+1")

    def test_duplicate_header_rejected(self):
        with self.assertRaisesRegex(m.ImportFormatError, "duplicate"):
            m.parse_csv(b"comment_id,comment_id\nA,B\n", "s", "x")

    def test_missing_header_column_rejected(self):
        with self.assertRaisesRegex(m.ImportFormatError, "missing columns"):
            m.parse_csv(b"comment_id\nA\n", "s", "x")

    def test_bad_encoding_and_nul_rejected(self):
        for raw in (b"\xff", b"a\x00"):
            with self.subTest(raw=raw), self.assertRaises(m.ImportFormatError):
                m.parse_csv(raw, "s", "x")

    def test_extra_and_missing_cells_rejected(self):
        raw = csv_bytes([row()])
        for bad in (raw + b"a,b\n", raw + b"a,b,c,d,e,f,g\n"):
            with self.subTest(bad=bad), self.assertRaisesRegex(m.ImportFormatError, "columns"):
                m.parse_csv(bad, "s", "x")

    def test_unterminated_quote_rejected(self):
        raw = csv_bytes([row()]).split(b"\r\n")[0] + b'\r\n"oops'
        with self.assertRaisesRegex(m.ImportFormatError, "malformed CSV"):
            m.parse_csv(raw, "s", "x")

    def test_empty_csv_and_bad_source_id_rejected(self):
        for raw, source in ((b"", "s"), (csv_bytes([row()]), " ")):
            with self.subTest(source=source), self.assertRaises(m.ImportFormatError):
                m.parse_csv(raw, source, "x")

    def test_prior_fingerprint_tampering_rejected(self):
        first = stage([row()])
        first["state"]["comments"][0]["variants"][0]["values"]["comment_text"] = "tampered"
        with self.assertRaisesRegex(m.ImportFormatError, "fingerprint"):
            stage([row()], prior=first["state"])

    def test_prior_bad_occurrences_rejected(self):
        for mutation in ({"source_id": "different"}, {"line_start": True}, {"line_end": 0}, {"sha256": "bad"}):
            first = stage([row()])
            first["state"]["comments"][0]["variants"][0]["occurrences"][0].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(m.ImportFormatError):
                stage([row()], prior=first["state"])

    def test_invalid_catalog_rejected(self):
        for bad in ({}, {"findings": ["F-1"]}, {"findings": [{"finding_id": "F-1"}]}):
            with self.subTest(bad=bad), self.assertRaises(m.ImportFormatError):
                stage([row()], bad or {"bad": 1})

    def test_cli_preserves_input_and_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = csv_bytes([row()])
            (root / "in.csv").write_bytes(raw)
            (root / "catalog.json").write_text(json.dumps(catalog()))
            command = [sys.executable, str(ROOT / "comment_import.py"), str(root / "in.csv"),
                       str(root / "catalog.json"), "--source-id", "s", "--out", str(root / "out.json")]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            output = (root / "out.json").read_bytes()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)
            self.assertEqual((root / "out.json").read_bytes(), output)
            self.assertEqual((root / "in.csv").read_bytes(), raw)

    def test_cli_unresolved_is_nonzero_but_output_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "in.csv").write_bytes(csv_bytes([row(finding_id="missing")]))
            (root / "catalog.json").write_text(json.dumps(catalog()))
            command = [sys.executable, str(ROOT / "comment_import.py"), str(root / "in.csv"),
                       str(root / "catalog.json"), "--source-id", "s", "--out", str(root / "out.json")]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertEqual(json.loads((root / "out.json").read_text())["summary"]["unresolved"], 1)

    def test_render_report_handles_unresolved_and_multiline(self):
        result = stage([row(), row(comment_id="C-02", finding_id="missing", comment_text="one\ntwo"), row(comment_id="")])
        report = m.render_report(result)
        self.assertIn("UNKNOWN_FINDING", report)
        self.assertIn("> one\n> two", report)
        self.assertIn("Unkeyed source record 3", report)


if __name__ == "__main__":
    unittest.main()
