"""UIOWA-114 reference/export regressions. All examples here are FICTION.

Run from this component: python -m unittest -v test_delivery_integrity
No network, live records, interview scheduling or model calls.
"""
import contextlib
import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import question_cards as q


def fixture():
    """An independent synthetic observation, not a replacement University record."""
    return {
        "templates": {"templates": {"CONFLICT": {
            "requires": ["subject"], "label": "Two sources disagree",
            "question": "Which account of {subject} is supported?",
            "context": "Two retained accounts concern {subject}.",
            "uncertainty_statement": "The accounts of {subject} differ."}},
            "vague_request_phrases": ["any relevant documentation"],
            "leading_phrases": ["why did you fail"],
            "absence_caveat_required_for": []},
        "sources": {"sources": [{"source_id": "SRC-1", "locator": "synthetic://original/entry-1"}]},
        "interviews": {"roles": [{"role_id": "ROLE-1", "title": "Fictional change manager", "session_id": "INT-1"}],
                       "sessions": [{"session_id": "INT-1", "label": "Fictional change review"}]},
        "observations": {"fiction_notice": "FICTION: independent regression example only; no interview or University finding.",
            "observations": [{"observation_id": "OBS-A", "group": "ESS", "assessment_area": "deployment",
                "uncertainty_type": "CONFLICT", "fields": {"subject": "approval entry CR-1"},
                "example_request": "The approval entries for synthetic change CR-1",
                "outcome_map": [
                    {"answer": "Exception record supplied", "resulting_finding": "Documented exception; retain scope"},
                    {"answer": "Record incomplete", "resulting_finding": "Evidence-location gap, not a control gap"}],
                "source_ids": ["SRC-1"], "ask_role": "ROLE-1",
                "decision_informed": "Which account the draft can support", "open_findings": ["F-1"]}]}}


def write_bundle(root, bundle):
    root = Path(root)
    for filename, key in (("templates.json", "templates"), ("sources.json", "sources"),
                          ("interview_register.json", "interviews"), ("observations.json", "observations")):
        (root / filename).write_text(json.dumps(bundle[key], ensure_ascii=False), encoding="utf-8")


class Identity(unittest.TestCase):
    def setUp(self):
        self.bundle = fixture()

    def test_ordinary_observation_reaches_one_question_and_source(self):
        cards, diagnostics, coverage = q.build_cards(self.bundle)
        self.assertEqual(diagnostics, [])
        self.assertEqual(coverage["accounted_for"], 1)
        self.assertEqual(q.CardIndex(cards).search("obs:OBS-A"), cards)
        self.assertEqual(cards[0]["source_locators"], ["synthetic://original/entry-1"])

    def test_duplicate_observations_are_not_counted_then_lost_by_search(self):
        rows = self.bundle["observations"]["observations"]
        rows.append(copy.deepcopy(rows[0]))
        rows[1]["fields"]["subject"] = "a different change CR-2"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ID: observations rows 1 and 2"):
            q.build_cards(self.bundle)

    def test_duplicate_identical_observations_are_still_ambiguous_ids(self):
        rows = self.bundle["observations"]["observations"]
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ID"):
            q.build_cards(self.bundle)

    def test_embedded_namespace_is_not_stripped(self):
        rows = self.bundle["observations"]["observations"]
        rows.append(copy.deepcopy(rows[0])); rows[1]["observation_id"] = "OBS-OBS-A"
        cards, diagnostics, coverage = q.build_cards(self.bundle)
        self.assertEqual(diagnostics, [])
        self.assertEqual({c["card_id"] for c in cards}, {"QC-A", "QC-OBS-A"})
        self.assertEqual(len(q.CardIndex(cards).search("")), 2)
        self.assertEqual(coverage["accounted_for"], 2)
        self.assertEqual(q.CardIndex(cards).search("obs:OBS-OBS-A")[0]["card_id"], "QC-OBS-A")

    def test_derived_id_collision_is_named(self):
        rows = self.bundle["observations"]["observations"]
        rows.append(copy.deepcopy(rows[0])); rows[1]["observation_id"] = "A"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ID: derived card identities"):
            q.build_cards(self.bundle)

    def test_duplicate_source_cannot_switch_cited_locator(self):
        self.bundle["sources"]["sources"].append({"source_id": "SRC-1", "locator": "synthetic://different/entry"})
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ID: sources"):
            q.build_cards(self.bundle)

    def test_duplicate_role_cannot_switch_recipient(self):
        roles = self.bundle["interviews"]["roles"]
        roles.append(dict(roles[0], title="A different fictional role"))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ID: roles"):
            q.build_cards(self.bundle)

    def test_duplicate_session_cannot_switch_label(self):
        sessions = self.bundle["interviews"]["sessions"]
        sessions.append(dict(sessions[0], label="A different fictional sitting"))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ID: sessions"):
            q.build_cards(self.bundle)

    def test_direct_search_index_rejects_duplicate_card_ids(self):
        cards, _, _ = q.build_cards(self.bundle)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ID: search cards"):
            q.CardIndex(cards + copy.deepcopy(cards))

    def test_invalid_identifier_types_are_named(self):
        for invalid in (None, "", "   ", 42, True, ["OBS-A"]):
            with self.subTest(invalid=invalid):
                bundle = copy.deepcopy(self.bundle)
                bundle["observations"]["observations"][0]["observation_id"] = invalid
                with self.assertRaisesRegex(ValueError, "INVALID_ID"):
                    q.build_cards(bundle)

    def test_invalid_register_and_record_shapes_are_named(self):
        for value, code in (({}, "INVALID_REGISTER"), ([None], "INVALID_RECORD")):
            with self.subTest(value=value):
                self.bundle["sources"]["sources"] = value
                with self.assertRaisesRegex(ValueError, code):
                    q.build_cards(self.bundle)

    def test_input_order_does_not_change_card_identity(self):
        rows = self.bundle["observations"]["observations"]
        rows.append(copy.deepcopy(rows[0])); rows[1]["observation_id"] = "OBS-B"
        first = q.build_cards(self.bundle)
        rows.reverse()
        self.assertEqual(q.build_cards(self.bundle), first)

    def test_bundle_is_not_mutated(self):
        before = copy.deepcopy(self.bundle)
        q.build_cards(self.bundle)
        self.assertEqual(self.bundle, before)


