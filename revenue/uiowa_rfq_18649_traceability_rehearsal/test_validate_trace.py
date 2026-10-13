"""Hermetic structural regression suite; all case data is synthetic."""
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("_uiowa093_trace_copperr61", HERE / "validate_trace.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
FIXTURES = {
    "evidence.csv": "fe11729edc5ec8c0c6e6adbd6238777118acc16d",
    "findings.csv": "f3dfb204685e72510a4c1bf591e72529702020e9",
    "recommendations.csv": "e81ad1fe6cc691ae8b00d47ab3052fca13e4b047",
    "trace-map.csv": "58feb62c097c7fd39dc18468c60ade50cc069a9a",
    "executive-summary.md": "09df50d32c1e1b562cda87fb1ab527b322e638b8",
    "final-report.md": "de758cbc119c4953984428d989e52ce7f18e95d6",
}


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in FIXTURES:
            shutil.copyfile(HERE / name, self.root / name)

    def result(self):
        return checker.validate(self.root)

    def codes(self):
        return {i["code"] for i in self.result()["issues"]}

    def rewrite(self, name, change):
        path = self.root / name
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            header, rows = reader.fieldnames, list(reader)
        change(rows)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)

    def field(self, name, key, value, index=0):
        self.rewrite(name, lambda rows: rows[index].__setitem__(key, value))

    def replace(self, name, old, new):
        path = self.root / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def run_cli(self, *args, optimized=False, cwd=None, seed="1"):
        command = [sys.executable] + (["-O"] if optimized else [])
        return subprocess.run(command + [str(HERE / "validate_trace.py"), *map(str, args)],
                              cwd=cwd, capture_output=True, text=True, timeout=10,
                              env={**os.environ, "PYTHONHASHSEED": seed})

    def test_native_fixture_passes_unchanged(self):
        result = self.result()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["counts"], dict(evidence=8, findings=3, recommendations=2, statements=5))
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["report_lines"], 50)

    def test_fixture_custody_is_provider_byte_exact(self):
        for name, expected in FIXTURES.items():
            with self.subTest(name=name):
                raw = (HERE / name).read_bytes()
                self.assertEqual(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(), expected)

    def test_validator_does_not_modify_inputs(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.result()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_no_argument_cli_is_cwd_independent(self):
        result = self.run_cli(cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "evidence=8 findings=3 recommendations=2 statements=5\ntrace validation: PASS\n")

    def test_json_cli_and_direct_api_agree(self):
        result = self.run_cli(self.root, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.result())

    def test_cli_help_has_no_assessment_side_effect(self):
        result = self.run_cli("--help", cwd=self.root)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--json", result.stdout)
        self.assertNotIn("trace validation: PASS", result.stdout)

    def test_missing_input_is_invalid_not_green(self):
        (self.root / "evidence.csv").unlink()
        result = self.run_cli(self.root, "--json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "INVALID_INPUT")
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_report_is_invalid(self):
        (self.root / "final-report.md").unlink()
        self.assertEqual(self.result()["status"], "INVALID_INPUT")

    def test_non_utf8_input_is_invalid(self):
        (self.root / "findings.csv").write_bytes(b"\xff")
        self.assertEqual(self.result()["status"], "INVALID_INPUT")

    def test_non_utf8_report_is_invalid(self):
        (self.root / "final-report.md").write_bytes(b"\xff")
        self.assertEqual(self.result()["status"], "INVALID_INPUT")

    def test_empty_file_is_invalid(self):
        (self.root / "evidence.csv").write_text("")
        self.assertIn("CSV_HEADER", self.codes())

    def test_empty_tables_cannot_vacuously_pass(self):
        for name in FIXTURES:
            if name.endswith(".csv"):
                self.rewrite(name, lambda rows: rows.clear())
            else:
                (self.root / name).write_text("")
        self.assertEqual(self.result()["status"], "INCOMPLETE")
        self.assertIn("NO_RECORDS", self.codes())

    def test_duplicate_id_in_each_table_is_invalid(self):
        for name, key, fields in checker.TABLES:
            with self.subTest(name=name):
                original = (self.root / name).read_bytes()
                self.rewrite(name, lambda rows: rows.append(dict(rows[0])))
                self.assertIn("DUPLICATE_ID", self.codes())
                self.assertEqual(self.result()["status"], "INVALID_INPUT")
                (self.root / name).write_bytes(original)

    def test_blank_identifier_is_invalid(self):
        self.field("findings.csv", "finding_id", "")
        self.assertIn("INVALID_ID", self.codes())

    def test_identifier_whitespace_is_not_silently_normalised(self):
        self.field("evidence.csv", "evidence_id", " E-001 ")
        self.assertIn("INVALID_ID", self.codes())

    def test_repeated_header_is_invalid(self):
        self.replace("evidence.csv", "source_name,locator", "locator,locator")
        self.assertIn("CSV_HEADER", self.codes())

    def test_missing_header_is_invalid(self):
        self.replace("findings.csv", "evidence_ids,confidence", "other,confidence")
        self.assertIn("CSV_HEADER", self.codes())

    def test_blank_header_is_invalid(self):
        self.replace("evidence.csv", "service,source_type", ",source_type")
        self.assertIn("CSV_HEADER", self.codes())

    def test_extra_csv_cell_is_invalid(self):
        self.replace("evidence.csv", "evidence_state\n", "evidence_state\nE-999,x,x,x,x,x,x,extra\n")
        self.assertIn("CSV_WIDTH", self.codes())

    def test_short_csv_row_is_invalid(self):
        self.replace("evidence.csv", "evidence_state\n", "evidence_state\nE-999,x\n")
        self.assertIn("CSV_WIDTH", self.codes())

    def test_unterminated_csv_quote_is_invalid(self):
        with (self.root / "evidence.csv").open("a") as stream:
            stream.write('"unterminated')
        self.assertEqual(self.result()["status"], "INVALID_INPUT")

    def test_bom_and_crlf_are_accepted(self):
        for name in FIXTURES:
            path = self.root / name
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.result()["status"], "PASS")

    def test_csv_extensions_are_not_rejected(self):
        path = self.root / "recommendations.csv"
        lines = path.read_text().splitlines()
        path.write_text("\n".join([lines[0] + ",extension"] + [line + ",retained" for line in lines[1:]]) + "\n")
        self.assertEqual(self.result()["status"], "PASS")

    def test_missing_evidence_locator_is_a_gap(self):
        self.field("evidence.csv", "locator", " ")
        self.assertIn("MISSING_LOCATOR", self.codes())
        self.assertEqual(self.result()["status"], "INCOMPLETE")

    def test_finding_requires_evidence(self):
        self.field("findings.csv", "evidence_ids", "")
        self.assertIn("MISSING_LINK", self.codes())

    def test_recommendation_requires_finding(self):
        self.field("recommendations.csv", "linked_findings", "")
        self.assertIn("MISSING_LINK", self.codes())

    def test_statement_requires_finding(self):
        self.field("trace-map.csv", "finding_ids", "")
        self.assertIn("MISSING_LINK", self.codes())

    def test_statement_requires_evidence(self):
        self.field("trace-map.csv", "evidence_ids", "")
        self.assertIn("MISSING_LINK", self.codes())

    def test_all_five_link_columns_detect_missing_targets(self):
        cases = [("findings.csv", "evidence_ids"), ("recommendations.csv", "linked_findings"),
                 ("trace-map.csv", "finding_ids"), ("trace-map.csv", "recommendation_ids"),
                 ("trace-map.csv", "evidence_ids")]
        for name, field in cases:
            with self.subTest(name=name, field=field):
                raw = (self.root / name).read_bytes()
                self.field(name, field, "UNKNOWN-ID")
                self.assertIn("BROKEN_LINK", self.codes())
                (self.root / name).write_bytes(raw)

    def test_link_separators_are_compatible(self):
        self.field("findings.csv", "evidence_ids", " E-001 , E-002 ; E-003 ; ")
        self.assertEqual(self.result()["status"], "PASS")

    def test_existing_but_disconnected_evidence_is_not_traceability(self):
        self.field("trace-map.csv", "evidence_ids", "E-007")
        self.assertIn("DISCONNECTED_EVIDENCE", self.codes())

    def test_existing_but_disconnected_recommendation_is_not_traceability(self):
        self.field("trace-map.csv", "recommendation_ids", "R-002", index=1)
        self.assertIn("DISCONNECTED_RECOMMENDATION", self.codes())

    def test_a_recommendation_can_span_multiple_findings(self):
        self.field("recommendations.csv", "linked_findings", "F-002;F-003")
        self.assertEqual(self.result()["status"], "PASS")

    def test_a_statement_can_cite_a_subset_of_finding_evidence(self):
        self.field("findings.csv", "evidence_ids", "E-001;E-002;E-003;E-004")
        self.assertEqual(self.result()["status"], "PASS")

    def test_prefix_occurrence_cannot_replace_a_statement(self):
        self.replace("executive-summary.md", "**S-001.**", "**S-0019.**")
        self.assertIn("MISSING_STATEMENT", self.codes())
        self.assertIn("UNMAPPED_STATEMENT", self.codes())

    def test_plain_prose_mention_is_not_a_declaration(self):
        self.replace("executive-summary.md", "**S-001.**", "S-001 is mentioned here:")
        self.assertIn("MISSING_STATEMENT", self.codes())

    def test_code_fence_example_is_not_a_declaration(self):
        self.replace("executive-summary.md", "**S-001.**", "```text\n**S-001.**")
        self.replace("executive-summary.md", "The statement is intentionally narrow:", "```\n\nThe statement is intentionally narrow:")
        self.assertIn("MISSING_STATEMENT", self.codes())

    def test_comment_example_is_not_a_declaration(self):
        self.replace("executive-summary.md", "**S-001.**", "<!-- **S-001.**")
        self.replace("executive-summary.md", "The statement is intentionally narrow:", "-->\n\nThe statement is intentionally narrow:")
        self.assertIn("MISSING_STATEMENT", self.codes())

    def test_comment_text_inside_fences_cannot_hide_later_real_statements(self):
        path = self.root / "executive-summary.md"
        path.write_text("```text\n<!--\n```\n\n" + path.read_text())
        self.assertEqual(self.result()["status"], "PASS")

    def test_wrong_section_is_reported(self):
        self.field("trace-map.csv", "report_location", "executive-summary.md#material-gap")
        self.assertIn("WRONG_LOCATION", self.codes())

    def test_wrong_report_is_reported(self):
        self.field("trace-map.csv", "report_location", "final-report.md#supported-strength")
        self.assertIn("WRONG_LOCATION", self.codes())

    def test_duplicate_statement_is_reported(self):
        path = self.root / "executive-summary.md"
        path.write_text(path.read_text() + "\n**S-001.** Duplicate. [F:F-001] [E:E-001,E-002,E-003]\n")
        self.assertIn("DUPLICATE_STATEMENT", self.codes())

    def test_unknown_statement_is_reported(self):
        path = self.root / "final-report.md"
        path.write_text(path.read_text() + "\n**S-999.** Unmapped claim.\n")
        self.assertIn("UNMAPPED_STATEMENT", self.codes())

    def test_citation_mismatch_names_missing_and_extra_ids(self):
        self.replace("executive-summary.md", "[F:F-001]", "[F:F-003]")
        result = self.result()
        issues = [i for i in result["issues"] if i["code"] == "CITATION_MISMATCH"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["detail"], "missing=F-001; extra=F-003")

    def test_missing_citation_is_reported(self):
        self.replace("executive-summary.md", "[E:E-001,E-002,E-003]", "")
        self.assertIn("CITATION_MISMATCH", self.codes())

    def test_extra_citation_is_reported(self):
        self.replace("executive-summary.md", "[E:E-001,E-002,E-003]", "[E:E-001,E-002,E-003,E-004]")
        self.assertIn("CITATION_MISMATCH", self.codes())

    def test_inline_recommendation_is_a_real_citation(self):
        self.replace("final-report.md", "S-004 / R-001", "S-004 / R-002")
        self.assertIn("CITATION_MISMATCH", self.codes())

    def test_multiline_statement_paragraph_is_supported(self):
        self.replace("executive-summary.md", "**S-001.** The", "**S-001.**\nThe")
        self.replace("executive-summary.md", "[F:F-001] [E:E-001,E-002,E-003]", "[F:F-001]\n[E:E-001,E-002,E-003]")
        self.assertEqual(self.result()["status"], "PASS")

    def test_citations_in_later_paragraph_do_not_launder_a_statement(self):
        self.replace("executive-summary.md", "[F:F-001] [E:E-001,E-002,E-003]", "\n\n[F:F-001] [E:E-001,E-002,E-003]")
        self.assertIn("CITATION_MISMATCH", self.codes())

    def test_duplicate_heading_slug_is_disambiguated(self):
        self.replace("final-report.md", "### Recommendation 1", "### Recommendation 1\n\n### Recommendation 1")
        self.field("trace-map.csv", "report_location", "final-report.md#recommendation-1-1", index=3)
        self.assertEqual(self.result()["status"], "PASS")

    def test_no_whole_report_read_is_needed(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("whole-file read")):
            self.assertEqual(self.result()["status"], "PASS")

    def test_each_input_is_opened_once(self):
        original, calls = Path.open, []
        def opened(path, *args, **kwargs):
            calls.append(path.name)
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", opened):
            self.assertEqual(self.result()["status"], "PASS")
        self.assertCountEqual(calls, list(FIXTURES))

    def test_unknown_evidence_state_is_not_promoted(self):
        self.field("evidence.csv", "evidence_state", "unknown")
        before = (self.root / "evidence.csv").read_bytes()
        result = self.result()
        self.assertEqual(result["scope"], "STRUCTURAL_ONLY_NOT_EVIDENCE_AUTHENTICATION")
        self.assertEqual(before, (self.root / "evidence.csv").read_bytes())

    def test_empty_report_is_incomplete(self):
        (self.root / "executive-summary.md").write_text("")
        self.assertIn("MISSING_STATEMENT", self.codes())
        self.assertEqual(self.result()["status"], "INCOMPLETE")

    def test_json_diagnostics_are_seed_path_and_optimization_independent(self):
        self.field("findings.csv", "evidence_ids", "E-Z;E-Y;E-X")
        first = self.run_cli(self.root, "--json", seed="1")
        second = self.run_cli(self.root, "--json", seed="927", optimized=True)
        with tempfile.TemporaryDirectory() as other:
            target = Path(other) / "different-root"
            shutil.copytree(self.root, target)
            third = self.run_cli(target, "--json", seed="332")
        self.assertEqual([first.returncode, second.returncode, third.returncode], [1, 1, 1])
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stdout, third.stdout)
        self.assertNotIn(str(self.root), first.stdout)

    def test_text_error_mode_returns_one_without_traceback(self):
        self.field("evidence.csv", "locator", "")
        result = self.run_cli(self.root, optimized=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("MISSING_LOCATOR", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_legacy_helpers_remain_available(self):
        self.assertEqual(len(checker.load(self.root / "evidence.csv")), 8)
        self.assertEqual(checker.split_ids(" E-1;E-2,E-1 "), {"E-1", "E-2"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(checker.main(self.root), 0)
        self.assertIn("trace validation: PASS", out.getvalue())


if __name__ == "__main__":
    unittest.main()
