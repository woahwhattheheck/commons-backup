"""Lattice's export regressions; every record is fictional and generated here.

Runs actual question_cards.py and its existing classifier/renderers. Only the
explicit filesystem-failure tests inject failures. No network or model calls.
"""
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import question_cards as q
import export_publication as publication


def sample():
    return {
        "templates": {"templates": {"CONFLICT": {
            "requires": ["subject"], "label": "Conflicting accounts",
            "question": "Which record supports {subject}?",
            "context": "Two accounts of {subject} remain unresolved.",
            "uncertainty_statement": "The accounts of {subject} disagree."}},
            "vague_request_phrases": ["any documentation"],
            "leading_phrases": ["why did you fail"], "absence_caveat_required_for": []},
        "sources": {"sources": [{"source_id": "SRC-L1", "locator": "synthetic://lattice/change-1"}]},
        "interviews": {"roles": [{"role_id": "ROLE-L1", "title": "Fictional reviewer", "session_id": "SESSION-L1"}],
                       "sessions": [{"session_id": "SESSION-L1", "label": "Fictional session; not scheduled"}]},
        "observations": {"fiction_notice": "FICTION: Lattice publication test; no University finding or interview.",
            "observations": [{"observation_id": "OBS-L1", "uncertainty_type": "CONFLICT",
                "fields": {"subject": "a fictional change"}, "group": "ESS", "assessment_area": "deployment",
                "example_request": "The approval entry for fictional change L1",
                "outcome_map": [{"answer": "Exception supplied", "resulting_finding": "Retain scoped exception"},
                                {"answer": "Record incomplete", "resulting_finding": "Keep evidence-location question open"}],
                "source_ids": ["SRC-L1"], "ask_role": "ROLE-L1", "open_findings": ["F-L1"],
                "decision_informed": "Which account is supportable"}]}}


def write_input(root, bundle):
    root.mkdir(parents=True, exist_ok=True)
    for name, key in (("templates.json", "templates"), ("sources.json", "sources"),
                      ("interview_register.json", "interviews"), ("observations.json", "observations")):
        (root / name).write_text(json.dumps(bundle[key], ensure_ascii=True), encoding="utf-8")


