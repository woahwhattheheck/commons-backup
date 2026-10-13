"""Executable classification, dependency, output and existing-component contracts."""
import copy
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

m = load_module("uiowa120_under_test", HERE / "source_impact.py")
r = load_module("uiowa120_rehearsal_under_test", HERE / "rehearse.py")

class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.g = r.synthetic_case()

    def report(self):
        return m.analyze(self.a, self.b, self.g)

    def row(self, sid, report=None):
        return next(x for x in (report or self.report())["source_changes"] if x["source_id"] == sid)

    def node(self, nid, report=None):
        return next(x for x in (report or self.report())["artifacts"] if x["artifact_id"] == nid)

    def test_scope_binding_required_for_complete_dependency_interpretation(self):
        del self.g["scope"]
        report = self.report()
        self.assertIn("unbound_dependency_scope", [d["code"] for d in report["diagnostics"]])
        self.assertTrue(all(a["mapping_incomplete"] for a in report["artifacts"]))

    def test_wrong_graph_scope_refused(self):
        self.g["scope"]["purpose"] = "another engagement"
        with self.assertRaisesRegex(m.InputError, "dependency scope"):
            self.report()

    def test_text_preview_and_truncation_explicit(self):
        change = self.row("POLICY")["text_change"]
        self.assertIn("urgent exceptions", change["after_preview"])
        self.assertFalse(change["truncated"])
        self.b["sources"][0]["text"] = "a" * 3000
        change = self.row("POLICY")["text_change"]
        self.assertTrue(change["truncated"])
        self.assertEqual(len(change["after_preview"]), 2048)

    def test_digest_change_does_not_invent_text_preview(self):
        self.assertIsNone(self.row("DIGEST")["text_change"])

    def test_frozen_inputs_and_receipts_match_generator(self):
        for filename, generated in zip(("before.json", "after.json", "dependencies.json"), (self.a, self.b, self.g)):
            self.assertEqual(m.load_json(HERE / "fixtures" / filename), generated)
        receipt = m.load_json(HERE / "examples" / "receipt.json")
        self.assertEqual(m.digest(self.report()), receipt["synthetic"]["report_sha256"])
        self.assertEqual(m.render_markdown(self.report()), (HERE / "examples" / "report.md").read_text(encoding="utf-8"))

    def test_all_eight_classifications(self):
        self.assertEqual(self.report()["counts"], {"text_changed": 1, "metadata_only": 1,
            "comparison_unavailable": 1, "unchanged": 1, "removed": 1, "added": 1,
            "interpretation_changed": 1, "content_changed": 1})

    def test_transitive_exact_witness(self):
        causes = self.node("narrative")["causes"]
        self.assertEqual(next(x for x in causes if x["source_id"] == "POLICY")["path"],
            ["source:POLICY", "artifact:worksheet", "artifact:mapping", "artifact:narrative"])
        self.assertEqual(len(causes), 5)

    def test_actions_differ_and_unknown_propagates(self):
        self.assertEqual(self.node("locator-index")["action"], "review_metadata_and_locators")
        self.assertEqual(self.node("glossary")["action"], "no_detected_change_in_declared_dependencies")
        self.assertEqual(self.node("narrative")["action"], "resolve_comparison_or_mapping")
        self.assertEqual(self.node("inventory")["action"], "review_content_and_interpretation")

    def test_claim_is_not_source_text(self):
        row = self.row("RATING")
        self.assertEqual(row["change_type"], "interpretation_changed")
        self.assertEqual(row["text_comparison"], "equal")
        self.assertEqual(self.row("DIGEST")["text_comparison"], "unavailable")

    def test_missing_text_never_means_unchanged(self):
        self.b = copy.deepcopy(self.a)
        self.assertEqual(self.row("INTERVIEW")["change_type"], "comparison_unavailable")
        self.assertEqual(self.report()["status"], "INCOMPLETE")

    def test_unavailable_preserves_metadata_delta(self):
        self.assertIn("review_note", self.row("INTERVIEW")["metadata_changes"])

    def test_partial_after_does_not_infer_removal(self):
        self.b["coverage"] = "partial"
        self.assertEqual(self.row("RETIRED")["change_type"], "comparison_unavailable")

    def test_partial_before_does_not_infer_addition(self):
        self.a["coverage"] = "partial"
        self.assertEqual(self.row("NEW")["change_type"], "comparison_unavailable")

    def test_namespace_collision_refused(self):
        self.b["namespace"] = "different-origin"
        with self.assertRaisesRegex(m.InputError, "namespace"):
            self.report()

    def test_scope_collision_refused(self):
        self.b["scope"]["purpose"] = "different engagement"
        with self.assertRaisesRegex(m.InputError, "scope"):
            self.report()

    def test_duplicate_ids_refused(self):
        self.a["sources"].append(copy.deepcopy(self.a["sources"][0]))
        with self.assertRaisesRegex(m.InputError, "duplicate source"):
            self.report()

    def test_wrong_digest_refused(self):
        self.a["sources"][0]["content"] = {"representation": m.TEXT_REP, "sha256": "0" * 64}
        with self.assertRaisesRegex(m.InputError, "text/digest conflict"):
            self.report()

    def test_changed_representation_not_false_diff(self):
        self.b["sources"][-2]["content"]["representation"] = "different-extraction/v2"
        self.assertEqual(self.row("DIGEST")["change_type"], "comparison_unavailable")

    def test_revision_cannot_be_shadowed_by_metadata(self):
        left = next(x for x in self.a["sources"] if x["id"] == "STABLE")
        right = next(x for x in self.b["sources"] if x["id"] == "STABLE")
        left["metadata"]["revision"] = right["metadata"]["revision"] = "same metadata label"
        right["revision"] = "r2"
        self.assertEqual(self.row("STABLE")["change_type"], "metadata_only")
        self.assertTrue(self.row("STABLE")["revision_changed"])
        self.assertEqual(self.row("STABLE")["metadata_changes"], {})

    def test_missing_null_false_zero_preserved(self):
        right = next(x for x in self.b["sources"] if x["id"] == "STABLE")
        left = next(x for x in self.a["sources"] if x["id"] == "STABLE")
        left["metadata"]["value"] = False
        right["metadata"].update(value=0, nullable=None)
        delta = self.row("STABLE")["metadata_changes"]
        self.assertEqual(set(delta), {"value", "nullable"})
        self.assertFalse(delta["nullable"]["before"]["present"])
        self.assertTrue(delta["nullable"]["after"]["present"])

    def test_exact_text_handles_empty_unicode_and_newlines(self):
        left = next(x for x in self.a["sources"] if x["id"] == "STABLE")
        right = next(x for x in self.b["sources"] if x["id"] == "STABLE")
        for before, after in [("", "\n"), ("é", "e\u0301"), ("a\r\n", "a\n")]:
            with self.subTest(before=before):
                left["text"], right["text"] = before, after
                self.assertEqual(self.row("STABLE")["change_type"], "text_changed")

    def test_capture_time_requires_offset_and_correct_order(self):
        for stamp in ["2026-09-19T13:00:00", "not a timestamp", "2026-09-17T13:00:00Z"]:
            with self.subTest(stamp=stamp):
                self.b["captured_at"] = stamp
                with self.assertRaises(m.InputError):
                    self.report()

    def test_mixed_offsets_compare_as_instants(self):
        self.b["captured_at"] = "2026-09-18T09:00:00-04:00"
        self.report()

    def test_missing_dependency_taints_descendants(self):
        self.g["artifacts"][0]["depends_on"].append({"artifact_id": "lost"})
        report = self.report()
        self.assertTrue(self.node("narrative", report)["mapping_incomplete"])
        self.assertFalse(self.node("glossary", report)["mapping_incomplete"])
        self.assertIn("unknown_artifact_reference", [d["code"] for d in report["diagnostics"]])

    def test_missing_source_reference_visible(self):
        self.g["artifacts"][0]["depends_on"].append({"source_id": "absent"})
        self.assertIn("unknown_source_reference", [d["code"] for d in self.report()["diagnostics"]])

    def test_cycle_witness_and_termination(self):
        self.g["artifacts"][0]["depends_on"].append({"artifact_id": "narrative"})
        report = self.report()
        cycle = next(d["path"] for d in report["diagnostics"] if d["code"] == "dependency_cycle")
        self.assertEqual(cycle[0], cycle[-1])
        self.assertEqual(set(cycle), {"worksheet", "mapping", "narrative"})
        self.assertTrue(self.node("narrative", report)["mapping_incomplete"])

    def test_shortest_shared_path_is_not_double_counted(self):
        self.g["artifacts"][2]["depends_on"].append({"source_id": "POLICY"})
        causes = [c for c in self.node("narrative")["causes"] if c["source_id"] == "POLICY"]
        self.assertEqual(len(causes), 1)
        self.assertEqual(causes[0]["path"], ["source:POLICY", "artifact:narrative"])

    def test_typed_source_and_artifact_identifiers(self):
        self.g["artifacts"].append(r.artifact("POLICY", "worksheet", [{"source_id": "POLICY"}]))
        self.assertEqual(self.node("POLICY")["causes"][0]["path"], ["source:POLICY", "artifact:POLICY"])

    def test_partial_graph_explicit(self):
        self.g["coverage"] = "partial"
        self.assertIn("partial_dependency_coverage", [d["code"] for d in self.report()["diagnostics"]])

    def test_readonly_and_deterministic(self):
        original = m.canonical([self.a, self.b, self.g])
        report = self.report()
        self.assertEqual(m.canonical(report), m.canonical(self.report()))
        self.assertEqual(original, m.canonical([self.a, self.b, self.g]))
        report["scope"]["synthetic"] = False
        self.assertTrue(self.a["scope"]["synthetic"])

    def test_no_detected_change_not_validated_assessment(self):
        self.a["sources"] = [s for s in self.a["sources"] if s["id"] == "STABLE"]
        self.b = copy.deepcopy(self.a)
        self.g["artifacts"] = [self.g["artifacts"][-1]]
        self.assertEqual(self.report()["status"], "NO_DETECTED_CHANGE")
        self.assertIn("No findings", self.report()["notice"])

    def test_html_escapes_content_and_resolves_anchors(self):
        self.g["artifacts"][0]["locator"] = '<script>alert("fiction")</script>'
        document = m.render_html(self.report())
        self.assertNotIn("<script>", document)
        self.assertIn("&lt;script&gt;", document)
        class Links(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids = set(); self.links = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if "id" in attrs: self.ids.add(attrs["id"])
                if tag == "a": self.links.append(attrs["href"])
        links = Links(); links.feed(document)
        self.assertTrue(links.links)
        self.assertTrue(all(x.startswith("#") and x[1:] in links.ids for x in links.links))

    def test_csv_neutralizes_formulas_without_changing_json(self):
        self.g["artifacts"][0]["locator"] = ' =SUM(1,2)'
        report = self.report()
        rows = list(csv.DictReader(io.StringIO(m.render_csv(report))))
        self.assertTrue(next(x for x in rows if x["artifact_id"] == "worksheet")["locator"].startswith("'"))
        self.assertEqual(self.node("worksheet", report)["locator"], ' =SUM(1,2)')

    def test_existing_outputs_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "report"
            m.write_report(self.report(), out)
            prior = {p.name: p.read_bytes() for p in out.iterdir()}
            with self.assertRaises(FileExistsError): m.write_report(self.report(), out)
            self.assertEqual(prior, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_strict_json_rejects_duplicates_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "bad.json"
            for value in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
                path.write_text(value)
                with self.assertRaises(m.InputError): m.load_json(path)

    def test_bounded_json_input(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "large.json"
            path.write_bytes(b" " * (m.LIMIT + 1))
            with self.assertRaisesRegex(m.InputError, "exceeds"): m.load_json(path)

    def test_malformed_graph_reference_refused(self):
        for ref in ["POLICY", {}, {"source_id": "POLICY", "artifact_id": "worksheet"}]:
            with self.subTest(ref=ref):
                self.g["artifacts"][0]["depends_on"] = [ref]
                with self.assertRaises(m.InputError): self.report()

    def test_unmapped_changed_source_preserved(self):
        self.g["artifacts"] = []
        self.assertEqual(len(self.report()["unmapped_changed_sources"]), 7)

    def test_existing_authority_roundtrip_fields_and_actual_mutation(self):
        before, after, graph = r.authority_case()
        bundle = m.load_json(r.AUTHORITY)
        self.assertEqual(len(before["sources"]), 12)
        for source, original in zip(before["sources"], bundle["sources"]):
            reconstructed = {**source["metadata"], **source["interpretation"],
                "source_id": source["id"], "authority_generation": source["revision"],
                "source_content_sha256": source["content"]["sha256"]}
            self.assertEqual(reconstructed, original)
            self.assertNotIn("text", source)
        report = m.analyze(before, after, graph)
        self.assertEqual(report["counts"], {"unchanged":9, "content_changed":1, "metadata_only":1, "interpretation_changed":1})
        self.assertEqual(report["status"], "INCOMPLETE")  # dependency survey intentionally partial
        self.assertTrue(all(x["text_comparison"] == "unavailable" for x in report["source_changes"]))

    def test_authority_source_transplant_refused(self):
        bundle = m.load_json(r.AUTHORITY)
        bundle["sources"][0]["prime_candidate"] = "Other scope"
        with self.assertRaisesRegex(m.InputError, "mismatch"):
            m.adapt_authority(bundle, "test", "2026-09-19T13:00:00Z", coverage="complete")

    def test_authority_extensions_retained(self):
        bundle = m.load_json(r.AUTHORITY)
        bundle["sources"][0]["future_extension"] = {"null": None, "items": ["α", 0]}
        result = m.adapt_authority(bundle, "test", "2026-09-19T13:00:00Z", coverage="partial")
        self.assertEqual(result["sources"][0]["metadata"]["future_extension"], bundle["sources"][0]["future_extension"])

    def test_full_cli_and_frozen_fixture_replay(self):
        with tempfile.TemporaryDirectory() as root:
            generated = Path(root) / "rehearsal"
            receipt = r.run(generated)
            args = [sys.executable, str(HERE / "source_impact.py"), "compare"]
            args += [str(generated / "synthetic" / n) for n in ("before.json", "after.json", "dependencies.json")]
            out = Path(root) / "cli"
            result = subprocess.run(args + ["--out-dir", str(out)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)  # generated valid report explicitly INCOMPLETE
            self.assertEqual(m.digest(m.load_json(out / "report.json")), receipt["synthetic"]["report_sha256"])
            self.assertFalse(result.stderr)
            again = subprocess.run(args + ["--out-dir", str(out)], capture_output=True, text=True, timeout=10)
            self.assertEqual(again.returncode, 2)
            self.assertIn("INPUT_OR_OUTPUT_ERROR", again.stderr)

if __name__ == "__main__":
    unittest.main()