class RoutingAndExports(unittest.TestCase):
    def test_absent_session_preserves_role_and_reports_unresolved_route(self):
        bundle = fixture(); bundle["interviews"]["roles"][0]["session_id"] = "INT-MISSING"
        cards, diagnostics, coverage = q.build_cards(bundle)
        self.assertEqual(cards[0]["session_id"], "UNSCHEDULED")
        self.assertEqual(cards[0]["role_title"], "Fictional change manager")
        self.assertEqual(cards[0]["ask_role"], "ROLE-1")
        self.assertEqual(diagnostics[0]["severity"], "WARNING")
        self.assertEqual(diagnostics[0]["code"], "NO_SESSION_FOR_ROLE")
        self.assertIn("INT-MISSING", diagnostics[0]["message"])
        self.assertEqual(coverage["accounted_for"], 1)

    def test_missing_session_value_warns_without_dropping_card(self):
        for missing in (None, "", [], "UNSCHEDULED"):
            with self.subTest(missing=missing):
                bundle = fixture(); bundle["interviews"]["roles"][0]["session_id"] = missing
                cards, diagnostics, _ = q.build_cards(bundle)
                self.assertEqual(cards[0]["session_id"], "UNSCHEDULED")
                self.assertEqual(diagnostics[0]["code"], "NO_SESSION_FOR_ROLE")

    def test_unknown_role_behavior_remains_warning(self):
        bundle = fixture(); bundle["observations"]["observations"][0]["ask_role"] = "ROLE-UNKNOWN"
        cards, diagnostics, _ = q.build_cards(bundle)
        self.assertEqual(cards[0]["session_id"], "UNSCHEDULED")
        self.assertEqual(diagnostics[0]["severity"], "WARNING")

    def test_csv_retains_answer_to_finding_pairs(self):
        cards, _, _ = q.build_cards(fixture())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cards.csv"; q.write_cards_csv(path, cards)
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(json.loads(rows[0]["outcome_map_json"]), cards[0]["outcome_map"])
        self.assertIn("possible_answers", rows[0])
        self.assertEqual(q.CARD_COLUMNS[-1], "outcome_map_json")

    def test_csv_mapping_round_trips_unicode_delimiters_and_literal_prefixes(self):
        cards, _, _ = q.build_cards(fixture())
        cards[0]["outcome_map"] = [
            {"answer": "=literal | x; y\nnext", "resulting_finding": "Cafe\u0301, quoted \"word\"\\N"},
            {"answer": "@literal\tanswer", "resulting_finding": "\u00e9 \u2603; another | result"}]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cards.csv"; q.write_cards_csv(path, cards)
            with path.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
        self.assertEqual(json.loads(row["outcome_map_json"]), cards[0]["outcome_map"])
        self.assertTrue(row["possible_answers"].startswith("'="))

    def test_repeat_exports_are_identical(self):
        cards, _, _ = q.build_cards(fixture())
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a.csv", Path(temp) / "b.csv"
            q.write_cards_csv(a, cards); q.write_cards_csv(b, cards)
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_single_outcome_and_vague_request_rules_remain_active(self):
        for field, value, code in (
                ("outcome_map", [{"answer": "a", "resulting_finding": "one"}], "USELESS_QUESTION"),
                ("example_request", "any relevant documentation", "VAGUE_EXAMPLE_REQUEST"),
                ("source_ids", ["SRC-NOT-THERE"], "UNKNOWN_SOURCE_REF")):
            with self.subTest(code=code):
                bundle = fixture(); bundle["observations"]["observations"][0][field] = value
                cards, diagnostics, coverage = q.build_cards(bundle)
                self.assertEqual(cards, [])
                self.assertEqual(diagnostics[0]["code"], code)
                self.assertEqual(coverage["accounted_for"], 1)