class ExportPublication(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data, self.out = self.root / "data", self.root / "out"
        self.bundle = sample()
        write_input(self.data, self.bundle)
        self.out.mkdir()
        self.previous = {name: ("PREVIOUS FICTIONAL REVIEW: " + name + "\n").encode()
                         for name in publication.OUTPUT_NAMES}
        for name, value in self.previous.items():
            (self.out / name).write_bytes(value)

    def saved(self):
        return {name: (self.out / name).read_bytes() for name in publication.OUTPUT_NAMES}

    def assert_preserved(self):
        self.assertEqual(self.saved(), self.previous)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), sorted(self.previous))

    def export(self):
        return q.build(str(self.data), str(self.out))

    def cli(self, helper=False, command="build", observations="observations.json"):
        script = Path(publication.__file__ if helper else q.__file__)
        return subprocess.run([sys.executable, "-O" if sys.flags.optimize else "-B",
            str(script), command, "--data", str(self.data), "--out", str(self.out),
            "--observations", observations], capture_output=True, text=True, timeout=10)

    def test_missing_notice_is_input_error_without_erasing_previous_json(self):
        del self.bundle["observations"]["fiction_notice"]
        write_input(self.data, self.bundle)
        with self.assertRaisesRegex(ValueError, "INVALID_BUNDLE"):
            self.export()
        self.assert_preserved()

    def test_missing_notice_cli_preserves_all_reports(self):
        del self.bundle["observations"]["fiction_notice"]
        write_input(self.data, self.bundle)
        result = self.cli()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assert_preserved()

    def test_blank_and_wrong_type_notices_are_rejected(self):
        for notice in (None, "", "  ", [], {}, False, 0):
            with self.subTest(notice=notice):
                self.bundle["observations"]["fiction_notice"] = notice
                write_input(self.data, self.bundle)
                with self.assertRaisesRegex(ValueError, "fiction_notice"):
                    self.export()
                self.assert_preserved()

    def test_null_locator_cannot_publish_mixed_old_and_new_reports(self):
        self.bundle["sources"]["sources"][0]["locator"] = None
        write_input(self.data, self.bundle)
        result = self.cli()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assert_preserved()

    def test_null_answer_cannot_leave_only_csv_header(self):
        self.bundle["observations"]["observations"][0]["outcome_map"][0]["answer"] = None
        write_input(self.data, self.bundle)
        result = self.cli()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assert_preserved()

    def test_invalid_nested_shapes_do_not_touch_existing_outputs(self):
        for field, value in (("outcome_map", [None]), ("fields", None), ("source_ids", [None]),
                             ("open_findings", [None])):
            with self.subTest(field=field):
                bundle = sample(); bundle["observations"]["observations"][0][field] = value
                write_input(self.data, bundle)
                with self.assertRaises(ValueError):
                    self.export()
                self.assert_preserved()

    def test_empty_request_remains_an_observation_diagnostic(self):
        self.bundle["observations"]["observations"][0]["example_request"] = ""
        write_input(self.data, self.bundle)
        result = self.cli(command="check")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads((self.out / "cards.json").read_text(encoding="utf-8"))
        self.assertEqual(report["coverage"]["accounted_for"], 1)
        self.assertEqual(report["cards"], [])
        self.assertEqual(report["diagnostics"][0]["code"], "VAGUE_EXAMPLE_REQUEST")

    def test_package_entrypoint_preserves_script_results(self):
        direct = self.cli(command="check")
        before = self.saved()
        module = "revenue.uiowa_rfq_18649_question_cards.question_cards"
        result = subprocess.run([sys.executable, "-O" if sys.flags.optimize else "-B",
            "-m", module, "check", "--data", str(self.data), "--out", str(self.out)],
            cwd=Path(q.__file__).resolve().parents[2], capture_output=True,
            text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, direct.stdout)
        self.assertEqual(self.saved(), before)

    def test_unencodable_text_rejected_before_output_creation(self):
        self.bundle["observations"]["fiction_notice"] = "FICTION \ud800"
        write_input(self.data, self.bundle)
        with self.assertRaises(ValueError):
            self.export()
        self.assert_preserved()

    def test_csv_renderer_failure_preserves_previous_reports(self):
        with patch.object(q, "write_cards_csv", side_effect=TypeError("injected CSV failure")):
            with self.assertRaisesRegex(ValueError, "injected CSV failure"):
                self.export()
        self.assert_preserved()

    def test_markdown_renderer_failure_preserves_previous_reports(self):
        with patch.object(q, "write_cards_markdown", side_effect=OSError("injected Markdown failure")):
            with self.assertRaisesRegex(OSError, "injected Markdown failure"):
                self.export()
        self.assert_preserved()

    def test_new_output_directory_not_created_on_render_failure(self):
        self.out = self.root / "not-created"
        with patch.object(q, "write_cards_markdown", side_effect=TypeError("injected")):
            with self.assertRaises(ValueError):
                self.export()
        self.assertFalse(self.out.exists())

    def test_staging_failure_does_not_touch_destinations(self):
        real = publication.tempfile.NamedTemporaryFile
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected staging failure")
            return real(*args, **kwargs)
        with patch.object(publication.tempfile, "NamedTemporaryFile", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "injected staging failure"):
                self.export()
        self.assert_preserved()

    def test_first_replacement_failure_preserves_all_and_cleans_staging(self):
        with patch.object(publication.os, "replace", side_effect=OSError("injected replacement failure")):
            with self.assertRaises(OSError):
                self.export()
        self.assert_preserved()

    def test_second_replacement_failure_is_not_claimed_set_atomic(self):
        real = publication.os.replace
        calls = 0
        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second replacement failure")
            return real(source, target)
        with patch.object(publication.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.export()
        after = self.saved()
        self.assertNotEqual(after["cards.json"], self.previous["cards.json"])
        self.assertEqual(after["cards.csv"], self.previous["cards.csv"])
        self.assertEqual(after["question_cards.md"], self.previous["question_cards.md"])
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), sorted(self.previous))

    def test_directory_collision_is_checked_before_any_replacement(self):
        (self.out / "cards.csv").unlink(); (self.out / "cards.csv").mkdir()
        with self.assertRaisesRegex(ValueError, "INVALID_OUTPUT"):
            self.export()
        self.assertEqual((self.out / "cards.json").read_bytes(), self.previous["cards.json"])
        self.assertEqual((self.out / "question_cards.md").read_bytes(), self.previous["question_cards.md"])

    def test_input_output_path_alias_is_refused(self):
        src = self.data / "observations.json"
        original = src.read_bytes(); src.rename(self.data / "cards.json")
        with self.assertRaisesRegex(ValueError, "INPUT_OUTPUT_ALIAS"):
            q.build(str(self.data), str(self.data), "cards.json")
        self.assertEqual((self.data / "cards.json").read_bytes(), original)

    def test_hard_link_to_input_is_refused(self):
        src = self.data / "sources.json"
        original = src.read_bytes(); (self.out / "cards.csv").unlink()
        (self.out / "cards.csv").hardlink_to(src)
        with self.assertRaisesRegex(ValueError, "INPUT_OUTPUT_ALIAS"):
            self.export()
        self.assertEqual(src.read_bytes(), original)
        self.assertEqual((self.out / "cards.json").read_bytes(), self.previous["cards.json"])

    def test_symlink_to_input_is_refused(self):
        src = self.data / "sources.json"
        original = src.read_bytes(); (self.out / "cards.csv").unlink()
        (self.out / "cards.csv").symlink_to(src)
        with self.assertRaisesRegex(ValueError, "INPUT_OUTPUT_ALIAS"):
            self.export()
        self.assertTrue((self.out / "cards.csv").is_symlink())
        self.assertEqual(src.read_bytes(), original)

    def test_valid_source_files_remain_unchanged(self):
        before = {p.name: p.read_bytes() for p in self.data.iterdir()}
        self.export()
        self.assertEqual({p.name: p.read_bytes() for p in self.data.iterdir()}, before)

    def test_valid_renderings_keep_original_renderer_bytes(self):
        cards, diagnostics, coverage = self.export()
        target = self.root / "reference"; target.mkdir()
        q.write_cards_csv(target / "cards.csv", cards)
        q.write_cards_markdown(target / "question_cards.md", cards, coverage, diagnostics)
        self.assertEqual((self.out / "cards.csv").read_bytes(), (target / "cards.csv").read_bytes())
        self.assertEqual((self.out / "question_cards.md").read_bytes(), (target / "question_cards.md").read_bytes())
        expected = {"fiction_notice": self.bundle["observations"]["fiction_notice"],
                    "cards": cards, "diagnostics": diagnostics, "coverage": coverage}
        self.assertEqual((self.out / "cards.json").read_text(), json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

    def test_valid_rebuild_is_byte_identical(self):
        self.export(); before = self.saved(); self.export()
        self.assertEqual(self.saved(), before)

    def test_clean_cli_helper_matches_canonical_cli(self):
        canonical = self.cli(); before = self.saved(); helper = self.cli(helper=True)
        self.assertEqual(canonical.returncode, 0, canonical.stderr)
        self.assertEqual(helper.returncode, 0, helper.stderr)
        self.assertEqual(canonical.stdout, helper.stdout)
        self.assertEqual(self.saved(), before)

    def test_check_retains_observation_error_semantics(self):
        self.bundle["observations"]["observations"][0]["source_ids"] = ["MISSING"]
        write_input(self.data, self.bundle)
        result = self.cli(command="check")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads((self.out / "cards.json").read_text())
        self.assertEqual(report["coverage"]["accounted_for"], 1)
        self.assertEqual(report["diagnostics"][0]["code"], "UNKNOWN_SOURCE_REF")

    def test_unresolved_routing_remains_a_warning_not_a_failure(self):
        self.bundle["interviews"]["roles"][0]["session_id"] = "MISSING"
        write_input(self.data, self.bundle)
        result = self.cli(command="check")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.out / "cards.json").read_text())
        self.assertEqual(report["cards"][0]["session_id"], "UNSCHEDULED")
        self.assertEqual(report["diagnostics"][0]["severity"], "WARNING")

    def test_embedded_identity_and_search_repair_stays_intact(self):
        rows = self.bundle["observations"]["observations"]
        rows.append(copy.deepcopy(rows[0])); rows[1]["observation_id"] = "OBS-OBS-L1"
        write_input(self.data, self.bundle)
        cards, _, coverage = self.export()
        self.assertEqual(coverage["accounted_for"], 2)
        self.assertEqual(q.CardIndex(cards).search("obs:OBS-OBS-L1")[0]["card_id"], "QC-OBS-L1")

    def test_duplicate_id_rejection_preserves_prior_exports(self):
        rows = self.bundle["observations"]["observations"]
        rows.append(copy.deepcopy(rows[0])); write_input(self.data, self.bundle)
        result = self.cli()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("DUPLICATE_ID", result.stderr)
        self.assert_preserved()

    def test_answer_mapping_round_trip_preserves_exact_unicode(self):
        row = self.bundle["observations"]["observations"][0]
        row["outcome_map"][0] = {"answer": "=literal | ; \n", "resulting_finding": "Cafe\u0301 \\N"}
        write_input(self.data, self.bundle)
        cards, _, _ = self.export()
        with (self.out / "cards.csv").open(encoding="utf-8", newline="") as handle:
            record = next(csv.DictReader(handle))
        self.assertEqual(json.loads(record["outcome_map_json"]), cards[0]["outcome_map"])

    def test_unrelated_output_file_is_not_deleted(self):
        (self.out / "reviewer-notes.txt").write_bytes(b"KEEP THIS NOTE")
        self.export()
        self.assertEqual((self.out / "reviewer-notes.txt").read_bytes(), b"KEEP THIS NOTE")

    def test_missing_input_produces_controlled_cli_error(self):
        (self.data / "sources.json").unlink()
        result = self.cli()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assert_preserved()


if __name__ == "__main__":
    unittest.main(verbosity=2)
