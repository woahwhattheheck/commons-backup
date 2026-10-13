"""Native adapter acceptance against the actual canonical mapper; no provider I/O."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import runpy
import unittest

if __package__:
    from . import adapter as a
    from . import replay
else:
    def _sibling(name):
        path = Path(__file__).resolve().with_name(name + ".py")
        spec = importlib.util.spec_from_file_location("_uiowa_workshare_test_" + name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load test dependency " + name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    a, replay = _sibling("adapter"), _sibling("replay")

HERE = Path(__file__).resolve().parent


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapper = a.load_mapper()
        cls.native = a.load_json(replay.PARENT_FIXTURE.read_text(encoding="utf-8"))

    def setUp(self):
        self.authority = a.adapt_authority(self.native, namespace="demo/workshare", locator=replay.PARENT_LOCATOR, synthetic=True)
        self.handoff_document = replay.handoff_fixture()
        self.handoff = a.adapt_handoff(self.handoff_document, namespace="demo/workbench", locator=replay.HANDOFF_LOCATOR)

    def request(self, **changes):
        kwargs = dict(source_id="ESS-SW-01", group="ESS", dimension="software_development",
            expected_receipt=self.handoff_document["report_receipt_sha256"], expected_generation=self.native["generation"],
            expected_handoff_revision=self.handoff["adapter"]["revision"], expected_authority_revision=self.authority["adapter"]["revision"],
            request_id="review-1", rationale="Explicit synthetic request; not a support claim")
        kwargs.update(changes)
        return a.review_request(self.authority, self.handoff, **kwargs)

    def test_native_fixture_exact_readback(self):
        raw = replay.PARENT_FIXTURE.read_bytes()
        # This receipt is deliberately pinned to the actually tested fixture bytes.
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        self.assertEqual(blob, "1d58638c067b35dbdc210365ac3f30d6e72c9548")
        self.assertEqual(len(self.native["sources"]), 12)

    def test_actual_mapper_baseline(self):
        report = self.mapper.reconcile(a.combine([self.authority, self.handoff], [self.request()]))
        self.assertEqual(report["summary"], {"input_records": 26, "occurrences": 26, "collisions": 0, "links": 25, "unresolved_links": 0})
        self.assertFalse(report["assessment_authority"])
        link = next(row for row in report["links"] if row["link_id"] == "review-1")
        self.assertEqual(link["original"]["relation"], "analyst_requests_review_of")
        self.assertEqual(link["status"], "resolved")

    def test_original_authority_rows_and_document_survive(self):
        self.assertEqual(self.authority["adapter"]["original_document"], self.native)
        rows = self.authority["records"][1:]
        self.assertEqual([row["payload"] for row in rows], self.native["sources"])
        self.assertEqual([row["id"] for row in rows], [row["source_id"] for row in self.native["sources"]])
        self.assertEqual(rows[0]["payload"]["dimension"], "software")
        self.assertEqual(rows[0]["source_locators"], [replay.PARENT_LOCATOR + "#/sources/0"])
        self.assertEqual(rows[0]["source_semantics"], "AUTHORITY_BUNDLE_ROW_NOT_FETCHED_UNDERLYING_DOCUMENT")

    def test_handoff_notes_are_not_findings_or_services(self):
        self.assertEqual({r["kind"] for r in self.handoff["records"]}, {"source", "observation"})
        self.assertNotIn("service", {r["kind"] for r in self.authority["records"]})
        note = self.handoff["records"][1]
        self.assertEqual(note["payload"]["dimension"], "software_development")
        self.assertEqual(note["evidence_class"], "ANALYST_STATEMENT_NOT_VERIFIED_OBSERVATION")
        self.assertEqual(note["bound_report_receipt_sha256"], "d" * 64)
        self.assertEqual(self.handoff["adapter"]["original_document"], self.handoff_document)

    def test_changed_note_same_receipt_changes_occurrence_not_entity(self):
        outputs = replay.run(self.native, self.mapper)
        summary = outputs["summary.json"]
        for field in ("compiler_receipt_unchanged", "handoff_revision_changed", "changed_note_entity_id_stable", "changed_note_occurrence_id_changed"):
            self.assertTrue(summary[field], field)
        self.assertEqual(summary["unqualified_note_status"], "ambiguous")
        self.assertEqual(summary["unqualified_candidate_count"], 2)
        self.assertEqual(summary["replay"], {"input_records": 39, "occurrences": 39, "collisions": 13, "links": 39, "unresolved_links": 1})

    def test_changed_authority_same_generation_changes_revision(self):
        changed = deepcopy(self.native)
        changed["sources"][0]["claim"] = "Synthetic revised source statement"
        revised = a.adapt_authority(changed, namespace="demo/workshare", locator=replay.PARENT_LOCATOR, synthetic=True)
        self.assertNotEqual(revised["adapter"]["revision"], self.authority["adapter"]["revision"])
        self.assertEqual(changed["generation"], self.native["generation"])

    def test_request_context_mismatches_are_errors(self):
        for field in ("expected_receipt", "expected_generation", "expected_handoff_revision", "expected_authority_revision"):
            with self.subTest(field=field), self.assertRaises(a.AdapterError):
                self.request(**{field: "mismatched"})

    def test_replaying_old_request_against_new_note_is_unresolved(self):
        old_link = self.request()
        changed = deepcopy(self.handoff_document)
        changed["cell_notes"][0]["analyst_note"] = "Revised note"
        updated = a.adapt_handoff(changed, namespace="demo/workbench", locator=replay.HANDOFF_LOCATOR)
        report = self.mapper.reconcile(a.combine([self.authority, updated], [old_link]))
        row = next(r for r in report["links"] if r["link_id"] == "review-1")
        self.assertEqual(row["from"]["status"], "missing")
        self.assertEqual(row["status"], "unresolved")

    def test_missing_source_request_is_diagnosed_not_fabricated(self):
        report = self.mapper.reconcile(a.combine([self.authority, self.handoff], [self.request(source_id="not-present")]))
        row = next(r for r in report["links"] if r["link_id"] == "review-1")
        self.assertEqual(row["to"]["status"], "missing")
        self.assertEqual(report["summary"]["occurrences"], 26)

    def test_different_origins_never_alias_by_source_id(self):
        other = a.adapt_authority(self.native, namespace="different/component", locator="synthetic://other-input", synthetic=True)
        report = self.mapper.reconcile(a.combine([self.authority, other]))
        self.assertEqual(report["summary"]["occurrences"], 26)
        self.assertEqual(report["summary"]["unresolved_links"], 0)
        index = self.mapper.IdentityMap(a.combine([self.authority, other])["records"])
        self.assertEqual(index.resolve({"kind": "source", "id": "ESS-SW-01"})["status"], "ambiguous")
        self.assertEqual(index.resolve(a.select(self.authority["records"][1]))["status"], "resolved")

    def test_equal_json_formatting_is_not_new_content(self):
        compact = a.load_json(a.canonical(self.handoff_document))
        pretty = a.load_json(json.dumps(self.handoff_document, indent=4, ensure_ascii=True))
        left = a.adapt_handoff(compact, namespace="x", locator="synthetic://same")
        right = a.adapt_handoff(pretty, namespace="x", locator="synthetic://same")
        self.assertEqual(left, right)

    def test_changed_provenance_locator_is_explicit_new_revision(self):
        changed = a.adapt_handoff(self.handoff_document, namespace="demo/workbench", locator="synthetic://relocated")
        self.assertNotEqual(changed["adapter"]["revision"], self.handoff["adapter"]["revision"])
        self.assertEqual(changed["adapter"]["document_sha256"], self.handoff["adapter"]["document_sha256"])

    def test_extensions_null_empty_unicode_are_lossless(self):
        doc = deepcopy(self.handoff_document)
        doc["extra"] = {"empty": "", "null": None, "unicode": "résumé — 登録", "literal": "=SUM(1,2)"}
        doc["cell_notes"][0]["new_metadata"] = [False, 0, "0"]
        packet = a.adapt_handoff(doc, namespace="x", locator="synthetic://handoff")
        report = self.mapper.reconcile(packet)
        self.assertEqual(report["extensions"]["adapter"]["original_document"], doc)
        row = next(r for r in report["records"] if r["original"]["kind"] == "observation" and r["original"]["payload"].get("new_metadata"))
        self.assertEqual(row["original"]["payload"]["new_metadata"], [False, 0, "0"])

    def test_duplicate_native_source_and_cells_rejected(self):
        doc = deepcopy(self.native)
        doc["sources"].append(deepcopy(doc["sources"][0]))
        with self.assertRaises(a.AdapterError):
            a.adapt_authority(doc, namespace="x", locator="synthetic://a", synthetic=True)
        doc = deepcopy(self.handoff_document)
        doc["cell_notes"].append(deepcopy(doc["cell_notes"][0]))
        with self.assertRaises(a.AdapterError):
            a.adapt_handoff(doc, namespace="x", locator="synthetic://h")

    def test_authority_flags_are_never_promoted(self):
        for flag in a.FLAGS:
            doc = deepcopy(self.handoff_document)
            doc["authority"][flag] = True
            with self.subTest(flag=flag), self.assertRaises(a.AdapterError):
                a.adapt_handoff(doc, namespace="x", locator="synthetic://h")
        doc = deepcopy(self.handoff_document)
        doc["report_mode"] = "TRUSTED"
        with self.assertRaises(a.AdapterError):
            a.adapt_handoff(doc, namespace="x", locator="synthetic://h")

    def test_synthetic_label_not_truthy_string_and_cross_label_request_rejected(self):
        with self.assertRaises(a.AdapterError):
            a.adapt_authority(self.native, namespace="x", locator="synthetic://a", synthetic="true")
        other = deepcopy(self.handoff)
        other["adapter"]["synthetic"] = False
        with self.assertRaises(a.AdapterError):
            a.review_request(self.authority, other, source_id="ESS-SW-01", group="ESS", dimension="software_development",
                expected_receipt="d" * 64, expected_generation=self.native["generation"],
                expected_authority_revision=self.authority["adapter"]["revision"], expected_handoff_revision=other["adapter"]["revision"],
                request_id="mixed", rationale="not allowed to relabel")

    def test_bad_json_and_native_shapes_fail_explicitly(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '[]', '{broken'):
            with self.assertRaises(a.AdapterError):
                a.load_json(raw)
        for value in (None, "", 123):
            doc = deepcopy(self.native)
            doc["sources"][0]["source_id"] = value
            with self.assertRaises(a.AdapterError):
                a.adapt_authority(doc, namespace="x", locator="synthetic://a", synthetic=True)

    def test_inputs_are_not_mutated(self):
        before_native, before_handoff = deepcopy(self.native), deepcopy(self.handoff_document)
        a.adapt_authority(self.native, namespace="x", locator="synthetic://a", synthetic=True)
        a.adapt_handoff(self.handoff_document, namespace="y", locator="synthetic://h")
        self.mapper.reconcile(a.combine([self.authority, self.handoff], [self.request()]))
        self.assertEqual(self.native, before_native)
        self.assertEqual(self.handoff_document, before_handoff)

    def test_cli_and_python_adapter_agree_and_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "adapted.json"
            cmd = [sys.executable, str(HERE / "adapter.py"), "authority", str(replay.PARENT_FIXTURE), str(output),
                   "--namespace", "demo/workshare", "--locator", replay.PARENT_LOCATOR, "--synthetic"]
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(a.load_json(output.read_text(encoding="utf-8")), self.authority)
            before = output.read_bytes()
            repeated = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(output.read_bytes(), before)

    def test_two_replay_runs_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            left, right = Path(tmp) / "one", Path(tmp) / "two"
            for output in (left, right):
                run = subprocess.run([sys.executable, str(HERE / "replay.py"), str(output)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(len(list(left.iterdir())), 9)
            for path in left.iterdir():
                self.assertEqual(path.read_bytes(), (right / path.name).read_bytes(), path.name)

    def test_generic_module_names_cannot_hijack_sibling_import(self):
        previous = sys.modules.get("adapter")
        sys.modules["adapter"] = ModuleType("adapter")
        try:
            loaded = runpy.run_path(str(HERE / "replay.py"), run_name="isolated_replay_test")
            self.assertEqual(loaded["a"].SCHEMA, a.SCHEMA)
            self.assertEqual(Path(loaded["a"].__file__).resolve(), (HERE / "adapter.py").resolve())
        finally:
            if previous is None:
                sys.modules.pop("adapter", None)
            else:
                sys.modules["adapter"] = previous

    def test_no_fuzzy_dimension_or_automatic_equivalence(self):
        report = self.mapper.reconcile(a.combine([self.authority, self.handoff], [self.request()]))
        self.assertEqual(report["equivalences"], [])
        self.assertEqual(self.authority["records"][1]["payload"]["dimension"], "software")
        self.assertEqual(self.handoff["records"][1]["payload"]["dimension"], "software_development")
        self.assertTrue(all(link["original"]["relation"] != "supported_by" for link in report["links"]))


if __name__ == "__main__":
    unittest.main()