class CommandLine(unittest.TestCase):
    def run_cli(self, bundle, command, *extra):
        with tempfile.TemporaryDirectory() as temp:
            write_bundle(temp, bundle)
            result = subprocess.run(
                [sys.executable, "-O" if sys.flags.optimize else "-B",
                 str(Path(q.__file__)), command, "--data", temp, "--out", str(Path(temp)/"out"), *extra],
                capture_output=True, text=True, check=False, timeout=10)
            files = sorted(str(p.relative_to(temp)) for p in Path(temp).rglob("*") if p.is_file())
            output = {}
            if (Path(temp)/"out").exists():
                output = {p.name:p.read_text(encoding="utf-8") for p in (Path(temp)/"out").iterdir()}
            return result, files, output

    def test_clean_cli_build_check_and_search(self):
        for command in ("build", "check", "search"):
            with self.subTest(command=command):
                result, files, output = self.run_cli(fixture(), command, "--query", "obs:OBS-A")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("accounted_for=1/1", result.stdout)
                if command == "search":
                    self.assertIn("QC-A", result.stdout); self.assertEqual(output, {})
                else:
                    self.assertEqual(set(output), {"cards.json", "cards.csv", "question_cards.md"})
                    self.assertIn("outcome_map_json", output["cards.csv"])

    def test_duplicate_cli_input_has_exit_two_and_no_outputs(self):
        bundle = fixture(); rows=bundle["observations"]["observations"]; rows.append(copy.deepcopy(rows[0]))
        for command in ("build", "check", "search"):
            with self.subTest(command=command):
                result, files, output = self.run_cli(bundle, command)
                self.assertEqual(result.returncode, 2)
                self.assertIn("DUPLICATE_ID", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(output, {})

    def test_search_exposes_rejected_observation_instead_of_false_empty_success(self):
        bundle=fixture(); bundle["observations"]["observations"][0]["source_ids"]=["MISSING"]
        result, files, output = self.run_cli(bundle, "search", "--query", "obs:OBS-A")
        self.assertEqual(result.returncode, 1)
        self.assertIn("UNKNOWN_SOURCE_REF", result.stdout)
        self.assertIn("accounted_for=1/1", result.stdout)
        self.assertIn("0 card(s)", result.stdout)
        self.assertEqual(output, {})

    def test_warning_search_retains_card_and_zero_exit(self):
        bundle=fixture(); bundle["interviews"]["roles"][0]["session_id"]="MISSING"
        result, _, _ = self.run_cli(bundle, "search")
        self.assertEqual(result.returncode, 0)
        self.assertIn("NO_SESSION_FOR_ROLE", result.stdout)
        self.assertIn("UNSCHEDULED", result.stdout)

    def test_no_match_in_valid_register_is_successful_empty_search(self):
        result, _, _ = self.run_cli(fixture(), "search", "--query", "absentword")
        self.assertEqual(result.returncode, 0)
        self.assertIn("0 card(s)", result.stdout)
        self.assertIn("errors=0", result.stdout)

    def test_unknown_search_field_still_returns_two(self):
        result, _, _ = self.run_cli(fixture(), "search", "--query", "colour:blue")
        self.assertEqual(result.returncode, 2)
        self.assertIn("bad query", result.stdout)

    def test_structural_rejection_preserves_existing_output_bytes(self):
        bundle=fixture(); rows=bundle["sources"]["sources"]; rows.append(copy.deepcopy(rows[0]))
        with tempfile.TemporaryDirectory() as temp:
            write_bundle(temp,bundle); out=Path(temp)/"out";out.mkdir(); sent=out/"cards.json";sent.write_bytes(b"prior retained packet")
            with contextlib.redirect_stderr(io.StringIO()):
                result=q.main(["build","--data",temp,"--out",str(out)])
            self.assertEqual(result,2)
            self.assertEqual(sent.read_bytes(),b"prior retained packet")
            self.assertEqual(sorted(p.name for p in out.iterdir()),["cards.json"])

    def test_bad_json_and_missing_file_are_named_input_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            write_bundle(temp,fixture()); p=Path(temp)/"sources.json";p.write_text("{",encoding="utf-8")
            for remove in (False,True):
                if remove:p.unlink()
                stderr=io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result=q.main(["check","--data",temp,"--out",str(Path(temp)/"out")])
                self.assertEqual(result,2)
                self.assertIn("input error",stderr.getvalue())
                self.assertFalse((Path(temp)/"out").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
